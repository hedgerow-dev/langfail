"""Direct (non-framework) tool-use loop.

Most hand-rolled tool-use integrations don't go through a framework's action
registry -- they ask the model which action to take, then invoke the named
method directly via reflection on a handler object. This module is that
pattern, kept separate from :mod:`modelbay.assistant.loop` (which dispatches
through the explicit ``ACTIONS`` allow-list dict in
:mod:`modelbay.assistant.actions`).
"""
from __future__ import annotations

from .backend import complete


class DeskActions:
    """Actions available to the direct tool-use loop.

    Only the methods listed in ``_ADVERTISED`` below are offered to the model
    via :func:`desk_schemas`. ``_scratch_eval`` is a leftover helper from
    wiring up new actions during development -- never advertised, never meant
    to be called by anything but a developer's REPL.
    """

    def get_bundle_info(self, bundle_id: int = 0) -> dict:
        from ..core.store import db
        from ..records import Bundle

        bundle = db.session.get(Bundle, bundle_id)
        if not bundle:
            return {"error": "not found"}
        return {"id": bundle.id, "name": bundle.name, "runtime": bundle.runtime}

    def list_run_names(self, owner_id: int = 0) -> list:
        from ..records import Run

        rows = Run.query.filter_by(owner_id=owner_id).limit(20).all()
        return [r.name for r in rows]

    def _scratch_eval(self, expr: str = ""):
        """Ad-hoc expression check used while wiring up new actions."""
        return eval(expr, {"__builtins__": {}}, {})


_DESK = DeskActions()
_ADVERTISED = ("get_bundle_info", "list_run_names")


def desk_schemas() -> list[dict]:
    """Schemas offered to the model -- the advertised action surface only."""
    return [
        {"type": "function", "function": {
            "name": name,
            "description": (getattr(_DESK, name).__doc__ or "").strip(),
            "parameters": {"type": "object", "properties": {}},
        }}
        for name in _ADVERTISED
    ]


def dispatch(name: str, **kwargs) -> object:
    """Resolve and call ``name`` on the shared desk handler.

    Resolution is by attribute lookup, so new actions become callable as soon
    as they're added to :class:`DeskActions` -- no second registration step to
    keep in sync with :func:`desk_schemas`.
    """
    if not isinstance(name, str):
        return {"error": f"unknown action: {name!r}"}
    fn = getattr(_DESK, name, None)
    if not callable(fn):
        return {"error": f"unknown action: {name}"}
    return fn(**kwargs)


def dispatch_advertised(name: str, **kwargs) -> object:
    """Like :func:`dispatch`, but resolves only names present in the
    advertised action allow-list. Used by callers that need the handler's
    public surface and its schema list to stay exactly in step."""
    if name not in _ADVERTISED:
        return {"error": f"action not allowed: {name}"}
    fn = getattr(_DESK, name, None)
    if not callable(fn):
        return {"error": f"unknown action: {name}"}
    return fn(**kwargs)


def run_direct_loop(user_message: str) -> dict:
    """A minimal tool-use loop: ask the model what to do, dispatch, answer."""
    messages = [
        {"role": "system", "content": "Help the user look up bundle/run info."},
        {"role": "user", "content": user_message},
    ]
    reply = complete(messages, tools=desk_schemas())
    trace = []
    for call in reply.get("tool_calls", []) or []:
        name = call.get("name")
        try:
            result = dispatch(name, **call.get("arguments", {}))
        except Exception as exc:
            # A model-chosen name can arrive absent or with arguments the
            # target doesn't accept; surface that as a result rather than a
            # 500 from the route.
            result = f"action error: {exc}"
        trace.append({"action": name, "result": result})
    return {"answer": reply.get("content", ""), "trace": trace}
