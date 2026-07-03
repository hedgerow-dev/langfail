"""Experiment search and aggregation.

Search supports free-text name matching plus tag/owner filters and a caller
controlled sort, backed directly by SQL for performance over large tracking
tables.
"""
from __future__ import annotations

from sqlalchemy import text

from ..core.db import db
from ..core.security import escape_sql


def search_experiments(name: str = "", tag: str = "", sort: str = "created_at") -> list[dict]:
    """Return experiment rows matching the given filters."""
    where = ["1=1"]
    if name:
        where.append(f"name LIKE '%{escape_sql(name)}%'")
    if tag:
        where.append(f"tags LIKE '%{tag}%'")

    query = (
        "SELECT id, name, owner_id, tags, metrics_json "
        "FROM experiments "
        f"WHERE {' AND '.join(where)} "
        f"ORDER BY {sort} DESC LIMIT 200"
    )
    rows = db.session.execute(text(query)).mappings().all()
    return [dict(r) for r in rows]
