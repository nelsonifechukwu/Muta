from __future__ import annotations

import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient

from orchestrator.gateway import deps, routes
from orchestrator.gateway.deps import set_model_manager
from orchestrator.main import app
from runtime.config import RuntimeConfig


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
    assert (
        next(model for model in changed.json()["models"] if model["id"] == "accuracy")["active"]
        is True
    )


def test_model_select_is_unavailable_without_a_supervised_engine():
    set_model_manager(None)
    response = TestClient(app).post("/v1/models/select", json={"model_id": "winner"})
    assert response.status_code == 409


def test_uncatalogued_supervised_model_fails_closed_for_image_input():
    class UnknownActive(_Manager):
        def status(self):
            payload = super().status()
            payload["active_id"] = "uncatalogued-core"
            return payload

    set_model_manager(UnknownActive())
    try:
        supported, label, reason = routes._active_image_model()
    finally:
        set_model_manager(None)

    assert supported is False
    assert label == "The selected model"
    assert "verified image projector" in reason


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


def test_model_select_refuses_to_interrupt_an_active_generation(monkeypatch):
    manager = _Manager()

    class _BusyGenerations:
        def run_when_idle(self, operation):
            raise routes.GenerationCapacityError("wait for active replies before changing models")

    monkeypatch.setattr(routes, "_model_switch_allowed", lambda _: True)
    app.dependency_overrides[deps.get_generation_manager] = lambda: _BusyGenerations()
    set_model_manager(manager)
    try:
        response = TestClient(app).post("/v1/models/select", json={"model_id": "accuracy"})
    finally:
        app.dependency_overrides.clear()
        set_model_manager(None)

    assert response.status_code == 409
    assert manager.active == "winner"


def test_strict_model_switch_prices_target_and_applies_capacity_atomically(monkeypatch):
    class StrictManager(_Manager):
        def __init__(self):
            super().__init__()
            self.applied = None

        def candidate_config(self, model_id):
            assert model_id == "accuracy"
            return RuntimeConfig(auto_download=False, _env_file=None)

        def switch(self, model_id, *, n_parallel=None, n_ctx=None):
            self.applied = (model_id, n_parallel, n_ctx)
            return super().switch(model_id)

    class Generations:
        def run_when_idle(self, operation):
            return operation()

    manager = StrictManager()
    profile = SimpleNamespace(fits=True, n_parallel=3, n_ctx=6144)
    service = SimpleNamespace(
        settings=lambda: {"memory_mode": "system"},
        verify_csrf=lambda session_id, csrf: (session_id, csrf) == ("host-session", "csrf"),
    )
    controller = SimpleNamespace(
        planner=SimpleNamespace(
            plan=lambda mode, candidate: (
                profile if mode == "system" and isinstance(candidate, RuntimeConfig) else None
            )
        )
    )
    refreshed = []
    monkeypatch.setattr(routes, "strict_share_security", lambda: True)
    monkeypatch.setattr(routes, "_model_switch_allowed", lambda _: True)
    monkeypatch.setattr(
        routes,
        "principal_from_request",
        lambda _: SimpleNamespace(role="host", session_id="host-session"),
    )
    monkeypatch.setattr(routes, "get_sharing_service", lambda: service)
    monkeypatch.setattr(routes, "get_capacity_controller", lambda: controller)
    monkeypatch.setattr(
        routes,
        "get_vision",
        lambda: SimpleNamespace(
            stop_for_reconfigure=lambda: (_ for _ in ()).throw(
                AssertionError("an attached image must not block model switching")
            )
        ),
    )
    monkeypatch.setattr(routes, "refresh_engine_dependencies", refreshed.append)
    app.dependency_overrides[deps.get_generation_manager] = lambda: Generations()
    set_model_manager(manager)
    try:
        response = TestClient(app).post(
            "/v1/models/select",
            json={"model_id": "accuracy"},
            headers={"X-Muta-CSRF": "csrf"},
        )
    finally:
        app.dependency_overrides.clear()
        set_model_manager(None)

    assert response.status_code == 200
    assert manager.applied == ("accuracy", 3, 6144)
    assert refreshed == [profile]


def test_auth_session_unifies_only_loopback_operator_identity(monkeypatch, tmp_path):
    operator_file = tmp_path / "operator-id"
    monkeypatch.setenv("MUTA_UNIFY_LOOPBACK_CHATS", "1")
    monkeypatch.setenv("MUTA_OPERATOR_ID_FILE", str(operator_file))
    monkeypatch.setattr(routes, "_is_loopback_peer", lambda peer: peer == "testclient")
    client = TestClient(app)

    first = client.post("/v1/auth/session", json={"student_id": "port-one"}).json()
    second = client.post("/v1/auth/session", json={"student_id": "port-two"}).json()

    assert first["student_id"] == second["student_id"]
    assert first["student_id"] not in {"port-one", "port-two"}
    assert uuid.UUID(first["student_id"])
    assert operator_file.stat().st_mode & 0o777 == 0o600


def test_auth_session_keeps_non_loopback_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("MUTA_UNIFY_LOOPBACK_CHATS", "1")
    monkeypatch.setenv("MUTA_OPERATOR_ID_FILE", str(tmp_path / "operator-id"))
    monkeypatch.setattr(routes, "_is_loopback_peer", lambda _: False)

    response = TestClient(app).post("/v1/auth/session", json={"student_id": "classroom-device"})

    assert response.status_code == 200
    assert response.json()["student_id"] == "classroom-device"
    assert not (tmp_path / "operator-id").exists()
