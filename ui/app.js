/* Muta chat client. Same-origin /v1 (nginx proxies to the backend). No framework. */
"use strict";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const studentId = (() => {
  let id = localStorage.getItem("muta-student");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("muta-student", id);
  }
  return id;
})();

// Bearer token for the data endpoints (conversations, attachments). In the default (no
// server secret) deployment the token IS the student id, so this works immediately; when the
// server sets MUTA_AUTH_SECRET, ensureAuth() upgrades it to a signed token. Attachment <img>
// URLs can't carry a header, so they take ?token= instead.
let authToken = studentId;
const authHeaders = () => ({ Authorization: `Bearer ${authToken}` });
const attachmentUrl = (id) => `/v1/attachments/${id}?token=${encodeURIComponent(authToken)}`;

async function ensureAuth() {
  try {
    const r = await fetch("/v1/auth/session", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ student_id: studentId }),
    });
    if (r.ok) authToken = (await r.json()).token || studentId;
  } catch {
    /* offline / older server: fall back to the student id (dev-mode token) */
  }
}

let conversationId = null;
let generating = false;
// The reply currently in flight, kept OUTSIDE the DOM so leaving its conversation cannot
// destroy it: { cid, handle, preamble, reasoning, content }. `handle` is re-pointed at a
// fresh bubble when the student comes back, and the three buffers are what gets replayed
// into it. Null whenever nothing is streaming.
let live = null;
let pendingAttachments = []; // {id, kind, mime, previewUrl, transcription?, status?}
let messageQueue = []; // {typed, attachments} — sent one by one when the tutor is free
let currentAbort = null; // AbortController while a *chat* stream runs (voice has its own barge)
let telemetrySource = null;
let telemetryCloseTimer = null;
// Reasoning effort for new turns: "off" (direct answer) | "auto" (think first) | "extended".
let thinkingLevel = localStorage.getItem("muta-thinking") || "auto";
let currentItem = null; // the item the active stream is answering (for "Answer now")
let pendingRegen = null; // set by "Answer now": re-dispatch this item with thinking off

const $ = (sel) => document.querySelector(sel);
const messagesEl = $("#messages");
const inputEl = $("#input");
const sendBtn = $("#btn-send");
const emptyStateEl = $("#empty-state");

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------
function toast(text, ms = 4200) {
  const el = $("#toast");
  el.textContent = text;
  el.hidden = false;
  clearTimeout(el._t);
  el._t = setTimeout(() => (el.hidden = true), ms);
}

// Screen-reader announcement (visually hidden #sr-live). Re-set to "" first so identical
// consecutive messages are still announced.
function announce(text) {
  const el = $("#sr-live");
  if (!el) return;
  el.textContent = "";
  requestAnimationFrame(() => (el.textContent = text));
}

// Only allow http(s) links from model/web-grounding output to become real hrefs — never
// javascript:/data: — even though the source URLs come from a server-side search.
function safeHttpUrl(url) {
  try {
    const u = new URL(url, location.origin);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : null;
  } catch {
    return null;
  }
}

function scrollToBottom() {
  const scroller = $("#chat-scroll");
  scroller.scrollTop = scroller.scrollHeight;
}

function autoGrow() {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 200) + "px";
}
inputEl.addEventListener("input", autoGrow);

// Cheap pre-check: renderMathInElement walks the whole subtree, and this runs on every
// frame of a streaming reply. No delimiter in the source means there is nothing to find.
const MATH_HINT = /\$|\\\(|\\\[/;

function renderMarkdown(el, text) {
  el.innerHTML = DOMPurify.sanitize(marked.parse(text));
  if (!MATH_HINT.test(text)) return;
  renderMathInElement(el, {
    delimiters: [
      { left: "$$", right: "$$", display: true },
      { left: "$", right: "$", display: false },
      { left: "\\(", right: "\\)", display: false },
      { left: "\\[", right: "\\]", display: true },
    ],
    throwOnError: false,
  });
}

function clearCursor(root) {
  root.classList.remove("cursor");
  for (const el of root.querySelectorAll(".cursor")) el.classList.remove("cursor");
}

/** Park the blinking cursor on whatever element ends the text.
 *
 * Once a partial reply renders as markdown its tail is a block element, so a cursor on
 * the container would blink on its own line below the paragraph. Descend to the last
 * element that closes the content — skipping the whitespace text nodes marked emits
 * between blocks, and stopping at a trailing text node, whose text comes *after* the
 * last element (`<p>a <em>b</em> c</p>` must keep the cursor on the p, not the em). */
function placeCursor(root) {
  clearCursor(root);
  let el = root;
  for (;;) {
    let last = el.lastChild;
    while (last && last.nodeType === Node.TEXT_NODE && !last.data.trim()) {
      last = last.previousSibling;
    }
    if (!last || last.nodeType !== Node.ELEMENT_NODE) break;
    el = last;
  }
  el.classList.add("cursor");
}

// ---------------------------------------------------------------------------
// Message rendering
// ---------------------------------------------------------------------------
function hideEmptyState() {
  emptyStateEl.style.display = "none";
}

function addUserMessage(text, attachments = []) {
  hideEmptyState();
  const wrap = document.createElement("div");
  wrap.className = "msg user";
  // The stack — attachments above the bubble — is the flex item inside `.msg.user`, so it
  // is the element that must carry the width cap. It used to be an unstyled <div>, which
  // left `.bubble`'s `max-width: 85%` resolving against a shrink-to-fit parent: a cyclic
  // percentage that Chrome answers with "no constraint", collapsing short messages to one
  // character per line and letting long ones escape the column.
  const inner = document.createElement("div");
  inner.className = "user-stack";
  if (attachments.length) {
    const row = document.createElement("div");
    row.className = "attach-row";
    for (const a of attachments) {
      if (a.kind === "image") {
        const img = document.createElement("img");
        img.src = a.previewUrl || attachmentUrl(a.id);
        row.appendChild(img);
      } else {
        const chip = document.createElement("span");
        chip.className = "audio-chip";
        chip.textContent = "🎙 audio";
        row.appendChild(chip);
      }
    }
    inner.appendChild(row);
  }
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  inner.appendChild(bubble);
  wrap.appendChild(inner);
  messagesEl.appendChild(wrap);
  scrollToBottom();
}

function beginAssistantMessage(onAnswerNow) {
  hideEmptyState();
  const wrap = document.createElement("div");
  wrap.className = "msg assistant";

  const thinking = document.createElement("details");
  thinking.className = "thinking";
  thinking.hidden = true;
  const summary = document.createElement("summary");
  const dot = document.createElement("span");
  dot.className = "think-dot"; // pulsing while thinking, becomes a check when settled
  const label = document.createElement("span");
  label.className = "think-label";
  label.textContent = "Thinking";
  const liveLine = document.createElement("span");
  liveLine.className = "think-line";
  // "Answer now" — skip the thinking and get a direct answer. Lives in the summary but must
  // not toggle the <details>, so it swallows the click.
  const answerNowBtn = document.createElement("button");
  answerNowBtn.type = "button";
  answerNowBtn.className = "answer-now";
  answerNowBtn.textContent = "Answer now";
  answerNowBtn.hidden = true;
  answerNowBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    answerNowBtn.hidden = true;
    if (onAnswerNow) onAnswerNow();
  });
  summary.append(dot, label, liveLine, answerNowBtn);
  const thought = document.createElement("div");
  thought.className = "thought";
  thinking.append(summary, thought);

  // TTFT preamble: filler from the 1M-parameter warm-up model, shown only while the real
  // engine prefills. Labelled, muted, and structurally separate from `prose` so it can
  // never be mistaken for — or scraped as — the tutor's answer. It is deleted, not
  // appended to, the moment the engine produces its first token.
  const preamble = document.createElement("div");
  preamble.className = "preamble";
  preamble.hidden = true;
  const preambleLabel = document.createElement("span");
  preambleLabel.className = "preamble-label";
  preambleLabel.textContent = "warming up";
  const preambleText = document.createElement("span");
  preambleText.className = "preamble-text";
  preamble.append(preambleLabel, preambleText);

  const prose = document.createElement("div");
  prose.className = "prose cursor";

  wrap.append(thinking, preamble, prose);
  messagesEl.appendChild(wrap);
  scrollToBottom();

  let full = "";
  let thought_ = "";
  let thinkStartedAt = 0; // 0 = this reply produced no thinking
  let thinkSettled = false;

  // Markdown and math render AS the reply streams. Parsing is O(reply) and tokens land
  // every ~30 ms, so rendering per token would be quadratic and spend the frame budget
  // in marked/KaTeX; instead coalesce to at most one render per RENDER_MIN_MS, on a
  // frame boundary. Partial syntax needs no special handling — an unclosed `**` or `$$`
  // simply has not matched yet and stays literal until its closer arrives.
  const RENDER_MIN_MS = 90;
  let renderTimer = 0;
  let lastRenderAt = 0;
  let renderedLen = -1;
  let streamDone = false; // the last render is finalize's; nothing may repaint after it

  // Deliberately a plain timer, not requestAnimationFrame: rAF does not fire in a
  // backgrounded tab, which would freeze the reply mid-sentence until the user came
  // back. The timer already spaces the work out; the browser batches the paint.
  const renderNow = () => {
    renderTimer = 0;
    lastRenderAt = performance.now();
    if (streamDone || full.length === renderedLen) return;
    renderedLen = full.length;
    renderMarkdown(prose, full);
    placeCursor(prose); // after markdown the tail is a block; keep the caret in the text
    scrollToBottom();
  };

  const scheduleRender = () => {
    if (streamDone || renderTimer) return;
    const wait = Math.max(0, RENDER_MIN_MS - (performance.now() - lastRenderAt));
    renderTimer = setTimeout(renderNow, wait);
  };

  // A pending timer outliving the stream would repaint the reply and restore the cursor.
  const cancelRender = () => {
    streamDone = true;
    if (renderTimer) clearTimeout(renderTimer);
    renderTimer = 0;
  };

  // Train of thought stays folded while it streams: the summary shows a shimmering
  // "Thinking…" plus ONE live line — the tail of the trace, advancing line by line —
  // so a long reasoning pass never pushes the conversation off screen. The whole trace
  // is one click away (the <details> body), and settles to "Thought for Ns".
  const settleThinking = () => {
    answerNowBtn.hidden = true;
    if (!thinkStartedAt || thinkSettled) return;
    thinkSettled = true;
    const s = Math.max(1, Math.round((performance.now() - thinkStartedAt) / 1000));
    label.textContent = s < 60 ? `Thought for ${s}s` : `Thought for ${Math.floor(s / 60)}m ${s % 60}s`;
    label.classList.remove("shimmer");
    thinking.classList.add("settled"); // dot → check, stop the pulse
    liveLine.textContent = ""; // the trace is the expandable body now, not a ticker
  };

  // The engine has spoken — the placeholder's whole job is over. Removed from the DOM
  // rather than hidden, so no copy of it survives in the transcript the student can select.
  const clearPreamble = () => {
    if (preamble.isConnected) preamble.remove();
  };

  return {
    pushPreamble(t) {
      if (preamble.hidden) {
        preamble.hidden = false;
        announce("Tutor is warming up.");
      }
      preambleText.textContent += t;
      scrollToBottom();
    },
    pushThought(t) {
      clearPreamble();
      if (!thinkStartedAt) {
        thinkStartedAt = performance.now();
        thinking.hidden = false;
        label.classList.add("shimmer");
        if (onAnswerNow) answerNowBtn.hidden = false; // offer the skip only while thinking
      }
      thought_ += t;
      thought.textContent = thought_;
      thought.scrollTop = thought.scrollHeight; // the box caps at 16rem; follow the tail
      // Last non-blank line: a just-arrived "\n" would otherwise blank the ticker until
      // the next token lands.
      const lines = thought_.split("\n");
      while (lines.length && !lines[lines.length - 1].trim()) lines.pop();
      liveLine.textContent = lines.length ? lines[lines.length - 1] : "";
      scrollToBottom();
    },
    pushDelta(t) {
      clearPreamble();
      settleThinking();
      full += t;
      scheduleRender();
    },
    finalize() {
      clearPreamble(); // a turn that ended before the engine spoke leaves nothing behind
      settleThinking(); // a reply stopped mid-think still gets its label settled
      cancelRender();
      if (full.trim()) renderMarkdown(prose, full);
      clearCursor(prose);
      scrollToBottom();
    },
    remove() {
      cancelRender();
      wrap.remove();
    },
    fail(message) {
      settleThinking();
      cancelRender();
      if (!full) {
        prose.textContent = message;
      } else {
        // A partial reply exists: render it, but never let a truncated answer look finished —
        // append a visible incomplete marker instead of silently dropping the error.
        renderMarkdown(prose, full);
        const warn = document.createElement("div");
        warn.className = "reply-incomplete";
        warn.textContent = message || "Connection lost — this answer is incomplete.";
        prose.appendChild(warn);
      }
      clearCursor(prose);
    },
  };
}

function renderHistoryMessage(m) {
  if (m.role === "user") {
    addUserMessage(m.content, m.attachments || []);
  } else if (m.role === "assistant") {
    hideEmptyState();
    const wrap = document.createElement("div");
    wrap.className = "msg assistant";
    const prose = document.createElement("div");
    prose.className = "prose";
    renderMarkdown(prose, m.content);
    wrap.appendChild(prose);
    messagesEl.appendChild(wrap);
  }
}

// ---------------------------------------------------------------------------
// Telemetry strip
// ---------------------------------------------------------------------------
const fmt = {
  gb: (v) => (v == null ? "—" : v.toFixed(2) + " GB"),
  temp: (v) => (v == null ? "—" : Math.round(v)) + " °C",
  flag: (v) => (v == null ? "—" : v ? "YES" : "no"),
  tps: (v) => (v == null ? "—" : v.toFixed(1)) + " tok/s",
};

function updateTelemetry(t) {
  $("#telemetry").hidden = false;
  $("#t-ram").textContent = "RAM " + fmt.gb(t.rss_gb);
  $("#t-peak").textContent = "peak " + fmt.gb(t.peak_rss_gb);
  $("#t-temp").textContent = fmt.temp(t.cpu_temp_c);
  const th = $("#t-throttle");
  th.textContent = "throttle " + fmt.flag(t.throttled);
  th.classList.toggle("hot", t.throttled === true);
  $("#t-tps").textContent = fmt.tps(t.tokens_per_second);
}

function openTelemetry(cid) {
  closeTelemetry(0);
  telemetrySource = new EventSource(`/v1/conversations/${cid}/telemetry/stream`);
  telemetrySource.onmessage = (ev) => {
    try {
      updateTelemetry(JSON.parse(ev.data));
    } catch {
      /* keep the strip's last values */
    }
  };
  telemetrySource.onerror = () => closeTelemetry(0);
}

function closeTelemetry(afterMs = 4000) {
  clearTimeout(telemetryCloseTimer);
  const source = telemetrySource; // capture: a later openTelemetry must not be killed by us
  const close = () => {
    if (source) source.close();
    if (telemetrySource === source) telemetrySource = null;
  };
  if (afterMs === 0) close();
  else telemetryCloseTimer = setTimeout(close, afterMs);
}

// ---------------------------------------------------------------------------
// Conversations sidebar
// ---------------------------------------------------------------------------
async function refreshSidebar() {
  try {
    const r = await fetch(`/v1/conversations?student_id=${encodeURIComponent(studentId)}`, {
      headers: authHeaders(),
    });
    if (!r.ok) return;
    const body = await r.json();
    const list = $("#conversation-list");
    list.innerHTML = "";
    for (const c of body.conversations) {
      const item = document.createElement("div");
      item.className = "conv-item" + (c.id === conversationId ? " active" : "");
      const title = document.createElement("span");
      title.className = "conv-title";
      title.textContent = c.title || "Untitled";
      const del = document.createElement("button");
      del.className = "conv-del";
      del.textContent = "✕";
      del.title = "Delete conversation";
      del.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        await fetch(`/v1/conversations/${c.id}`, { method: "DELETE", headers: authHeaders() });
        if (c.id === conversationId) newChat();
        refreshSidebar();
      });
      item.append(title, del);
      item.addEventListener("click", () => loadConversation(c.id));
      list.appendChild(item);
    }
  } catch {
    /* sidebar is a convenience; the chat keeps working without it */
  }
}

async function loadConversation(cid) {
  // Leaving a conversation no longer cancels its reply. It used to: the stream was aborted
  // and the partial left to the server, so coming back showed a truncated answer at best —
  // and usually nothing, because the partial was not durable yet. The stream now runs on,
  // and `live` carries it across the switch.
  discardQueue(); // queued messages were aimed at the thread we're leaving
  const r = await fetch(`/v1/conversations/${cid}/messages`, { headers: authHeaders() });
  if (!r.ok) return toast("Couldn't load that conversation.");
  const body = await r.json();
  conversationId = cid;
  messagesEl.innerHTML = "";
  const restoring = live && live.cid === cid;
  let messages = body.messages;
  // The server writes a streaming reply through to its row as it arrives, so the in-flight
  // turn is already in this history — as a snapshot that is at most a moment old. `live`
  // holds the same text plus whatever landed since, so drop the row and replay the buffer.
  if (restoring && messages.length && messages[messages.length - 1].role === "assistant") {
    messages = messages.slice(0, -1);
  }
  emptyStateEl.style.display = messages.length ? "none" : "";
  for (const m of messages) renderHistoryMessage(m);
  if (restoring) reattachLive();
  refreshSidebar();
  syncComposerState(); // the send button is only a Stop button in the streaming thread
  scrollToBottom();
}

/** Re-render the in-flight reply into a fresh bubble and point the stream at it. */
function reattachLive() {
  const handle = beginAssistantMessage(null); // no "Answer now" on a resumed view
  if (live.preamble) handle.pushPreamble(live.preamble);
  if (live.reasoning) handle.pushThought(live.reasoning);
  if (live.content) handle.pushDelta(live.content);
  live.handle = handle;
}

function newChat() {
  discardQueue();
  conversationId = null;
  pendingAttachments = [];
  renderChips();
  messagesEl.innerHTML = "";
  emptyStateEl.style.display = "";
  refreshSidebar();
  syncComposerState();
}
$("#new-chat").addEventListener("click", newChat);

// ---------------------------------------------------------------------------
// Attachments (image via /v1/tutor/vision, audio via /v1/audio/transcribe)
// ---------------------------------------------------------------------------
/** True while any image is still being read. Reading a photo is a 15–90 s job on this
 *  hardware, so the composer has to hold the door: without it a student who sees no progress
 *  clicks again, and each extra click is another CORE-VISION spawn racing for the same port. */
function readingAnImage() {
  return pendingAttachments.some((a) => a.status === "reading");
}

/** True when the reply in flight belongs to the conversation on screen. A stream in another
 *  thread must not be stoppable from here — the Stop button has to mean "this reply". */
function viewingLiveStream() {
  return currentAbort != null && (!live || live.cid == null || live.cid === conversationId);
}

function syncComposerState() {
  const busy = readingAnImage();
  const streaming = viewingLiveStream();
  $("#btn-image").disabled = busy;
  // During a chat stream the send button *is* the stop button, so it stays enabled. During a
  // voice reply (generating without a chat stream) the mic button owns interruption.
  sendBtn.disabled = busy || (generating && !streaming);
  sendBtn.classList.toggle("stop", streaming);
  sendBtn.title = streaming ? "Stop the reply (Esc)" : "Send";
}

function stopGeneration() {
  if (currentAbort) currentAbort.abort();
}

function renderChips() {
  const box = $("#attachment-chips");
  box.innerHTML = "";
  for (const a of pendingAttachments) {
    const chip = document.createElement("span");
    chip.className = "chip" + (a.status ? " " + a.status : "");
    if (a.kind === "image" && a.previewUrl) {
      const img = document.createElement("img");
      img.src = a.previewUrl;
      chip.appendChild(img);
    } else {
      chip.append(a.kind === "audio" ? "🎙 audio" : "📎 file");
    }
    if (a.status === "reading" || a.status === "failed") {
      // Durable, not a toast that has already faded: this is the only signal that tells the
      // student whether the tutor can actually see what they attached.
      const label = document.createElement("span");
      label.className = "chip-status";
      label.textContent = a.status === "reading" ? "reading…" : "couldn't read it";
      if (a.detail) label.title = a.detail;
      chip.appendChild(label);
    }
    const x = document.createElement("button");
    x.className = "x";
    x.textContent = "✕";
    x.addEventListener("click", () => {
      pendingAttachments = pendingAttachments.filter((p) => p !== a);
      renderChips();
    });
    chip.appendChild(x);
    box.appendChild(chip);
  }
  syncComposerState();
}

async function addImage(file) {
  // The chip goes up before the request, not after it: the student needs to see that the
  // photo landed while CORE-VISION spends the next minute reading it.
  const entry = {
    id: null,
    kind: "image",
    previewUrl: URL.createObjectURL(file),
    transcription: "",
    status: "reading",
  };
  pendingAttachments.push(entry);
  renderChips();

  const form = new FormData();
  form.append("session_id", studentId);
  if (conversationId) form.append("conversation_id", conversationId);
  form.append("image", file);

  const settle = (status, detail) => {
    entry.status = status;
    entry.detail = detail || "";
    renderChips();
  };

  let body;
  try {
    const r = await fetch("/v1/tutor/vision", { method: "POST", body: form });
    body = await r.json();
  } catch {
    settle("failed", "the upload never reached the tutor");
    return toast("Image upload failed — is the backend up?");
  }
  entry.id = body.attachment_id ?? null;
  if (body.accepted && body.transcription) {
    entry.transcription = body.transcription;
    settle("ready");
    toast("Image read. Ask your question and send.", 3000);
  } else if (body.accepted) {
    // The reader ran but saw nothing it could transcribe — a camera problem, not a system
    // problem. Say so: "couldn't be read" sends the student hunting for a bug that isn't there.
    settle("failed", "the photo came back empty — try a closer, sharper shot");
    toast(entry.detail);
  } else {
    settle("failed", body.detail || "the image couldn't be read");
    toast(entry.detail);
  }
}

async function addAudio(file) {
  toast("Transcribing the audio…", 3000);
  const form = new FormData();
  if (conversationId) form.append("conversation_id", conversationId);
  form.append("student_id", studentId); // owner, so the stored recording is scoped to us
  form.append("audio", file);
  let body;
  try {
    const r = await fetch("/v1/audio/transcribe", { method: "POST", body: form });
    if (r.status === 503) {
      const detail = (await r.json()).detail;
      return toast(detail || "Speech recognition isn't available — type the question instead.");
    }
    body = await r.json();
  } catch {
    return toast("Audio upload failed — is the backend up?");
  }
  if (body.attachment_id != null) {
    pendingAttachments.push({ id: body.attachment_id, kind: "audio" });
    renderChips();
  }
  if (body.text) {
    inputEl.value = body.text;
    autoGrow();
    send(); // spoken/uploaded question goes straight to the tutor
  } else {
    toast("Couldn't hear anything in that file.");
  }
}

$("#btn-image").addEventListener("click", () => $("#file-image").click());
$("#btn-audio").addEventListener("click", () => $("#file-audio").click());
$("#file-image").addEventListener("change", (e) => {
  if (e.target.files[0]) addImage(e.target.files[0]);
  e.target.value = "";
});
$("#file-audio").addEventListener("change", (e) => {
  if (e.target.files[0]) addAudio(e.target.files[0]);
  e.target.value = "";
});

// Drag & drop for both kinds.
//
// Driven by a `dragover` heartbeat rather than balanced dragenter/dragleave counting:
// browsers do not guarantee a final dragleave when a drag ends outside the window or is
// cancelled, and one lost event strands a full-screen overlay over the whole app. dragover
// fires continuously while a file drag is over the page and simply stops when it ends —
// however it ends — so the hint always heals itself.
const DRAG_HEARTBEAT_MS = 900;
let dragTimer = null;

function draggingFiles(e) {
  const types = e.dataTransfer && e.dataTransfer.types;
  // Dragging selected text also fires these events; only a file drag is ours.
  return types ? Array.prototype.indexOf.call(types, "Files") >= 0 : false;
}

function showDropHint() {
  $("#drop-overlay").hidden = false;
  clearTimeout(dragTimer);
  dragTimer = setTimeout(hideDropHint, DRAG_HEARTBEAT_MS);
}

function hideDropHint() {
  clearTimeout(dragTimer);
  dragTimer = null;
  $("#drop-overlay").hidden = true;
}

window.addEventListener("dragover", (e) => {
  if (!draggingFiles(e)) return;
  e.preventDefault(); // required, or the drop event never fires
  showDropHint();
});
window.addEventListener("dragend", hideDropHint);
window.addEventListener("blur", hideDropHint);
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    hideDropHint();
    const menu = $("#think-menu");
    if (menu && !menu.hidden) return openThinkMenu(false); // close the menu before stopping
    stopGeneration(); // no-op unless a chat stream is running
  }
});
window.addEventListener("drop", (e) => {
  e.preventDefault();
  hideDropHint();
  for (const file of e.dataTransfer.files) {
    if (file.type.startsWith("image/")) addImage(file);
    else if (file.type.startsWith("audio/")) addAudio(file);
    else toast(`Not sure what to do with ${file.name}`);
  }
});

// ---------------------------------------------------------------------------
// Sending + SSE streaming
// ---------------------------------------------------------------------------
function composeOutgoingMessage(typed, attachments) {
  // This text is the ONLY thing the tutor learns about a photo: `attachment_ids` binds rows
  // in Postgres for history, it does not reach the model. So a photo we failed to read has
  // to be declared too — otherwise the student watches their image sit in the transcript
  // while the tutor insists there is no image, which is the worst of both worlds.
  const lines = attachments
    .filter((a) => a.kind === "image")
    .map((a) =>
      a.transcription
        ? `Problem transcribed from my image: "${a.transcription}"`
        : "I attached a photo but it could not be read, so you cannot see it. " +
          "Ask me to type the problem out."
    );
  if (!lines.length) return typed;
  return typed ? `${lines.join("\n")}\n\n${typed}` : lines.join("\n");
}

// --- the queue: messages typed while the tutor is busy -----------------------------------
function renderQueue() {
  const box = $("#queue");
  box.innerHTML = "";
  box.hidden = messageQueue.length === 0;
  messageQueue.forEach((item) => {
    const row = document.createElement("div");
    row.className = "queued";
    const label = document.createElement("span");
    label.className = "queued-text";
    const imgs = item.attachments.filter((a) => a.kind === "image").length;
    label.textContent =
      (imgs ? `🖼 ` : "") + (item.typed || "(from my image)");
    const x = document.createElement("button");
    x.className = "x";
    x.textContent = "✕";
    x.title = "Don't send this";
    x.addEventListener("click", () => {
      messageQueue = messageQueue.filter((q) => q !== item);
      renderQueue();
    });
    row.append(label, x);
    box.appendChild(row);
  });
}

function discardQueue() {
  if (messageQueue.length) {
    toast(`Discarded ${messageQueue.length} queued message${messageQueue.length > 1 ? "s" : ""}.`);
  }
  messageQueue = [];
  renderQueue();
}

function drainQueue() {
  if (generating) return;
  const next = messageQueue.shift();
  renderQueue();
  if (next) dispatch(next);
}

function send(steer = false) {
  const typed = inputEl.value.trim();
  if (readingAnImage()) return toast("Still reading your image — one moment.");
  if (!typed && !pendingAttachments.some((a) => a.transcription)) return;

  const item = { typed, attachments: pendingAttachments.slice() };
  pendingAttachments = [];
  renderChips();
  inputEl.value = "";
  autoGrow();

  if (generating) {
    // A reply running in a *different* thread must not be queued into this one — the queue
    // drains into whatever conversation is open when the stream ends, which would post this
    // message to the wrong conversation.
    if (!viewingLiveStream() && live) {
      // Hand the student's draft back exactly as it was — text and attachments — rather
      // than swallowing it.
      inputEl.value = item.typed;
      pendingAttachments = item.attachments;
      renderChips();
      autoGrow();
      return toast("Finish or stop the reply in the other chat first.");
    }
    // Human in the loop: Enter while the tutor talks queues the message; Ctrl+Enter steers —
    // it cuts the current reply short (partial is persisted) and sends this message next,
    // ahead of anything already queued. A voice reply can't be stopped from the keyboard
    // (the mic button owns barge-in), so steering degrades to queueing there.
    if (steer && currentAbort) {
      messageQueue.unshift(item);
      renderQueue();
      stopGeneration(); // dispatch's finally drains the queue straight away
    } else {
      messageQueue.push(item);
      renderQueue();
    }
    return;
  }
  dispatch(item);
}

async function dispatch(item, opts = {}) {
  const { regenerate = false, thinking = thinkingLevel } = opts;
  const message = composeOutgoingMessage(item.typed, item.attachments);
  const attachmentIds = item.attachments.map((a) => a.id).filter((id) => id != null);

  // A regenerate ("answer now") re-answers the turn already on screen, so it neither adds a
  // new user bubble nor re-links attachments — the backend re-runs the last user turn.
  if (!regenerate) addUserMessage(item.typed || "(from my image)", item.attachments);
  // "Answer now" is offered while the tutor is thinking: it cancels this stream and asks for
  // a direct answer to the same question. Not offered on a regenerate (it is already the
  // direct answer — thinking is off — so it can't loop).
  const assistant = beginAssistantMessage(
    regenerate ? null : () => {
      pendingRegen = item;
      stopGeneration();
    },
  );
  // Everything the stream produces goes here as well as to the DOM, so that leaving this
  // conversation costs nothing: `reattachLive` replays these buffers into a new bubble.
  live = { cid: conversationId, handle: assistant, preamble: "", reasoning: "", content: "" };
  const startedIn = conversationId;
  currentItem = item;
  generating = true;
  currentAbort = new AbortController();
  syncComposerState();

  try {
    const res = await fetch("/v1/chat/stream", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        student_id: studentId,
        message,
        // The thread this turn belongs to, captured at dispatch — not `conversationId`,
        // which now follows whatever the student is looking at.
        conversation_id: startedIn,
        attachment_ids: regenerate ? [] : attachmentIds,
        use_web: useWeb,
        thinking,
        regenerate,
      }),
      signal: currentAbort.signal,
    });
    if (!res.ok) {
      const detail = (await res.json().catch(() => ({}))).detail;
      live.handle.fail(detail || `The tutor couldn't answer (HTTP ${res.status}).`);
      return;
    }
    await pumpSse(res);
  } catch (err) {
    // `live.handle`, not `assistant`: after a switch away and back these are different
    // bubbles, and the message belongs on the one currently on screen.
    if (err && err.name === "AbortError") {
      // A deliberate stop. If it was "Answer now", the finally re-dispatches — don't flash a
      // "Stopped" first; just drop this bubble. Otherwise the partial reply is saved as-is.
      if (pendingRegen) live.handle.remove();
      else live.handle.fail("Stopped.");
    } else {
      live.handle.fail("Lost the connection mid-answer — the partial reply is saved.");
    }
  } finally {
    generating = false;
    live = null;
    currentAbort = null;
    currentItem = null;
    syncComposerState();
    closeTelemetry();
    refreshSidebar();
    if (pendingRegen) {
      // "Answer now": re-answer the same turn directly, no thinking, no duplicate question.
      const again = pendingRegen;
      pendingRegen = null;
      dispatch(again, { regenerate: true, thinking: "off" });
    } else {
      drainQueue(); // steering: a stop followed by a queued correction sends it immediately
    }
  }
}

async function pumpSse(res) {
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  let telemetryOpened = false;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const frame = buf.slice(0, i);
      buf = buf.slice(i + 2);
      for (const line of frame.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        let ev;
        try {
          ev = JSON.parse(line.slice(6));
        } catch {
          continue;
        }
        // The id leads the stream (first frame), so even a reply stopped mid-token knows
        // which conversation its partial landed in — a stopped first turn must not fork a
        // second thread on the next message. It names the *stream's* thread, so it only
        // moves the view when the student is still looking at that thread.
        if (ev.conversation_id) {
          const wasViewingThisStream = conversationId === live.cid;
          live.cid = ev.conversation_id;
          if (wasViewingThisStream) conversationId = ev.conversation_id;
          syncComposerState();
        }
        // Buffer first, then paint. `live.handle` is whichever bubble is on screen now.
        if (ev.preamble) {
          live.preamble += ev.preamble;
          live.handle.pushPreamble(ev.preamble);
        } else if (ev.reasoning) {
          live.reasoning += ev.reasoning;
          live.handle.pushThought(ev.reasoning);
        } else if (ev.delta) {
          live.content += ev.delta;
          live.handle.pushDelta(ev.delta);
        } else if (ev.error) live.handle.fail(ev.error);
        else if (ev.done) {
          live.handle.finalize();
          announce("Tutor replied.");
          if (Array.isArray(ev.sources) && ev.sources.length) {
            const msgs = messagesEl.querySelectorAll(".msg.assistant");
            const last = msgs[msgs.length - 1];
            if (last && !last.querySelector(".sources")) {
              const box = document.createElement("div");
              box.className = "sources";
              box.append("Sources: ");
              ev.sources.forEach((s, i) => {
                const safe = safeHttpUrl(s.url);
                const a = document.createElement(safe ? "a" : "span");
                if (safe) {
                  a.href = safe;
                  a.target = "_blank";
                  a.rel = "noopener noreferrer";
                }
                a.textContent = `[${i + 1}] ${s.title}`;
                box.appendChild(a);
                if (i < ev.sources.length - 1) box.append(" · ");
              });
              last.appendChild(box);
            }
          }
          if (ev.source === "cloud") {
            // The one thing a privacy-respecting cloud boost owes the student: saying so.
            const msgs = messagesEl.querySelectorAll(".msg.assistant");
            const last = msgs[msgs.length - 1];
            if (last && !last.querySelector(".src-badge")) {
              const badge = document.createElement("span");
              badge.className = "src-badge";
              badge.textContent = "answered via cloud";
              last.appendChild(badge);
            }
          }
          // Self-check result: a "steps checked" badge when the model's explicit arithmetic
          // held, or a friendly caution the server produced when a step contradicted itself.
          const last = messagesEl.querySelector(".msg.assistant:last-child");
          if (last) {
            if (ev.check_note) {
              const warn = document.createElement("div");
              warn.className = "reply-incomplete";
              warn.textContent = ev.check_note;
              last.querySelector(".prose")?.appendChild(warn);
            } else if (ev.verified === true && !last.querySelector(".verified-badge")) {
              const badge = document.createElement("span");
              badge.className = "verified-badge";
              badge.textContent = "✓ steps checked";
              badge.title = "The explicit arithmetic in this reply was verified with a math engine.";
              last.appendChild(badge);
            }
          }
          if (ev.queued) {
            toast(
              `You're #${ev.queue_position || 1} in line — the tutor is busy. Your answer will start shortly.`,
              4000,
            );
          }
        }
        // Telemetry follows the STREAM's thread, not the viewed one — a student who
        // wanders off must not point the live strip at a conversation that is idle.
        if (!telemetryOpened && (ev.reasoning || ev.delta) && live.cid) {
          openTelemetry(live.cid);
          telemetryOpened = true;
        }
      }
    }
  }
  const streamCid = live && live.cid;
  if (streamCid && !telemetryOpened) openTelemetry(streamCid);
  if (streamCid) {
    // One last snapshot so a brand-new thread still shows its numbers.
    fetch(`/v1/conversations/${streamCid}/telemetry`)
      .then((r) => (r.ok ? r.json() : null))
      .then((t) => t && updateTelemetry(t))
      .catch(() => {});
  }
}

sendBtn.addEventListener("click", () => {
  // While a chat stream runs the button is Stop; Enter still queues (see send()).
  if (currentAbort) stopGeneration();
  else send();
});
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    // Cmd+Enter is the macOS spelling of Ctrl+Enter; both steer.
    send(e.ctrlKey || e.metaKey);
  }
});

// Exposed for audio.js (the voice loop reuses the transcript rendering).
window.MutaChat = {
  studentId,
  getConversationId: () => conversationId,
  setConversationId: (cid) => {
    conversationId = cid;
    refreshSidebar();
  },
  addUserMessage,
  beginAssistantMessage,
  openTelemetry,
  closeTelemetry,
  toast,
  isGenerating: () => generating,
  setGenerating: (v) => {
    generating = v;
    syncComposerState();
    if (!v) drainQueue(); // a message typed during a voice reply goes out when it ends
  },
};

// --- mobile sidebar drawer -------------------------------------------------------------
const appEl = $("#app");
const menuToggle = $("#menu-toggle");
function setDrawer(open) {
  appEl.classList.toggle("sidebar-open", open);
  if (menuToggle) menuToggle.setAttribute("aria-expanded", String(open));
  const backdrop = $("#sidebar-backdrop");
  if (backdrop) backdrop.hidden = !open;
}
if (menuToggle) {
  menuToggle.addEventListener("click", () => setDrawer(!appEl.classList.contains("sidebar-open")));
  $("#sidebar-backdrop").addEventListener("click", () => setDrawer(false));
  // Close the drawer after picking a thread or starting a new one (mobile only).
  $("#conversation-list").addEventListener("click", () => setDrawer(false));
  $("#new-chat").addEventListener("click", () => setDrawer(false));
}

// Mint the bearer token (signed-mode servers), then load the sidebar. In default mode the
// token already equals the student id, so a failed/slow mint never blocks startup.
ensureAuth().then(refreshSidebar);

// --- thinking-level selector ------------------------------------------------------------
const THINK_LABELS = { off: "Instant", auto: "Thinking", extended: "Extended" };
const thinkBtn = $("#btn-think");
const thinkMenu = $("#think-menu");
const thinkCurrent = $("#think-current");
function applyThinkingLabel() {
  thinkCurrent.textContent = THINK_LABELS[thinkingLevel] || "Thinking";
  thinkMenu.querySelectorAll("[data-level]").forEach((b) => {
    b.setAttribute("aria-checked", String(b.dataset.level === thinkingLevel));
    b.classList.toggle("active", b.dataset.level === thinkingLevel);
  });
}
function openThinkMenu(open) {
  thinkMenu.hidden = !open;
  thinkBtn.setAttribute("aria-expanded", String(open));
}
thinkBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  openThinkMenu(thinkMenu.hidden);
});
thinkMenu.querySelectorAll("[data-level]").forEach((b) => {
  b.addEventListener("click", () => {
    thinkingLevel = b.dataset.level;
    localStorage.setItem("muta-thinking", thinkingLevel);
    applyThinkingLabel();
    openThinkMenu(false);
    toast(`Reasoning: ${THINK_LABELS[thinkingLevel]}.`, 2000);
  });
});
document.addEventListener("click", (e) => {
  if (!thinkMenu.hidden && !e.target.closest(".think-select")) openThinkMenu(false);
});
applyThinkingLabel();

// --- web grounding toggle ---------------------------------------------------------------
let useWeb = false;
$("#btn-web").addEventListener("click", () => {
  useWeb = !useWeb;
  const btn = $("#btn-web");
  btn.classList.toggle("active", useWeb);
  btn.setAttribute("aria-pressed", String(useWeb));
  toast(useWeb ? "Web grounding on — sources will be cited when online." : "Web grounding off.", 2500);
});

// --- connectivity dot: /v1/ready.online, polled slowly ---------------------------------
async function refreshNetDot() {
  const dot = $("#net-dot");
  if (!dot) return;
  try {
    const body = await (await fetch("/v1/ready")).json();
    if (body.online == null) return; // probe hasn't run yet — keep the dot hidden
    dot.hidden = false;
    dot.classList.toggle("online", body.online === true);
    dot.title = body.online ? "internet available" : "offline";
  } catch {
    /* the ready poll failing is not worth a toast */
  }
}
refreshNetDot();
setInterval(refreshNetDot, 60_000);
