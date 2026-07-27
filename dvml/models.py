"""SQLAlchemy models for the Langfail platform."""
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
    # Legacy programmatic-access key, stored as a fast digest for quick lookup.
    api_key_md5 = db.Column(db.String(32), unique=True)
    # Password-reset token currently active for this account, with its expiry.
    reset_token = db.Column(db.String(64))
    reset_token_expires = db.Column(db.DateTime)
    # Uploaded profile avatar (served back from the registry).
    avatar_path = db.Column(db.String(500))
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
    static docstring. ``applies_after`` stages a note's rollout: it is only
    appended once the connecting client has listed the tools that many times,
    so revised guidance does not disrupt sessions already in flight.
    """
    __tablename__ = "tool_notes"

    id = db.Column(db.Integer, primary_key=True)
    tool_name = db.Column(db.String(80), nullable=False)
    note = db.Column(db.Text, default="")
    applies_after = db.Column(db.Integer, default=0, nullable=False)
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


class ExperimentNote(db.Model):
    """A private free-text note a user attaches to one of their experiments
    (triage remarks, contact details for the data owner, internal follow-ups).

    Notes are owner-scoped: the REST read path filters by the caller, and the
    assistant may quote a user's own notes back to them when briefing an
    experiment.
    """
    __tablename__ = "experiment_notes"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    experiment_id = db.Column(db.Integer, db.ForeignKey("experiments.id"))
    note = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=_now)


class Feedback(db.Model):
    """A user-submitted (features, label) correction for a model, queued for
    the next scheduled retrain. ``status`` tracks review: pending samples are
    candidates; only approved ones should be used."""
    __tablename__ = "feedback"

    id = db.Column(db.Integer, primary_key=True)
    model_id = db.Column(db.Integer, db.ForeignKey("models.id"), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    features = db.Column(db.Text, default="")
    label = db.Column(db.String(80), default="")
    status = db.Column(db.String(20), default="pending")
    created_at = db.Column(db.DateTime, default=_now)


class Setting(db.Model):
    """A runtime-tunable setting, layered over the env-based Config.

    Operators and per-user preferences write here (see core/settings.py); the
    value is a JSON document so namespaced preferences can be merged without a
    schema migration.
    """
    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(120), unique=True, nullable=False)
    value_json = db.Column(db.Text, default="null")
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    updated_at = db.Column(db.DateTime, default=_now, onupdate=_now)


class CorpusDoc(db.Model):
    """A row from the assistant's built-in fine-tune corpus (historical support
    transcripts the assistant was tuned on). Shipped with the deployment so the
    assistant can answer account-policy questions consistently."""
    __tablename__ = "corpus_docs"

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=_now)


class Plugin(db.Model):
    """An installed analysis plugin: a Python file contributed through the API
    and imported into the app process at startup, so its metrics/hooks register
    themselves with the pipeline runner."""
    __tablename__ = "plugins"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    path = db.Column(db.String(500), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    enabled = db.Column(db.Boolean, default=True, nullable=False)
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


# ----------------------------------------------------------------------
# Object-level authorization demo tier. A dedicated, self-contained set of
# models covering each of four object-level authorization models in
# isolation: ownership (PrivateNote), membership (Team/TeamMember/TeamNote),
# hierarchical (Project/Task), and status (Article). See
# dvml/api/authz_demo.py for the routes.
# ----------------------------------------------------------------------


class PrivateNote(db.Model):
    __tablename__ = "private_notes"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    body = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=_now)


class Team(db.Model):
    __tablename__ = "teams"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=_now)

    @property
    def members(self) -> list[int]:
        """User ids belonging to this team -- a plain Python property (not a
        relationship) so the membership check reads as a direct attribute
        chain off the fetched object (`note.team.members`), matching the
        BOLARAY containment idiom."""
        return [tm.user_id for tm in TeamMember.query.filter_by(team_id=self.id)]


class TeamMember(db.Model):
    __tablename__ = "team_members"

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)


class TeamNote(db.Model):
    __tablename__ = "team_notes"

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    body = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=_now)

    team = db.relationship("Team")


class Project(db.Model):
    __tablename__ = "authz_demo_projects"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=_now)


class Task(db.Model):
    __tablename__ = "authz_demo_tasks"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("authz_demo_projects.id"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    body = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=_now)


class Article(db.Model):
    __tablename__ = "articles"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    body = db.Column(db.Text, default="")
    status = db.Column(db.String(20), default="draft")  # draft | published
    created_at = db.Column(db.DateTime, default=_now)
