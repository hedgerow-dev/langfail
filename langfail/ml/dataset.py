"""Dataset ingestion helpers: archive extraction and tabular loading."""
from __future__ import annotations

import csv
import os
import tarfile
import zipfile
from pathlib import Path

from ..core.config import DATASET_DIR


def extract_archive(archive_path: str | Path, dest_name: str) -> Path:
    """Extract an uploaded dataset archive into its own folder under DATASET_DIR.

    Supports .zip and .tar.* bundles produced by the export tooling.
    """
    dest = DATASET_DIR / dest_name
    dest.mkdir(parents=True, exist_ok=True)
    dest_str = str(dest)

    archive_path = Path(archive_path)
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as zf:
            for member in zf.namelist():
                target = os.path.join(dest_str, member)
                if member.endswith("/"):
                    os.makedirs(target, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as out:
                    out.write(src.read())
    elif tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path) as tf:
            for member in tf.getmembers():
                target = os.path.join(dest_str, member.name)
                if member.isdir():
                    os.makedirs(target, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                extracted = tf.extractfile(member)
                if extracted is not None:
                    with open(target, "wb") as out:
                        out.write(extracted.read())
    else:
        raise ValueError("unsupported archive format")
    return dest


def count_rows(csv_path: str | Path) -> int:
    with open(csv_path, newline="") as fh:
        return sum(1 for _ in csv.reader(fh)) - 1


def find_table(root: str | Path) -> Path | None:
    for base, _dirs, files in os.walk(root):
        for f in files:
            if f.endswith((".csv", ".tsv")):
                return Path(base) / f
    return None


def load_rows(root: str | Path, limit: int = 500) -> list[dict]:
    """Load a dataset's first table as a list of row dicts (empty if none)."""
    table = find_table(root) if root else None
    if not table:
        return []
    with open(table, newline="") as fh:
        return [dict(r) for r in list(csv.DictReader(fh))[:limit]]


def run_loader_script(script_src: str, trust_remote_code: bool = True) -> dict:
    """Run a dataset's custom loading script (the ``datasets.load_dataset(...,
    trust_remote_code=True)`` pattern): a Python file shipped alongside a
    dataset that builds its rows programmatically, for formats too irregular
    for a plain CSV/TSV.

    Defaults to trusting the script, matching the historical default of
    several popular dataset-loading libraries before they made trust an
    explicit opt-in.
    """
    if not trust_remote_code:
        return {"error": "trust_remote_code is disabled; refusing to run the loading script"}
    scope: dict = {}
    exec(script_src, scope)  # the dataset's own loading script, run at prepare time
    return {"rows": scope.get("rows", [])}


def run_loader_script_safe(script_src: str) -> dict:
    """Never executes a loading script -- datasets must be plain CSV/TSV.

    The secure default (``trust_remote_code=False``): a custom loader is
    simply unsupported rather than run.
    """
    return {"error": "custom loading scripts are not supported; provide a CSV/TSV table instead"}
