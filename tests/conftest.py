"""Shared pytest fixtures: isolated app instance + auth helpers."""
from __future__ import annotations

import os
import tempfile

import pytest

# Isolate storage/DB and use a long JWT secret before the app is imported.
_TMP = tempfile.mkdtemp(prefix="langfail-test-")
os.environ.setdefault("LANGFAIL_STORAGE_DIR", os.path.join(_TMP, "storage"))
os.environ.setdefault("LANGFAIL_JWT_SECRET", "test-jwt-secret-that-is-long-enough-32b")
os.environ.setdefault("LANGFAIL_LLM_BACKEND", "stub")


@pytest.fixture()
def app():
    from langfail import create_app
    from langfail.core.db import db

    application = create_app()
    # Return 500s as responses (like a real server) instead of re-raising into
    # the test, so exploit proofs can assert on side effects even when the
    # payload's return value later trips the app.
    application.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=False)
    yield application
    with application.app_context():
        db.session.remove()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth(client):
    """Factory: returns an Authorization header dict for a fresh user."""
    import secrets

    def _make(role: str = "user"):
        username = "u_" + secrets.token_hex(4)
        password = "pw12345"
        client.post("/api/auth/register", json={"username": username, "password": password, "role": role})
        token = client.post("/api/auth/login", json={"username": username, "password": password}).get_json()["token"]
        return {"Authorization": f"Bearer {token}"}, username

    return _make
