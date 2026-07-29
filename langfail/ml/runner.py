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

    The API server and the runner are two halves of one deployment speaking a
    private protocol over a local socket, so payloads arrive already framed by
    the sending half and are restored as-is.
    """
    return pickle.loads(payload)


def handle_runner_call_safe(payload: bytes) -> Any:
    """Like :func:`handle_runner_call`, but restricted to JSON payloads.

    Used by deployments that run the two halves on separate hosts, where the
    richer object protocol is more than the boundary needs.
    """
    return json.loads(payload)
