"""Shareable HTML report/preview endpoints."""
from __future__ import annotations

from flask import Blueprint, Response, g, jsonify, request

from ..core.store import db
from ..records import Bundle
from ..store.markup import to_html
from ..store.rendering import (render_named_report, render_stock_report,
                               render_template_source, wrap_page)
from .guard import authenticated

bp = Blueprint("previews", __name__, url_prefix="/previews")


@bp.post("/page")
@authenticated
def render_preview():
    """Render a shareable HTML preview of a bundle report.

    The report body is supplied by the caller (or produced upstream) and
    embedded into the dashboard page shell for sharing.
    """
    data = request.get_json(force=True, silent=True) or {}
    bundle = db.session.get(Bundle, data.get("bundle_id"))
    if not bundle:
        return jsonify(error="not found"), 404

    body = data.get("body") or ""
    template = data.get("template", "")
    if template:
        body = render_template_source(template, {"bundle": bundle, "owner": g.account_id})

    html = wrap_page(title=bundle.name, body_html=body)
    return Response(html, mimetype="text/html")


@bp.post("/notes")
@authenticated
def notes_preview():
    """Render a bundle's notes (Markdown) to a shareable HTML preview.

    The notes body is authored by the bundle owner or produced by the
    assistant; it is converted from Markdown to HTML for display.
    """
    data = request.get_json(force=True, silent=True) or {}
    bundle = db.session.get(Bundle, data.get("bundle_id"))
    if not bundle:
        return jsonify(error="not found"), 404
    body = to_html(bundle.notes or "")
    return Response(wrap_page(title=bundle.name, body_html=body), mimetype="text/html")


@bp.post("/styled")
@authenticated
def styled_report():
    """Render a report from either a stock style or a named template file.

    ``style`` selects one of the small fixed set of stock report styles. Power
    users can instead pass ``template_name`` to point at their own ``.tpl``
    file placed alongside the stock ones.
    """
    data = request.get_json(force=True, silent=True) or {}
    bundle = db.session.get(Bundle, data.get("bundle_id"))
    if not bundle:
        return jsonify(error="not found"), 404

    context = {"bundle": bundle, "owner": g.account_id}
    if data.get("template_name"):
        body = render_named_report(data["template_name"], context)
    else:
        body = render_stock_report(data.get("style", "summary"), context)

    html = wrap_page(title=bundle.name, body_html=body)
    return Response(html, mimetype="text/html")
