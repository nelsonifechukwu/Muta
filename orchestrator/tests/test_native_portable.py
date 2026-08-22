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

    frame = client.get("/chat/viz-frame.html")
    assert frame.status_code == 200
    assert frame.headers["x-frame-options"] == "SAMEORIGIN"
    csp = frame.headers["content-security-policy"]
    assert "default-src 'none'" in csp
    assert "script-src 'self'" in csp
    assert "style-src 'self'" in csp
    assert "connect-src 'none'" in csp
    assert "frame-ancestors 'self'" in csp
    assert "ws:" not in csp and "blob:" not in csp


def test_removed_ui_paths_and_missing_chat_assets_return_404():
    client = TestClient(app)
    for path in ("/ui", "/ui/", "/ui/app.js", "/chat/missing.js", "/missing"):
        assert client.get(path, follow_redirects=False).status_code == 404


def test_checked_in_landing_page_is_served_at_root_without_nginx():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "A tutor that asks" in response.text
    assert client.get("/styles.css").status_code == 200
    assert client.get("/script.js").status_code == 200
    assert client.get("/og.png").status_code == 200
