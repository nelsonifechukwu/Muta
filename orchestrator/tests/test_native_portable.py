from __future__ import annotations

from fastapi.testclient import TestClient

from orchestrator.gateway.routes import _db_up
from orchestrator.main import app


def test_sqlite_readiness_creates_portable_database(tmp_path):
    dsn = f"sqlite:///{tmp_path / 'muta.sqlite3'}"
    assert _db_up(dsn) is True
    assert (tmp_path / "muta.sqlite3").is_file()


def test_checked_in_ui_is_mounted_without_nginx():
    assert any(getattr(route, "path", None) == "/ui" for route in app.routes)
    client = TestClient(app)
    for path in ("/ui/", "/ui/app.js", "/ui/styles.css", "/ui/worklet.js"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store, max-age=0"
        assert response.headers["x-muta-ui-revision"]
