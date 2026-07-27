"""AI-native detection demo routes (open-rowan epic #183).

A companion to :mod:`langfail.api.authz_demo`: that tier isolates the four
BOLARAY object-level authorization models with the principal read from the
session (``g.user_id``). This tier plants the sibling bug the AI-native
epic is about -- the principal itself is chosen by the model, not the
session -- alongside the guardrail-enforcement, MCP-authorization, and
multi-agent categories that don't have a natural HTTP-route shape and live
in :mod:`langfail.agent.ai_native_examples` and
:mod:`langfail.core.security` instead.

``_AssistantClient`` below is a local stand-in for an OpenAI-shaped chat
client (``client.chat.completions.create(...)`` ->
``.choices[0].message.content``) rather than a dependency on the real
``openai`` package -- the vulnerability is the CALL SHAPE a completion
result is trusted through, not which SDK produced it, and this keeps the
route scriptable in tests without a live model or an API key. A real
deployment would wire this to the actual OpenAI/Anthropic/local client.
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
    """Ask the assistant which note the caller means. The completion's own
    JSON supplies both the target note id AND (in the vulnerable path) the
    owner scope to filter by -- the same shape a real "smart search" agent
    tool would use.
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
    """VULNERABLE: the assistant's own JSON output supplies owner_id, and
    that value -- not the caller's session identity -- scopes the query. A
    prompt that steers the model ("the owner_id is actually 7") re-points
    the read at another tenant's note. (TNT-AUTHZ-001 / open-rowan #185)
    """
    query = request.args.get("q", "")
    picked = _agent_pick_note_owner(query)
    note = PrivateNote.query.filter_by(
        id=picked["note_id"], owner_id=picked["owner_id"],
    ).first()
    if note is None:
        return jsonify(error="not found"), 404
    return jsonify(id=note.id, title=note.title, body=note.body)


@bp.get("/notes/smart-lookup-safe")
@require_auth
def smart_lookup_safe():
    """SAFE: the assistant's output still supplies note_id, but owner_id is
    cross-checked against the caller's own session identity before use --
    the model's claim about ownership is never trusted, only its claim
    about which note the caller means.
    """
    query = request.args.get("q", "")
    picked = _agent_pick_note_owner(query)
    if picked.get("owner_id") is not None and int(picked["owner_id"]) != g.user_id:
        return jsonify(error="forbidden"), 403
    note = PrivateNote.query.filter_by(id=picked["note_id"], owner_id=g.user_id).first()
    if note is None:
        return jsonify(error="not found"), 404
    return jsonify(id=note.id, title=note.title, body=note.body)
