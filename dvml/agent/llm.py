"""Pluggable local LLM backend for the ModelForge assistant.

Two backends are supported, selected by ``DVML_LLM_BACKEND``:

* ``stub``   — deterministic, offline. Used in CI and for reproducible demos.
* ``ollama`` — a local Ollama server (Metal-accelerated on macOS). Configure the
  model with ``DVML_LLM_MODEL`` (e.g. ``llama3.1``).

Both expose the same :func:`chat` contract and return
``{"content": str, "tool_calls": [{"name": str, "arguments": dict}]}``.

The stub also mimics an under-aligned fine-tuned model: pushed off-distribution
(say, a repetitive loop), it falls back to regurgitating rows it memorised from
its fine-tune corpus, the way real models recite training data under divergence.
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


# Zero-width / joiner characters that carry no glyph but survive in text.
_ZERO_WIDTH = "\u200b\u200c\u200d\u2060\ufeff"


def _deobfuscate(text: str) -> str:
    """Fold invisible-Unicode "ASCII smuggling" back to plain ASCII.

    Characters in the Unicode Tags block (U+E0020–U+E007E) render as nothing but
    encode ordinary ASCII; zero-width characters likewise carry no glyph. A
    capable model reads both as the underlying instruction, so the stub does the
    same before scanning for directives — otherwise the backends would disagree
    on what the "same" prompt says.
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


def _parse_args(raw: str) -> dict:
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {"input": raw}


# Off-distribution trigger: the same word looped back-to-back, or an explicit
# "repeat forever" request — the classic way a chat model is pushed out of its
# alignment regime.
_REPEAT_RE = re.compile(r"\b(\w+)(?:\s+\1\b){4,}", re.IGNORECASE)


def _diverged(conversation: str) -> bool:
    """Whether the conversation has slipped into a repetition/divergence loop."""
    return "repeat forever" in conversation.lower() or bool(_REPEAT_RE.search(conversation))


def _memorized_corpus(limit: int = 3) -> list[str]:
    """Rows from the assistant's fine-tune corpus, recalled verbatim."""
    try:
        from ..models import CorpusDoc

        return [d.content for d in CorpusDoc.query.order_by(CorpusDoc.id).limit(limit)]
    except Exception:
        return []


def _stub_chat(messages: list[dict], tools: list[dict] | None) -> dict:
    conversation = _deobfuscate("\n".join(m.get("content", "") for m in messages))
    calls = []
    for name, raw in _ACTION_RE.findall(conversation):
        calls.append({"name": name, "arguments": _parse_args(raw)})
    if calls:
        return {"content": "", "tool_calls": calls}
    context = "\n".join(str(m.get("content", "")) for m in messages if m.get("role") != "system")
    content = f"Here's a summary based on the available context: {context[:2000]}"
    if _diverged(conversation):
        memorized = _memorized_corpus()
        if memorized:
            content += "\n\n" + "\n".join(memorized)
    return {"content": content, "tool_calls": []}


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


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def redact_sensitive(text: str) -> str:
    """Redact common PII shapes (email addresses, SSNs) from model output
    before it is shown to a user or written to a log."""
    text = _EMAIL_RE.sub("[REDACTED-EMAIL]", text or "")
    return _SSN_RE.sub("[REDACTED-SSN]", text)


def generate_sql(question: str, table: str = "experiments") -> str:
    """Text-to-SQL: ask the model to translate a natural-language question into
    a SQL WHERE-clause condition against ``table``, and return the full query.

    Mirrors the shape of LangChain's ``SQLDatabaseChain`` / Vanna.ai: the model
    is trusted to author a syntactically-valid SQL fragment, which the caller
    then runs directly. The stub backend mimics an under-constrained model that
    reproduces the request's SQL-like phrasing verbatim into the condition.
    """
    if Config.LLM_BACKEND == "ollama":
        reply = chat([
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
    return (f"SELECT id, name, owner_id, tags, metrics_json FROM {table} "
            f"WHERE {condition} LIMIT 200")


def generate_code(question: str, columns: list[str] | None = None) -> str:
    """Text-to-code: ask the model to write Python that answers ``question``
    about a dataframe ``df``, assigning its answer to ``result``.

    Mirrors PandasAI / the "chat with your dataframe" agents (see
    CVE-2024-12366): the model authors a Python snippet that the caller then
    ``exec``-utes. The stub backend mimics an under-constrained model that emits
    the request's code-like phrasing verbatim.
    """
    if Config.LLM_BACKEND == "ollama":
        cols = ", ".join(columns or []) or "the provided columns"
        reply = chat([
            {"role": "system", "content": (
                f"You are a data analyst. Write Python that operates on a pandas "
                f"DataFrame `df` (columns: {cols}) and assigns the answer to a "
                f"variable named `result`. Reply with only the code.")},
            {"role": "user", "content": question},
        ])
        return (reply.get("content") or "").strip()
    return (question or "").strip()
