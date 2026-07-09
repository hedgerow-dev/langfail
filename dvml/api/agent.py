"""LLM assistant endpoints."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..core.db import db
from ..models import Dataset, Model
from ..agent.core import run_agent, run_agent_unbounded
from ..agent.memory import recall_scoped, remember
from ..agent.native import run_native_loop
from ..agent.sanitize import strip_directives
from .deps import require_auth

bp = Blueprint("agent", __name__, url_prefix="/api/agent")


@bp.post("/chat")
@require_auth
def chat():
    data = request.get_json(force=True, silent=True) or {}
    message = data.get("message", "")
    result = run_agent(message)
    return jsonify(**result)


@bp.post("/ask")
@require_auth
def ask():
    """Assistant chat with prompt-injection filtering applied to the message.

    Unlike ``/chat``, inline ``[[TOOL:...]]`` directives in the user's message
    are stripped before the agent runs, so obvious prompt-injection attempts are
    neutralised.
    """
    data = request.get_json(force=True, silent=True) or {}
    message = strip_directives(data.get("message", ""))
    result = run_agent(message)
    return jsonify(**result)


@bp.post("/memory")
@require_auth
def add_memory():
    """Save a fact for the assistant to recall in future sessions."""
    content = (request.get_json(force=True, silent=True) or {}).get("content", "")
    mem_id = remember(content, owner_id=g.user_id)
    return jsonify(id=mem_id), 201


@bp.get("/memory")
@require_auth
def list_memory():
    """List the caller's own saved memories (per-user, isolated view)."""
    return jsonify(memories=recall_scoped(g.user_id))


@bp.post("/session")
@require_auth
def session():
    """A memory-augmented assistant turn.

    Saved long-term memories are recalled into the conversation, and the user's
    message is remembered so it can inform later sessions.
    """
    data = request.get_json(force=True, silent=True) or {}
    message = data.get("message", "")
    result = run_agent(message, use_memory=True)
    remember(message, owner_id=g.user_id)
    return jsonify(**result)


@bp.post("/iterate")
@require_auth
def iterate():
    """Multi-round assistant session for research-style back-and-forth that
    needs more rounds than the default assistant allows.

    ``max_rounds`` sets how many tool-call rounds the session may run.
    """
    data = request.get_json(force=True, silent=True) or {}
    message = data.get("message", "")
    max_rounds = data.get("max_rounds", 3)
    result = run_agent_unbounded(message, int(max_rounds))
    return jsonify(**result)


@bp.post("/native")
@require_auth
def native():
    """A lightweight, non-framework tool-use assistant for looking up model
    and experiment info (see :mod:`dvml.agent.native`)."""
    data = request.get_json(force=True, silent=True) or {}
    result = run_native_loop(data.get("message", ""))
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
