"""LLM assistant endpoints."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..core import settings as runtime_settings
from ..core.db import db
from ..models import Dataset, Experiment, ExperimentNote, Model
from ..agent.core import run_agent, run_agent_guarded, run_agent_extended
from ..agent.llm import redact_sensitive
from ..agent.memory import recall_for_owner, remember
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
    return jsonify(memories=recall_for_owner(g.user_id))


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
    result = run_agent_extended(message, int(max_rounds))
    return jsonify(**result)


@bp.post("/native")
@require_auth
def native():
    """A lightweight, non-framework tool-use assistant for looking up model
    and experiment info (see :mod:`langfail.agent.native`)."""
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


@bp.post("/execute")
@require_auth
def execute():
    """Run the assistant with a confirmation gate on destructive actions.

    Actions that mutate or drop records (destructive SQL, removing jobs) are
    held until the user has confirmed them in the conversation.
    """
    data = request.get_json(force=True, silent=True) or {}
    result = run_agent_guarded(data.get("message", ""), context_docs=data.get("context_docs"))
    return jsonify(**result)


@bp.post("/notes")
@require_auth
def add_note():
    """Attach a private note to an experiment (triage remarks, follow-ups,
    contact details for the data owner)."""
    data = request.get_json(force=True, silent=True) or {}
    row = ExperimentNote(owner_id=g.user_id, experiment_id=data.get("experiment_id"),
                         note=data.get("note", ""))
    db.session.add(row)
    db.session.commit()
    return jsonify(id=row.id), 201


@bp.get("/notes")
@require_auth
def list_notes():
    """List the caller's own experiment notes (per-user, isolated view)."""
    rows = (ExperimentNote.query.filter_by(owner_id=g.user_id)
            .order_by(ExperimentNote.id.desc()).limit(100).all())
    return jsonify(notes=[{"id": n.id, "experiment_id": n.experiment_id,
                           "note": n.note} for n in rows])


@bp.post("/brief")
@require_auth
def brief():
    """Ground the assistant in the notes recorded for an experiment and
    answer with a short briefing."""
    data = request.get_json(force=True, silent=True) or {}
    exp = db.session.get(Experiment, data.get("experiment_id"))
    if not exp:
        return jsonify(error="not found"), 404
    rows = (ExperimentNote.query.filter_by(experiment_id=exp.id)
            .order_by(ExperimentNote.id).limit(50).all())
    docs = [n.note for n in rows]
    result = run_agent(f"Brief me on experiment '{exp.name}'.", context_docs=docs)
    return jsonify(**result)


@bp.post("/chat_brief")
@require_auth
def chat_brief():
    """Assistant chat with output-side redaction of common PII shapes
    (emails, SSNs) applied to the answer before it is returned."""
    data = request.get_json(force=True, silent=True) or {}
    result = run_agent(data.get("message", ""))
    result["answer"] = redact_sensitive(result.get("answer", ""))
    return jsonify(**result)


@bp.post("/preferences")
@require_auth
def save_preferences():
    """Merge the caller's preferences into the runtime settings store.

    Preferences arrive as a namespace document (e.g. ``{"ui": {"theme":
    "dark"}}``); each top-level namespace is deep-merged so settings the
    caller didn't mention stay intact.
    """
    data = request.get_json(force=True, silent=True) or {}
    prefs = data.get("preferences") or {}
    applied = {}
    for namespace, patch in prefs.items():
        if isinstance(patch, dict):
            applied[namespace] = runtime_settings.merge_namespace(
                namespace, patch, updated_by=g.user_id)
    return jsonify(preferences=applied)


@bp.post("/preferences_scoped")
@require_auth
def save_preferences_scoped():
    """Like ``/preferences``, but restricted to caller-tunable namespaces
    (``ui``, ``llm``); anything else is reported as rejected."""
    data = request.get_json(force=True, silent=True) or {}
    outcome = runtime_settings.merge_user_preferences(
        data.get("preferences") or {}, updated_by=g.user_id)
    return jsonify(**outcome)
