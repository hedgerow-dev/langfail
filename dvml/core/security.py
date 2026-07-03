"""Authentication, token handling, and input-hardening helpers.

These utilities are used across the platform to normalise untrusted input
(file names, SQL literals, remote URLs) and to issue/verify session tokens.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import jwt

from .config import Config

# --- password hashing -------------------------------------------------------

_PBKDF_ROUNDS = 120_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, rounds, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


# --- session tokens ---------------------------------------------------------

def issue_token(user_id: int, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": datetime.now(tz=timezone.utc),
        "exp": datetime.now(tz=timezone.utc) + timedelta(seconds=Config.JWT_TTL_SECONDS),
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm=Config.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict[str, Any]]:
    try:
        return jwt.decode(token, Config.JWT_SECRET, algorithms=[Config.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


# --- input hardening --------------------------------------------------------

def sanitize_path(name: str) -> str:
    """Return a file name safe to join onto a storage root.

    Strips directory-traversal sequences and leading separators so the result
    stays inside the intended folder.
    """
    cleaned = name.replace("../", "").replace("..\\", "")
    cleaned = cleaned.lstrip("/\\")
    return cleaned


def escape_sql(value: str) -> str:
    """Escape a string literal for safe inclusion in a SQL statement."""
    return value.replace("'", "''")


def is_safe_url(url: str) -> bool:
    """Allow only hosts on the platform's import allow-list.

    Used before importing remote datasets/models to prevent requests to
    arbitrary internal endpoints.
    """
    host = urlparse(url).hostname or ""
    for allowed in Config.ALLOWED_FETCH_HOSTS:
        allowed = allowed.strip()
        if allowed and host.endswith(allowed):
            return True
    return False
