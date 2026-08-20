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
        r"async function loadConversation\(cid,[^)]*\)\s*\{(?P<body>.*?)\n\}", js, re.DOTALL
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


def test_selected_conversation_lives_in_the_url_and_restores_on_startup():
    js = (UI / "app.js").read_text()
    assert 'searchParams.get("chat")' in js
    assert 'url.searchParams.set("chat", cid)' in js
    assert "history[mode === \"replace\" ? \"replaceState\" : \"pushState\"]" in js
    assert "const selected = conversationFromLocation()" in js
    assert 'window.addEventListener("popstate"' in js
    assert 'setConversationLocation(conversationId, { mode: "replace" })' in js


def test_new_chat_start_can_be_recovered_if_the_page_refreshes_immediately():
    js = (UI / "app.js").read_text()
    assert "client_request_id: clientRequestId" in js
    assert "setPendingLocation(clientRequestId)" in js
    assert "/v1/chat/generations?client_request_id=" in js
    assert "recoverPendingGeneration(pending)" in js
    assert 'if (job.terminal)' in js and 'job.error = ev.error' in js
    assert "if (startRejected" in js


def test_only_the_latest_conversation_navigation_can_commit():
    js = (UI / "app.js").read_text()
    assert "const requestedNavigation = ++navigationVersion" in js
    assert js.count("requestedNavigation !== navigationVersion") >= 2
    assert "const targetJobBeforeLoad = jobForConversation(cid)" in js
    assert "const restoring = targetJobBeforeLoad || jobForConversation(cid)" in js
    assert "currentViewId = newViewId()" in js
    assert "returnedToConversation" in js
    assert "pendingConversationLoad === started.conversation_id" in js
    assert js.index("if (returnedToConversation) void loadConversation") < js.index(
        "void followGeneration(job)", js.index("if (returnedToConversation)")
    )


def test_settings_escape_is_consumed_before_the_stop_shortcut():
    js = (UI / "app.js").read_text()
    assert "event.stopPropagation()" in js
    assert 'if (!settingsModal.hidden) return;' in js


def test_voice_status_uses_the_same_guarded_auto_follow_policy():
    audio = (UI / "audio.js").read_text()
    app = (UI / "app.js").read_text()
    assert "chat.scrollIfFollowing()" in audio
    assert "scrollTop = 1e9" not in audio
    assert "chat.setVoiceActive(true)" in audio
    assert "if (voiceModeActive)" in app


def test_student_identity_boots_on_plain_http_lan_origins():
    js = (UI / "app.js").read_text()
    assert 'typeof crypto.randomUUID === "function"' in js
    assert "crypto.getRandomValues(new Uint8Array(16))" in js
    assert "Math.random" not in js


def test_math_is_protected_before_markdown_and_loaded_before_the_chat_app():
    js = (UI / "app.js").read_text()
    math = (UI / "math.js").read_text()
    assert "extractMath(markdown)" in math
    assert "marked.parse(protectedSource)" in math
    markdown_at = math.index("marked.parse(protectedSource)")
    restore_at = math.index("restoreMath(root, expressions, placeholderOpen);")
    katex_at = math.index("global.katex.render(input.tex", restore_at)
    assert markdown_at < restore_at < katex_at
    assert 'slot.closest("pre, code, script, style, textarea, noscript, option, title")' in math
    assert HTML.index('<script src="math.js"></script>') < HTML.index(
        '<script src="app.js"></script>'
    )
    assert "MutaMath.render(el, text)" in js
    assert 'last.matches(".katex, .katex-display")' in js


def test_display_math_cannot_widen_the_conversation_column():
    display = "".join(_blocks(".prose .katex-display"))
    assert re.search(r"max-width\s*:\s*100%", display)
    assert re.search(r"overflow-x\s*:\s*auto", display)
    inline = "".join(_blocks(".prose .math-source.inline-math"))
    assert re.search(r"max-width\s*:\s*100%", inline)
    assert re.search(r"overflow-x\s*:\s*auto", inline)
