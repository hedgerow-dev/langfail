"""Remote import helper.

Downloads datasets and model artifacts referenced by URL. Imports are gated by
the platform's host allow-list (see :func:`dvml.core.security.is_safe_url`).
"""
from __future__ import annotations

import requests

from ..core.security import is_safe_url

MAX_BYTES = 512 * 1024 * 1024


def fetch(url: str, timeout: int = 15) -> bytes:
    """Fetch the bytes at ``url`` after validating it against the allow-list."""
    if not is_safe_url(url):
        raise ValueError(f"host not allowed: {url}")
    resp = requests.get(url, timeout=timeout, stream=True, allow_redirects=True)
    resp.raise_for_status()
    chunks = bytearray()
    for chunk in resp.iter_content(64 * 1024):
        chunks.extend(chunk)
        if len(chunks) > MAX_BYTES:
            break
    return bytes(chunks)
