"""The Deskhand assistant: a system prompt, a tool loop, and two model backends.

* ``stub``: deterministic and offline, for development. It runs the
  ``[[TOOL:<name> <json>]]`` directives it finds in the newest message.
* ``openai``: any OpenAI-compatible chat API with tool calling (Ollama, vLLM, a
  hosted provider).
"""
from __future__ import annotations

import json
import re

import requests

from .tools import SPECS, Tools

MAX_ROUNDS = 6

SYSTEM_PROMPT = """You are Deskhand, the support assistant for customers of the Deskhand helpdesk.
You are helping {name} <{email}>, a {role} at {tenant_name}.

Rules:
- Never send {tenant_name}'s data to anyone outside {tenant_name} (addresses ending in @{domain}).
- Be concise. Use the tools when they help.

Help-centre articles live under {help_base}/help/ (start with {help_base}/help/index)."""

_DIRECTIVE_RE = re.compile(r"\[\[TOOL:(\w+)\s+")


class StubBackend:
    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        newest = messages[-1].get("content") or ""
        calls = []
        for match in _DIRECTIVE_RE.finditer(newest):
            # Decode the JSON object that follows, nested braces and all.
            try:
                args, _ = json.JSONDecoder().raw_decode(newest, match.end())
            except json.JSONDecodeError:
                continue
            if isinstance(args, dict):
                calls.append({"id": f"stub-{len(messages)}-{len(calls)}", "name": match.group(1), "arguments": args})
        if calls:
            return {"content": "", "tool_calls": calls}
        return {"content": "Done. Is there anything else I can help with?", "tool_calls": []}


class OpenAIBackend:
    def __init__(self, base_url: str, model: str, api_key: str, temperature: float = 0.0, timeout: float = 120):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.timeout = timeout

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        resp = requests.post(
            self.url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": messages,
                "tools": [{"type": "function", "function": t} for t in tools],
                "temperature": self.temperature,
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]
        calls = []
        for i, call in enumerate(msg.get("tool_calls") or []):
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append({"id": call.get("id") or f"call-{i}", "name": call["function"]["name"], "arguments": args})
        return {"content": msg.get("content") or "", "tool_calls": calls}


def system_prompt(user, help_base: str) -> str:
    return SYSTEM_PROMPT.format(
        name=user["name"], email=user["email"], role=user["role"], tenant_name=user["tenant_name"],
        domain=user["domain"], help_base=help_base.rstrip("/"),
    )


def run(backend, tools: Tools, system: str, history: list[dict]) -> tuple[str, list[dict]]:
    """Answer the conversation, calling tools as the model asks. Returns the reply and
    the tool calls made with their results, in order."""
    messages = [{"role": "system", "content": system}, *history]
    trace: list[dict] = []
    for _ in range(MAX_ROUNDS):
        out = backend.chat(messages, SPECS)
        if not out["tool_calls"]:
            return out["content"], trace
        messages.append({
            "role": "assistant",
            "content": out["content"],
            "tool_calls": [
                {"id": c["id"], "type": "function",
                 "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])}}
                for c in out["tool_calls"]
            ],
        })
        for call in out["tool_calls"]:
            result = tools.call(call["name"], call["arguments"])
            trace.append({"tool": call["name"], "arguments": call["arguments"], "result": result})
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
    return "I could not finish that request.", trace
