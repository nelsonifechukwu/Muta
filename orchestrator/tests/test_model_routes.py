from __future__ import annotations

from fastapi.testclient import TestClient

from orchestrator.gateway import routes
from orchestrator.gateway.deps import set_model_manager
from orchestrator.main import app


class _Manager:
    def __init__(self) -> None:
        self.active = "winner"

    def status(self):
        return {
            "active_id": self.active,
            "switching": False,
            "models": [
                {
                    "id": "winner",
                    "label": "Winner",
                    "kind": "local",
                    "description": "fast",
                    "available": True,
                    "active": self.active == "winner",
                    "recommended": True,
                },
                {
                    "id": "accuracy",
                    "label": "Accuracy",
                    "kind": "local",
                    "description": "accurate",
                    "available": True,
                    "active": self.active == "accuracy",
                },
            ],
        }

    def switch(self, model_id):
        self.active = model_id
        return self.status()


def test_model_catalog_and_select_are_public_contract_routes(monkeypatch):
    manager = _Manager()
    monkeypatch.setattr(routes, "_model_switch_allowed", lambda _: True)
    set_model_manager(manager)
    try:
        client = TestClient(app)
        first = client.get("/v1/models")
        changed = client.post("/v1/models/select", json={"model_id": "accuracy"})
    finally:
        set_model_manager(None)

    assert first.status_code == 200
    assert first.json()["active_id"] == "winner"
    assert changed.status_code == 200
    assert changed.json()["active_id"] == "accuracy"
    assert next(model for model in changed.json()["models"] if model["id"] == "accuracy")[
        "active"
    ] is True


def test_model_select_is_unavailable_without_a_supervised_engine():
    set_model_manager(None)
    response = TestClient(app).post("/v1/models/select", json={"model_id": "winner"})
    assert response.status_code == 409


def test_model_select_is_for_the_loopback_operator_only(monkeypatch):
    manager = _Manager()
    set_model_manager(manager)
    monkeypatch.setenv("MUTA_ALLOW_MODEL_SWITCH", "1")
    try:
        response = TestClient(app).post("/v1/models/select", json={"model_id": "accuracy"})
    finally:
        set_model_manager(None)
    # TestClient's synthetic peer is not an IP address; a real 127.0.0.1/::1 peer is allowed.
    assert response.status_code == 403
    assert routes._model_switch_allowed("127.0.0.1") is True
    assert routes._model_switch_allowed("192.168.1.20") is False
