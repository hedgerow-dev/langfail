"""Subprocess helpers for the small jobs the workbench hands to coreutils."""
from __future__ import annotations

import asyncio
import shlex
import subprocess
from pathlib import Path


async def export_weights(src: Path, stem: str, fmt: str, dest_dir: Path) -> int:
    """Copy a checkpoint's weights into the exports folder as ``<stem>.<fmt>``."""
    line = f"cp {shlex.quote(str(src))} {dest_dir}/{stem}.{shlex.quote(fmt)}"
    proc = await asyncio.create_subprocess_shell(line, stdout=asyncio.subprocess.DEVNULL,
                                                 stderr=asyncio.subprocess.DEVNULL)
    return await proc.wait()


def count_lines(path: Path, label: str) -> int:
    """Line count of an intake file, echoed with its collection label for the job log."""
    out = subprocess.check_output(f'echo "{label}: $(wc -l < {shlex.quote(str(path))})"',
                                  shell=True, text=True)
    try:
        return int(out.rsplit(":", 1)[-1])
    except ValueError:
        return 0


def prune_outputs(directory: str, pattern: str) -> int:
    """Delete files matching ``pattern`` inside a run's outputs directory."""
    return subprocess.run(["/bin/sh", "-c", f"cd {directory} && rm -f -- {pattern}"]).returncode
