"""Assistant endpoints."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..assistant.backend import redact_pii
from ..assistant.direct import run_direct_loop
from ..assistant.loop import (run_assistant, run_assistant_budgeted,
                              run_assistant_gated)
from ..assistant.memory import recall_own, store_memory
from ..assistant.sanitize import scrub_directives
from ..core import runtime_settings
from ..core.store import db
from ..records import Bundle, Corpus, Run, RunNote
from .guard import authenticated

bp = Blueprint("assistant", __name__, url_prefix="/assistant")


@bp.post("/converse")
@authenticated
def converse():
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(**run_assistant(data.get("message", "")))


@bp.post("/ask")
@authenticated
def ask():
    """Assistant chat with prompt-injection filtering applied to the message.

    Unlike ``/converse``, inline ``<<ACT:...>>`` directives in the user's
    message are stripped before the assistant runs, so obvious
    prompt-injection attempts are neutralised.
    """
    data = request.get_json(force=True, silent=True) or {}
    message = scrub_directives(data.get("message", ""))
    return jsonify(**run_assistant(message))


@bp.post("/memory")
@authenticated
def add_memory():
    """Save a fact for the assistant to recall in future sessions."""
    content = (request.get_json(force=True, silent=True) or {}).get("content", "")
    return jsonify(id=store_memory(content, owner_id=g.account_id)), 201


@bp.get("/memory")
@authenticated
def list_memory():
    """List the caller's own saved memories (per-account, isolated view)."""
    return jsonify(memories=recall_own(g.account_id))


@bp.post("/session")
@authenticated
def session():
    """A memory-augmented assistant turn.

    Saved long-term memories are recalled into the conversation, and the
    caller's message is remembered so it can inform later sessions.
    """
    data = request.get_json(force=True, silent=True) or {}
    message = data.get("message", "")
    result = run_assistant(message, use_memory=True)
    store_memory(message, owner_id=g.account_id)
    return jsonify(**result)


@bp.post("/notes")
@authenticated
def add_note():
    """Attach a private note to a run (triage remarks, follow-ups, contact
    details for the data owner)."""
    data = request.get_json(force=True, silent=True) or {}
    row = RunNote(owner_id=g.account_id, run_id=data.get("run_id"),
                  note=data.get("note", ""))
    db.session.add(row)
    db.session.commit()
    return jsonify(id=row.id), 201


@bp.get("/notes")
@authenticated
def list_notes():
    """List the caller's own run notes (per-account, isolated view)."""
    rows = (RunNote.query.filter_by(owner_id=g.account_id)
            .order_by(RunNote.id.desc()).limit(100).all())
    return jsonify(notes=[{"id": n.id, "run_id": n.run_id, "note": n.note} for n in rows])


@bp.post("/brief")
@authenticated
def brief():
    """Ground the assistant in the notes recorded for a run and answer with a
    short briefing."""
    data = request.get_json(force=True, silent=True) or {}
    run = db.session.get(Run, data.get("run_id"))
    if not run:
        return jsonify(error="not found"), 404
    rows = (RunNote.query.filter_by(run_id=run.id).order_by(RunNote.id).limit(50).all())
    docs = [n.note for n in rows]
    return jsonify(**run_assistant(f"Brief me on run '{run.name}'.", context_docs=docs))


@bp.post("/direct")
@authenticated
def direct():
    """A lightweight, non-framework tool-use assistant for looking up bundle
    and run info (see :mod:`modelbay.assistant.direct`)."""
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(**run_direct_loop(data.get("message", "")))


@bp.post("/preferences")
@authenticated
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
                namespace, patch, updated_by=g.account_id)
    return jsonify(preferences=applied)


@bp.post("/preferences_scoped")
@authenticated
def save_preferences_scoped():
    """Like ``/preferences``, but restricted to caller-tunable namespaces
    (``ui``, ``assistant``); anything else is reported as rejected."""
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(**runtime_settings.merge_account_preferences(
        data.get("preferences") or {}, updated_by=g.account_id))


@bp.post("/converse_brief")
@authenticated
def converse_brief():
    """Assistant chat with output-side redaction of common PII shapes
    (emails, SSNs) applied to the answer before it is returned."""
    data = request.get_json(force=True, silent=True) or {}
    result = run_assistant(data.get("message", ""))
    result["answer"] = redact_pii(result.get("answer", ""))
    return jsonify(**result)


@bp.post("/deep_dive")
@authenticated
def deep_dive():
    """Multi-round assistant session for research-style back-and-forth that
    needs more rounds than the default assistant allows.

    ``max_rounds`` sets how many action-call rounds the session may run.
    """
    data = request.get_json(force=True, silent=True) or {}
    max_rounds = data.get("max_rounds", 3)
    return jsonify(**run_assistant_budgeted(data.get("message", ""), int(max_rounds)))


@bp.post("/act")
@authenticated
def act():
    """Run the assistant with an approval gate on mutating actions.

    Actions that mutate or drop records are held until the user has approved
    them in the conversation.
    """
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(**run_assistant_gated(data.get("message", ""),
                                         context_docs=data.get("context_docs")))


@bp.post("/summarize")
@authenticated
def summarize_bundle():
    """Summarise a bundle using its notes and linked corpus descriptions."""
    data = request.get_json(force=True, silent=True) or {}
    bundle = db.session.get(Bundle, data.get("bundle_id"))
    if not bundle:
        return jsonify(error="not found"), 404

    docs = []
    if bundle.notes:
        docs.append(bundle.notes)
    for corpus in Corpus.query.filter_by(owner_id=bundle.owner_id).limit(5):
        if corpus.origin_url:
            docs.append(f"Corpus {corpus.name}: {corpus.origin_url}")

    return jsonify(**run_assistant(
        f"Summarise the bundle '{bundle.name}' and note anything important in it.",
        context_docs=docs,
    ))
