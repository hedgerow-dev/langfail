"""Assistant-driven lookups for private notes.

A companion to :mod:`langfail.api.authz_demo`, which covers the classic
note and project routes. These routes let the in-app assistant resolve a
free-text request ("my note about the Q3 launch") to a specific note. The
other agent features (moderated command execution, research crews,
interpreter sandboxes, MCP bearer tokens) live in
:mod:`langfail.agent.ai_native_examples` and
:mod:`langfail.core.security`.
Both routes require an authenticated session.

``_AssistantClient`` below is a local stand-in for an OpenAI-shaped chat
client (``client.chat.completions.create(...)`` ->
``.choices[0].message.content``) rather than a dependency on the real
``openai`` package. Only the call shape matters here, and this keeps the
routes scriptable in tests without a live model or an API key. A real
deployment would wire this to the actual OpenAI/Anthropic/local client.
The client below is deliberately minimal: one completion per request.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from flask import Blueprint, g, jsonify, request

from ..models import PrivateNote
from .deps import require_auth

bp = Blueprint("ai_native_demo", __name__, url_prefix="/api/ai-native-demo")


@dataclass
class _Message:
    content: str


@dataclass
class _Choice:
    message: _Message


@dataclass
class _Completion:
    choices: list = field(default_factory=list)


class _Completions:
    #: Test hook: set to a callable(prompt: str) -> str returning the JSON
    #: payload the assistant "decided" for this request. Defaults to a
    #: fixed, harmless completion so importing this module never requires a
    #: live model.
    responder = staticmethod(lambda prompt: '{"note_id": 0, "owner_id": 0}')

    def create(self, *, model: str, messages: list[dict], **_: object) -> _Completion:
        prompt = messages[-1]["content"] if messages else ""
        content = self.responder(prompt)
        return _Completion(choices=[_Choice(message=_Message(content=content))])


class _AssistantClient:
    def __init__(self) -> None:
        self.chat = self
        self.completions = _Completions()


client = _AssistantClient()


def _agent_pick_note_owner(query: str) -> dict:
    """Ask the assistant which note the caller means. The completion's
    JSON names the target note id and the owner it belongs to -- the same
    shape a real "smart search" agent tool would return.
    Returns the parsed JSON as a dict.
    """
    resp = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": 'Return JSON: {"note_id": int, "owner_id": int}'},
            {"role": "user", "content": query},
        ],
    )
    return json.loads(resp.choices[0].message.content)


@bp.get("/notes/smart-lookup")
@require_auth
def smart_lookup():
    """Resolve the caller's request with the assistant and return the note
    it picked. The assistant returns both the note id and its owner, so the
    lookup uses both to find the exact row.
    Returns 404 when the assistant picks a note that does not exist.
    """
    query = request.args.get("q", "")
    picked = _agent_pick_note_owner(query)
    note = PrivateNote.query.filter_by(
        id=picked["note_id"], owner_id=picked["owner_id"],
    ).first()
    if note is None:
        return jsonify(error="not found"), 404
    return jsonify(id=note.id, title=note.title, body=note.body)


@bp.get("/notes/assisted-lookup")
@require_auth
def assisted_lookup():
    """Resolve the caller's request with the assistant, then read the note
    from the caller's own notes. A mismatched owner in the assistant's
    answer is refused.
    Returns 403 for a mismatched owner and 404 for a missing note.
    """
    query = request.args.get("q", "")
    picked = _agent_pick_note_owner(query)
    if picked.get("owner_id") is not None and int(picked["owner_id"]) != g.user_id:
        return jsonify(error="forbidden"), 403
    note = PrivateNote.query.filter_by(id=picked["note_id"], owner_id=g.user_id).first()
    if note is None:
        return jsonify(error="not found"), 404
    return jsonify(id=note.id, title=note.title, body=note.body)
