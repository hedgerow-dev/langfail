"""Prompt-injection input filtering for the assistant.

Before the assistant acts on user- or document-supplied text we strip the
inline action-control syntax it honours (``<<ACT:...>>``) so untrusted content
cannot smuggle action calls into the conversation. Applied on the filtered
``/assistant/ask`` path.
"""
from __future__ import annotations

import re

# Matches the literal ASCII directive syntax the assistant interprets.
_DIRECTIVE_RE = re.compile(r"<<ACT:.*?>>", re.DOTALL)


def scrub_directives(text: str) -> str:
    """Remove inline ``<<ACT:...>>`` directives from untrusted text."""
    return _DIRECTIVE_RE.sub("", text or "")
