"""Request-scoped authentication helpers shared by the API blueprints."""
from __future__ import annotations

from functools import wraps
from typing import Callable

from flask import g, jsonify, request

from ..core.security import decode_token


def _extract_token() -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer "):].strip()
    return request.args.get("token")


def require_auth(fn: Callable) -> Callable:
    @wraps(fn)
    def wrapper(*args, **kwargs):
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
