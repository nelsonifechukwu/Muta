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
        'rx="112" fill="#181715"',
        'fill="#F3F0EA"',
        'fill="#FF8A66"',
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
    assert 'fill="#181715"' in body
    assert 'fill="#F3F0EA"' in body
    assert 'fill="#FF8A66"' in body


def test_every_authored_product_surface_uses_supplied_logo_artwork() -> None:
    app = (UI / "index.html").read_text(encoding="utf-8")
    landing = (ROOT / "landing" / "index.html").read_text(encoding="utf-8")
    report = (ROOT / "muta-iq" / "dashboard" / "index.html").read_text(encoding="utf-8")
    splash = (DESKTOP / "splash" / "index.html").read_text(encoding="utf-8")

    assert app.count("brand/muta-wordmark-on-light.svg") == 2
    assert app.count("brand/muta-wordmark-on-dark.svg") == 2
    assert "brand/muta-symbol-on-light.svg" in app
    assert "brand/muta-symbol-on-dark.svg" in app
    assert "brand/muta-stacked-on-light.svg" in app
    assert "brand/muta-stacked-on-dark.svg" in app
    assert landing.count("brand/muta-wordmark-on-light.svg") == 2
    assert landing.count("brand/muta-wordmark-on-dark.svg") == 2
    assert "brand/muta-wordmark-on-light.svg" in report
    assert "brand/muta-stacked-on-light.svg" in splash
    assert "muta-wordmark-u" not in app + landing + report + splash


def test_runtime_brand_subset_matches_the_approved_kit() -> None:
    # v5 product surfaces render live text in bundled Onest (ui/fonts, landing/fonts); the
    # brand kit's Instrument Sans / Libre Baskerville stay in branding/fonts for regenerating
    # outlined artwork only, so they are not shipped in the runtime brand subset.
    source_pairs = {
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
        expected_names = set(source_pairs)
        if destination == UI / "brand":
            expected_names |= {"muta-symbol-on-light.svg", "muta-symbol-on-dark.svg"}
        assert {path.name for path in destination.iterdir()} == expected_names
        for name, source in source_pairs.items():
            assert (destination / name).read_bytes() == source.read_bytes()
    for name in ("muta-symbol-on-light.svg", "muta-symbol-on-dark.svg"):
        assert (UI / "brand" / name).read_bytes() == (BRANDING / "logos" / name).read_bytes()


def test_brand_assets_are_part_of_the_offline_ui_and_entry_pages() -> None:
    builder = (ROOT / "scripts" / "build_ui_dist.py").read_text(encoding="utf-8")
    worker = (ROOT / "scripts" / "manual_desktop_worker.py").read_text(encoding="utf-8")
    app = (UI / "index.html").read_text(encoding="utf-8")
    landing = (ROOT / "landing" / "index.html").read_text(encoding="utf-8")

    assert 'UI_DIRECTORIES = ("brand", "fonts", "units", "courses")' in builder
    assert '"ui/brand/*"' in worker
    assert '<link rel="icon" href="muta-icon.svg" type="image/svg+xml">' in app
    assert '<link rel="icon" href="brand/muta-favicon-32.svg" type="image/svg+xml">' in landing


def test_brand_artwork_sits_on_the_established_neutral_product_theme() -> None:
    chat_css = (UI / "styles.css").read_text(encoding="utf-8")
    landing_css = (ROOT / "landing" / "styles.css").read_text(encoding="utf-8")
    report_css = (ROOT / "muta-iq" / "dashboard" / "style.css").read_text(encoding="utf-8")

    # v5 "Bright" logo colourway: Muta coral replaced terracotta (docs/design/muta-v5-bright.md).
    for css in (chat_css, landing_css, report_css):
        assert "#d9573a" in css.lower()
        assert 'font-family: "Instrument Sans"' not in css
        assert 'font-family: "Libre Baskerville"' not in css

    # The landing page shares the app's v5 palette: warm-graphite dark surfaces and Muta coral.
    for color in ("#181715", "#1d1c1a", "#242220", "#f3f0ea", "#ff8a66", "#3fcfb4"):
        assert color in landing_css.lower()
    # The v5 app shell is the bright, mint-led theme (docs/design/muta-v5-bright.md) and carries
    # the logo's coral pair as its brand token.
    for color in ("#181715", "#1d1c1a", "#242220", "#f3f0ea", "#3fcfb4", "#d9573a", "#ff8a66"):
        assert color in chat_css.lower()
    for css in (chat_css, landing_css):
        for green_wash in ("--bg: #1d251f", "--paper: #1d251f", "--card: #273129"):
            assert green_wash not in css.lower()

    for color in ("#ffffff", "#faf9f7", "#f4f2ee", "#282828"):
        assert color in report_css.lower()
