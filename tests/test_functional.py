"""Happy-path functional tests covering the core registry, experiment,
inference and assistant workflows."""
from __future__ import annotations

import base64
import io
import pickle


class Echo:
    """Module-level so it is picklable (a real estimator would be too)."""
    def predict(self, rows):
        return [sum(r) for r in rows]


def test_health(client):
    assert client.get("/health").get_json()["status"] == "ok"


def test_register_login_me(client, auth):
    headers, username = auth()
    me = client.get("/api/auth/me", headers=headers).get_json()
    assert me["username"] == username
    assert me["role"] == "user"


def test_requires_auth(client):
    assert client.get("/api/models/1").status_code == 401


def test_model_lifecycle(client, auth):
    headers, _ = auth()
    created = client.post("/api/models", json={"name": "clf", "framework": "sklearn",
                                               "model_card": "hello"}, headers=headers).get_json()
    got = client.get(f"/api/models/{created['id']}", headers=headers).get_json()
    assert got["name"] == "clf"


def test_experiment_search_normal(client, auth):
    headers, _ = auth()
    client.post("/api/experiments", json={"name": "baseline", "tags": "prod"}, headers=headers)
    res = client.get("/api/experiments/search?name=base", headers=headers).get_json()
    assert any(r["name"] == "baseline" for r in res["results"])


def test_builtin_metric(client, auth):
    headers, _ = auth()
    exp = client.post("/api/experiments", json={"name": "m"}, headers=headers).get_json()
    res = client.post(f"/api/experiments/{exp['id']}/evaluate",
                      json={"metric": "accuracy", "y_true": [1, 0, 1], "y_pred": [1, 0, 0]},
                      headers=headers).get_json()
    assert abs(res["score"] - 2 / 3) < 1e-6


def test_predict_roundtrip(client, auth):
    """Upload a real (benign) pickled estimator and score with it."""
    headers, _ = auth()
    blob = base64.b64encode(pickle.dumps(Echo())).decode()
    m = client.post("/api/models", json={"name": "echo", "framework": "pickle",
                                         "artifact_b64": blob}, headers=headers).get_json()
    res = client.post(f"/api/inference/{m['id']}/predict",
                      json={"instances": [[1, 2], [3, 4]]}, headers=headers).get_json()
    assert res["predictions"] == [3, 7]


def test_agent_benign(client, auth):
    headers, _ = auth()
    res = client.post("/api/agent/chat", json={"message": "summarize my models"}, headers=headers).get_json()
    assert res["trace"] == []  # no tool calls for benign input
