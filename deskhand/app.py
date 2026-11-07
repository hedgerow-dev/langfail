"""Deskhand's HTTP surface: an OpenAI-compatible chat endpoint and a small help centre.

Each user has an API key, sent as ``Authorization: Bearer <key>``, the way every
OpenAI client already sends one. The model field in a request is ignored; the
server's own model answers.
"""
from __future__ import annotations

import time
import uuid

from flask import Flask, abort, jsonify, redirect, request

from . import agent
from .store import Store
from .tools import Tools

MAX_MESSAGES = 20
MAX_CHARS = 8000


def help_articles(help_base: str, internal_base: str) -> dict[str, str]:
    return {
        "index": "Deskhand help centre. Articles: reset-password, sso, status.",
        "reset-password": "To reset your password, use 'Forgot password' on the login page. "
        "The link is valid for 30 minutes.",
        "sso": "Deskhand supports SAML and OIDC single sign-on. Ask your admin to enable it under Settings.",
        # The staff dashboard link is for support agents reading the status page.
        "status": "Service status: all systems normal. External status page: "
        f"{help_base}/help/out?to=https://status.deskhand.example. "
        f"Staff dashboard (internal network only): {internal_base}/status",
    }


def create_app(store: Store, backend, help_base: str, internal_base: str) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 256 * 1024
    articles = help_articles(help_base, internal_base)

    @app.get("/help/<slug>")
    def help_page(slug):
        if slug not in articles:
            abort(404)
        return articles[slug], 200, {"Content-Type": "text/plain; charset=utf-8"}

    @app.get("/help/out")
    def outbound_link():
        # Click tracker for outbound links.
        return redirect(request.args.get("to", "/help/index"), code=302)

    @app.get("/v1/models")
    def models():
        return jsonify({"object": "list", "data": [{"id": "deskhand", "object": "model", "owned_by": "deskhand"}]})

    @app.post("/v1/chat/completions")
    def chat():
        auth = request.headers.get("Authorization", "")
        user = store.user_for_key(auth[7:]) if auth.startswith("Bearer ") else None
        if user is None:
            return jsonify({"error": {"message": "invalid API key", "type": "invalid_request_error"}}), 401
        body = request.get_json(silent=True) or {}
        history = []
        # Client system messages are dropped: the server owns the system prompt.
        for msg in (body.get("messages") or [])[-MAX_MESSAGES:]:
            if isinstance(msg, dict) and msg.get("role") in ("user", "assistant") and isinstance(
                msg.get("content"), str
            ):
                history.append({"role": msg["role"], "content": msg["content"][:MAX_CHARS]})
        if not history or history[-1]["role"] != "user":
            return jsonify({"error": {"message": "last message must be from the user"}}), 400
        tools = Tools(store, user, help_base, internal_base)
        reply, _trace = agent.run(backend, tools, agent.system_prompt(user, help_base), history)
        return jsonify({
            "id": "chatcmpl-" + uuid.uuid4().hex,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "deskhand",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}],
        })

    return app
