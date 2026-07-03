"""Pluggable local LLM backend for the ModelForge assistant.

Two backends are supported, selected by ``DVML_LLM_BACKEND``:

* ``stub``   — deterministic, offline. Used in CI and for reproducible demos.
* ``ollama`` — a local Ollama server (Metal-accelerated on macOS). Configure the
  model with ``DVML_LLM_MODEL`` (e.g. ``llama3.1``).

Both expose the same :func:`chat` contract and return
``{"content": str, "tool_calls": [{"name": str, "arguments": dict}]}``.
"""
from __future__ import annotations

import json
import re

import requests

from ..core.config import Config

# The assistant is trusted to act on behalf of the user, so it may invoke tools.
# For determinism, the stub honours inline action directives of the form
# ``[[TOOL:<name> <json-or-text-args>]]`` found anywhere in the conversation.
_ACTION_RE = re.compile(r"\[\[TOOL:(\w+)\s+(.*?)\]\]", re.DOTALL)


def _parse_args(raw: str) -> dict:
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {"input": raw}


def _stub_chat(messages: list[dict], tools: list[dict] | None) -> dict:
    conversation = "\n".join(m.get("content", "") for m in messages)
    calls = []
    for name, raw in _ACTION_RE.findall(conversation):
        calls.append({"name": name, "arguments": _parse_args(raw)})
    if calls:
        return {"content": "", "tool_calls": calls}
    last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    return {"content": f"Here's a summary based on the available context: {last_user[:200]}",
            "tool_calls": []}


def _ollama_chat(messages: list[dict], tools: list[dict] | None) -> dict:
    payload = {"model": Config.LLM_MODEL, "messages": messages, "stream": False}
    if tools:
        payload["tools"] = tools
    resp = requests.post(f"{Config.LLM_OLLAMA_URL}/api/chat", json=payload, timeout=120)
    resp.raise_for_status()
    body = resp.json()
    msg = body.get("message", {})
    calls = []
    for tc in msg.get("tool_calls", []) or []:
        fn = tc.get("function", {})
        args = fn.get("arguments", {})
        if isinstance(args, str):
            args = _parse_args(args)
        calls.append({"name": fn.get("name"), "arguments": args})
    return {"content": msg.get("content", ""), "tool_calls": calls}


def chat(messages: list[dict], tools: list[dict] | None = None) -> dict:
    if Config.LLM_BACKEND == "ollama":
        return _ollama_chat(messages, tools)
    return _stub_chat(messages, tools)
