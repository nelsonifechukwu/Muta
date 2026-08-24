"""Consent, offline retry, erasure, and operator-boundary tests for fleet sync."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from orchestrator import product_analytics as analytics
from orchestrator.gateway import product_analytics as routes


def service(tmp_path, *, configured=True):
    config = analytics.FleetConfig(
        url="https://fleet.example" if configured else None,
        ingest_key="write-only" if configured else None,
        sync_interval_s=60,
        timeout_s=1,
    )
    state = analytics.ProductAnalyticsState(tmp_path / "analytics.sqlite3")
    return analytics.ProductAnalytics(state=state, config=config)


def response(status=200):
    return SimpleNamespace(
        status_code=status,
        raise_for_status=lambda: None,
    )


def test_unknown_and_declined_consent_never_send(monkeypatch, tmp_path):
    product = service(tmp_path)
    monkeypatch.setattr(
        analytics.httpx,
        "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected sync")),
    )

    assert product.status(manageable=True)["prompt_required"] is True
    assert product.sync_once() is False
    product.set_consent(False)
    assert product.sync_once() is False

    product.state.close()
    reopened = analytics.ProductAnalyticsState(tmp_path / "analytics.sqlite3")
    assert reopened.snapshot()["consent"] == "declined"
    reopened.close()


def test_granted_sync_is_minimal_and_updates_delivery_receipt(monkeypatch, tmp_path):
    product = service(tmp_path)
    product.set_consent(True)
    sent = {}

    def fake_post(url, *, headers, json, timeout):
        sent.update(url=url, headers=headers, json=json, timeout=timeout)
        return response()

    monkeypatch.setattr(analytics.httpx, "post", fake_post)
    assert product.sync_once() is True
    assert sent["url"] == "https://fleet.example/v1/heartbeat"
    assert sent["headers"]["Authorization"] == "Bearer write-only"
    assert {
        "installation_id", "app_version", "build_id", "platform", "architecture",
        "active_at", "sent_at", "local_user_count",
        "active_local_user_count",
    } == set(sent["json"])
    forbidden = {"hostname", "username", "email", "conversation", "latitude", "longitude", "ip"}
    assert forbidden.isdisjoint(sent["json"])
    assert product.state.snapshot()["last_synced_at"] is not None


def test_network_failure_is_a_nonfatal_retry(monkeypatch, tmp_path):
    product = service(tmp_path)
    product.set_consent(True)

    def offline(*_args, **_kwargs):
        raise analytics.httpx.ConnectError("offline")

    monkeypatch.setattr(analytics.httpx, "post", offline)
    assert product.sync_once() is False
    assert product.state.snapshot()["last_synced_at"] is None


def test_revocation_deletes_cloud_row_and_rotates_identity(monkeypatch, tmp_path):
    product = service(tmp_path)
    product.set_consent(True)
    old_id = product.state.snapshot()["installation_id"]
    product.set_consent(False)
    deleted = []
    monkeypatch.setattr(
        analytics.httpx,
        "delete",
        lambda url, **_kwargs: (deleted.append(url), response())[1],
    )

    assert product.state.snapshot()["deletion_pending"] is True
    assert product.sync_once() is True
    row = product.state.snapshot()
    assert deleted == [f"https://fleet.example/v1/installations/{old_id}"]
    assert row["deletion_pending"] is False
    assert row["installation_id"] != old_id
    assert row["consent"] == "declined"


def test_pending_erasure_survives_repeat_decline_and_regrant(tmp_path):
    product = service(tmp_path)
    product.set_consent(True)
    old_id = product.state.snapshot()["installation_id"]
    product.set_consent(False)
    product.set_consent(False)
    assert product.state.snapshot()["deletion_pending"] is True
    product.set_consent(True)
    row = product.state.snapshot()
    assert row["deletion_pending"] is True
    assert row["installation_id"] == old_id


def test_touch_prunes_and_caps_activity_without_needing_a_heartbeat(monkeypatch, tmp_path):
    product = service(tmp_path)
    now = datetime.now(timezone.utc)
    product._active_subjects = {
        f"old-{index}": now - timedelta(hours=1) for index in range(5000)
    }
    monkeypatch.setattr(analytics, "_now", lambda: now)
    product.touch("current")
    assert len(product._active_subjects) == 1


def test_cleartext_collector_is_loopback_only(monkeypatch):
    monkeypatch.setenv("MUTA_FLEET_URL", "http://fleet.example")
    monkeypatch.setenv("MUTA_FLEET_INGEST_KEY", "write-only")
    try:
        analytics.FleetConfig.from_env()
    except ValueError as exc:
        assert "HTTPS" in str(exc)
    else:
        raise AssertionError("cleartext non-loopback collector was accepted")

    monkeypatch.setenv("MUTA_FLEET_URL", "http://127.0.0.1:8088/ingest")
    assert analytics.FleetConfig.from_env().configured is True


def test_consent_route_is_local_operator_only(monkeypatch, tmp_path):
    product = service(tmp_path)
    monkeypatch.setattr(routes, "get_product_analytics", lambda: product)
    app = FastAPI()
    app.include_router(routes.router, prefix="/v1")
    local = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 51001))
    remote = TestClient(app, base_url="https://muta.test", client=("192.0.2.10", 51002))

    assert local.get("/v1/product-analytics").status_code == 200
    updated = local.put("/v1/product-analytics", json={"allowed": True})
    assert updated.status_code == 200
    assert updated.json()["consent"] == "granted"
    assert remote.get("/v1/product-analytics").status_code == 403


def test_ui_discloses_location_and_never_requests_browser_geolocation():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    html = (root / "ui/index.html").read_text()
    script = (root / "ui/product-analytics.js").read_text()
    assert "approximate city-level" in html
    assert "Never sends conversations" in html
    assert "Turning it off also asks the server to delete" in html
    assert "navigator.geolocation" not in script
    assert "/v1/product-analytics" in script
