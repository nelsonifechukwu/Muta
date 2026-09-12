from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DESKTOP = ROOT / "desktop"
UI = ROOT / "ui"


def test_native_icon_uses_the_foothold_mark_and_platform_mask() -> None:
    native = (DESKTOP / "icon.svg").read_text(encoding="utf-8")
    master = (DESKTOP / "icon-master.svg").read_text(encoding="utf-8")

    foothold = '<rect x="232" y="404" width="48" height="48" rx="4" fill="#E58C69"/>'
    mark = '<path d="M150 164v74c0 76 42 116 106 116s106-40 106-116V112"'
    assert mark in native
    assert foothold in native
    assert '<rect width="512" height="512" rx="112" fill="#1D251F"/>' in native
    assert '<rect width="512" height="512" fill="#1D251F"/>' in master
    assert mark in master
    assert foothold in master
    assert "<circle" not in native + master


def test_browser_icon_uses_the_optical_small_size_foothold() -> None:
    browser = (UI / "muta-icon.svg").read_text(encoding="utf-8")

    assert 'viewBox="0 0 32 32"' in browser
    assert '<path d="M9 10.5v4c0 4.6 2.6 7.1 7 7.1s7-2.5 7-7.1v-7"' in browser
    assert '<rect x="14" y="26" width="4" height="4" rx=".4" fill="#E58C69"/>' in browser
    assert "<circle" not in browser


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
