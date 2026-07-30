"""Inference endpoints — load a registered model and score inputs."""
from __future__ import annotations

import base64
import json

from flask import Blueprint, g, jsonify, request

from ..core.db import db
from ..models import Model
from ..ml import model_loader
from ..ml import predict as scorer
from ..ml.features import load_feature_cache
from ..ml.runner import handle_runner_call
from .deps import require_auth

bp = Blueprint("inference", __name__, url_prefix="/api/inference")

# Small per-process cache of reconstructed estimators.
_LOADED: dict[int, tuple[tuple, object]] = {}


def _get_estimator(model: Model):
    # Keyed by artifact path and framework as well as id, so replacing a
    # model's artifact serves the new one instead of the cached estimator
    # built from the old bytes.
    key = (model.id, model.artifact_path, model.framework)
    cached = _LOADED.get(model.id)
    if cached is None or cached[0] != key:
        _LOADED[model.id] = (key, model_loader.load_model(model.artifact_path,
                                                          model.framework))
    return _LOADED[model.id][1]


@bp.post("/<int:model_id>/predict")
@require_auth
def predict(model_id: int):
    model = db.session.get(Model, model_id)
    if not model or not model.artifact_path:
        return jsonify(error="not found"), 404

    data = request.get_json(force=True, silent=True) or {}
    rows = data.get("instances", [])

    # An experiment may supply a precomputed feature cache to score against.
    cache = data.get("feature_cache")
    if cache:
        rows = list(load_feature_cache(cache))

    estimator = _get_estimator(model)
    try:
        preds = estimator.predict(rows)
        preds = preds.tolist() if hasattr(preds, "tolist") else list(preds)
    except Exception as exc:
        return jsonify(error=f"prediction failed: {exc}"), 400
    return jsonify(predictions=preds)


@bp.post("/<int:model_id>/predict_proba")
@require_auth
def predict_proba(model_id: int):
    """Score a feature row with the built-in scorer and return the full
    per-class probability vector (introspection endpoint for debugging)."""
    model = db.session.get(Model, model_id)
    if not model:
        return jsonify(error="not found"), 404
    data = request.get_json(force=True, silent=True) or {}
    features = data.get("features", [])
    return jsonify(model_id=model.id, classes=list(scorer.CLASSES),
                   probabilities=scorer.predict_proba(model, features))


@bp.post("/<int:model_id>/predict_label")
@require_auth
def predict_label(model_id: int):
    """Score a feature row and return only the top-1 label."""
    model = db.session.get(Model, model_id)
    if not model:
        return jsonify(error="not found"), 404
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(model_id=model.id, label=scorer.predict_label(model, data.get("features", [])))


@bp.post("/<int:model_id>/train_row")
@require_auth
def train_row(model_id: int):
    """Record a feature row as a training member so per-record diagnostics
    (e.g. the loss endpoint) can compare seen and unseen rows."""
    model = db.session.get(Model, model_id)
    if not model:
        return jsonify(error="not found"), 404
    data = request.get_json(force=True, silent=True) or {}
    scorer.register_training_row(model, data.get("features", []))
    db.session.commit()
    return jsonify(recorded=True)


@bp.get("/<int:model_id>/loss")
@require_auth
def row_loss(model_id: int):
    """Per-record loss for a single feature row, passed as ``?features=<json>``."""
    model = db.session.get(Model, model_id)
    if not model:
        return jsonify(error="not found"), 404
    features = json.loads(request.args.get("features", "[]"))
    return jsonify(model_id=model.id, loss=scorer.record_loss(model, features))


@bp.post("/<int:model_id>/predict_remote")
@require_auth
def predict_remote(model_id: int):
    """Score inputs via the runner-process protocol (see ml/runner.py).

    ``runner_call_b64`` carries the serialized call arguments across the
    API-server/runner process boundary, mirroring frameworks that split
    inference into a lightweight API server and a separate runner process.
    """
    model = db.session.get(Model, model_id)
    if not model:
        return jsonify(error="not found"), 404
    data = request.get_json(force=True, silent=True) or {}
    payload = base64.b64decode(data.get("runner_call_b64", ""))
    call = handle_runner_call(payload)
    return jsonify(result=str(call))
