"""Adversarial lifecycle tests for offline Muta Share accounts and sessions."""

from __future__ import annotations

import socket
import sqlite3
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from contracts.models import ShareHostUpdate
from orchestrator.gateway import auth, lan, share_routes, sharing
from orchestrator.gateway.lan import LanServerManager
from orchestrator.gateway.share_routes import router
from orchestrator.gateway.sharing import (
    AuthenticationError,
    EnrollmentError,
    SharingService,
    get_sharing_service,
)
from orchestrator.main import app as assembled_app


def test_account_survives_logout_restart_and_is_erased_only_by_host(tmp_path):
    path = tmp_path / "share.sqlite3"
    service = SharingService(path)
    with pytest.raises(EnrollmentError, match="not accepting"):
        service.signup("Ada", "correct horse battery", throttle_key="off")

    service.update_settings(enabled=True, memory_mode="competition")
    signup = service.signup("Ada", "correct horse battery", throttle_key="signup")
    user_id = service.users()[0]["id"]
    assert service.users()[0]["status"] == "pending"
    with pytest.raises(AuthenticationError, match="waiting"):
        service.login("ada", "correct horse battery", throttle_key="pending")

    service.approve(user_id)
    enrollment, approved_session = service.enrollment(
        signup["enrollment_id"], signup["enrollment_secret"]
    )
    assert enrollment["status"] == "approved"
    assert approved_session is not None
    assert service.resolve_session(approved_session.token).subject == user_id
    assert service.logout(approved_session.token)
    assert service.resolve_session(approved_session.token) is None

    login = service.login("ADA", "correct horse battery", throttle_key="login")
    assert login.principal.subject == user_id
    service.close()

    reopened = SharingService(path)
    assert reopened.resolve_session(login.token).subject == user_id
    reopened.begin_removal(user_id)
    assert reopened.resolve_session(login.token) is None
    reopened.finalize_removal(user_id)
    replacement = reopened.signup("ada", "a new password", throttle_key="replacement")
    assert replacement["status"] == "pending"
    reopened.close()

    raw = path.read_bytes()
    assert b"correct horse battery" not in raw
    assert b"a new password" not in raw


def test_disable_preserves_accounts_but_revokes_every_member_session(tmp_path):
    service = SharingService(tmp_path / "share.sqlite3")
    service.update_settings(enabled=True, memory_mode="system")
    service.signup("Bimpe", "another good password", throttle_key="signup")
    user_id = service.users()[0]["id"]
    service.approve(user_id)
    session = service.login("bimpe", "another good password", throttle_key="login")

    service.update_settings(enabled=False, memory_mode="competition")

    assert service.users()[0]["status"] == "approved"
    assert service.resolve_session(session.token) is None
    with pytest.raises(AuthenticationError, match="cannot sign in"):
        service.login("bimpe", "another good password", throttle_key="disabled")


def test_removal_waits_for_an_acquired_write_and_refuses_every_late_write(tmp_path):
    service = SharingService(tmp_path / "share.sqlite3")
    service.update_settings(enabled=True, memory_mode="competition")
    service.signup("Bola", "private classroom password", throttle_key="signup")
    user_id = service.users()[0]["id"]
    service.approve(user_id)
    removed = threading.Event()

    with service.member_write(user_id):
        worker = threading.Thread(
            target=lambda: (service.begin_removal(user_id), removed.set()), daemon=True
        )
        worker.start()
        time.sleep(0.05)
        assert not removed.is_set(), "erase passed an in-flight durable write"
    worker.join(timeout=1)
    assert removed.is_set()
    service.finalize_removal(user_id)

    with pytest.raises(AuthenticationError, match="no longer save"), service.member_write(user_id):
        pass


def test_declined_signup_can_request_approval_again(tmp_path):
    service = SharingService(tmp_path / "share.sqlite3")
    service.update_settings(enabled=True, memory_mode="competition")
    first = service.signup("Grace", "first private password", throttle_key="first")
    user_id = service.users()[0]["id"]

    service.reject(user_id)
    enrollment, session = service.enrollment(first["enrollment_id"], first["enrollment_secret"])

    assert enrollment["status"] == "rejected"
    assert session is None
    second = service.signup("grace", "second private password", throttle_key="second")
    assert second["status"] == "pending"


def test_password_hashing_has_a_process_wide_memory_concurrency_cap(monkeypatch):
    gate = threading.Event()
    lock = threading.Lock()
    active = 0
    peak = 0

    def fake_scrypt(password, *, salt, n, r, p, dklen):
        nonlocal active, peak
        _ = (password, salt, n, r, p)
        with lock:
            active += 1
            peak = max(peak, active)
        assert gate.wait(2.0)
        with lock:
            active -= 1
        return b"x" * dklen

    monkeypatch.setattr(sharing.hashlib, "scrypt", fake_scrypt)
    workers = [
        threading.Thread(
            target=sharing._password_hash,
            args=(b"private password", bytes([index]) * 16),
            daemon=True,
        )
        for index in range(6)
    ]
    for worker in workers:
        worker.start()
    deadline = time.monotonic() + 1.0
    while peak < 2 and time.monotonic() < deadline:
        time.sleep(0.005)
    assert peak == 2
    gate.set()
    for worker in workers:
        worker.join(timeout=1.0)
        assert not worker.is_alive()


def test_disabled_signup_is_rejected_before_password_hashing(monkeypatch, tmp_path):
    service = SharingService(tmp_path / "share.sqlite3")
    monkeypatch.setattr(
        sharing,
        "_password_hash",
        lambda *_args: pytest.fail("disabled signup must not spend RAM on scrypt"),
    )
    with pytest.raises(EnrollmentError, match="not accepting"):
        service.signup("Ada", "private password", throttle_key="disabled")


def test_expired_pending_signup_releases_username_and_roster_slot(tmp_path):
    service = SharingService(tmp_path / "share.sqlite3")
    service.update_settings(enabled=True, memory_mode="competition")
    first = service.signup("Amina", "private password", throttle_key="first")
    with service._lock, service._conn:
        service._conn.execute(
            "UPDATE share_enrollments SET expires_at = ? WHERE id = ?",
            ("1970-01-01T00:00:00+00:00", first["enrollment_id"]),
        )

    assert service.users() == []
    replacement = service.signup("amina", "new private password", throttle_key="replacement")
    assert replacement["status"] == "pending"


def test_expired_approved_enrollment_directs_learner_to_login(tmp_path):
    service = SharingService(tmp_path / "share.sqlite3")
    service.update_settings(enabled=True, memory_mode="competition")
    signup = service.signup("Kofi", "private password", throttle_key="signup")
    service.approve(service.users()[0]["id"])
    with service._lock, service._conn:
        service._conn.execute(
            "UPDATE share_enrollments SET expires_at = ? WHERE id = ?",
            ("1970-01-01T00:00:00+00:00", signup["enrollment_id"]),
        )

    status, session = service.enrollment(signup["enrollment_id"], signup["enrollment_secret"])
    assert status == {"status": "expired", "username": "Kofi", "can_login": True}
    assert session is None
    assert service.login("kofi", "private password", throttle_key="login")


class _Capacity:
    def status(self, mode):
        return {
            "memory_mode": mode,
            "n_parallel": 2,
            "context_per_chat": 1024,
            "memory_ceiling_bytes": 6 * 1024**3,
        }


class _Lan:
    running = True
    last_error = None

    def urls(self):
        return ["https://192.168.1.5:8443/chat/"]

    def primary_url(self):
        return self.urls()[0]

    def certificate_fingerprint(self):
        return "AA:BB"


def _share_app(monkeypatch, service: SharingService) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    monkeypatch.setattr(share_routes, "get_sharing_service", lambda: service)
    monkeypatch.setattr(auth, "get_sharing_service", lambda: service)
    monkeypatch.setattr(share_routes, "get_capacity_controller", lambda: _Capacity())
    monkeypatch.setattr(share_routes, "get_lan_manager", lambda: _Lan())
    return app


def test_https_signup_host_approval_cookie_exchange_and_logout(monkeypatch, tmp_path):
    service = SharingService(tmp_path / "share.sqlite3")
    service.update_settings(enabled=True, memory_mode="competition")
    app = _share_app(monkeypatch, service)
    remote = TestClient(app, base_url="https://muta.test", client=("192.168.1.20", 51000))

    signup = remote.post(
        "/v1/share/signup",
        json={"username": "Chidi", "password": "private classroom password"},
    )
    assert signup.status_code == 200
    assert remote.get("/v1/share/me").status_code == 401

    user_id = service.users()[0]["id"]
    host_session = service.issue_host_session("operator")
    host = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 51001))
    host.cookies.set("muta_share_session", host_session.token)
    approved = host.post(
        f"/v1/share/host/users/{user_id}/approve",
        headers={"X-Muta-CSRF": host_session.csrf_token},
    )
    assert approved.status_code == 200

    payload = signup.json()
    exchanged = remote.post(
        f"/v1/share/enrollments/{payload['enrollment_id']}",
        json={"secret": payload["enrollment_secret"]},
    )
    assert exchanged.status_code == 200
    assert exchanged.json()["authenticated"] is True
    cookie = exchanged.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
    assert remote.get("/v1/share/me").json()["user_id"] == user_id
    assert remote.post("/v1/share/logout").status_code == 200
    assert remote.get("/v1/share/me").status_code == 401


def test_remote_password_endpoint_refuses_plain_http(monkeypatch, tmp_path):
    service = SharingService(tmp_path / "share.sqlite3")
    service.update_settings(enabled=True, memory_mode="competition")
    app = _share_app(monkeypatch, service)
    remote = TestClient(app, base_url="http://muta.test", client=("192.168.1.20", 51000))

    response = remote.post(
        "/v1/share/signup",
        json={"username": "Dayo", "password": "private classroom password"},
    )

    assert response.status_code == 426
    assert service.users() == []


def test_passwords_are_scrypt_hashes_not_reversible_values(tmp_path):
    path = tmp_path / "share.sqlite3"
    service = SharingService(path)
    service.update_settings(enabled=True, memory_mode="competition")
    service.signup("Efe", "unusually memorable password", throttle_key="signup")
    with sqlite3.connect(path) as connection:
        salt, digest = connection.execute(
            "SELECT password_salt, password_hash FROM share_users"
        ).fetchone()
    assert len(salt) == 16
    assert len(digest) == 32
    assert digest != b"unusually memorable password"


def test_assembled_firewall_is_fail_closed_for_lan_and_keeps_host_local(monkeypatch, tmp_path):
    monkeypatch.setenv("MUTA_SHARE_STRICT", "1")
    monkeypatch.setenv("MUTA_SHARE_DB_PATH", str(tmp_path / "share.sqlite3"))
    get_sharing_service.cache_clear()
    remote = TestClient(
        assembled_app,
        base_url="https://muta.test:8443",
        client=("192.168.1.20", 51000),
    )
    host = TestClient(
        assembled_app,
        base_url="http://localhost",
        client=("127.0.0.1", 51001),
    )
    try:
        assert remote.get("/v1/health").status_code == 200
        assert remote.get("/v1/share/status").status_code == 200
        assert remote.get("/v1/models").status_code == 401
        assert remote.post("/v1/auth/session", json={"student_id": "attacker"}).status_code == 403
        assert remote.get("/internal/math/health").status_code == 404

        issued = host.post("/v1/auth/session", json={"student_id": "ignored"})
        assert issued.status_code == 200
        assert issued.json()["role"] == "host"
        assert host.get("/v1/share/host").status_code == 200
    finally:
        get_sharing_service().close()
        get_sharing_service.cache_clear()


def test_operator_bootstrap_rejects_dns_rebinding_host_and_origin(monkeypatch, tmp_path):
    monkeypatch.setenv("MUTA_SHARE_STRICT", "1")
    monkeypatch.setenv("MUTA_SHARE_DB_PATH", str(tmp_path / "share.sqlite3"))
    monkeypatch.setenv("MUTA_TRUST_PRIMARY_LISTENER", "1")
    monkeypatch.setenv("MUTA_PRIMARY_PORT", "8000")
    get_sharing_service.cache_clear()
    try:
        rebound = TestClient(
            assembled_app,
            base_url="http://attacker.example:8000",
            client=("127.0.0.1", 51001),
        )
        assert rebound.post("/v1/auth/session", json={"student_id": "x"}).status_code == 403

        proxy = TestClient(
            assembled_app,
            base_url="http://localhost:8000",
            client=("172.18.0.4", 51002),
        )
        hostile_origin = proxy.post(
            "/v1/auth/session",
            json={"student_id": "x"},
            headers={"Origin": "http://attacker.example:3000"},
        )
        assert hostile_origin.status_code == 403
        assert proxy.post("/v1/auth/session", json={"student_id": "x"}).status_code == 200

        # SSH forwarding collapses a learner's peer address to loopback. The dedicated learner
        # listener must still reject host bootstrap, even with a forged localhost Host header.
        forwarded_lan = TestClient(
            assembled_app,
            base_url="https://localhost:8443",
            client=("127.0.0.1", 51003),
        )
        assert forwarded_lan.post("/v1/auth/session", json={"student_id": "x"}).status_code == 403
    finally:
        get_sharing_service().close()
        get_sharing_service.cache_clear()


def test_lan_material_is_offline_https_qr_with_private_keys_locked_down(monkeypatch, tmp_path):
    monkeypatch.setenv("TUTOR_ROOT", str(tmp_path))
    monkeypatch.setenv("MUTA_SHARE_CERT_DIR", str(tmp_path / "certs"))
    monkeypatch.setenv("MUTA_SHARE_PORT", "9443")
    monkeypatch.setattr(lan, "lan_addresses", lambda: ["192.168.50.10"])
    manager = LanServerManager()

    manager._ensure_certificate()

    assert manager.primary_url() == "https://192.168.50.10:9443/chat/"
    assert manager.certificate_fingerprint()
    assert manager.qr_png().startswith(b"\x89PNG\r\n\x1a\n")
    assert manager.ca_bytes().startswith(b"-----BEGIN CERTIFICATE-----")
    assert (manager.cert_dir / "rootCA.key").stat().st_mode & 0o777 == 0o600
    assert (manager.cert_dir / "privkey.pem").stat().st_mode & 0o777 == 0o600


def test_container_never_advertises_its_private_bridge_address(monkeypatch):
    monkeypatch.delenv("MUTA_SHARE_HOST", raising=False)
    monkeypatch.setenv("MUTA_CONTAINERIZED", "1")
    assert lan.lan_addresses() == []

    monkeypatch.setenv("MUTA_SHARE_HOST", "192.168.50.20")
    assert lan.lan_addresses() == ["192.168.50.20"]


def test_cloud_launch_requires_an_explicit_relay_host(monkeypatch):
    monkeypatch.delenv("MUTA_SHARE_HOST", raising=False)
    monkeypatch.delenv("MUTA_CONTAINERIZED", raising=False)
    monkeypatch.setenv("MUTA_SHARE_REQUIRE_HOST", "1")
    monkeypatch.setattr(lan, "_default_route_address", lambda _ipv6: "10.138.0.2")

    assert lan.lan_addresses() == []

    monkeypatch.setenv("MUTA_SHARE_HOST", "192.168.50.20")
    assert lan.lan_addresses() == ["192.168.50.20"]


def test_listener_never_advertises_an_address_absent_from_its_certificate(monkeypatch, tmp_path):
    current = ["192.168.50.10"]
    monkeypatch.setenv("TUTOR_ROOT", str(tmp_path))
    monkeypatch.setenv("MUTA_SHARE_CERT_DIR", str(tmp_path / "certs"))
    monkeypatch.setattr(lan, "lan_addresses", lambda: list(current))
    manager = LanServerManager()
    manager._ensure_certificate()
    current[:] = ["192.168.50.99"]

    assert manager.urls() == ["https://192.168.50.10:8443/chat/"]


def test_address_discovery_only_advertises_the_bound_socket_family(monkeypatch):
    monkeypatch.setenv("MUTA_SHARE_HOST", "fd00::20")
    monkeypatch.delenv("MUTA_SHARE_BIND", raising=False)
    assert lan.lan_addresses() == []

    monkeypatch.setenv("MUTA_SHARE_BIND", "::")
    assert lan.lan_addresses() == ["[fd00::20]"]


def test_address_discovery_prefers_physical_default_route_over_bridges(monkeypatch):
    addresses = {
        "docker0": [SimpleNamespace(family=socket.AF_INET, address="172.17.0.1")],
        "utun4": [SimpleNamespace(family=socket.AF_INET, address="10.7.0.2")],
        "en0": [SimpleNamespace(family=socket.AF_INET, address="192.168.50.20")],
    }
    monkeypatch.delenv("MUTA_SHARE_HOST", raising=False)
    monkeypatch.delenv("MUTA_CONTAINERIZED", raising=False)
    monkeypatch.delenv("MUTA_SHARE_BIND", raising=False)
    monkeypatch.setattr(lan.psutil, "net_if_addrs", lambda: addresses)
    monkeypatch.setattr(lan, "_default_route_address", lambda _ipv6: "192.168.50.20")

    assert lan.lan_addresses() == ["192.168.50.20", "10.7.0.2", "172.17.0.1"]


def test_ipv6_listener_waits_for_its_own_started_server_and_probes_ipv6(monkeypatch, tmp_path):
    started_probe: list[str] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    class Server:
        def __init__(self, _config):
            self.started = False
            self.should_exit = False

        def run(self):
            self.started = True
            while not self.should_exit:
                time.sleep(0.001)

    monkeypatch.setenv("MUTA_SHARE_BIND", "::")
    monkeypatch.setenv("TUTOR_ROOT", str(tmp_path))
    monkeypatch.setattr(lan.uvicorn, "Config", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(lan.uvicorn, "Server", Server)
    monkeypatch.setattr(LanServerManager, "_ensure_certificate", lambda self: None)
    monkeypatch.setattr(
        lan.socket,
        "create_connection",
        lambda target, timeout: (started_probe.append(target[0]), Connection())[1],
    )
    manager = LanServerManager()

    manager.start(object())
    manager.stop()

    assert started_probe == ["::1"]


def test_host_update_rolls_back_capacity_and_listener_when_settings_persistence_fails(
    monkeypatch,
):
    class Service:
        def __init__(self):
            self.state = {"enabled": False, "memory_mode": "competition"}
            self.calls = 0

        def settings(self):
            return dict(self.state)

        def update_settings(self, *, enabled, memory_mode):
            self.calls += 1
            if self.calls == 1:
                raise sqlite3.DatabaseError("disk write failed")
            self.state = {"enabled": enabled, "memory_mode": memory_mode}

    class Manager:
        running = False

        def start(self, _app):
            self.running = True

        def stop(self):
            self.running = False

    service = Service()
    manager = Manager()
    applied = []
    restored = []
    capacity = SimpleNamespace(
        snapshot=lambda: "old-runtime",
        apply=lambda mode: applied.append(mode),
        restore=lambda snapshot, mode: restored.append((snapshot, mode)),
    )
    monkeypatch.setattr(share_routes, "get_sharing_service", lambda: service)
    monkeypatch.setattr(share_routes, "get_lan_manager", lambda: manager)
    monkeypatch.setattr(
        share_routes,
        "get_capacity_controller",
        lambda: capacity,
    )
    request = Request(
        {
            "type": "http",
            "method": "PUT",
            "path": "/v1/share/host",
            "headers": [],
            "app": FastAPI(),
        }
    )

    with pytest.raises(HTTPException) as caught:
        share_routes.update_share_host(
            request,
            ShareHostUpdate(enabled=True, memory_mode="system"),
            SimpleNamespace(),
        )

    assert caught.value.status_code == 409
    assert service.state == {"enabled": False, "memory_mode": "competition"}
    assert manager.running is False
    assert applied == ["system"]
    assert restored == [("old-runtime", "competition")]


def test_host_removal_drains_work_and_erases_every_learner_store(monkeypatch, tmp_path):
    service = SharingService(tmp_path / "share.sqlite3")
    service.update_settings(enabled=True, memory_mode="competition")
    service.signup("Fola", "private classroom password", throttle_key="signup")
    user_id = service.users()[0]["id"]
    service.approve(user_id)
    calls: list[tuple[str, str]] = []

    class _Generations:
        def stop_student(self, subject):
            calls.append(("stop", subject))
            return 1

        def active(self, _subject):
            return []

    class _Store:
        def list_conversations(self, subject):
            assert subject == user_id
            return [{"id": "conversation-one"}, {"id": "conversation-two"}]

        def delete_student(self, subject):
            calls.append(("delete", subject))
            return {"conversations": 2, "orphan_attachments": 1, "resources": 3, "settings": 1}

    class _Reaper:
        def drop(self, conversation):
            calls.append(("snapshot", conversation))
            return True

    class _Twins:
        def path_for(self, subject):
            return tmp_path / f"{subject}.json"

    class _OwnedWork:
        def stop_owner(self, subject):
            calls.append(("aux", subject))
            return True

    class _Resources:
        def stop_owner(self, subject):
            calls.append(("resource", subject))
            return True

    twin_path = _Twins().path_for(user_id)
    twin_path.write_text("private twin")
    monkeypatch.setattr(share_routes, "get_generation_manager", lambda: _Generations())
    monkeypatch.setattr(share_routes, "get_engine", lambda: SimpleNamespace(store=_Store()))
    monkeypatch.setattr(share_routes, "get_reaper", lambda: _Reaper())
    monkeypatch.setattr(share_routes, "get_twin_store", lambda: _Twins())
    monkeypatch.setattr(share_routes, "get_owner_work_manager", lambda: _OwnedWork())
    monkeypatch.setattr(share_routes, "get_resource_service", lambda: _Resources())

    erased = share_routes.erase_share_user(user_id, service)

    assert erased == {
        "conversations": 2,
        "orphan_attachments": 1,
        "resources": 3,
        "settings": 1,
        "learning_twin": 1,
    }
    assert calls == [
        ("stop", user_id),
        ("aux", user_id),
        ("resource", user_id),
        ("snapshot", "conversation-one"),
        ("snapshot", "conversation-two"),
        ("delete", user_id),
    ]
    assert not twin_path.exists()
    assert service.users() == []
