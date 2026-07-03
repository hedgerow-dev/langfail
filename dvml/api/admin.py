"""Administrative endpoints (job status, platform config)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..core.db import db
from ..models import Job
from ..services.config_loader import load_safe
from .deps import require_admin

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
