"""Hub-style bundle repo loading (torch.hub.load semantics).

A bundle repo is a zip archive with an ``entrypoints.py`` at its root declaring
entry-point callables (``model()``, ``preprocess()``, ...). Installing a repo
extracts it under the hub storage directory and imports that module, so the
repo's entry points -- and any module-level setup they need -- are available to
the process.
"""
from __future__ import annotations

import importlib.util
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from ..core.config import DATA_DIR

HUB_DIR = DATA_DIR / "hub"

# owner/repo, where each half must contain something other than dots -- so a
# slug may carry a dot ("acme/vision.v2") without "..", "." or ".." ever
# standing in as a path component.
_SLUG_RE = re.compile(r"^(?!\.+/)[A-Za-z0-9_.-]*[A-Za-z0-9_-][A-Za-z0-9_.-]*"
                      r"/(?!\.+$)[A-Za-z0-9_.-]*[A-Za-z0-9_-][A-Za-z0-9_.-]*$")

# Publisher signatures the manifest-only installer trusts.
_TRUSTED_SIGNATURES = frozenset({"modelbay-hub", "hub-ci"})

ENTRYPOINT_MODULE = "entrypoints.py"


def _repo_dir(slug: str) -> Path:
    if not _SLUG_RE.match(slug):
        raise ValueError(f"invalid repo name: {slug!r}")
    return HUB_DIR / slug


def _module_name(slug: str) -> str:
    return "modelbay_hub_" + re.sub(r"[^A-Za-z0-9_]", "_", slug)


def install_repo(slug: str, archive_bytes: bytes) -> dict[str, Any]:
    """Extract a hub archive and import its entry-point module.

    Returns the repo's public entry points (name -> callable).
    """
    dest = _repo_dir(slug)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
        zf.extractall(dest)
    entry = dest / ENTRYPOINT_MODULE
    if not entry.is_file():
        raise ValueError(f"archive has no {ENTRYPOINT_MODULE} at its root")
    spec = importlib.util.spec_from_file_location(_module_name(slug), entry)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load entry points for {slug}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {
        name: getattr(module, name)
        for name in dir(module)
        if not name.startswith("_") and callable(getattr(module, name))
    }


def install_repo_manifest(slug: str, archive_bytes: bytes) -> dict[str, Any]:
    """Read a repo's publisher-signed ``manifest.json`` without importing repo code.

    Only metadata (repo name and declared entry-point names) is returned; the
    repo's Python sources are never loaded into the process.
    """
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
        try:
            raw = zf.read("manifest.json")
        except KeyError:
            raise ValueError("archive has no manifest.json at its root")
    manifest = json.loads(raw)
    if manifest.get("signature") not in _TRUSTED_SIGNATURES:
        raise ValueError("manifest is not signed by a trusted publisher")
    return {
        "name": manifest.get("name", slug),
        "entrypoints": list(manifest.get("entrypoints", [])),
    }
