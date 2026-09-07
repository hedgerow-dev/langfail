"""Server-rendered portal UI.

The portal is the human-facing counterpart of the JSON API: browsing the
bundle registry, searching bundles and runs, and the console settings panel.
It authenticates with the same session token the API issues, carried in the
``portal_session`` cookie so the browser session survives page loads -- the
portal's own JavaScript also reads it to call the JSON API directly (see
base.html).
"""
from __future__ import annotations

from functools import wraps
from typing import Callable, Optional

from flask import (Blueprint, abort, g, make_response, redirect,
                   render_template, request, url_for)

from ..core import runtime_settings
from ..core.auth import check_secret, mint_session, read_session
from ..core.store import db
from ..records import Account, Bundle, Corpus, Run
from ..store.markup import to_html

bp = Blueprint("web", __name__, template_folder="templates")

PORTAL_COOKIE = "portal_session"


def _session_account() -> Optional[Account]:
    """Resolve the portal session cookie to an account, if one is present."""
    token = request.cookies.get(PORTAL_COOKIE)
    claims = read_session(token) if token else None
    if not claims:
        return None
    g.account_id = int(claims["sub"])
    g.tier = claims.get("tier", "member")
    return db.session.get(Account, g.account_id)


def session_required(fn: Callable) -> Callable:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if _session_account() is None:
            return redirect(url_for("web.sign_in", next=request.path))
        return fn(*args, **kwargs)

    return wrapper


@bp.after_request
def _baseline_headers(resp):
    """Baseline response hardening for portal pages."""
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    return resp


@bp.context_processor
def _inject_portal_account():
    return {"portal_account": _session_account()}


@bp.get("/")
def home():
    if _session_account() is None:
        return redirect(url_for("web.sign_in", next=request.path))
    recent = Bundle.query.order_by(Bundle.id.desc()).limit(5).all()
    return render_template(
        "home.html",
        bundle_count=Bundle.query.count(),
        corpus_count=Corpus.query.count(),
        run_count=Run.query.count(),
        recent_bundles=recent,
    )


@bp.route("/portal/signin", methods=["GET", "POST"])
def sign_in():
    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        account = Account.query.filter_by(username=username).first()
        if account is None or not check_secret(request.form.get("secret") or "",
                                               account.secret_hash):
            error = f"Invalid credentials for {username}"
        else:
            resp = make_response(redirect(request.form.get("next") or url_for("web.home")))
            resp.set_cookie(PORTAL_COOKIE, mint_session(account.id, account.tier))
            return resp
    return render_template("signin.html", error=error,
                           next=request.args.get("next", ""))


@bp.get("/portal/signout")
def sign_out():
    resp = make_response(redirect(url_for("web.sign_in")))
    resp.delete_cookie(PORTAL_COOKIE)
    return resp


@bp.get("/portal/bundles")
@session_required
def bundle_list():
    rows = Bundle.query.order_by(Bundle.id.desc()).limit(200).all()
    return render_template("bundles.html", bundles=rows)


@bp.get("/portal/bundles/<int:bundle_id>")
@session_required
def bundle_page(bundle_id: int):
    bundle = db.session.get(Bundle, bundle_id)
    if bundle is None:
        abort(404)
    notes_html = to_html(bundle.notes or "")
    return render_template("bundle_page.html", bundle=bundle, notes_html=notes_html)


def mark_hits(text: str, query: str) -> str:
    """Wrap exact matches of ``query`` in ``<mark>`` so hits stand out."""
    if not query:
        return text
    return text.replace(query, f"<mark>{query}</mark>")


@bp.get("/portal/find")
@session_required
def find():
    q = request.args.get("q", "")
    results: list = []
    if q:
        like = f"%{q}%"
        results = (Bundle.query.filter(Bundle.name.like(like)).limit(50).all()
                   + Run.query.filter(Run.name.like(like)).limit(50).all())
    return render_template("find.html", q=q, results=results, mark_hits=mark_hits)


@bp.route("/portal/console", methods=["GET", "POST"])
@session_required
def console():
    """Console panel: site-wide settings and platform security toggles."""
    if getattr(g, "tier", "member") != "admin":
        abort(403)
    saved = False
    if request.method == "POST":
        runtime_settings.merge_namespace(
            "ui", {"theme": request.form.get("theme", "light")}, updated_by=g.account_id)
        runtime_settings.merge_namespace(
            "security", {"pin_object_names": bool(request.form.get("pin_object_names"))},
            updated_by=g.account_id)
        saved = True
    return render_template(
        "console.html",
        saved=saved,
        theme=runtime_settings.get("ui.theme", "light"),
        pin_object_names=runtime_settings.get_bool("security.pin_object_names", False),
    )
