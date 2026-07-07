"""Prompt-injection input filtering for the assistant.

Before the assistant acts on user- or document-supplied text we strip the inline
tool-control syntax the agent honours (``[[TOOL:...]]``) so untrusted content
cannot smuggle tool calls into the conversation. Applied on the guarded
``/api/agent/ask`` path.
"""
from __future__ import annotations

import re

# Matches the literal ASCII directive syntax the agent interprets.
_DIRECTIVE_RE = re.compile(r"\[\[TOOL:.*?\]\]", re.DOTALL)


def strip_directives(text: str) -> str:
    """Remove inline ``[[TOOL:...]]`` directives from untrusted text."""
    return _DIRECTIVE_RE.sub("", text or "")
