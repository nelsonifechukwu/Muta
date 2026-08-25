/* Offline UI localization for Muta. The response preference is either an explicit locale or
 * Auto; it is sent as generation metadata and never added to the user's message. Auto resolves
 * the interface to the best supported browser locale while the model follows each latest user
 * message. A translated UI is not evidence of teaching quality, so review pedagogy separately. */
"use strict";

(() => {
  const STORAGE_KEY = "muta-ui-locale-v1";
  const DEFAULT_LOCALE = "en";
  const AUTO_LANGUAGE = "auto";
  const listeners = new Set();
  const africaRegistry = globalThis.MutaAfricaLanguages
    || (typeof require === "function" ? require("./africa-languages.js") : null);
  const interfaceLocaleManifest = globalThis.MutaInterfaceLocales
    || (typeof require === "function" ? require("./locale-manifest.js") : []);
  if (!africaRegistry) throw new Error("Africa-54 language registry must load before i18n.js");
  const localeDefinitions = africaRegistry.languages.map((locale) => ({
    ...locale,
    baseline: "africa54",
    countries: africaRegistry.countriesByLanguage[locale.tag] || [],
  }));
  localeDefinitions.push({
    tag: "de",
    autonym: "Deutsch",
    direction: "ltr",
    group: "other",
    baseline: "additional",
    countries: [],
  });

  const catalogs = {
    en: {
      "groups.african": "African languages",
      "groups.other": "Other languages",
      "country.southAfrica": "South Africa",
      "country.zimbabwe": "Zimbabwe",
      "nav.showConversations": "Show conversations",
      "nav.conversations": "Conversations",
      "nav.newChat": "+ New chat",
      "nav.home": "Muta home",
      "nav.aboutMuta": "About Muta",
      "settings.title": "Settings",
      "settings.close": "Close settings",
      "settings.interface": "Interface",
      "settings.language": "Language",
      "settings.languageAuto": "Auto",
      "settings.languageHelp": "Sets Muta’s response language. Complete interface translations change the menus too. Auto follows your browser for the interface and your latest message for each reply.",
      "settings.general": "General",
      "settings.parallel": "Generate in multiple chats",
      "settings.parallelHelp": "Keep one reply running while you start another. Parallel replies share the local CPU and may each run more slowly.",
      "settings.limits": "Muta stays within the operator’s fixed inference-slot and memory limits.",
      "settings.saveFailed": "Couldn’t save that setting.",
      "runtime.offlineLocal": "offline · local CPU",
      "model.loading": "Loading models…",
      "model.choose": "Choose a model",
      "model.runsLocal": "Runs on this machine",
      "model.defaultRecommended": "The recommended model is selected by default.",
      "model.recommended": "Recommended",
      "model.imageInput": "Image input",
      "model.localTutor": "Local tutor model",
      "model.switching": "Switching model…",
      "model.currentLocal": "Current local model",
      "model.chooseLocal": "Choose the local tutor model",
      "model.operatorOnly": "Only the laptop operator can change the shared tutor model.",
      "model.outsideRegistry": "The current engine is outside this registry. Choose an installed tutor model.",
      "model.noneInstalled": "No verified optional model is installed.",
      "model.checking": "Checking model status…",
      "model.switchUncertain": "The switch may still be completing. Choices stay locked until Muta reconnects.",
      "model.registryFailed": "Could not read the local model registry.",
      "model.stopBeforeChange": "Stop the current reply before changing models.",
      "model.loadingNamed": "Loading {model}…",
      "model.loadingNote": "Loading {model}… The chat and saved conversations will stay open.",
      "model.switchingNamed": "Switching to {model}…",
      "model.readyNew": "{model} is ready. New replies will use it.",
      "model.ready": "{model} is ready.",
      "model.connectionDropped": "The connection dropped while switching models. Muta is checking the result.",
      "model.switchFailed": "Model switch failed.",
      "model.unavailable": "This model is not available on this machine.",
      "empty.title": "What are we working on?",
      "empty.body": "Ask about any subject, drop in a photo of your work, or hold the mic and just say it.",
      "chat.conversation": "Conversation",
      "composer.placeholder": "Ask anything — Enter to send (queues while replying), Ctrl+Enter to interrupt & send",
      "composer.attachImageTitle": "Attach an image (or drag one in)",
      "composer.attachImage": "Attach an image",
      "composer.attachAudioTitle": "Attach an audio file (or drag one in)",
      "composer.attachAudio": "Attach an audio file",
      "composer.send": "Send",
      "composer.sendMessage": "Send message",
      "composer.stop": "Stop the reply (Esc)",
      "fineprint": "Muta runs entirely on this machine. Answers can be wrong — check the working.",
      "drop.addFile": "Drop an image, audio file, or PDF to add it",
      "telemetry.ramTitle": "Current RSS of the backend process tree",
      "telemetry.peakTitle": "Peak RSS since backend start",
      "telemetry.tempTitle": "CPU package temperature",
      "telemetry.throttleTitle": "Thermal throttling",
      "telemetry.tpsTitle": "Tokens per second (this conversation)",
      "telemetry.peak": "peak",
      "telemetry.throttle": "throttle",
      "telemetry.yes": "YES",
      "telemetry.no": "no",
      "queue.messages": "Queued messages",
      "queue.position": "Queued #{position} — other responses are running. Your answer will start automatically as soon as a slot is free.",
      "queue.waiting": "Queued — other responses are running. Your answer will start automatically as soon as a slot is free.",
      "queue.slotFree": "A slot is free — starting your answer…",
      "queue.recovering": "The tutor paused briefly — resuming automatically…",
      "queue.waitingSlot": "Queued{position} — waiting for a slot",
      "queue.automatic": "Queued — other responses are running. Your answer will start automatically when a slot is free.",
      "queue.fromImage": "(from my image)",
      "queue.dontSend": "Don’t send this",
      "queue.discardedOne": "Discarded {count} queued message.",
      "queue.discardedMany": "Discarded {count} queued messages.",
      "thinking.label": "Thinking",
      "thinking.answerNow": "Answer now",
      "thinking.warming": "warming up",
      "thinking.warmingAnnouncement": "Tutor is warming up.",
      "thinking.seconds": "Thought for {seconds}s",
      "thinking.minutes": "Thought for {minutes}m {seconds}s",
      "conversation.untitled": "Untitled",
      "conversation.background": "Replying in the background",
      "conversation.delete": "Delete conversation",
      "conversation.open": "Open conversation: {title}",
      "conversation.voiceChanging": "Finish or stop voice mode before changing chats.",
      "conversation.unavailable": "That conversation is temporarily unavailable — retrying.",
      "conversation.notFound": "Couldn’t find that conversation.",
      "reply.connectionLost": "Connection lost — this answer is incomplete.",
      "reply.couldNotFinish": "The tutor couldn’t finish that reply.",
      "reply.stopFailed": "Couldn’t stop that reply yet — it is still running.",
      "reply.openingChats": "Opening your chats — your draft is safe.",
      "reply.voiceTyped": "Finish voice mode before sending a typed message.",
      "reply.modelLoading": "The selected model is still loading — your draft is safe.",
      "reply.imageReading": "Still reading your image — one moment.",
      "reply.imageUploading": "Still attaching your image — one moment.",
      "reply.previousStarting": "Starting your previous message — this draft is still here.",
      "reply.parallelDisabled": "A reply is running in another chat. Enable multiple chats in Settings to continue here.",
      "reply.earlierRunning": "The earlier reply is still running. This message is queued and will send automatically.",
      "reply.earlierFinishing": "The earlier reply is finishing. This message remains queued until it can send.",
      "reply.startFailed": "Couldn’t start that reply — your message is saved above.",
      "reply.httpAnswerFailed": "The tutor couldn’t answer (HTTP {status}).",
      "reply.reconnecting": "Connection interrupted — reconnecting while the tutor keeps working.",
      "reply.stopped": "Stopped.",
      "reply.tutorReplied": "Tutor replied.",
      "reply.didNotStart": "That reply did not start. Your conversation list is still intact.",
      "attachment.audio": "audio",
      "attachment.file": "file",
      "attachment.reading": "reading…",
      "attachment.uploading": "attaching…",
      "attachment.readFailed": "couldn’t read it",
      "attachment.imageUploadFailed": "Image upload failed — is the backend up?",
      "attachment.imageRead": "Image read. Ask your question and send.",
      "attachment.imageAttached": "Image attached. Ask your question and send.",
      "attachment.chooseImageModel": "Choose a model marked ‘Image input’ or remove the image.",
      "attachment.oneImage": "Send one image per question on this laptop.",
      "attachment.preview": "Attached image preview",
      "attachment.previewNamed": "Attached image preview: {file}",
      "attachment.sent": "Image sent with this question",
      "attachment.sentNamed": "Image sent with this question: {file}",
      "attachment.photoEmpty": "The photo came back empty — try a closer, sharper shot.",
      "attachment.imageUnreadable": "The image couldn’t be read.",
      "attachment.transcribing": "Transcribing the audio…",
      "attachment.speechUnavailable": "Speech recognition isn’t available — type the question instead.",
      "attachment.audioUploadFailed": "Audio upload failed — is the backend up?",
      "attachment.heardNothing": "Couldn’t hear anything in that file.",
      "attachment.unknownFile": "Not sure what to do with {file}",
      "attachment.remove": "Remove attachment",
      "reason.title": "Reasoning effort",
      "reason.off": "Instant",
      "reason.offHelp": "Answers directly — fastest",
      "reason.auto": "Thinking",
      "reason.autoHelp": "Reasons first — default",
      "reason.extended": "Extended",
      "reason.extendedHelp": "Thinks longer — hardest problems",
      "reason.changed": "Reasoning: {level}.",
      "web.title": "Ground answers with the web when online (off by default)",
      "web.label": "Ground answers with the web",
      "web.on": "Web grounding on — sources will be cited when online.",
      "web.off": "Web grounding off.",
      "network.online": "internet available",
      "network.offline": "offline",
      "badge.sources": "Sources: ",
      "badge.cloud": "answered via cloud",
      "badge.verified": "✓ steps checked",
      "badge.verifiedTitle": "The explicit arithmetic in this reply was verified with a math engine.",
      "badge.checkFailed": "Some arithmetic could not be verified — check the working.",
      "voice.talkTitle": "Speak your question",
      "voice.talk": "Speak your question",
      "voice.listening": "Listening… Click the microphone when you’re done.",
      "voice.thinking": "Thinking…",
      "voice.speaking": "Speaking…",
      "voice.wait": "Wait for the current reply to finish.",
      "voice.permission": "Microphone access was refused — voice needs it (and http://localhost).",
      "voice.stopTitle": "Stop listening and transcribe",
      "voice.stop": "Stop listening and transcribe",
      "voice.connectionFailed": "Voice connection failed.",
      "voice.answerFailed": "That answer failed — I’m still listening, ask again.",
      "voice.unavailable": "Voice unavailable.",
      "voice.unavailableReason": "Voice unavailable — {reason}.",
      "voice.didNotCatch": "Didn’t catch that — try again.",
    },
  };

  function safeStorageGet(key) {
    try {
      return globalThis.localStorage?.getItem(key) || null;
    } catch {
      return null;
    }
  }

  function safeStorageSet(key, value) {
    try {
      globalThis.localStorage?.setItem(key, value);
    } catch {
      /* Language switching still works when storage is unavailable. */
    }
  }

  function supportedDefinitions() {
    const required = Object.keys(catalogs[DEFAULT_LOCALE]);
    const ready = new Set(interfaceLocaleManifest.map((locale) => locale.tag));
    return localeDefinitions.filter((locale) => {
      const catalog = catalogs[locale.tag];
      return ready.has(locale.tag)
        && catalog
        && required.every((key) => Object.hasOwn(catalog, key));
    });
  }

  function matchLocale(candidate, definitions) {
    if (!candidate || typeof candidate !== "string") return null;
    const normalized = candidate.trim().replace("_", "-").toLowerCase();
    const available = definitions.map((locale) => locale.tag);
    return available.find((tag) => normalized === tag.toLowerCase())
      || available.find((tag) => normalized.split("-")[0] === tag.split("-")[0])
      || null;
  }

  function normalizeLocale(candidate) {
    return matchLocale(candidate, supportedDefinitions());
  }

  function normalizeKnownLocale(candidate) {
    return matchLocale(candidate, localeDefinitions);
  }

  function browserLocale() {
    const preferences = globalThis.navigator?.languages || [globalThis.navigator?.language];
    for (const preference of preferences) {
      const matched = normalizeLocale(preference);
      if (matched) return matched;
    }
    return DEFAULT_LOCALE;
  }

  function normalizeLanguagePreference(candidate) {
    if (typeof candidate === "string" && candidate.trim().toLowerCase() === AUTO_LANGUAGE) {
      return AUTO_LANGUAGE;
    }
    // The internal registry retains planned languages, but Settings may select only complete
    // interface packs. This keeps the visible product promise and response preference aligned.
    return normalizeLocale(candidate);
  }

  function startupLanguagePreference() {
    return normalizeLanguagePreference(safeStorageGet(STORAGE_KEY)) || AUTO_LANGUAGE;
  }

  function resolveInterfaceLocale(preference) {
    return preference === AUTO_LANGUAGE
      ? browserLocale()
      : normalizeLocale(preference) || DEFAULT_LOCALE;
  }

  let currentLanguagePreference = startupLanguagePreference();
  let currentLocale = resolveInterfaceLocale(currentLanguagePreference);

  function interpolate(value, variables = {}) {
    return String(value).replace(/\{([a-zA-Z][\w]*)\}/g, (match, name) =>
      Object.hasOwn(variables, name) ? String(variables[name]) : match
    );
  }

  function t(key, variables = {}, locale = currentLocale) {
    const normalized = normalizeLocale(locale) || DEFAULT_LOCALE;
    const value = catalogs[normalized]?.[key] ?? catalogs[DEFAULT_LOCALE][key] ?? key;
    return interpolate(value, variables);
  }

  const translatableAttributes = ["title", "aria-label", "placeholder", "data-placeholder"];

  function variablesFor(element, suffix = "") {
    const raw = element.getAttribute(`data-i18n${suffix}-vars`);
    if (!raw) return {};
    try {
      return JSON.parse(raw);
    } catch {
      return {};
    }
  }

  function applyToDocument(doc = globalThis.document) {
    if (!doc?.documentElement) return;
    const definition = localeDefinitions.find((item) => item.tag === currentLocale)
      || localeDefinitions.find((item) => item.tag === DEFAULT_LOCALE);
    doc.documentElement.lang = definition.tag;
    doc.documentElement.dir = definition.direction;
    for (const element of doc.querySelectorAll("[data-i18n]")) {
      element.textContent = t(element.dataset.i18n, variablesFor(element));
    }
    for (const attribute of translatableAttributes) {
      const dataName = `data-i18n-${attribute}`;
      for (const element of doc.querySelectorAll(`[${dataName}]`)) {
        element.setAttribute(attribute, t(
          element.getAttribute(dataName),
          variablesFor(element, `-${attribute}`),
        ));
      }
    }
  }

  function populateSelector(select, doc = globalThis.document) {
    if (!select || !doc) return;
    select.innerHTML = "";
    const autoOption = doc.createElement("option");
    autoOption.value = AUTO_LANGUAGE;
    autoOption.textContent = t("settings.languageAuto");
    select.appendChild(autoOption);
    const visibleDefinitions = supportedDefinitions();
    const autonymCounts = visibleDefinitions.reduce((counts, locale) => {
      counts.set(locale.autonym, (counts.get(locale.autonym) || 0) + 1);
      return counts;
    }, new Map());
    for (const groupName of ["african", "other"]) {
      const locales = visibleDefinitions.filter(
        (locale) => locale.group === groupName,
      );
      if (!locales.length) continue;
      const group = doc.createElement("optgroup");
      group.label = t(`groups.${groupName}`);
      for (const locale of locales) {
        const option = doc.createElement("option");
        option.value = locale.tag;
        option.lang = locale.tag;
        option.dir = locale.direction;
        option.dataset.countries = (locale.countries || []).join(" ");
        option.dataset.baseline = locale.baseline || "additional";
        const qualifier = locale.qualifierKey ? t(locale.qualifierKey) : "";
        const autonym = qualifier
          ? `${locale.autonym} · ${qualifier}`
          : autonymCounts.get(locale.autonym) > 1
            ? `${locale.autonym} · ${locale.tag}`
            : locale.autonym;
        option.textContent = autonym;
        group.appendChild(option);
      }
      select.appendChild(group);
    }
    select.value = currentLanguagePreference;
  }

  function refreshLanguageUI(doc = globalThis.document) {
    applyToDocument(doc);
    populateSelector(doc?.querySelector?.("#setting-language"), doc);
  }

  function setLocale(locale, { persist = true, doc = globalThis.document } = {}) {
    const preference = normalizeLanguagePreference(locale);
    if (!preference) return false;
    currentLanguagePreference = preference;
    currentLocale = resolveInterfaceLocale(preference);
    if (persist) safeStorageSet(STORAGE_KEY, preference);
    refreshLanguageUI(doc);
    for (const listener of listeners) listener(currentLocale, preference);
    if (doc?.dispatchEvent && typeof globalThis.CustomEvent === "function") {
      doc.dispatchEvent(new CustomEvent("muta:localechange", {
        detail: { locale: currentLocale, languagePreference: preference },
      }));
    }
    return true;
  }

  function multimodalAttachmentMessages(messages) {
    // The 22 machine-assisted packs are generated in a separately reviewed pipeline.  Do not
    // hide every non-English interface merely because this feature adds a compact status label:
    // compose the new labels from each pack's already-translated image/model vocabulary.  This
    // also deliberately avoids reusing the old "read image" wording that implied OCR.
    const attach = messages["composer.attachImage"];
    const choose = messages["model.choose"];
    if (!attach || !choose) return {};
    return {
      "model.imageInput": attach,
      "reply.imageUploading": `${attach}…`,
      "attachment.uploading": `${attach}…`,
      "attachment.imageAttached": `${attach} ✓`,
      "attachment.chooseImageModel": `${choose} · ${attach}`,
      "attachment.oneImage": `1 · ${attach}`,
      "attachment.preview": attach,
      "attachment.previewNamed": `${attach}: {file}`,
      "attachment.sent": `${attach} ✓`,
      "attachment.sentNamed": `${attach}: {file}`,
    };
  }

  function registerLocale(definition, messages) {
    if (!definition?.tag || !messages) return false;
    const combined = { ...(catalogs[definition.tag] || {}), ...messages };
    const attachmentMessages = multimodalAttachmentMessages(combined);
    catalogs[definition.tag] = {
      ...attachmentMessages,
      ...combined,
    };
    const index = localeDefinitions.findIndex((item) => item.tag === definition.tag);
    if (index >= 0) localeDefinitions[index] = { ...localeDefinitions[index], ...definition };
    else localeDefinitions.push({ ...definition });
    return supportedDefinitions().some((locale) => locale.tag === definition.tag);
  }

  function subscribe(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }

  function initialize(doc = globalThis.document) {
    currentLanguagePreference = startupLanguagePreference();
    currentLocale = resolveInterfaceLocale(currentLanguagePreference);
    refreshLanguageUI(doc);
    return currentLocale;
  }

  const api = {
    STORAGE_KEY,
    DEFAULT_LOCALE,
    AUTO_LANGUAGE,
    catalogs,
    localeDefinitions,
    africaRegistry,
    interfaceLocaleManifest,
    get locale() { return currentLocale; },
    get languagePreference() { return currentLanguagePreference; },
    get responseLanguage() { return currentLanguagePreference; },
    t,
    normalizeLocale,
    normalizeKnownLocale,
    normalizeLanguagePreference,
    browserLocale,
    resolveInterfaceLocale,
    supportedDefinitions,
    applyToDocument,
    populateSelector,
    refreshLanguageUI,
    setLocale,
    registerLocale,
    subscribe,
    initialize,
  };

  globalThis.MutaI18n = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  refreshLanguageUI();
})();
