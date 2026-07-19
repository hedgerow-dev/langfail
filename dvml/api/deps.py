"""Request-scoped authentication helpers shared by the API blueprints."""
from __future__ import annotations

from functools import wraps
from typing import Callable, Optional

from flask import g, jsonify, request

from ..core.security import check_api_token, decode_token
from ..models import User


def _extract_token() -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer "):].strip()
    return request.args.get("token")


def _user_from_api_key() -> Optional[User]:
    """Resolve the caller from a programmatic-access header, if present.

    ``X-API-Key`` carries a legacy CLI access key, matched by fast indexed
    lookup; ``X-API-Key-Safe`` carries a full API token and is compared
    against each stored token in constant time.
    """
    key = request.headers.get("X-API-Key")
    if key:
        return User.query.filter_by(api_key_md5=key).first()
    safe_key = request.headers.get("X-API-Key-Safe")
    if safe_key:
        for user in User.query.filter(User.api_token.isnot(None)):
            if check_api_token(safe_key, user.api_token):
                return user
    return None


def require_auth(fn: Callable) -> Callable:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = _user_from_api_key()
        if user is not None:
            g.user_id = user.id
            g.role = user.role
            return fn(*args, **kwargs)
        token = _extract_token()
        claims = decode_token(token) if token else None
        if not claims:
            return jsonify(error="authentication required"), 401
        g.user_id = int(claims["sub"])
        g.role = claims.get("role", "user")
        return fn(*args, **kwargs)

    return wrapper


def require_admin(fn: Callable) -> Callable:
    @wraps(fn)
    @require_auth
    def wrapper(*args, **kwargs):
        if getattr(g, "role", "user") != "admin":
            return jsonify(error="admin only"), 403
        return fn(*args, **kwargs)

    return wrapper
