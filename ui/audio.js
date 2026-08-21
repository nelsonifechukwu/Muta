/* Voice loop client: mic → WS /v1/audio/voice → transcript + streamed reply + spoken audio.
 *
 * Half-duplex: the mic is muted while the tutor speaks (no echo cancellation needed).
 * One persistent AudioContext is created on the mic click — that user gesture is what lets
 * the reply auto-play later with zero extra clicks.
 *
 * Mic button states: idle → listening → (replying/speaking: click = barge) → listening.
 */
"use strict";

(() => {
  const TARGET_RATE = 16000;
  const BATCH_SAMPLES = 5120; // ~320 ms at 16 kHz
  const t = (key, variables) => window.MutaI18n.t(key, variables);

  const micBtn = document.querySelector("#btn-mic");
  const chat = window.MutaChat;

  let audioCtx = null;
  let mediaStream = null;
  let captureNode = null;
  let sourceNode = null;
  let ws = null;
  let active = false; // voice mode on
  let replying = false; // server is generating/speaking
  let micMuted = false; // drop capture while TTS plays
  let suppressTts = false; // after a barge: ignore stale TTS until the next turn
  let pending = new Int16Array(0);
  let playhead = 0;
  let activeSources = [];
  let ttsRate = 22050;
  let assistant = null;
  let statusEl = null;
  let statusKey = null;
  let statusVariables = {};

  // --- capture pipeline ---------------------------------------------------

  let resamplePos = 0; // fractional read position carried across worklet blocks

  function downsampleTo16k(float32, fromRate) {
    const ratio = fromRate / TARGET_RATE;
    const out = [];
    let pos = resamplePos;
    while (pos < float32.length - 1) {
      const lo = Math.floor(pos);
      const frac = pos - lo;
      let s = float32[lo] * (1 - frac) + float32[lo + 1] * frac;
      s = Math.max(-1, Math.min(1, s));
      out.push(s < 0 ? s * 0x8000 : s * 0x7fff);
      pos += ratio;
    }
    resamplePos = Math.max(0, pos - float32.length);
    return Int16Array.from(out);
  }

  function onCapture(float32) {
    if (!active || micMuted || !ws || ws.readyState !== WebSocket.OPEN) return;
    const chunk = downsampleTo16k(float32, audioCtx.sampleRate);
    const merged = new Int16Array(pending.length + chunk.length);
    merged.set(pending);
    merged.set(chunk, pending.length);
    pending = merged;
    while (pending.length >= BATCH_SAMPLES) {
      ws.send(pending.slice(0, BATCH_SAMPLES).buffer);
      pending = pending.slice(BATCH_SAMPLES);
    }
  }

  async function startCapture() {
    resamplePos = 0;
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    await audioCtx.resume();
    sourceNode = audioCtx.createMediaStreamSource(mediaStream);
    if (audioCtx.audioWorklet) {
      await audioCtx.audioWorklet.addModule(new URL("worklet.js", document.baseURI));
      captureNode = new AudioWorkletNode(audioCtx, "muta-capture");
      captureNode.port.onmessage = (ev) => onCapture(ev.data);
      sourceNode.connect(captureNode);
    } else {
      // Legacy fallback; every 2026 evergreen browser has AudioWorklet.
      captureNode = audioCtx.createScriptProcessor(4096, 1, 1);
      captureNode.onaudioprocess = (ev) => onCapture(ev.inputBuffer.getChannelData(0).slice(0));
      sourceNode.connect(captureNode);
      captureNode.connect(audioCtx.destination);
    }
  }

  function stopCapture() {
    if (sourceNode) sourceNode.disconnect();
    if (captureNode) captureNode.disconnect();
    if (mediaStream) mediaStream.getTracks().forEach((t) => t.stop());
    sourceNode = captureNode = mediaStream = null;
    pending = new Int16Array(0);
  }

  // --- playback -----------------------------------------------------------

  function playPcm(arrayBuffer) {
    const int16 = new Int16Array(arrayBuffer);
    if (!int16.length) return;
    const f32 = Float32Array.from(int16, (v) => v / 32768);
    const buf = audioCtx.createBuffer(1, f32.length, ttsRate);
    buf.copyToChannel(f32, 0);
    const src = audioCtx.createBufferSource();
    src.buffer = buf;
    src.connect(audioCtx.destination);
    const at = Math.max(audioCtx.currentTime, playhead);
    src.start(at);
    playhead = at + buf.duration;
    activeSources.push(src);
    src.onended = () => {
      activeSources = activeSources.filter((s) => s !== src);
      maybeResumeListening();
    };
  }

  function stopPlayback() {
    for (const s of activeSources) {
      try {
        s.stop();
      } catch {
        /* already stopped */
      }
    }
    activeSources = [];
    playhead = 0;
  }

  function maybeResumeListening() {
    if (!replying && activeSources.length === 0 && active) {
      micMuted = false;
      setStatus("voice.listening");
    }
  }

  // --- UI status ----------------------------------------------------------

  function setStatus(key, variables = {}) {
    if (!active) {
      if (statusEl) statusEl.remove();
      statusEl = null;
      statusKey = null;
      statusVariables = {};
      return;
    }
    statusKey = key;
    statusVariables = variables;
    if (!statusEl) {
      statusEl = document.createElement("div");
      statusEl.className = "voice-status";
      document.querySelector("#messages").appendChild(statusEl);
    }
    statusEl.textContent = "🎙 " + t(key, variables);
    chat.scrollIfFollowing();
  }

  function syncMicAccessibility() {
    micBtn.setAttribute("aria-pressed", String(active));
    micBtn.title = t(active ? "voice.stopTitle" : "voice.talkTitle");
    micBtn.setAttribute("aria-label", t(active ? "voice.stop" : "voice.talk"));
  }

  // --- websocket voice session ---------------------------------------------

  function wsUrl() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    return `${proto}://${location.host}/v1/audio/voice`;
  }

  async function startVoice() {
    if (chat.isGenerating()) return chat.toast(t("voice.wait"));
    try {
      await startCapture();
    } catch {
      return chat.toast(t("voice.permission"));
    }
    ws = new WebSocket(wsUrl());
    ws.binaryType = "arraybuffer";
    ws.onopen = () => {
      ws.send(
        JSON.stringify({
          type: "start",
          student_id: chat.studentId,
          conversation_id: chat.getConversationId(),
          mode: "socratic",
          language: window.MutaI18n.locale,
        })
      );
      active = true;
      chat.setVoiceActive(true);
      replying = false;
      micMuted = false;
      micBtn.classList.add("recording");
      syncMicAccessibility();
      setStatus("voice.listening");
    };
    ws.onmessage = onWsMessage;
    ws.onerror = () => stopVoice(t("voice.connectionFailed"));
    ws.onclose = () => {
      if (active) stopVoice();
    };
  }

  function onWsMessage(ev) {
    if (ev.data instanceof ArrayBuffer) {
      if (!suppressTts) playPcm(ev.data); // stale sentence after a barge: drop it
      return;
    }
    let msg;
    try {
      msg = JSON.parse(ev.data);
    } catch {
      return;
    }
    switch (msg.type) {
      case "error":
        if (msg.reason === "voice-turn-failed") {
          // One failed turn (engine hiccup, timeout) is not a dead session: finish the
          // half-built bubble, free the mic, keep listening. Tearing the whole voice mode
          // down here made every transient error cost the student a click and their flow.
          if (assistant) {
            assistant.finalize();
            assistant = null;
          }
          replying = false;
          suppressTts = false;
          chat.setGenerating(false);
          chat.closeTelemetry();
          micMuted = false;
          setStatus("voice.listening");
          chat.toast(t("voice.answerFailed"));
          break;
        }
        stopVoice(t("voice.unavailable"));
        break;
      case "transcript":
        suppressTts = false; // a new turn: play its speech
        chat.setConversationId(msg.conversation_id);
        chat.addUserMessage(msg.text, [{ kind: "audio" }]);
        assistant = chat.beginAssistantMessage();
        chat.setGenerating(true);
        chat.openTelemetry(msg.conversation_id);
        replying = true;
        micMuted = true;
        setStatus("voice.thinking");
        break;
      case "reasoning":
        if (assistant) assistant.pushThought(msg.text);
        break;
      case "delta":
        if (assistant) assistant.pushDelta(msg.text);
        break;
      case "tts_start":
        if (suppressTts) break; // barged: don't re-mute the mic we just freed
        ttsRate = msg.sample_rate || ttsRate;
        micMuted = true;
        setStatus("voice.speaking");
        break;
      case "tts_end":
        break;
      case "done":
        if (msg.heard === false) {
          setStatus("voice.didNotCatch");
        } else if (assistant) {
          assistant.finalize();
        }
        assistant = null;
        replying = false;
        suppressTts = false;
        chat.setGenerating(false);
        chat.closeTelemetry();
        maybeResumeListening();
        break;
    }
  }

  function stopVoice(toastText) {
    active = false;
    chat.setVoiceActive(false);
    replying = false;
    micMuted = false;
    stopPlayback();
    stopCapture();
    setStatus(null);
    if (ws) {
      try {
        ws.close();
      } catch {
        /* already closed */
      }
      ws = null;
    }
    if (assistant) {
      assistant.finalize();
      assistant = null;
    }
    chat.setGenerating(false);
    chat.closeTelemetry();
    micBtn.classList.remove("recording");
    syncMicAccessibility();
    if (toastText) chat.toast(toastText);
  }

  function barge() {
    // Interrupt: stop local playback, tell the server to abandon the reply, keep listening.
    suppressTts = true; // sentences already synthesized keep arriving — ignore them
    stopPlayback();
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "barge" }));
    if (assistant) {
      assistant.finalize();
      assistant = null;
    }
    replying = false;
    chat.setGenerating(false);
    micMuted = false;
    setStatus("voice.listening");
  }

  window.MutaI18n.subscribe(() => {
    if (statusKey && active) setStatus(statusKey, statusVariables);
    if (active && ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "language", language: window.MutaI18n.locale }));
    }
    syncMicAccessibility();
  });

  syncMicAccessibility();

  micBtn.addEventListener("click", () => {
    if (!active) startVoice();
    else if (replying || activeSources.length) barge();
    else stopVoice();
  });
})();
