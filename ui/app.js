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
let pendingAttachments = []; // {id, kind, mime, previewUrl, transcription?}
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

function renderMarkdown(el, text) {
  el.innerHTML = DOMPurify.sanitize(marked.parse(text));
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
  summary.textContent = "Thinking…";
  const thought = document.createElement("div");
  thought.className = "thought";
  thinking.append(summary, thought);

  const prose = document.createElement("div");
  prose.className = "prose cursor";
  const textNode = document.createTextNode("");
  prose.appendChild(textNode);

  wrap.append(thinking, prose);
  messagesEl.appendChild(wrap);
  scrollToBottom();

  let full = "";
  return {
    pushThought(t) {
      thinking.hidden = false;
      thought.textContent += t;
    },
    pushDelta(t) {
      full += t;
      textNode.data = full;
      scrollToBottom();
    },
    finalize() {
      prose.classList.remove("cursor");
      thinking.querySelector("summary").textContent = "Thought process";
      if (full.trim()) renderMarkdown(prose, full);
      scrollToBottom();
    },
    fail(message) {
      prose.classList.remove("cursor");
      if (!full) prose.textContent = message;
      else renderMarkdown(prose, full);
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
  if (generating) return toast("Wait for the current reply to finish.");
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
  if (generating) return toast("Wait for the current reply to finish.");
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
function renderChips() {
  const box = $("#attachment-chips");
  box.innerHTML = "";
  for (const a of pendingAttachments) {
    const chip = document.createElement("span");
    chip.className = "chip";
    if (a.kind === "image" && a.previewUrl) {
      const img = document.createElement("img");
      img.src = a.previewUrl;
      chip.appendChild(img);
    } else {
      chip.append(a.kind === "audio" ? "🎙 audio" : "📎 file");
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
}

async function addImage(file) {
  toast("Reading the image…", 2000);
  const form = new FormData();
  form.append("session_id", studentId);
  if (conversationId) form.append("conversation_id", conversationId);
  form.append("image", file);
  let body;
  try {
    const r = await fetch("/v1/tutor/vision", { method: "POST", body: form });
    body = await r.json();
  } catch {
    return toast("Image upload failed — is the backend up?");
  }
  if (!body.accepted) {
    toast(body.detail || "The image was refused.");
    if (body.attachment_id == null) return;
  }
  pendingAttachments.push({
    id: body.attachment_id,
    kind: "image",
    previewUrl: URL.createObjectURL(file),
    transcription: body.accepted ? body.transcription : "",
  });
  renderChips();
  if (body.accepted && body.transcription) {
    toast("Image read. Ask your question and send.", 3000);
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
  if (e.key === "Escape") hideDropHint();
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
function composeOutgoingMessage(typed) {
  // Image transcriptions ride along as context the tutor can see.
  const transcribed = pendingAttachments
    .filter((a) => a.kind === "image" && a.transcription)
    .map((a) => `Problem transcribed from my image: "${a.transcription}"`);
  if (!transcribed.length) return typed;
  return typed ? `${transcribed.join("\n")}\n\n${typed}` : transcribed.join("\n");
}

async function send() {
  const typed = inputEl.value.trim();
  if (generating) return;
  if (!typed && !pendingAttachments.some((a) => a.transcription)) return;

  const message = composeOutgoingMessage(typed);
  const attachments = pendingAttachments.slice();
  const attachmentIds = attachments.map((a) => a.id).filter((id) => id != null);
  pendingAttachments = [];
  renderChips();
  inputEl.value = "";
  autoGrow();

  addUserMessage(typed || "(from my image)", attachments);
  const assistant = beginAssistantMessage();
  generating = true;
  sendBtn.disabled = true;

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
    });
    if (!res.ok) {
      const detail = (await res.json().catch(() => ({}))).detail;
      assistant.fail(detail || `The tutor couldn't answer (HTTP ${res.status}).`);
      return;
    }
    await pumpSse(res, assistant);
  } catch (err) {
    assistant.fail("Lost the connection mid-answer — the partial reply is saved.");
  } finally {
    generating = false;
    sendBtn.disabled = false;
    closeTelemetry();
    refreshSidebar();
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
        if (ev.reasoning) assistant.pushThought(ev.reasoning);
        else if (ev.delta) assistant.pushDelta(ev.delta);
        else if (ev.error) assistant.fail(ev.error);
        else if (ev.done) {
          conversationId = ev.conversation_id || conversationId;
          assistant.finalize();
        }
        if (!telemetryOpened && (ev.reasoning || ev.delta) && conversationId) {
          // Existing threads watch live from the first token; brand-new ones learn their
          // id at `done` and are opened by the post-stream branch below.
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

sendBtn.addEventListener("click", send);
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send();
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
    sendBtn.disabled = v;
  },
};

refreshSidebar();
