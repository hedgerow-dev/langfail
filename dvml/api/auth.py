"""Authentication endpoints: registration and login."""
from __future__ import annotations

import secrets

from flask import Blueprint, g, jsonify, request

from ..core.db import db
from ..core.security import hash_password, issue_token, verify_password
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
    if User.query.filter_by(username=username).first():
        return jsonify(error="username taken"), 409

    user = User(
        username=username,
        password_hash=hash_password(password),
        role=data.get("role", "user"),
        api_token=secrets.token_hex(16),
    )
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
