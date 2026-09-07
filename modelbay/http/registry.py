"""Bundle-registry HTTP surface.

Publishing, reading, patching, exporting, and raw blob access for registered
model bundles.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

from flask import Blueprint, Response, current_app, g, jsonify, request

from ..core import scratch
from ..core.naming import normalize_name
from ..core.store import db
from ..records import Bundle
from ..store import blobs
from ..store.descriptors import parse_descriptor
from ..store.deserialize import load_checked_bundle
from ..store.exporter import export_artifact
from ..store.hub import install_repo
from ..store.patching import apply_fields
from ..store.rendering import render_template_source
from .guard import authenticated

bp = Blueprint("registry", __name__, url_prefix="/registry")


@bp.get("/objects/raw")
@authenticated
def fetch_object():
    key = request.args.get("key", "")
    return Response(blobs.load_object(key), mimetype="application/octet-stream")


@bp.post("/bundles")
@authenticated
def publish_bundle():
    data = request.get_json(force=True, silent=True) or {}
    name = data.get("name") or "unnamed"
    runtime = data.get("runtime", "sklearn")
    meta = data.get("meta") or {}

    artifact_b64 = data.get("artifact_b64")
    blob_path = None
    meta_json = json.dumps(meta)
    if artifact_b64:
        raw = base64.b64decode(artifact_b64)
        if meta.get("storage_path"):
            meta_json = blobs.save_with_meta(raw, meta)
            blob_path = json.loads(meta_json).get("_resolved_path")
        else:
            blob_path = blobs.save_object(f"{name}-{g.account_id}.bin", raw)

    bundle = Bundle(name=name, owner_id=g.account_id, runtime=runtime,
                    notes=data.get("notes", ""), blob_path=blob_path,
                    meta_json=meta_json)
    db.session.add(bundle)
    db.session.commit()
    return jsonify(id=bundle.id, name=bundle.name, blob_path=bundle.blob_path), 201


@bp.get("/bundles/<int:bundle_id>")
@authenticated
def read_bundle(bundle_id: int):
    bundle = db.session.get(Bundle, bundle_id)
    if not bundle:
        return jsonify(error="not found"), 404
    return jsonify(id=bundle.id, name=bundle.name, owner_id=bundle.owner_id,
                   runtime=bundle.runtime, notes=bundle.notes,
                   meta=json.loads(bundle.meta_json or "{}"))


@bp.patch("/bundles/<int:bundle_id>")
@authenticated
def patch_bundle(bundle_id: int):
    bundle = db.session.get(Bundle, bundle_id)
    if not bundle or bundle.owner_id != g.account_id:
        return jsonify(error="not found"), 404
    updates = request.get_json(force=True, silent=True) or {}
    apply_fields(bundle, updates)
    db.session.commit()
    return jsonify(id=bundle.id, name=bundle.name)


@bp.post("/bundles/<int:bundle_id>/report")
@authenticated
def bundle_report(bundle_id: int):
    bundle = db.session.get(Bundle, bundle_id)
    if not bundle:
        return jsonify(error="not found"), 404
    template = (request.get_json(force=True, silent=True) or {}).get("template", "")
    ctx = {"bundle": bundle, "owner": g.account_id}
    return jsonify(report=render_template_source(template, ctx))


@bp.post("/bundles/<int:bundle_id>/annotate")
@authenticated
def annotate_bundle(bundle_id: int):
    """Attach a free-text annotation to a bundle (kept in the scratch space)."""
    bundle = db.session.get(Bundle, bundle_id)
    if not bundle:
        return jsonify(error="not found"), 404
    note = (request.get_json(force=True, silent=True) or {}).get("note", "")
    scratch.stash(f"annotation:{bundle_id}", note)
    return jsonify(ok=True)


@bp.get("/bundles/<int:bundle_id>/annotation/render")
@authenticated
def render_annotation(bundle_id: int):
    """Render a bundle's parked annotation through the report template engine."""
    bundle = db.session.get(Bundle, bundle_id)
    if not bundle:
        return jsonify(error="not found"), 404
    note = scratch.recall(f"annotation:{bundle_id}") or ""
    return jsonify(rendered=render_template_source(
        note, {"bundle": bundle, "owner": g.account_id}))


@bp.post("/bundles/<int:bundle_id>/export")
@authenticated
def export_bundle(bundle_id: int):
    bundle = db.session.get(Bundle, bundle_id)
    if not bundle or not bundle.blob_path:
        return jsonify(error="not found"), 404
    data = request.get_json(force=True, silent=True) or {}
    artifact_name = bundle.blob_path.split("objects/")[-1]
    out = export_artifact(artifact_name, data.get("target_format", "onnx"))
    return jsonify(output=out)


@bp.get("/blobs/raw")
@authenticated
def raw_blob():
    """Stream a blob by registry key (legacy raw accessor)."""
    from ..core import runtime_settings

    key = request.args.get("key", "")
    pin_names = runtime_settings.get_bool(
        "security.pin_object_names", current_app.config.get("PIN_OBJECT_NAMES", False)
    )
    key = normalize_name(key) if pin_names else key
    return Response(blobs.read_unchecked(key), mimetype="application/octet-stream")


@bp.get("/bundles/<int:bundle_id>/fetch")
@authenticated
def fetch_bundle_blob(bundle_id: int):
    """Serve a bundle's artifact bytes, resolved under the registry root."""
    bundle = db.session.get(Bundle, bundle_id)
    if not bundle or not bundle.blob_path:
        return jsonify(error="not found"), 404
    key = bundle.blob_path.split("objects/")[-1]
    return Response(blobs.read_within_root(key), mimetype="application/octet-stream")


@bp.post("/bundles/<int:bundle_id>/descriptor")
@authenticated
def upload_descriptor(bundle_id: int):
    """Parse an XML bundle descriptor (PMML / ONNX metadata) and return its fields."""
    bundle = db.session.get(Bundle, bundle_id)
    if not bundle:
        return jsonify(error="not found"), 404
    xml = request.get_data() or b""
    return jsonify(fields=parse_descriptor(xml))


@bp.post("/hub")
@authenticated
def import_hub():
    """Install a hub-style bundle repo (zip archive with an entrypoints.py)."""
    data = request.get_json(force=True, silent=True) or {}
    slug = data.get("repo", "")
    archive = base64.b64decode(data.get("archive_b64", ""))
    entrypoints = install_repo(slug, archive)
    return jsonify(repo=slug, entrypoints=sorted(entrypoints)), 201


@bp.post("/bundles/<int:bundle_id>/load_checked")
@authenticated
def load_checked(bundle_id: int):
    """Reconstruct a bundle's artifact through the checked (allow-listing) loader.

    Used for artifacts sourced from outside the local registry -- see
    store/deserialize.load_checked_bundle for the allow-list policy.
    """
    bundle = db.session.get(Bundle, bundle_id)
    if not bundle or not bundle.blob_path:
        return jsonify(error="not found"), 404
    estimator = load_checked_bundle(Path(bundle.blob_path).read_bytes())
    return jsonify(loaded=True, type=type(estimator).__name__)
