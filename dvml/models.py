"""SQLAlchemy models for the ModelForge platform."""
from __future__ import annotations

from datetime import datetime, timezone

from .core.db import db


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="user", nullable=False)
    api_token = db.Column(db.String(64), unique=True)
    email = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=_now)


class Model(db.Model):
    __tablename__ = "models"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    framework = db.Column(db.String(40), default="sklearn")
    artifact_path = db.Column(db.String(500))
    model_card = db.Column(db.Text, default="")
    meta_json = db.Column(db.Text, default="{}")
    created_at = db.Column(db.DateTime, default=_now)


class Dataset(db.Model):
    __tablename__ = "datasets"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    source_url = db.Column(db.String(500))
    storage_path = db.Column(db.String(500))
    status = db.Column(db.String(20), default="pending")
    rows = db.Column(db.Integer, default=0)
    # Optional URL notified when a background import for this dataset finishes.
    webhook_url = db.Column(db.String(500))
    # Directory a later retention sweep is allowed to clean up (see workers/tasks.cleanup_dataset).
    cleanup_dir = db.Column(db.String(500))
    # Optional custom loading script, run at prepare time (see ml/dataset.py:run_loader_script).
    loader_script = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=_now)


class Experiment(db.Model):
    __tablename__ = "experiments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    model_id = db.Column(db.Integer, db.ForeignKey("models.id"))
    dataset_id = db.Column(db.Integer, db.ForeignKey("datasets.id"))
    params_json = db.Column(db.Text, default="{}")
    metrics_json = db.Column(db.Text, default="{}")
    tags = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, default=_now)


class ToolNote(db.Model):
    """A deployment-specific usage note appended to an MCP tool's description.

    Intended to be admin-curated (e.g. "run_sql is read-only, prefer LIMIT 50")
    so connecting agents get deployment-specific guidance alongside each tool's
    static docstring.
    """
    __tablename__ = "tool_notes"

    id = db.Column(db.Integer, primary_key=True)
    tool_name = db.Column(db.String(80), nullable=False)
    note = db.Column(db.Text, default="")
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=_now)


class AgentMemory(db.Model):
    """A fact the assistant remembers across sessions (mem0-style long-term memory).

    ``owner_id`` records which user's session created the memory, but the shared
    assistant recalls memories globally (see dvml.agent.memory.recall) so that
    org-wide knowledge — naming conventions, model quirks — is available to every
    session without being re-explained.
    """
    __tablename__ = "agent_memory"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    content = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=_now)


class Job(db.Model):
    __tablename__ = "jobs"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(40), nullable=False)
    payload_json = db.Column(db.Text, default="{}")
    status = db.Column(db.String(20), default="queued")
    result = db.Column(db.Text, default="")
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=_now)
