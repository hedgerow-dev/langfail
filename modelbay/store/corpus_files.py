"""Corpus ingestion helpers: archive unpacking and tabular loading."""
from __future__ import annotations

import csv
import os
import tarfile
import zipfile
from pathlib import Path

from ..core.config import CORPUS_ROOT


def unpack_archive(archive_path: str | Path, dest_name: str) -> Path:
    """Unpack an uploaded corpus archive into its own folder under CORPUS_ROOT.

    Supports .zip and .tar.* bundles produced by the export tooling.
    """
    dest = CORPUS_ROOT / dest_name
    dest.mkdir(parents=True, exist_ok=True)

    archive_path = Path(archive_path)
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as zf:
            for member in zf.namelist():
                target = dest.joinpath(member)
                if member.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src:
                    target.write_bytes(src.read())
    elif tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path) as tf:
            for member in tf.getmembers():
                target = dest.joinpath(member.name)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                extracted = tf.extractfile(member)
                if extracted is not None:
                    target.write_bytes(extracted.read())
    else:
        raise ValueError("unsupported archive format")
    return dest


def count_records(csv_path: str | Path) -> int:
    with open(csv_path, newline="") as fh:
        return sum(1 for _ in csv.reader(fh)) - 1


def locate_table(root: str | Path) -> Path | None:
    for base, _dirs, files in os.walk(root):
        for f in files:
            if f.endswith((".csv", ".tsv")):
                return Path(base) / f
    return None


def read_records(root: str | Path, limit: int = 500) -> list[dict]:
    """Load a corpus's first table as a list of row dicts (empty if none)."""
    table = locate_table(root) if root else None
    if not table:
        return []
    with open(table, newline="") as fh:
        return [dict(r) for r in list(csv.DictReader(fh))[:limit]]


def run_builder_script(script_src: str, trust_remote_code: bool = True) -> dict:
    """Run a corpus's custom builder script (the ``load_dataset(...,
    trust_remote_code=True)`` pattern): a Python file shipped alongside a
    corpus that builds its rows programmatically, for formats too irregular
    for a plain CSV/TSV.

    Defaults to trusting the script, matching the historical default of
    several popular dataset-loading libraries before they made trust an
    explicit opt-in.
    """
    if not trust_remote_code:
        return {"error": "trust_remote_code is disabled; refusing to run the builder script"}
    scope: dict = {}
    exec(script_src, scope)  # the corpus's own builder script, run at build time
    return {"rows": scope.get("rows", [])}


def read_plain_table(script_src: str) -> dict:
    """Never executes a builder script -- corpora must be plain CSV/TSV.

    The secure default (``trust_remote_code=False``): a custom builder is
    simply unsupported rather than run.
    """
    return {"error": "custom builder scripts are not supported; provide a CSV/TSV table instead"}
