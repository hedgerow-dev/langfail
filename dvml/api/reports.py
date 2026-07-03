"""Shareable HTML report/preview endpoints."""
from __future__ import annotations

from flask import Blueprint, Response, g, jsonify, request

from ..core.db import db
from ..models import Model
from ..services.reports import render_page, render_report
from ..agent.core import run_agent
from .deps import require_auth

bp = Blueprint("reports", __name__, url_prefix="/api/reports")


@bp.post("/preview")
@require_auth
def preview():
    """Render a shareable HTML preview of a model report.

    The report body is produced by the assistant (or supplied directly) and
    embedded into the dashboard page shell for sharing.
    """
    data = request.get_json(force=True, silent=True) or {}
    model = db.session.get(Model, data.get("model_id"))
    if not model:
        return jsonify(error="not found"), 404

    if data.get("body"):
        body = data["body"]
    else:
        summary = run_agent(f"Write an HTML summary card for model '{model.name}'.",
                            context_docs=[model.model_card or ""])
        body = summary["answer"]

    template = data.get("template", "")
    if template:
        body = render_report(template, {"model": model, "owner": g.user_id})

    html = render_page(title=model.name, body_html=body)
    return Response(html, mimetype="text/html")
