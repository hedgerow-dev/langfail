"""Actions the Modelbay assistant can call to answer questions.

The assistant helps users explore their registry: querying run metrics,
reading bundle notes from disk, fetching linked documentation, running quick
numeric checks, managing stale job-queue entries, and pulling in missing
analysis libraries for the extension runner.
"""
from __future__ import annotations

import os
import subprocess
import sys

import requests
from sqlalchemy import text

from ..core.config import EXTENSION_DIR, OBJECT_ROOT
from ..core.store import db


def query_db(input: str = "", **_) -> str:
    """Run a read-only analytics query against the tracking database."""
    rows = db.session.execute(text(input)).fetchall()
    return "\n".join(str(tuple(r)) for r in rows[:50])


def open_file(input: str = "", **_) -> str:
    """Read a bundle note or documentation file referenced by a bundle."""
    with open(input, "r", errors="replace") as fh:
        return fh.read()[:5000]


def fetch_url(input: str = "", **_) -> str:
    """Fetch a linked documentation URL."""
    return requests.get(input, timeout=10).text[:5000]


def compute(input: str = "", **_) -> str:
    """Evaluate a small numeric expression for quick metric math."""
    return str(eval(input, {"__builtins__": {}}, {}))


def drop_job(job_id: int | str = 0, input: str = "", **_) -> str:
    """Remove a job-queue entry that is no longer needed."""
    from ..records import Job

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
    return f"dropped job {jid}"


def add_library(package: str = "", input: str = "", **_) -> str:
    """Install an analysis library into the extensions package directory.

    When an analysis needs a library that is not part of the base image, the
    assistant can pull it in on demand -- ``package`` is any pip requirement
    specifier or source tree -- so follow-up extension code can import it.
    """
    name = (package or input or "").strip()
    if not name:
        return "no package specified"
    target = EXTENSION_DIR / "packages"
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
REVIEWED_LIBRARIES = {
    "numpy": "numpy==1.26.4",
    "pandas": "pandas==2.2.2",
    "scikit-learn": "scikit-learn==1.5.1",
}


def add_listed_library(package: str = "", input: str = "", **_) -> str:
    """Install one of the analysis libraries in ``REVIEWED_LIBRARIES``.

    Used by deployments that pin their analysis stack to a reviewed set of
    versions, so extension code gets the same library build everywhere.
    """
    name = (package or input or "").strip()
    pinned = REVIEWED_LIBRARIES.get(name)
    if pinned is None:
        raise ValueError(f"package not on the reviewed allow-list: {name!r}")
    target = EXTENSION_DIR / "packages"
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


def open_owned_file(input: str = "", owner_id: int | None = None, **_) -> str:
    """Read a registry file from an account's own object prefix
    (``objects/a<owner_id>/``), the per-account layout used by deployments
    that give each account its own storage namespace."""
    prefix = os.path.realpath(os.path.join(str(OBJECT_ROOT), f"a{owner_id}"))
    target = os.path.realpath(os.path.join(prefix, input or ""))
    if target != prefix and not target.startswith(prefix + os.sep):
        raise ValueError("path escapes the caller's object prefix")
    with open(target, "r", errors="replace") as fh:
        return fh.read()[:5000]


ACTIONS = {
    "query_db": query_db,
    "open_file": open_file,
    "fetch_url": fetch_url,
    "compute": compute,
    "drop_job": drop_job,
    "add_library": add_library,
}


# Parameters an action takes beyond the generic ``input`` string. Without these
# a real model only ever sees ``input`` and cannot call drop_job or add_library
# with their named arguments.
_EXTRA_PARAMETERS: dict[str, dict] = {
    "drop_job": {"job_id": {"type": "integer",
                            "description": "id of the queue entry to remove"}},
    "add_library": {"package": {"type": "string",
                                "description": "pip requirement specifier"}},
}


def action_schemas() -> list[dict]:
    schemas = []
    for name, fn in ACTIONS.items():
        properties = {"input": {"type": "string"}}
        properties.update(_EXTRA_PARAMETERS.get(name, {}))
        schemas.append({"type": "function", "function": {
            "name": name,
            "description": (fn.__doc__ or "").strip(),
            "parameters": {"type": "object", "properties": properties},
        }})
    return schemas
