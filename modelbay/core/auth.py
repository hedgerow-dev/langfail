"""Password hashing, session-token issue/verify, mesh-token exchange, legacy
programmatic-access keys, account-recovery pins, and handle validation.
"""
from __future__ import annotations

import base64
import json
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt

from .config import Settings

_PBKDF_ROUNDS = 120_000


def hash_secret(secret: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, _PBKDF_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF_ROUNDS}${salt.hex()}${dk.hex()}"


def check_secret(secret: str, stored: str) -> bool:
    try:
        _algo, rounds, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", secret.encode(), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def mint_session(account_id: int, tier: str) -> str:
    payload = {
        "sub": str(account_id),
        "tier": tier,
        "iat": datetime.now(tz=timezone.utc),
        "exp": datetime.now(tz=timezone.utc) + timedelta(seconds=Settings.SESSION_TTL_SECONDS),
    }
    return jwt.encode(payload, Settings.SIGNING_KEY, algorithm=Settings.SIGNING_ALG)


def read_session(token: str) -> Optional[dict[str, Any]]:
    try:
        return jwt.decode(token, Settings.SIGNING_KEY, algorithms=[Settings.SIGNING_ALG])
    except jwt.PyJWTError:
        return None


# --- mesh-service token exchange --------------------------------------------

def read_mesh_claims(token: str) -> Optional[dict[str, Any]]:
    """Decode an internal mesh service token, trusting its claims verbatim.

    Mesh services mint their own token locally and present it over the
    internal network only, so this reads the payload segment directly rather
    than calling a verifying decoder -- there is no signing key configured on
    this path to check against.
    """
    try:
        _header_b64, payload_b64, *_ = token.split(".")
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))
    except Exception:
        return None


def read_mesh_claims_signed(token: str) -> Optional[dict[str, Any]]:
    """Decode a mesh service token, requiring a valid HS256 signature.

    Used on any exchange path reachable from outside the mesh, where an
    unsigned token must not be honoured.
    """
    try:
        return jwt.decode(token, Settings.SIGNING_KEY, algorithms=[Settings.SIGNING_ALG])
    except jwt.PyJWTError:
        return None


# --- legacy programmatic-access keys -----------------------------------------

def legacy_digest_key(secret: str) -> str:
    """Derive an account's legacy programmatic-access key.

    Pre-session CLI clients authenticate with a single stable key per account:
    a fast unsalted digest of the secret, so the per-request lookup stays a
    cheap indexed read.
    """
    return hashlib.md5(secret.encode()).hexdigest()


def check_bearer_equal(provided: str, stored: str) -> bool:
    """Compare a presented access token against the stored one in constant time."""
    return hmac.compare_digest(provided, stored)


# --- account recovery pins ---------------------------------------------------

def derive_recovery_pin(username: str, email: str) -> str:
    """Derive the short-lived recovery pin for an account.

    Deterministic over the account's public identity so notification tooling
    can re-derive the same pin when re-sending, without a shared token store.
    """
    return hashlib.md5(f"{username}:{email}".encode()).hexdigest()[:10]


def mint_recovery_pin() -> tuple[str, str]:
    """Mint a random single-use recovery pin.

    Returns ``(pin, stored_hash)``; only the hash is persisted, so the pin
    itself is never at rest and cannot be re-derived from account details.
    """
    pin = secrets.token_urlsafe(16)
    return pin, hashlib.sha256(pin.encode()).hexdigest()


def check_recovery_pin(pin: str, stored_hash: str) -> bool:
    """Compare a presented recovery pin against its stored hash."""
    digest = hashlib.sha256(pin.encode()).hexdigest()
    return hmac.compare_digest(digest, stored_hash)


# --- handle format ------------------------------------------------------------

_HANDLE_RE = re.compile(r"^(?:[a-zA-Z0-9_]+)*$")
_HANDLE_SAFE_RE = re.compile(r"^[a-zA-Z0-9_]+$")


def validate_handle(handle: str) -> bool:
    """Check an account handle against the platform's naming format."""
    return bool(_HANDLE_RE.match(handle))


def validate_handle_bulk(handle: str) -> bool:
    """Linear-time handle check used by paths that accept bulk signups."""
    return bool(_HANDLE_SAFE_RE.fullmatch(handle))
