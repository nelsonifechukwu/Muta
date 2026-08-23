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
ACCESS_BOOTSTRAP = (UI / "access-bootstrap.js").read_text()


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


def test_loopback_host_opens_the_local_shell_without_the_shared_connection_gate():
    """The laptop running Muta is the operator, not a client joining its own share.

    Detection happens in the blocking head so the wrong full-screen gate cannot flash before
    app.js starts. This is only first-paint routing; backend authorization remains mandatory.
    """
    bootstrap_tag = '<script src="access-bootstrap.js?v=20260822-local-host-1"></script>'
    assert bootstrap_tag in HTML
    assert HTML.index(bootstrap_tag) < HTML.index('<link rel="stylesheet"')
    assert 'hostname === "localhost"' in ACCESS_BOOTSTRAP
    assert 'hostname === "::1"' in ACCESS_BOOTSTRAP
    assert 'hostname.startsWith("127.")' in ACCESS_BOOTSTRAP
    assert 'localOperator ? "operator" : "shared"' in ACCESS_BOOTSTRAP
    assert "window.MutaAccess = Object.freeze({ localOperator })" in ACCESS_BOOTSTRAP
    assert 'html[data-muta-access="operator"] #share-auth { display: none; }' in CSS
    assert 'html[data-muta-access="operator"] #app[hidden] { display: flex; }' in CSS

    js = (UI / "app.js").read_text()
    assert "const localOperatorPage = Boolean(window.MutaAccess?.localOperator)" in js
    assert 'app.removeAttribute("inert")' in js
    assert 'app.setAttribute("aria-busy", "false")' in js
    assert "if (localOperatorPage)" in js
    assert "A loopback page is the operator's own Muta" in js


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


def test_resource_citations_use_safe_inline_links_and_a_responsive_source_rail():
    js = (UI / "app.js").read_text()
    citations = (UI / "citations.js").read_text()

    assert 'src="citations.js?v=' in HTML
    assert HTML.index('src="citations.js?v=') < HTML.index('src="app.js?v=')
    assert 'window.MutaCitations?.decorate(container.querySelector(".prose")' in js
    assert js.count("renderResourceSources(") == 3, "history and live replies must share citations"
    assert 'window.matchMedia("(min-width: 1580px)")' in js
    assert 'trigger.setAttribute("aria-expanded", String(expanded))' in js
    assert "list.hidden = !expanded" in js
    assert 'box.classList.toggle("is-rail-active", box === active.box)' in js
    assert "box === focusedBox || (" in js
    assert 'box.addEventListener("focusin", () => preferResourceSources(box))' in js
    assert "position: fixed" in "".join(_blocks(".resource-sources.is-rail-active"))
    assert "const markerRect = owner.marker?.isConnected" in js
    assert "active.box.scrollHeight" in js
    assert "if (scrollRect.height < 60)" in js
    assert "function moveFocusFromResourceSources(" in js
    assert "(markerVisible ? marker : inputEl).focus({ preventScroll: true })" in js
    assert "const availableHeight = scrollRect.height - 16" in js
    assert "syncResourceSourcesLayout(box);\n      continue;" in js
    assert "box.contains(document.activeElement)" in js
    assert "moveFocusFromResourceSources(box);" in js
    assert "requestAnimationFrame(() => scrollToBottom());" in js
    assert 'document.addEventListener("muta:localechange"' in js
    assert 'window.addEventListener("muta:localechange"' not in js
    assert "resourceSourcesOwners.get(box).container.style.minHeight" in js
    assert "style.minHeight = `${" not in js, "the margin rail must not stretch a chat turn"
    assert "if (!resourceCitationRail.matches) scrollToBottom();" in js
    assert "link.href = resourcePageUrl(source.resource_id, source.page)" in js

    # Model text is never trusted to invent destinations: decoration is post-sanitize and the
    # parser only promotes a reference that maps to a server-owned record.
    assert "const REFERENCE = /\\[R([1-9]\\d*)\\]/gi" in citations
    assert "if (number <= limit)" in citations
    assert "function planClaimCitations(" in citations
    assert "function normalizeReferences(" in citations
    assert 'job.handle?.replace(job.content)' in js
    assert 'Object.prototype.hasOwnProperty.call(ev, "replace")' in js
    assert "{ legacyNumeric: true }" in js
    assert "job.terminalEvent = { ...ev" in js
    assert "decorateCompletedReply(job, job.terminalEvent" in js
    assert "addFallbackMarkers(root, records, explicitAssignments, options, markers)" in citations
    assert "evidence.exact && evidence.tokenCount >= 3" in citations
    assert "evidence.sameModifiers && evidence.sameNumbers && evidence.samePolarity" in citations
    assert "function normalizeEvidence(" in citations
    assert "function explicitClaimCitations(" in citations
    assert "function fallbackSentenceRanges(" in citations
    assert "const tail = claim.node.splitText(claim.offset)" in citations
    assert "marker(records[number - 1], number, options)" in citations
    assert "node.parentElement?.closest(EXCLUDED)" in citations
    assert '"a", "button", "code", "pre", "kbd", "samp", "textarea"' in citations
    assert '".katex", ".katex-display", ".math-source", ".resource-sources"' in citations

    rail = "".join(
        _blocks(".msg.assistant.has-resource-sources > .resource-sources.is-rail-active")
    )
    trigger = "".join(_blocks(".resource-sources-trigger"))
    hidden_list = "".join(_blocks(".resource-sources-list[hidden]"))
    clipped_preview_guard = "".join(_blocks("@media (max-width: 1319px)"))
    assert "position: fixed" in rail and "--citation-rail-left" in rail
    assert "overflow: hidden" in rail and "--citation-rail-height" in rail
    assert re.search(r"min-height\s*:\s*44px", trigger)
    assert re.search(r"display\s*:\s*none", hidden_list)
    assert (
        ".resource-citation-preview" in clipped_preview_guard
        and "display: none" in clipped_preview_guard
    )


def test_resource_mentions_hide_transport_syntax_and_flow_inline_with_prose():
    js = (UI / "app.js").read_text()
    mentions = (UI / "resource-mentions.js").read_text()

    assert 'src="resource-mentions.js?v=' in HTML
    assert HTML.index('src="resource-mentions.js?v=') < HTML.index('src="app.js?v=')
    select = js[js.index("function selectMention(") : js.index("function positionMentionMenu(")]
    assert "MutaResourceMentions.place(" in select
    assert "@{" not in select, "the transport token must never be pasted into the textarea"
    assert "MutaResourceMentions?.append(item.typed, item.ragResources)" in js
    assert "addUserMessage(mentionedText ||" in js
    assert "addUserMessage(m.content, m.attachments || [])" in js
    assert "records.set(name, records.has(name) ? null : resource)" in js
    assert "const resourceNames = (item.ragResources || [])" in js
    assert 'featureT("rag.document", { name: resourceNames })' in js
    assert 'if (e.key === "Enter")' in js
    assert 'mentionMatches.findIndex((resource) => resource.status === "ready")' in js
    assert 'role="combobox"' not in HTML
    assert 'aria-autocomplete="list"' in HTML
    assert 'aria-controls="resource-mention-menu" aria-haspopup="listbox"' in HTML
    assert 'id="resource-mention-status" class="sr-only" role="status"' in HTML
    assert 'featureT("rag.pickerResults", { count: readyCount })' in js
    assert 'featureT("rag.pickerClosed")' in js
    assert "const MAX_SELECTED_RAG_RESOURCES = 8" in js
    assert ".slice(0, MAX_SELECTED_RAG_RESOURCES)" in js
    assert 'featureT("rag.maxFiles", { count: MAX_SELECTED_RAG_RESOURCES })' in js
    assert "window.MutaResourceMentions.resolveResources(" in js
    assert "window.MutaResourceMentions.place(" in js
    assert "window.MutaResourceMentions.removeMarker(" in js
    assert "window.MutaResourceMentions.sanitizeDraft(" in js
    assert "typed: restoredRag.text.slice(0, 4096)" in js
    send = js[js.index("function send(") : js.index("async function dispatch(")]
    assert send.index("ragResources.length > MAX_SELECTED_RAG_RESOURCES") < send.index(
        "pendingAttachments = []"
    )

    # Names cross the DOM only through textContent; resource IDs remain the only authority used
    # to open a document or select retrieval context.
    assert "label.textContent = displayName" in js
    assert "mention.href = resourcePageUrl(resource.id, 1)" in js
    assert "const MENTION = /@\\{([^{}\\n]+)\\}" in mentions
    assert "(?![\\p{L}\\p{N}\\p{M}_]|\\.[\\p{L}\\p{N}])/gu" in mentions
    assert "result = result.split(marker).join(token)" in mentions

    composer_mention = "".join(_blocks(".composer-resource-mention"))
    sent_mention = "".join(_blocks(".user-resource-mention"))
    assert 'contenteditable="true" role="textbox"' in HTML
    assert 'aria-multiline="true"' in HTML
    assert 'id="rag-resource-chips"' not in HTML
    assert "display: inline" in composer_mention and "overflow-wrap: anywhere" in composer_mention
    assert "display: inline" in sent_mention and "overflow-wrap: anywhere" in sent_mention
    assert "border:" not in composer_mention and "background:" not in composer_mention
    assert "border:" not in sent_mention and "background:" not in sent_mention
    assert 'mention.className = "composer-resource-mention"' in js
    assert 'mention.contentEditable = "false"' in js
    assert "serializeComposerNode" in js and "composerMarker" in js
    assert "deleteComposerReferenceForKey" in js
    assert "e.isComposing || e.keyCode === 229" in js
    assert "if (event.isComposing) return" in js
    assert "composerOffsetAt(mention.parentNode" in js
    assert "dataset.composerOffset" not in js
    assert 'resourcePdfIcon("user-resource-mention-icon")' in js
    assert ".composer-resource-mention-icon" in CSS and ".user-resource-mention-icon" in CSS


def test_resource_retrieval_is_inferred_from_inline_mentions_without_a_mode_toggle():
    js = (UI / "app.js").read_text()
    mentions = (UI / "resource-mentions.js").read_text()
    send = js[js.index("function send(") : js.index("async function dispatch(")]
    trigger = js[js.index("function mentionTrigger(") : js.index("function selectMention(")]
    keydown = js[
        js.index('inputEl.addEventListener("keydown"') : js.index(
            'inputEl.addEventListener("beforeinput"'
        )
    ]

    assert 'id="btn-rag"' not in HTML
    assert "rag-toggle" not in HTML and ".rag-toggle" not in CSS
    assert "let useRag" not in js and "ragButton" not in js
    assert "const ragResources = resourcesFromTypedMentions(typed);" in send
    assert "!ragResources.length" in send
    assert 'featureT("rag.chooseFile")' not in send
    assert "if (!useRag)" not in trigger
    assert "empty.textContent = featureT(emptyKey)" in js
    assert '"rag.noFiles": "No files found"' in js
    assert "use_rag: (item.ragResources || []).length > 0" in js
    assert "useRag:" not in js
    assert "resolveResources(" in js
    assert 'resource?.status === "ready"' in mentions
    assert 'inputEl.removeAttribute("aria-activedescendant");' in js
    assert 'let resourceCatalogState = "loading"' in js
    assert 'resourceCatalogState === "error"' in js
    assert "reconcileQueuedResources()" in js
    assert "replaceResourceMarker(typed, resource)" in js
    assert "resourceLoadFailures < RESOURCE_LOAD_MAX_RETRIES || resourceQueueWaiters.size > 0" in js
    assert "resourceQueueWaiters.delete(item.cid);" in js
    assert "setTimeout(() => drainQueue(item.cid), 0);" in js
    assert keydown.index('e.key === "Enter" && e.shiftKey') < keydown.index(
        "if (!mentionMenu.hidden)"
    )
    assert "closeMentionMenu();\n        send(e.ctrlKey || e.metaKey);" in js


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
        'setComposerValue("")', js.index("function send(")
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


def test_settings_exposes_persisted_parallel_chat_and_power_switches():
    js = (UI / "app.js").read_text()
    assert 'id="settings-modal"' in HTML
    assert 'id="setting-parallel-chats"' in HTML
    assert 'id="setting-power-optimization"' in HTML
    assert 'id="power-status"' in HTML
    assert 'id="power-badge"' in HTML
    assert 'role="switch"' in HTML
    assert 'fetch("/v1/settings"' in js
    assert 'fetch("/v1/power/status"' in js
    assert "allow_parallel_chats: enabled" in js
    assert "power_optimization_enabled: enabled" in js
    assert 'setAttribute("aria-label", badgeLabel)' in js
    assert "Battery sensor temporarily unavailable; Critical reserve remains active." in js
    assert 'hostMode === "critical"' in js
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
    subscriber = js[subscriber_start:]
    assert "localizeModelCatalog()" in subscriber
    assert "renderModelCatalog(modelCatalog)" not in subscriber


def test_model_catalog_starts_after_auth_without_blocking_saved_conversations():
    js = (UI / "app.js").read_text()
    boot = js[js.index("async function bootChat()") : js.index("void bootChat();")]
    assert "while (!(await ensureAuth()))" in boot
    assert "void refreshModelCatalog();" in boot
    assert "await refreshModelCatalog();" not in boot
    assert boot.index("while (!(await ensureAuth()))") < boot.index("void refreshModelCatalog();")
    assert "void refreshSidebar();" in boot
    assert "void loadSettings();" in boot
    assert "void loadResources({ quiet: true });" in boot
    assert boot.index("void refreshSidebar();") < boot.index("await recoverGenerations();")
    assert "if (!selected) settleStartupRouting();" in boot
    load = js[js.index("async function loadConversation(") : js.index("/** Re-render one in-flight")]
    assert load.count("settleStartupRouting();") == 2


def test_inference_controls_stay_locked_until_catalog_and_initial_routing_are_ready():
    js = (UI / "app.js").read_text()
    sync = js[
        js.index("function syncComposerState()") : js.index("async function stopGeneration(")
    ]
    assert "let startupRoutingReady = false;" in js
    assert "modelCatalog === null" in sync
    assert 'modelTrigger?.dataset.loadFailed !== "true"' in sync
    assert "const inferenceUnavailable" in sync
    assert "!startupRoutingReady" in sync
    assert "imageButton.disabled = busy || inferenceUnavailable" in sync
    assert '$("#btn-audio").disabled = inferenceUnavailable' in sync
    assert '$("#btn-mic").disabled = inferenceUnavailable' in sync
    assert "sendBtn.disabled =\n    (!streaming && inferenceUnavailable)" in sync


def test_host_capacity_change_refreshes_image_capability_catalog():
    js = (UI / "app.js").read_text()
    save = js[
        js.index("async function saveHostSettings()") : js.index("async function hostUserAction")
    ]
    assert "renderHostStatus(payload);" in save
    assert "await refreshModelCatalog();" in save
    assert save.index("renderHostStatus(payload);") < save.index("await refreshModelCatalog();")


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


def test_image_attachments_upload_without_an_eager_reader_and_keep_recovery_detail():
    js = (UI / "app.js").read_text()
    upload = (UI / "image-upload.js").read_text()
    add_image = js[js.index("async function addImage(") : js.index("async function addAudio(")]

    assert "MutaImageUpload.request" in add_image
    assert '"/v1/attachments/images"' in add_image
    assert '"/v1/tutor/vision"' not in add_image
    assert "transcription" not in add_image
    assert "body.attachment_id" in upload
    assert "return uploadFailure()" in upload
    assert "entry.detail = detail" in add_image
    assert "toast(detail)" in add_image
    assert "aria-live=" not in re.search(r'<div id="attachment-chips"[^>]*>', HTML).group()
    assert 'id="toast" dir="auto" role="status" aria-live="assertive"' in HTML
    assert 'img.alt = a.name ? t("attachment.previewNamed"' in js
    assert "white-space: nowrap" not in re.search(
        r"\.chip-status\s*\{([^}]*)\}", CSS, re.DOTALL
    ).group(1)
    reduced_motion = re.search(
        r"@media \(prefers-reduced-motion: reduce\)\s*\{\s*"
        r"\.chip\.uploading \.chip-status\s*\{([^}]*)\}",
        CSS,
        re.DOTALL,
    )
    assert reduced_motion and "animation: none" in reduced_motion.group(1)


def test_conversation_titles_render_resource_mentions_without_transport_syntax():
    js = (UI / "app.js").read_text()
    mentions = (UI / "resource-mentions.js").read_text()
    renderer = js[
        js.index("function renderConversationTitle(") : js.index(
            "function addUserMessage(", js.index("function renderConversationTitle(")
        )
    ]
    sidebar = js[
        js.index("async function refreshSidebar(") : js.index(
            "function scheduleConversationRetry(", js.index("async function refreshSidebar(")
        )
    ]
    assert "MutaResourceMentions?.segmentConversationTitle(source)" in renderer
    assert 'mention.className = "conv-resource-mention"' in renderer
    assert "document.createTextNode(part.value)" in renderer
    assert "label.textContent = part.name" in renderer
    assert 'resourcePdfIcon("conv-resource-mention-icon")' in renderer
    assert "title.textContent = displayTitle" not in sidebar
    assert "renderConversationTitle(title, displayTitle)" in sidebar
    assert "title: readableTitle" in sidebar
    assert "const MENTION = /@\\{([^{}\\n]+)\\}" in mentions
    assert "Array.from(source).length !== Math.max(0, Number(legacyLimit) || 0)" in mentions
    assert 'const opener = source.lastIndexOf("@{")' in mentions
    title_css = "".join(_blocks(".conv-title"))
    icon_css = "".join(_blocks(".conv-resource-mention-icon"))
    assert "text-overflow: ellipsis" in title_css and "min-width: 0" in title_css
    assert "vertical-align" in icon_css and "width: 0.95em" in icon_css


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
    assert '<div id="input" class="composer-input" contenteditable="true" role="textbox"' in html
    assert 'aria-multiline="true" dir="auto"' in html


def test_authored_entry_assets_share_one_cache_busting_revision():
    versions = re.findall(
        r'(?:href|src)="(?:styles\.css|math\.js|resource-mentions\.js|image-upload\.js|app\.js|audio\.js)\?v=([^"]+)"',
        HTML,
    )
    assert len(versions) == 6
    assert len(set(versions)) == 1
    assert re.search(r'src="i18n\.js\?v=([^"]+)"', HTML).group(1) == versions[0]


def test_muta_share_gate_is_labeled_persistent_and_role_scoped():
    js = (UI / "app.js").read_text()
    for fragment in (
        'autocomplete="username"',
        'autocomplete="current-password"',
        'autocomplete="new-password"',
        'role="alert" aria-live="assertive"',
        'id="host-settings"',
        'id="host-qr"',
    ):
        assert fragment in HTML
    assert 'const SHARE_ENROLLMENT_KEY = "muta-share-enrollment"' in js
    assert 'document.querySelector("#host-settings").hidden = role !== "host"' in js
    assert 'document.querySelector(".model-selector").hidden = role === "member"' in js
    assert 'method: "POST"' in js and "/v1/share/enrollments/" in js
    assert "window.confirm(" in js and "conversations, files and learning profile" in js
    assert "?token=" not in js


def test_muta_share_tabs_and_revocation_flow_are_keyboard_and_session_safe():
    js = (UI / "app.js").read_text()
    assert 'role="tabpanel" aria-labelledby="share-login-tab"' in HTML
    assert 'id="share-signup-tab" type="button" role="tab" tabindex="-1"' in HTML
    assert 'event.key === "ArrowRight"' in js
    assert 'event.key === "Home"' in js
    assert 'shareTab(index === 0 ? "login" : "signup", { focus: "tab" })' in js
    assert '$("#share-pending-title").focus()' in js
    assert "function revalidateShareIdentity()" in js
    assert 'sessionStorage.setItem(\n    "muta-share-reauth"' in js


def test_checked_in_dist_entry_assets_are_byte_identical_to_authored_sources():
    dist = UI / "dist"
    if not dist.is_dir():
        return
    authored = sorted(
        path.name
        for path in UI.iterdir()
        if path.is_file()
        and path.suffix.lower() in {".css", ".html", ".js"}
        and not path.name.lower().endswith((".spec.js", ".test.js"))
    )
    for name in authored:
        assert (UI / name).read_bytes() == (dist / name).read_bytes(), name


def _contrast(left: str, right: str) -> float:
    def luminance(value: str) -> float:
        channels = [int(value[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    high, low = sorted((luminance(left), luminance(right)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _dark_tokens(css: str) -> dict[str, str]:
    match = re.search(r':root\[data-theme="dark"\]\s*\{(.*?)\n\}', css, re.DOTALL)
    assert match
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", match.group(1)))


def test_dark_mode_is_prepaint_persistent_complete_and_accessible():
    js = (UI / "app.js").read_text()
    theme = (UI / "theme.js").read_text()
    landing_theme = (UI.parent / "landing" / "theme.js").read_bytes()

    assert HTML.index('src="theme.js') < HTML.index('rel="stylesheet" href="styles.css')
    assert 'id="setting-theme"' in HTML
    assert all(f'<option value="{value}">' in HTML for value in ("system", "light", "dark"))
    assert "MutaTheme?.applyPreference(themeSelect.value, { persist: true })" in js
    assert 'document.addEventListener("muta:themechange", syncThemeSetting)' in js
    assert 'global.addEventListener?.("storage"' in theme
    assert 'media.addEventListener("change"' in theme
    assert (UI / "theme.js").read_bytes() == landing_theme
    assert ':root[data-theme="dark"]' in CSS

    tokens = _dark_tokens(CSS)
    for foreground, background, minimum in (
        ("text", "bg", 4.5),
        ("muted", "bg", 4.5),
        ("text", "card", 4.5),
        ("muted", "card", 4.5),
        ("accent", "bg", 4.5),
        ("danger", "bg", 4.5),
        ("power-text", "power-bg", 4.5),
    ):
        assert _contrast(tokens[foreground], tokens[background]) >= minimum, (foreground, background)
    assert _contrast("#ffffff", tokens["danger-fill"]) >= 3


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


def test_generation_feedback_replaces_the_blinking_cursor_and_names_visual_work():
    js = (UI / "app.js").read_text()
    css = (UI / "styles.css").read_text()
    assert 'activity.className = "generation-status"' in js
    assert 'wrap.setAttribute("aria-busy", "true")' in js
    assert 'visualization: "Generating diagram…"' in js
    assert 'job.handle?.showPhase(ev.phase)' in js
    assert 'job.handle?.replaceContent(job.content)' in js
    assert ".generation-dots" in css and "@keyframes generation-dot" in css
    assert "prefers-reduced-motion: reduce" in css
    assert ".cursor::after" not in css
    assert "placeCursor(" not in js


def test_display_math_cannot_widen_the_conversation_column():
    display = "".join(_blocks(".prose .katex-display"))
    assert re.search(r"max-width\s*:\s*100%", display)
    assert re.search(r"overflow-x\s*:\s*auto", display)
    inline = "".join(_blocks(".prose .math-source.inline-math"))
    assert re.search(r"max-width\s*:\s*100%", inline)
    assert re.search(r"overflow-x\s*:\s*auto", inline)
