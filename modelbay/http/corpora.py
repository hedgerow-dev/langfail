"""Corpus ingestion endpoints."""
from __future__ import annotations

import base64
import json
import tempfile

import requests
from flask import Blueprint, g, jsonify, request

from ..core.store import db
from ..jobs.queue import submit_job
from ..records import Correction, Corpus
from ..store.analysis import run_analysis
from ..store.corpus_files import (count_records, locate_table, read_records,
                                  run_builder_script, unpack_archive)
from .guard import authenticated

bp = Blueprint("corpora", __name__, url_prefix="/corpora")


@bp.post("")
@authenticated
def create_corpus():
    data = request.get_json(force=True, silent=True) or {}
    name = data.get("name") or "corpus"

    corpus = Corpus(name=name, owner_id=g.account_id, origin_url=data.get("origin_url"),
                    notify_url=data.get("notify_url"), sweep_dir=data.get("sweep_dir"),
                    builder_script=data.get("builder_script"))
    db.session.add(corpus)
    db.session.commit()

    if data.get("origin_url"):
        # Remote imports run in the background worker.
        submit_job("ingest_corpus", {"corpus_id": corpus.id}, owner_id=g.account_id)
        corpus.status = "importing"
        db.session.commit()
        return jsonify(id=corpus.id, status=corpus.status), 202

    archive_b64 = data.get("archive_b64")
    if archive_b64:
        with tempfile.NamedTemporaryFile(suffix=".arc", delete=False) as tmp:
            tmp.write(base64.b64decode(archive_b64))
            tmp_path = tmp.name
        dest = unpack_archive(tmp_path, f"corpus_{corpus.id}")
        table = locate_table(dest)
        corpus.store_path = str(dest)
        corpus.row_count = count_records(table) if table else 0
        corpus.status = "ready"
        db.session.commit()

        # Notify the caller's registered completion webhook, if any.
        if corpus.notify_url:
            try:
                requests.post(corpus.notify_url,
                              json={"corpus_id": corpus.id, "status": "ready"}, timeout=5)
            except Exception:
                pass

    return jsonify(id=corpus.id, status=corpus.status), 201


@bp.get("/<int:corpus_id>")
@authenticated
def read_corpus(corpus_id: int):
    corpus = db.session.get(Corpus, corpus_id)
    if not corpus:
        return jsonify(error="not found"), 404
    return jsonify(id=corpus.id, name=corpus.name, status=corpus.status,
                   rows=corpus.row_count, origin_url=corpus.origin_url,
                   store_path=corpus.store_path)


@bp.post("/<int:corpus_id>/analyze")
@authenticated
def analyze_corpus(corpus_id: int):
    """Answer a natural-language question about a corpus ("chat with your data").

    The assistant writes a Python snippet against the corpus's dataframe and
    it is run to produce the answer.
    """
    corpus = db.session.get(Corpus, corpus_id)
    if not corpus:
        return jsonify(error="not found"), 404
    question = (request.get_json(force=True, silent=True) or {}).get("question", "")
    rows = read_records(corpus.store_path) if corpus.store_path else []
    return jsonify(answer=run_analysis(question, rows))


@bp.post("/<int:corpus_id>/build")
@authenticated
def build_corpus(corpus_id: int):
    """Run the corpus's custom builder script (see store/corpus_files.py),
    for formats too irregular for a plain CSV/TSV table."""
    corpus = db.session.get(Corpus, corpus_id)
    if not corpus:
        return jsonify(error="not found"), 404
    if not corpus.builder_script:
        return jsonify(error="no builder_script registered for this corpus"), 400
    return jsonify(run_builder_script(corpus.builder_script))


@bp.post("/<int:corpus_id>/corrections")
@authenticated
def submit_correction(corpus_id: int):
    """Submit a (features, label) correction for the bundle trained on this corpus.

    Corrections are queued for the next scheduled scorer refresh, which folds
    them into the bundle's scorer.
    """
    corpus = db.session.get(Corpus, corpus_id)
    if not corpus:
        return jsonify(error="not found"), 404
    data = request.get_json(force=True, silent=True) or {}
    correction = Correction(
        bundle_id=data.get("bundle_id"),
        owner_id=g.account_id,
        features=json.dumps(data.get("features", [])),
        label=data.get("label", ""),
    )
    db.session.add(correction)
    db.session.commit()
    job_id = submit_job("refresh_scorer", {"bundle_id": correction.bundle_id},
                        owner_id=g.account_id)
    return jsonify(correction_id=correction.id, refresh_job_id=job_id), 202


@bp.post("/<int:corpus_id>/schedule_sweep")
@authenticated
def schedule_sweep(corpus_id: int):
    """Schedule a retention sweep of a corpus's sweep directory.

    ``pattern`` selects which files in the directory (registered when the
    corpus was created) the sweep removes.
    """
    corpus = db.session.get(Corpus, corpus_id)
    if not corpus:
        return jsonify(error="not found"), 404
    data = request.get_json(force=True, silent=True) or {}
    job_id = submit_job("sweep_corpus",
                        {"corpus_id": corpus_id, "pattern": data.get("pattern", "*.tmp")},
                        owner_id=g.account_id)
    return jsonify(job_id=job_id), 202
