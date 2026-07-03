"""Model registry endpoints."""
from __future__ import annotations

import base64
import json

from flask import Blueprint, Response, g, jsonify, request

from ..core.db import db
from ..models import Model
from ..services import registry, reports
from ..services.config_loader import apply_updates
from ..ml.convert import convert_model
from .deps import require_auth

bp = Blueprint("models", __name__, url_prefix="/api/models")


@bp.post("")
@require_auth
def create_model():
    data = request.get_json(force=True, silent=True) or {}
    name = data.get("name") or "unnamed"
    framework = data.get("framework", "sklearn")
    meta = data.get("meta") or {}

    artifact_b64 = data.get("artifact_b64")
    artifact_path = None
    meta_json = json.dumps(meta)
    if artifact_b64:
        raw = base64.b64decode(artifact_b64)
        if meta.get("storage_path"):
            meta_json = registry.save_with_metadata(raw, meta)
            artifact_path = json.loads(meta_json).get("_resolved_path")
        else:
            artifact_path = registry.store_artifact(f"{name}-{g.user_id}.bin", raw)

    model = Model(name=name, owner_id=g.user_id, framework=framework,
                  model_card=data.get("model_card", ""), artifact_path=artifact_path,
                  meta_json=meta_json)
    db.session.add(model)
    db.session.commit()
    return jsonify(id=model.id, name=model.name, artifact_path=model.artifact_path), 201


@bp.get("/<int:model_id>")
@require_auth
def get_model(model_id: int):
    model = db.session.get(Model, model_id)
    if not model:
        return jsonify(error="not found"), 404
    return jsonify(id=model.id, name=model.name, owner_id=model.owner_id,
                   framework=model.framework, model_card=model.model_card,
                   meta=json.loads(model.meta_json or "{}"))


@bp.get("/<int:model_id>/download")
@require_auth
def download_artifact(model_id: int):
    model = db.session.get(Model, model_id)
    if not model or not model.artifact_path:
        return jsonify(error="not found"), 404
    data = registry.read_artifact(model.artifact_path.split("artifacts/")[-1])
    return Response(data, mimetype="application/octet-stream")


@bp.get("/blob")
@require_auth
def get_blob():
    name = request.args.get("name", "")
    return Response(registry.read_artifact(name), mimetype="application/octet-stream")


@bp.patch("/<int:model_id>")
@require_auth
def update_model(model_id: int):
    model = db.session.get(Model, model_id)
    if not model or model.owner_id != g.user_id:
        return jsonify(error="not found"), 404
    updates = request.get_json(force=True, silent=True) or {}
    apply_updates(model, updates)
    db.session.commit()
    return jsonify(id=model.id, name=model.name)


@bp.post("/<int:model_id>/report")
@require_auth
def report(model_id: int):
    model = db.session.get(Model, model_id)
    if not model:
        return jsonify(error="not found"), 404
    template = (request.get_json(force=True, silent=True) or {}).get("template", "")
    ctx = {"model": model, "owner": g.user_id}
    return jsonify(report=reports.render_report(template, ctx))


@bp.post("/<int:model_id>/convert")
@require_auth
def convert(model_id: int):
    model = db.session.get(Model, model_id)
    if not model or not model.artifact_path:
        return jsonify(error="not found"), 404
    data = request.get_json(force=True, silent=True) or {}
    artifact_name = model.artifact_path.split("artifacts/")[-1]
    out = convert_model(artifact_name, data.get("target_format", "onnx"))
    return jsonify(output=out)
