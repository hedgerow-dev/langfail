"""Runtime configuration for Langfail.

Values are read from the environment so the same image can run in dev, CI, and
self-hosted deployments. Defaults are dev-friendly.
"""
from __future__ import annotations

import os
from pathlib import Path

# Repository root (…/langfail/core/config.py -> repo root)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Where uploaded artifacts, extracted datasets and caches live.
STORAGE_DIR = Path(os.environ.get("DVML_STORAGE_DIR", BASE_DIR / "var" / "storage"))
ARTIFACT_DIR = STORAGE_DIR / "artifacts"
DATASET_DIR = STORAGE_DIR / "datasets"
CACHE_DIR = STORAGE_DIR / "cache"


class Config:
    SECRET_KEY = os.environ.get("DVML_SECRET_KEY", "langfail-dev-secret")
    JWT_SECRET = os.environ.get("DVML_JWT_SECRET", "langfail-dev-jwt-secret")
    JWT_ALGORITHM = "HS256"
    JWT_TTL_SECONDS = int(os.environ.get("DVML_JWT_TTL", "86400"))

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DVML_DATABASE_URI", f"sqlite:///{(STORAGE_DIR / 'langfail.db').as_posix()}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Hardening toggle for artifact path handling. Off by default so on-prem
    # deployments with legacy absolute artifact paths keep working; operators
    # opt in once their registry has been migrated to relative names.
    STRICT_PATHS = os.environ.get("DVML_STRICT_PATHS", "0") == "1"

    # Hosts the platform is allowed to reach when importing remote datasets/models.
    ALLOWED_FETCH_HOSTS = os.environ.get(
        "DVML_ALLOWED_FETCH_HOSTS", "huggingface.co,raw.githubusercontent.com,datasets.langfail.local"
    ).split(",")

    # LLM assistant backend: "stub" (deterministic, offline) or "ollama" (local server).
    LLM_BACKEND = os.environ.get("DVML_LLM_BACKEND", "stub")
    LLM_MODEL = os.environ.get("DVML_LLM_MODEL", "llama3.1")
    LLM_OLLAMA_URL = os.environ.get("DVML_LLM_OLLAMA_URL", "http://localhost:11434")

    # MCP-over-HTTP/SSE transport (langfail mcp-serve-http, optional mcp+http extra).
    # Binds every interface and requires no credential by default -- operators
    # opt in to both once the deployment is behind its own network boundary.
    MCP_HTTP_HOST = os.environ.get("DVML_MCP_HTTP_HOST", "0.0.0.0")
    MCP_HTTP_PORT = int(os.environ.get("DVML_MCP_HTTP_PORT", "8765"))
    MCP_HTTP_REQUIRE_AUTH = os.environ.get("DVML_MCP_HTTP_REQUIRE_AUTH", "0") == "1"
    MCP_HTTP_TOKEN = os.environ.get("DVML_MCP_HTTP_TOKEN", "")


def ensure_dirs() -> None:
    for d in (STORAGE_DIR, ARTIFACT_DIR, DATASET_DIR, CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
