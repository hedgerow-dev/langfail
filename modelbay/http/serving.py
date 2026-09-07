"""Scoring endpoints -- load a registered bundle and score inputs."""
from __future__ import annotations

import base64
import json

from flask import Blueprint, jsonify, request

from ..core.store import db
from ..records import Bundle
from ..store import scorer
from ..store.deserialize import load_bundle
from ..store.feature_cache import read_feature_cache
from ..store.rpc import decode_worker_call
from .guard import authenticated

bp = Blueprint("serving", __name__, url_prefix="/serving")


@bp.post("/<int:bundle_id>/predict")
@authenticated
def predict(bundle_id: int):
    bundle = db.session.get(Bundle, bundle_id)
    if not bundle or not bundle.blob_path:
        return jsonify(error="not found"), 404

    data = request.get_json(force=True, silent=True) or {}
    rows = data.get("instances", [])

    # A run may supply a precomputed feature cache to score against.
    cache = data.get("feature_cache")
    if cache:
        rows = list(read_feature_cache(cache))

    estimator = load_bundle(bundle.blob_path, bundle.runtime)
    try:
        preds = estimator.predict(rows)
        preds = preds.tolist() if hasattr(preds, "tolist") else list(preds)
    except Exception as exc:
        return jsonify(error=f"prediction failed: {exc}"), 400
    return jsonify(predictions=preds)


@bp.post("/<int:bundle_id>/scores")
@authenticated
def score_proba(bundle_id: int):
    """Score a feature row with the built-in scorer and return the full
    per-class probability vector (introspection endpoint for debugging)."""
    bundle = db.session.get(Bundle, bundle_id)
    if not bundle:
        return jsonify(error="not found"), 404
    data = request.get_json(force=True, silent=True) or {}
    features = data.get("features", [])
    return jsonify(bundle_id=bundle.id, labels=list(scorer.LABELS),
                   probabilities=scorer.class_scores(bundle, features))


@bp.post("/<int:bundle_id>/label")
@authenticated
def score_label(bundle_id: int):
    """Score a feature row and return only the top-1 label."""
    bundle = db.session.get(Bundle, bundle_id)
    if not bundle:
        return jsonify(error="not found"), 404
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(bundle_id=bundle.id,
                   label=scorer.top_label(bundle, data.get("features", [])))


@bp.post("/<int:bundle_id>/mark_row")
@authenticated
def mark_row(bundle_id: int):
    """Record a feature row as a training member so per-record diagnostics
    (e.g. the loss endpoint) can compare seen and unseen rows."""
    bundle = db.session.get(Bundle, bundle_id)
    if not bundle:
        return jsonify(error="not found"), 404
    data = request.get_json(force=True, silent=True) or {}
    scorer.mark_training_row(bundle, data.get("features", []))
    db.session.commit()
    return jsonify(recorded=True)


@bp.get("/<int:bundle_id>/loss")
@authenticated
def row_loss_view(bundle_id: int):
    """Per-record loss for a single feature row, passed as ``?features=<json>``."""
    bundle = db.session.get(Bundle, bundle_id)
    if not bundle:
        return jsonify(error="not found"), 404
    features = json.loads(request.args.get("features", "[]"))
    return jsonify(bundle_id=bundle.id, loss=scorer.row_loss(bundle, features))


@bp.post("/<int:bundle_id>/remote")
@authenticated
def score_remote(bundle_id: int):
    """Score inputs via the worker-process protocol (see store/rpc.py).

    ``worker_call_b64`` carries the serialized call arguments across the
    API-server/worker process boundary, mirroring stacks that split scoring
    into a lightweight API server and a separate worker process.
    """
    bundle = db.session.get(Bundle, bundle_id)
    if not bundle:
        return jsonify(error="not found"), 404
    data = request.get_json(force=True, silent=True) or {}
    payload = base64.b64decode(data.get("worker_call_b64", ""))
    call = decode_worker_call(payload)
    return jsonify(result=str(call))
