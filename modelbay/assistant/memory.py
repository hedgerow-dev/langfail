"""Persistent cross-session memory for the Modelbay assistant.

The assistant keeps a running long-term memory of facts it has picked up (a
team's naming conventions, a bundle's quirks) so useful context carries over
between sessions instead of being re-explained every time. Memories are written
as the assistant works and recalled into the prompt at the start of the next
session.
"""
from __future__ import annotations

from ..core.store import db
from ..records import AssistantMemory


def store_memory(content: str, owner_id: int | None = None) -> int:
    """Persist a memory so future sessions can recall it."""
    row = AssistantMemory(content=content, owner_id=owner_id)
    db.session.add(row)
    db.session.commit()
    return row.id


def recall_all(limit: int = 20) -> list[str]:
    """Return recent memories to seed the next session's context.

    The shared assistant is an org-wide resource: a colleague's note about a
    flaky corpus should still be there when the next person asks, so every
    session reads from the same collective memory.
    """
    rows = AssistantMemory.query.order_by(AssistantMemory.id.desc()).limit(limit).all()
    return [r.content for r in reversed(rows)]


def recall_own(owner_id: int, limit: int = 20) -> list[str]:
    """Return only the caller's own memories (per-account isolation).

    Used by the single-account notes view; the shared assistant session path
    uses :func:`recall_all`, which spans all accounts.
    """
    rows = (AssistantMemory.query.filter_by(owner_id=owner_id)
            .order_by(AssistantMemory.id.desc()).limit(limit).all())
    return [r.content for r in reversed(rows)]
