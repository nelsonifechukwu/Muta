from __future__ import annotations

from fastapi.testclient import TestClient

from orchestrator.gateway.routes import _db_up
from orchestrator.main import app


def test_sqlite_readiness_creates_portable_database(tmp_path):
    dsn = f"sqlite:///{tmp_path / 'muta.sqlite3'}"
    assert _db_up(dsn) is True
    assert (tmp_path / "muta.sqlite3").is_file()


def test_checked_in_ui_is_mounted_without_nginx():
    assert any(getattr(route, "path", None) == "/chat" for route in app.routes)
    client = TestClient(app)
    chat_root = client.get("/chat", follow_redirects=False)
    assert chat_root.status_code == 308
    assert chat_root.headers["location"] == "/chat/"
    chat_bookmark = client.get("/chat?chat=abc", follow_redirects=False)
    assert chat_bookmark.headers["location"] == "/chat/?chat=abc"
    for path in ("/chat/", "/chat/app.js", "/chat/styles.css", "/chat/worklet.js"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store, max-age=0"
        assert response.headers["x-muta-ui-revision"]


def test_legacy_ui_paths_redirect_to_chat_without_duplicate_assets():
    client = TestClient(app)
    expected = {
        "/ui": "/chat/",
        "/ui/": "/chat/",
        "/ui/app.js": "/chat/app.js",
        "/ui/?chat=abc": "/chat/?chat=abc",
        "/ui/app.js?v=20260821": "/chat/app.js?v=20260821",
    }
    for source, target in expected.items():
        response = client.get(source, follow_redirects=False)
        assert response.status_code == 308
        assert response.headers["location"] == target


def test_checked_in_landing_page_is_served_at_root_without_nginx():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "A tutor that asks" in response.text
    assert client.get("/styles.css").status_code == 200
    assert client.get("/script.js").status_code == 200
    assert client.get("/og.png").status_code == 200
