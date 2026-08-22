"""Small regression checks for the standalone public landing page."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LANDING = ROOT / "landing"


def test_landing_bundle_is_self_contained() -> None:
    html = (LANDING / "index.html").read_text()
    css = (LANDING / "styles.css").read_text()

    for asset in ("index.html", "styles.css", "script.js", "og.png"):
        assert (LANDING / asset).is_file()

    sources = re.findall(r'\b(?:src|href)="([^"]+)"', html)
    authored_assets = [value for value in sources if not value.startswith(("#", "/", "http"))]
    assert set(authored_assets) == {"styles.css", "script.js"}
    assert html.count('content="og.png"') == 2
    assert "url(http" not in css


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
    assert chat_html.count('href="/"') == 3
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
    assert html.index('class="lesson-intro"') < html.index('data-carousel-track')
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
    assert 'prefers-reduced-motion: reduce' in script
    assert "IntersectionObserver" in script
    assert "cancelAnimationFrame" in script
    assert "scrollIntoView" not in script
