"""Input-hardening helpers used across the platform to normalise untrusted
object keys and SQL literals."""
from __future__ import annotations

import re

# Parent-directory hop, either separator. Applied once to strip traversal.
_HOP = re.compile(r"\.\.[/\\]")


def normalize_name(key: str) -> str:
    """Return an object key reduced to stay under the storage root.

    Drops ``../`` (and ``..\\``) hops, then any leading separators, so the
    result resolves inside the intended folder.
    """
    collapsed = _HOP.sub("", key)
    return collapsed.lstrip("/\\")


def escape_sql_literal(value: str) -> str:
    """Escape a string literal for safe inclusion in a SQL statement."""
    return value.replace("'", "''")


def host_allowed(url: str) -> bool:
    """Allow only hosts on the platform's import allow-list.

    Used before importing remote corpora/bundles to prevent requests to
    arbitrary internal endpoints.
    """
    from urllib.parse import urlparse

    from .config import Settings

    host = urlparse(url).hostname or ""
    for allowed in Settings.IMPORT_HOSTS:
        allowed = allowed.strip()
        if allowed and allowed in host:
            return True
    return False
