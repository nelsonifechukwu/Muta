from pathlib import Path


def test_ui_exposes_catalog_selector_and_never_sends_a_model_path():
    html = Path("ui/index.html").read_text()
    script = Path("ui/app.js").read_text()

    assert 'id="model-trigger"' in html
    assert 'id="model-menu"' in html
    assert 'fetch("/v1/models")' in script
    assert 'fetch("/v1/models/select"' in script
    assert "JSON.stringify({ model_id: target })" in script
    assert "model_path" not in script


def test_outside_catalog_engine_gets_an_honest_selectable_placeholder():
    script = Path("ui/app.js").read_text()
    i18n = Path("ui/i18n.js").read_text()

    assert "const active = models.find((model) => model.id === catalog.active_id);" in script
    assert 'catalog.active_id ? t("model.currentLocal") : t("model.choose")' in script
    assert 't("model.outsideRegistry")' in script
    assert '"model.outsideRegistry": "Choose an installed model."' in i18n


def test_loopback_session_can_replace_the_port_scoped_browser_identity():
    script = Path("ui/app.js").read_text()

    assert "let studentId = (() =>" in script
    assert "studentId = session.student_id || studentId" in script
    assert 'localStorage.setItem("muta-student", studentId)' in script
    assert "get studentId() { return studentId; }" in script
