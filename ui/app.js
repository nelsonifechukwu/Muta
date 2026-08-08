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

let conversationId = null;
let generating = false;
let pendingAttachments = []; // {id, kind, mime, previewUrl, transcription?, status?}
let messageQueue = []; // {typed, attachments} — sent one by one when the tutor is free
let currentAbort = null; // AbortController while a *chat* stream runs (voice has its own barge)
let telemetrySource = null;
let telemetryCloseTimer = null;

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
  const inner = document.createElement("div");
  if (attachments.length) {
    const row = document.createElement("div");
    row.className = "attach-row";
    for (const a of attachments) {
      if (a.kind === "image") {
        const img = document.createElement("img");
        img.src = a.previewUrl || `/v1/attachments/${a.id}`;
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

function beginAssistantMessage() {
  hideEmptyState();
  const wrap = document.createElement("div");
  wrap.className = "msg assistant";

  const thinking = document.createElement("details");
  thinking.className = "thinking";
  thinking.hidden = true;
  const summary = document.createElement("summary");
  const label = document.createElement("span");
  label.className = "think-label";
  label.textContent = "Thinking…";
  const liveLine = document.createElement("span");
  liveLine.className = "think-line";
  summary.append(label, liveLine);
  const thought = document.createElement("div");
  thought.className = "thought";
  thinking.append(summary, thought);

  const prose = document.createElement("div");
  prose.className = "prose cursor";

  wrap.append(thinking, prose);
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
    if (!thinkStartedAt || thinkSettled) return;
    thinkSettled = true;
    const s = Math.max(1, Math.round((performance.now() - thinkStartedAt) / 1000));
    label.textContent = s < 60 ? `Thought for ${s}s` : `Thought for ${Math.floor(s / 60)}m ${s % 60}s`;
    label.classList.remove("shimmer");
    liveLine.textContent = ""; // the trace is the expandable body now, not a ticker
  };

  return {
    pushThought(t) {
      if (!thinkStartedAt) {
        thinkStartedAt = performance.now();
        thinking.hidden = false;
        label.classList.add("shimmer");
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
      settleThinking();
      full += t;
      scheduleRender();
    },
    finalize() {
      settleThinking(); // a reply stopped mid-think still gets its label settled
      cancelRender();
      if (full.trim()) renderMarkdown(prose, full);
      clearCursor(prose);
      scrollToBottom();
    },
    fail(message) {
      settleThinking();
      cancelRender();
      if (!full) prose.textContent = message;
      else renderMarkdown(prose, full);
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
    const r = await fetch(`/v1/conversations?student_id=${encodeURIComponent(studentId)}`);
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
        await fetch(`/v1/conversations/${c.id}`, { method: "DELETE" });
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
  // A running *chat* stream is interruptible — stop it (partial is persisted) and move on.
  // A voice reply is not ours to kill from here; the mic button owns that loop.
  if (generating) {
    if (!currentAbort) return toast("Wait for the current reply to finish.");
    stopGeneration();
  }
  discardQueue(); // queued messages were aimed at the thread we're leaving
  const r = await fetch(`/v1/conversations/${cid}/messages`);
  if (!r.ok) return toast("Couldn't load that conversation.");
  const body = await r.json();
  conversationId = cid;
  messagesEl.innerHTML = "";
  emptyStateEl.style.display = body.messages.length ? "none" : "";
  for (const m of body.messages) renderHistoryMessage(m);
  refreshSidebar();
  scrollToBottom();
}

function newChat() {
  if (generating) {
    if (!currentAbort) return toast("Wait for the current reply to finish.");
    stopGeneration();
  }
  discardQueue();
  conversationId = null;
  pendingAttachments = [];
  renderChips();
  messagesEl.innerHTML = "";
  emptyStateEl.style.display = "";
  refreshSidebar();
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

function syncComposerState() {
  const busy = readingAnImage();
  const streaming = currentAbort != null;
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

async function dispatch(item) {
  const message = composeOutgoingMessage(item.typed, item.attachments);
  const attachmentIds = item.attachments.map((a) => a.id).filter((id) => id != null);

  addUserMessage(item.typed || "(from my image)", item.attachments);
  const assistant = beginAssistantMessage();
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
        conversation_id: conversationId,
        attachment_ids: attachmentIds,
      }),
      signal: currentAbort.signal,
    });
    if (!res.ok) {
      const detail = (await res.json().catch(() => ({}))).detail;
      assistant.fail(detail || `The tutor couldn't answer (HTTP ${res.status}).`);
      return;
    }
    await pumpSse(res, assistant);
  } catch (err) {
    if (err && err.name === "AbortError") {
      // Deliberate stop, not a failure. The backend persists the partial reply on
      // disconnect, so what is on screen is what history will replay.
      assistant.fail("Stopped.");
    } else {
      assistant.fail("Lost the connection mid-answer — the partial reply is saved.");
    }
  } finally {
    generating = false;
    currentAbort = null;
    syncComposerState();
    closeTelemetry();
    refreshSidebar();
    drainQueue(); // steering: a stop followed by a queued correction sends it immediately
  }
}

async function pumpSse(res, assistant) {
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
        // second thread on the next message.
        if (ev.conversation_id) conversationId = ev.conversation_id;
        if (ev.reasoning) assistant.pushThought(ev.reasoning);
        else if (ev.delta) assistant.pushDelta(ev.delta);
        else if (ev.error) assistant.fail(ev.error);
        else if (ev.done) {
          assistant.finalize();
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
        }
        if (!telemetryOpened && (ev.reasoning || ev.delta) && conversationId) {
          openTelemetry(conversationId);
          telemetryOpened = true;
        }
      }
    }
  }
  if (conversationId && !telemetryOpened) openTelemetry(conversationId);
  if (conversationId) {
    // One last snapshot so a brand-new thread still shows its numbers.
    fetch(`/v1/conversations/${conversationId}/telemetry`)
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

refreshSidebar();

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
