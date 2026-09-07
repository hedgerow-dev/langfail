"""Object-boundary lookups for the four authorization-model demos.

Each ``fetch_*`` pairs with one HTTP route in ``http/boundaries.py``: the route
extracts the caller's identity and the requested id from the request (the
source), this module decides which record actually gets returned (the sink).
Splitting the decision out here means the id that reaches a lookup and the
lookup's own (mis)handling of ownership live in different files.
"""
from __future__ import annotations

from typing import Optional

from ..core.store import db
from ..records import Memo, Post, Squad, SquadMemo, Ticket, Workspace


def _by_id(model, record_id: int):
    """Thin wrapper over the primary-key lookup, used by every unchecked read."""
    return db.session.get(model, record_id)


# --- ownership (Memo) --------------------------------------------------------

def fetch_memo_unchecked(memo_id: int) -> Optional[Memo]:
    return _by_id(Memo, memo_id)


def fetch_memo_conditional(memo_id: int, account_id: int, enforce: bool) -> tuple[Optional[Memo], bool]:
    """Return ``(memo, allowed)``; the ownership check only runs when ``enforce``."""
    memo = _by_id(Memo, memo_id)
    if memo is None:
        return None, False
    allowed = not (enforce and memo.owner_id != account_id)
    return memo, allowed


def fetch_memo_scoped(memo_id: int, account_id: int) -> Optional[Memo]:
    """Query-fused: ownership is part of the filter, not a separate check."""
    return Memo.query.filter(Memo.id == memo_id, Memo.owner_id == account_id).first()


def fetch_memo_checked(memo_id: int, account_id: int) -> tuple[Optional[Memo], bool]:
    """Fetch-then-guard: returns ``(memo, allowed)`` for the caller to branch on."""
    memo = _by_id(Memo, memo_id)
    if memo is None:
        return None, False
    return memo, memo.owner_id == account_id


# --- membership (SquadMemo) --------------------------------------------------

def fetch_squad_memo_unchecked(note_id: int) -> Optional[SquadMemo]:
    return _by_id(SquadMemo, note_id)


def fetch_squad_memo_conditional(note_id: int, account_id: int, enforce: bool) -> tuple[Optional[SquadMemo], bool]:
    note = _by_id(SquadMemo, note_id)
    if note is None:
        return None, False
    allowed = not (enforce and account_id not in note.squad.roster)
    return note, allowed


def fetch_squad_memo_checked(note_id: int, account_id: int) -> tuple[Optional[SquadMemo], bool]:
    note = _by_id(SquadMemo, note_id)
    if note is None:
        return None, False
    return note, account_id in note.squad.roster


def is_squad_member(squad_id: int, account_id: int) -> bool:
    squad = _by_id(Squad, squad_id)
    return bool(squad) and account_id in squad.roster


# --- hierarchical (Ticket under Workspace) -----------------------------------

def fetch_ticket_unchecked(ticket_id: int) -> Optional[Ticket]:
    return _by_id(Ticket, ticket_id)


def fetch_ticket_ignoring_workspace(ticket_id: int, workspace_id: int) -> Optional[Ticket]:
    """``workspace_id`` is accepted (it looks like scoping) but never used."""
    return _by_id(Ticket, ticket_id)


def fetch_ticket_via_workspace_id(ticket_id: int, workspace_id: int, account_id: int) -> Optional[Ticket]:
    workspace = Workspace.query.filter(Workspace.id == workspace_id,
                                       Workspace.owner_id == account_id).first()
    if workspace is None:
        return None
    return Ticket.query.filter(Ticket.id == ticket_id, Ticket.workspace_id == workspace.id).first()


def fetch_ticket_via_workspace_object(ticket_id: int, workspace_id: int, account_id: int) -> Optional[Ticket]:
    workspace = Workspace.query.filter(Workspace.id == workspace_id,
                                       Workspace.owner_id == account_id).first()
    if workspace is None:
        return None
    return Ticket.query.filter(Ticket.id == ticket_id, Ticket.workspace == workspace).first()


# --- status (Post) ------------------------------------------------------------

def fetch_post_unchecked(post_id: int) -> Optional[Post]:
    return _by_id(Post, post_id)


def fetch_post_conditional(post_id: int, enforce: bool) -> tuple[Optional[Post], bool]:
    post = _by_id(Post, post_id)
    if post is None:
        return None, False
    allowed = not (enforce and post.status != "published")
    return post, allowed


def fetch_post_gated(post_id: int) -> Optional[Post]:
    post = _by_id(Post, post_id)
    if post is None or post.status != "published":
        return None
    return post


def fetch_post_scoped(post_id: int) -> Optional[Post]:
    return Post.query.filter(Post.id == post_id, Post.status == "published").first()
