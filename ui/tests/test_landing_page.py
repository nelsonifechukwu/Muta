"""Small regression checks for the standalone public landing page."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LANDING = ROOT / "landing"


def _contrast(foreground: str, background: str) -> float:
    def luminance(value: str) -> float:
        channels = [int(value[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
            for channel in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _dark_tokens(css: str) -> dict[str, str]:
    block = re.search(r':root\[data-theme="dark"\]\s*\{(?P<body>.*?)\}', css, re.DOTALL)
    assert block
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;", block.group("body")))


def test_landing_bundle_is_self_contained() -> None:
    html = (LANDING / "index.html").read_text()
    css = (LANDING / "styles.css").read_text()

    for asset in ("index.html", "styles.css", "script.js", "theme.js", "og.png"):
        assert (LANDING / asset).is_file()

    sources = re.findall(r'\b(?:src|href)="([^"]+)"', html)
    authored_assets = [value for value in sources if not value.startswith(("#", "/", "http"))]
    assert {value.split("?", 1)[0] for value in authored_assets} == {
        "styles.css", "script.js", "theme.js"
    }
    assert html.count('content="og.png"') == 2
    assert "url(http" not in css


def test_landing_applies_the_persistent_theme_before_css() -> None:
    html = (LANDING / "index.html").read_text()
    css = (LANDING / "styles.css").read_text()
    theme = (LANDING / "theme.js").read_text()

    assert html.index('src="theme.js') < html.index('rel="stylesheet"')
    assert 'meta name="theme-color"' in html
    assert ':root[data-theme="dark"]' in css
    assert 'const STORAGE_KEY = "muta-theme"' in theme
    assert 'global.addEventListener?.("storage"' in theme
    assert 'media.addEventListener("change"' in theme


def test_landing_header_can_switch_the_shared_theme_without_entering_chat() -> None:
    html = (LANDING / "index.html").read_text()
    css = (LANDING / "styles.css").read_text()
    script = (LANDING / "script.js").read_text()

    assert 'id="theme-toggle"' in html
    assert 'type="button" aria-label="Switch to dark mode"' in html
    assert '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">' in html
    assert html.index('id="theme-toggle"') < html.index('class="button button-small button-solid nav-launch"')
    assert "width: 2.75rem;" in css and "height: 2.75rem;" in css
    assert ':root[data-theme="dark"] .theme-icon-moon { display: none; }' in css
    assert "window.MutaTheme?.bindToggle(themeToggle)" in script


def test_landing_dark_palette_meets_text_contrast_baselines() -> None:
    tokens = _dark_tokens((LANDING / "styles.css").read_text())

    assert _contrast(tokens["ink"], tokens["paper"]) >= 4.5
    assert _contrast(tokens["ink-soft"], tokens["paper"]) >= 4.5
    assert _contrast(tokens["terracotta"], tokens["paper"]) >= 4.5
    assert _contrast(tokens["ink"], tokens["card"]) >= 4.5
    assert _contrast("#ffffff", tokens["accent-fill"]) >= 4.5
    assert _contrast("#ffffff", tokens["green-fill"]) >= 4.5


def test_landing_separates_current_product_from_roadmap() -> None:
    html = (LANDING / "index.html").read_text()

    assert html.count("<h1>") == 1
    assert "Inside Muta today" in html
    assert "Being built next" in html
    assert html.count("working now") == 4
    assert "each shipping as it becomes real" in html


def test_landing_is_wired_into_both_deployment_topologies() -> None:
    main = (ROOT / "orchestrator" / "main.py").read_text()
    frontend = (ROOT / "docker" / "frontend.Dockerfile").read_text()
    nginx = (ROOT / "docker" / "nginx.conf.template").read_text()
    exporter = (ROOT / "scripts" / "export_native_linux.py").read_text()

    assert 'app.mount("/", StaticFiles(directory=str(_landing_assets)' in main
    assert "COPY landing/ /usr/share/nginx/html/" in frontend
    assert "COPY ui/ /usr/share/nginx/html/chat/" in frontend
    assert '"/usr/share/nginx/html/chat"' in exporter
    assert "location = /chat" in nginx
    assert "location /chat/" in nginx
    assert "/ui" not in nginx
    assert nginx.count("try_files $uri $uri/ =404;") == 2


def test_every_open_muta_action_targets_the_canonical_chat_route() -> None:
    html = (LANDING / "index.html").read_text()
    chat_html = (ROOT / "ui" / "index.html").read_text()
    script = (LANDING / "script.js").read_text()

    assert html.count('href="/chat/"') == 4
    assert 'href="/ui/"' not in html
    assert 'href: "/ui/"' not in script
    assert script.count('href: "/chat/"') == 2
    # The account gate carries the same canonical home link as the authenticated shell.
    assert chat_html.count('href="/"') == 4
    assert 'class="brand" href="/"' in chat_html
    assert 'class="product-home-link" href="/"' in chat_html
    assert 'class="mobile-home-link" href="/"' in chat_html


def test_landing_has_no_dead_public_repository_links() -> None:
    html = (LANDING / "index.html").read_text()
    assert "github.com/nelsonifechukwu/Muta" not in html


def test_learning_examples_cover_all_tracks_and_pause_during_interaction() -> None:
    html = (LANDING / "index.html").read_text()
    script = (LANDING / "script.js").read_text()
    css = (LANDING / "styles.css").read_text()

    assert html.count("data-learning-slide") == 3
    for category in ("sciences", "humanities", "business"):
        assert f'data-category="{category}"' in html
    assert "data-carousel-toggle" in html
    assert "Humanities (Arts)" in html
    assert "Business (Commercial)" in html
    assert "perspective-choices" in html
    assert "price-slider" in html and "units-slider" in html
    assert html.index('class="lesson-intro"') < html.index("data-carousel-track")
    assert html.count('class="lesson-intro"') == 1
    assert "lesson-copy" not in html
    assert ".lesson-viewport { overflow: hidden; overflow: clip;" in css
    assert "container-type: inline-size" in css
    assert "12.5cqi" in css
    assert "text-wrap: balance" in css
    assert "@media (max-width: 960px)" in css
    assert "AUTO_ADVANCE_MS" in script
    assert 'carouselInteraction?.matches(":hover")' in script
    assert 'carouselInteraction?.addEventListener("pointerleave"' in script
    assert 'learningCarousel.addEventListener("pointerleave"' not in script
    assert "humanitiesPrompt" not in script and "businessPrompt" not in script
    assert ".track-tabs button:focus-visible" in css
    assert "keyboardMode" in script
    assert "prefers-reduced-motion: reduce" in script
    assert "IntersectionObserver" in script
    assert "cancelAnimationFrame" in script
    assert "scrollIntoView" not in script
