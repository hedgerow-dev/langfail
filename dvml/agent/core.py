"""The ModelForge assistant agent loop.

Assembles a system prompt plus any retrieved context (model cards, dataset
descriptions), asks the LLM what to do, executes any requested tools, and feeds
the results back for a final answer.
"""
from __future__ import annotations

from .llm import chat
from .tools import TOOLS, tool_schemas

SYSTEM_PROMPT = (
    "You are ModelForge Assistant. Help the user analyse their models, datasets "
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
