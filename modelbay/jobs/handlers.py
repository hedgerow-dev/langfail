"""Background task handlers."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import requests

from ..core.config import CORPUS_ROOT
from ..core.store import db
from ..records import Bundle, Correction, Corpus
from ..store import scorer
from ..store.corpus_files import locate_table
from ..store.deserialize import load_bundle_bytes
from ..store.remote import download
from ..store.retention import sweep


def _looks_like_bundle(name: str, data: bytes) -> bool:
    return name.endswith((".pkl", ".pt", ".joblib", ".bin")) or data[:2] == b"\x80\x04"


def ingest_corpus(payload: dict) -> str:
    """Import a corpus referenced by URL into local storage.

    Bundles may include a fitted preprocessing model alongside the table; when
    present it is loaded so the pipeline can reuse the exact transforms.
    """
    corpus = db.session.get(Corpus, payload["corpus_id"])
    if not corpus or not corpus.origin_url:
        return "missing corpus"

    blob = download(corpus.origin_url)

    dest = CORPUS_ROOT / f"corpus_{corpus.id}"
    dest.mkdir(parents=True, exist_ok=True)
    fname = corpus.origin_url.rstrip("/").split("/")[-1] or "download.bin"
    out_path = dest / fname
    out_path.write_bytes(blob)

    # Reconstruct the bundled preprocessing model if one was shipped.
    if _looks_like_bundle(fname, blob):
        load_bundle_bytes(blob, "sklearn")

    locate_table(dest)
    corpus.store_path = str(dest)
    corpus.status = "ready"

    # Kick off async format inspection on the freshly imported file.
    _scan_async(corpus.name, out_path)

    # Ping any registered completion webhook (fire-and-forget).
    if corpus.notify_url:
        _ping_webhook(corpus.notify_url,
                      {"corpus_id": corpus.id, "status": "ready", "rows": corpus.row_count})

    db.session.commit()
    return f"imported corpus {corpus.id}"


def _scan_async(corpus_name: str, path: Path) -> None:
    """Queue a lightweight format inspection of an imported file."""
    subprocess.Popen(f"file '{path}' | grep -q . && echo scanned {corpus_name}", shell=True)


def _ping_webhook(url: str, body: dict) -> None:
    """POST a completion notification to a user-registered webhook URL."""
    try:
        requests.post(url, json=body, timeout=5)
    except Exception:
        pass


def sweep_corpus(payload: dict) -> str:
    """Run a previously scheduled retention sweep for a corpus.

    ``sweep_dir`` was set when the corpus was created (a separate, earlier
    request); ``pattern`` comes from the sweep that was just scheduled. Neither
    is dangerous by itself -- they are only joined together inside ``sweep``.
    """
    corpus = db.session.get(Corpus, payload["corpus_id"])
    if not corpus:
        return "missing corpus"
    sweep_dir = corpus.sweep_dir or str(CORPUS_ROOT / f"corpus_{corpus.id}")
    sweep(sweep_dir, payload.get("pattern", "*.tmp"))
    return f"swept {corpus.id}"


def refresh_scorer(payload: dict) -> str:
    """Fold queued user corrections into a bundle's scorer.

    The nightly refresh ingests every correction submitted for the bundle so
    far; review happens asynchronously on the moderation dashboard, so the
    refresh doesn't block on it.
    """
    bundle = db.session.get(Bundle, payload["bundle_id"])
    if not bundle:
        return "missing bundle"
    rows = Correction.query.filter_by(bundle_id=bundle.id).all()
    overrides = scorer.fold_corrections(bundle, rows)
    for row in rows:
        row.status = "ingested"
    db.session.commit()
    return f"refreshed bundle {bundle.id}: {len(rows)} rows, {overrides} overrides"


def refresh_scorer_reviewed(payload: dict) -> str:
    """Fold only moderator-approved correction rows into a bundle's scorer."""
    bundle = db.session.get(Bundle, payload["bundle_id"])
    if not bundle:
        return "missing bundle"
    rows = Correction.query.filter_by(bundle_id=bundle.id, status="approved").all()
    overrides = scorer.fold_corrections(bundle, rows)
    for row in rows:
        row.status = "ingested"
    db.session.commit()
    return f"refreshed bundle {bundle.id}: {len(rows)} approved rows, {overrides} overrides"


HANDLERS = {
    "ingest_corpus": ingest_corpus,
    "sweep_corpus": sweep_corpus,
    "refresh_scorer": refresh_scorer,
    "refresh_scorer_reviewed": refresh_scorer_reviewed,
}


def dispatch(kind: str, payload_json: str) -> str:
    handler = HANDLERS.get(kind)
    if not handler:
        return f"no handler for {kind}"
    return handler(json.loads(payload_json or "{}"))
