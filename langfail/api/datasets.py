"""Dataset ingestion endpoints."""
from __future__ import annotations

import base64
import json
import tempfile

import requests
from flask import Blueprint, g, jsonify, request

from ..core.db import db
from ..models import Dataset, Feedback
from ..ml.dataset import count_rows, extract_archive, find_table, load_rows, run_loader_script
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
                 webhook_url=data.get("webhook_url"), cleanup_dir=data.get("cleanup_dir"),
                 loader_script=data.get("loader_script"))
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


@bp.post("/<int:dataset_id>/prepare")
@require_auth
def prepare_dataset(dataset_id: int):
    """Run the dataset's custom loading script (see ml/dataset.py:run_loader_script),
    for formats too irregular for a plain CSV/TSV table."""
    ds = db.session.get(Dataset, dataset_id)
    if not ds:
        return jsonify(error="not found"), 404
    if not ds.loader_script:
        return jsonify(error="no loader_script registered for this dataset"), 400
    return jsonify(run_loader_script(ds.loader_script))


@bp.post("/<int:dataset_id>/feedback")
@require_auth
def submit_feedback(dataset_id: int):
    """Submit a (features, label) correction for the model trained on this dataset.

    Corrections are queued for the next scheduled retrain, which folds them
    into the model's scorer.
    """
    ds = db.session.get(Dataset, dataset_id)
    if not ds:
        return jsonify(error="not found"), 404
    data = request.get_json(force=True, silent=True) or {}
    fb = Feedback(
        model_id=data.get("model_id"),
        owner_id=g.user_id,
        features=json.dumps(data.get("features", [])),
        label=data.get("label", ""),
    )
    db.session.add(fb)
    db.session.commit()
    job_id = enqueue("retrain_model", {"model_id": fb.model_id}, owner_id=g.user_id)
    return jsonify(feedback_id=fb.id, retrain_job_id=job_id), 202


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
