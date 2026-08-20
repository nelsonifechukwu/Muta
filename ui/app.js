/* Muta chat client. Same-origin /v1 (nginx proxies to the backend). No framework. */
"use strict";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let studentId = (() => {
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
    if (r.ok) {
      const session = await r.json();
      // Native loopback mode returns one persistent operator id. Unlike localStorage, this is
      // independent of the SSH tunnel's local port, so every operator URL sees the same chats.
      studentId = session.student_id || studentId;
      authToken = session.token || studentId;
      localStorage.setItem("muta-student", studentId);
    }
  } catch {
    /* offline / older server: fall back to the student id (dev-mode token) */
  }
}

let conversationId = null;
// Chat inference is owned by the gateway. Each entry mirrors one replayable server job and
// keeps only view state in the browser; losing this Map on refresh is harmless because
// recoverGenerations() rebuilds it from GET /v1/chat/generations.
const generationJobs = new Map(); // job id -> {id, cid, handle, buffers, item, ...}
const startingConversations = new Set(); // prevent duplicate sends while POST /generations starts
let voiceGenerating = false;
// Kept false until the Settings UI lands; the per-conversation machinery itself is already
// capable of parallel jobs, while this gate preserves today's one-chat product behaviour.
let allowParallelChats = true;
let pendingAttachments = []; // {id, kind, mime, previewUrl, transcription?, status?}
let messageQueue = []; // {typed, attachments} — sent one by one when the tutor is free
let telemetrySource = null;
let telemetryCloseTimer = null;
// Reasoning effort for new turns: "off" (direct answer) | "auto" (think first) | "extended".
let thinkingLevel = localStorage.getItem("muta-thinking") || "auto";
let modelCatalog = null;

const anyGeneration = () => voiceGenerating || generationJobs.size > 0 || startingConversations.size > 0;
const jobForConversation = (cid = conversationId) =>
  [...generationJobs.values()].find((job) => job.cid === cid && !job.terminal) || null;

const $ = (sel) => document.querySelector(sel);
const messagesEl = $("#messages");
const inputEl = $("#input");
const sendBtn = $("#btn-send");
const emptyStateEl = $("#empty-state");
const chatScroller = $("#chat-scroll");

// Streaming should follow only while the student is already reading the tail. Keeping this
// as explicit state (instead of checking after every DOM append) matters: appending a large
// markdown block can move the bottom beyond the threshold even though the student was at it
// immediately before that render.
const AUTO_FOLLOW_THRESHOLD_PX = 96;
let autoFollow = true;

function conversationFromLocation() {
  const cid = new URL(location.href).searchParams.get("chat");
  return cid && cid.length <= 64 ? cid : null;
}

function setConversationLocation(cid, { mode = "push" } = {}) {
  if (mode === "none") return;
  const url = new URL(location.href);
  if (cid) url.searchParams.set("chat", cid);
  else url.searchParams.delete("chat");
  if (url.href === location.href) return;
  history[mode === "replace" ? "replaceState" : "pushState"]({ chat: cid }, "", url);
}

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

function nearChatBottom() {
  return chatScroller.scrollHeight - chatScroller.scrollTop - chatScroller.clientHeight <=
    AUTO_FOLLOW_THRESHOLD_PX;
}

function scrollToBottom({ force = false } = {}) {
  if (!force && !autoFollow) return;
  chatScroller.scrollTop = chatScroller.scrollHeight;
  autoFollow = true;
}

// A real user scroll is the authority: moving up pauses following, returning to the tail
// resumes it. Programmatic scrolls also fire this event but leave `nearChatBottom()` true.
chatScroller.addEventListener("scroll", () => {
  autoFollow = nearChatBottom();
}, { passive: true });

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
    element: wrap,
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
      const backgroundJob = jobForConversation(c.id);
      item.className = "conv-item" +
        (c.id === conversationId ? " active" : "") +
        (backgroundJob ? " generating" : "");
      const title = document.createElement("span");
      title.className = "conv-title";
      title.textContent = c.title || "Untitled";
      if (backgroundJob) {
        const dot = document.createElement("span");
        dot.className = "conv-generating";
        dot.title = "Replying in the background";
        item.appendChild(dot);
      }
      const del = document.createElement("button");
      del.className = "conv-del";
      del.textContent = "✕";
      del.title = "Delete conversation";
      del.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        if (backgroundJob) await stopGeneration(backgroundJob);
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

async function loadConversation(cid, { historyMode = "push" } = {}) {
  // Detach only the view. The gateway owns the job and our subscription keeps buffering it.
  const leaving = jobForConversation();
  if (leaving) {
    leaving.handle = null;
    leaving.telemetryOpened = false;
  }
  closeTelemetry(0);
  discardQueue(); // queued messages were aimed at the thread we're leaving
  const r = await fetch(`/v1/conversations/${cid}/messages`, { headers: authHeaders() });
  if (!r.ok) {
    toast("Couldn't load that conversation.");
    return false;
  }
  const body = await r.json();
  conversationId = cid;
  setConversationLocation(cid, { mode: historyMode });
  messagesEl.innerHTML = "";
  const restoring = jobForConversation(cid);
  let messages = body.messages;
  // The server writes a streaming reply through to its row as it arrives, so the in-flight
  // turn is already in this history — as a snapshot that is at most a moment old. The job
  // replay buffer holds the same text plus whatever landed since, so drop the partial row.
  if (restoring && messages.length && messages[messages.length - 1].role === "assistant") {
    messages = messages.slice(0, -1);
  }
  emptyStateEl.style.display = messages.length ? "none" : "";
  for (const m of messages) renderHistoryMessage(m);
  if (restoring) {
    reattachJob(restoring);
    openTelemetry(restoring.cid);
    restoring.telemetryOpened = true;
  }
  refreshSidebar();
  syncComposerState(); // the send button is only a Stop button in the streaming thread
  scrollToBottom({ force: true });
  return true;
}

/** Re-render one in-flight reply into a fresh bubble and point its subscription at it. */
function reattachJob(job) {
  const handle = beginAssistantMessage(null); // no "Answer now" on a resumed view
  if (job.preamble) handle.pushPreamble(job.preamble);
  if (job.reasoning) handle.pushThought(job.reasoning);
  if (job.content) handle.pushDelta(job.content);
  job.handle = handle;
}

function newChat({ historyMode = "push" } = {}) {
  const leaving = jobForConversation();
  if (leaving) {
    leaving.handle = null;
    leaving.telemetryOpened = false;
  }
  closeTelemetry(0);
  discardQueue();
  conversationId = null;
  setConversationLocation(null, { mode: historyMode });
  pendingAttachments = [];
  renderChips();
  messagesEl.innerHTML = "";
  emptyStateEl.style.display = "";
  scrollToBottom({ force: true });
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
  return jobForConversation();
}

function syncComposerState() {
  const busy = readingAnImage();
  const streaming = viewingLiveStream();
  const switchingModel = $("#model-select")?.dataset.switching === "true";
  $("#btn-image").disabled = busy || switchingModel;
  $("#btn-audio").disabled = switchingModel;
  $("#btn-mic").disabled = switchingModel;
  // During a chat stream the send button *is* the stop button, so it stays enabled. During a
  // voice reply (generating without a chat stream) the mic button owns interruption.
  sendBtn.disabled = switchingModel || busy || voiceGenerating || startingConversations.has(conversationId);
  sendBtn.classList.toggle("stop", Boolean(streaming));
  sendBtn.title = streaming ? "Stop the reply (Esc)" : "Send";
  const modelSelect = $("#model-select");
  if (modelSelect) {
    const hasChoice = modelCatalog?.selection_enabled
      && modelCatalog.models?.some((model) => model.available);
    modelSelect.disabled = anyGeneration() || modelSelect.dataset.switching === "true" || !hasChoice;
  }
}

async function stopGeneration(job = viewingLiveStream()) {
  if (!job || job.stopping) return;
  job.stopping = true;
  syncComposerState();
  try {
    const response = await fetch(`/v1/chat/generations/${job.id}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
    if (!response.ok && response.status !== 404) throw new Error(`HTTP ${response.status}`);
  } catch {
    job.stopping = false;
    syncComposerState();
    toast("Couldn't stop that reply yet — it is still running.");
  }
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

function drainQueue(cid = conversationId) {
  if (cid !== conversationId || voiceGenerating || jobForConversation(cid)) return;
  const next = messageQueue.shift();
  renderQueue();
  if (next) dispatch(next);
}

function restoreDraft(item) {
  inputEl.value = item.typed;
  pendingAttachments = item.attachments;
  renderChips();
  autoGrow();
}

function send(steer = false) {
  if ($("#model-select")?.dataset.switching === "true") {
    return toast("The selected model is still loading — your draft is safe.");
  }
  const typed = inputEl.value.trim();
  if (readingAnImage()) return toast("Still reading your image — one moment.");
  if (!typed && !pendingAttachments.some((a) => a.transcription)) return;

  const item = { typed, attachments: pendingAttachments.slice() };
  pendingAttachments = [];
  renderChips();
  inputEl.value = "";
  autoGrow();

  const currentJob = viewingLiveStream();
  if (currentJob) {
    // Human in the loop: Enter while the tutor talks queues the message; Ctrl+Enter steers —
    // it cuts the current reply short (partial is persisted) and sends this message next,
    // ahead of anything already queued. A voice reply can't be stopped from the keyboard
    // (the mic button owns barge-in), so steering degrades to queueing there.
    if (steer) {
      messageQueue.unshift(item);
      renderQueue();
      stopGeneration(currentJob); // finishGeneration drains the correction straight away
    } else {
      messageQueue.push(item);
      renderQueue();
    }
    return;
  }
  if (voiceGenerating) {
    messageQueue.push(item);
    renderQueue();
    return;
  }
  if (!allowParallelChats && generationJobs.size) {
    restoreDraft(item);
    return toast("A reply is running in another chat. Enable multiple chats in Settings to continue here.");
  }
  dispatch(item);
}

async function dispatch(item, opts = {}) {
  const {
    regenerate = false,
    thinking = thinkingLevel,
    conversationOverride = conversationId,
  } = opts;
  const message = composeOutgoingMessage(item.typed, item.attachments);
  const attachmentIds = item.attachments.map((a) => a.id).filter((id) => id != null);
  const startedIn = conversationOverride;
  const startKey = startedIn;
  if (startingConversations.has(startKey) || jobForConversation(startedIn)) return;

  // A regenerate ("answer now") re-answers the turn already on screen, so it neither adds a
  // new user bubble nor re-links attachments — the backend re-runs the last user turn.
  const renderingHere = conversationId === startedIn;
  if (!regenerate && renderingHere) addUserMessage(item.typed || "(from my image)", item.attachments);
  // "Answer now" is offered while the tutor is thinking: it cancels this stream and asks for
  // a direct answer to the same question. Not offered on a regenerate (it is already the
  // direct answer — thinking is off — so it can't loop).
  let job = null;
  const assistant = renderingHere
    ? beginAssistantMessage(
        regenerate ? null : () => {
          if (!job) return;
          job.pendingRegen = item;
          stopGeneration(job);
        },
      )
    : null;
  startingConversations.add(startKey);
  syncComposerState();

  try {
    const res = await fetch("/v1/chat/generations", {
      method: "POST",
      headers: { "content-type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        student_id: studentId,
        message,
        conversation_id: startedIn,
        attachment_ids: regenerate ? [] : attachmentIds,
        use_web: useWeb,
        thinking,
        regenerate,
      }),
    });
    if (!res.ok) {
      const detail = (await res.json().catch(() => ({}))).detail;
      if (assistant) assistant.fail(detail || `The tutor couldn't answer (HTTP ${res.status}).`);
      return;
    }
    const started = await res.json();
    const stillHere = conversationId === startedIn;
    if (stillHere) {
      conversationId = started.conversation_id;
      // The first persisted id replaces the blank-new-chat URL immediately, before any
      // tokens arrive, so even an instant refresh returns to the correct conversation.
      setConversationLocation(conversationId, { mode: "replace" });
    }
    job = {
      id: started.job_id,
      cid: started.conversation_id,
      handle: stillHere ? assistant : null,
      preamble: "",
      reasoning: "",
      content: "",
      item,
      pendingRegen: null,
      framesSeen: 0,
      terminal: false,
      stopping: false,
      telemetryOpened: false,
    };
    generationJobs.set(job.id, job);
    refreshSidebar();
    void followGeneration(job);
  } catch {
    if (assistant) assistant.fail("Couldn't start that reply — your message is saved above.");
  } finally {
    startingConversations.delete(startKey);
    syncComposerState();
  }
}

async function followGeneration(job) {
  let reconnectNoticeShown = false;
  while (!job.terminal && generationJobs.get(job.id) === job) {
    try {
      const res = await fetch(
        `/v1/chat/generations/${job.id}/stream?after=${job.framesSeen}`,
        { headers: authHeaders() },
      );
      if (res.status === 404) {
        // A gateway restart loses the live replay buffer, never the write-through transcript.
        job.terminal = true;
        generationJobs.delete(job.id);
        if (conversationId === job.cid) await loadConversation(job.cid);
        break;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      reconnectNoticeShown = false;
      await pumpSse(res, job);
      if (!job.terminal) throw new Error("stream ended before the job finished");
    } catch {
      if (job.terminal) break;
      if (!reconnectNoticeShown && conversationId === job.cid) {
        toast("Connection interrupted — reconnecting while the tutor keeps working.");
        reconnectNoticeShown = true;
      }
      await new Promise((resolve) => setTimeout(resolve, 750));
    }
  }
  if (job.terminal && generationJobs.get(job.id) === job) finishGeneration(job);
}

async function pumpSse(res, job) {
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
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
        job.framesSeen += 1;
        let ev;
        try {
          ev = JSON.parse(line.slice(6));
        } catch {
          continue;
        }
        if (ev.conversation_id) job.cid = ev.conversation_id;
        // Buffer first, then paint only if this conversation is still on screen.
        if (ev.preamble) {
          job.preamble += ev.preamble;
          job.handle?.pushPreamble(ev.preamble);
        } else if (ev.reasoning) {
          job.reasoning += ev.reasoning;
          job.handle?.pushThought(ev.reasoning);
        } else if (ev.delta) {
          job.content += ev.delta;
          job.handle?.pushDelta(ev.delta);
        } else if (ev.error) {
          job.failed = true;
          job.handle?.fail(ev.error);
        } else if (ev.done) {
          job.terminal = true;
          if (ev.stopped && job.pendingRegen) job.handle?.remove();
          else if (ev.stopped) job.handle?.fail("Stopped.");
          else if (!job.failed) job.handle?.finalize();
          decorateCompletedReply(job, ev);
          if (conversationId === job.cid) announce("Tutor replied.");
          if (ev.queued) {
            toast(
              `You're #${ev.queue_position || 1} in line — the tutor is busy. Your answer will start shortly.`,
              4000,
            );
          }
        }
        if (!job.telemetryOpened && (ev.reasoning || ev.delta) && conversationId === job.cid) {
          openTelemetry(job.cid);
          job.telemetryOpened = true;
        }
      }
    }
  }
  if (job.cid) {
    // One last snapshot so a brand-new thread still shows its numbers.
    fetch(`/v1/conversations/${job.cid}/telemetry`)
      .then((r) => (r.ok ? r.json() : null))
      .then((t) => t && conversationId === job.cid && updateTelemetry(t))
      .catch(() => {});
  }
}

function decorateCompletedReply(job, ev) {
  const last = job.handle?.element;
  if (!last) return;
  if (Array.isArray(ev.sources) && ev.sources.length && !last.querySelector(".sources")) {
    const box = document.createElement("div");
    box.className = "sources";
    box.append("Sources: ");
    ev.sources.forEach((source, i) => {
      const safe = safeHttpUrl(source.url);
      const link = document.createElement(safe ? "a" : "span");
      if (safe) {
        link.href = safe;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
      }
      link.textContent = `[${i + 1}] ${source.title}`;
      box.appendChild(link);
      if (i < ev.sources.length - 1) box.append(" · ");
    });
    last.appendChild(box);
  }
  if (ev.source === "cloud" && !last.querySelector(".src-badge")) {
    const badge = document.createElement("span");
    badge.className = "src-badge";
    badge.textContent = "answered via cloud";
    last.appendChild(badge);
  }
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

function finishGeneration(job) {
  generationJobs.delete(job.id);
  if (conversationId === job.cid) closeTelemetry();
  refreshSidebar();
  syncComposerState();
  if (job.pendingRegen) {
    const again = job.pendingRegen;
    dispatch(again, {
      regenerate: true,
      thinking: "off",
      conversationOverride: job.cid,
    });
  } else {
    drainQueue(job.cid);
  }
}

async function recoverGenerations() {
  try {
    const response = await fetch("/v1/chat/generations", { headers: authHeaders() });
    if (!response.ok) return;
    const body = await response.json();
    for (const active of body.generations || []) {
      if (generationJobs.has(active.job_id)) continue;
      const job = {
        id: active.job_id,
        cid: active.conversation_id,
        handle: null,
        preamble: "",
        reasoning: "",
        content: "",
        item: null,
        pendingRegen: null,
        framesSeen: 0,
        terminal: false,
        stopping: false,
        telemetryOpened: false,
      };
      generationJobs.set(job.id, job);
      void followGeneration(job);
    }
    syncComposerState();
  } catch {
    /* history remains usable; the next reload can try reconnecting again */
  }
}

sendBtn.addEventListener("click", () => {
  // While a chat stream runs the button is Stop; Enter still queues (see send()).
  if (viewingLiveStream()) stopGeneration();
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
  get studentId() { return studentId; },
  getConversationId: () => conversationId,
  setConversationId: (cid) => {
    conversationId = cid;
    setConversationLocation(cid, { mode: "replace" });
    refreshSidebar();
  },
  addUserMessage,
  beginAssistantMessage,
  openTelemetry,
  closeTelemetry,
  toast,
  isGenerating: anyGeneration,
  setGenerating: (v) => {
    voiceGenerating = v;
    syncComposerState();
    if (!v) drainQueue(); // a message typed during a voice reply goes out when it ends
  },
};

// --- settings --------------------------------------------------------------------------
const settingsModal = $("#settings-modal");
const parallelChatsToggle = $("#setting-parallel-chats");

function setSettingsOpen(open) {
  settingsModal.hidden = !open;
  if (open) {
    parallelChatsToggle.focus();
  } else {
    $("#settings-open").focus();
  }
}

async function loadSettings() {
  // localStorage is a compatibility fallback for an older gateway; the authenticated store
  // is authoritative and makes the preference follow the unified loopback learner identity.
  const cached = localStorage.getItem("muta-parallel-chats");
  if (cached != null) allowParallelChats = cached === "true";
  parallelChatsToggle.checked = allowParallelChats;
  try {
    const response = await fetch("/v1/settings", { headers: authHeaders() });
    if (!response.ok) return;
    const settings = await response.json();
    allowParallelChats = settings.allow_parallel_chats !== false;
    parallelChatsToggle.checked = allowParallelChats;
    localStorage.setItem("muta-parallel-chats", String(allowParallelChats));
  } catch {
    /* keep the local fallback */
  }
}

async function saveParallelChats(enabled) {
  const previous = allowParallelChats;
  allowParallelChats = enabled;
  localStorage.setItem("muta-parallel-chats", String(enabled));
  parallelChatsToggle.disabled = true;
  try {
    const response = await fetch("/v1/settings", {
      method: "PUT",
      headers: { "content-type": "application/json", ...authHeaders() },
      body: JSON.stringify({ allow_parallel_chats: enabled }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
  } catch {
    allowParallelChats = previous;
    parallelChatsToggle.checked = previous;
    localStorage.setItem("muta-parallel-chats", String(previous));
    toast("Couldn't save that setting.");
  } finally {
    parallelChatsToggle.disabled = false;
    syncComposerState();
  }
}

$("#settings-open").addEventListener("click", () => setSettingsOpen(true));
$("#settings-close").addEventListener("click", () => setSettingsOpen(false));
settingsModal.addEventListener("click", (event) => {
  if (event.target === settingsModal) setSettingsOpen(false);
});
parallelChatsToggle.addEventListener("change", () => {
  void saveParallelChats(parallelChatsToggle.checked);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !settingsModal.hidden) setSettingsOpen(false);
});

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
ensureAuth().then(async () => {
  await loadSettings();
  await recoverGenerations();
  const selected = conversationFromLocation();
  if (selected) {
    const loaded = await loadConversation(selected, { historyMode: "none" });
    if (!loaded) newChat({ historyMode: "replace" });
  } else {
    refreshSidebar();
  }
});

window.addEventListener("popstate", () => {
  const selected = conversationFromLocation();
  if (selected) void loadConversation(selected, { historyMode: "none" });
  else newChat({ historyMode: "none" });
});

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

// --- local model registry ---------------------------------------------------------------
const modelSelect = $("#model-select");
const modelNote = $("#model-note");

function modelSummary(model) {
  const metrics = [];
  if (model.arc_easy != null) metrics.push(`ARC-Easy ${(100 * model.arc_easy).toFixed(0)}%`);
  if (model.audit_proxy_tps != null) {
    metrics.push(`audit proxy ${model.audit_proxy_tps.toFixed(1)} tok/s`);
  }
  return [model.description, metrics.join(" · ")].filter(Boolean).join(" ");
}

function renderModelCatalog(catalog) {
  modelCatalog = catalog;
  const models = catalog.models || [];
  const active = models.find((model) => model.id === catalog.active_id);
  modelSelect.innerHTML = "";
  // A custom --model path can be healthy without belonging to the fixed registry. Keep the
  // visible value honest and give the first catalog item its own selectable transition.
  if (!active) {
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = catalog.active_id
      ? "Current engine · outside registry"
      : "Select a local model…";
    placeholder.selected = true;
    placeholder.disabled = true;
    modelSelect.append(placeholder);
  }
  for (const model of models) {
    const option = document.createElement("option");
    option.value = model.id;
    option.textContent = model.label + (model.recommended ? " · recommended" : "");
    option.disabled = !model.available;
    if (model.disabled_reason) option.textContent += ` — ${model.disabled_reason}`;
    option.selected = model.id === catalog.active_id;
    modelSelect.append(option);
  }
  const hasChoice = catalog.selection_enabled && models.some((model) => model.available);
  modelNote.textContent = active
    ? modelSummary(active)
    : hasChoice
      ? "The current engine is outside this registry. Choose an installed tutor model."
      : catalog.selection_enabled
        ? "No verified optional model is installed."
        : "Only the laptop operator can change the shared tutor model.";
  modelSelect.dataset.switching = String(catalog.switching === true);
  modelSelect.disabled = anyGeneration() || catalog.switching === true || !hasChoice;
}

async function refreshModelCatalog() {
  try {
    const response = await fetch("/v1/models");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderModelCatalog(await response.json());
  } catch {
    modelSelect.disabled = true;
    modelNote.textContent = "Could not read the local model registry.";
  }
}

modelSelect.addEventListener("change", async () => {
  const target = modelSelect.value;
  const prior = modelCatalog && modelCatalog.active_id;
  if (!target || target === prior) return;
  if (anyGeneration()) {
    modelSelect.value = prior;
    toast("Stop the current reply before changing models.");
    return;
  }
  const chosen = modelCatalog.models.find((model) => model.id === target);
  modelSelect.dataset.switching = "true";
  modelSelect.disabled = true;
  syncComposerState();
  modelNote.textContent = `Loading ${chosen.label}… The chat and saved conversations will stay open.`;
  toast(`Switching to ${chosen.label}…`, 120000);
  try {
    const response = await fetch("/v1/models/select", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ model_id: target }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
    renderModelCatalog(body);
    toast(`${chosen.label} is ready. New replies will use it.`);
    announce(`${chosen.label} is ready.`);
  } catch (error) {
    toast(`Model switch failed: ${error.message}`);
    await refreshModelCatalog();
  } finally {
    modelSelect.dataset.switching = "false";
    syncComposerState();
  }
});

refreshModelCatalog();
