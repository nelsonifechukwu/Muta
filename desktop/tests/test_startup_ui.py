"""Static desktop-shell startup invariants; Rust unit tests cover the parsers themselves."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DESKTOP = ROOT / "desktop"


def test_tauri_paints_the_real_browser_frontend_before_starting_dependencies() -> None:
    config = json.loads((DESKTOP / "src-tauri" / "tauri.conf.json").read_text())
    rust = (DESKTOP / "src-tauri" / "src" / "main.rs").read_text()
    launch = rust[rust.index("fn launch(") : rust.index("fn start_launch(")]

    assert config["build"]["frontendDist"] == "../../ui/dist"
    assert config["app"]["withGlobalTauri"] is True
    assert ".setup(|app|" in rust and "start_launch(app.handle().clone())" in rust
    assert "thread::spawn(move ||" in rust
    assert launch.index("update_startup(&app, 14") < launch.index("install_model_pack(")
    assert launch.index("update_startup(&app, 38") < launch.index("spawn_backend(")
    assert launch.index("if !readiness.ready") < launch.index(".navigate(url)")


def test_every_direct_desktop_build_stages_the_verified_ui_export_first() -> None:
    builder = (ROOT / "scripts" / "build_desktop.py").read_text()
    makefile = (ROOT / "Makefile").read_text()
    assert builder.index('REPO_ROOT / "scripts" / "build_ui_dist.py"') < builder.index(
        'run([npm, "ci"], cwd=DESKTOP)'
    )
    desktop_test = makefile[makefile.index("desktop-test:") : makefile.index(
        "final-package", makefile.index("desktop-test:")
    )]
    assert "scripts/build_ui_dist.py" in desktop_test
    assert desktop_test.index("scripts/build_ui_dist.py") < desktop_test.index("cargo test")
    ui_builder = (ROOT / "scripts" / "build_ui_dist.py").read_text()
    for required_script in (
        "startup.js",
        "syntax.js",
        "parallel-policy.js",
        "release-lifecycle.js",
        "confirm-dialog.js",
    ):
        assert f'"{required_script}"' in ui_builder


def test_desktop_progress_is_monotonic_failure_aware_and_retryable() -> None:
    rust = (DESKTOP / "src-tauri" / "src" / "main.rs").read_text()
    assert "guard.percent.max(percent.min(100))" in rust
    assert "let restarting = guard.ready && !ready" in rust
    assert 'update_startup(&app, 64, "startup.connecting", false, true, true)' in rust
    assert "fn retry_startup" in rust
    assert "compare_exchange(false, true" in rust
    assert "startup_snapshot, retry_startup" in rust
    assert "body.get(\"ready\")" in rust
    assert "checks" in rust and "inference" in rust and "db" in rust
    assert "fn monitor_backend" in rust
    assert '"tauri://localhost/"' in rust
    assert '"http://tauri.localhost/"' in rust
    assert "ShutdownState(AtomicBool)" in rust
    assert "The tutor engine did not become ready" in rust


def test_fallback_startup_surface_uses_only_the_brand_message() -> None:
    html = (DESKTOP / "splash" / "index.html").read_text()
    script = (DESKTOP / "splash" / "splash.js").read_text()
    assert "Muta" in html
    assert "wordmark-u" in html and "<i></i>" in html
    assert "the personal education companion for every student at every level. powered by AI." in html
    assert "Verifying" not in html and "Loading" not in html
    assert "backend-status" not in script
