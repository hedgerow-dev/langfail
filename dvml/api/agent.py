"""LLM assistant endpoints."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..core.db import db
from ..models import Dataset, Model
from ..agent.core import run_agent
from .deps import require_auth

bp = Blueprint("agent", __name__, url_prefix="/api/agent")


@bp.post("/chat")
@require_auth
def chat():
    data = request.get_json(force=True, silent=True) or {}
    message = data.get("message", "")
    result = run_agent(message)
    return jsonify(**result)


@bp.post("/analyze")
@require_auth
def analyze():
    """Summarise a model using its card and linked dataset descriptions."""
    data = request.get_json(force=True, silent=True) or {}
    model = db.session.get(Model, data.get("model_id"))
    if not model:
        return jsonify(error="not found"), 404

    docs = []
    if model.model_card:
        docs.append(model.model_card)
    for ds in Dataset.query.filter_by(owner_id=model.owner_id).limit(5):
        if ds.source_url:
            docs.append(f"Dataset {ds.name}: {ds.source_url}")

    result = run_agent(
        f"Summarise the model '{model.name}' and note anything important in its card.",
        context_docs=docs,
    )
    return jsonify(**result)
