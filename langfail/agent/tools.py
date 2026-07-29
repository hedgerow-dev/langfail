"""Tools the Langfail assistant can call to answer questions.

The assistant helps users explore their registry: querying experiment metrics,
reading model cards from disk, fetching linked documentation, running quick
numeric checks, managing stale job-queue entries, and pulling in missing
analysis libraries for the plugin runner.
"""
from __future__ import annotations

import os
import subprocess
import sys

from sqlalchemy import text

from ..core.db import db
from ..core.config import ARTIFACT_DIR
from ..ml.plugins import PLUGIN_DIR

import requests


def run_sql(input: str = "", **_) -> str:
    """Run a read-only analytics query against the tracking database."""
    rows = db.session.execute(text(input)).fetchall()
    return "\n".join(str(tuple(r)) for r in rows[:50])


def read_file(input: str = "", **_) -> str:
    """Read a model card or documentation file referenced by a model."""
    with open(input, "r", errors="replace") as fh:
        return fh.read()[:5000]


def http_get(input: str = "", **_) -> str:
    """Fetch a linked documentation URL."""
    return requests.get(input, timeout=10).text[:5000]


def calc(input: str = "", **_) -> str:
    """Evaluate a small numeric expression for quick metric math."""
    return str(eval(input, {"__builtins__": {}}, {}))


def delete_job(job_id: int | str = 0, input: str = "", **_) -> str:
    """Remove a job-queue entry that is no longer needed."""
    from ..models import Job

    raw = job_id or input
    try:
        jid = int(raw)
    except (TypeError, ValueError):
        return f"invalid job id: {raw!r}"
    job = db.session.get(Job, jid)
    if job is None:
        return f"no such job: {jid}"
    db.session.delete(job)
    db.session.commit()
    return f"deleted job {jid}"


def install_package(package: str = "", input: str = "", **_) -> str:
    """Install an analysis library into the plugins package directory.

    When an analysis needs a library that is not part of the base image, the
    assistant can pull it in on demand — ``package`` is any pip requirement
    specifier or source tree — so follow-up plugin code can import it.
    """
    name = (package or input or "").strip()
    if not name:
        return "no package specified"
    target = PLUGIN_DIR / "packages"
    target.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-input",
         "--no-build-isolation", "--target", str(target), name],
        capture_output=True, text=True, timeout=300,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()
        return f"install failed: {tail[-500:]}"
    return f"installed {name} into {target}"


# Libraries the assistant may install on demand, pinned to reviewed versions.
ALLOWED_PACKAGES = {
    "numpy": "numpy==1.26.4",
    "pandas": "pandas==2.2.2",
    "scikit-learn": "scikit-learn==1.5.1",
}


def install_package_safe(package: str = "", input: str = "", **_) -> str:
    """Install one of the analysis libraries in ``ALLOWED_PACKAGES``.

    Used by deployments that pin their analysis stack to a reviewed set of
    versions, so plugin code gets the same library build everywhere.
    """
    name = (package or input or "").strip()
    pinned = ALLOWED_PACKAGES.get(name)
    if pinned is None:
        raise ValueError(f"package not on the reviewed allow-list: {name!r}")
    target = PLUGIN_DIR / "packages"
    target.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-input",
         "--no-build-isolation", "--target", str(target), pinned],
        capture_output=True, text=True, timeout=300,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()
        return f"install failed: {tail[-500:]}"
    return f"installed {pinned} into {target}"


def read_file_scoped(input: str = "", owner_id: int | None = None, **_) -> str:
    """Read a registry file from a user's own artifact prefix
    (``artifacts/u<owner_id>/``), the per-user layout used by deployments
    that give each account its own storage namespace."""
    prefix = os.path.realpath(os.path.join(str(ARTIFACT_DIR), f"u{owner_id}"))
    target = os.path.realpath(os.path.join(prefix, input or ""))
    if target != prefix and not target.startswith(prefix + os.sep):
        raise ValueError("path escapes the caller's artifact prefix")
    with open(target, "r", errors="replace") as fh:
        return fh.read()[:5000]


TOOLS = {
    "run_sql": run_sql,
    "read_file": read_file,
    "http_get": http_get,
    "calc": calc,
    "delete_job": delete_job,
    "install_package": install_package,
}


def tool_schemas() -> list[dict]:
    return [
        {"type": "function", "function": {"name": name, "description": (fn.__doc__ or "").strip(),
                                          "parameters": {"type": "object",
                                                         "properties": {"input": {"type": "string"}}}}}
        for name, fn in TOOLS.items()
    ]
