"""Runtime settings for Modelbay.

Read from the environment so one image runs everywhere; defaults are
dev-friendly. Names are intentionally unrelated to any sibling project's.
"""
from __future__ import annotations

import os
from pathlib import Path

# …/modelbay/core/config.py -> repo root
ROOT_DIR = Path(__file__).resolve().parent.parent.parent

# Where uploaded objects, corpora, extensions, and caches live.
DATA_DIR = Path(os.environ.get("MODELBAY_DATA_DIR", ROOT_DIR / "var" / "modelbay"))
OBJECT_ROOT = DATA_DIR / "objects"
CORPUS_ROOT = DATA_DIR / "corpora"
CACHE_ROOT = DATA_DIR / "cache"
EXTENSION_DIR = DATA_DIR / "extensions"


class Settings:
    SECRET_KEY = os.environ.get("MODELBAY_SECRET_KEY", "modelbay-dev-secret")
    SIGNING_KEY = os.environ.get("MODELBAY_SIGNING_KEY", "modelbay-dev-signing-key")
    SIGNING_ALG = "HS256"
    SESSION_TTL_SECONDS = int(os.environ.get("MODELBAY_SESSION_TTL", "86400"))

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "MODELBAY_DATABASE_URI", f"sqlite:///{(DATA_DIR / 'modelbay.db').as_posix()}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Object-name hardening toggle. Off by default so deployments with legacy
    # absolute object keys keep resolving; operators opt in after migration.
    PIN_OBJECT_NAMES = os.environ.get("MODELBAY_PIN_OBJECT_NAMES", "0") == "1"

    # Hosts the platform may reach when importing remote corpora/bundles.
    IMPORT_HOSTS = os.environ.get(
        "MODELBAY_IMPORT_HOSTS", "huggingface.co,raw.githubusercontent.com,corpora.modelbay.local"
    ).split(",")

    # Assistant backend: "offline" (deterministic, no network) or "remote".
    ASSISTANT_BACKEND = os.environ.get("MODELBAY_ASSISTANT_BACKEND", "offline")
    ASSISTANT_MODEL = os.environ.get("MODELBAY_ASSISTANT_MODEL", "llama3.1")
    ASSISTANT_ENDPOINT = os.environ.get("MODELBAY_ASSISTANT_ENDPOINT", "http://localhost:11434")


def ensure_dirs() -> None:
    for d in (DATA_DIR, OBJECT_ROOT, CORPUS_ROOT, CACHE_ROOT, EXTENSION_DIR):
        d.mkdir(parents=True, exist_ok=True)
