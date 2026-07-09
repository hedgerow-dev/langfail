"""Experiment tracking endpoints."""
from __future__ import annotations

import json

from flask import Blueprint, g, jsonify, request

from ..core.db import db
from ..models import Experiment
from ..ml.metrics import evaluate_metric
from ..services.config_loader import load_pipeline_config
from ..services.experiments import (ask_experiments, ask_experiments_safe, count_by_owner,
                                    search_by_tag, search_experiments)
from ..services.pipeline import run_pipeline
from .deps import require_auth

bp = Blueprint("experiments", __name__, url_prefix="/api/experiments")


@bp.post("")
@require_auth
def create_experiment():
    data = request.get_json(force=True, silent=True) or {}
    params = {}
    if data.get("pipeline_config"):
        # Parse the training-pipeline YAML (may bind custom stage callables).
        params = load_pipeline_config(data["pipeline_config"])

    exp = Experiment(
        name=data.get("name", "experiment"),
        owner_id=g.user_id,
        model_id=data.get("model_id"),
        dataset_id=data.get("dataset_id"),
        params_json=json.dumps(params, default=str),
        tags=data.get("tags", ""),
    )
    db.session.add(exp)
    db.session.commit()
    return jsonify(id=exp.id, name=exp.name), 201


@bp.get("/search")
@require_auth
def search():
    rows = search_experiments(
        name=request.args.get("name", ""),
        tag=request.args.get("tag", ""),
        sort=request.args.get("sort", "created_at"),
    )
    return jsonify(results=rows)


@bp.get("/count")
@require_auth
def count():
    """Return how many experiments a given owner has (dashboard tally)."""
    total = count_by_owner(request.args.get("owner", str(g.user_id)))
    return jsonify(count=total)


@bp.get("/by_tag")
@require_auth
def by_tag():
    """Return experiments with an exact tag match."""
    return jsonify(results=search_by_tag(request.args.get("tag", "")))


@bp.post("/ask")
@require_auth
def ask():
    """Natural-language experiment search, powered by text-to-SQL.

    The assistant translates ``question`` into SQL and it is run directly
    against the tracking database.
    """
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(results=ask_experiments(data.get("question", "")))


@bp.post("/ask_safe")
@require_auth
def ask_safe():
    """Constrained natural-language search (``column=value`` only, allow-listed
    columns, bound parameters) — no model-authored SQL is ever executed."""
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(results=ask_experiments_safe(data.get("question", "")))


@bp.post("/<int:exp_id>/run")
@require_auth
def run(exp_id: int):
    """Execute the experiment's training pipeline and return the stage log.

    Stages may be supplied directly or, if omitted, are read from the stored
    pipeline configuration captured when the experiment was created.
    """
    exp = db.session.get(Experiment, exp_id)
    if not exp:
        return jsonify(error="not found"), 404
    data = request.get_json(force=True, silent=True) or {}
    stages = data.get("stages")
    if stages is None:
        stages = json.loads(exp.params_json or "{}").get("stages", [])
    return jsonify(log=run_pipeline(stages))


@bp.post("/<int:exp_id>/evaluate")
@require_auth
def evaluate(exp_id: int):
    exp = db.session.get(Experiment, exp_id)
    if not exp:
        return jsonify(error="not found"), 404
    data = request.get_json(force=True, silent=True) or {}
    metric = data.get("metric", "mae")
    y_true = data.get("y_true", [])
    y_pred = data.get("y_pred", [])
    score = evaluate_metric(metric, y_true, y_pred)
    metrics = json.loads(exp.metrics_json or "{}")
    metrics[metric] = score
    exp.metrics_json = json.dumps(metrics)
    db.session.commit()
    return jsonify(metric=metric, score=score)
