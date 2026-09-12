"""Support-desk assistant: draft a reply grounded in an account's details.

Lets support staff ask the assistant to draft a reply referencing a specific
account (e.g. "let them know their export finished") without having to restate
the account details themselves.
"""
from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")


def _account_summary(account) -> str:
    return f"Account: username={account.username}, email={account.email or ''}"


def draft_reply(account_id: int, question: str) -> dict:
    """Draft a reply for ``account_id``, grounding the assistant in their
    account details exactly as stored -- including their email address, sent
    to the model call with no redaction."""
    from ..core.store import db
    from ..records import Account
    from .loop import run_assistant

    account = db.session.get(Account, account_id)
    if not account:
        return {"error": "not found"}
    return run_assistant(question, context_docs=[_account_summary(account)])


def draft_reply_redacted(account_id: int, question: str) -> dict:
    """Like :func:`draft_reply`, but redacts email addresses from the account
    context before it ever reaches the model call."""
    from ..core.store import db
    from ..records import Account
    from .loop import run_assistant

    account = db.session.get(Account, account_id)
    if not account:
        return {"error": "not found"}
    context = _EMAIL_RE.sub("[REDACTED_EMAIL]", _account_summary(account))
    return run_assistant(question, context_docs=[context])
