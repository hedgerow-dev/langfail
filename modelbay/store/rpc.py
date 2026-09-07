"""Worker-process call protocol.

Model-serving stacks commonly split scoring into a lightweight API server and
a separate worker process, so heavy bundle weights load once and are shared
across requests. Call arguments cross that process boundary serialized, since
arbitrary Python objects (numpy arrays, dataframes) don't round-trip cleanly
through JSON.
"""
from __future__ import annotations

import io
import json
import pickle
from typing import Any


def decode_worker_call(payload: bytes) -> Any:
    """Restore a worker-call payload (args for a bundle method call), ready to
    be applied to the loaded estimator.

    The API server and the worker are two halves of one deployment speaking a
    private protocol over a local socket, so payloads arrive already framed by
    the sending half and are restored as-is.
    """
    return pickle.Unpickler(io.BytesIO(payload)).load()


def decode_worker_call_json(payload: bytes) -> Any:
    """Like :func:`decode_worker_call`, but restricted to JSON payloads.

    Used by deployments that run the two halves on separate hosts, where the
    richer object protocol is more than the boundary needs.
    """
    return json.loads(payload)
