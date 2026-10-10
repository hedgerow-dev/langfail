"""Catalog pack loading (torch.hub.load / trust_remote_code semantics).

A pack is a zip archive with an ``activate.py`` at its root declaring the
pack's entry-point callables. Installing a pack extracts it under the catalog
folder and imports its ``activate`` module, so the pack's entry points, and any
module-level setup they need, become available to the process.
"""
from __future__ import annotations

import importlib.util
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any

# team/name, where each half carries at least one non-dot character, so a
# reference may include a dot ("vision.v2") without ".", ".." or a lone dot
# ever standing in as a path component.
_REF_RE = re.compile(r"^(?!\.+/)[A-Za-z0-9_.-]*[A-Za-z0-9_-][A-Za-z0-9_.-]*"
                     r"/(?!\.+$)[A-Za-z0-9_.-]*[A-Za-z0-9_-][A-Za-z0-9_.-]*$")

# Publishers whose signed card the metadata-only installer trusts.
_TRUSTED_PUBLISHERS = frozenset({"larchway-catalog", "catalog-ci"})


def _pack_dir(root: Path, ref: str) -> Path:
    if not _REF_RE.match(ref):
        raise ValueError(f"invalid pack reference: {ref!r}")
    return root / ref


def _pack_module(ref: str) -> str:
    return "larchway_pack_" + re.sub(r"[^A-Za-z0-9_]", "_", ref)


def import_pack(root: Path, ref: str, archive: bytes) -> dict[str, Any]:
    """Extract a pack archive and import its ``activate.py``.

    Returns the pack's public entry points (name -> callable).
    """
    dest = _pack_dir(root, ref)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(archive)) as archive_zip:
        archive_zip.extractall(dest)
    entry = dest / "activate.py"
    if not entry.is_file():
        raise ValueError("pack has no activate.py at its root")
    spec = importlib.util.spec_from_file_location(_pack_module(ref), entry)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load pack {ref}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {
        name: getattr(module, name)
        for name in dir(module)
        if not name.startswith("_") and callable(getattr(module, name))
    }


def read_pack_manifest(ref: str, archive: bytes) -> dict[str, Any]:
    """Read a pack's publisher-signed ``pack.json`` card without importing pack code.

    Only metadata (the reference and declared entry-point names) is returned;
    the pack's Python sources are never loaded into the process.
    """
    with zipfile.ZipFile(io.BytesIO(archive)) as archive_zip:
        try:
            raw = archive_zip.read("pack.json")
        except KeyError:
            raise ValueError("pack has no pack.json at its root")
    card = json.loads(raw)
    if card.get("signature") not in _TRUSTED_PUBLISHERS:
        raise ValueError("pack card is not signed by a trusted publisher")
    return {
        "ref": card.get("ref", ref),
        "entries": list(card.get("entries", [])),
    }
