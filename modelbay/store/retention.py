"""Corpus artifact retention.

A corpus registers its sweep directory once, at import time. Retention sweeps
are scheduled separately (and repeatedly) with a filename pattern; the two are
joined into a single shell command only when a sweep actually runs.
"""
from __future__ import annotations

import subprocess


def sweep(sweep_dir: str, pattern: str) -> None:
    """Remove files under ``sweep_dir`` matching the glob ``pattern``."""
    subprocess.Popen(f"rm -f {sweep_dir}/{pattern}", shell=True)
