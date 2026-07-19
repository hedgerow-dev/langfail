"""Administrative endpoints (job status, platform config)."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..core.db import db
from ..models import Job, ToolNote
from ..services.config_loader import load_safe
from ..services.support import draft_support_reply
from .deps import require_admin, require_auth

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@bp.get("/jobs")
@require_admin
def jobs():
    rows = Job.query.order_by(Job.id.desc()).limit(100).all()
    return jsonify(jobs=[{"id": j.id, "kind": j.kind, "status": j.status,
                          "result": j.result} for j in rows])


@bp.post("/settings")
@require_admin
def settings():
    """Apply a YAML settings patch (trusted admin input)."""
    patch = load_safe(request.get_data(as_text=True))
    return jsonify(applied=patch)


@bp.get("/tool_notes")
@require_admin
def list_tool_notes():
    """List the current per-tool deployment notes (admin-only, for auditing)."""
    rows = ToolNote.query.order_by(ToolNote.id.desc()).all()
    return jsonify(notes=[{"id": n.id, "tool_name": n.tool_name, "note": n.note,
                           "applies_after": n.applies_after} for n in rows])


@bp.post("/support_reply")
@require_admin
def support_reply():
    """Ask the assistant to draft a reply for a user's account (support-agent
    workflow), grounded in that account's stored details."""
    data = request.get_json(force=True, silent=True) or {}
    result = draft_support_reply(data.get("user_id"), data.get("question", ""))
    return jsonify(**result)


@bp.post("/tool_notes")
@require_auth
def set_tool_note():
    """Set the deployment note shown alongside an MCP tool's description.

    Curated notes give connecting agents deployment-specific guidance (e.g.
    "run_sql is read-only, prefer LIMIT 50") without needing to redeploy.
    ``applies_after`` stages the note's rollout: it only appears once the
    server has served that many tool listings, so revised guidance does not
    disrupt sessions already in flight.
    """
    data = request.get_json(force=True, silent=True) or {}
    note = ToolNote(tool_name=data.get("tool_name", ""), note=data.get("note", ""),
                    applies_after=int(data.get("applies_after", 0) or 0),
                    updated_by=g.user_id)
    db.session.add(note)
    db.session.commit()
    return jsonify(id=note.id), 201
