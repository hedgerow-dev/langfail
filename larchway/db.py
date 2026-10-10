"""SQLite storage: connection helper and schema.

Plain ``sqlite3`` keeps the workbench dependency-light. Each request gets its
own connection (see ``deps.sessions.get_db``); background work opens its own.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    handle        TEXT NOT NULL UNIQUE,
    display_name  TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'annotator',
    email         TEXT,
    passphrase    TEXT NOT NULL,
    cli_key       TEXT,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS access_tokens (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id     INTEGER NOT NULL REFERENCES members(id),
    label         TEXT NOT NULL,
    digest        TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS resets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id     INTEGER NOT NULL REFERENCES members(id),
    channel       TEXT NOT NULL,
    reset_secret  TEXT NOT NULL,
    expires_at    REAL NOT NULL,
    used          INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS work_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT NOT NULL,
    payload      TEXT NOT NULL DEFAULT '{}',
    member_id    INTEGER REFERENCES members(id),
    state        TEXT NOT NULL DEFAULT 'pending',
    outcome      TEXT,
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id     INTEGER NOT NULL REFERENCES members(id),
    name          TEXT NOT NULL,
    readme        TEXT NOT NULL DEFAULT '',
    size_bytes    INTEGER NOT NULL DEFAULT 0,
    placement     TEXT,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS journal_entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id     INTEGER NOT NULL REFERENCES members(id),
    heading       TEXT NOT NULL,
    text          TEXT NOT NULL DEFAULT '',
    updated_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS collections (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    created_by    INTEGER NOT NULL REFERENCES members(id)
);

CREATE TABLE IF NOT EXISTS collaborators (
    collection_id INTEGER NOT NULL REFERENCES collections(id),
    member_id     INTEGER NOT NULL REFERENCES members(id),
    PRIMARY KEY (collection_id, member_id)
);

CREATE TABLE IF NOT EXISTS collection_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL REFERENCES collections(id),
    prompt        TEXT NOT NULL,
    reference     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS eval_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id     INTEGER NOT NULL REFERENCES members(id),
    name          TEXT NOT NULL,
    label         TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS verdicts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER NOT NULL REFERENCES eval_runs(id),
    sample        TEXT NOT NULL,
    score         REAL NOT NULL,
    rationale     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS rubrics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id     INTEGER NOT NULL REFERENCES members(id),
    title         TEXT NOT NULL,
    guidance      TEXT NOT NULL DEFAULT '',
    state         TEXT NOT NULL DEFAULT 'draft'
);

CREATE TABLE IF NOT EXISTS tuning_rows (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    checkpoint_id INTEGER NOT NULL REFERENCES checkpoints(id),
    fingerprint   TEXT NOT NULL,
    outcome       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workspace_settings (
    namespace     TEXT PRIMARY KEY,
    document      TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS graders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id     INTEGER NOT NULL REFERENCES members(id),
    name          TEXT NOT NULL,
    runtime       TEXT NOT NULL DEFAULT 'portable',
    blob_path     TEXT,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recipes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id     INTEGER NOT NULL REFERENCES members(id),
    name          TEXT NOT NULL,
    steps_json    TEXT NOT NULL DEFAULT '[]',
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS addons (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id     INTEGER REFERENCES members(id),
    name          TEXT NOT NULL,
    path          TEXT NOT NULL,
    active         INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS intakes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL REFERENCES collections(id),
    member_id     INTEGER NOT NULL REFERENCES members(id),
    stored_path   TEXT NOT NULL,
    source_url    TEXT,
    callback_url  TEXT,
    state         TEXT NOT NULL DEFAULT 'queued',
    line_count    INTEGER
);

CREATE TABLE IF NOT EXISTS run_outputs (
    run_id        INTEGER PRIMARY KEY REFERENCES eval_runs(id),
    directory     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS heuristics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id     INTEGER NOT NULL REFERENCES members(id),
    name          TEXT NOT NULL,
    source        TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS amendments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id     INTEGER NOT NULL REFERENCES members(id),
    text          TEXT NOT NULL,
    label         TEXT NOT NULL,
    state         TEXT NOT NULL DEFAULT 'queued'
);

CREATE TABLE IF NOT EXISTS suggester_cues (
    cue           TEXT PRIMARY KEY,
    label         TEXT NOT NULL
);
"""


def connect(path: Path) -> sqlite3.Connection:
    # check_same_thread=False: FastAPI may open the connection in one
    # threadpool worker and use it in another within the same request.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
