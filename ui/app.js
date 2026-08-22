/* Muta chat client. Same-origin /v1 (nginx proxies to the backend). No framework. */
"use strict";

// Resource-RAG ships while the larger interface catalog is being regenerated independently.
// Keep its English fallback local so this branch does not invalidate complete locale packs.
const RESOURCE_RAG_COPY = Object.freeze({
  "resources.empty": "No learning resources yet.",
  "resources.processing": "Preparing…",
  "resources.ready": "Ready",
  "resources.failed": "Failed",
  "resources.pages": "{count} PDF pages",
  "resources.retry": "Retry",
  "resources.delete": "Delete",
  "resources.uploading": "Uploading {name}…",
  "resources.uploaded": "{name} is being prepared. You can keep chatting.",
  "resources.uploadFailed": "Couldn’t upload that PDF.",
  "resources.deleteFailed": "Couldn’t delete that file.",
  "rag.on": "Resource RAG on — type @ to choose a ready file.",
  "rag.off": "Resource RAG off.",
  "rag.noFiles": "No PDFs yet. Add one in Settings → Files.",
  "rag.chooseFile": "RAG is on — type @ and choose a ready file.",
  "rag.remove": "Remove {name}",
  "rag.document": "Document: {name}",
  "rag.openDocument": "Open document {name}",
  "rag.maxFiles": "You can use up to {count} documents in one message.",
  "rag.pickerResults": "{count} ready documents available. Use Up and Down arrows, then Enter.",
  "rag.pickerEmpty": "No ready documents match.",
  "rag.pickerClosed": "Document picker closed.",
  "rag.sourcePage": "{title}, PDF page {page}",
  "rag.openPage": "Open {title} at PDF page {page}",
  "rag.sources": "Sources",
  "rag.sourceCount": "{count} sources",
  "rag.sourceCountOne": "1 source",
  "rag.sourceMeta": "PDF · page {page}",
  "rag.citation": "Citation {number}: {title}, PDF page {page}",
  "rag.previewLabel": "Citation {number}",
  "rag.showSources": "Show {count} sources",
  "rag.hideSources": "Hide {count} sources",
});
// Power ships independently of the bulk locale-generation pass, as resource RAG does above.
// Dynamic copy falls back to English without marking the existing complete locale packs partial.
const POWER_COPY = Object.freeze({
  checking: "Checking host power…",
  checkingHelp: "Reading the battery of the laptop serving Muta.",
  unavailable: "Power information unavailable",
  unavailableHelp: "This device does not expose a battery sensor. Muta still keeps its fixed memory and thermal safeguards.",
  sensorGrace: "Battery sensor temporarily unavailable; Critical reserve remains active.",
  off: "Power optimization off",
  normal: "Balanced",
  eco: "Eco mode",
  critical: "Critical battery mode",
  plugged: "Plugged in",
  connectedDraining: "Power connected; battery still draining",
  battery: "Host battery {percentage}%",
  remaining: "about {time} remaining",
  rate: "{watts} W",
  actions: "Active: {actions}",
  action_limit_auto_reasoning: "bounded automatic reasoning",
  action_limit_response_length: "shorter replies",
  action_direct_responses: "direct responses",
  action_pause_vision: "new image reading paused",
  action_pause_tts: "speech playback paused",
  openSettings: "Open power settings",
});
const powerText = (key, variables = {}) => (POWER_COPY[key] || key).replace(
  /\{([a-zA-Z][\w]*)\}/g,
  (match, name) => Object.hasOwn(variables, name) ? String(variables[name]) : match,
);
const t = (key, variables) => window.MutaI18n.t(key, variables);
const featureT = (key, variables = {}) => {
  const value = RESOURCE_RAG_COPY[key] || key;
  return value.replace(/\{([a-zA-Z][\w]*)\}/g, (match, name) =>
    Object.hasOwn(variables, name) ? String(variables[name]) : match
  );
};

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
function newStudentId() {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  // randomUUID is secure-context-only in some browsers, while getRandomValues remains
  // available on the plain-HTTP classroom LAN. Produce an RFC 4122 v4 id without making
  // first boot depend on HTTPS or on weak pseudo-random entropy.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

let studentId = (() => {
  let id = localStorage.getItem("muta-student");
  if (!id) {
    id = newStudentId();
    localStorage.setItem("muta-student", id);
  }
  return id;
})();

// Share sessions primarily use an HttpOnly same-origin cookie. The host bootstrap also returns
// a short-lived bearer for CLI compatibility, but media URLs intentionally rely on the cookie
// so credentials never appear in browser history, referrers or proxy logs.
let authToken = "";
let authRole = null;
let authUsername = null;
let csrfToken = null;
let identityReady = false;
let shareAuthWake = null;
let revocationReloading = false;
const localOperatorPage = Boolean(window.MutaAccess?.localOperator);
const authHeaders = () => ({
  ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
  ...(csrfToken ? { "X-Muta-CSRF": csrfToken } : {}),
});
const attachmentUrl = (id) => `/v1/attachments/${id}`;
const resourcePageUrl = (id, page) =>
  `/v1/resources/${encodeURIComponent(id)}/content#page=${Math.max(1, Number(page) || 1)}`;

function activateIdentity({ userId, role, username = null, token = "", csrf = null }) {
  studentId = userId;
  authRole = role;
  authUsername = username;
  authToken = token;
  csrfToken = csrf;
  identityReady = true;
  localStorage.setItem("muta-student", studentId);
  document.querySelector("#share-auth").hidden = true;
  const app = document.querySelector("#app");
  app.hidden = false;
  app.removeAttribute("inert");
  app.setAttribute("aria-busy", "false");
  const account = document.querySelector("#share-account");
  account.hidden = false;
  document.querySelector("#share-account-name").textContent = username || "Muta host";
  document.querySelector("#share-account-role").textContent = role === "host" ? "Host" : "Member";
  document.querySelector("#share-logout").hidden = role === "host";
  document.querySelector("#host-settings").hidden = role !== "host";
  document.querySelector(".model-selector").hidden = role === "member";
  if (shareAuthWake) {
    shareAuthWake();
    shareAuthWake = null;
  }
}

function showShareAuth(status = {}) {
  // A loopback page is the operator's own Muta, never a shared-client login surface. Keep the
  // local shell visible while the backend finishes starting and let bootChat retry the private
  // session bootstrap. Backend Host/Origin/peer checks still decide whether authority is issued.
  if (localOperatorPage) {
    document.querySelector("#share-auth").hidden = true;
    document.querySelector("#app").hidden = false;
    return;
  }
  document.querySelector("#app").hidden = true;
  document.querySelector("#share-auth").hidden = false;
  document.querySelector("#share-auth-loading").hidden = true;
  document.querySelector("#share-auth-panel").hidden = false;
  const reauthMessage = sessionStorage.getItem("muta-share-reauth");
  if (reauthMessage) sessionStorage.removeItem("muta-share-reauth");
  document.querySelector("#share-auth-message").textContent = reauthMessage || status.message ||
    (status.enabled ? "Sign in to open your private tutor." : "This laptop is not sharing Muta right now.");
  const secureLink = document.querySelector("#share-secure-link");
  secureLink.hidden = !status.join_url || status.secure !== false;
  if (!secureLink.hidden) secureLink.href = status.join_url;
  const available = status.enabled && status.secure !== false;
  const pendingActive = !document.querySelector("#share-pending").hidden;
  document.querySelector("#share-auth-tabs").hidden = !available || pendingActive;
  if (!available) {
    document.querySelector("#share-login-form").hidden = true;
    document.querySelector("#share-signup-form").hidden = true;
  }
}

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
      activateIdentity({
        userId: session.student_id || studentId,
        role: session.role || "host",
        token: session.token || "",
        csrf: session.csrf_token || null,
      });
      return true;
    }
  } catch {
    /* Remote members cannot mint a host session; status below selects their login state. */
  }
  try {
    const response = await fetch("/v1/share/status", { cache: "no-store" });
    const status = await response.json();
    if (response.ok && status.authenticated && status.role === "member") {
      activateIdentity({ userId: status.user_id, role: "member", username: status.username });
      return true;
    }
    showShareAuth(status);
  } catch {
    showShareAuth({ message: "Could not reach this Muta. Check the network and try again." });
  }
  return false;
}

function reloadForShareReauthentication() {
  if (revocationReloading || authRole !== "member") return;
  revocationReloading = true;
  identityReady = false;
  for (const job of generationJobs.values()) job.source?.close();
  generationJobs.clear();
  closeTelemetry();
  sessionStorage.setItem(
    "muta-share-reauth",
    "Your access changed on the host laptop. Sign in again to continue.",
  );
  window.location.reload();
}

async function revalidateShareIdentity() {
  if (authRole !== "member" || revocationReloading) return;
  try {
    const response = await fetch("/v1/share/status", { cache: "no-store" });
    const status = await response.json().catch(() => ({}));
    if (!response.ok || !status.authenticated || status.role !== "member") {
      reloadForShareReauthentication();
    }
  } catch {
    // A network interruption is not revocation. Normal connectivity UI handles it.
  }
}

let conversationId = null;
// A blank chat has no persisted conversation id yet, but it is still a distinct view. This
// token prevents a slow start response from an older blank chat attaching itself to a newer
// blank chat merely because both have conversationId === null.
const newViewId = () => `view:${newStudentId()}`;
let currentViewId = newViewId();
// Chat inference is owned by the gateway. Each entry mirrors one replayable server job and
// keeps only view state in the browser; losing this Map on refresh is harmless because
// recoverGenerations() rebuilds it from GET /v1/chat/generations.
const generationJobs = new Map(); // job id -> {id, cid, handle, buffers, item, ...}
const startingConversations = new Set(); // prevent duplicate sends while POST /generations starts
let voiceGenerating = false;
let voiceModeActive = false;
// Kept false until the Settings UI lands; the per-conversation machinery itself is already
// capable of parallel jobs, while this gate preserves today's one-chat product behaviour.
let allowParallelChats = true;
let powerOptimizationEnabled = true;
let latestPowerStatus = null;
let pendingAttachments = []; // {id, kind, mime, previewUrl, transcription?, status?}
let useRag = false;
let learningResources = [];
let selectedRagResources = []; // stable {id, name}; request authority is always the id
const MAX_SELECTED_RAG_RESOURCES = 8; // ChatRequest.resource_ids contract maximum
let resourcePollTimer = null;
let mentionMatches = [];
let mentionActiveIndex = 0;
// Follow-ups typed while a reply is running are view state, but they still have to survive a
// reload. Each item is scoped to its conversation so navigating elsewhere never discards it.
let messageQueue = []; // {typed, attachments, ragResources, useRag, cid}
let telemetrySource = null;
let telemetryCloseTimer = null;
// Reasoning effort for new turns: "off" (direct answer) | "auto" (think first) | "extended".
let thinkingLevel = localStorage.getItem("muta-thinking") || "auto";
let modelCatalog = null;
let modelSwitchUncertain = false;
let modelRecoveryTimer = null;

const anyGeneration = () =>
  voiceModeActive || voiceGenerating || generationJobs.size > 0 || startingConversations.size > 0;
const jobForConversation = (cid = conversationId) =>
  [...generationJobs.values()].find((job) => job.cid === cid && !job.terminal) || null;
const startKeyFor = (cid, viewId = currentViewId) => cid ? `conversation:${cid}` : viewId;

const $ = (sel) => document.querySelector(sel);
const messagesEl = $("#messages");
const inputEl = $("#input");
const sendBtn = $("#btn-send");
const emptyStateEl = $("#empty-state");
const chatScroller = $("#chat-scroll");

// --- Muta Share account gate ----------------------------------------------------------
const SHARE_ENROLLMENT_KEY = "muta-share-enrollment";
let shareEnrollmentTimer = null;

function shareError(message = "") {
  $("#share-auth-error").textContent = message;
}

function shareTab(tab, { focus = "field" } = {}) {
  const login = tab === "login";
  const loginTab = $("#share-login-tab");
  const signupTab = $("#share-signup-tab");
  loginTab.setAttribute("aria-selected", String(login));
  signupTab.setAttribute("aria-selected", String(!login));
  loginTab.tabIndex = login ? 0 : -1;
  signupTab.tabIndex = login ? -1 : 0;
  $("#share-login-form").hidden = !login;
  $("#share-signup-form").hidden = login;
  $("#share-pending").hidden = true;
  shareError();
  if (focus === "tab") (login ? loginTab : signupTab).focus();
  else $(login ? "#share-login-username" : "#share-signup-username").focus();
}

function shareDetail(payload, fallback) {
  if (typeof payload?.detail === "string") return payload.detail;
  return fallback;
}

async function submitShareCredentials(kind, form) {
  if (!form.reportValidity()) return;
  shareError();
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  const body = {
    username: form.elements.username.value.trim(),
    password: form.elements.password.value,
  };
  try {
    const response = await fetch(`/v1/share/${kind}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => ({}));
    form.elements.password.value = "";
    if (!response.ok) throw new Error(shareDetail(payload, `Could not ${kind}.`));
    if (kind === "login") {
      activateIdentity({ userId: payload.user_id, role: "member", username: payload.username });
      return;
    }
    const enrollment = {
      id: payload.enrollment_id,
      secret: payload.enrollment_secret,
      username: payload.username,
      expiresAt: payload.expires_at,
    };
    localStorage.setItem(SHARE_ENROLLMENT_KEY, JSON.stringify(enrollment));
    showPendingEnrollment(enrollment);
  } catch (error) {
    shareError(error.message || "Something went wrong. Try again.");
  } finally {
    button.disabled = false;
  }
}

function clearPendingEnrollment() {
  localStorage.removeItem(SHARE_ENROLLMENT_KEY);
  if (shareEnrollmentTimer) window.clearTimeout(shareEnrollmentTimer);
  shareEnrollmentTimer = null;
}

async function pollEnrollment(enrollment) {
  try {
    const response = await fetch(`/v1/share/enrollments/${encodeURIComponent(enrollment.id)}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ secret: enrollment.secret }),
      cache: "no-store",
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(shareDetail(payload, "Could not check the request."));
    if (payload.authenticated) {
      clearPendingEnrollment();
      activateIdentity({ userId: payload.user_id, role: "member", username: payload.username });
      return;
    }
    if (["rejected", "removed", "expired"].includes(payload.status)) {
      clearPendingEnrollment();
      shareTab(payload.can_login ? "login" : "signup");
      shareError(payload.can_login
        ? "Your approval link expired, but your account is ready. Sign in with your password."
        : payload.status === "rejected"
          ? "The host did not approve that request. You can ask to join again."
          : "That request is no longer active. Ask to join again.");
      return;
    }
  } catch (error) {
    shareError(error.message || "Connection lost. Retrying…");
  }
  shareEnrollmentTimer = window.setTimeout(() => void pollEnrollment(enrollment), 2000);
}

function showPendingEnrollment(enrollment) {
  $("#share-auth-tabs").hidden = true;
  $("#share-login-form").hidden = true;
  $("#share-signup-form").hidden = true;
  $("#share-pending").hidden = false;
  shareError();
  $("#share-pending-title").focus();
  void pollEnrollment(enrollment);
}

$("#share-login-tab").addEventListener("click", () => shareTab("login"));
$("#share-signup-tab").addEventListener("click", () => shareTab("signup"));
$("#share-auth-tabs").addEventListener("keydown", (event) => {
  const tabs = [$("#share-login-tab"), $("#share-signup-tab")];
  const current = tabs.indexOf(document.activeElement);
  let index = null;
  if (event.key === "ArrowRight") index = (current + 1) % tabs.length;
  if (event.key === "ArrowLeft") index = (current - 1 + tabs.length) % tabs.length;
  if (event.key === "Home") index = 0;
  if (event.key === "End") index = tabs.length - 1;
  if (index == null) return;
  event.preventDefault();
  shareTab(index === 0 ? "login" : "signup", { focus: "tab" });
});
$("#share-login-form").addEventListener("submit", (event) => {
  event.preventDefault();
  void submitShareCredentials("login", event.currentTarget);
});
$("#share-signup-form").addEventListener("submit", (event) => {
  event.preventDefault();
  void submitShareCredentials("signup", event.currentTarget);
});
$("#share-pending-cancel").addEventListener("click", () => {
  clearPendingEnrollment();
  $("#share-auth-tabs").hidden = false;
  shareTab("login");
});
$("#share-logout").addEventListener("click", async () => {
  await fetch("/v1/share/logout", { method: "POST", headers: authHeaders() }).catch(() => null);
  identityReady = false;
  authRole = null;
  authToken = "";
  csrfToken = null;
  window.location.reload();
});

try {
  const pending = JSON.parse(localStorage.getItem(SHARE_ENROLLMENT_KEY) || "null");
  if (pending?.id && pending?.secret) showPendingEnrollment(pending);
} catch {
  clearPendingEnrollment();
}

// Streaming should follow only while the student is already reading the tail. Keeping this
// as explicit state (instead of checking after every DOM append) matters: appending a large
// markdown block can move the bottom beyond the threshold even though the student was at it
// immediately before that render.
const AUTO_FOLLOW_THRESHOLD_PX = 96;
let autoFollow = true;
let lastChatScrollTop = chatScroller.scrollTop;
let viewportResizeActive = false;
let viewportSettleTimer = null;
let pointerScrollingChat = false;
let manualScrollIntent = false;
let manualScrollDirection = 0;
let manualScrollIntentTimer = null;
let touchStartY = null;
let navigationVersion = 0;
let pendingConversationLoad = null;
let conversationRetryTimer = null;
let conversationRetryTarget = null;

// `interactive-widget=resizes-content` handles Chrome's virtual keyboard. Safari/iOS still
// exposes the genuinely visible height only through visualViewport, so make that height the
// shell's source of truth. This also follows the mobile address-bar animation without ever
// unlocking body/document scrolling.
function applyAppViewportMetrics() {
  const viewport = window.visualViewport;
  const height = viewport?.height || window.innerHeight;
  if (height <= 0) return;
  const root = document.documentElement;
  root.style.setProperty("--app-height", `${height}px`);
  root.style.setProperty("--app-top", `${viewport?.offsetTop || 0}px`);
  // Queue rows and attachment chips share a small, height-aware budget. At keyboard height
  // each keeps one usable row and scrolls internally, leaving the input and send controls visible.
  const regionHeight = Math.max(40, Math.min(112, height * 0.14));
  root.style.setProperty("--composer-region-max", `${regionHeight}px`);
  root.classList.toggle("compact-height", height < 240);
}

// A virtual-keyboard or browser-chrome resize can reduce scrollTop without student input as the
// browser clamps the old value to the new scroll range. Preserve an already-followed tail across
// that movement and sample again after the viewport animation; explicit wheel/touch/drag intent
// below can still cancel following immediately.
function syncAppViewportHeight() {
  const preserveFollow = autoFollow;
  viewportResizeActive = true;
  applyAppViewportMetrics();
  if (preserveFollow) scrollToBottom({ force: true });

  requestAnimationFrame(() => {
    applyAppViewportMetrics();
    if (preserveFollow && autoFollow) scrollToBottom({ force: true });
  });

  clearTimeout(viewportSettleTimer);
  viewportSettleTimer = setTimeout(() => {
    applyAppViewportMetrics();
    // A student who explicitly returned to the tail during the resize owns that decision;
    // layout clamping never sets manualScrollIntent, so it cannot trigger this resume path.
    if (!autoFollow && manualScrollDirection > 0 && nearChatBottom()) autoFollow = true;
    if (preserveFollow && autoFollow) scrollToBottom({ force: true });
    viewportResizeActive = false;
    lastChatScrollTop = chatScroller.scrollTop;
  }, 320);
}

function conversationFromLocation() {
  const cid = new URL(location.href).searchParams.get("chat");
  return cid && cid.length <= 64 ? cid : null;
}

function pendingRequestFromLocation() {
  const requestId = new URL(location.href).searchParams.get("pending");
  return requestId && requestId.length <= 64 ? requestId : null;
}

function setConversationLocation(cid, { mode = "push" } = {}) {
  if (mode === "none") return;
  const url = new URL(location.href);
  url.searchParams.delete("pending");
  if (cid) url.searchParams.set("chat", cid);
  else url.searchParams.delete("chat");
  if (url.href === location.href) return;
  history[mode === "replace" ? "replaceState" : "pushState"]({ chat: cid }, "", url);
}


function setPendingLocation(requestId) {
  const url = new URL(location.href);
  url.searchParams.delete("chat");
  url.searchParams.set("pending", requestId);
  history.replaceState({ pending: requestId }, "", url);
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
  lastChatScrollTop = chatScroller.scrollTop;
  autoFollow = true;
}

function pauseAutoFollow() {
  autoFollow = false;
}

function noteManualScrollIntent(direction = 0) {
  manualScrollIntent = true;
  if (direction) manualScrollDirection = direction;
  clearTimeout(manualScrollIntentTimer);
  // Outlast the 320 ms viewport settle sample so a keyboard-era flick that reaches the
  // tail through momentum is still recognized as the student's downward intent.
  manualScrollIntentTimer = setTimeout(() => {
    manualScrollIntent = false;
    manualScrollDirection = 0;
  }, 480);
}

// Moving upward by even one pixel is intent to read earlier text, including when the reader is
// still inside the 96 px bottom tolerance. Moving down does not resume following until the tail
// is actually reached. Viewport-driven clamping is ignored unless a pointer is actively dragging
// the chat; programmatic scroll-to-bottom only moves forward and remains followed.
chatScroller.addEventListener("scroll", () => {
  const current = chatScroller.scrollTop;
  if (pointerScrollingChat && current !== lastChatScrollTop) {
    noteManualScrollIntent(Math.sign(current - lastChatScrollTop));
  }
  const studentMovedChat = manualScrollIntent;
  if (current < lastChatScrollTop) {
    if (!viewportResizeActive || studentMovedChat) pauseAutoFollow();
  } else if (
    (!viewportResizeActive || manualScrollDirection > 0) &&
    nearChatBottom()
  ) {
    autoFollow = true;
  }
  lastChatScrollTop = current;
}, { passive: true });

chatScroller.addEventListener("wheel", (event) => {
  noteManualScrollIntent(Math.sign(event.deltaY));
  if (event.deltaY < 0) pauseAutoFollow();
}, { passive: true });
chatScroller.addEventListener("pointerdown", () => {
  pointerScrollingChat = true;
  // Pressing/selecting is neutral. Direction is recorded only after the pointer actually
  // moves the scroll position, so layout clamping cannot borrow a bare pointerdown as consent.
  manualScrollIntent = false;
  manualScrollDirection = 0;
  clearTimeout(manualScrollIntentTimer);
}, { passive: true });
window.addEventListener("pointerup", () => { pointerScrollingChat = false; }, { passive: true });
window.addEventListener("pointercancel", () => { pointerScrollingChat = false; }, {
  passive: true,
});
chatScroller.addEventListener("touchstart", (event) => {
  touchStartY = event.touches[0]?.clientY ?? null;
}, { passive: true });
chatScroller.addEventListener("touchmove", (event) => {
  const y = event.touches[0]?.clientY;
  if (touchStartY !== null && y !== undefined) {
    noteManualScrollIntent(Math.sign(touchStartY - y));
  }
  if (touchStartY !== null && y !== undefined && y > touchStartY + 2) pauseAutoFollow();
  if (y !== undefined) touchStartY = y;
}, { passive: true });
chatScroller.addEventListener("touchend", () => { touchStartY = null; }, { passive: true });

syncAppViewportHeight();
window.addEventListener("resize", syncAppViewportHeight, { passive: true });
window.visualViewport?.addEventListener("resize", syncAppViewportHeight, { passive: true });
window.visualViewport?.addEventListener("scroll", syncAppViewportHeight, { passive: true });

function autoGrow() {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 200) + "px";
}
inputEl.addEventListener("input", autoGrow);

function renderMarkdown(el, text) {
  MutaMath.render(el, text);
}

/** A complete assistant turn may contain one declarative visualization fence. Streaming keeps
 * using ordinary Markdown so an incomplete fence is harmless; only this completion path removes
 * a valid spec from the prose and mounts its sandboxed frame. */
function renderCompletedReply(wrap, prose, text) {
  const extracted = window.MutaViz
    ? window.MutaViz.extract(text)
    : { markdown: text, visualizations: [] };
  renderMarkdown(prose, extracted.markdown);
  window.MutaViz?.renderAll(wrap, extracted.visualizations);
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
    if (last.matches(".katex, .katex-display")) {
      el = last;
      break;
    }
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

function resourceDocumentIcon(className = "") {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  if (className) svg.classList.add(className);
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const page = document.createElementNS("http://www.w3.org/2000/svg", "path");
  page.setAttribute("d", "M7 2.75h6.8L19 8v13.25H7V2.75Z");
  page.setAttribute("fill", "none");
  page.setAttribute("stroke", "currentColor");
  page.setAttribute("stroke-width", "1.7");
  page.setAttribute("stroke-linejoin", "round");
  const fold = document.createElementNS("http://www.w3.org/2000/svg", "path");
  fold.setAttribute("d", "M13.5 3v5.5H19M9.5 12h7M9.5 15h7M9.5 18h4.5");
  fold.setAttribute("fill", "none");
  fold.setAttribute("stroke", "currentColor");
  fold.setAttribute("stroke-width", "1.45");
  fold.setAttribute("stroke-linecap", "round");
  fold.setAttribute("stroke-linejoin", "round");
  svg.append(page, fold);
  return svg;
}

function renderUserBubbleContent(bubble, text, resources = []) {
  const records = new Map();
  for (const resource of Array.isArray(resources) ? resources : []) {
    const name = window.MutaResourceMentions?.nameFor(resource) || resource.name;
    // The transport syntax contains a name, not an id. Never guess which file a pill should
    // open when the live selection itself contains duplicate names.
    records.set(name, records.has(name) ? null : resource);
  }
  const parts = window.MutaResourceMentions?.segment(text) || [
    { type: "text", value: String(text || "") },
  ];
  for (const part of parts) {
    if (part.type === "text") {
      bubble.appendChild(document.createTextNode(part.value));
      continue;
    }
    const resource = records.get(part.name);
    const displayName = resource
      ? window.MutaResourceMentions.nameFor(resource)
      : part.name;
    const mention = document.createElement(resource?.id ? "a" : "span");
    mention.className = "user-resource-mention";
    mention.dir = "auto";
    mention.title = displayName;
    mention.setAttribute(
      "aria-label",
      featureT(resource?.id ? "rag.openDocument" : "rag.document", { name: displayName }),
    );
    if (resource?.id) {
      mention.href = resourcePageUrl(resource.id, 1);
      mention.target = "_blank";
      mention.rel = "noopener noreferrer";
    }
    const label = document.createElement("span");
    label.textContent = displayName;
    mention.append(resourceDocumentIcon("user-resource-mention-icon"), label);
    bubble.appendChild(mention);
  }
}

function addUserMessage(text, attachments = [], resources = []) {
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
        const label = document.createElement("span");
        label.dataset.i18n = "attachment.audio";
        label.textContent = t("attachment.audio");
        chip.append("🎙 ", label);
        row.appendChild(chip);
      }
    }
    inner.appendChild(row);
  }
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.dir = "auto";
  renderUserBubbleContent(bubble, text, resources);
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
  label.dataset.i18n = "thinking.label";
  label.textContent = t("thinking.label");
  const liveLine = document.createElement("span");
  liveLine.className = "think-line";
  liveLine.dir = "auto";
  // "Answer now" — skip the thinking and get a direct answer. Lives in the summary but must
  // not toggle the <details>, so it swallows the click.
  const answerNowBtn = document.createElement("button");
  answerNowBtn.type = "button";
  answerNowBtn.className = "answer-now";
  answerNowBtn.dataset.i18n = "thinking.answerNow";
  answerNowBtn.textContent = t("thinking.answerNow");
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
  thought.dir = "auto";
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
  preambleLabel.dataset.i18n = "thinking.warming";
  preambleLabel.textContent = t("thinking.warming");
  const preambleText = document.createElement("span");
  preambleText.className = "preamble-text";
  preambleText.dir = "auto";
  preamble.append(preambleLabel, preambleText);

  const prose = document.createElement("div");
  prose.className = "prose cursor";
  prose.dir = "auto";

  const recovering = document.createElement("div");
  recovering.className = "reply-recovering";
  recovering.hidden = true;

  wrap.append(thinking, preamble, prose, recovering);
  messagesEl.appendChild(wrap);
  scrollToBottom();

  let full = "";
  let thought_ = "";
  let thinkStartedAt = 0; // 0 = this reply produced no thinking
  let thinkSettled = false;
  let queuedNotice = false;

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
    const key = s < 60 ? "thinking.seconds" : "thinking.minutes";
    const variables = s < 60
      ? { seconds: s }
      : { minutes: Math.floor(s / 60), seconds: s % 60 };
    label.dataset.i18n = key;
    label.setAttribute("data-i18n-vars", JSON.stringify(variables));
    label.textContent = t(key, variables);
    label.classList.remove("shimmer");
    thinking.classList.add("settled"); // dot → check, stop the pulse
    liveLine.textContent = ""; // the trace is the expandable body now, not a ticker
  };

  // The engine has spoken — the placeholder's whole job is over. Removed from the DOM
  // rather than hidden, so no copy of it survives in the transcript the student can select.
  const clearPreamble = () => {
    if (preamble.isConnected) preamble.remove();
  };

  const clearQueuedNotice = () => {
    if (!queuedNotice) return;
    queuedNotice = false;
    wrap.classList.remove("reply-queued");
    delete prose.dataset.i18n;
    prose.removeAttribute("data-i18n-vars");
    prose.textContent = "";
    prose.classList.add("cursor");
  };

  const clearRecovering = () => {
    recovering.hidden = true;
    recovering.textContent = "";
  };

  return {
    element: wrap,
    showQueued(position = 1) {
      queuedNotice = true;
      wrap.classList.add("reply-queued");
      prose.classList.remove("cursor");
      const key = position > 1 ? "queue.position" : "queue.waiting";
      const variables = position > 1 ? { position } : {};
      prose.dataset.i18n = key;
      prose.setAttribute("data-i18n-vars", JSON.stringify(variables));
      prose.textContent = t(key, variables);
      scrollToBottom();
    },
    startQueued() {
      if (!queuedNotice) return;
      prose.dataset.i18n = "queue.slotFree";
      prose.removeAttribute("data-i18n-vars");
      prose.textContent = t("queue.slotFree");
      scrollToBottom();
    },
    showRecovering() {
      clearQueuedNotice();
      recovering.dataset.i18n = "queue.recovering";
      recovering.textContent = t("queue.recovering");
      recovering.hidden = false;
      scrollToBottom();
    },
    pushPreamble(chunk) {
      clearQueuedNotice();
      clearRecovering();
      if (preamble.hidden) {
        preamble.hidden = false;
        announce(t("thinking.warmingAnnouncement"));
      }
      preambleText.textContent += chunk;
      scrollToBottom();
    },
    pushThought(t) {
      clearQueuedNotice();
      clearRecovering();
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
      clearQueuedNotice();
      clearRecovering();
      clearPreamble();
      settleThinking();
      full += t;
      scheduleRender();
    },
    finalize() {
      clearQueuedNotice();
      clearRecovering();
      clearPreamble(); // a turn that ended before the engine spoke leaves nothing behind
      settleThinking(); // a reply stopped mid-think still gets its label settled
      cancelRender();
      if (full.trim()) renderCompletedReply(wrap, prose, full);
      clearCursor(prose);
      scrollToBottom();
    },
    remove() {
      cancelRender();
      wrap.remove();
    },
    fail(message, translationKey = null, variables = {}) {
      wrap.classList.remove("reply-queued");
      queuedNotice = false;
      delete prose.dataset.i18n;
      prose.removeAttribute("data-i18n-vars");
      clearRecovering();
      settleThinking();
      cancelRender();
      if (!full) {
        if (translationKey) {
          prose.dataset.i18n = translationKey;
          prose.setAttribute("data-i18n-vars", JSON.stringify(variables));
        }
        prose.textContent = message;
      } else {
        // A partial reply exists: render it, but never let a truncated answer look finished —
        // append a visible incomplete marker instead of silently dropping the error.
        renderMarkdown(prose, full);
        const warn = document.createElement("div");
        warn.className = "reply-incomplete";
        const key = translationKey || (!message ? "reply.connectionLost" : null);
        if (key) {
          warn.dataset.i18n = key;
          warn.setAttribute("data-i18n-vars", JSON.stringify(variables));
        }
        warn.textContent = message || t("reply.connectionLost");
        prose.appendChild(warn);
      }
      clearCursor(prose);
    },
  };
}

function syncResourceSourcesLayout(box) {
  const container = box.closest(".msg.assistant");
  const list = box.querySelector(".resource-sources-list");
  if (!container || !list) return;
  container.style.minHeight = "";
  if (!resourceCitationRail.matches || list.hidden) {
    if (box.isConnected) scrollToBottom();
    return;
  }
  requestAnimationFrame(() => {
    if (!box.isConnected || !resourceCitationRail.matches || list.hidden) return;
    const railBottom = box.offsetTop + box.offsetHeight;
    if (railBottom > container.offsetHeight) {
      container.style.minHeight = `${Math.ceil(railBottom)}px`;
    }
    scrollToBottom();
  });
}

function setResourceSourcesExpanded(box, expanded) {
  const trigger = box.querySelector(".resource-sources-trigger");
  const list = box.querySelector(".resource-sources-list");
  const count = Number(box.dataset.sourceCount) || 0;
  list.hidden = !expanded;
  box.classList.toggle("is-expanded", expanded);
  trigger.setAttribute("aria-expanded", String(expanded));
  trigger.setAttribute(
    "aria-label",
    featureT(expanded ? "rag.hideSources" : "rag.showSources", { count }),
  );
  syncResourceSourcesLayout(box);
}

function renderResourceSources(container, sources) {
  const records = (Array.isArray(sources) ? sources : []).filter(
    (source) => source && source.resource_id && Number(source.page) >= 1,
  );
  if (!records.length || container.querySelector(".resource-sources")) return;
  const box = document.createElement("aside");
  box.className = "resource-sources";
  box.dataset.sourceCount = String(records.length);
  box.setAttribute("aria-label", featureT("rag.sources"));
  container.classList.add("has-resource-sources");

  const trigger = document.createElement("button");
  trigger.className = "resource-sources-trigger";
  trigger.type = "button";
  const listId = `resource-sources-${++renderResourceSources.sequence}`;
  trigger.setAttribute("aria-controls", listId);

  const book = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  book.setAttribute("viewBox", "0 0 24 24");
  book.setAttribute("aria-hidden", "true");
  const bookPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
  bookPath.setAttribute("d", "M4 4.5h6.2A2.8 2.8 0 0 1 13 7.3V20a3.3 3.3 0 0 0-2.8-1.5H4v-14Zm16 0h-4.2A2.8 2.8 0 0 0 13 7.3V20a3.3 3.3 0 0 1 2.8-1.5H20v-14Z");
  book.appendChild(bookPath);
  const heading = document.createElement("span");
  heading.className = "resource-sources-heading";
  heading.textContent = featureT("rag.sources");
  const count = document.createElement("span");
  count.className = "resource-sources-count";
  count.textContent = featureT(records.length === 1 ? "rag.sourceCountOne" : "rag.sourceCount", {
    count: records.length,
  });
  const chevron = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  chevron.classList.add("resource-sources-chevron");
  chevron.setAttribute("viewBox", "0 0 24 24");
  chevron.setAttribute("aria-hidden", "true");
  const chevronPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
  chevronPath.setAttribute("d", "m7 9.5 5 5 5-5");
  chevronPath.setAttribute("fill", "none");
  chevronPath.setAttribute("stroke", "currentColor");
  chevronPath.setAttribute("stroke-width", "1.8");
  chevronPath.setAttribute("stroke-linecap", "round");
  chevronPath.setAttribute("stroke-linejoin", "round");
  chevron.appendChild(chevronPath);
  trigger.append(book, heading, count, chevron);

  const list = document.createElement("ol");
  list.id = listId;
  list.className = "resource-sources-list";
  records.forEach((source, index) => {
    const variables = { title: source.title, page: source.page };
    const item = document.createElement("li");
    item.className = "resource-source-item";
    item.dataset.resourceCitation = String(index + 1);
    const link = document.createElement("a");
    link.className = "resource-source";
    link.href = resourcePageUrl(source.resource_id, source.page);
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.setAttribute("aria-label", featureT("rag.openPage", variables));
    const number = document.createElement("span");
    number.className = "resource-source-index";
    number.setAttribute("aria-hidden", "true");
    number.textContent = String(index + 1);
    const copy = document.createElement("span");
    copy.className = "resource-source-copy";
    const title = document.createElement("strong");
    title.dir = "auto";
    title.textContent = source.title;
    const meta = document.createElement("span");
    meta.className = "resource-source-meta";
    meta.textContent = featureT("rag.sourceMeta", { page: source.page });
    copy.append(title, meta);
    if (source.excerpt) {
      const excerpt = document.createElement("span");
      excerpt.className = "resource-source-excerpt";
      excerpt.dir = "auto";
      excerpt.textContent = source.excerpt;
      copy.appendChild(excerpt);
    }
    const arrow = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    arrow.classList.add("resource-source-arrow");
    arrow.setAttribute("viewBox", "0 0 24 24");
    arrow.setAttribute("aria-hidden", "true");
    const arrowPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
    arrowPath.setAttribute("d", "M9 7h8v8M17 7 7 17");
    arrowPath.setAttribute("fill", "none");
    arrowPath.setAttribute("stroke", "currentColor");
    arrowPath.setAttribute("stroke-width", "1.7");
    arrowPath.setAttribute("stroke-linecap", "round");
    arrowPath.setAttribute("stroke-linejoin", "round");
    arrow.appendChild(arrowPath);
    link.append(number, copy, arrow);
    item.appendChild(link);
    list.appendChild(item);
  });

  const setActive = (number, active) => {
    for (const element of container.querySelectorAll(`[data-resource-citation="${number}"]`)) {
      element.classList.toggle("is-active", active);
    }
  };
  for (const item of list.children) {
    const number = Number(item.dataset.resourceCitation);
    const link = item.querySelector("a");
    link.addEventListener("mouseenter", () => setActive(number, true));
    link.addEventListener("mouseleave", () => setActive(number, false));
    link.addEventListener("focus", () => setActive(number, true));
    link.addEventListener("blur", () => setActive(number, false));
  }

  trigger.addEventListener("click", () => {
    box.dataset.userToggled = "true";
    setResourceSourcesExpanded(box, trigger.getAttribute("aria-expanded") !== "true");
  });

  box.append(trigger, list);
  container.appendChild(box);
  setResourceSourcesExpanded(box, resourceCitationRail.matches);
  const markers = window.MutaCitations?.decorate(container.querySelector(".prose"), records, {
    hrefFor: (source) => resourcePageUrl(source.resource_id, source.page),
    labelFor: (source, number) => featureT("rag.citation", {
      number,
      title: source.title,
      page: source.page,
    }),
    copy: {
      previewLabel: (number) => featureT("rag.previewLabel", { number }),
      meta: (page) => featureT("rag.sourceMeta", { page }),
    },
    onActive: setActive,
  }) || [];
  const firstMarker = markers[0];
  if (firstMarker) {
    box.style.setProperty("--citation-anchor-y", `${Math.max(0, firstMarker.offsetTop - 8)}px`);
  }
  syncResourceSourcesLayout(box);
}
renderResourceSources.sequence = 0;

const resourceCitationRail = window.matchMedia("(min-width: 1580px)");
resourceCitationRail.addEventListener?.("change", ({ matches }) => {
  for (const box of document.querySelectorAll(".resource-sources")) {
    if (box.dataset.userToggled === "true") {
      syncResourceSourcesLayout(box);
      continue;
    }
    setResourceSourcesExpanded(box, matches);
  }
});

function renderHistoryMessage(m) {
  if (m.role === "user") {
    // Historical MessageOut rows do not yet carry their selected resource ids. Render the
    // mention treatment, but keep it inert instead of linking a re-uploaded same-name PDF.
    addUserMessage(m.content, m.attachments || []);
  } else if (m.role === "assistant") {
    hideEmptyState();
    const wrap = document.createElement("div");
    wrap.className = "msg assistant";
    const prose = document.createElement("div");
    prose.className = "prose";
    prose.dir = "auto";
    wrap.appendChild(prose);
    renderCompletedReply(wrap, prose, m.content);
    renderResourceSources(wrap, m.resource_citations);
    messagesEl.appendChild(wrap);
  }
}

// ---------------------------------------------------------------------------
// Telemetry strip
// ---------------------------------------------------------------------------
const fmt = {
  gb: (v) => (v == null ? "—" : v.toFixed(2) + " GB"),
  temp: (v) => (v == null ? "—" : Math.round(v)) + " °C",
  flag: (v) => (v == null ? "—" : v ? t("telemetry.yes") : t("telemetry.no")),
  tps: (v) => (v == null ? "—" : v.toFixed(1)) + " tok/s",
};

let latestTelemetry = null;

function updateTelemetry(telemetry) {
  latestTelemetry = telemetry;
  $("#telemetry").hidden = false;
  $("#t-ram").textContent = "RAM " + fmt.gb(telemetry.rss_gb);
  $("#t-peak").textContent = t("telemetry.peak") + " " + fmt.gb(telemetry.peak_rss_gb);
  $("#t-temp").textContent = fmt.temp(telemetry.cpu_temp_c);
  const th = $("#t-throttle");
  th.textContent = t("telemetry.throttle") + " " + fmt.flag(telemetry.throttled);
  th.classList.toggle("hot", telemetry.throttled === true);
  $("#t-tps").textContent = fmt.tps(telemetry.tokens_per_second);
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
      const open = document.createElement("button");
      open.type = "button";
      open.className = "conv-open";
      const title = document.createElement("span");
      title.className = "conv-title";
      const displayTitle = c.title || t("conversation.untitled");
      title.textContent = displayTitle;
      open.setAttribute("aria-label", t("conversation.open", { title: displayTitle }));
      if (c.id === conversationId) open.setAttribute("aria-current", "page");
      if (backgroundJob) {
        const dot = document.createElement("span");
        dot.className = "conv-generating" + (backgroundJob.state === "queued" ? " queued" : "");
        dot.title = backgroundJob.state === "queued"
          ? t("queue.waitingSlot", {
            position: backgroundJob.queuePosition ? ` #${backgroundJob.queuePosition}` : "",
          })
          : t("conversation.background");
        open.appendChild(dot);
      }
      open.appendChild(title);
      open.addEventListener("click", () => loadConversation(c.id));
      const del = document.createElement("button");
      del.type = "button";
      del.className = "conv-del";
      del.textContent = "✕";
      del.title = t("conversation.delete");
      del.setAttribute("aria-label", t("conversation.delete"));
      del.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        if (backgroundJob) await stopGeneration(backgroundJob);
        discardQueue(c.id, { announce: false });
        await fetch(`/v1/conversations/${c.id}`, { method: "DELETE", headers: authHeaders() });
        if (c.id === conversationId) newChat();
        refreshSidebar();
      });
      item.append(open, del);
      list.appendChild(item);
    }
  } catch {
    /* sidebar is a convenience; the chat keeps working without it */
  }
}

function scheduleConversationRetry(cid) {
  clearTimeout(conversationRetryTimer);
  conversationRetryTarget = cid;
  conversationRetryTimer = setTimeout(() => {
    conversationRetryTimer = null;
    // A retry belongs to the URL the student refreshed. Back/Forward or a deliberate click
    // cancels it implicitly, so a recovered gateway can never pull the UI to an old chat.
    if (
      conversationRetryTarget !== cid ||
      conversationFromLocation() !== cid ||
      conversationId === cid
    ) return;
    void loadConversation(cid, {
      historyMode: "none",
      attempts: 6,
      retryUnavailable: true,
      quietUnavailable: true,
    });
  }, 2000);
}

async function loadConversation(
  cid,
  {
    historyMode = "push",
    attempts = 1,
    retryUnavailable = false,
    quietUnavailable = false,
  } = {},
) {
  if (conversationRetryTarget && conversationRetryTarget !== cid) {
    clearTimeout(conversationRetryTimer);
    conversationRetryTimer = null;
    conversationRetryTarget = null;
  }
  if (voiceModeActive) {
    setConversationLocation(conversationId, { mode: "replace" });
    toast(t("conversation.voiceChanging"));
    return null;
  }
  const requestedNavigation = ++navigationVersion;
  pendingConversationLoad = cid;
  // Keep a reference even if finishGeneration removes it from the Map while history is in
  // flight. That history snapshot may contain only a partial assistant row.
  const targetJobBeforeLoad = jobForConversation(cid);
  let r = null;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const candidate = await fetch(`/v1/conversations/${cid}/messages`, {
        headers: authHeaders(),
      });
      if (candidate.ok || candidate.status === 404) {
        r = candidate;
        break;
      }
    } catch {
      /* A refresh can race a brief gateway/model restart; retry without changing the URL. */
    }
    if (requestedNavigation !== navigationVersion) return null;
    if (attempt + 1 < attempts) {
      await new Promise((resolve) => setTimeout(resolve, 400));
    }
  }
  // A slower A load must never overwrite a newer B click or Back/Forward navigation.
  if (requestedNavigation !== navigationVersion) return null;
  if (!r) {
    pendingConversationLoad = null;
    // A 5xx/network outage says nothing about whether this chat exists. Preserve the selected
    // URL and keep trying in the background; only a definitive 404 may clear it.
    if (retryUnavailable) scheduleConversationRetry(cid);
    if (!quietUnavailable) toast(t("conversation.unavailable"));
    return null;
  }
  if (r.status === 404) {
    pendingConversationLoad = null;
    conversationRetryTarget = null;
    setConversationLocation(conversationId, { mode: "replace" });
    toast(t("conversation.notFound"));
    return false;
  }
  const body = await r.json();
  if (requestedNavigation !== navigationVersion) return null;
  // Commit the navigation only after its history arrived. Until here, the previous stream
  // remains attached and visible if the target request fails.
  const leaving = jobForConversation();
  if (leaving) {
    leaving.handle = null;
    leaving.telemetryOpened = false;
  }
  closeTelemetry(0);
  conversationId = cid;
  pendingConversationLoad = null;
  clearTimeout(conversationRetryTimer);
  conversationRetryTimer = null;
  conversationRetryTarget = null;
  currentViewId = newViewId();
  setConversationLocation(cid, { mode: historyMode });
  window.MutaViz?.cleanup(messagesEl);
  messagesEl.replaceChildren();
  const restoring = targetJobBeforeLoad || jobForConversation(cid);
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
    if (restoring.state !== "queued") {
      openTelemetry(restoring.cid);
      restoring.telemetryOpened = true;
    }
  }
  refreshSidebar();
  renderQueue();
  syncComposerState(); // the send button is only a Stop button in the streaming thread
  scrollToBottom({ force: true });
  if (!restoring) drainQueue(cid);
  return true;
}

/** Re-render one in-flight reply into a fresh bubble and point its subscription at it. */
function reattachJob(job) {
  const handle = beginAssistantMessage(null); // no "Answer now" on a resumed view
  if (job.state === "queued") handle.showQueued(job.queuePosition);
  else if (job.preamble) handle.pushPreamble(job.preamble);
  if (job.reasoning) handle.pushThought(job.reasoning);
  if (job.content) handle.pushDelta(job.content);
  if (job.recovering) handle.showRecovering();
  job.handle = handle;
  if (job.source) decorateCompletedReply(job, { source: job.source });
  // Replay can finish while the history request is still in flight. In that ordering the
  // terminal event had no view handle to settle, so settle the freshly attached bubble now.
  if (job.terminal) {
    if (job.failed) handle.fail(t("reply.couldNotFinish"), "reply.couldNotFinish");
    else handle.finalize();
  }
}

function newChat({ historyMode = "push" } = {}) {
  clearTimeout(conversationRetryTimer);
  conversationRetryTimer = null;
  conversationRetryTarget = null;
  if (voiceModeActive) {
    setConversationLocation(conversationId, { mode: "replace" });
    return toast(t("conversation.voiceChanging"));
  }
  navigationVersion += 1;
  pendingConversationLoad = null;
  const leaving = jobForConversation();
  if (leaving) {
    leaving.handle = null;
    leaving.telemetryOpened = false;
  }
  closeTelemetry(0);
  conversationId = null;
  currentViewId = newViewId();
  setConversationLocation(null, { mode: historyMode });
  pendingAttachments = [];
  renderChips();
  window.MutaViz?.cleanup(messagesEl);
  messagesEl.replaceChildren();
  emptyStateEl.style.display = "";
  renderQueue();
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
  const modelTrigger = $("#model-trigger");
  const switchingModel = modelTrigger?.dataset.switching === "true";
  $("#btn-image").disabled = busy || switchingModel;
  $("#btn-audio").disabled = switchingModel;
  $("#btn-mic").disabled = switchingModel;
  // During a chat stream the send button *is* the stop button, so it stays enabled. During a
  // voice reply (generating without a chat stream) the mic button owns interruption.
  sendBtn.disabled =
    !identityReady ||
    switchingModel ||
    busy ||
    voiceModeActive ||
    startingConversations.has(startKeyFor(conversationId));
  sendBtn.classList.toggle("stop", Boolean(streaming));
  sendBtn.title = streaming ? t("composer.stop") : t("composer.send");
  sendBtn.setAttribute("aria-label", streaming ? t("composer.stop") : t("composer.sendMessage"));
  if (modelTrigger) {
    const inspectable = modelCatalog !== null || modelTrigger.dataset.loadFailed === "true";
    modelTrigger.disabled = !inspectable;
    modelTrigger.setAttribute("aria-disabled", String(modelTrigger.disabled));
    modelTrigger.setAttribute("aria-busy", String(switchingModel));
    $("#model-options")?.querySelectorAll(".model-option").forEach((option) => {
      option.disabled = switchingModel
        || anyGeneration()
        || option.dataset.selectable !== "true";
    });
    if (modelTrigger.disabled && !$("#model-menu")?.hidden) setModelMenuOpen(false);
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
    toast(t("reply.stopFailed"));
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
      chip.append(a.kind === "audio" ? `🎙 ${t("attachment.audio")}` : `📎 ${t("attachment.file")}`);
    }
    if (a.status === "reading" || a.status === "failed") {
      // Durable, not a toast that has already faded: this is the only signal that tells the
      // student whether the tutor can actually see what they attached.
      const label = document.createElement("span");
      label.className = "chip-status";
      label.textContent = a.status === "reading" ? t("attachment.reading") : t("attachment.readFailed");
      if (a.detailKey) label.title = t(a.detailKey);
      else if (a.detail) label.title = a.detail;
      chip.appendChild(label);
    }
    const x = document.createElement("button");
    x.type = "button";
    x.className = "x";
    x.textContent = "✕";
    x.title = t("attachment.remove");
    x.setAttribute("aria-label", t("attachment.remove"));
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

  const settle = (status, detailKey = null) => {
    entry.status = status;
    entry.detailKey = detailKey;
    renderChips();
  };

  let body;
  try {
    const r = await fetch("/v1/tutor/vision", { method: "POST", body: form });
    body = await r.json();
  } catch {
    settle("failed", "attachment.imageUploadFailed");
    return toast(t("attachment.imageUploadFailed"));
  }
  entry.id = body.attachment_id ?? null;
  if (body.accepted && body.transcription) {
    entry.transcription = body.transcription;
    settle("ready");
    toast(t("attachment.imageRead"), 3000);
  } else if (body.accepted) {
    // The reader ran but saw nothing it could transcribe — a camera problem, not a system
    // problem. Say so: "couldn't be read" sends the student hunting for a bug that isn't there.
    settle("failed", "attachment.photoEmpty");
    toast(t("attachment.photoEmpty"));
  } else {
    settle("failed", "attachment.imageUnreadable");
    toast(t("attachment.imageUnreadable"));
  }
}

async function addAudio(file) {
  toast(t("attachment.transcribing"), 3000);
  const form = new FormData();
  if (conversationId) form.append("conversation_id", conversationId);
  form.append("student_id", studentId); // owner, so the stored recording is scoped to us
  form.append("audio", file);
  let body;
  try {
    const r = await fetch("/v1/audio/transcribe", { method: "POST", body: form });
    if (r.status === 503) {
      return toast(t("attachment.speechUnavailable"));
    }
    body = await r.json();
  } catch {
    return toast(t("attachment.audioUploadFailed"));
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
    toast(t("attachment.heardNothing"));
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
    if (!settingsModal.hidden) return;
    if (appEl?.classList.contains("sidebar-open")) {
      setDrawer(false);
      menuToggle?.focus();
      return;
    }
    hideDropHint();
    const modelMenuEl = $("#model-menu");
    if (modelMenuEl && !modelMenuEl.hidden) {
      setModelMenuOpen(false);
      $("#model-trigger")?.focus();
      return;
    }
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
    else if (file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")) {
      void uploadResource(file);
    }
    else toast(t("attachment.unknownFile", { file: file.name }));
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
const MESSAGE_QUEUE_STORAGE_KEY = "muta-message-queue";

function persistMessageQueue() {
  try {
    if (messageQueue.length) {
      sessionStorage.setItem(MESSAGE_QUEUE_STORAGE_KEY, JSON.stringify(messageQueue));
    } else {
      sessionStorage.removeItem(MESSAGE_QUEUE_STORAGE_KEY);
    }
  } catch {
    /* Storage can be disabled; the in-memory queue still works for this page lifetime. */
  }
}

function restoreMessageQueue() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(MESSAGE_QUEUE_STORAGE_KEY) || "[]");
    if (!Array.isArray(saved)) return;
    // Browser storage is untrusted input. Keep only the small, serialisable shape dispatch()
    // understands, and bound it to the same maximum as the server-side waiting room.
    messageQueue = saved.slice(0, 32).flatMap((item) => {
      if (!item || typeof item.typed !== "string" || typeof item.cid !== "string") return [];
      const attachments = Array.isArray(item.attachments)
        ? item.attachments.filter((a) => a && typeof a === "object").slice(0, 8)
        : [];
      const ragResources = Array.isArray(item.ragResources)
        ? item.ragResources
            .filter((resource) => resource && typeof resource.id === "string" && typeof resource.name === "string")
            .map((resource) => ({
              id: resource.id,
              name: window.MutaResourceMentions.nameFor(resource),
            }))
            .slice(0, 8)
        : [];
      return [{
        typed: item.typed.slice(0, 4096),
        attachments,
        useRag: item.useRag === true,
        ragResources,
        useWeb: item.useWeb === true,
        cid: item.cid,
        conflictRetries: Math.min(2, Math.max(0, Number(item.conflictRetries) || 0)),
      }];
    });
  } catch {
    messageQueue = [];
    sessionStorage.removeItem(MESSAGE_QUEUE_STORAGE_KEY);
  }
  persistMessageQueue();
}

function pendingStartsFor(cid) {
  const matches = [];
  for (let index = 0; index < sessionStorage.length; index += 1) {
    const key = sessionStorage.key(index);
    if (!key?.startsWith("muta-pending:")) continue;
    try {
      const marker = JSON.parse(sessionStorage.getItem(key) || "null");
      if (marker?.conversation_id === cid) matches.push(key.slice("muta-pending:".length));
    } catch {
      /* Legacy blank-chat markers are recovered from the pending URL, not from this list. */
    }
  }
  return matches;
}

function queueMessage(item, cid, { front = false } = {}) {
  const queued = { ...item, cid };
  if (front) messageQueue.unshift(queued);
  else messageQueue.push(queued);
  persistMessageQueue();
  renderQueue();
}

function renderQueue() {
  const box = $("#queue");
  box.innerHTML = "";
  const visible = messageQueue.filter((item) => item.cid === conversationId);
  box.hidden = visible.length === 0;
  visible.forEach((item) => {
    const row = document.createElement("div");
    row.className = "queued";
    const label = document.createElement("span");
    label.className = "queued-text";
    const imgs = item.attachments.filter((a) => a.kind === "image").length;
    const resourceNames = (item.ragResources || [])
      .map((resource) => window.MutaResourceMentions.nameFor(resource))
      .join(", ");
    const queuedText = item.typed || (resourceNames
      ? featureT("rag.document", { name: resourceNames })
      : t("queue.fromImage"));
    label.textContent = (imgs ? `🖼 ` : "") + queuedText;
    const x = document.createElement("button");
    x.type = "button";
    x.className = "x";
    x.textContent = "✕";
    x.title = t("queue.dontSend");
    x.setAttribute("aria-label", t("queue.dontSend"));
    x.addEventListener("click", () => {
      messageQueue = messageQueue.filter((q) => q !== item);
      persistMessageQueue();
      renderQueue();
    });
    row.append(label, x);
    box.appendChild(row);
  });
}

function discardQueue(cid = conversationId, { announce = true } = {}) {
  const removed = messageQueue.filter((item) => item.cid === cid).length;
  if (removed && announce) {
    toast(t(removed > 1 ? "queue.discardedMany" : "queue.discardedOne", { count: removed }));
  }
  messageQueue = messageQueue.filter((item) => item.cid !== cid);
  persistMessageQueue();
  renderQueue();
}

function drainQueue(cid = conversationId) {
  if (!cid || voiceGenerating || jobForConversation(cid) || startingConversations.has(startKeyFor(cid))) {
    return;
  }
  const index = messageQueue.findIndex((item) => item.cid === cid);
  if (index < 0) return;
  const [next] = messageQueue.splice(index, 1);
  persistMessageQueue();
  renderQueue();
  dispatch(next, {
    conversationOverride: cid,
    viewOverride: conversationId === cid ? currentViewId : newViewId(),
  });
}

function restoreDraft(item) {
  inputEl.value = item.typed;
  pendingAttachments = item.attachments;
  useRag = item.useRag === true;
  selectedRagResources = (item.ragResources || []).slice(0, MAX_SELECTED_RAG_RESOURCES);
  useWeb = item.useWeb === true;
  ragButton.classList.toggle("active", useRag);
  ragButton.setAttribute("aria-pressed", String(useRag));
  $("#btn-web").classList.toggle("active", useWeb);
  $("#btn-web").setAttribute("aria-pressed", String(useWeb));
  renderChips();
  renderRagChips();
  autoGrow();
}

function send(steer = false) {
  if (!identityReady) return toast(t("reply.openingChats"));
  if (voiceModeActive) return toast(t("reply.voiceTyped"));
  if ($("#model-trigger")?.dataset.switching === "true") {
    return toast(t("reply.modelLoading"));
  }
  const typed = inputEl.value.trim();
  if (readingAnImage()) return toast(t("reply.imageReading"));
  if (
    !typed &&
    !pendingAttachments.some((a) => a.transcription) &&
    !(useRag && selectedRagResources.length)
  ) return;
  if (startingConversations.has(startKeyFor(conversationId))) {
    return toast(t("reply.previousStarting"));
  }

  const ragResources = useRag ? resourcesFromTypedMentions(typed) : [];
  if (ragResources.length > MAX_SELECTED_RAG_RESOURCES) {
    return toast(featureT("rag.maxFiles", { count: MAX_SELECTED_RAG_RESOURCES }), 4000);
  }
  if (useRag && !ragResources.length) return toast(featureT("rag.chooseFile"), 4000);
  const item = {
    typed,
    attachments: pendingAttachments.slice(),
    useRag,
    ragResources,
    useWeb,
  };
  pendingAttachments = [];
  selectedRagResources = [];
  renderChips();
  renderRagChips();
  inputEl.value = "";
  autoGrow();

  const currentJob = viewingLiveStream();
  if (currentJob) {
    // Human in the loop: Enter while the tutor talks queues the message; Ctrl+Enter steers —
  // it cuts the current reply short (partial is persisted) and sends this message next,
    // ahead of anything already queued. A voice reply can't be stopped from the keyboard
    // (the mic button owns barge-in), so steering degrades to queueing there.
    if (steer) {
      queueMessage(item, currentJob.cid, { front: true });
      stopGeneration(currentJob); // finishGeneration drains the correction straight away
    } else {
      queueMessage(item, currentJob.cid);
    }
    return;
  }
  if (voiceGenerating) {
    if (conversationId) queueMessage(item, conversationId);
    else restoreDraft(item);
    return;
  }
  if (!allowParallelChats && generationJobs.size) {
    restoreDraft(item);
    return toast(t("reply.parallelDisabled"));
  }
  dispatch(item);
}

async function dispatch(item, opts = {}) {
  const {
    regenerate = false,
    thinking = thinkingLevel,
    conversationOverride = conversationId,
    viewOverride = currentViewId,
    clientRequestId = newStudentId(),
  } = opts;
  const mentionedText = window.MutaResourceMentions?.append(item.typed, item.ragResources) ||
    item.typed;
  const message = composeOutgoingMessage(mentionedText, item.attachments);
  const attachmentIds = item.attachments.map((a) => a.id).filter((id) => id != null);
  const startedIn = conversationOverride;
  const startedView = viewOverride;
  const startKey = startKeyFor(startedIn, startedView);
  if (startingConversations.has(startKey) || jobForConversation(startedIn)) return;

  // A regenerate ("answer now") re-answers the turn already on screen, so it neither adds a
  // new user bubble nor re-links attachments — the backend re-runs the last user turn.
  const renderingHere = currentViewId === startedView;
  if (!regenerate && renderingHere) {
    addUserMessage(mentionedText || t("queue.fromImage"), item.attachments, item.ragResources);
  }
  // "Answer now" is offered while the tutor is thinking: it cancels this stream and asks for
  // a direct answer to the same question. Not offered on a regenerate (it is already the
  // direct answer — thinking is off — so it can't loop).
  let job = null;
  let startRejected = false;
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
  // Every start is idempotently discoverable by client_request_id. Keep the marker until a
  // definitive response or successful recovery — existing-conversation starts can lose their
  // POST response during refresh just as easily as brand-new chats can.
  sessionStorage.setItem(
    `muta-pending:${clientRequestId}`,
    JSON.stringify({ conversation_id: startedIn }),
  );
  if (startedIn == null && renderingHere) {
    setPendingLocation(clientRequestId);
  }
  syncComposerState();

  try {
    const res = await fetch("/v1/chat/generations", {
      method: "POST",
      headers: { "content-type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        student_id: studentId,
        message,
        conversation_id: startedIn,
        client_request_id: clientRequestId,
        attachment_ids: regenerate ? [] : attachmentIds,
        use_web: item.useWeb === true,
        use_rag: item.useRag === true,
        resource_ids: (item.ragResources || [])
          .slice(0, MAX_SELECTED_RAG_RESOURCES)
          .map((resource) => resource.id),
        thinking,
        regenerate,
        // Response-language preference is trusted request metadata. Never prefix or rewrite
        // `message`: the gateway puts this value in the system prompt instead.
        language: window.MutaI18n.responseLanguage,
      }),
    });
    if (!res.ok) {
      startRejected = true;
      const detail = (await res.json().catch(() => ({}))).detail;
      // The page may have missed recovery during a transient startup failure. If the gateway
      // says this thread is already replying, adopt that server job and retain this follow-up
      // instead of rendering a dead-end error or asking the student to type "continue" again.
      if (
        res.status === 409 &&
        startedIn &&
        !regenerate &&
        typeof detail === "string" &&
        detail.includes("reply is already running")
      ) {
        await recoverGenerations({ attempts: 4, delayMs: 400 });
        const existing = jobForConversation(startedIn);
        if (existing) {
          sessionStorage.removeItem(`muta-pending:${clientRequestId}`);
          queueMessage(item, startedIn);
          assistant?.remove();
          if (currentViewId === startedView) {
            await loadConversation(startedIn, { historyMode: "none" });
          }
          toast(t("reply.earlierRunning"), 5000);
          // If that reply finished during the canonical history load, its normal drain ran
          // while this rejected start key was still held. Retry once the finally block frees it.
          setTimeout(() => drainQueue(startedIn), 0);
          return;
        }
        const retries = item.conflictRetries || 0;
        sessionStorage.removeItem(`muta-pending:${clientRequestId}`);
        queueMessage(
          { ...item, conflictRetries: retries < 2 ? retries + 1 : 0 },
          startedIn,
          { front: true },
        );
        assistant?.remove();
        if (currentViewId === startedView) {
          await loadConversation(startedIn, { historyMode: "none" });
        }
        toast(t("reply.earlierFinishing"), 5000);
        setTimeout(async () => {
          await recoverGenerations({ attempts: 4, delayMs: 500 });
          if (!jobForConversation(startedIn)) drainQueue(startedIn);
        }, retries < 2 ? 500 : 2000);
        return;
      }
      if (assistant) {
        if (typeof detail === "string" && (res.status === 404 || res.status === 409)) {
          assistant.fail(detail);
        } else {
          const variables = { status: res.status };
          assistant.fail(t("reply.httpAnswerFailed", variables), "reply.httpAnswerFailed", variables);
        }
      }
      return;
    }
    const started = await res.json();
    const stillHere = currentViewId === startedView;
    const returnedToConversation =
      !stillHere &&
      startedIn != null &&
      (conversationId === started.conversation_id ||
        pendingConversationLoad === started.conversation_id);
    if (stillHere) {
      conversationId = started.conversation_id;
      // The first persisted id replaces the blank-new-chat URL immediately, before any
      // tokens arrive, so even an instant refresh returns to the correct conversation.
      setConversationLocation(conversationId, { mode: "replace" });
    }
    sessionStorage.removeItem(`muta-pending:${clientRequestId}`);
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
      recovering: null,
      source: null,
      clientRequestId: started.client_request_id || clientRequestId,
      state: started.state || "running",
      queuePosition: started.queue_position || 0,
    };
    generationJobs.set(job.id, job);
    if (job.state === "queued") {
      job.handle?.showQueued(job.queuePosition);
      toast(t("queue.automatic"), 5000);
    }
    refreshSidebar();
    // Begin the replacement load first so it captures this job synchronously, before a very
    // short generation can finish and leave an older in-flight history snapshot behind.
    if (returnedToConversation) void loadConversation(job.cid, { historyMode: "none" });
    void followGeneration(job);
  } catch {
    const recovered = await recoverPendingGeneration(clientRequestId, {
      navigate: true,
      fallbackConversation: startedIn,
      expectedViewId: startedView,
    });
    if (!recovered && assistant) {
      assistant.fail(t("reply.startFailed"), "reply.startFailed");
    }
  } finally {
    if (startRejected) sessionStorage.removeItem(`muta-pending:${clientRequestId}`);
    if (startRejected && currentViewId === startedView && startedIn == null) {
      setConversationLocation(null, { mode: "replace" });
    }
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
        toast(t("reply.reconnecting"));
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
        if (ev.queued === true && !ev.done) {
          job.state = "queued";
          job.queuePosition = ev.queue_position || 1;
          job.handle?.showQueued(job.queuePosition);
          refreshSidebar();
        } else if (ev.started) {
          job.state = "running";
          job.queuePosition = 0;
          job.handle?.startQueued();
          refreshSidebar();
        } else if (ev.recovering) {
          job.recovering = true;
          job.handle?.showRecovering();
        } else if (ev.source && !ev.done) {
          if (ev.source === "cloud") job.source = "cloud";
          decorateCompletedReply(job, { source: job.source || ev.source });
        } else if (ev.preamble) {
          job.recovering = null;
          job.preamble += ev.preamble;
          job.handle?.pushPreamble(ev.preamble);
        } else if (ev.reasoning) {
          job.recovering = null;
          job.reasoning += ev.reasoning;
          job.handle?.pushThought(ev.reasoning);
        } else if (ev.delta) {
          job.recovering = null;
          job.content += ev.delta;
          job.handle?.pushDelta(ev.delta);
        } else if (ev.error) {
          job.failed = true;
          job.error = true;
          job.handle?.fail(t("reply.couldNotFinish"), "reply.couldNotFinish");
        } else if (ev.done) {
          job.terminal = true;
          if (ev.stopped && job.pendingRegen) job.handle?.remove();
          else if (ev.stopped) job.handle?.fail(t("reply.stopped"), "reply.stopped");
          else if (!job.failed) job.handle?.finalize();
          decorateCompletedReply(job, { ...ev, source: ev.source || job.source });
          if (conversationId === job.cid) announce(t("reply.tutorReplied"));
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
  const allSources = Array.isArray(ev.sources) ? ev.sources : [];
  const resourceSources = allSources.filter((source) => source?.resource_id);
  const webSources = allSources.filter((source) => source?.url && !source?.resource_id);
  renderResourceSources(last, resourceSources);
  if (webSources.length && !last.querySelector(".sources")) {
    const box = document.createElement("div");
    box.className = "sources";
    const heading = document.createElement("span");
    heading.dataset.i18n = "badge.sources";
    heading.textContent = t("badge.sources");
    box.append(heading);
    webSources.forEach((source, i) => {
      const safe = safeHttpUrl(source.url);
      const link = document.createElement(safe ? "a" : "span");
      link.dir = "auto";
      if (safe) {
        link.href = safe;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
      }
      link.textContent = `[${i + 1}] ${source.title}`;
      box.appendChild(link);
      if (i < webSources.length - 1) box.append(" · ");
    });
    last.appendChild(box);
  }
  if (ev.source === "cloud" && !last.querySelector(".src-badge")) {
    const badge = document.createElement("span");
    badge.className = "src-badge";
    badge.dataset.i18n = "badge.cloud";
    badge.textContent = t("badge.cloud");
    last.appendChild(badge);
  }
  if (ev.check_note) {
    const warn = document.createElement("div");
    warn.className = "reply-incomplete";
    warn.dataset.i18n = "badge.checkFailed";
    warn.textContent = t("badge.checkFailed");
    last.querySelector(".prose")?.appendChild(warn);
  } else if (ev.verified === true && !last.querySelector(".verified-badge")) {
    const badge = document.createElement("span");
    badge.className = "verified-badge";
    badge.dataset.i18n = "badge.verified";
    badge.setAttribute("data-i18n-title", "badge.verifiedTitle");
    badge.textContent = t("badge.verified");
    badge.title = t("badge.verifiedTitle");
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
      viewOverride: conversationId === job.cid ? currentViewId : newViewId(),
    });
  } else {
    drainQueue(job.cid);
  }
}

function recoveredJob(active, clientRequestId = active.client_request_id || null) {
  return {
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
    recovering: null,
    source: null,
    clientRequestId,
    state: active.state || "running",
    queuePosition: active.queue_position || 0,
  };
}

async function recoverGenerations({ attempts = 6, delayMs = 400 } = {}) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetch("/v1/chat/generations", { headers: authHeaders() });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const body = await response.json();
      for (const active of body.generations || []) {
        if (active.client_request_id) {
          sessionStorage.removeItem(`muta-pending:${active.client_request_id}`);
        }
        if (generationJobs.has(active.job_id)) continue;
        const job = recoveredJob(active);
        generationJobs.set(job.id, job);
        void followGeneration(job);
      }
      syncComposerState();
      return true;
    } catch {
      if (attempt + 1 < attempts) {
        await new Promise((resolve) => setTimeout(resolve, delayMs));
      }
    }
  }
  // A transient boot failure must not become permanent for this page. The next dispatch also
  // performs targeted recovery if the gateway reports an already-running conversation.
  return false;
}

async function recoverPendingGeneration(
  clientRequestId,
  { navigate = true, fallbackConversation = null, expectedViewId = null, quiet = false } = {},
) {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      const response = await fetch(
        `/v1/chat/generations?client_request_id=${encodeURIComponent(clientRequestId)}`,
        { headers: authHeaders() },
      );
      if (response.ok) {
        const body = await response.json();
        const active = body.generations?.[0];
        if (active) {
          let job = generationJobs.get(active.job_id);
          let created = false;
          if (!job) {
            job = recoveredJob(active, clientRequestId);
            generationJobs.set(job.id, job);
            created = true;
          }
          sessionStorage.removeItem(`muta-pending:${clientRequestId}`);
          // Polling can last 20 seconds. Re-evaluate the view when the match arrives so an old
          // recovery cannot yank the student back from a chat they deliberately navigated to;
          // conversely, attach if they have since returned to this conversation.
          const returnedToConversation =
            conversationId === active.conversation_id ||
            pendingConversationLoad === active.conversation_id;
          const pendingBlankStillVisible =
            fallbackConversation == null && pendingRequestFromLocation() === clientRequestId;
          const expectedViewStillVisible =
            expectedViewId == null || currentViewId === expectedViewId;
          const shouldAttach = returnedToConversation ||
            (navigate && expectedViewStillVisible &&
              (fallbackConversation != null || pendingBlankStillVisible));
          if (shouldAttach) {
            conversationId = active.conversation_id;
            setConversationLocation(conversationId, { mode: "replace" });
            // Start the canonical history load while the recovered job is definitely retained
            // in the Map; this closes the short-completion snapshot race on refresh.
            const loading = loadConversation(conversationId, { historyMode: "none" });
            if (created) void followGeneration(job);
            await loading;
          } else if (created) {
            void followGeneration(job);
          }
          return true;
        }
      }
    } catch {
      /* the original start may still be crossing the refresh; keep polling briefly */
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  sessionStorage.removeItem(`muta-pending:${clientRequestId}`);
  if (
    navigate &&
    fallbackConversation == null &&
    pendingRequestFromLocation() === clientRequestId &&
    (expectedViewId == null || currentViewId === expectedViewId)
  ) {
    setConversationLocation(null, { mode: "replace" });
    currentViewId = newViewId();
  }
  if (!quiet) toast(t("reply.didNotStart"));
  return false;
}

sendBtn.addEventListener("click", () => {
  // While a chat stream runs the button is Stop; Enter still queues (see send()).
  if (viewingLiveStream()) stopGeneration();
  else send();
});
inputEl.addEventListener("keydown", (e) => {
  if (!mentionMenu.hidden) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const direction = e.key === "ArrowDown" ? 1 : -1;
      let next = mentionActiveIndex;
      for (let count = 0; count < mentionMatches.length; count += 1) {
        next = (next + direction + mentionMatches.length) % mentionMatches.length;
        if (mentionMatches[next]?.status === "ready") break;
      }
      mentionActiveIndex = next;
      renderMentionMenu();
      mentionMenu.querySelector(".resource-option.active")?.scrollIntoView({ block: "nearest" });
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      closeMentionMenu();
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      if (mentionMatches[mentionActiveIndex]?.status === "ready") {
        selectMention(mentionMatches[mentionActiveIndex]);
      }
      return;
    }
  }
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
  scrollIfFollowing: () => scrollToBottom(),
  isGenerating: anyGeneration,
  setVoiceActive: (v) => {
    voiceModeActive = v;
    syncComposerState();
  },
  setGenerating: (v) => {
    voiceGenerating = v;
    syncComposerState();
    if (!v) drainQueue(); // a message typed during a voice reply goes out when it ends
  },
};

// --- learner PDF resources + @ picker -------------------------------------------------
const ragButton = $("#btn-rag");
const ragChips = $("#rag-resource-chips");
const mentionMenu = $("#resource-mention-menu");
const mentionStatus = $("#resource-mention-status");
const resourceList = $("#resource-list");

function resourceStatusLabel(resource) {
  return featureT(`resources.${resource.status || "processing"}`);
}

function renderRagChips() {
  ragChips.innerHTML = "";
  ragChips.hidden = !useRag || selectedRagResources.length === 0;
  selectedRagResources.forEach((resource) => {
    const displayName = window.MutaResourceMentions.nameFor(resource);
    const chip = document.createElement("span");
    chip.className = "rag-chip";
    chip.title = displayName;
    chip.setAttribute("aria-label", featureT("rag.document", { name: displayName }));
    const label = document.createElement("span");
    label.className = "rag-chip-label";
    label.dir = "auto";
    label.textContent = displayName;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.setAttribute("aria-label", featureT("rag.remove", { name: displayName }));
    const removeIcon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    removeIcon.setAttribute("viewBox", "0 0 24 24");
    removeIcon.setAttribute("aria-hidden", "true");
    const removePath = document.createElementNS("http://www.w3.org/2000/svg", "path");
    removePath.setAttribute("d", "m7 7 10 10M17 7 7 17");
    removePath.setAttribute("fill", "none");
    removePath.setAttribute("stroke", "currentColor");
    removePath.setAttribute("stroke-width", "1.8");
    removePath.setAttribute("stroke-linecap", "round");
    removeIcon.appendChild(removePath);
    remove.appendChild(removeIcon);
    remove.addEventListener("click", () => {
      selectedRagResources = selectedRagResources.filter((item) => item.id !== resource.id);
      renderRagChips();
    });
    chip.append(resourceDocumentIcon("rag-chip-icon"), label, remove);
    ragChips.appendChild(chip);
  });
}

function closeMentionMenu() {
  const wasOpen = !mentionMenu.hidden;
  mentionMenu.hidden = true;
  mentionMatches = [];
  mentionActiveIndex = 0;
  inputEl.removeAttribute("aria-activedescendant");
  if (wasOpen) mentionStatus.textContent = featureT("rag.pickerClosed");
}

function mentionTrigger() {
  if (!useRag) return null;
  const caret = inputEl.selectionStart;
  const before = inputEl.value.slice(0, caret);
  const at = before.lastIndexOf("@");
  if (at < 0 || /[}\n]/.test(before.slice(at + 1))) return null;
  const prefix = before.slice(at + 1).replace(/^\{/, "");
  // Do not turn an email-like token into a resource picker.
  if (!window.MutaResourceMentions.hasTriggerBoundary(inputEl.value, at)) return null;
  return { at, caret, query: prefix.trim().toLowerCase() };
}

function selectMention(resource) {
  const trigger = mentionTrigger();
  if (!trigger || resource.status !== "ready") return;
  const alreadySelected = selectedRagResources.some((item) => item.id === resource.id);
  if (!alreadySelected && selectedRagResources.length >= MAX_SELECTED_RAG_RESOURCES) {
    closeMentionMenu();
    toast(featureT("rag.maxFiles", { count: MAX_SELECTED_RAG_RESOURCES }), 4000);
    inputEl.focus();
    return;
  }
  const next = window.MutaResourceMentions.removeTrigger(
    inputEl.value,
    trigger.at,
    trigger.caret,
  );
  inputEl.value = next.text;
  inputEl.setSelectionRange(next.caret, next.caret);
  if (!alreadySelected) {
    selectedRagResources.push({
      id: resource.id,
      name: window.MutaResourceMentions.nameFor(resource),
    });
  }
  renderRagChips();
  closeMentionMenu();
  autoGrow();
  inputEl.focus();
}

function positionMentionMenu() {
  if (mentionMenu.hidden) return;
  const composer = $("#composer").getBoundingClientRect();
  const width = Math.min(composer.width - 24, 520);
  mentionMenu.style.width = `${Math.max(240, width)}px`;
  mentionMenu.style.left = `${Math.max(8, composer.left + 12)}px`;
  const height = mentionMenu.getBoundingClientRect().height;
  mentionMenu.style.top = `${Math.max(8, composer.top - height - 8)}px`;
}

function renderMentionMenu() {
  const trigger = mentionTrigger();
  if (!trigger) return closeMentionMenu();
  mentionMenu.innerHTML = "";
  mentionMatches = learningResources.filter(
    (resource) => !trigger.query || window.MutaResourceMentions
      .nameFor(resource)
      .toLowerCase()
      .includes(trigger.query),
  );
  if (!mentionMatches.length) {
    const empty = document.createElement("div");
    empty.className = "resource-empty";
    empty.textContent = featureT(learningResources.length ? "resources.empty" : "rag.noFiles");
    mentionMenu.appendChild(empty);
  } else {
    mentionActiveIndex = Math.min(mentionActiveIndex, mentionMatches.length - 1);
    if (mentionMatches[mentionActiveIndex]?.status !== "ready") {
      const firstReady = mentionMatches.findIndex((resource) => resource.status === "ready");
      mentionActiveIndex = firstReady >= 0 ? firstReady : 0;
    }
    mentionMatches.forEach((resource, index) => {
      const option = document.createElement("button");
      option.type = "button";
      option.id = `resource-option-${index}`;
      option.className = `resource-option${index === mentionActiveIndex ? " active" : ""}`;
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", String(index === mentionActiveIndex));
      option.disabled = resource.status !== "ready";
      const name = document.createElement("strong");
      name.dir = "auto";
      name.textContent = window.MutaResourceMentions.nameFor(resource);
      const detail = document.createElement("small");
      detail.textContent = resource.page_count
        ? featureT("resources.pages", { count: resource.page_count })
        : resource.error || resourceStatusLabel(resource);
      const status = document.createElement("span");
      status.className = `resource-status ${resource.status}`;
      status.textContent = resourceStatusLabel(resource);
      option.append(name, detail, status);
      option.addEventListener("mousedown", (event) => event.preventDefault());
      option.addEventListener("click", () => selectMention(resource));
      mentionMenu.appendChild(option);
    });
    inputEl.setAttribute("aria-activedescendant", `resource-option-${mentionActiveIndex}`);
  }
  mentionMenu.hidden = false;
  const readyCount = mentionMatches.filter((resource) => resource.status === "ready").length;
  mentionStatus.textContent = readyCount
    ? featureT("rag.pickerResults", { count: readyCount })
    : featureT("rag.pickerEmpty");
  requestAnimationFrame(positionMentionMenu);
}

function resourcesFromTypedMentions(text) {
  const selected = [...selectedRagResources];
  const names = window.MutaResourceMentions.segment(text)
    .filter((part) => part.type === "resource")
    .map((part) => part.name);
  names.forEach((name) => {
    const matches = learningResources.filter(
      (resource) => window.MutaResourceMentions.nameFor(resource) === name,
    );
    if (matches.length === 1 && !selected.some((resource) => resource.id === matches[0].id)) {
      selected.push({ id: matches[0].id, name });
    }
  });
  return selected;
}

function renderResourceList() {
  resourceList.innerHTML = "";
  if (!learningResources.length) {
    const empty = document.createElement("div");
    empty.className = "resource-list-empty";
    empty.textContent = featureT("resources.empty");
    resourceList.appendChild(empty);
    return;
  }
  learningResources.forEach((resource) => {
    const row = document.createElement("div");
    row.className = "resource-row";
    const name = document.createElement("strong");
    name.dir = "auto";
    name.textContent = window.MutaResourceMentions.nameFor(resource);
    const detail = document.createElement("small");
    detail.textContent = resource.page_count
      ? `${resourceStatusLabel(resource)} · ${featureT("resources.pages", { count: resource.page_count })}`
      : resource.error || resourceStatusLabel(resource);
    const actions = document.createElement("div");
    actions.className = "resource-actions";
    if (resource.status === "failed") {
      const retry = document.createElement("button");
      retry.type = "button";
      retry.className = "resource-action";
      retry.textContent = featureT("resources.retry");
      retry.addEventListener("click", () => retryResource(resource.id));
      actions.appendChild(retry);
    }
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "resource-action delete";
    remove.textContent = featureT("resources.delete");
    remove.addEventListener("click", () => deleteResource(resource.id));
    actions.appendChild(remove);
    row.append(name, detail, actions);
    resourceList.appendChild(row);
  });
}

function scheduleResourcePoll() {
  clearTimeout(resourcePollTimer);
  resourcePollTimer = null;
  if (learningResources.some((resource) => resource.status === "processing")) {
    resourcePollTimer = setTimeout(() => loadResources({ quiet: true }), 1500);
  }
}

async function loadResources({ quiet = false } = {}) {
  try {
    const response = await fetch("/v1/resources", { headers: authHeaders() });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const body = await response.json();
    learningResources = Array.isArray(body.resources) ? body.resources : [];
    const ids = new Set(learningResources.map((resource) => resource.id));
    selectedRagResources = selectedRagResources.filter((resource) => ids.has(resource.id));
    renderRagChips();
    renderResourceList();
    if (!mentionMenu.hidden) renderMentionMenu();
  } catch {
    if (!quiet) resourceList.textContent = featureT("resources.uploadFailed");
  } finally {
    scheduleResourcePoll();
  }
}

async function uploadResource(file) {
  if (!file) return;
  const displayName = window.MutaResourceMentions.nameFor({ name: file.name });
  toast(featureT("resources.uploading", { name: displayName }), 3000);
  const form = new FormData();
  form.append("file", file);
  try {
    const response = await fetch("/v1/resources", {
      method: "POST",
      headers: authHeaders(),
      body: form,
    });
    if (!response.ok) {
      const detail = (await response.json().catch(() => ({}))).detail;
      throw new Error(typeof detail === "string" ? detail : "");
    }
    const resource = await response.json();
    learningResources = [resource, ...learningResources.filter((item) => item.id !== resource.id)];
    renderResourceList();
    scheduleResourcePoll();
    toast(featureT("resources.uploaded", {
      name: window.MutaResourceMentions.nameFor(resource),
    }), 5000);
  } catch (error) {
    toast(error.message || featureT("resources.uploadFailed"), 5000);
  }
}

async function retryResource(resourceId) {
  const response = await fetch(`/v1/resources/${encodeURIComponent(resourceId)}/retry`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!response.ok) return toast(featureT("resources.uploadFailed"));
  await loadResources({ quiet: true });
}

async function deleteResource(resourceId) {
  const response = await fetch(`/v1/resources/${encodeURIComponent(resourceId)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!response.ok) return toast(featureT("resources.deleteFailed"));
  learningResources = learningResources.filter((resource) => resource.id !== resourceId);
  selectedRagResources = selectedRagResources.filter((resource) => resource.id !== resourceId);
  renderResourceList();
  renderRagChips();
}

ragButton.addEventListener("click", () => {
  useRag = !useRag;
  ragButton.classList.toggle("active", useRag);
  ragButton.setAttribute("aria-pressed", String(useRag));
  if (!useRag) {
    selectedRagResources = [];
    closeMentionMenu();
    renderRagChips();
  } else {
    void loadResources({ quiet: true });
  }
  toast(featureT(useRag ? "rag.on" : "rag.off"), 3000);
  inputEl.focus();
});

inputEl.addEventListener("input", () => {
  renderMentionMenu();
});
inputEl.addEventListener("click", renderMentionMenu);
inputEl.addEventListener("blur", () => setTimeout(closeMentionMenu, 100));
window.addEventListener("resize", positionMentionMenu);

$("#resource-upload").addEventListener("click", () => $("#file-resource").click());
$("#file-resource").addEventListener("change", (event) => {
  const file = event.target.files[0];
  event.target.value = "";
  if (file) void uploadResource(file);
});

// --- settings --------------------------------------------------------------------------
const settingsModal = $("#settings-modal");
const parallelChatsToggle = $("#setting-parallel-chats");
const powerOptimizationToggle = $("#setting-power-optimization");
const languageSelect = $("#setting-language");
const hostEnabledToggle = $("#setting-host-enabled");
let hostStatus = null;
let hostPollTimer = null;
let hostRosterSignature = "";

function setSettingsOpen(open) {
  settingsModal.hidden = !open;
  $("#app").inert = open;
  if (open) {
    void loadResources({ quiet: true });
    void refreshPowerStatus();
    if (authRole === "host") void loadHostStatus();
    languageSelect.focus();
  } else {
    if (hostPollTimer) window.clearTimeout(hostPollTimer);
    hostPollTimer = null;
    $("#settings-open").focus();
  }
}

function formatHostRam(bytes) {
  if (!Number.isFinite(Number(bytes))) return "—";
  return `${(Number(bytes) / 2 ** 30).toFixed(1)} GB`;
}

function hostUserRow(user) {
  const row = document.createElement("div");
  row.className = "host-user-row";
  const identity = document.createElement("span");
  const name = document.createElement("strong");
  name.textContent = user.username;
  const detail = document.createElement("small");
  detail.textContent = user.status === "pending" ? "Waiting for approval" :
    user.status === "deleting" ? "Removing data…" :
    user.last_login_at ? "Approved · has signed in" : "Approved";
  identity.append(name, detail);
  const actions = document.createElement("div");
  actions.className = "host-user-actions";
  if (user.status === "pending") {
    for (const [label, action, danger] of [["Accept", "approve", false], ["Decline", "reject", true]]) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      if (danger) button.className = "danger";
      button.addEventListener("click", () => void hostUserAction(user, action, button));
      actions.append(button);
    }
  } else if (user.status === "approved") {
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "danger";
    remove.textContent = "Remove";
    remove.addEventListener("click", () => void hostUserAction(user, "remove", remove));
    actions.append(remove);
  }
  row.append(identity, actions);
  return row;
}

function renderHostStatus(status) {
  hostStatus = status;
  hostEnabledToggle.checked = Boolean(status.enabled);
  for (const input of document.querySelectorAll('input[name="host-memory"]')) {
    input.checked = input.value === status.memory_mode;
  }
  const shareCard = $("#host-share-card");
  const primaryUrl = status.join_urls?.[0] || "";
  shareCard.hidden = !status.enabled || !primaryUrl;
  if (!shareCard.hidden) {
    $("#host-join-url").value = primaryUrl;
    $("#host-qr").src = `/v1/share/host/qr.png?v=${encodeURIComponent(status.updated_at)}`;
    $("#host-cert-fingerprint").textContent = status.certificate_fingerprint || "Certificate fingerprint unavailable";
  }
  const capacity = status.capacity || {};
  const capacityEl = $("#host-capacity");
  capacityEl.hidden = !Object.keys(capacity).length;
  capacityEl.replaceChildren();
  for (const [value, label] of [
    [capacity.n_parallel ?? "—", "simultaneous chats"],
    [capacity.context_per_chat ?? "—", "tokens per chat"],
    [formatHostRam(capacity.memory_ceiling_bytes), "RAM ceiling"],
  ]) {
    const card = document.createElement("div");
    const strong = document.createElement("strong");
    const small = document.createElement("small");
    strong.textContent = String(value);
    small.textContent = label;
    card.append(strong, small);
    capacityEl.append(card);
  }
  const users = status.users || [];
  $("#host-roster").hidden = !status.enabled && users.length === 0;
  $("#host-roster-count").textContent = `${users.length} account${users.length === 1 ? "" : "s"}`;
  const rosterSignature = JSON.stringify(users);
  if (rosterSignature !== hostRosterSignature) {
    hostRosterSignature = rosterSignature;
    const list = $("#host-user-list");
    list.replaceChildren();
    if (!users.length) {
      const empty = document.createElement("p");
      empty.className = "host-roster-empty";
      empty.textContent = "No one has asked to join yet.";
      list.append(empty);
    } else {
      users.forEach((user) => list.append(hostUserRow(user)));
    }
  }
  $("#host-save-state").textContent = status.warning ||
    (status.enabled ? "Host mode is on. New replies are queued when all slots are busy." : "Host mode is off.");
}

async function loadHostStatus({ poll = true } = {}) {
  if (authRole !== "host") return;
  try {
    const response = await fetch("/v1/share/host", { headers: authHeaders(), cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderHostStatus(await response.json());
  } catch {
    $("#host-save-state").textContent = "Could not read Host mode settings.";
  }
  if (poll && !settingsModal.hidden) {
    if (hostPollTimer) window.clearTimeout(hostPollTimer);
    hostPollTimer = window.setTimeout(() => void loadHostStatus(), 3000);
  }
}

async function saveHostSettings() {
  const previous = hostStatus;
  const memory = document.querySelector('input[name="host-memory"]:checked')?.value || "competition";
  hostEnabledToggle.disabled = true;
  document.querySelectorAll('input[name="host-memory"]').forEach((input) => { input.disabled = true; });
  $("#host-save-state").textContent = "Applying the safe chat capacity…";
  try {
    const response = await fetch("/v1/share/host", {
      method: "PUT",
      headers: { "content-type": "application/json", ...authHeaders() },
      body: JSON.stringify({ enabled: hostEnabledToggle.checked, memory_mode: memory }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(shareDetail(payload, "Could not update Host mode."));
    renderHostStatus(payload);
  } catch (error) {
    if (previous) renderHostStatus(previous);
    $("#host-save-state").textContent = error.message || "Could not update Host mode.";
  } finally {
    hostEnabledToggle.disabled = false;
    document.querySelectorAll('input[name="host-memory"]').forEach((input) => { input.disabled = false; });
  }
}

async function hostUserAction(user, action, button) {
  if (action === "remove" && !window.confirm(
    `Remove ${user.username}? Their account, conversations, files and learning profile will be deleted.`
  )) return;
  button.disabled = true;
  const method = action === "remove" ? "DELETE" : "POST";
  const suffix = action === "remove" ? "" : `/${action}`;
  try {
    const response = await fetch(`/v1/share/host/users/${encodeURIComponent(user.id)}${suffix}`, {
      method,
      headers: authHeaders(),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(shareDetail(payload, `Could not ${action} that account.`));
    await loadHostStatus({ poll: false });
  } catch (error) {
    $("#host-save-state").textContent = error.message || "Could not update that account.";
  } finally {
    button.disabled = false;
  }
}

hostEnabledToggle.addEventListener("change", () => void saveHostSettings());
document.querySelectorAll('input[name="host-memory"]').forEach((input) => {
  input.addEventListener("change", () => void saveHostSettings());
});
$("#host-copy-url").addEventListener("click", async () => {
  const value = $("#host-join-url").value;
  try {
    await navigator.clipboard.writeText(value);
    $("#host-save-state").textContent = "Join address copied.";
  } catch {
    $("#host-join-url").select();
    $("#host-save-state").textContent = "Address selected — copy it from the field.";
  }
});

async function loadSettings() {
  // localStorage is a compatibility fallback for an older gateway; the authenticated store
  // is authoritative and makes the preference follow the unified loopback learner identity.
  const cached = localStorage.getItem("muta-parallel-chats");
  if (cached != null) allowParallelChats = cached === "true";
  const cachedPower = localStorage.getItem("muta-power-optimization");
  if (cachedPower != null) powerOptimizationEnabled = cachedPower === "true";
  parallelChatsToggle.checked = allowParallelChats;
  powerOptimizationToggle.checked = powerOptimizationEnabled;
  try {
    const response = await fetch("/v1/settings", { headers: authHeaders() });
    if (!response.ok) return;
    const settings = await response.json();
    allowParallelChats = settings.allow_parallel_chats !== false;
    powerOptimizationEnabled = settings.power_optimization_enabled !== false;
    parallelChatsToggle.checked = allowParallelChats;
    powerOptimizationToggle.checked = powerOptimizationEnabled;
    localStorage.setItem("muta-parallel-chats", String(allowParallelChats));
    localStorage.setItem("muta-power-optimization", String(powerOptimizationEnabled));
  } catch {
    /* keep the local fallback */
  }
  await refreshPowerStatus();
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
    toast(t("settings.saveFailed"));
  } finally {
    parallelChatsToggle.disabled = false;
    syncComposerState();
  }
}

function powerDuration(seconds) {
  if (seconds == null || seconds < 0) return null;
  const minutes = Math.max(1, Math.round(seconds / 60));
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  if (!hours) return `${minutes}m`;
  return remainder ? `${hours}h ${remainder}m` : `${hours}h`;
}

function updatePowerStatus(status) {
  latestPowerStatus = status;
  const card = $("#power-status");
  const modeEl = $("#power-status-mode");
  const detailEl = $("#power-status-detail");
  const actionsEl = $("#power-status-actions");
  const badge = $("#power-badge");
  card.classList.remove("normal", "eco", "critical");
  const hostMode = status.host_mode || status.mode || "normal";
  card.classList.add(hostMode === "critical" ? "critical" : (status.mode || "normal"));

  if (!status.available) {
    if (hostMode === "critical") {
      modeEl.textContent = powerText("critical");
      detailEl.textContent = powerText("sensorGrace");
      const graceActions = (status.actions || []).map((action) =>
        powerText(`action_${action}`),
      );
      actionsEl.hidden = graceActions.length === 0;
      actionsEl.textContent = graceActions.length
        ? powerText("actions", { actions: graceActions.join(", ") })
        : "";
      badge.hidden = false;
      badge.classList.add("critical");
      $("#power-badge-mode").textContent = powerText("critical");
      $("#power-badge-level").textContent = "sensor";
      badge.setAttribute(
        "aria-label",
        `${powerText("critical")}. ${powerText("sensorGrace")} ${powerText("openSettings")}`,
      );
      return;
    }
    modeEl.textContent = powerText("unavailable");
    detailEl.textContent = powerText("unavailableHelp");
    actionsEl.hidden = true;
    badge.hidden = true;
    return;
  }

  const modeKey = status.optimization_enabled ? status.mode : "off";
  modeEl.textContent = powerText(modeKey || "normal");
  const details = [];
  if (status.on_battery === true && status.external_power_connected === true) {
    details.push(powerText("connectedDraining"));
  } else if (status.on_battery === false) {
    details.push(powerText("plugged"));
  }
  if (status.percentage != null) {
    details.push(powerText("battery", { percentage: Math.round(status.percentage) }));
  }
  const remaining = powerDuration(status.time_to_empty_s);
  if (status.on_battery === true && remaining) {
    details.push(powerText("remaining", { time: remaining }));
  }
  if (status.energy_rate_w != null) {
    details.push(powerText("rate", { watts: Number(status.energy_rate_w).toFixed(1) }));
  }
  detailEl.textContent = details.join(" · ") || powerText("checkingHelp");

  const actions = (status.actions || []).map((action) =>
    powerText(`action_${action}`),
  );
  actionsEl.hidden = actions.length === 0;
  actionsEl.textContent = actions.length
    ? powerText("actions", { actions: actions.join(", ") })
    : "";

  const active = (
    status.optimization_enabled && ["eco", "critical"].includes(status.mode)
  ) || hostMode === "critical";
  badge.hidden = !active;
  badge.classList.toggle("critical", hostMode === "critical");
  $("#power-badge-mode").textContent = powerText(
    hostMode === "critical" ? "critical" : status.mode,
  );
  $("#power-badge-level").textContent = status.percentage == null
    ? "battery"
    : `${Math.round(status.percentage)}%`;
  const badgeLabel = [
    powerText(hostMode === "critical" ? "critical" : status.mode),
    status.percentage == null
      ? null
      : powerText("battery", { percentage: Math.round(status.percentage) }),
    powerText("openSettings"),
  ].filter(Boolean).join(". ");
  badge.setAttribute("aria-label", badgeLabel);
}

async function refreshPowerStatus() {
  try {
    const response = await fetch("/v1/power/status", { headers: authHeaders() });
    if (response.status === 401 || response.status === 403) {
      void revalidateShareIdentity();
      return;
    }
    if (!response.ok) return;
    updatePowerStatus(await response.json());
  } catch {
    /* Keep the last trustworthy sample; power telemetry never blocks tutoring. */
  }
}

async function savePowerOptimization(enabled) {
  const previous = powerOptimizationEnabled;
  powerOptimizationEnabled = enabled;
  localStorage.setItem("muta-power-optimization", String(enabled));
  powerOptimizationToggle.disabled = true;
  try {
    const response = await fetch("/v1/settings", {
      method: "PUT",
      headers: { "content-type": "application/json", ...authHeaders() },
      body: JSON.stringify({ power_optimization_enabled: enabled }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    await refreshPowerStatus();
  } catch {
    powerOptimizationEnabled = previous;
    powerOptimizationToggle.checked = previous;
    localStorage.setItem("muta-power-optimization", String(previous));
    toast(t("settings.saveFailed"));
  } finally {
    powerOptimizationToggle.disabled = false;
  }
}

$("#settings-open").addEventListener("click", () => setSettingsOpen(true));
$("#settings-close").addEventListener("click", () => setSettingsOpen(false));
settingsModal.addEventListener("click", (event) => {
  if (event.target === settingsModal) setSettingsOpen(false);
});
settingsModal.addEventListener("keydown", (event) => {
  if (event.key !== "Tab" || settingsModal.hidden) return;
  const focusable = [...settingsModal.querySelectorAll(
    'button:not([disabled]), select:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )].filter((element) => !element.hidden);
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
});
parallelChatsToggle.addEventListener("change", () => {
  void saveParallelChats(parallelChatsToggle.checked);
});
powerOptimizationToggle.addEventListener("change", () => {
  void savePowerOptimization(powerOptimizationToggle.checked);
});
$("#power-badge").addEventListener("click", () => setSettingsOpen(true));
languageSelect.addEventListener("change", () => {
  window.MutaI18n.setLocale(languageSelect.value);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !settingsModal.hidden) {
    event.preventDefault();
    event.stopPropagation();
    setSettingsOpen(false);
  }
});

// --- mobile sidebar drawer -------------------------------------------------------------
const appEl = $("#app");
const menuToggle = $("#menu-toggle");
const sidebarEl = $("#sidebar");
const mainEl = $("#main");
const mobileSidebar = window.matchMedia("(max-width: 720px)");
function setDrawer(open) {
  const drawerOpen = Boolean(open && mobileSidebar.matches);
  appEl.classList.toggle("sidebar-open", drawerOpen);
  if (menuToggle) menuToggle.setAttribute("aria-expanded", String(drawerOpen));
  const backdrop = $("#sidebar-backdrop");
  if (backdrop) backdrop.hidden = !drawerOpen;
  if (sidebarEl) sidebarEl.toggleAttribute("inert", mobileSidebar.matches && !drawerOpen);
  if (mainEl) mainEl.toggleAttribute("inert", drawerOpen);
}
if (menuToggle) {
  menuToggle.addEventListener("click", () => setDrawer(!appEl.classList.contains("sidebar-open")));
  $("#sidebar-backdrop").addEventListener("click", () => setDrawer(false));
  // Close the drawer after picking a thread or starting a new one (mobile only).
  $("#conversation-list").addEventListener("click", () => setDrawer(false));
  $("#new-chat").addEventListener("click", () => setDrawer(false));
}
mobileSidebar.addEventListener?.("change", () => setDrawer(false));
setDrawer(false);

// Identity is a readiness barrier, not a best-effort enhancement. In unified-loopback and
// signed deployments the temporary browser UUID is not the eventual owner; loading or sending
// under it can make a selected chat look missing and strand a reply under the wrong identity.
async function bootChat() {
  if (localOperatorPage) {
    // access-bootstrap.js already made this the first paint; remove `hidden` from the DOM state
    // as well. The shell remains inert and aria-busy until activateIdentity proves the host.
    document.querySelector("#share-auth").hidden = true;
    document.querySelector("#app").hidden = false;
  }
  sendBtn.disabled = true;
  while (!(await ensureAuth())) {
    await new Promise((resolve) => {
      shareAuthWake = resolve;
      window.setTimeout(resolve, 2500);
    });
  }
  syncComposerState();
  restoreMessageQueue();
  await loadSettings();
  window.setInterval(() => {
    if (!document.hidden) {
      void refreshPowerStatus();
      void revalidateShareIdentity();
    }
  }, 15_000);
  await loadResources({ quiet: true });
  await recoverGenerations();
  const selected = conversationFromLocation();
  const pending = pendingRequestFromLocation();
  if (selected) {
    const loaded = await loadConversation(selected, {
      historyMode: "none",
      attempts: 6,
      retryUnavailable: true,
    });
    if (loaded === false) newChat({ historyMode: "replace" });
    else {
      // A POST can be accepted just as the old document unloads, then finish before the active
      // list is queried. Recover its retained replay by request id so the marker cannot become a
      // stale dead end and a queued "continue" survives the reload. This also runs while history
      // is temporarily unavailable: the job can then be followed in the background and attached
      // by the URL-scoped history retry, instead of leaving a partial snapshot onscreen.
      for (const requestId of pendingStartsFor(selected)) {
        void recoverPendingGeneration(requestId, {
          navigate: conversationId === selected,
          fallbackConversation: selected,
          expectedViewId: currentViewId,
          quiet: true,
        });
      }
    }
  } else if (pending && sessionStorage.getItem(`muta-pending:${pending}`)) {
    const recovered = await recoverPendingGeneration(pending);
    if (!recovered) refreshSidebar();
  } else {
    if (pending) setConversationLocation(null, { mode: "replace" });
    refreshSidebar();
  }
}
void bootChat();

window.addEventListener("popstate", () => {
  const selected = conversationFromLocation();
  if (selected) void loadConversation(selected, { historyMode: "none" });
  else newChat({ historyMode: "none" });
});

// --- thinking-level selector ------------------------------------------------------------
const thinkBtn = $("#btn-think");
const thinkMenu = $("#think-menu");
const thinkCurrent = $("#think-current");
const thinkingLabel = (level) => t(`reason.${level === "off" || level === "extended" ? level : "auto"}`);
function applyThinkingLabel() {
  thinkCurrent.textContent = thinkingLabel(thinkingLevel);
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
    toast(t("reason.changed", { level: thinkingLabel(thinkingLevel) }), 2000);
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
  toast(t(useWeb ? "web.on" : "web.off"), 2500);
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
    dot.title = t(body.online ? "network.online" : "network.offline");
  } catch {
    /* the ready poll failing is not worth a toast */
  }
}
refreshNetDot();
setInterval(refreshNetDot, 60_000);

// --- local model registry ---------------------------------------------------------------
const modelTrigger = $("#model-trigger");
const modelTriggerLabel = $("#model-trigger-label");
const modelMenu = $("#model-menu");
const modelOptions = $("#model-options");
const modelNote = $("#model-note");

function modelSummary(model) {
  const metrics = [];
  if (model.arc_easy != null) metrics.push(`ARC-Easy ${(100 * model.arc_easy).toFixed(0)}%`);
  if (model.audit_proxy_tps != null) {
    metrics.push(`audit proxy ${model.audit_proxy_tps.toFixed(1)} tok/s`);
  }
  const description = window.MutaI18n.locale === "en" ? model.description : "";
  return [description, metrics.join(" · ")].filter(Boolean).join(" ");
}

function setModelMenuOpen(open, { focus = false, restoreFocus = false } = {}) {
  const next = Boolean(open && !modelTrigger.disabled);
  const focusWasInMenu = modelMenu.contains(document.activeElement);
  modelMenu.hidden = !next;
  modelTrigger.setAttribute("aria-expanded", String(next));
  if (next && focus) {
    modelOptions.querySelector(".model-option:not(:disabled)")?.focus();
  } else if (!next && (restoreFocus || focusWasInMenu)) {
    modelTrigger.focus();
  }
}

function makeModelOption(model, activeId, selectionEnabled) {
  const option = document.createElement("button");
  option.type = "button";
  option.className = "model-option";
  option.dataset.modelId = model.id;
  option.dataset.selectable = String(selectionEnabled && model.available);
  option.setAttribute("role", "menuitemradio");
  option.setAttribute("aria-checked", String(model.id === activeId));
  option.disabled = option.dataset.selectable !== "true";

  const title = document.createElement("span");
  title.className = "model-option-title";
  const label = document.createElement("span");
  label.dir = "auto";
  label.textContent = model.label;
  title.append(label);
  if (model.recommended) {
    const badge = document.createElement("span");
    badge.className = "model-badge";
    badge.dataset.i18n = "model.recommended";
    badge.textContent = t("model.recommended");
    title.append(badge);
  }

  const detail = document.createElement("span");
  detail.className = "model-option-detail";
  detail.dir = "auto";
  detail.textContent = !model.available
    ? t("model.unavailable")
    : modelSummary(model) || t("model.localTutor");
  const check = document.createElement("span");
  check.className = "model-check";
  check.setAttribute("aria-hidden", "true");
  check.textContent = "✓";
  option.append(title, detail, check);
  return option;
}

function renderModelCatalog(catalog) {
  modelCatalog = catalog;
  const models = catalog.models || [];
  const active = models.find((model) => model.id === catalog.active_id);
  modelOptions.innerHTML = "";
  for (const model of models) {
    modelOptions.append(makeModelOption(model, catalog.active_id, catalog.selection_enabled));
  }
  const hasChoice = catalog.selection_enabled && models.some((model) => model.available);
  modelTriggerLabel.textContent = catalog.switching
    ? t("model.switching")
    : active?.label || (catalog.active_id ? t("model.currentLocal") : t("model.choose"));
  modelTrigger.title = active ? modelSummary(active) : t("model.chooseLocal");
  modelNote.textContent = !catalog.selection_enabled
    ? t("model.operatorOnly")
    : active
      ? modelSummary(active)
      : hasChoice
      ? t("model.outsideRegistry")
      : t("model.noneInstalled");
  modelTrigger.dataset.loadFailed = "false";
  modelTrigger.dataset.switching = String(catalog.switching === true);
  modelTrigger.disabled = false;
  if (catalog.switching) scheduleModelCatalogRecovery();
  else if (modelRecoveryTimer !== null) {
    clearTimeout(modelRecoveryTimer);
    modelRecoveryTimer = null;
  }
  syncComposerState();
}

function scheduleModelCatalogRecovery() {
  if (modelRecoveryTimer !== null) return;
  modelRecoveryTimer = setTimeout(async () => {
    modelRecoveryTimer = null;
    const recovered = await refreshModelCatalog();
    if (!recovered || modelTrigger.dataset.switching === "true") {
      scheduleModelCatalogRecovery();
    }
  }, 2500);
}

async function refreshModelCatalog() {
  const preserveSwitchLock = modelSwitchUncertain
    || modelTrigger.dataset.switching === "true";
  try {
    const response = await fetch("/v1/models");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    modelSwitchUncertain = false;
    renderModelCatalog(await response.json());
    return true;
  } catch {
    modelTrigger.dataset.loadFailed = "true";
    if (preserveSwitchLock) {
      modelSwitchUncertain = true;
      modelTrigger.dataset.switching = "true";
      modelTriggerLabel.textContent = t("model.checking");
      modelNote.textContent = t("model.switchUncertain");
      scheduleModelCatalogRecovery();
    } else {
      modelTrigger.dataset.switching = "false";
      const active = modelCatalog?.models?.find((model) => model.id === modelCatalog.active_id);
      modelTriggerLabel.textContent = active?.label || t("model.localTutor");
      modelNote.textContent = t("model.registryFailed");
    }
    syncComposerState();
    return false;
  }
}

async function selectModel(target) {
  const prior = modelCatalog && modelCatalog.active_id;
  if (!target || target === prior) {
    setModelMenuOpen(false, { restoreFocus: true });
    return;
  }
  if (anyGeneration()) {
    toast(t("model.stopBeforeChange"));
    return;
  }
  const chosen = modelCatalog.models.find((model) => model.id === target);
  if (!chosen || !chosen.available || !modelCatalog.selection_enabled) return;
  setModelMenuOpen(false, { restoreFocus: true });
  modelSwitchUncertain = true;
  modelTrigger.dataset.switching = "true";
  modelTriggerLabel.textContent = t("model.loadingNamed", { model: chosen.label });
  syncComposerState();
  modelNote.textContent = t("model.loadingNote", { model: chosen.label });
  toast(t("model.switchingNamed", { model: chosen.label }), 120000);
  try {
    const response = await fetch("/v1/models/select", {
      method: "POST",
      headers: { "content-type": "application/json", ...authHeaders() },
      body: JSON.stringify({ model_id: target }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(body.detail || `HTTP ${response.status}`);
      error.definitive = response.status >= 400
        && response.status < 500
        && typeof body.detail === "string";
      throw error;
    }
    modelSwitchUncertain = false;
    renderModelCatalog(body);
    toast(t("model.readyNew", { model: chosen.label }));
    announce(t("model.ready", { model: chosen.label }));
  } catch (error) {
    if (!error.definitive) {
      modelTrigger.dataset.loadFailed = "true";
      modelTriggerLabel.textContent = t("model.checking");
      modelNote.textContent = t("model.switchUncertain");
      toast(t("model.connectionDropped"));
      scheduleModelCatalogRecovery();
      return;
    }
    modelSwitchUncertain = false;
    modelTrigger.dataset.switching = "false";
    toast(t("model.switchFailed"));
    await refreshModelCatalog();
  } finally {
    syncComposerState();
  }
}

modelTrigger.addEventListener("click", (event) => {
  // Keyboard activation emits a zero-detail click. Move focus into the menu in that case;
  // pointer users keep focus on the trigger until they choose a row.
  setModelMenuOpen(modelMenu.hidden, { focus: event.detail === 0 });
});
modelTrigger.addEventListener("keydown", (event) => {
  const opensMenu = event.key === "ArrowDown"
    || event.key === "ArrowUp"
    || event.key === "Enter"
    || event.key === " ";
  if (!opensMenu) return;
  event.preventDefault();
  const toggle = event.key === "Enter" || event.key === " ";
  setModelMenuOpen(toggle ? modelMenu.hidden : true, { focus: true });
});
modelOptions.addEventListener("click", (event) => {
  const option = event.target.closest(".model-option");
  if (!option || option.disabled) return;
  void selectModel(option.dataset.modelId);
});
modelMenu.addEventListener("keydown", (event) => {
  const options = [...modelOptions.querySelectorAll(".model-option:not(:disabled)")];
  const index = options.indexOf(document.activeElement);
  let target = null;
  if (event.key === "ArrowDown") target = options[(index + 1) % options.length];
  if (event.key === "ArrowUp") target = options[(index - 1 + options.length) % options.length];
  if (event.key === "Home") target = options[0];
  if (event.key === "End") target = options[options.length - 1];
  if (event.key === "Escape") {
    event.preventDefault();
    event.stopPropagation();
    setModelMenuOpen(false);
    modelTrigger.focus();
    return;
  }
  if (target) {
    event.preventDefault();
    target.focus();
  }
});
document.addEventListener("click", (event) => {
  if (!modelMenu.hidden && !event.target.closest(".model-selector")) setModelMenuOpen(false);
});

function localizeModelCatalog() {
  if (!modelCatalog) return;
  // A locale change must never replay a stale pre-switch catalog through renderModelCatalog:
  // that would overwrite dataset.switching and unlock controls while /models/select is still
  // in flight. Translate the transient status in place and let the authoritative response own
  // the next state transition.
  if (modelTrigger.dataset.switching === "true") {
    modelTriggerLabel.textContent = t(modelSwitchUncertain ? "model.checking" : "model.switching");
    modelNote.textContent = t("model.switchUncertain");
    syncComposerState();
    return;
  }
  renderModelCatalog(modelCatalog);
}

window.MutaI18n.subscribe(() => {
  applyThinkingLabel();
  renderChips();
  renderQueue();
  refreshSidebar();
  syncComposerState();
  if (latestTelemetry) updateTelemetry(latestTelemetry);
  if (latestPowerStatus) updatePowerStatus(latestPowerStatus);
  localizeModelCatalog();
  void refreshNetDot();
});

refreshModelCatalog();
