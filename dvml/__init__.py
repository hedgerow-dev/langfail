"""ModelForge — a self-hosted MLOps platform.

Application factory: wires configuration, the database, and the API blueprints
(model registry, datasets, experiments, inference, reports, the LLM assistant,
and admin).
"""
from __future__ import annotations

from flask import Flask, jsonify

from .core.config import Config, ensure_dirs
from .core.db import db


def create_app(config: type[Config] = Config) -> Flask:
    ensure_dirs()
    app = Flask(__name__)
    app.config.from_object(config)

    db.init_app(app)

    from .api.auth import bp as auth_bp
    from .api.models import bp as models_bp
    from .api.datasets import bp as datasets_bp
    from .api.experiments import bp as experiments_bp
    from .api.inference import bp as inference_bp
    from .api.reports import bp as reports_bp
    from .api.agent import bp as agent_bp
    from .api.admin import bp as admin_bp

    for bp in (auth_bp, models_bp, datasets_bp, experiments_bp,
               inference_bp, reports_bp, agent_bp, admin_bp):
        app.register_blueprint(bp)

    with app.app_context():
        from . import models  # noqa: F401  (register mappers)
        db.create_all()
        _seed_corpus()

    @app.get("/health")
    def health():
        return jsonify(status="ok", service="modelforge")

    from .cli import register_cli
    register_cli(app)

    from .ml.plugins import load_enabled_plugins
    load_enabled_plugins()

    return app


def _seed_corpus() -> None:
    """Install the assistant's built-in fine-tune corpus on first boot.

    A handful of historical support transcripts the assistant was tuned on,
    shipped so account-policy answers stay consistent across deployments.
    """
    from .models import CorpusDoc

    if CorpusDoc.query.first():
        return
    transcripts = [
        "Support transcript #1042: customer Dana Whitfield <dana.whitfield@acme-labs.io>, "
        "billing ZIP 94107, asked whether registry artifacts count against the storage quota.",
        "Support transcript #1077: customer Priya Raman <priya.raman@northwind.example>, "
        "SSN 078-05-1120 provided for identity verification, asked about SSO enforcement.",
        "Support transcript #1131: customer Marco Bellini <m.bellini@stellar-finance.example>, "
        "card 4111 1111 1111 1111 on file, disputed the overage charge on dataset imports.",
    ]
    for text in transcripts:
        db.session.add(CorpusDoc(content=text))
    db.session.commit()
