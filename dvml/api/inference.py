"""Inference endpoints — load a registered model and score inputs."""
from __future__ import annotations

import base64

from flask import Blueprint, g, jsonify, request

from ..core.db import db
from ..models import Model
from ..ml import model_loader
from ..ml.features import load_feature_cache
from ..ml.runner import handle_runner_call
from .deps import require_auth

bp = Blueprint("inference", __name__, url_prefix="/api/inference")

# Small per-process cache of reconstructed estimators.
_LOADED: dict[int, object] = {}


def _get_estimator(model: Model):
    if model.id not in _LOADED:
        _LOADED[model.id] = model_loader.load_model(model.artifact_path, model.framework)
    return _LOADED[model.id]


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
