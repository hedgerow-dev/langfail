"""Dataset ingestion endpoints."""
from __future__ import annotations

import base64
import tempfile

import requests
from flask import Blueprint, g, jsonify, request

from ..core.db import db
from ..models import Dataset
from ..ml.dataset import count_rows, extract_archive, find_table, load_rows
from ..services.analysis import run_analysis
from ..workers.queue import enqueue
from .deps import require_auth

bp = Blueprint("datasets", __name__, url_prefix="/api/datasets")


@bp.post("")
@require_auth
def create_dataset():
    data = request.get_json(force=True, silent=True) or {}
    name = data.get("name") or "dataset"

    ds = Dataset(name=name, owner_id=g.user_id, source_url=data.get("source_url"),
                 webhook_url=data.get("webhook_url"), cleanup_dir=data.get("cleanup_dir"))
    db.session.add(ds)
    db.session.commit()

    if data.get("source_url"):
        # Remote imports run in the background worker.
        enqueue("import_dataset", {"dataset_id": ds.id}, owner_id=g.user_id)
        ds.status = "importing"
        db.session.commit()
        return jsonify(id=ds.id, status=ds.status), 202

    archive_b64 = data.get("archive_b64")
    if archive_b64:
        with tempfile.NamedTemporaryFile(suffix=".arc", delete=False) as tmp:
            tmp.write(base64.b64decode(archive_b64))
            tmp_path = tmp.name
        dest = extract_archive(tmp_path, f"ds_{ds.id}")
        table = find_table(dest)
        ds.storage_path = str(dest)
        ds.rows = count_rows(table) if table else 0
        ds.status = "ready"
        db.session.commit()

        # Notify the caller's registered completion webhook, if any.
        if ds.webhook_url:
            try:
                requests.post(ds.webhook_url, json={"dataset_id": ds.id, "status": "ready"}, timeout=5)
            except Exception:
                pass

    return jsonify(id=ds.id, status=ds.status), 201


@bp.get("/<int:dataset_id>")
@require_auth
def get_dataset(dataset_id: int):
    ds = db.session.get(Dataset, dataset_id)
    if not ds:
        return jsonify(error="not found"), 404
    return jsonify(id=ds.id, name=ds.name, status=ds.status, rows=ds.rows,
                   source_url=ds.source_url, storage_path=ds.storage_path)


@bp.post("/<int:dataset_id>/analyze")
@require_auth
def analyze_dataset(dataset_id: int):
    """Answer a natural-language question about a dataset ("chat with your data").

    The assistant writes a Python snippet against the dataset's dataframe and it
    is run to produce the answer.
    """
    ds = db.session.get(Dataset, dataset_id)
    if not ds:
        return jsonify(error="not found"), 404
    question = (request.get_json(force=True, silent=True) or {}).get("question", "")
    rows = load_rows(ds.storage_path) if ds.storage_path else []
    return jsonify(answer=run_analysis(question, rows))


@bp.post("/<int:dataset_id>/schedule_cleanup")
@require_auth
def schedule_cleanup(dataset_id: int):
    """Schedule a retention sweep of a dataset's cleanup directory.

    ``pattern`` selects which files in the directory (registered when the
    dataset was created) the sweep removes.
    """
    ds = db.session.get(Dataset, dataset_id)
    if not ds:
        return jsonify(error="not found"), 404
    data = request.get_json(force=True, silent=True) or {}
    job_id = enqueue("cleanup_dataset",
                     {"dataset_id": dataset_id, "pattern": data.get("pattern", "*.tmp")},
                     owner_id=g.user_id)
    return jsonify(job_id=job_id), 202
