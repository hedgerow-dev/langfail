"""Operations endpoints: the admin-only job queue view and settings write."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..assistant.support import draft_reply
from ..core import runtime_settings
from ..records import Job
from .guard import admin_only

bp = Blueprint("ops", __name__, url_prefix="/ops")


@bp.get("/jobs")
@admin_only
def jobs():
    rows = Job.query.order_by(Job.id.desc()).limit(100).all()
    return jsonify(jobs=[{"id": j.id, "kind": j.kind, "status": j.status,
                          "result": j.result} for j in rows])


@bp.post("/support_reply")
@admin_only
def support_reply():
    """Draft a support reply grounded in an account's stored details."""
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(**draft_reply(data.get("account_id"), data.get("question", "")))


@bp.post("/settings")
@admin_only
def settings():
    """Merge a settings document. Bearer-authenticated: an ambient portal
    cookie alone never reaches this endpoint."""
    data = request.get_json(force=True, silent=True) or {}
    applied = {}
    for namespace, patch in data.items():
        if isinstance(patch, dict):
            applied[namespace] = runtime_settings.merge_namespace(
                namespace, patch, updated_by=g.account_id)
    return jsonify(applied=applied)
