"""Support-agent assistant: draft a reply grounded in a user's account details.

Lets support staff ask the assistant to draft a reply referencing a specific
user's account (e.g. "let them know their export finished") without having to
restate the account details themselves.
"""
from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")


def _account_context(user) -> str:
    return f"Account: username={user.username}, email={user.email or ''}"


def draft_support_reply(user_id: int, question: str) -> dict:
    """Draft a reply for ``user_id``'s account, grounding the assistant in
    their account details exactly as stored -- including their email address,
    sent to the LLM call with no redaction."""
    from ..core.db import db
    from ..models import User
    from ..agent.core import run_agent

    user = db.session.get(User, user_id)
    if not user:
        return {"error": "not found"}
    return run_agent(question, context_docs=[_account_context(user)])


def draft_support_reply_safe(user_id: int, question: str) -> dict:
    """Like :func:`draft_support_reply`, but redacts email addresses from the
    account context before it ever reaches the LLM call."""
    from ..core.db import db
    from ..models import User
    from ..agent.core import run_agent

    user = db.session.get(User, user_id)
    if not user:
        return {"error": "not found"}
    context = _EMAIL_RE.sub("[REDACTED_EMAIL]", _account_context(user))
    return run_agent(question, context_docs=[context])
