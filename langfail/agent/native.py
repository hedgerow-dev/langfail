"""Native (non-framework) tool-use loop.

Most hand-rolled OpenAI/Anthropic tool-use integrations don't go through a
framework's tool registry — they ask the model which action to take, then
invoke the named method directly via reflection on a handler object. This
module is that pattern, kept separate from :mod:`langfail.agent.core` (which
dispatches through the explicit ``TOOLS`` allow-list dict in
:mod:`langfail.agent.tools`).
"""
from __future__ import annotations

from .llm import chat


class AssistantActions:
    """Actions available to the native tool-use loop.

    Only the methods listed in ``_PUBLIC_ACTIONS`` below are advertised to the
    model via :func:`action_schemas`. ``_debug_eval`` is a leftover helper from
    wiring up new actions during development — never advertised, never meant
    to be called by anything but a developer's REPL.
    """

    def get_model_info(self, model_id: int = 0) -> dict:
        from ..core.db import db
        from ..models import Model

        model = db.session.get(Model, model_id)
        if not model:
            return {"error": "not found"}
        return {"id": model.id, "name": model.name, "framework": model.framework}

    def list_experiment_names(self, owner_id: int = 0) -> list:
        from ..models import Experiment

        rows = Experiment.query.filter_by(owner_id=owner_id).limit(20).all()
        return [e.name for e in rows]

    def _debug_eval(self, expr: str = ""):
        """Ad-hoc expression check used while wiring up new actions."""
        return eval(expr, {"__builtins__": {}}, {})


_ACTIONS = AssistantActions()
_PUBLIC_ACTIONS = ("get_model_info", "list_experiment_names")


def action_schemas() -> list[dict]:
    """Schemas advertised to the model — the public action surface only."""
    return [
        {"type": "function", "function": {
            "name": name,
            "description": (getattr(_ACTIONS, name).__doc__ or "").strip(),
            "parameters": {"type": "object", "properties": {}},
        }}
        for name in _PUBLIC_ACTIONS
    ]


def dispatch(name: str, **kwargs) -> object:
    """Resolve and call ``name`` on the shared actions handler.

    Resolution is by attribute lookup, so new actions become callable as soon
    as they're added to :class:`AssistantActions` -- no second registration
    step to keep in sync with :func:`action_schemas`.
    """
    if not isinstance(name, str):
        return {"error": f"unknown action: {name!r}"}
    fn = getattr(_ACTIONS, name, None)
    if not callable(fn):
        return {"error": f"unknown action: {name}"}
    return fn(**kwargs)


def dispatch_public(name: str, **kwargs) -> object:
    """Like :func:`dispatch`, but resolves only names present in the
    advertised action allow-list. Used by callers that need the handler's
    public surface and its schema list to stay exactly in step."""
    if name not in _PUBLIC_ACTIONS:
        return {"error": f"action not allowed: {name}"}
    fn = getattr(_ACTIONS, name, None)
    if not callable(fn):
        return {"error": f"unknown action: {name}"}
    return fn(**kwargs)


def run_native_loop(user_message: str) -> dict:
    """A minimal tool-use loop: ask the model what to do, dispatch, answer."""
    messages = [
        {"role": "system", "content": "Help the user look up model/experiment info."},
        {"role": "user", "content": user_message},
    ]
    reply = chat(messages, tools=action_schemas())
    trace = []
    for call in reply.get("tool_calls", []) or []:
        name = call.get("name")
        try:
            result = dispatch(name, **call.get("arguments", {}))
        except Exception as exc:
            # A model-chosen name can arrive absent or with arguments the
            # target doesn't accept; surface that as a result like
            # langfail.agent.core does, rather than a 500 from the route.
            result = f"action error: {exc}"
        trace.append({"action": name, "result": result})
    return {"answer": reply.get("content", ""), "trace": trace}
