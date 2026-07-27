"""Shareable HTML report/preview endpoints."""
from __future__ import annotations

from flask import Blueprint, Response, g, jsonify, request

from ..core.db import db
from ..models import Model
from ..services.reports import render_builtin_report, render_custom_report, render_page, render_report
from ..services.markdown import render_markdown
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


@bp.post("/markdown")
@require_auth
def markdown_preview():
    """Render a model's card (Markdown) to a shareable HTML preview.

    The card body is authored by the model owner or produced by the assistant;
    it is converted from Markdown to HTML for display on the dashboard.
    """
    data = request.get_json(force=True, silent=True) or {}
    model = db.session.get(Model, data.get("model_id"))
    if not model:
        return jsonify(error="not found"), 404
    body = render_markdown(model.model_card or "")
    html = render_page(title=model.name, body_html=body)
    return Response(html, mimetype="text/html")


@bp.post("/custom")
@require_auth
def custom_report():
    """Render a report from either a built-in kind or a custom template file.

    ``kind`` selects one of the small fixed set of built-in report styles.
    Power users can instead pass ``template_name`` to point at their own
    ``.tpl`` file placed alongside the built-ins.
    """
    data = request.get_json(force=True, silent=True) or {}
    model = db.session.get(Model, data.get("model_id"))
    if not model:
        return jsonify(error="not found"), 404

    context = {"model": model, "owner": g.user_id}
    if data.get("template_name"):
        body = render_custom_report(data["template_name"], context)
    else:
        body = render_builtin_report(data.get("kind", "summary"), context)

    html = render_page(title=model.name, body_html=body)
    return Response(html, mimetype="text/html")
