from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DESKTOP = ROOT / "desktop"
UI = ROOT / "ui"


def test_native_and_browser_icons_share_the_revised_square_signature() -> None:
    native = (DESKTOP / "icon.svg").read_text(encoding="utf-8")
    browser = (UI / "muta-icon.svg").read_text(encoding="utf-8")

    assert native == browser
    assert "<circle" not in native
    assert '<path d="M286 222h50v78' in native
    assert '<rect x="354" y="373" width="24" height="24" rx="2" fill="#e58c69"/>' in native


def test_every_authored_product_wordmark_places_the_mark_below_the_u() -> None:
    app = (UI / "index.html").read_text(encoding="utf-8")
    landing = (ROOT / "landing" / "index.html").read_text(encoding="utf-8")
    report = (ROOT / "muta-iq" / "dashboard" / "index.html").read_text(encoding="utf-8")

    signature = 'M<span class="muta-wordmark-u">u<i></i></span>ta.'
    assert signature in app
    assert landing.count(signature) == 2
    assert signature in report
    assert "Muta<span aria-hidden=\"true\">.</span>" not in landing


def test_browser_icon_is_part_of_the_offline_ui_and_both_entry_pages_use_it() -> None:
    builder = (ROOT / "scripts" / "build_ui_dist.py").read_text(encoding="utf-8")
    app = (UI / "index.html").read_text(encoding="utf-8")
    landing = (ROOT / "landing" / "index.html").read_text(encoding="utf-8")

    assert '"muta-icon.svg"' in builder
    assert '<link rel="icon" href="muta-icon.svg" type="image/svg+xml">' in app
    assert '<link rel="icon" href="/chat/muta-icon.svg" type="image/svg+xml">' in landing
