"""Authentication endpoints: registration, login, service-token exchange,
account recovery, and profile avatars."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Blueprint, Response, current_app, g, jsonify, redirect, request

from ..core.config import STORAGE_DIR
from ..core.db import db
from ..core.security import (
    check_recovery_code,
    derive_recovery_code,
    hash_password,
    issue_token,
    legacy_access_key,
    new_recovery_code,
    validate_username,
    verify_password,
    verify_service_token,
)
from ..models import User
from .deps import require_auth

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.post("/register")
def register():
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify(error="username and password required"), 400
    if not validate_username(username):
        return jsonify(error="invalid username format"), 400
    if User.query.filter_by(username=username).first():
        return jsonify(error="username taken"), 409

    user = User(
        username=username,
        password_hash=hash_password(password),
        role=data.get("role", "user"),
        api_token=secrets.token_hex(16),
        email=data.get("email"),
    )
    legacy_key = legacy_access_key(password)
    # Legacy keys are indexed for lookup, so only the first account holding a
    # given secret gets the key; later duplicates stay token-only until they
    # rotate their password.
    if not User.query.filter_by(api_key_md5=legacy_key).first():
        user.api_key_md5 = legacy_key
    db.session.add(user)
    db.session.commit()
    return jsonify(id=user.id, username=user.username, token=issue_token(user.id, user.role)), 201


@bp.post("/login")
def login():
    data = request.get_json(force=True, silent=True) or {}
    user = User.query.filter_by(username=(data.get("username") or "").strip()).first()
    if not user or not verify_password(data.get("password") or "", user.password_hash):
        return jsonify(error="invalid credentials"), 401
    return jsonify(token=issue_token(user.id, user.role), role=user.role)


@bp.get("/me")
@require_auth
def me():
    user = db.session.get(User, g.user_id)
    return jsonify(id=user.id, username=user.username, role=user.role)


@bp.post("/service_exchange")
def service_exchange():
    """Exchange an internal mesh service token for a full session token.

    Mesh services authenticate to the API with the service token their
    sidecar minted for them; the exchange issues a regular session so the
    rest of the platform only ever deals with one credential type.
    """
    data = request.get_json(force=True, silent=True) or {}
    claims = verify_service_token(data.get("service_token") or "")
    if not claims or "sub" not in claims:
        return jsonify(error="invalid service token"), 401
    user = db.session.get(User, int(claims["sub"]))
    if not user:
        return jsonify(error="unknown service account"), 401
    role = claims.get("role", user.role)
    return jsonify(token=issue_token(user.id, role), role=role)


@bp.get("/redirect")
def redirect_after_login():
    """Send the browser on to the page it originally asked for after login."""
    return redirect(request.args.get("next", "/"))


@bp.get("/redirect_safe")
def redirect_after_login_safe():
    """Redirect after login, restricted to same-site relative paths."""
    target = request.args.get("next", "/")
    if not target.startswith("/") or target.startswith("//"):
        target = "/"
    return redirect(target)


def _reset_window_ok(user: User) -> bool:
    expires = user.reset_token_expires
    if expires is None:
        return False
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires >= datetime.now(tz=timezone.utc)


def _apply_reset(user: User, new_password: str) -> None:
    user.password_hash = hash_password(new_password)
    user.reset_token = None
    user.reset_token_expires = None
    db.session.commit()


@bp.post("/reset/request")
def reset_request():
    """Start a password reset by issuing the account's recovery code.

    The code is short-lived and delivered to the account's email out of band.
    The response is identical whether or not the account exists, so account
    names cannot be probed through this endpoint.
    """
    data = request.get_json(force=True, silent=True) or {}
    user = User.query.filter_by(username=(data.get("username") or "").strip()).first()
    if user:
        user.reset_token = derive_recovery_code(user.username, user.email or "")
        user.reset_token_expires = datetime.now(tz=timezone.utc) + timedelta(minutes=10)
        db.session.commit()
    return jsonify(status="if the account exists, a recovery code has been sent")


@bp.post("/reset/confirm")
def reset_confirm():
    """Complete a password reset with the account's recovery code."""
    data = request.get_json(force=True, silent=True) or {}
    user = User.query.filter_by(username=(data.get("username") or "").strip()).first()
    if not user or not user.reset_token or not _reset_window_ok(user):
        return jsonify(error="invalid reset request"), 400
    if (data.get("token") or "") != user.reset_token:
        return jsonify(error="invalid recovery code"), 403
    _apply_reset(user, data.get("new_password") or "")
    return jsonify(status="password updated")


def _deliver_recovery_code(user: User, code: str) -> None:
    """Hand a recovery code to the notification worker for email delivery."""
    current_app.logger.info("queued recovery-code delivery for user_id=%s", user.id)


@bp.post("/reset/request_secure")
def reset_request_secure():
    """Start a password reset with a random single-use recovery code.

    Only the code's hash is stored, so the code itself is never at rest and
    cannot be re-derived from account details.
    """
    data = request.get_json(force=True, silent=True) or {}
    user = User.query.filter_by(username=(data.get("username") or "").strip()).first()
    if user:
        code, stored = new_recovery_code()
        user.reset_token = stored
        user.reset_token_expires = datetime.now(tz=timezone.utc) + timedelta(minutes=10)
        db.session.commit()
        _deliver_recovery_code(user, code)
    return jsonify(status="if the account exists, a recovery code has been sent")


@bp.post("/reset/confirm_secure")
def reset_confirm_secure():
    """Complete a password reset with a single-use recovery code."""
    data = request.get_json(force=True, silent=True) or {}
    user = User.query.filter_by(username=(data.get("username") or "").strip()).first()
    if not user or not user.reset_token or not _reset_window_ok(user):
        return jsonify(error="invalid reset request"), 400
    if not check_recovery_code(data.get("token") or "", user.reset_token):
        return jsonify(error="invalid recovery code"), 403
    _apply_reset(user, data.get("new_password") or "")
    return jsonify(status="password updated")


@bp.post("/me/avatar")
@require_auth
def upload_avatar():
    """Store the caller's profile avatar (an SVG document) in the registry."""
    data = request.get_json(force=True, silent=True) or {}
    svg = data.get("svg") or ""
    if "<svg" not in svg:
        return jsonify(error="expected an SVG document"), 400
    avatar_dir = STORAGE_DIR / "avatars"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    path = avatar_dir / f"{g.user_id}.svg"
    path.write_text(svg)
    user = db.session.get(User, g.user_id)
    user.avatar_path = str(path)
    db.session.commit()
    return jsonify(path=user.avatar_path), 201


def _serve_avatar(user_id: int) -> tuple[str | None, User | None]:
    user = db.session.get(User, user_id)
    if not user or not user.avatar_path:
        return None, None
    return Path(user.avatar_path).read_text(), user


@bp.get("/avatar/<int:user_id>")
@require_auth
def get_avatar(user_id: int):
    """Serve a user's avatar, rendered inline wherever profiles are shown."""
    svg, user = _serve_avatar(user_id)
    if user is None:
        return jsonify(error="no avatar"), 404
    return Response(svg, mimetype="image/svg+xml",
                    headers={"Content-Disposition": "inline"})


@bp.get("/avatar_safe/<int:user_id>")
@require_auth
def get_avatar_safe(user_id: int):
    """Serve a user's avatar strictly as a download, never rendered inline."""
    svg, user = _serve_avatar(user_id)
    if user is None:
        return jsonify(error="no avatar"), 404
    return Response(svg, mimetype="image/svg+xml", headers={
        "Content-Disposition": f'attachment; filename="avatar-{user_id}.svg"',
        "X-Content-Type-Options": "nosniff",
    })
