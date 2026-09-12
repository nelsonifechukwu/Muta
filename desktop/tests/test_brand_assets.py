from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRANDING = ROOT / "branding"
DESKTOP = ROOT / "desktop"
UI = ROOT / "ui"


def test_native_icon_is_the_approved_book_and_speaking_dot() -> None:
    native = (DESKTOP / "icon.svg").read_text(encoding="utf-8")
    master = (DESKTOP / "icon-master.svg").read_text(encoding="utf-8")
    approved = (BRANDING / "icons" / "muta-app-master.svg").read_text(encoding="utf-8")

    assert master == approved
    for fragment in (
        'rx="112" fill="#1D251F"',
        'fill="#F5F1E7"',
        'fill="#E58C69"',
        'd="M3 0H37Q40 0 40 3V37',
    ):
        assert fragment in native
    assert "open-book mark and speaking square-dot" in native
    assert "foothold" not in native + master


def test_browser_icon_is_the_approved_optical_favicon() -> None:
    browser = UI / "muta-icon.svg"
    approved = BRANDING / "icons" / "muta-favicon-32.svg"

    assert browser.read_bytes() == approved.read_bytes()
    body = browser.read_text(encoding="utf-8")
    assert 'viewBox="0 0 32 32"' in body
    assert 'fill="#1D251F"' in body
    assert 'fill="#F5F1E7"' in body
    assert 'fill="#E58C69"' in body


def test_every_authored_product_surface_uses_supplied_logo_artwork() -> None:
    app = (UI / "index.html").read_text(encoding="utf-8")
    landing = (ROOT / "landing" / "index.html").read_text(encoding="utf-8")
    report = (ROOT / "muta-iq" / "dashboard" / "index.html").read_text(encoding="utf-8")
    splash = (DESKTOP / "splash" / "index.html").read_text(encoding="utf-8")

    assert app.count("brand/muta-wordmark-on-light.svg") == 3
    assert app.count("brand/muta-wordmark-on-dark.svg") == 3
    assert "brand/muta-stacked-on-light.svg" in app
    assert "brand/muta-stacked-on-dark.svg" in app
    assert landing.count("brand/muta-wordmark-on-light.svg") == 2
    assert landing.count("brand/muta-wordmark-on-dark.svg") == 2
    assert "brand/muta-wordmark-on-light.svg" in report
    assert "brand/muta-stacked-on-light.svg" in splash
    assert "muta-wordmark-u" not in app + landing + report + splash


def test_runtime_brand_subset_matches_the_approved_kit() -> None:
    source_pairs = {
        "InstrumentSans-Regular.ttf": BRANDING / "fonts" / "InstrumentSans-Regular.ttf",
        "InstrumentSans-Bold.ttf": BRANDING / "fonts" / "InstrumentSans-Bold.ttf",
        "LibreBaskerville-Regular.ttf": BRANDING / "fonts" / "LibreBaskerville-Regular.ttf",
        "InstrumentSans-OFL.txt": BRANDING / "fonts" / "InstrumentSans-OFL.txt",
        "LibreBaskerville-OFL.txt": BRANDING / "fonts" / "LibreBaskerville-OFL.txt",
        "muta-wordmark-on-light.svg": BRANDING / "logos" / "muta-wordmark-on-light.svg",
        "muta-wordmark-on-dark.svg": BRANDING / "logos" / "muta-wordmark-on-dark.svg",
        "muta-stacked-on-light.svg": BRANDING / "logos" / "muta-stacked-on-light.svg",
        "muta-stacked-on-dark.svg": BRANDING / "logos" / "muta-stacked-on-dark.svg",
        "muta-favicon-32.svg": BRANDING / "icons" / "muta-favicon-32.svg",
    }
    destinations = (
        UI / "brand",
        ROOT / "landing" / "brand",
        DESKTOP / "splash" / "brand",
        ROOT / "muta-iq" / "dashboard" / "brand",
    )
    for destination in destinations:
        assert {path.name for path in destination.iterdir()} == set(source_pairs)
        for name, source in source_pairs.items():
            assert (destination / name).read_bytes() == source.read_bytes()


def test_brand_assets_are_part_of_the_offline_ui_and_entry_pages() -> None:
    builder = (ROOT / "scripts" / "build_ui_dist.py").read_text(encoding="utf-8")
    worker = (ROOT / "scripts" / "manual_desktop_worker.py").read_text(encoding="utf-8")
    app = (UI / "index.html").read_text(encoding="utf-8")
    landing = (ROOT / "landing" / "index.html").read_text(encoding="utf-8")

    assert 'UI_DIRECTORIES = ("brand",)' in builder
    assert '"ui/brand/*"' in worker
    assert '<link rel="icon" href="muta-icon.svg" type="image/svg+xml">' in app
    assert '<link rel="icon" href="brand/muta-favicon-32.svg" type="image/svg+xml">' in landing


def test_product_themes_and_fonts_follow_the_brand_guide() -> None:
    chat_css = (UI / "styles.css").read_text(encoding="utf-8")
    landing_css = (ROOT / "landing" / "styles.css").read_text(encoding="utf-8")
    report_css = (ROOT / "muta-iq" / "dashboard" / "style.css").read_text(encoding="utf-8")

    for css in (chat_css, landing_css, report_css):
        assert 'font-family: "Instrument Sans"' in css
        assert 'font-family: "Libre Baskerville"' in css
        assert "#ad4f31" in css.lower()
    for css in (chat_css, landing_css):
        for color in ("#1d251f", "#171c18", "#f5f1e7", "#faf9f5", "#e58c69"):
            assert color in css.lower()
