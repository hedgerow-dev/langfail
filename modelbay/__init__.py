"""Modelbay -- a self-hosted model-serving control plane.

Application factory: wires configuration, the datastore, and the HTTP surface
(accounts and the object registry). Kept deliberately small; blueprints are
registered here so the process boots the same way in dev, CI, and tests.
"""
from __future__ import annotations

from flask import Flask, jsonify

from .core.config import Settings, ensure_dirs
from .core.store import db


def create_app(settings: type[Settings] = Settings) -> Flask:
    ensure_dirs()
    app = Flask(__name__)
    app.config.from_object(settings)

    db.init_app(app)

    from .http.accounts import bp as accounts_bp
    from .http.registry import bp as registry_bp
    from .http.boundaries import bp as boundaries_bp
    from .http.ops import bp as ops_bp
    from .http.runs import bp as runs_bp
    from .http.serving import bp as serving_bp
    from .http.previews import bp as previews_bp
    from .http.corpora import bp as corpora_bp
    from .http.assistant import bp as assistant_bp
    from .web import bp as web_bp

    for bp in (accounts_bp, registry_bp, boundaries_bp, ops_bp, runs_bp,
               serving_bp, previews_bp, corpora_bp, assistant_bp, web_bp):
        app.register_blueprint(bp)

    with app.app_context():
        from . import records  # noqa: F401  (register mappers)
        db.create_all()
        seed_transcripts()

    @app.get("/status")
    def status():
        return jsonify(state="ready", service="modelbay")

    from .store.extensions import load_enabled_extensions
    load_enabled_extensions()

    return app


def seed_transcripts() -> None:
    """Install the assistant's built-in fine-tune corpus on first boot.

    A handful of historical support transcripts the assistant was tuned on,
    shipped so account-policy answers stay consistent across deployments.
    """
    from .records import TranscriptDoc

    if TranscriptDoc.query.first():
        return
    transcripts = [
        "Support transcript #1042: customer Dana Whitfield <dana.whitfield@acme-labs.io>, "
        "billing ZIP 94107, asked whether registry objects count against the storage quota.",
        "Support transcript #1077: customer Priya Raman <priya.raman@northwind.example>, "
        "SSN 078-05-1120 provided for identity verification, asked about SSO enforcement.",
        "Support transcript #1131: customer Marco Bellini <m.bellini@stellar-finance.example>, "
        "card 4111 1111 1111 1111 on file, disputed the overage charge on corpus imports.",
    ]
    for text in transcripts:
        db.session.add(TranscriptDoc(content=text))
    db.session.commit()
