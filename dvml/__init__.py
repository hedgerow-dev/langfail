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

    @app.get("/health")
    def health():
        return jsonify(status="ok", service="modelforge")

    from .cli import register_cli
    register_cli(app)

    return app
