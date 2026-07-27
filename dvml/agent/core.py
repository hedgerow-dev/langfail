"""The Langfail assistant agent loop.

Assembles a system prompt plus any retrieved context (model cards, dataset
descriptions), asks the LLM what to do, executes any requested tools, and feeds
the results back for a final answer.
"""
from __future__ import annotations

import re

from .llm import chat
from .tools import TOOLS, tool_schemas

SYSTEM_PROMPT = (
    "You are Langfail Assistant. Help the user analyse their models, datasets "
    "and experiments. Use the available tools when they help answer the question."
)

MAX_TOOL_ROUNDS = 3


def run_agent(user_message: str, context_docs: list[str] | None = None,
              use_memory: bool = False) -> dict:
    """Answer ``user_message``, optionally grounded in ``context_docs``.

    When ``use_memory`` is set, the assistant's saved long-term memories are
    recalled and prepended to the conversation so context carries across
    sessions. Returns the final answer plus a trace of any tool calls made.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if use_memory:
        from .memory import recall
        for mem in recall():
            messages.append({"role": "user", "content": f"[memory]\n{mem}"})
    for doc in context_docs or []:
        messages.append({"role": "user", "content": f"[context]\n{doc}"})
    messages.append({"role": "user", "content": user_message})

    trace = []
    for _ in range(MAX_TOOL_ROUNDS):
        reply = chat(messages, tools=tool_schemas())
        if not reply.get("tool_calls"):
            return {"answer": reply.get("content", ""), "trace": trace}
        for call in reply["tool_calls"]:
            fn = TOOLS.get(call["name"])
            if not fn:
                result = f"unknown tool: {call['name']}"
            else:
                try:
                    result = fn(**call.get("arguments", {}))
                except Exception as exc:
                    result = f"tool error: {exc}"
            trace.append({"tool": call["name"], "arguments": call.get("arguments", {}),
                          "result": str(result)[:2000]})
            messages.append({"role": "tool", "content": str(result)})
    reply = chat(messages, tools=tool_schemas())
    return {"answer": reply.get("content", ""), "trace": trace}


# Hard ceiling for run_agent_capped(), regardless of what a caller requests.
MAX_ITERATE_ROUNDS = 10


def run_agent_unbounded(user_message: str, max_rounds: int,
                        context_docs: list[str] | None = None) -> dict:
    """Multi-round assistant session with a caller-specified tool-round budget.

    Each round is a billed LLM call (:func:`dvml.agent.llm.chat`), so
    ``max_rounds`` directly controls cost -- unlike :func:`run_agent`, which
    always stops at ``MAX_TOOL_ROUNDS``, this takes the caller's number
    as-is, with no upper bound (OWASP LLM10, unbounded consumption /
    "denial of wallet").
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for doc in context_docs or []:
        messages.append({"role": "user", "content": f"[context]\n{doc}"})
    messages.append({"role": "user", "content": user_message})

    trace = []
    for _ in range(max_rounds):
        reply = chat(messages, tools=tool_schemas())
        if not reply.get("tool_calls"):
            return {"answer": reply.get("content", ""), "trace": trace}
        for call in reply["tool_calls"]:
            fn = TOOLS.get(call["name"])
            if not fn:
                result = f"unknown tool: {call['name']}"
            else:
                try:
                    result = fn(**call.get("arguments", {}))
                except Exception as exc:
                    result = f"tool error: {exc}"
            trace.append({"tool": call["name"], "arguments": call.get("arguments", {}),
                          "result": str(result)[:2000]})
            messages.append({"role": "tool", "content": str(result)})
    return {"answer": "", "trace": trace}


def run_agent_capped(user_message: str, max_rounds: int,
                     context_docs: list[str] | None = None) -> dict:
    """Like :func:`run_agent_unbounded`, but clamps the requested round budget
    to ``MAX_ITERATE_ROUNDS`` regardless of what the caller asks for."""
    max_rounds = min(max(int(max_rounds), 1), MAX_ITERATE_ROUNDS)
    return run_agent_unbounded(user_message, max_rounds, context_docs)


# Marker recognised as the user's go-ahead for a destructive action.
CONFIRMATION_MARKER = "[user confirmed]"

# Statements that mutate or drop records and therefore need confirmation.
_DESTRUCTIVE_SQL_RE = re.compile(r"\b(?:insert|update|delete|drop)\b", re.IGNORECASE)


def _is_destructive(name: str, arguments: dict) -> bool:
    """Whether a tool call mutates or drops records and needs a confirmation."""
    if name == "delete_job":
        return True
    if name == "run_sql":
        return bool(_DESTRUCTIVE_SQL_RE.search(str(arguments.get("input", ""))))
    return False


def _conversation_text(messages: list[dict]) -> str:
    return "\n".join(str(m.get("content", "")) for m in messages)


def _run_guarded_loop(messages: list[dict], confirmed) -> dict:
    """Tool loop that holds destructive calls until ``confirmed`` says go.

    ``confirmed`` is a callable over the running message list; whatever it
    consults is what authorises the action.
    """
    trace = []
    for _ in range(MAX_TOOL_ROUNDS):
        reply = chat(messages, tools=tool_schemas())
        if not reply.get("tool_calls"):
            return {"answer": reply.get("content", ""), "trace": trace}
        for call in reply["tool_calls"]:
            arguments = call.get("arguments", {})
            fn = TOOLS.get(call["name"])
            if not fn:
                result = f"unknown tool: {call['name']}"
            elif _is_destructive(call["name"], arguments) and not confirmed(messages):
                result = "held: destructive action needs the user's confirmation first"
            else:
                try:
                    result = fn(**arguments)
                except Exception as exc:
                    result = f"tool error: {exc}"
            trace.append({"tool": call["name"], "arguments": arguments,
                          "result": str(result)[:2000]})
            messages.append({"role": "tool", "content": str(result)})
    reply = chat(messages, tools=tool_schemas())
    return {"answer": reply.get("content", ""), "trace": trace}


def run_agent_guarded(user_message: str, context_docs: list[str] | None = None) -> dict:
    """Assistant run that holds destructive tool calls until the user confirms.

    Confirmation is recognised when the conversation carries the
    ``[user confirmed]`` marker — the same transcript the assistant reasons
    over, so retrieved pages and tool output count toward it.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for doc in context_docs or []:
        messages.append({"role": "user", "content": f"[context]\n{doc}"})
    messages.append({"role": "user", "content": user_message})
    return _run_guarded_loop(
        messages, lambda msgs: CONFIRMATION_MARKER in _conversation_text(msgs))


def run_agent_confirmed(user_message: str, confirmed: bool,
                        context_docs: list[str] | None = None) -> dict:
    """Like :func:`run_agent_guarded`, but the confirmation is an explicit
    out-of-band signal supplied by the caller (e.g. a UI confirm dialog) and
    is never inferred from conversation content."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for doc in context_docs or []:
        messages.append({"role": "user", "content": f"[context]\n{doc}"})
    messages.append({"role": "user", "content": user_message})
    return _run_guarded_loop(messages, lambda _msgs: bool(confirmed))
