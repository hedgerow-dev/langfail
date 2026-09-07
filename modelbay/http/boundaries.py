"""Object-boundary demo routes.

Four object-level authorization models in isolation -- ownership, membership,
hierarchical (parent/child), and status/publication gating -- each with a
default lookup plus a handful of scoped variants. Setup (create) endpoints are
unguarded by design (any account may create its own memo/squad/workspace/post);
the read variants below are what differs.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..core.store import db
from ..records import Memo, Post, Squad, SquadMemo, SquadRoster, Ticket, Workspace
from ..store import boundaries_repo as repo
from .guard import authenticated

bp = Blueprint("boundaries", __name__, url_prefix="/boundaries")


# --- setup ------------------------------------------------------------------

@bp.post("/memos")
@authenticated
def add_memo():
    data = request.get_json(force=True, silent=True) or {}
    memo = Memo(owner_id=g.account_id, title=data.get("title", "untitled"),
                body=data.get("body", ""))
    db.session.add(memo)
    db.session.commit()
    return jsonify(id=memo.id), 201


@bp.post("/squads")
@authenticated
def add_squad():
    data = request.get_json(force=True, silent=True) or {}
    squad = Squad(name=data.get("name", "squad"))
    db.session.add(squad)
    db.session.commit()
    if data.get("include_creator", True):
        db.session.add(SquadRoster(squad_id=squad.id, account_id=g.account_id))
        db.session.commit()
    return jsonify(id=squad.id), 201


@bp.post("/squads/<int:squad_id>/roster")
@authenticated
def add_squad_member(squad_id: int):
    """Add an account to a squad. Restricted to existing members: this
    endpoint is the only way a squad's roster grows after creation, so an
    unguarded version here would let anyone self-add to any squad and walk
    straight through the membership checks below (read_squad_memo_checked) --
    the guard would be checking a value the caller could set themselves
    first."""
    if not repo.is_squad_member(squad_id, g.account_id):
        return jsonify(error="forbidden"), 403
    data = request.get_json(force=True, silent=True) or {}
    db.session.add(SquadRoster(squad_id=squad_id, account_id=int(data["account_id"])))
    db.session.commit()
    return jsonify(ok=True), 201


@bp.post("/squad-memos")
@authenticated
def add_squad_memo():
    data = request.get_json(force=True, silent=True) or {}
    note = SquadMemo(squad_id=int(data["squad_id"]), title=data.get("title", "untitled"),
                     body=data.get("body", ""))
    db.session.add(note)
    db.session.commit()
    return jsonify(id=note.id), 201


@bp.post("/workspaces")
@authenticated
def add_workspace():
    data = request.get_json(force=True, silent=True) or {}
    workspace = Workspace(owner_id=g.account_id, name=data.get("name", "workspace"))
    db.session.add(workspace)
    db.session.commit()
    return jsonify(id=workspace.id), 201


@bp.post("/workspaces/<int:workspace_id>/tickets")
@authenticated
def add_ticket(workspace_id: int):
    data = request.get_json(force=True, silent=True) or {}
    ticket = Ticket(workspace_id=workspace_id, title=data.get("title", "untitled"),
                    body=data.get("body", ""))
    db.session.add(ticket)
    db.session.commit()
    return jsonify(id=ticket.id), 201


@bp.post("/posts")
@authenticated
def add_post():
    data = request.get_json(force=True, silent=True) or {}
    post = Post(owner_id=g.account_id, title=data.get("title", "untitled"),
                body=data.get("body", ""), status=data.get("status", "draft"))
    db.session.add(post)
    db.session.commit()
    return jsonify(id=post.id), 201


# --- ownership model: Memo ---------------------------------------------------

@bp.get("/memos/<int:memo_id>")
@authenticated
def read_memo(memo_id: int):
    """Return a memo by id."""
    memo = repo.fetch_memo_unchecked(memo_id)
    if not memo:
        return jsonify(error="not found"), 404
    return jsonify(id=memo.id, title=memo.title, body=memo.body)


@bp.get("/memos/<int:memo_id>/conditional")
@authenticated
def read_memo_conditional(memo_id: int):
    """Return a memo by id; ownership is only enforced when the caller
    passes ?enforce=on (a single combined condition, rather than a nested
    if -- same bypass, different shape)."""
    memo, allowed = repo.fetch_memo_conditional(
        memo_id, g.account_id, enforce=request.args.get("enforce") == "on")
    if memo is None:
        return jsonify(error="not found"), 404
    if not allowed:
        return jsonify(error="forbidden"), 403
    return jsonify(id=memo.id, title=memo.title, body=memo.body)


@bp.get("/memos/<int:memo_id>/prebuilt")
@authenticated
def read_memo_prebuilt(memo_id: int):
    """Return a memo by id. The response payload is built from the memo's
    fields before the ownership check runs, but the check's own deny branch
    returns a separate response object, so the built payload is discarded
    whenever the caller isn't the owner."""
    memo = repo.fetch_memo_unchecked(memo_id)
    if not memo:
        return jsonify(error="not found"), 404
    payload = jsonify(id=memo.id, title=memo.title, body=memo.body)
    if memo.owner_id != g.account_id:
        return jsonify(error="forbidden"), 403
    return payload


@bp.get("/memos/<int:memo_id>/scoped")
@authenticated
def read_memo_scoped(memo_id: int):
    """Return a memo by id, scoped to the caller via a query filter."""
    memo = repo.fetch_memo_scoped(memo_id, g.account_id)
    if not memo:
        return jsonify(error="not found"), 404
    return jsonify(id=memo.id, title=memo.title, body=memo.body)


@bp.get("/memos/<int:memo_id>/checked")
@authenticated
def read_memo_checked(memo_id: int):
    """Return a memo by id, after checking the caller owns it."""
    memo, allowed = repo.fetch_memo_checked(memo_id, g.account_id)
    if memo is None:
        return jsonify(error="not found"), 404
    if not allowed:
        return jsonify(error="forbidden"), 403
    return jsonify(id=memo.id, title=memo.title, body=memo.body)


@bp.get("/memos/<int:memo_id>/checked-positive")
@authenticated
def read_memo_checked_positive(memo_id: int):
    """Return a memo by id, after checking the caller owns it (ownership
    checked positively, with an else-deny branch -- same guarantee as
    read_memo_checked, inverted syntax)."""
    memo, allowed = repo.fetch_memo_checked(memo_id, g.account_id)
    if memo is None:
        return jsonify(error="not found"), 404
    if allowed:
        pass
    else:
        return jsonify(error="forbidden"), 403
    return jsonify(id=memo.id, title=memo.title, body=memo.body)


# --- membership model: Squad / SquadRoster / SquadMemo -----------------------

@bp.get("/squad-memos/<int:note_id>")
@authenticated
def read_squad_memo(note_id: int):
    """Return a squad memo by id."""
    note = repo.fetch_squad_memo_unchecked(note_id)
    if not note:
        return jsonify(error="not found"), 404
    return jsonify(id=note.id, title=note.title, body=note.body)


@bp.get("/squad-memos/<int:note_id>/conditional")
@authenticated
def read_squad_memo_conditional(note_id: int):
    """Return a squad memo by id; membership is only enforced when the
    caller passes ?enforce=on."""
    note, allowed = repo.fetch_squad_memo_conditional(
        note_id, g.account_id, enforce=request.args.get("enforce") == "on")
    if note is None:
        return jsonify(error="not found"), 404
    if not allowed:
        return jsonify(error="forbidden"), 403
    return jsonify(id=note.id, title=note.title, body=note.body)


@bp.get("/squad-memos/<int:note_id>/checked")
@authenticated
def read_squad_memo_checked(note_id: int):
    """Return a squad memo by id, after checking the caller is on its
    squad's roster."""
    note, allowed = repo.fetch_squad_memo_checked(note_id, g.account_id)
    if note is None:
        return jsonify(error="not found"), 404
    if not allowed:
        return jsonify(error="forbidden"), 403
    return jsonify(id=note.id, title=note.title, body=note.body)


@bp.get("/squad-memos/<int:note_id>/checked-positive")
@authenticated
def read_squad_memo_checked_positive(note_id: int):
    """Return a squad memo by id, after checking roster membership
    (checked positively, with an else-deny branch)."""
    note, allowed = repo.fetch_squad_memo_checked(note_id, g.account_id)
    if note is None:
        return jsonify(error="not found"), 404
    if allowed:
        pass
    else:
        return jsonify(error="forbidden"), 403
    return jsonify(id=note.id, title=note.title, body=note.body)


# --- hierarchical model: Workspace / Ticket ----------------------------------

@bp.get("/tickets/<int:ticket_id>")
@authenticated
def read_ticket(ticket_id: int):
    """Return a ticket by id."""
    ticket = repo.fetch_ticket_unchecked(ticket_id)
    if not ticket:
        return jsonify(error="not found"), 404
    return jsonify(id=ticket.id, title=ticket.title, body=ticket.body)


@bp.get("/workspaces/<int:workspace_id>/tickets/<int:ticket_id>/direct")
@authenticated
def read_ticket_under_workspace(workspace_id: int, ticket_id: int):
    """Return a ticket by id under a workspace path; the ticket is looked up
    by ticket_id alone, so the workspace_id in the path does not scope the
    read."""
    ticket = repo.fetch_ticket_ignoring_workspace(ticket_id, workspace_id)
    if not ticket:
        return jsonify(error="not found"), 404
    return jsonify(id=ticket.id, title=ticket.title, body=ticket.body)


@bp.get("/workspaces/<int:workspace_id>/tickets/<int:ticket_id>")
@authenticated
def read_ticket_via_workspace_id(workspace_id: int, ticket_id: int):
    """Return a ticket by id, scoped to a workspace the caller owns."""
    ticket = repo.fetch_ticket_via_workspace_id(ticket_id, workspace_id, g.account_id)
    if not ticket:
        return jsonify(error="not found"), 404
    return jsonify(id=ticket.id, title=ticket.title, body=ticket.body)


@bp.get("/workspaces/<int:workspace_id>/tickets/<int:ticket_id>/via-object")
@authenticated
def read_ticket_via_workspace_object(workspace_id: int, ticket_id: int):
    """Return a ticket by id, scoped to a workspace the caller owns (matched
    via the workspace relationship rather than a second id comparison)."""
    ticket = repo.fetch_ticket_via_workspace_object(ticket_id, workspace_id, g.account_id)
    if not ticket:
        return jsonify(error="not found"), 404
    return jsonify(id=ticket.id, title=ticket.title, body=ticket.body)


# --- status model: Post -------------------------------------------------------

@bp.get("/posts/<int:post_id>")
@authenticated
def read_post(post_id: int):
    """Return a post by id."""
    post = repo.fetch_post_unchecked(post_id)
    if not post:
        return jsonify(error="not found"), 404
    return jsonify(id=post.id, title=post.title, body=post.body, status=post.status)


@bp.get("/posts/<int:post_id>/conditional")
@authenticated
def read_post_conditional(post_id: int):
    """Return a post by id; the published-status gate only runs when the
    caller passes ?enforce=on."""
    post, allowed = repo.fetch_post_conditional(post_id, enforce=request.args.get("enforce") == "on")
    if post is None or not allowed:
        return jsonify(error="not found"), 404
    return jsonify(id=post.id, title=post.title, body=post.body)


@bp.get("/posts/<int:post_id>/gated")
@authenticated
def read_post_gated(post_id: int):
    """Return a post by id, after checking it is published."""
    post = repo.fetch_post_gated(post_id)
    if not post:
        return jsonify(error="not found"), 404
    return jsonify(id=post.id, title=post.title, body=post.body)


@bp.get("/posts/<int:post_id>/scoped")
@authenticated
def read_post_scoped(post_id: int):
    """Return a post by id, scoped to published posts via a query filter."""
    post = repo.fetch_post_scoped(post_id)
    if not post:
        return jsonify(error="not found"), 404
    return jsonify(id=post.id, title=post.title, body=post.body)
