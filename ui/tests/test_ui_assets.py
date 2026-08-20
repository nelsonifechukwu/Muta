"""Cascade invariants for the static UI.

There is no JS runtime in this repo's test stack, but the rules that decide whether an
element is on screen at all are checkable from the stylesheet — and getting one wrong is
how a full-screen drop hint ended up covering the whole app on page load.
"""

from __future__ import annotations

import re
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
HTML = (UI / "index.html").read_text()
CSS = (UI / "styles.css").read_text()


def _hidden_elements() -> list[tuple[str, str]]:
    """(id, class list) for every element carrying the boolean `hidden` attribute.

    The `(?<![-\\w])hidden(?![-\\w=])` guard matches the standalone HTML attribute while
    excluding `aria-hidden` (decorative SVGs legitimately carry it, and the display-override
    invariant below does not apply to ARIA)."""
    out: list[tuple[str, str]] = []
    for tag in re.findall(r"<[a-zA-Z][^>]*(?<![-\w])hidden(?![-\w=])[^>]*>", HTML):
        el_id = re.search(r'id="([^"]+)"', tag)
        classes = re.search(r'class="([^"]+)"', tag)
        out.append((el_id.group(1) if el_id else "", classes.group(1) if classes else ""))
    return out


def _blocks(selector: str) -> list[str]:
    """Declaration bodies for rules whose selector is exactly `selector`."""
    return re.findall(re.escape(selector) + r"\s*\{([^}]*)\}", CSS)


def test_the_html_actually_uses_the_hidden_attribute():
    # Guards the guard: if the markup stops using `hidden`, the invariant below is vacuous.
    assert _hidden_elements()


def test_hidden_elements_are_not_re_shown_by_an_author_display_rule():
    """`[hidden] { display: none }` lives in the UA stylesheet, and ANY author `display:`
    declaration outranks it (author origin beats UA, specificity never enters into it).
    An element that declares its own display therefore needs an explicit override, or it
    renders while the markup and every reader believe it is hidden."""
    for el_id, classes in _hidden_elements():
        selectors = ([f"#{el_id}"] if el_id else []) + [f".{c}" for c in classes.split()]
        declares_display = any(
            re.search(r"\bdisplay\s*:", body) for s in selectors for body in _blocks(s)
        )
        if not declares_display:
            continue  # UA rule applies untouched — nothing to override
        assert any(_blocks(f"{s}[hidden]") for s in selectors), (
            f"{el_id or classes}: an author `display:` rule overrides the UA [hidden] rule, "
            f"so this element renders despite its hidden attribute. Add "
            f"`{selectors[0]}[hidden] {{ display: none; }}`."
        )


def test_the_drop_overlay_can_never_swallow_clicks():
    """The overlay is a hint, not a target: fixed + inset 0 + a z-index means that while it
    is up it hit-tests over the entire app, so a stuck overlay freezes every control."""
    body = "".join(_blocks("#drop-overlay"))
    assert body, "#drop-overlay rule missing"
    assert re.search(r"pointer-events\s*:\s*none", body), (
        "#drop-overlay must be pointer-events:none — otherwise it intercepts every click "
        "in the app while visible, and it perturbs the very drag events it reacts to"
    )


def test_streaming_only_follows_while_the_reader_is_near_the_bottom():
    """Every token render calls scrollToBottom, so that helper must carry the pause guard.

    The scroll listener is the resume path: without it, one upward scroll would disable
    following for the rest of the page lifetime even after the reader returned to the tail.
    """
    js = (UI / "app.js").read_text()
    helper = re.search(
        r"function scrollToBottom\([^)]*\)\s*\{(?P<body>.*?)\n\}", js, re.DOTALL
    )
    assert helper, "scrollToBottom helper missing"
    assert "!autoFollow" in helper.group("body")
    assert 'chatScroller.addEventListener("scroll"' in js
    assert "autoFollow = nearChatBottom()" in js


def test_chat_generation_is_server_owned_and_recovered_after_reload():
    js = (UI / "app.js").read_text()
    assert 'fetch("/v1/chat/generations"' in js, "UI must start a durable gateway job"
    assert "/stream?after=${job.framesSeen}" in js, "reconnect must resume from a frame offset"
    assert "await recoverGenerations()" in js, "startup must discover generations already running"
    assert "const generationJobs = new Map()" in js, "generation state must be per job, not global"
    assert 'fetch("/v1/chat/stream"' not in js, "a page-owned POST stream stops on refresh"


def test_switching_conversations_detaches_rendering_without_stopping_the_job():
    js = (UI / "app.js").read_text()
    load = re.search(
        r"async function loadConversation\(cid\)\s*\{(?P<body>.*?)\n\}", js, re.DOTALL
    )
    assert load
    body = load.group("body")
    assert "leaving.handle = null" in body
    assert "stopGeneration" not in body


def test_settings_exposes_a_persisted_parallel_chat_switch():
    js = (UI / "app.js").read_text()
    assert 'id="settings-modal"' in HTML
    assert 'id="setting-parallel-chats"' in HTML
    assert 'role="switch"' in HTML
    assert 'fetch("/v1/settings"' in js
    assert "allow_parallel_chats: enabled" in js
    assert "!allowParallelChats && generationJobs.size" in js
