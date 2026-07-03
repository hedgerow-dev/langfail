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


def run_agent(user_message: str, context_docs: list[str] | None = None) -> dict:
    """Answer ``user_message``, optionally grounded in ``context_docs``.

    Returns the final answer plus a trace of any tool calls that were made.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
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
