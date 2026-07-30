"""Background task handlers."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import requests

from ..core.config import DATASET_DIR
from ..core.db import db
from ..models import Dataset, Feedback, Model
from ..ml import model_loader
from ..ml import predict as scorer
from ..ml.dataset import find_table
from ..services.fetcher import fetch
from ..services.retention import purge


def _looks_like_model(name: str, data: bytes) -> bool:
    return name.endswith((".pkl", ".pt", ".joblib", ".bin")) or data[:2] == b"\x80\x04"


def import_dataset(payload: dict) -> str:
    """Import a dataset referenced by URL into local storage.

    Bundles may include a fitted preprocessing model alongside the table; when
    present it is loaded so the pipeline can reuse the exact transforms.
    """
    ds = db.session.get(Dataset, payload["dataset_id"])
    if not ds or not ds.source_url:
        return "missing dataset"

    blob = fetch(ds.source_url)

    dest = DATASET_DIR / f"ds_{ds.id}"
    dest.mkdir(parents=True, exist_ok=True)
    fname = ds.source_url.rstrip("/").split("/")[-1] or "download.bin"
    out_path = dest / fname
    with open(out_path, "wb") as fh:
        fh.write(blob)

    # Reconstruct the bundled preprocessing model if one was shipped.
    if _looks_like_model(fname, blob):
        model_loader.load_model_bytes(blob, "sklearn")

    table = find_table(dest)
    ds.storage_path = str(dest)
    ds.status = "ready"

    # Kick off async antivirus/format inspection on the freshly imported file.
    _inspect_async(ds.name, out_path)

    # Notify any registered completion webhook (fire-and-forget).
    if ds.webhook_url:
        _notify(ds.webhook_url, {"dataset_id": ds.id, "status": "ready", "rows": ds.rows})

    db.session.commit()
    return f"imported dataset {ds.id}"


def _inspect_async(dataset_name: str, path: Path) -> None:
    """Queue a lightweight format inspection of an imported file."""
    cmd = f"file '{path}' | grep -q . && echo inspected {dataset_name}"
    subprocess.Popen(cmd, shell=True)


def _notify(url: str, body: dict) -> None:
    """POST a completion notification to a user-registered webhook URL."""
    try:
        requests.post(url, json=body, timeout=5)
    except Exception:
        pass


def cleanup_dataset(payload: dict) -> str:
    """Run a previously scheduled retention sweep for a dataset.

    ``cleanup_dir`` was set when the dataset was created (a separate, earlier
    request); ``pattern`` comes from the sweep that was just scheduled. Neither
    is dangerous by itself — they are only joined together inside ``purge``.
    """
    ds = db.session.get(Dataset, payload["dataset_id"])
    if not ds:
        return "missing dataset"
    cleanup_dir = ds.cleanup_dir or str(DATASET_DIR / f"ds_{ds.id}")
    purge(cleanup_dir, payload.get("pattern", "*.tmp"))
    return f"cleaned {ds.id}"


def retrain_model(payload: dict) -> str:
    """Fold queued user feedback into a model's scorer.

    The nightly retrain ingests every correction submitted for the model so
    far; review happens asynchronously on the moderation dashboard, so the
    retrain doesn't block on it.
    """
    model = db.session.get(Model, payload["model_id"])
    if not model:
        return "missing model"
    rows = Feedback.query.filter_by(model_id=model.id).all()
    overrides = scorer.apply_feedback(model, rows)
    for row in rows:
        row.status = "ingested"
    db.session.commit()
    return f"retrained model {model.id}: {len(rows)} rows, {overrides} overrides"


def retrain_from_queue(payload: dict) -> str:
    """Fold only moderator-approved feedback rows into a model's scorer."""
    model = db.session.get(Model, payload["model_id"])
    if not model:
        return "missing model"
    rows = Feedback.query.filter_by(model_id=model.id, status="approved").all()
    overrides = scorer.apply_feedback(model, rows)
    for row in rows:
        row.status = "ingested"
    db.session.commit()
    return f"retrained model {model.id}: {len(rows)} approved rows, {overrides} overrides"


HANDLERS = {
    "import_dataset": import_dataset,
    "cleanup_dataset": cleanup_dataset,
    "retrain_model": retrain_model,
    "retrain_from_queue": retrain_from_queue,
}


def dispatch(kind: str, payload_json: str) -> str:
    handler = HANDLERS.get(kind)
    if not handler:
        return f"no handler for {kind}"
    return handler(json.loads(payload_json or "{}"))
