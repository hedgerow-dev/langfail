"""Run search and aggregation.

Search supports free-text name matching plus a label filter and a caller
controlled sort, backed directly by SQL for performance over large tracking
tables.
"""
from __future__ import annotations

import re

from sqlalchemy import text

from ..core.store import db
from ..core.naming import escape_sql_literal


def _exec_raw(sql: str):
    """Run a SQL string assembled by string formatting (no bound parameters).

    A thin wrapper so call sites that build their own WHERE clause read as
    intent, distinct from the parameterized ``db.session.execute(query, {...})``
    calls used by the properly bound queries below.
    """
    return db.session.execute(text(sql)).mappings().all()


def search_runs(name: str = "", label: str = "", sort: str = "id") -> list[dict]:
    """Return run rows matching the given filters."""
    where = ["1=1"]
    if name:
        where.append(f"name LIKE '%{escape_sql_literal(name)}%'")
    if label:
        where.append(f"label LIKE '%{label}%'")

    query = (
        "SELECT id, name, owner_id, label, metrics_json "
        "FROM runs "
        f"WHERE {' AND '.join(where)} "
        f"ORDER BY {sort} DESC LIMIT 200"
    )
    return [dict(r) for r in _exec_raw(query)]


def tally_by_owner(owner: str = "") -> int:
    """Return how many runs belong to ``owner`` (numeric owner id).

    Used by dashboard widgets that only need a tally, so it returns a scalar
    count rather than rows.
    """
    owner = owner or "0"
    query = f"SELECT COUNT(*) FROM runs WHERE owner_id = {owner}"
    rows = db.session.execute(text(query)).scalar()
    return int(rows or 0)


def find_by_label(label: str = "") -> list[dict]:
    """Return runs carrying ``label`` (exact match), bound as a parameter."""
    query = text(
        "SELECT id, name, owner_id, label FROM runs "
        "WHERE label = :label ORDER BY id DESC LIMIT 200"
    )
    rows = db.session.execute(query, {"label": label}).mappings().all()
    return [dict(r) for r in rows]


# Columns the constrained natural-language search is allowed to filter on.
_ASK_ALLOWED_COLUMNS = {"owner_id", "label", "name"}


def ask_runs(question: str) -> list[dict]:
    """Natural-language run search.

    Asks the assistant to translate ``question`` into a SQL condition
    (:func:`modelbay.assistant.backend.draft_sql`) and runs the model's SQL
    directly -- the text-to-SQL pattern (LangChain ``SQLDatabaseChain`` /
    Vanna.ai).
    """
    from ..assistant.backend import draft_sql

    return [dict(r) for r in _exec_raw(draft_sql(question, table="runs"))]


def ask_runs_structured(question: str) -> list[dict]:
    """Constrained natural-language search: only ``column=value`` questions
    against an allow-list of columns are accepted, and the value is always
    bound as a parameter -- the model never authors raw SQL to execute."""
    match = re.match(r"^\s*(\w+)\s*=\s*(.+?)\s*$", question or "")
    if not match or match.group(1) not in _ASK_ALLOWED_COLUMNS:
        return []
    column, value = match.group(1), match.group(2)
    query = text(
        f"SELECT id, name, owner_id, label, metrics_json FROM runs "
        f"WHERE {column} = :value LIMIT 200"
    )
    rows = db.session.execute(query, {"value": value}).mappings().all()
    return [dict(r) for r in rows]
