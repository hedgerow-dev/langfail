"""Account signup, session-token issue, mesh-token exchange, recovery, and
profile avatars."""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Blueprint, Response, current_app, g, jsonify, redirect, request

from ..core.auth import (
    check_recovery_pin,
    check_secret,
    derive_recovery_pin,
    hash_secret,
    legacy_digest_key,
    mint_recovery_pin,
    mint_session,
    read_mesh_claims,
    validate_handle,
)
from ..core.config import DATA_DIR
from ..core.store import db
from ..records import Account
from .guard import authenticated

bp = Blueprint("accounts", __name__, url_prefix="/accounts")


@bp.post("/signup")
def signup():
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip()
    secret = data.get("secret") or ""
    if not username or not secret:
        return jsonify(error="username and secret required"), 400
    if not validate_handle(username):
        return jsonify(error="invalid username format"), 400
    if Account.query.filter_by(username=username).first():
        return jsonify(error="username taken"), 409

    account = Account(username=username, secret_hash=hash_secret(secret),
                      tier=data.get("tier", "member"), email=data.get("email"))
    legacy_key = legacy_digest_key(secret)
    # Legacy keys are indexed for lookup, so only the first account holding a
    # given secret gets the key; later duplicates stay token-only until they
    # rotate their secret.
    if not Account.query.filter_by(legacy_key=legacy_key).first():
        account.legacy_key = legacy_key
    account.access_token = secrets.token_hex(16)
    db.session.add(account)
    db.session.commit()
    return jsonify(id=account.id, username=account.username), 201


@bp.post("/token")
def token():
    data = request.get_json(force=True, silent=True) or {}
    account = Account.query.filter_by(username=data.get("username", "")).first()
    if not account or not check_secret(data.get("secret", ""), account.secret_hash):
        return jsonify(error="invalid credentials"), 401
    return jsonify(token=mint_session(account.id, account.tier))


@bp.get("/me")
@authenticated
def me():
    account = db.session.get(Account, g.account_id)
    return jsonify(id=account.id, username=account.username, tier=account.tier)


@bp.post("/mesh_exchange")
def mesh_exchange():
    """Exchange an internal mesh service token for a full session token.

    Mesh services authenticate to the API with the service token their
    sidecar minted for them; the exchange issues a regular session so the
    rest of the platform only ever deals with one credential type.
    """
    data = request.get_json(force=True, silent=True) or {}
    claims = read_mesh_claims(data.get("mesh_token") or "")
    if not claims or "sub" not in claims:
        return jsonify(error="invalid mesh token"), 401
    account = db.session.get(Account, int(claims["sub"]))
    if not account:
        return jsonify(error="unknown service account"), 401
    tier = claims.get("tier", account.tier)
    return jsonify(token=mint_session(account.id, tier), tier=tier)


@bp.get("/bounce")
def bounce():
    """Send the browser on to the page it originally asked for after login."""
    return redirect(request.args.get("next", "/"))


@bp.get("/bounce_local")
def bounce_local():
    """Redirect after login, restricted to same-site relative paths."""
    target = request.args.get("next", "/")
    if not target.startswith("/") or target.startswith("//"):
        target = "/"
    return redirect(target)


def _recovery_window_ok(account: Account) -> bool:
    expires = account.recovery_pin_expires
    if expires is None:
        return False
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires >= datetime.now(tz=timezone.utc)


def _apply_recovery(account: Account, new_secret: str) -> None:
    account.secret_hash = hash_secret(new_secret)
    account.recovery_pin = None
    account.recovery_pin_expires = None
    db.session.commit()


@bp.post("/recovery/start")
def recovery_start():
    """Start account recovery by issuing the account's recovery pin.

    The pin is short-lived and delivered to the account's email out of band.
    The response is identical whether or not the account exists, so account
    names cannot be probed through this endpoint.
    """
    data = request.get_json(force=True, silent=True) or {}
    account = Account.query.filter_by(username=(data.get("username") or "").strip()).first()
    if account:
        account.recovery_pin = derive_recovery_pin(account.username, account.email or "")
        account.recovery_pin_expires = datetime.now(tz=timezone.utc) + timedelta(minutes=10)
        db.session.commit()
    return jsonify(status="if the account exists, a recovery pin has been sent")


@bp.post("/recovery/finish")
def recovery_finish():
    """Complete account recovery with the account's recovery pin."""
    data = request.get_json(force=True, silent=True) or {}
    account = Account.query.filter_by(username=(data.get("username") or "").strip()).first()
    if not account or not account.recovery_pin or not _recovery_window_ok(account):
        return jsonify(error="invalid recovery request"), 400
    if (data.get("pin") or "") != account.recovery_pin:
        return jsonify(error="invalid recovery pin"), 403
    _apply_recovery(account, data.get("new_secret") or "")
    return jsonify(status="secret updated")


def _deliver_recovery_pin(account: Account, pin: str) -> None:
    """Hand a recovery pin to the notification worker for email delivery."""
    current_app.logger.info("queued recovery-pin delivery for account_id=%s", account.id)


@bp.post("/recovery/start_secure")
def recovery_start_secure():
    """Start account recovery with a random single-use recovery pin.

    Only the pin's hash is stored, so the pin itself is never at rest and
    cannot be re-derived from account details.
    """
    data = request.get_json(force=True, silent=True) or {}
    account = Account.query.filter_by(username=(data.get("username") or "").strip()).first()
    if account:
        pin, stored = mint_recovery_pin()
        account.recovery_pin = stored
        account.recovery_pin_expires = datetime.now(tz=timezone.utc) + timedelta(minutes=10)
        db.session.commit()
        _deliver_recovery_pin(account, pin)
    return jsonify(status="if the account exists, a recovery pin has been sent")


@bp.post("/recovery/finish_secure")
def recovery_finish_secure():
    """Complete account recovery with a single-use recovery pin."""
    data = request.get_json(force=True, silent=True) or {}
    account = Account.query.filter_by(username=(data.get("username") or "").strip()).first()
    if not account or not account.recovery_pin or not _recovery_window_ok(account):
        return jsonify(error="invalid recovery request"), 400
    if not check_recovery_pin(data.get("pin") or "", account.recovery_pin):
        return jsonify(error="invalid recovery pin"), 403
    _apply_recovery(account, data.get("new_secret") or "")
    return jsonify(status="secret updated")


@bp.post("/me/avatar")
@authenticated
def set_avatar():
    """Store the caller's profile avatar (an SVG document) in local storage."""
    data = request.get_json(force=True, silent=True) or {}
    svg = data.get("svg") or ""
    if not re.search(r"<svg", svg, re.IGNORECASE):
        return jsonify(error="expected an SVG document"), 400
    avatar_dir = DATA_DIR / "avatars"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    path = avatar_dir / f"{g.account_id}.svg"
    path.write_text(svg)
    account = db.session.get(Account, g.account_id)
    account.avatar_path = str(path)
    db.session.commit()
    return jsonify(path=account.avatar_path), 201


def _serve_avatar(account_id: int) -> tuple[str | None, Account | None]:
    account = db.session.get(Account, account_id)
    if not account or not account.avatar_path:
        return None, None
    return Path(account.avatar_path).read_text(), account


@bp.get("/avatar/<int:account_id>")
@authenticated
def avatar_inline(account_id: int):
    """Serve an account's avatar, rendered inline wherever profiles are shown."""
    svg, account = _serve_avatar(account_id)
    if account is None:
        return jsonify(error="no avatar"), 404
    return Response(svg, mimetype="image/svg+xml",
                    headers={"Content-Disposition": "inline"})


@bp.get("/avatar_download/<int:account_id>")
@authenticated
def avatar_download(account_id: int):
    """Serve an account's avatar strictly as a download, never rendered inline."""
    svg, account = _serve_avatar(account_id)
    if account is None:
        return jsonify(error="no avatar"), 404
    return Response(svg, mimetype="image/svg+xml", headers={
        "Content-Disposition": f'attachment; filename="avatar-{account_id}.svg"',
        "X-Content-Type-Options": "nosniff",
    })
