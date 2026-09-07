"""Persistent records: accounts and registry artifacts."""
from __future__ import annotations

from .core.store import db


class Account(db.Model):
    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(200))
    secret_hash = db.Column(db.String(255), nullable=False)
    tier = db.Column(db.String(20), default="member")
    # Legacy programmatic-access digest (unsalted md5 of the plaintext secret,
    # for pre-session CLI clients) and its modern replacement (a random token).
    legacy_key = db.Column(db.String(32), unique=True)
    access_token = db.Column(db.String(64))
    recovery_pin = db.Column(db.String(64))
    recovery_pin_expires = db.Column(db.DateTime)
    avatar_path = db.Column(db.String(500))


class Job(db.Model):
    """An operations-queue entry, listed on the admin-only jobs view."""
    __tablename__ = "jobs"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(40), nullable=False)
    payload_json = db.Column(db.Text, default="{}")
    status = db.Column(db.String(20), default="queued")
    result = db.Column(db.Text, default="")
    owner_id = db.Column(db.Integer, db.ForeignKey("accounts.id"))


class Artifact(db.Model):
    __tablename__ = "artifacts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("accounts.id"))
    object_key = db.Column(db.String(400))


# --- object-boundaries demo: ownership / membership / hierarchical / status --

class Memo(db.Model):
    """An owner-private note (ownership authorization model)."""
    __tablename__ = "memos"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    body = db.Column(db.Text, default="")


class Squad(db.Model):
    """A team-equivalent grouping (membership authorization model)."""
    __tablename__ = "squads"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)

    @property
    def roster(self) -> list[int]:
        """Account ids belonging to this squad.

        A plain Python property rather than a relationship, so callers can
        read membership as a direct attribute chain off an already-fetched
        memo (``memo.squad.roster``) without configuring a second mapper.
        """
        return [m.account_id for m in SquadRoster.query.filter_by(squad_id=self.id)]


class SquadRoster(db.Model):
    __tablename__ = "squad_rosters"

    id = db.Column(db.Integer, primary_key=True)
    squad_id = db.Column(db.Integer, db.ForeignKey("squads.id"), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)


class SquadMemo(db.Model):
    __tablename__ = "squad_memos"

    id = db.Column(db.Integer, primary_key=True)
    squad_id = db.Column(db.Integer, db.ForeignKey("squads.id"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    body = db.Column(db.Text, default="")

    squad = db.relationship("Squad")


class Workspace(db.Model):
    """A project-equivalent parent (hierarchical authorization model)."""
    __tablename__ = "workspaces"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)


class Ticket(db.Model):
    __tablename__ = "tickets"

    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.Integer, db.ForeignKey("workspaces.id"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    body = db.Column(db.Text, default="")


class Post(db.Model):
    """A draft/published article (status authorization model)."""
    __tablename__ = "posts"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    body = db.Column(db.Text, default="")
    status = db.Column(db.String(20), default="draft")  # draft | published


# --- run tracking: search/count SQL, pipeline reflection, eval, extensions --

class Run(db.Model):
    """A tracked experiment run."""
    __tablename__ = "runs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("accounts.id"))
    label = db.Column(db.String(120), default="")
    params_json = db.Column(db.Text, default="{}")
    metrics_json = db.Column(db.Text, default="{}")


class Bundle(db.Model):
    """A registered model bundle: metadata plus a stored artifact blob."""
    __tablename__ = "bundles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    runtime = db.Column(db.String(40), default="sklearn")
    blob_path = db.Column(db.String(500))
    notes = db.Column(db.Text, default="")
    meta_json = db.Column(db.Text, default="{}")


class Corpus(db.Model):
    """An ingested dataset (local archive or remote import)."""
    __tablename__ = "corpora"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    origin_url = db.Column(db.String(500))
    store_path = db.Column(db.String(500))
    status = db.Column(db.String(20), default="pending")
    row_count = db.Column(db.Integer, default=0)
    # Optional URL pinged when a background import for this corpus finishes.
    notify_url = db.Column(db.String(500))
    # Directory a later retention sweep may clean up (see jobs/handlers.sweep_corpus).
    sweep_dir = db.Column(db.String(500))
    # Optional custom builder script, run at build time (see store/corpus_files.py).
    builder_script = db.Column(db.Text)


class Correction(db.Model):
    """A user-submitted (features, label) correction for a bundle, queued for
    the next scheduled scorer refresh. ``status`` tracks review: pending rows
    are candidates; only approved ones should be used."""
    __tablename__ = "corrections"

    id = db.Column(db.Integer, primary_key=True)
    bundle_id = db.Column(db.Integer, db.ForeignKey("bundles.id"), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("accounts.id"))
    features = db.Column(db.Text, default="")
    label = db.Column(db.String(80), default="")
    status = db.Column(db.String(20), default="pending")


class AssistantMemory(db.Model):
    """A durable fact the assistant recalls across sessions."""
    __tablename__ = "assistant_memories"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("accounts.id"))
    content = db.Column(db.Text, default="")


class RunNote(db.Model):
    """A private note attached to a run."""
    __tablename__ = "run_notes"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    run_id = db.Column(db.Integer, db.ForeignKey("runs.id"))
    note = db.Column(db.Text, default="")


class TranscriptDoc(db.Model):
    """A row of the assistant's shipped fine-tune transcript corpus."""
    __tablename__ = "transcript_docs"

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, default="")


class Setting(db.Model):
    """A runtime settings document, keyed by dotted namespace."""
    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(120), unique=True, nullable=False)
    value_json = db.Column(db.Text, default="null")
    updated_by = db.Column(db.Integer, db.ForeignKey("accounts.id"))


class Extension(db.Model):
    """A contributed Python module, imported into the process at next boot
    if enabled."""
    __tablename__ = "extensions"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    path = db.Column(db.String(500), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("accounts.id"))
    enabled = db.Column(db.Boolean, default=False)
