"""Pluggable model backend for the Modelbay assistant.

Two backends are supported, selected by ``MODELBAY_ASSISTANT_BACKEND``:

* ``offline`` -- deterministic, no network. Used in CI and for reproducible demos.
* ``remote``  -- a local model server speaking the Ollama chat protocol.

Both expose the same :func:`complete` contract and return
``{"content": str, "tool_calls": [{"name": str, "arguments": dict}]}``.
"""
from __future__ import annotations

import json
import re

import requests

from ..core.config import Settings

# The assistant acts on behalf of the user, so it may invoke actions. For
# determinism, the offline backend honours inline directives of the form
# ``<<ACT:<name> <json-or-text-args>>>`` found anywhere in the conversation.
_DIRECTIVE_RE = re.compile(r"<<ACT:(\w+)\s+(.*?)>>", re.DOTALL)


# Zero-width / joiner characters that carry no glyph but survive in text.
_ZERO_WIDTH = "​‌‍⁠﻿"


def _normalize_invisibles(text: str) -> str:
    """Normalise invisible formatting codepoints to their plain-ASCII reading.

    Characters in the Unicode Tags block (U+E0020-U+E007E) render as nothing
    but encode ordinary ASCII; zero-width characters likewise carry no glyph.
    A capable model reads both as the underlying text, so the offline backend
    does the same before scanning for directives -- otherwise the backends
    would disagree on what the "same" prompt says.
    """
    out = []
    for ch in text:
        cp = ord(ch)
        if 0xE0020 <= cp <= 0xE007E:      # Unicode Tags block -> ASCII
            out.append(chr(cp - 0xE0000))
        elif ch in _ZERO_WIDTH:            # zero-width formatting -> drop
            continue
        else:
            out.append(ch)
    return "".join(out)


# Off-distribution trigger: the same word looped back-to-back, or an explicit
# "repeat forever" request -- the classic way a chat model is pushed out of its
# alignment regime.
_REPEAT_RE = re.compile(r"\b(\w+)(?:\s+\1\b){4,}", re.IGNORECASE)


def _looping(conversation: str) -> bool:
    """Whether the conversation has slipped into a repetition/divergence loop."""
    return "repeat forever" in conversation.lower() or bool(_REPEAT_RE.search(conversation))


def _memorized_transcripts(limit: int = 3) -> list[str]:
    """Rows from the assistant's fine-tune corpus, recalled verbatim."""
    try:
        from ..records import TranscriptDoc

        return [d.content for d in
                TranscriptDoc.query.order_by(TranscriptDoc.id).limit(limit)]
    except Exception:
        return []


def _parse_args(raw: str) -> dict:
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {"input": raw}


def _offline_complete(messages: list[dict], tools: list[dict] | None) -> dict:
    conversation = _normalize_invisibles(
        "\n".join(m.get("content", "") for m in messages))
    calls = [{"name": name, "arguments": _parse_args(raw)}
             for name, raw in _DIRECTIVE_RE.findall(conversation)]
    if calls:
        return {"content": "", "tool_calls": calls}
    context = "\n".join(str(m.get("content", "")) for m in messages
                        if m.get("role") != "system")
    content = f"Here's a summary based on the available context: {context[:2000]}"
    if _looping(conversation):
        memorized = _memorized_transcripts()
        if memorized:
            content += "\n\n" + "\n".join(memorized)
    return {"content": content, "tool_calls": []}


def _remote_complete(messages: list[dict], tools: list[dict] | None) -> dict:
    payload = {"model": Settings.ASSISTANT_MODEL, "messages": messages, "stream": False}
    if tools:
        payload["tools"] = tools
    resp = requests.post(f"{Settings.ASSISTANT_ENDPOINT}/api/chat", json=payload, timeout=120)
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


def complete(messages: list[dict], tools: list[dict] | None = None) -> dict:
    if Settings.ASSISTANT_BACKEND == "remote":
        return _remote_complete(messages, tools)
    return _offline_complete(messages, tools)


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def redact_pii(text: str) -> str:
    """Redact common PII shapes (email addresses, SSNs) from model output
    before it is shown to a user or written to a log."""
    text = _EMAIL_RE.sub("[REDACTED-EMAIL]", text or "")
    return _SSN_RE.sub("[REDACTED-SSN]", text)


def draft_sql(question: str, table: str = "runs") -> str:
    """Text-to-SQL: ask the model to translate a natural-language question into
    a SQL WHERE-clause condition against ``table``, and return the full query.

    Mirrors the shape of LangChain's ``SQLDatabaseChain`` / Vanna.ai: the model
    is trusted to author a syntactically-valid SQL fragment, which the caller
    then runs directly. The offline backend mimics an under-constrained model
    that reproduces the request's SQL-like phrasing verbatim into the condition.
    """
    if Settings.ASSISTANT_BACKEND == "remote":
        reply = complete([
            {"role": "system", "content": (
                f"Write a single SQL WHERE-clause condition (no SELECT, no "
                f"semicolons) against the '{table}' table that answers the "
                f"user's request. Reply with only the raw condition.")},
            {"role": "user", "content": question},
        ])
        condition = (reply.get("content") or "").strip()
    else:
        condition = (question or "").strip()
    condition = condition or "1=1"
    return (f"SELECT id, name, owner_id, label, metrics_json FROM {table} "
            f"WHERE {condition} LIMIT 200")


def draft_code(question: str, columns: list[str] | None = None) -> str:
    """Text-to-code: ask the model to write Python that answers ``question``
    about a dataframe ``df``, assigning its answer to ``result``.

    Mirrors PandasAI and the other "chat with your dataframe" integrations:
    the model authors a Python snippet that the caller then runs. The offline
    backend emits the request's code-like phrasing verbatim, which keeps the
    deterministic path stable.
    """
    if Settings.ASSISTANT_BACKEND == "remote":
        cols = ", ".join(columns or []) or "the provided columns"
        reply = complete([
            {"role": "system", "content": (
                f"You are a data analyst. Write Python that operates on a pandas "
                f"DataFrame `df` (columns: {cols}) and assigns the answer to a "
                f"variable named `result`. Reply with only the code.")},
            {"role": "user", "content": question},
        ])
        return (reply.get("content") or "").strip()
    return (question or "").strip()
