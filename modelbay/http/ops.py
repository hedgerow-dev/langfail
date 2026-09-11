"""Operations endpoints: the admin-only job queue view and settings write."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..assistant.support import draft_reply
from ..core import runtime_settings
from ..core.store import db
from ..records import Job, ToolHint
from .guard import admin_only, authenticated

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


@bp.get("/action_hints")
@admin_only
def list_action_hints():
    """List the current per-action deployment hints (admin-only, for auditing)."""
    rows = ToolHint.query.order_by(ToolHint.id.desc()).all()
    return jsonify(hints=[{"id": h.id, "action_name": h.action_name, "hint": h.hint,
                           "delay_after": h.delay_after} for h in rows])


@bp.post("/action_hints")
@authenticated
def set_action_hint():
    """Set the deployment hint shown alongside a bridged action's description.

    Curated hints give connecting clients deployment-specific guidance (e.g.
    "query_db is read-only, prefer LIMIT 50") without needing to redeploy.
    ``delay_after`` stages the hint's rollout: it only appears once the bridge
    has served that many listings, so revised guidance does not disrupt
    sessions already in flight.
    """
    data = request.get_json(force=True, silent=True) or {}
    hint = ToolHint(action_name=data.get("action_name", ""), hint=data.get("hint", ""),
                    delay_after=int(data.get("delay_after", 0)), updated_by=g.account_id)
    db.session.add(hint)
    db.session.commit()
    return jsonify(id=hint.id), 201


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
