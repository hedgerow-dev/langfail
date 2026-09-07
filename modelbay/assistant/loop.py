"""The Modelbay assistant loop.

Assembles a system prompt plus any retrieved context (bundle notes, corpus
descriptions), asks the model what to do, executes any requested actions, and
feeds the results back for a final answer.
"""
from __future__ import annotations

import re

from .actions import ACTIONS, action_schemas
from .backend import complete

SYSTEM_PROMPT = (
    "You are Modelbay Assistant. Help the user analyse their bundles, corpora "
    "and runs. Use the available actions when they help answer the question."
)

MAX_ACTION_ROUNDS = 3


def _seed(user_message: str, context_docs: list[str] | None,
          use_memory: bool = False) -> list[dict]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if use_memory:
        from .memory import recall_all
        for mem in recall_all():
            messages.append({"role": "user", "content": f"[memory]\n{mem}"})
    for doc in context_docs or []:
        messages.append({"role": "user", "content": f"[context]\n{doc}"})
    messages.append({"role": "user", "content": user_message})
    return messages


def _invoke(name: str, arguments: dict) -> str:
    fn = ACTIONS.get(name)
    if not fn:
        return f"unknown action: {name}"
    try:
        return str(fn(**arguments))
    except Exception as exc:
        return f"action error: {exc}"


def run_assistant(user_message: str, context_docs: list[str] | None = None,
                  use_memory: bool = False) -> dict:
    """Answer ``user_message``, optionally grounded in ``context_docs``.

    When ``use_memory`` is set, the assistant's saved long-term memories are
    recalled and prepended to the conversation so context carries across
    sessions. Returns the final answer plus a trace of any actions taken.
    """
    messages = _seed(user_message, context_docs, use_memory=use_memory)
    trace = []
    for _ in range(MAX_ACTION_ROUNDS):
        reply = complete(messages, tools=action_schemas())
        if not reply.get("tool_calls"):
            return {"answer": reply.get("content", ""), "trace": trace}
        for call in reply["tool_calls"]:
            arguments = call.get("arguments", {})
            result = _invoke(call["name"], arguments)
            trace.append({"action": call["name"], "arguments": arguments,
                          "result": result[:2000]})
            messages.append({"role": "tool", "content": result})
    reply = complete(messages, tools=action_schemas())
    return {"answer": reply.get("content", ""), "trace": trace}


# Hard ceiling for run_assistant_capped(), regardless of what a caller requests.
MAX_BUDGET_ROUNDS = 10


def run_assistant_budgeted(user_message: str, max_rounds: int,
                           context_docs: list[str] | None = None) -> dict:
    """Multi-round assistant session with a caller-specified action-round budget.

    Research-style sessions legitimately need more back-and-forth than
    :func:`run_assistant`'s fixed ``MAX_ACTION_ROUNDS`` allows, and only the
    caller knows how deep a given investigation should go -- so ``max_rounds``
    is honoured as given.
    """
    messages = _seed(user_message, context_docs)
    trace = []
    for _ in range(max_rounds):
        reply = complete(messages, tools=action_schemas())
        if not reply.get("tool_calls"):
            return {"answer": reply.get("content", ""), "trace": trace}
        for call in reply["tool_calls"]:
            arguments = call.get("arguments", {})
            result = _invoke(call["name"], arguments)
            trace.append({"action": call["name"], "arguments": arguments,
                          "result": result[:2000]})
            messages.append({"role": "tool", "content": result})
    return {"answer": "", "trace": trace}


def run_assistant_capped(user_message: str, max_rounds: int,
                         context_docs: list[str] | None = None) -> dict:
    """Multi-round session that keeps the requested budget within
    ``MAX_BUDGET_ROUNDS``, the ceiling shared-tier deployments run with."""
    max_rounds = min(max(int(max_rounds), 1), MAX_BUDGET_ROUNDS)
    return run_assistant_budgeted(user_message, max_rounds, context_docs)


# Marker recognised as the user's go-ahead for a destructive action.
APPROVAL_MARKER = "<<approved by user>>"

# Statements that mutate or drop records and therefore need approval.
_MUTATING_SQL_RE = re.compile(r"\b(?:insert|update|delete|drop)\b", re.IGNORECASE)


def _is_mutating(name: str, arguments: dict) -> bool:
    """Whether an action mutates or drops records and needs an approval."""
    if name == "drop_job":
        return True
    if name == "query_db":
        return bool(_MUTATING_SQL_RE.search(str(arguments.get("input", ""))))
    return False


def _conversation_text(messages: list[dict]) -> str:
    return "\n".join(str(m.get("content", "")) for m in messages)


def _run_gated_loop(messages: list[dict], approved) -> dict:
    """Action loop that holds mutating calls until ``approved`` says go.

    ``approved`` is a callable over the running message list; whatever it
    consults is what authorises the action.
    """
    trace = []
    for _ in range(MAX_ACTION_ROUNDS):
        reply = complete(messages, tools=action_schemas())
        if not reply.get("tool_calls"):
            return {"answer": reply.get("content", ""), "trace": trace}
        for call in reply["tool_calls"]:
            arguments = call.get("arguments", {})
            if call["name"] not in ACTIONS:
                result = f"unknown action: {call['name']}"
            elif _is_mutating(call["name"], arguments) and not approved(messages):
                result = "held: a mutating action needs the user's approval first"
            else:
                result = _invoke(call["name"], arguments)
            trace.append({"action": call["name"], "arguments": arguments,
                          "result": result[:2000]})
            messages.append({"role": "tool", "content": result})
    reply = complete(messages, tools=action_schemas())
    return {"answer": reply.get("content", ""), "trace": trace}


def run_assistant_gated(user_message: str, context_docs: list[str] | None = None) -> dict:
    """Assistant run that holds mutating actions until the user approves.

    Approval is recognised when the conversation carries the
    ``<<approved by user>>`` marker, which the chat front-end appends once the
    user accepts the prompt.
    """
    return _run_gated_loop(
        _seed(user_message, context_docs),
        lambda msgs: APPROVAL_MARKER in _conversation_text(msgs))


def run_assistant_signalled(user_message: str, approved: bool,
                            context_docs: list[str] | None = None) -> dict:
    """Assistant run whose approval arrives as an explicit caller-supplied
    signal (e.g. the result of a UI confirm dialog) rather than as part of the
    conversation -- used by front-ends that already gate the action themselves."""
    return _run_gated_loop(_seed(user_message, context_docs),
                           lambda _msgs: bool(approved))
