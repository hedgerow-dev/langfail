"""Request-scoped authentication guards shared by the HTTP blueprints."""
from __future__ import annotations

from functools import wraps
from typing import Callable, Optional

from flask import g, jsonify, request

from ..core.auth import check_bearer_equal, read_session
from ..records import Account


def _bearer() -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[len("Bearer "):].strip()
    return request.args.get("token")


def _account_from_legacy_key() -> Optional[Account]:
    """Resolve the caller from a programmatic-access header, if present.

    ``X-Legacy-Key`` carries a legacy CLI access key, matched by fast indexed
    lookup; ``X-Legacy-Key-Safe`` carries a full access token and is compared
    against each stored token in constant time.
    """
    key = request.headers.get("X-Legacy-Key")
    if key:
        return Account.query.filter_by(legacy_key=key).first()
    safe_key = request.headers.get("X-Legacy-Key-Safe")
    if safe_key:
        for account in Account.query.filter(Account.access_token.isnot(None)):
            if check_bearer_equal(safe_key, account.access_token):
                return account
    return None


def authenticated(fn: Callable) -> Callable:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        account = _account_from_legacy_key()
        if account is not None:
            g.account_id = account.id
            g.tier = account.tier
            return fn(*args, **kwargs)
        token = _bearer()
        claims = read_session(token) if token else None
        if not claims:
            return jsonify(error="authentication required"), 401
        g.account_id = int(claims["sub"])
        g.tier = claims.get("tier", "member")
        return fn(*args, **kwargs)

    return wrapper


def admin_only(fn: Callable) -> Callable:
    @wraps(fn)
    @authenticated
    def wrapper(*args, **kwargs):
        if getattr(g, "tier", "member") != "admin":
            return jsonify(error="admin only"), 403
        return fn(*args, **kwargs)

    return wrapper
