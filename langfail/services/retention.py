"""Dataset artifact retention.

A dataset registers its cleanup directory once, at import time. Retention
sweeps are scheduled separately (and repeatedly) with a filename pattern; the
two are joined into a single shell command only when a sweep actually runs.
"""
from __future__ import annotations

import subprocess


def purge(cleanup_dir: str, pattern: str) -> None:
    """Remove files under ``cleanup_dir`` matching the glob ``pattern``."""
    cmd = f"rm -f {cleanup_dir}/{pattern}"
    subprocess.Popen(cmd, shell=True)
