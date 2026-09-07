"""Run-tracking endpoints: create, search, pipeline execution, metric scoring,
and extension install."""
from __future__ import annotations

import base64
import json

import jsonpickle
from flask import Blueprint, g, jsonify, request

from ..core.store import db
from ..records import Run
from ..store.config_docs import load_pipeline_doc
from ..store.extensions import enable_extension
from ..store.pipeline_runner import execute_stages
from ..store.runs_repo import (ask_runs, ask_runs_structured, find_by_label,
                               search_runs, tally_by_owner)
from ..store.scoring import score_metric
from .guard import authenticated

bp = Blueprint("runs", __name__, url_prefix="/runs")


@bp.post("")
@authenticated
def create_run():
    data = request.get_json(force=True, silent=True) or {}
    params = {}
    if data.get("pipeline_config"):
        # Parse the training-pipeline YAML (may bind custom stage callables).
        params = load_pipeline_doc(data["pipeline_config"])

    run = Run(name=data.get("name", "run"), owner_id=g.account_id,
              label=data.get("label", ""),
              params_json=json.dumps(params, default=str))
    db.session.add(run)
    db.session.commit()
    return jsonify(id=run.id, name=run.name), 201


_DOC_KEYS = frozenset({"name", "params", "metrics", "label"})


def import_run_document(payload: str) -> dict:
    """Parse a run document as plain JSON, allow-listing top-level keys."""
    doc = json.loads(payload)
    if not isinstance(doc, dict):
        raise ValueError("run document must be a JSON object")
    unknown = set(doc) - _DOC_KEYS
    if unknown:
        raise ValueError(f"unexpected keys in run document: {sorted(unknown)}")
    return {k: doc[k] for k in _DOC_KEYS if k in doc}


@bp.get("/<int:run_id>/export")
@authenticated
def export_run(run_id: int):
    """Export a run as a portable document (round-trips through /import)."""
    run = db.session.get(Run, run_id)
    if not run:
        return jsonify(error="not found"), 404
    doc = {
        "name": run.name,
        "params": json.loads(run.params_json or "{}"),
        "metrics": json.loads(run.metrics_json or "{}"),
        "label": run.label,
    }
    return jsonify(payload=jsonpickle.encode(doc))


@bp.post("/import")
@authenticated
def import_run():
    """Import a run document previously produced by the export endpoint.

    The payload is a typed JSON document, so nested pipeline parameters and
    metric objects survive the round-trip intact.
    """
    data = request.get_json(force=True, silent=True) or {}
    doc = jsonpickle.decode(data.get("payload", ""))
    if not isinstance(doc, dict):
        return jsonify(error="invalid run document"), 400
    run = Run(
        name=doc.get("name", "run"),
        owner_id=g.account_id,
        params_json=json.dumps(doc.get("params", {}), default=str),
        metrics_json=json.dumps(doc.get("metrics", {}), default=str),
        label=doc.get("label", ""),
    )
    db.session.add(run)
    db.session.commit()
    return jsonify(id=run.id, name=run.name), 201


@bp.get("/search")
@authenticated
def browse():
    rows = search_runs(
        name=request.args.get("name", ""),
        label=request.args.get("label", ""),
        sort=request.args.get("sort", "id"),
    )
    return jsonify(results=rows)


@bp.get("/count")
@authenticated
def tally():
    """Return how many runs a given owner has (dashboard tally)."""
    total = tally_by_owner(request.args.get("owner", str(g.account_id)))
    return jsonify(count=total)


@bp.get("/by_label")
@authenticated
def by_label():
    """Return runs with an exact label match."""
    return jsonify(results=find_by_label(request.args.get("label", "")))


@bp.post("/ask")
@authenticated
def ask():
    """Natural-language run search, powered by text-to-SQL.

    The assistant translates ``question`` into SQL and it is run directly
    against the tracking database.
    """
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(results=ask_runs(data.get("question", "")))


@bp.post("/ask_structured")
@authenticated
def ask_structured():
    """Constrained natural-language search (``column=value`` only, allow-listed
    columns, bound parameters) -- no model-authored SQL is ever executed."""
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(results=ask_runs_structured(data.get("question", "")))


@bp.post("/<int:run_id>/execute")
@authenticated
def execute(run_id: int):
    """Execute the run's training pipeline and return the stage log.

    Stages may be supplied directly or, if omitted, are read from the stored
    pipeline configuration captured when the run was created.
    """
    run = db.session.get(Run, run_id)
    if not run:
        return jsonify(error="not found"), 404
    data = request.get_json(force=True, silent=True) or {}
    stages = data.get("stages")
    if stages is None:
        stages = json.loads(run.params_json or "{}").get("stages", [])
    return jsonify(log=execute_stages(stages))


@bp.post("/extensions")
@authenticated
def install_extension():
    """Install an analysis extension (Python source); imported at the next app boot."""
    data = request.get_json(force=True, silent=True) or {}
    source = base64.b64decode(data.get("source_b64", ""))
    extension = enable_extension(data.get("name", "extension"), source, owner_id=g.account_id)
    return jsonify(id=extension.id, name=extension.name, enabled=extension.enabled), 201


@bp.post("/<int:run_id>/score")
@authenticated
def score(run_id: int):
    run = db.session.get(Run, run_id)
    if not run:
        return jsonify(error="not found"), 404
    data = request.get_json(force=True, silent=True) or {}
    metric = data.get("metric", "mae")
    y_true = data.get("y_true", [])
    y_pred = data.get("y_pred", [])
    value = score_metric(metric, y_true, y_pred)
    metrics = json.loads(run.metrics_json or "{}")
    metrics[metric] = value
    run.metrics_json = json.dumps(metrics)
    db.session.commit()
    return jsonify(metric=metric, score=value)
