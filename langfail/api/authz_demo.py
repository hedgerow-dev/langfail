"""Object-level authorization demo routes.

A self-contained set of routes exercising four object-level authorization
models in isolation -- ownership, membership, hierarchical (parent/child),
and status/publication gating -- each with a default lookup plus a handful
of scoped variants.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..core.db import db
from ..models import Article, PrivateNote, Project, Task, Team, TeamMember, TeamNote
from .deps import require_auth

bp = Blueprint("authz_demo", __name__, url_prefix="/api/authz-demo")


# --- setup: private notes, team notes, projects/tasks, articles ----------

@bp.post("/notes")
@require_auth
def create_note():
    data = request.get_json(force=True, silent=True) or {}
    note = PrivateNote(owner_id=g.user_id, title=data.get("title", "untitled"),
                        body=data.get("body", ""))
    db.session.add(note)
    db.session.commit()
    return jsonify(id=note.id), 201


@bp.post("/teams")
@require_auth
def create_team():
    data = request.get_json(force=True, silent=True) or {}
    team = Team(name=data.get("name", "team"))
    db.session.add(team)
    db.session.commit()
    if data.get("include_creator", True):
        db.session.add(TeamMember(team_id=team.id, user_id=g.user_id))
        db.session.commit()
    return jsonify(id=team.id), 201


@bp.post("/teams/<int:team_id>/members")
@require_auth
def add_team_member(team_id: int):
    """Add a user to a team. Restricted to existing members: this endpoint
    is the only way `Team.members` grows after creation, so an unguarded
    version here would let anyone self-add to any team and walk straight
    through the membership checks below (get_team_note_guarded /
    get_team_note_guarded_inverted) -- the guard would be checking a value the
    caller could set themselves first."""
    team = db.session.get(Team, team_id)
    if not team or g.user_id not in team.members:
        return jsonify(error="forbidden"), 403
    data = request.get_json(force=True, silent=True) or {}
    db.session.add(TeamMember(team_id=team_id, user_id=int(data["user_id"])))
    db.session.commit()
    return jsonify(ok=True), 201


@bp.post("/team-notes")
@require_auth
def create_team_note():
    data = request.get_json(force=True, silent=True) or {}
    note = TeamNote(team_id=int(data["team_id"]), title=data.get("title", "untitled"),
                     body=data.get("body", ""))
    db.session.add(note)
    db.session.commit()
    return jsonify(id=note.id), 201


@bp.post("/projects")
@require_auth
def create_project():
    data = request.get_json(force=True, silent=True) or {}
    project = Project(owner_id=g.user_id, name=data.get("name", "project"))
    db.session.add(project)
    db.session.commit()
    return jsonify(id=project.id), 201


@bp.post("/projects/<int:project_id>/tasks")
@require_auth
def create_task(project_id: int):
    data = request.get_json(force=True, silent=True) or {}
    task = Task(project_id=project_id, title=data.get("title", "untitled"),
                body=data.get("body", ""))
    db.session.add(task)
    db.session.commit()
    return jsonify(id=task.id), 201


@bp.post("/articles")
@require_auth
def create_article():
    data = request.get_json(force=True, silent=True) or {}
    article = Article(owner_id=g.user_id, title=data.get("title", "untitled"),
                       body=data.get("body", ""), status=data.get("status", "draft"))
    db.session.add(article)
    db.session.commit()
    return jsonify(id=article.id), 201


# --- ownership model: PrivateNote ------------------------------------------

@bp.get("/notes/<int:note_id>")
@require_auth
def get_note(note_id: int):
    """Return a private note by id."""
    note = db.session.get(PrivateNote, note_id)
    if not note:
        return jsonify(error="not found"), 404
    return jsonify(id=note.id, title=note.title, body=note.body)


@bp.get("/notes/<int:note_id>/branchy")
@require_auth
def get_note_branchy(note_id: int):
    """Return a private note by id; ownership is only checked when the
    caller passes ?mode=strict."""
    note = db.session.get(PrivateNote, note_id)
    if not note:
        return jsonify(error="not found"), 404
    if request.args.get("mode") == "strict":
        if note.owner_id != g.user_id:
            return jsonify(error="forbidden"), 403
    return jsonify(id=note.id, title=note.title, body=note.body)


@bp.get("/notes/<int:note_id>/late-built")
@require_auth
def get_note_late_built(note_id: int):
    """Return a private note by id. The response payload is built from the
    note's fields before the ownership check runs, but the check's own deny
    branch returns a separate response object, so the built payload is
    discarded whenever the caller isn't the owner."""
    note = db.session.get(PrivateNote, note_id)
    if not note:
        return jsonify(error="not found"), 404
    payload = jsonify(id=note.id, title=note.title, body=note.body)
    if note.owner_id != g.user_id:
        return jsonify(error="forbidden"), 403
    return payload


@bp.get("/notes/<int:note_id>/fused")
@require_auth
def get_note_fused(note_id: int):
    """Return a private note by id, scoped to the caller via a query filter."""
    note = PrivateNote.query.filter_by(id=note_id, owner_id=g.user_id).first()
    if not note:
        return jsonify(error="not found"), 404
    return jsonify(id=note.id, title=note.title, body=note.body)


@bp.get("/notes/<int:note_id>/guarded")
@require_auth
def get_note_guarded(note_id: int):
    """Return a private note by id, after checking the caller owns it."""
    note = db.session.get(PrivateNote, note_id)
    if not note:
        return jsonify(error="not found"), 404
    if note.owner_id != g.user_id:
        return jsonify(error="forbidden"), 403
    return jsonify(id=note.id, title=note.title, body=note.body)


@bp.get("/notes/<int:note_id>/guarded-inverted")
@require_auth
def get_note_guarded_inverted(note_id: int):
    """Return a private note by id, after checking the caller owns it
    (ownership checked positively, with an else-deny branch)."""
    note = db.session.get(PrivateNote, note_id)
    if not note:
        return jsonify(error="not found"), 404
    if note.owner_id == g.user_id:
        pass
    else:
        return jsonify(error="forbidden"), 403
    return jsonify(id=note.id, title=note.title, body=note.body)


# --- membership model: Team / TeamMember / TeamNote ------------------------

@bp.get("/team-notes/<int:note_id>")
@require_auth
def get_team_note(note_id: int):
    """Return a team note by id."""
    note = db.session.get(TeamNote, note_id)
    if not note:
        return jsonify(error="not found"), 404
    return jsonify(id=note.id, title=note.title, body=note.body)


@bp.get("/team-notes/<int:note_id>/branchy")
@require_auth
def get_team_note_branchy(note_id: int):
    """Return a team note by id; membership is only checked when the caller
    passes ?mode=strict."""
    note = db.session.get(TeamNote, note_id)
    if not note:
        return jsonify(error="not found"), 404
    if request.args.get("mode") == "strict":
        if g.user_id not in note.team.members:
            return jsonify(error="forbidden"), 403
    return jsonify(id=note.id, title=note.title, body=note.body)


@bp.get("/team-notes/<int:note_id>/guarded")
@require_auth
def get_team_note_guarded(note_id: int):
    """Return a team note by id, after checking the caller is a member of
    its team."""
    note = db.session.get(TeamNote, note_id)
    if not note:
        return jsonify(error="not found"), 404
    if g.user_id not in note.team.members:
        return jsonify(error="forbidden"), 403
    return jsonify(id=note.id, title=note.title, body=note.body)


@bp.get("/team-notes/<int:note_id>/guarded-inverted")
@require_auth
def get_team_note_guarded_inverted(note_id: int):
    """Return a team note by id, after checking the caller is a member of
    its team (membership checked positively, with an else-deny branch)."""
    note = db.session.get(TeamNote, note_id)
    if not note:
        return jsonify(error="not found"), 404
    if g.user_id in note.team.members:
        pass
    else:
        return jsonify(error="forbidden"), 403
    return jsonify(id=note.id, title=note.title, body=note.body)


# --- hierarchical model: Project / Task ------------------------------------

@bp.get("/tasks/<int:task_id>")
@require_auth
def get_task(task_id: int):
    """Return a task by id."""
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify(error="not found"), 404
    return jsonify(id=task.id, title=task.title, body=task.body)


@bp.get("/projects/<int:project_id>/tasks/<int:task_id>/direct")
@require_auth
def get_task_under_project(project_id: int, task_id: int):
    """Return a task by id under a project path; the task is looked up by
    task_id alone, so the project_id in the path does not scope the read."""
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify(error="not found"), 404
    return jsonify(id=task.id, title=task.title, body=task.body)


@bp.get("/projects/<int:project_id>/tasks/<int:task_id>")
@require_auth
def get_task_via_parent_id(project_id: int, task_id: int):
    """Return a task by id, scoped to a project the caller owns (matched via
    the project's id)."""
    project = Project.query.filter_by(id=project_id, owner_id=g.user_id).first()
    if not project:
        return jsonify(error="not found"), 404
    task = Task.query.filter_by(id=task_id, project_id=project.id).first()
    if not task:
        return jsonify(error="not found"), 404
    return jsonify(id=task.id, title=task.title, body=task.body)


@bp.get("/projects/<int:project_id>/tasks/<int:task_id>/via-object")
@require_auth
def get_task_via_parent_object(project_id: int, task_id: int):
    """Return a task by id, scoped to a project the caller owns (matched via
    the project relationship rather than its id)."""
    project = Project.query.filter_by(id=project_id, owner_id=g.user_id).first()
    if not project:
        return jsonify(error="not found"), 404
    task = Task.query.filter_by(id=task_id, project=project).first()
    if not task:
        return jsonify(error="not found"), 404
    return jsonify(id=task.id, title=task.title, body=task.body)


# --- status model: Article --------------------------------------------------

@bp.get("/articles/<int:article_id>")
@require_auth
def get_article(article_id: int):
    """Return an article by id."""
    article = db.session.get(Article, article_id)
    if not article:
        return jsonify(error="not found"), 404
    return jsonify(id=article.id, title=article.title, body=article.body,
                   status=article.status)


@bp.get("/articles/<int:article_id>/branchy")
@require_auth
def get_article_branchy(article_id: int):
    """Return an article by id; the published-status gate only runs when
    the caller passes ?strict=1."""
    article = db.session.get(Article, article_id)
    if not article:
        return jsonify(error="not found"), 404
    if request.args.get("strict") == "1":
        if article.status != "published":
            return jsonify(error="not found"), 404
    return jsonify(id=article.id, title=article.title, body=article.body)


@bp.get("/articles/<int:article_id>/gated")
@require_auth
def get_article_gated(article_id: int):
    """Return an article by id, after checking it is published."""
    article = db.session.get(Article, article_id)
    if not article:
        return jsonify(error="not found"), 404
    if article.status != "published":
        return jsonify(error="not found"), 404
    return jsonify(id=article.id, title=article.title, body=article.body)


@bp.get("/articles/<int:article_id>/fused")
@require_auth
def get_article_fused(article_id: int):
    """Return an article by id, scoped to published articles via a query
    filter."""
    article = Article.query.filter_by(id=article_id, status="published").first()
    if not article:
        return jsonify(error="not found"), 404
    return jsonify(id=article.id, title=article.title, body=article.body)
