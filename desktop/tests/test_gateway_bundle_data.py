from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_desktop_gateway_bundles_runtime_pedagogy_data() -> None:
    spec = (ROOT / "desktop" / "pyinstaller" / "muta_gateway.spec").read_text(
        encoding="utf-8"
    )

    assert 'ROOT / "orchestrator" / "pedagogy" / "data"' in spec
    assert '"orchestrator/pedagogy/data"' in spec
    for filename in ("africa_context.json", "override_patterns.json"):
        assert (ROOT / "orchestrator" / "pedagogy" / "data" / filename).is_file()
