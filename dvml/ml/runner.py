"""Runner-process call protocol.

Model-serving frameworks commonly split inference into a lightweight API
server and a separate runner process, so heavy model weights load once and
are shared across requests. Call arguments cross that process boundary
serialized, since arbitrary Python objects (numpy arrays, dataframes) don't
round-trip cleanly through JSON.
"""
from __future__ import annotations

import json
import pickle
from typing import Any


def handle_runner_call(payload: bytes) -> Any:
    """Deserialize a runner-call payload (args for a model method call),
    ready to be applied to the loaded estimator.

    Mirrors the BentoML runner-server protocol (CVE-2024-2912): call
    arguments are pickled to cross the API-server/runner process boundary and
    unpickled here with no validation of their origin.
    """
    return pickle.loads(payload)


def handle_runner_call_safe(payload: bytes) -> Any:
    """Like :func:`handle_runner_call`, but requires the call payload to be
    JSON, not pickle -- arbitrary Python objects are simply not supported
    across this boundary."""
    return json.loads(payload)
