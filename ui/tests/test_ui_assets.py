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
I18N = (UI / "i18n.js").read_text()
NGINX = (UI.parent / "docker" / "nginx.conf.template").read_text()


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


def test_chat_shell_has_localized_routes_back_to_the_landing_page():
    assert re.search(r'<a class="brand" href="/"[^>]*data-i18n-aria-label="nav\.home"', HTML)
    assert re.search(r'<a class="product-home-link" href="/">', HTML)
    assert re.search(r'<a class="mobile-home-link" href="/"', HTML)
    assert 'data-i18n="nav.aboutMuta"' in HTML
    assert '"nav.home": "Muta home"' in I18N
    assert '"nav.aboutMuta": "About Muta"' in I18N
    assert "Ask about any subject" in HTML
    assert "maths or science question" not in HTML

    for token in ("#faf9f5", "#f1ede3", "#302d24", "#dfddd4", "#ad4f31"):
        assert token in CSS
    assert ".mobile-home-link { display: inline-flex; }" in CSS


def test_closed_mobile_drawer_does_not_expose_offscreen_navigation_to_the_keyboard():
    js = (UI / "app.js").read_text()
    assert 'window.matchMedia("(max-width: 720px)")' in js
    assert 'sidebarEl.toggleAttribute("inert", mobileSidebar.matches && !drawerOpen)' in js
    assert 'mainEl.toggleAttribute("inert", drawerOpen)' in js
    assert 'appEl?.classList.contains("sidebar-open")' in js
    assert 'mobileSidebar.addEventListener?.("change", () => setDrawer(false))' in js


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
    helper = re.search(r"function scrollToBottom\([^)]*\)\s*\{(?P<body>.*?)\n\}", js, re.DOTALL)
    assert helper, "scrollToBottom helper missing"
    assert "!autoFollow" in helper.group("body")
    assert 'chatScroller.addEventListener("scroll"' in js
    assert "current < lastChatScrollTop" in js
    assert "pointerScrollingChat && current !== lastChatScrollTop" in js
    assert "const studentMovedChat = manualScrollIntent" in js
    assert "!viewportResizeActive || studentMovedChat" in js
    assert "!viewportResizeActive || manualScrollDirection > 0" in js
    assert 'chatScroller.addEventListener("wheel"' in js
    assert "noteManualScrollIntent(Math.sign(event.deltaY))" in js
    assert "event.deltaY < 0" in js
    assert 'chatScroller.addEventListener("touchmove"' in js
    assert "!autoFollow && manualScrollDirection > 0 && nearChatBottom()" in js
    assert "}, 480)" in js
    assert "manualScrollDirection = 0" in js
    assert "lastChatScrollTop = current" in js


def test_only_the_chat_pane_scrolls_while_the_composer_stays_docked():
    """Long streamed content must not turn the body or app shell into a scroll container.

    A flex column also needs explicit zero minimum heights: otherwise its content-derived
    minimum can grow the entire document and carry the composer upward with it.
    """
    document = "".join(_blocks("html, body"))
    app = "".join(_blocks("#app"))
    main = "".join(_blocks("#main"))
    chat = "".join(_blocks("#chat-scroll"))
    composer = "".join(_blocks("#composer-wrap"))

    assert re.search(r"overflow\s*:\s*hidden", document)
    assert re.search(r"overflow\s*:\s*hidden", app)
    assert re.search(r"min-height\s*:\s*0", main)
    assert re.search(r"overflow\s*:\s*hidden", main)
    assert re.search(r"min-height\s*:\s*0", chat)
    assert re.search(r"overflow-y\s*:\s*auto", chat)
    assert re.search(r"flex\s*:\s*0\s+0\s+auto", composer)
    assert "calc(100% - 58px)" in composer


def test_mobile_keyboard_and_large_composer_regions_remain_bounded():
    viewport = re.search(r'<meta name="viewport" content="([^"]+)">', HTML)
    assert viewport and "interactive-widget=resizes-content" in viewport.group(1)

    js = (UI / "app.js").read_text()
    assert "viewport?.height || window.innerHeight" in js
    assert "viewport?.offsetTop || 0" in js
    assert 'style.setProperty("--app-height"' in js
    assert 'style.setProperty("--app-top"' in js
    assert 'style.setProperty("--composer-region-max"' in js
    assert 'window.visualViewport?.addEventListener("resize"' in js
    assert 'window.visualViewport?.addEventListener("scroll"' in js
    assert 'root.classList.toggle("compact-height"' in js
    assert "viewportResizeActive = true" in js
    assert "if (preserveFollow) scrollToBottom({ force: true })" in js
    assert "}, 320)" in js

    # Safari may pan the visual viewport instead of leaving it at layout y=0. Every fixed
    # surface must share the same visible origin/height as #app, or the hamburger/sidebar
    # and overlays straddle browser chrome or the on-screen keyboard.
    menu_toggle = "".join(_blocks(".menu-toggle"))
    backdrop = "".join(_blocks("#sidebar-backdrop"))
    sidebar = "".join(_blocks("#sidebar"))
    model_menu = "".join(_blocks(".model-menu"))
    mobile_header = "".join(_blocks(".chat-header"))
    drop_overlay = "".join(_blocks("#drop-overlay"))
    settings_modal = "".join(_blocks(".settings-modal"))
    toast = "".join(_blocks("#toast"))
    assert "var(--app-top" in menu_toggle
    for surface in (backdrop, sidebar, model_menu, drop_overlay, settings_modal):
        assert "var(--app-top" in surface
        assert "var(--app-height" in surface
    assert "var(--app-top" in toast and "var(--app-height" in toast
    assert "backdrop-filter: none" in mobile_header

    wrap = "".join(_blocks("#composer-wrap"))
    queue = "".join(_blocks("#queue"))
    chips = "".join(_blocks("#attachment-chips"))
    composer = "".join(_blocks("#composer"))
    assert re.search(r"max-height\s*:", wrap)
    assert re.search(r"overflow\s*:\s*hidden", wrap)
    assert re.search(r"max-height\s*:", composer)
    assert re.search(r"overflow\s*:\s*hidden", composer)
    for region in (queue, chips):
        assert re.search(r"max-height\s*:", region)
        assert re.search(r"overflow-y\s*:\s*auto", region)

    compact = "".join(_blocks(".compact-height #composer-wrap"))
    compact_composer = "".join(_blocks(".compact-height #composer"))
    assert "calc(100% - 58px)" in compact
    assert re.search(r"min-height\s*:\s*4\.6rem", compact_composer)


def test_chat_generation_is_server_owned_and_recovered_after_reload():
    js = (UI / "app.js").read_text()
    assert 'fetch("/v1/chat/generations"' in js, "UI must start a durable gateway job"
    assert "/stream?after=${job.framesSeen}" in js, "reconnect must resume from a frame offset"
    assert "await recoverGenerations()" in js, "startup must discover generations already running"
    assert "const generationJobs = new Map()" in js, "generation state must be per job, not global"
    assert 'fetch("/v1/chat/stream"' not in js, "a page-owned POST stream stops on refresh"


def test_selected_locale_is_generation_metadata_not_a_user_message_prefix():
    js = (UI / "app.js").read_text()
    audio = (UI / "audio.js").read_text()
    start = js.index('fetch("/v1/chat/generations"')
    request = js[start : js.index("if (!res.ok)", start)]
    assert "message," in request
    assert "language: window.MutaI18n.responseLanguage" in request
    assert "composeOutgoingMessage" not in request
    assert "language: window.MutaI18n.responseLanguage" in audio
    assert '{ type: "language", language: window.MutaI18n.responseLanguage }' in audio


def test_refresh_retries_recovery_and_keeps_same_chat_followups():
    js = (UI / "app.js").read_text()
    assert "async function recoverGenerations({ attempts = 6" in js
    assert "await recoverGenerations({ attempts: 4, delayMs: 400 })" in js
    assert "reply is already running" in js
    assert 't("reply.earlierRunning")' in js
    assert "The earlier reply is still running. This message is queued" in I18N
    assert 'const MESSAGE_QUEUE_STORAGE_KEY = "muta-message-queue"' in js
    assert "persistMessageQueue()" in js and "restoreMessageQueue()" in js
    assert "item.cid === conversationId" in js
    assert "pendingStartsFor(selected)" in js
    assert "fallbackConversation: startedIn" in js
    assert "identityReady = true" in js and "while (!(await ensureAuth()))" in js
    assert "!identityReady ||" in js
    assert 't("reply.previousStarting")' in js
    assert "Starting your previous message — this draft is still here." in I18N
    assert js.index("startingConversations.has(startKeyFor(conversationId))") < js.index(
        'inputEl.value = ""', js.index("function send(")
    )
    assert "expectedViewStillVisible" in js and "returnedToConversation" in js
    assert 't("reply.earlierFinishing")' in js
    assert "This message remains queued until it can send." in I18N
    assert "setTimeout(() => drainQueue(startedIn), 0)" in js
    assert "retryUnavailable: true" in js


def test_refresh_only_clears_selected_chat_after_a_definitive_not_found():
    js = (UI / "app.js").read_text()
    load = js[
        js.index("async function loadConversation(") : js.index("/** Re-render one in-flight")
    ]
    assert "if (!r)" in load and "if (r.status === 404)" in load
    assert load.index("if (!r)") < load.index("if (r.status === 404)")
    unavailable = load[load.index("if (!r)") : load.index("if (r.status === 404)")]
    assert "setConversationLocation" not in unavailable
    assert "scheduleConversationRetry(cid)" in unavailable
    assert "if (loaded === false) newChat" in js
    assert "if (!loaded) newChat" not in js
    boot = js[js.index("async function bootChat()") : js.index("void bootChat();")]
    assert "if (loaded === false) newChat" in boot
    assert "pendingStartsFor(selected)" in boot
    assert "loaded === true" not in boot


def test_full_inference_slots_become_a_durable_visible_queue():
    js = (UI / "app.js").read_text()
    assert 'started.state || "running"' in js
    assert 'active.state || "running"' in js
    assert "ev.queued === true && !ev.done" in js
    assert "ev.started" in js
    assert "showQueued(position = 1)" in js
    assert "startQueued()" in js
    assert '"queue.waiting"' in js
    assert (
        "Queued — other responses are running. Your answer will start automatically "
        "as soon as a slot is free."
    ) in I18N
    assert 'backgroundJob.state === "queued"' in js

    queued = "".join(_blocks(".reply-queued .prose"))
    queued_dot = "".join(_blocks(".conv-generating.queued"))
    assert "border-inline-start" in queued and "background" in queued
    assert "animation: none" in queued_dot


def test_transient_engine_drop_shows_automatic_recovery_not_a_terminal_disconnect():
    js = (UI / "app.js").read_text()
    assert "ev.recovering" in js
    assert "showRecovering()" in js
    assert "job.recovering = true" in js
    assert 't("queue.recovering")' in js
    assert "resuming automatically" in I18N
    assert "the tutor dropped the connection" not in js.lower()
    recovering = "".join(_blocks(".reply-recovering"))
    assert "background" in recovering and "color" in recovering
    assert "ev.source && !ev.done" in js
    assert "source: ev.source || job.source" in js


def test_switching_conversations_detaches_rendering_without_stopping_the_job():
    js = (UI / "app.js").read_text()
    body = js[
        js.index("async function loadConversation(") : js.index("/** Re-render one in-flight")
    ]
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


def test_model_picker_uses_an_accessible_header_menu_instead_of_a_native_select():
    js = (UI / "app.js").read_text()
    assert 'id="model-trigger"' in HTML
    assert 'aria-haspopup="menu"' in HTML
    assert 'aria-controls="model-menu"' in HTML
    assert 'aria-describedby="model-note"' in HTML
    assert 'id="model-menu"' in HTML and 'role="menu"' in HTML
    assert 'id="model-options"' in HTML
    assert 'id="model-select"' not in HTML
    assert 'option.setAttribute("role", "menuitemradio")' in js
    assert 'option.setAttribute("aria-checked"' in js
    assert 'check.textContent = "✓"' in js
    assert 't("model.unavailable")' in js
    assert 'option.dataset.selectable !== "true"' in js
    assert "modelTrigger.disabled = !inspectable" in js
    assert 'event.key === "ArrowDown"' in js and 'event.key === "Enter"' in js
    assert "focus: event.detail === 0" in js
    assert "restoreFocus: true" in js
    assert 'fetch("/v1/models/select"' in js


def test_model_switch_transport_failure_stays_locked_until_authoritative_recovery():
    js = (UI / "app.js").read_text()
    assert "let modelSwitchUncertain = false" in js
    assert "scheduleModelCatalogRecovery()" in js
    assert 'modelTrigger.dataset.switching = "true"' in js
    assert 't("model.switchUncertain")' in js
    assert "The switch may still be completing" in I18N
    assert "error.definitive = response.status >= 400" in js
    assert "if (!error.definitive)" in js
    assert 't("model.connectionDropped")' in js
    assert "The connection dropped while switching models" in I18N


def test_locale_change_cannot_unlock_a_model_switch_in_flight():
    js = (UI / "app.js").read_text()
    helper = js[
        js.index("function localizeModelCatalog()") : js.index(
            "window.MutaI18n.subscribe", js.index("function localizeModelCatalog()")
        )
    ]
    assert 'modelTrigger.dataset.switching === "true"' in helper
    assert "syncComposerState()" in helper
    assert "renderModelCatalog(modelCatalog)" in helper
    switching = helper[: helper.index("renderModelCatalog(modelCatalog)")]
    assert "return;" in switching
    subscriber_start = js.index("window.MutaI18n.subscribe")
    subscriber = js[subscriber_start : js.index("refreshModelCatalog();", subscriber_start)]
    assert "localizeModelCatalog()" in subscriber
    assert "renderModelCatalog(modelCatalog)" not in subscriber


def test_model_menu_remains_inspectable_when_selection_is_not_permitted():
    js = (UI / "app.js").read_text()
    assert "modelTrigger.disabled = false" in js
    assert "option.dataset.selectable = String(selectionEnabled && model.available)" in js
    assert "!catalog.selection_enabled" in js
    assert 't("model.operatorOnly")' in js
    assert "Only the laptop operator can change the shared tutor model." in I18N


def test_settings_icon_has_intrinsic_dimensions_even_before_css_loads():
    settings = re.search(r'<button id="settings-open".*?</button>', HTML, re.DOTALL)
    assert settings
    assert '<svg width="16" height="16"' in settings.group()


def test_localized_dynamic_controls_remain_keyboard_and_screen_reader_operable():
    js = (UI / "app.js").read_text()
    audio = (UI / "audio.js").read_text()
    assert 'open.className = "conv-open"' in js
    assert 'open.setAttribute("aria-label", t("conversation.open"' in js
    assert 'del.setAttribute("aria-label", t("conversation.delete"))' in js
    assert 'x.setAttribute("aria-label", t("attachment.remove"))' in js
    assert 'x.setAttribute("aria-label", t("queue.dontSend"))' in js
    assert '$("#app").inert = open' in js
    assert 'settingsModal.addEventListener("keydown"' in js
    assert 'event.key !== "Tab"' in js
    assert 'micBtn.setAttribute("aria-pressed", String(active))' in audio
    assert 'micBtn.setAttribute("aria-label", t(active ? "voice.stop" : "voice.talk"))' in audio


def test_model_generated_text_keeps_its_own_direction_inside_an_rtl_interface():
    js = (UI / "app.js").read_text()
    html = (UI / "index.html").read_text()
    for assignment in (
        'bubble.dir = "auto"',
        'prose.dir = "auto"',
        'liveLine.dir = "auto"',
        'thought.dir = "auto"',
        'preambleText.dir = "auto"',
        'link.dir = "auto"',
    ):
        assert assignment in js
    assert '<textarea id="input" rows="1" dir="auto"' in html


def test_authored_entry_assets_share_one_cache_busting_revision():
    versions = re.findall(
        r'(?:href|src)="(?:styles\.css|math\.js|app\.js|audio\.js)\?v=([^"]+)"', HTML
    )
    assert len(versions) == 4
    assert len(set(versions)) == 1


def test_frontend_nginx_does_not_cache_static_ui_revisions():
    assert 'default "no-store, max-age=0";' in NGINX
    assert '~^/v1/ "";' in NGINX
    assert "add_header Cache-Control $muta_cache_control always;" in NGINX


def test_model_menu_is_contained_on_desktop_and_phone_layouts():
    menu = "".join(_blocks(".model-menu"))
    assert re.search(r"max-height\s*:", menu)
    assert re.search(r"overflow-y\s*:\s*auto", menu)
    assert "calc(100vw - 290px)" in menu
    assert re.search(
        r"@media\s*\(max-width:\s*720px\).*?\.model-menu\s*\{[^}]*position\s*:\s*fixed",
        CSS,
        re.DOTALL,
    )


def test_selected_conversation_lives_in_the_url_and_restores_on_startup():
    js = (UI / "app.js").read_text()
    assert 'searchParams.get("chat")' in js
    assert 'url.searchParams.set("chat", cid)' in js
    assert 'history[mode === "replace" ? "replaceState" : "pushState"]' in js
    assert "const selected = conversationFromLocation()" in js
    assert 'window.addEventListener("popstate"' in js
    assert 'setConversationLocation(conversationId, { mode: "replace" })' in js


def test_new_chat_start_can_be_recovered_if_the_page_refreshes_immediately():
    js = (UI / "app.js").read_text()
    assert "client_request_id: clientRequestId" in js
    assert "setPendingLocation(clientRequestId)" in js
    assert "/v1/chat/generations?client_request_id=" in js
    assert "recoverPendingGeneration(pending)" in js
    assert "if (job.terminal)" in js and "job.error = true" in js
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
    assert "if (!settingsModal.hidden) return;" in js


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
    assert HTML.index('<script src="math.js?') < HTML.index('<script src="app.js?')
    assert "MutaMath.render(el, text)" in js
    assert 'last.matches(".katex, .katex-display")' in js


def test_display_math_cannot_widen_the_conversation_column():
    display = "".join(_blocks(".prose .katex-display"))
    assert re.search(r"max-width\s*:\s*100%", display)
    assert re.search(r"overflow-x\s*:\s*auto", display)
    inline = "".join(_blocks(".prose .math-source.inline-math"))
    assert re.search(r"max-width\s*:\s*100%", inline)
    assert re.search(r"overflow-x\s*:\s*auto", inline)
