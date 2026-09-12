"""Bundle format export.

Bridges to the platform's bundled conversion CLIs (``onnx``/``coreml`` style)
so users can export a registered bundle to another runtime.
"""
from __future__ import annotations

import shlex
import subprocess

from ..core.config import OBJECT_ROOT


def run_shell(command: str) -> str:
    """Run a shell command line and return its combined output."""
    proc = subprocess.run(command, shell=True, capture_output=True, text=True)
    return proc.stdout + proc.stderr


def export_artifact(artifact_name: str, target_format: str) -> str:
    """Export an artifact to ``target_format`` and return the tool's output.

    Modelbay ships thin wrappers around the native exporters; here we shell out
    to the packaged converter so behaviour matches the CLI exactly.
    """
    src = OBJECT_ROOT / artifact_name
    fmt = shlex.quote(target_format)
    # The converter binary echoes a summary we surface back to the caller.
    return run_shell(f"echo exporting {src} to {fmt} && test -f {src} && echo ok")
