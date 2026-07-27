"""Hub-style model repo loading (torch.hub.load semantics).

A model repo is a zip archive with a ``hubconf.py`` at its root declaring
entry-point callables (``model()``, ``preprocess()``, ...). Installing a repo
extracts it under the hub storage directory and imports its hubconf, so the
repo's entry points — and any module-level setup they need — are available to
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

from ..core.config import STORAGE_DIR

HUB_DIR = STORAGE_DIR / "hub"

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

# Publisher signatures the manifest-only installer trusts.
_TRUSTED_SIGNATURES = frozenset({"langfail-hub", "hub-ci"})


def _repo_dir(repo_name: str) -> Path:
    if not _REPO_RE.match(repo_name):
        raise ValueError(f"invalid repo name: {repo_name!r}")
    return HUB_DIR / repo_name


def _module_name(repo_name: str) -> str:
    return "langfail_hub_" + re.sub(r"[^A-Za-z0-9_]", "_", repo_name)


def load_from_hub(repo_name: str, archive_bytes: bytes) -> dict[str, Any]:
    """Extract a hub archive and import its ``hubconf.py``.

    Returns the repo's public entry points (name -> callable).
    """
    dest = _repo_dir(repo_name)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
        zf.extractall(dest)
    hubconf = dest / "hubconf.py"
    if not hubconf.is_file():
        raise ValueError("archive has no hubconf.py at its root")
    spec = importlib.util.spec_from_file_location(_module_name(repo_name), hubconf)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load hubconf for {repo_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {
        name: getattr(module, name)
        for name in dir(module)
        if not name.startswith("_") and callable(getattr(module, name))
    }


def load_from_hub_manifest(repo_name: str, archive_bytes: bytes) -> dict[str, Any]:
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
        "name": manifest.get("name", repo_name),
        "entrypoints": list(manifest.get("entrypoints", [])),
    }
