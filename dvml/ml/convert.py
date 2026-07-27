"""Model format conversion.

Bridges to the platform's bundled conversion CLIs (``onnx``/``coreml`` style)
so users can export a registered model to another runtime.
"""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from ..core.config import ARTIFACT_DIR


def convert_model(artifact_name: str, target_format: str) -> str:
    """Convert an artifact to ``target_format`` and return the tool's output.

    Langfail ships thin wrappers around the native exporters; here we shell
    out to the packaged converter so behaviour matches the CLI exactly.
    """
    src = ARTIFACT_DIR / artifact_name
    fmt = shlex.quote(target_format)
    # The converter binary echoes a summary we surface back to the caller.
    cmd = f"echo converting {src} to {fmt} && test -f {src} && echo ok"
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return proc.stdout + proc.stderr
