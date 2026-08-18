from pathlib import Path


def test_ui_exposes_catalog_selector_and_never_sends_a_model_path():
    html = Path("ui/index.html").read_text()
    script = Path("ui/app.js").read_text()

    assert 'id="model-select"' in html
    assert 'fetch("/v1/models")' in script
    assert 'fetch("/v1/models/select"' in script
    assert "JSON.stringify({ model_id: target })" in script
    assert "model_path" not in script


def test_outside_catalog_engine_gets_an_honest_selectable_placeholder():
    script = Path("ui/app.js").read_text()

    assert "const active = models.find((model) => model.id === catalog.active_id);" in script
    assert "if (!active)" in script
    assert "Current engine · outside registry" in script
