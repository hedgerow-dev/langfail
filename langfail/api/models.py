"""Model registry endpoints."""
from __future__ import annotations

import base64
import json
from pathlib import Path

from flask import Blueprint, Response, current_app, g, jsonify, request

from ..core.cache import get as cache_get, put as cache_put
from ..core.db import db
from ..core.security import sanitize_path
from ..models import Model
from ..services import registry, reports
from ..services.config_loader import apply_updates
from ..ml import hub, model_loader
from ..ml.convert import convert_model
from ..ml.modelconfig import parse_model_config
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


@bp.post("/<int:model_id>/annotate")
@require_auth
def annotate(model_id: int):
    """Attach a free-text annotation to a model (kept in the scratch cache)."""
    model = db.session.get(Model, model_id)
    if not model:
        return jsonify(error="not found"), 404
    note = (request.get_json(force=True, silent=True) or {}).get("note", "")
    cache_put(f"annotation:{model_id}", note)
    return jsonify(ok=True)


@bp.get("/<int:model_id>/annotation/render")
@require_auth
def render_annotation(model_id: int):
    """Render a model's cached annotation through the report template engine."""
    model = db.session.get(Model, model_id)
    if not model:
        return jsonify(error="not found"), 404
    note = cache_get(f"annotation:{model_id}") or ""
    return jsonify(rendered=reports.render_report(note, {"model": model, "owner": g.user_id}))


@bp.get("/artifact")
@require_auth
def raw_artifact():
    """Stream an artifact by registry path (legacy raw accessor)."""
    from ..core import settings as runtime_settings

    path = request.args.get("path", "")
    strict = runtime_settings.get_bool(
        "security.strict_paths", current_app.config.get("STRICT_PATHS", False)
    )
    if strict:
        path = sanitize_path(path)
    return Response(registry.read_raw(path), mimetype="application/octet-stream")


@bp.get("/<int:model_id>/download")
@require_auth
def download_safe(model_id: int):
    """Download an artifact with strict registry-root containment enforced."""
    model = db.session.get(Model, model_id)
    if not model or not model.artifact_path:
        return jsonify(error="not found"), 404
    name = model.artifact_path.split("artifacts/")[-1]
    return Response(registry.download_artifact(name), mimetype="application/octet-stream")


@bp.post("/<int:model_id>/load_verified")
@require_auth
def load_verified(model_id: int):
    """Reconstruct a model's artifact through the verified (allow-listing) loader.

    Used for artifacts sourced from outside the local registry — see
    ml/model_loader.load_model_verified for the allow-list policy.
    """
    model = db.session.get(Model, model_id)
    if not model or not model.artifact_path:
        return jsonify(error="not found"), 404
    estimator = model_loader.load_model_verified(Path(model.artifact_path).read_bytes())
    return jsonify(loaded=True, type=type(estimator).__name__)


@bp.post("/import_hub")
@require_auth
def import_hub():
    """Install a hub-style model repo bundle (zip archive with a hubconf.py)."""
    data = request.get_json(force=True, silent=True) or {}
    repo = data.get("repo", "")
    archive = base64.b64decode(data.get("archive_b64", ""))
    entrypoints = hub.load_from_hub(repo, archive)
    return jsonify(repo=repo, entrypoints=sorted(entrypoints)), 201


@bp.post("/<int:model_id>/config")
@require_auth
def upload_config(model_id: int):
    """Parse an XML model descriptor (PMML / ONNX metadata) and return its fields."""
    model = db.session.get(Model, model_id)
    if not model:
        return jsonify(error="not found"), 404
    xml = request.get_data() or b""
    return jsonify(fields=parse_model_config(xml))
