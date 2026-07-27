"""Server-rendered dashboard UI.

The dashboard is the human-facing counterpart of the JSON API: browsing the
model registry, searching models and experiments, chatting with the assistant,
and the admin settings panel. It authenticates with the same JWT the API
issues, carried in the ``session_token`` cookie so the browser session
survives page loads — the dashboard's own JavaScript also reads it to call
the JSON API directly (see base.html).
"""
from __future__ import annotations

from functools import wraps
from typing import Callable, Optional

from flask import (Blueprint, abort, g, make_response, redirect,
                   render_template, request, url_for)

from ..agent.core import run_agent
from ..core import settings as runtime_settings
from ..core.db import db
from ..core.security import decode_token, issue_token, verify_password
from ..models import Dataset, Experiment, Model, User
from ..services.markdown import render_markdown

bp = Blueprint("ui", __name__, template_folder="templates")

SESSION_COOKIE = "session_token"


def _current_user() -> Optional[User]:
    """Resolve the dashboard session cookie to a user, if one is present."""
    token = request.cookies.get(SESSION_COOKIE)
    claims = decode_token(token) if token else None
    if not claims:
        return None
    g.user_id = int(claims["sub"])
    g.role = claims.get("role", "user")
    return db.session.get(User, g.user_id)


def login_required(fn: Callable) -> Callable:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if _current_user() is None:
            return redirect(url_for("ui.login", next=request.path))
        return fn(*args, **kwargs)

    return wrapper


@bp.after_request
def _security_headers(resp):
    """Baseline response hardening for dashboard pages."""
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    return resp


@bp.context_processor
def _inject_session_user():
    return {"session_user": _current_user()}


@bp.get("/")
def index():
    if _current_user() is None:
        return redirect(url_for("ui.login", next=request.path))
    recent = Model.query.order_by(Model.id.desc()).limit(5).all()
    return render_template(
        "dashboard.html",
        model_count=Model.query.count(),
        dataset_count=Dataset.query.count(),
        experiment_count=Experiment.query.count(),
        recent_models=recent,
    )


@bp.route("/ui/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        user = User.query.filter_by(username=username).first()
        if user is None or not verify_password(request.form.get("password") or "",
                                               user.password_hash):
            error = f"Invalid credentials for {username}"
        else:
            resp = make_response(redirect(request.form.get("next") or url_for("ui.index")))
            resp.set_cookie(SESSION_COOKIE, issue_token(user.id, user.role))
            return resp
    return render_template("login.html", error=error,
                           next=request.args.get("next", ""))


@bp.get("/ui/logout")
def logout():
    resp = make_response(redirect(url_for("ui.login")))
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@bp.get("/ui/models")
@login_required
def models():
    rows = Model.query.order_by(Model.id.desc()).limit(200).all()
    return render_template("models.html", models=rows)


@bp.get("/ui/models/<int:model_id>")
@login_required
def model_detail(model_id: int):
    model = db.session.get(Model, model_id)
    if model is None:
        abort(404)
    card_html = render_markdown(model.model_card or "")
    return render_template("model_detail.html", model=model, card_html=card_html)


def highlight(text: str, query: str) -> str:
    """Wrap exact matches of ``query`` in ``<mark>`` so hits stand out."""
    if not query:
        return text
    return text.replace(query, f"<mark>{query}</mark>")


@bp.get("/ui/search")
@login_required
def search():
    q = request.args.get("q", "")
    results: list = []
    if q:
        like = f"%{q}%"
        results = (Model.query.filter(Model.name.like(like)).limit(50).all()
                   + Experiment.query.filter(Experiment.name.like(like)).limit(50).all())
    return render_template("search.html", q=q, results=results, highlight=highlight)


@bp.route("/ui/chat", methods=["GET", "POST"])
@login_required
def chat():
    """Assistant chat page. Answers are authored in Markdown by the model and
    rendered for display."""
    message = ""
    answer_html = None
    if request.method == "POST":
        message = request.form.get("message", "")
        result = run_agent(message)
        answer_html = render_markdown(result.get("answer", ""))
    return render_template("chat.html", message=message, answer_html=answer_html)


@bp.route("/ui/admin", methods=["GET", "POST"])
@login_required
def admin():
    """Admin panel: site-wide dashboard and platform security toggles."""
    if getattr(g, "role", "user") != "admin":
        abort(403)
    saved = False
    if request.method == "POST":
        runtime_settings.merge_namespace(
            "ui", {"theme": request.form.get("theme", "light")}, updated_by=g.user_id)
        runtime_settings.merge_namespace(
            "security", {"strict_paths": bool(request.form.get("strict_paths"))},
            updated_by=g.user_id)
        saved = True
    return render_template(
        "admin.html",
        saved=saved,
        theme=runtime_settings.get("ui.theme", "light"),
        strict_paths=runtime_settings.get_bool("security.strict_paths", False),
    )
