/* Offline UI localization for Muta. The response preference is either an explicit locale or
 * Auto; it is sent as generation metadata and never added to the user's message. Auto resolves
 * the interface to the best supported browser locale while the model follows each latest user
 * message. A translated UI is not evidence of teaching quality, so review pedagogy separately. */
"use strict";

(() => {
  const STORAGE_KEY = "muta-ui-locale-v1";
  const DEFAULT_LOCALE = "en";
  const AUTO_LANGUAGE = "auto";
  // Unit copy may fall back to reviewed English while the visible locale packs catch up. Teaching
  // style controls ship with localized copy below because they remain visible throughout a chat.
  const ENGLISH_FALLBACK_KEYS = Object.freeze([
    "unit.open",
    "unit.libraryTitle",
    "unit.back",
    "unit.close",
    "unit.import",
    "unit.importHelp",
    "unit.loading",
    "unit.loadFailed",
    "unit.invalid",
    "unit.mastery",
    "unit.masteryNamed",
    "unit.summaryMinutes",
    "unit.submit",
    "unit.submitFailed",
    "unit.unchecked",
    "unit.sources",
    "unit.previewOnly",
    "unit.score",
    "unit.progressNotSaved",
    "settings.studyCountry",
    "settings.studyCountryHelp",
    "settings.studyCountryNone",
    "style.explain",
    "style.methodGuide",
    "style.descGuide",
    "style.methodShow",
    "style.descShow",
    "style.methodExamples",
    "style.descExamples",
    "style.methodHints",
    "style.descHints",
  ]);
  const STYLE_KEYS = Object.freeze([
    "style.label", "style.guide", "style.show", "style.examples", "style.hints",
    "style.saved", "style.saveFailed",
  ]);
  // Machine-assisted translations were collected through the same visible Google Translate
  // workflow as the generated locale packs and reviewed in the teaching-style picker context.
  const STYLE_MESSAGES = Object.freeze({
    af: ["Hoe moet Muta onderrig?", "Lei my", "Wys my hoe", "Alledaagse voorbeelde", "Slegs wenke", "Onderrigstyl gestoor", "Kon nie daardie onderrigstyl stoor nie."],
    am: ["Muta እንዴት ማስተማር አለበት?", "ምራኝ", "እንዴት እንደሚደረግ አሳየኝ", "የዕለት ተዕለት ምሳሌዎች", "ፍንጮች ብቻ", "የማስተማሪያ ዘዴው ተቀምጧል", "ያንን የማስተማሪያ ዘዴ ማስቀመጥ አልተቻለም።"],
    ar: ["كيف يجب أن يُدرِّس Muta؟", "أرشدني", "أرني الطريقة", "أمثلة من الحياة اليومية", "تلميحات فقط", "تم حفظ أسلوب التدريس", "تعذر حفظ أسلوب التدريس هذا."],
    bem: ["Bushe Muta afwile ukusambilisha shani?", "Ntungulula", "Nlangisheni ifyo", "Ifyakumwenako ifya cila bushiku", "Ifishinka fye", "Umusango wa kusambilishishamo walisungwa", "Teti nsungile iyo nshila ya kusambilishishamo."],
    din: ["Ye Muta piööc yedi?", "Gɛ̈l ɣa", "Nyuɔɔthë ɣɛɛn ye", "Kä ye nyuɔɔth ë kööl ëbɛ̈n", "Kä ye nyuɔɔth abac", "Dhöl de piööc acï tɔ̈ɔ̈u", "Acïï lëu ba dhöl de piööc kënë gël."],
    ff: ["Hol no Muta foti jannginde?", "Ardin am", "Hollu am no", "Yeruuji ñalnde kala", "Hinnde tan", "Jannginde style hisnaama", "Waawaa hisnude oon sifaa jannginde."],
    ha: ["Ta yaya ya kamata Muta ta koyar?", "Yi mini jagora", "Nuna mini yadda ake yi", "Misalan rayuwar yau da kullum", "Alamomi ko bayanai kadan kawai", "An adana salon koyarwar", "Ba a iya adana wannan salon koyarwar ba."],
    ig: ["Kedu ka Muta kwesịrị isi kụziie ihe?", "Duzie m", "Gosi m otu esi eme ya", "Ihe atụ sitere na ndụ kwa ụbọchị", "Ntụnye aka naanị", "Echekwala ụdị nkuzi a", "Enweghị ike ịchekwa ụdị nkuzi ahụ."],
    kg: ["Inki mutindu Muta fwete longa?", "Twadisa mono", "Monisa mono mutindu", "Bambandu ya konso kilumbu", "Bandongisila mpamba", "Mutindu ya kulonga me bumbana", "Ka lenda vuluza mpila yayina ya longa ko."],
    mg: ["Ahoana no tokony hampianaran'i Muta?", "Tariho aho", "Asehoy ahy ny fomba fanaovana azy", "Ohatra avy amin'ny fiainana andavanandro", "Torolalana ihany", "Voatahiry ny fomba fampianarana", "Tsy voatahiry io fomba fampianarana io."],
    ny: ["Kodi Muta iyenera kuphunzitsa bwanji?", "Nditsogolereni", "Ndionetseni momwe zimachitikira", "Zitsanzo za tsiku ndi tsiku", "Malangizo chabe", "Njira yophunzitsira yasungidwa", "Njira yophunzitsirayo sinathe kusungidwa."],
    rn: ["Muta akwiye kwigisha gute?", "Nyobora", "Nyereka uko", "Ingero za misi yose", "Impanuro gusa", "Uburyo bwo kwigisha bwazigamye", "Ntashobora gukiza iyo nzira yo kwigisha."],
    rw: ["Muta ikwiye kwigisha ite?", "Nyobora", "Nyereka uko bikorwa", "Ingero zo mu buzima bwa buri munsi", "Amakuru y'ibanze gusa", "Uburyo bwo kwigisha bwabitswe", "Ntibishobokeye kubika ubwo buryo bwo kwigisha."],
    sn: ["Muta inofanira kudzidzisa sei?", "Nditungamirire", "Ndiratidze maitiro acho", "Mienzaniso yezuva nezuva", "Mazano chete", "Maitiro ekudzidzisa achengetwa", "Maitiro ekudzidzisa iwayo haana kukwanisa kuchengetwa."],
    so: ["Sidee ayay tahay in Muta wax u dhigto?", "I hag", "I tus sida loo sameeyo", "Tusaalooyin maalinle ah", "Tilmaamo kaliya", "Qaabkii wax-baridda waa la keydiyay", "Suurtagal ma noqon in la keydiyo qaabkaas wax-baridda."],
    ss: ["Muta kufanele afundzise njani?", "Ngicondzise", "Ngikhombise kutsi kanjani", "Tibonelo tamalanga onkhe", "Tiluleko kuphela", "Indlela yekufundzisa isindisiwe", "Angizange ngikhone kugcina leso sitayela sekufundzisa."],
    st: ["Muta e lokela ho ruta joang?", "Ntatisetse tsela", "Mpontše mokhoa", "Mehlala ea letsatsi le letsatsi", "Malebela feela", "Mokhoa oa ho ruta o bolokiloe", "Mokhoa oo oa ho ruta ha oa ka oa bolokeha."],
    sw: ["Muta ifundishe vipi?", "Niongoze", "Nionyeshe jinsi ya kufanya", "Mifano ya kila siku", "Vidokezo pekee", "Mtindo wa ufundishaji umehifadhiwa", "Imeshindikana kuhifadhi mtindo huo wa ufundishaji."],
    tn: ["Muta o tshwanetse go ruta jang?", "Nkaela", "Mpontshe gore jang", "Dikai tsa letsatsi le letsatsi", "Ditlhagiso fela", "Mokgwa wa go ruta o bolokilwe", "Ga ke kgone go boloka mokgwa oo wa go ruta."],
    xh: ["U-Muta ufanele afundise njani?", "Ndikhokele", "Ndibonise indlela", "Imizekelo yemihla ngemihla", "Iingcebiso kuphela", "Indlela yokufundisa igciniwe", "Ayiphumelelanga ukugcina loo ndlela yokufundisa."],
    yo: ["Báwo ni Muta ṣe yẹ kí ó kọ́ni?", "Ṣe amọ̀nà mi", "Fi ọ̀nà hàn mí", "Àwọn àpẹẹrẹ ojoojúmọ́", "Àwọn àbá lásán", "A ti fi ọ̀nà ìkọ́ni yìí pamọ́", "A kò lè fi ọ̀nà ìkọ́ni yẹn pamọ́."],
    zu: ["U-Muta kufanele afundise kanjani?", "Ngikhombise indlela", "Ngikhombise ukuthi kwenziwa kanjani", "Izibonelo zansuku zonke", "Amacebiso kuphela", "Indlela yokufundisa igciniwe", "Ayikwazanga ukugcinwa leyo ndlela yokufundisa."],
    es: ["¿Cómo debería enseñar Muta?", "Guíame", "Enséñame cómo", "Ejemplos cotidianos", "Solo pistas", "Estilo de enseñanza guardado", "No se pudo guardar ese estilo de enseñanza."],
    fr: ["Comment Muta doit-il enseigner ?", "Guidez-moi", "Montrez-moi comment faire", "Exemples du quotidien", "Indices uniquement", "Style d'enseignement enregistré", "Impossible d'enregistrer ce style d'enseignement."],
    pt: ["Como o Muta deve ensinar?", "Guie-me", "Mostre-me como", "Exemplos do dia a dia", "Apenas dicas", "Estilo de ensino salvo", "Não foi possível salvar esse estilo de ensino."],
    de: ["Wie soll Muta unterrichten?", "Führe mich", "Zeig mir, wie es geht", "Beispiele aus dem Alltag", "Nur Hinweise", "Unterrichtsstil gespeichert", "Dieser Unterrichtsstil konnte nicht gespeichert werden."],
  });
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
      "style.label": "How should Muta teach?",
      "style.guide": "Guide me",
      "style.show": "Show me how",
      "style.examples": "Everyday examples",
      "style.hints": "Hints only",
      "style.saved": "Teaching style saved",
      "style.saveFailed": "Couldn’t save that teaching style.",
      "style.explain": "Explain teaching methods",
      "style.methodGuide": "Socratic guidance",
      "style.descGuide": "Muta asks focused questions and checks your reasoning while you do the thinking.",
      "style.methodShow": "Worked-example method",
      "style.descShow": "Muta models one clear solution step by step, then helps you try the next one.",
      "style.methodExamples": "Concrete-to-abstract method",
      "style.descExamples": "Muta begins with familiar situations, then connects them to the formal idea.",
      "style.methodHints": "Minimal scaffolding",
      "style.descHints": "Muta gives the smallest useful clue and keeps the final step with you.",
      "unit.open": "STEM learning units",
      "unit.libraryTitle": "Learn across STEM",
      "unit.back": "← All STEM units",
      "unit.close": "Close learning unit",
      "unit.import": "Import unit",
      "unit.importHelp": "Open a Muta unit JSON file from this device. No network is used.",
      "unit.loading": "Opening unit…",
      "unit.loadFailed": "Couldn’t open that unit.",
      "unit.invalid": "That file is not a valid Muta unit.",
      "unit.mastery": "Linear equations mastery",
      "unit.masteryNamed": "{title} mastery",
      "unit.summaryMinutes": "{summary} · {minutes} min",
      "unit.submit": "Check my answers",
      "unit.submitFailed": "Couldn’t check those answers.",
      "unit.unchecked": "One or more answers could not be checked. Your mastery was not changed.",
      "unit.sources": "Sources",
      "unit.previewOnly": "Imported units are preview-only unless they match a built-in verified unit.",
      "unit.score": "Checkpoint score: {score}%",
      "unit.progressNotSaved": "Your answers were checked, but progress could not be saved.",
      "settings.title": "Settings",
      "settings.close": "Close settings",
      "settings.interface": "Interface",
      "settings.language": "Language",
      "settings.languageAuto": "Auto",
      "settings.languageHelp": "Auto mode detects your language and replies in it.",
      "settings.general": "General",
      "settings.studyCountry": "Where do you study?",
      "settings.studyCountryHelp": "Uses local currency and exam examples when helpful.",
      "settings.studyCountryNone": "Not set",
      "settings.parallel": "Generate in multiple chats",
      "settings.parallelHelp": "Parallel replies share same CPU and RAM. Queue queries to optimize resources.",
      "settings.saveFailed": "Couldn’t save that setting.",
      "runtime.offlineLocal": "offline · local CPU",
      "model.loading": "Loading models…",
      "model.choose": "Choose a model",
      "model.runsLocal": "Runs on this machine",
      "model.defaultRecommended": "Best fit is selected.",
      "model.recommended": "Recommended",
      "model.imageInput": "Image input",
      "model.localTutor": "Local tutor model",
      "model.textTutor": "Text tutor",
      "model.imageTutor": "Text and image tutor",
      "model.switching": "Switching model…",
      "model.currentLocal": "Current local model",
      "model.chooseLocal": "Choose the local tutor model",
      "model.operatorOnly": "Only the host can change the model.",
      "model.outsideRegistry": "Choose an installed model.",
      "model.noneInstalled": "No verified optional model is installed.",
      "model.checking": "Checking model status…",
      "model.switchUncertain": "Checking the model switch…",
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
      "empty.body": "Ask a question, add a photo, or use the mic.",
      "chat.conversation": "Conversation",
      "composer.placeholder": "Ask anything",
      "composer.attachImageTitle": "Attach an image (or drag one in)",
      "composer.attachImage": "Attach an image",
      "composer.attachAudioTitle": "Attach an audio file (or drag one in)",
      "composer.attachAudio": "Attach an audio file",
      "composer.send": "Send",
      "composer.sendMessage": "Send message",
      "composer.stop": "Stop the reply (Esc)",
      "fineprint": "Muta can make mistakes. Check important info.",
      "startup.tagline": "the personal education companion for every student at every level. powered by AI.",
      "startup.opening": "Opening Muta",
      "startup.verifying": "Checking your tutor",
      "startup.packReady": "Tutor files ready",
      "startup.starting": "Starting the tutor",
      "startup.retrying": "Trying again",
      "startup.connecting": "Opening the tutor",
      "startup.openingData": "Opening your chats",
      "startup.loadingTutor": "Loading the tutor",
      "startup.finishing": "Almost ready",
      "startup.ready": "Ready",
      "startup.failed": "Muta couldn’t finish starting",
      "startup.retry": "Retry",
      "startup.progress": "{stage}, {percent}%",
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
      "conversation.pin": "Pin chat",
      "conversation.unpin": "Unpin chat",
      "conversation.pinned": "Pinned",
      "conversation.chats": "Chats",
      "conversation.deleteTitle": "Delete chat?",
      "conversation.deleteBody": "This will delete {title}.",
      "conversation.cancel": "Cancel",
      "conversation.confirmDelete": "Delete",
      "conversation.deleteFailed": "Couldn’t delete that chat.",
      "conversation.pinFailed": "Couldn’t update that chat.",
      "conversation.open": "Open conversation: {title}",
      "code.copy": "Copy code",
      "code.copied": "Copied",
      "code.copyFailed": "Couldn’t copy",
      "code.plain": "Code",
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

  const releaseEnglish = globalThis.MutaReleaseEnglish
    || (typeof require === "function" ? require("./release-english.js") : {});
  Object.assign(catalogs[DEFAULT_LOCALE], releaseEnglish);
  // Pitch features are additive and English is the required first catalog. Keeping these keys
  // outside the release-complete catalog lets the 26 reviewed interface packs remain visible;
  // untranslated feature copy intentionally falls back to this English layer.
  const additiveEnglishCatalog = Object.freeze({
    "nav.learn": "Learn",
    "learning.kicker": "OFFLINE LEARNING LIBRARY",
    "learning.title": "Learn with Muta",
    "learning.subtitle": "Interactive books, practice, games and experiments—all saved on this device.",
    "learning.close": "Close Learn",
    "learning.sections": "Learn sections",
    "learning.tabLibrary": "Library",
    "learning.tabStudio": "Study studio",
    "learning.tabPractice": "Practice",
    "learning.tabGames": "Games",
    "learning.tabPlayground": "Playground",
    "learning.tabTracker": "Tracker",
    "learning.tabCorrectness": "Correctness",
    "learning.show": "Show",
    "learning.allSubjects": "All subjects",
    "learning.subjectAI": "AI",
    "learning.subjectMath": "Mathematics",
    "learning.subjectPhysical": "Physical science",
    "learning.subjectLife": "Life science",
    "learning.subjectHistory": "History",
    "learning.import": "Import .muta",
    "learning.libraryTitle": "Your offline library",
    "learning.libraryHelp": "Download once, learn anywhere. Import a .muta course from a teacher or friend and it stays on this device.",
    "learning.included": " · Included",
    "learning.imported": " · Imported",
    "learning.courseMeta": "{chapters} chapters · {minutes} min{exams}",
    "learning.exams": " · {exams}",
    "learning.continue": "Continue",
    "learning.openCourse": "Open course",
    "learning.export": "Export",
    "learning.remove": "Remove",
    "learning.removeConfirm": "Remove “{title}” from this device? The exported .muta file is not affected.",
    "learning.noCourses": "No courses match this subject yet. Import a .muta course to add one.",
    "learning.storageUnavailable": "This browser cannot save offline courses.",
    "learning.importLoadFailed": "Imported courses could not be loaded.",
    "learning.invalidBundled": "Couldn’t open the included course {file}.",
    "learning.coursePractice": "Course practice",
    "learning.numericAnswer": "Your numeric answer",
    "learning.checkAnswer": "Check answer",
    "learning.correct": "Correct. ",
    "learning.notYet": "Not yet. ",
    "learning.checked": "Checked",
    "learning.tryAgain": "Try again",
    "learning.readerChapter": "{subject} · Chapter {chapter} of {total}",
    "learning.previousChapter": "Previous chapter",
    "learning.nextChapter": "Next chapter",
    "learning.interactiveExplanation": "Interactive explanation",
    "learning.readerEmpty": "This page focuses on reading and practice. Open Playground for interactive experiments.",
    "learning.practiceTitle": "Practice with explanations",
    "learning.practiceHelp": "Every question is authored inside its course, checked locally, and followed by an explanation—not just a score.",
    "learning.reviewConcept": "Review this concept in the course reader.",
    "learning.flashcardsTitle": "{title} flashcards",
    "learning.flashcardsHelp": "Select a card to reveal its study cue.",
    "learning.buildsOn": "Builds on {concepts}.",
    "learning.startingConcept": "A starting concept in this course.",
    "learning.atGlance": "{title} at a glance",
    "learning.atGlanceHelp": "Concepts are ordered by their prerequisite relationships.",
    "learning.coursePracticeTitle": "{title} practice",
    "learning.coursePracticeHelp": "Answers are checked locally and include authored explanations.",
    "learning.studioTitle": "Study studio",
    "learning.studioHelp": "Turn an installed course into a guided lesson, quiz, flashcards, diagram or infographic. For a new topic, hand a structured request to the offline tutor.",
    "learning.newTopic": "New topic",
    "learning.topicPlaceholder": "e.g. photosynthesis, bearings, West African trade",
    "learning.installedCourse": "Installed course",
    "learning.guidedLesson": "Guided lesson",
    "learning.guidedLessonHelp": "Step-by-step reading with checkpoints and an interactive side panel.",
    "learning.practiceQuiz": "Practice quiz",
    "learning.practiceQuizHelp": "Local questions with immediate feedback and explanations.",
    "learning.flashcards": "Flashcards",
    "learning.flashcardsModeHelp": "Compact prompts for active recall.",
    "learning.diagram": "Diagram",
    "learning.diagramHelp": "Open the course's interactive visual experiment.",
    "learning.infographic": "Infographic",
    "learning.infographicHelp": "See the course's concept and prerequisite structure.",
    "learning.createWithTutor": "Create new topic with tutor",
    "learning.studioEvidence": "Installed-course tools are deterministic and source-linked. New-topic tools use the selected local model, so important claims still need the correctness trail.",
    "learning.studioPromptLesson": "Create a short guided lesson with checkpoints and one diagram",
    "learning.studioPromptQuiz": "Create a five-question practice quiz with explanations after each answer",
    "learning.studioPromptFlashcards": "Create concise study flashcards with question and answer sides",
    "learning.studioPromptDiagram": "Draw and explain an accurate labelled diagram",
    "learning.studioPromptInfographic": "Create a concise visual infographic with key facts and relationships",
    "learning.studioPromptSuffix": "{request} about {topic}. Teach it at secondary-school level, show uncertainty honestly, and keep every factual claim source-ready.",
    "learning.gamesTitle": "Learning games",
    "learning.gamesHelp": "Short challenges built into shareable course modules. They end after a few rounds and always explain the answer.",
    "learning.play": "Play",
    "learning.gameComplete": "Game complete",
    "learning.gameResult": "You answered {score} of {total} correctly. Review the explanations, then try again when you are ready.",
    "learning.backGames": "Back to games",
    "learning.gameScore": "Round {round} of {total} · Score {score}",
    "learning.seeResult": "See result",
    "learning.nextRound": "Next round",
    "learning.playgroundTitle": "Interactive playground",
    "learning.playgroundHelp": "Change a parameter, watch the model respond, and connect the motion back to the lesson. Everything runs locally.",
    "learning.openExperiment": "Open experiment",
    "learning.allExperiments": "All experiments",
    "learning.trackerTitle": "Learning tracker",
    "learning.trackerHelp": "Evidence of learning—not screen-time theatre. Mastery changes only when an authored question or activity is checked.",
    "learning.timeToday": "Time learning today",
    "learning.topicsToday": "Topics today",
    "learning.checkedAttempts": "Checked attempts",
    "learning.evidenceAccuracy": "Evidence accuracy",
    "learning.noEvidence": "No evidence yet",
    "learning.minutes": "{minutes} min",
    "learning.graphTitle": "Knowledge and context graph",
    "learning.graphHelp": "Each node is a course concept. A filled node has repeated correct evidence; lines show prerequisites.",
    "learning.todayTitle": "What you learned today",
    "learning.todayHelp": "A local summary assembled from course, practice, game and playground activity.",
    "learning.correctEvidence": "Correct evidence",
    "learning.needsReview": "Needs review",
    "learning.noTimeline": "Open a course or answer a practice question to begin your learning record.",
    "learning.graphLabel": "Concept prerequisite graph",
    "learning.correctnessTitle": "Correctness trail",
    "learning.correctnessHelp": "Muta separates a fluent explanation from evidence that can actually support it.",
    "learning.computed": "Computed",
    "learning.computedHelp": "Maths and numeric work can be checked by bounded symbolic or numerical tools.",
    "learning.sourceBacked": "Source-backed",
    "learning.sourceBackedHelp": "Course claims show their source and licence; uploaded textbooks keep page citations.",
    "learning.crossChecked": "Cross-checked",
    "learning.crossCheckedHelp": "Rules look for contradictions, invalid working and unsupported agreement with a learner.",
    "learning.needsReviewHelp": "If Muta cannot establish evidence, it says so and points to a source, teacher or class instead of showing a green badge.",
    "learning.correctnessBoundaryTitle": "What this does not claim",
    "learning.correctnessBoundary": "There is no universal proof checker for history, biology or open-ended explanations. For those subjects, Muta exposes provenance and uncertainty and supports human review. The language model is never the final authority.",
    "learning.sourcesTitle": "Sources in the installed library",
    "learning.sourcesHelp": "Every bundled course exposes the references used to author and review it.",
    "learning.fileTooLarge": "That course is too large. .muta files must be 2 MB or smaller.",
    "learning.invalidFile": "This is not a valid Muta course file.",
    "learning.coreConflict": "An included course with this ID is already installed.",
    "learning.importedStatus": "Imported “{title}”.",
    "tour.initialStep": "1 of 6",
    "tour.step": "{step} of {total}",
    "tour.welcome": "Welcome to Muta",
    "tour.intro": "Let’s take a quick tour. Everything here works without internet.",
    "tour.skip": "Skip tour",
    "tour.back": "Back",
    "tour.next": "Next",
    "tour.finish": "Finish",
    "tour.deviceTitle": "Muta works on this device",
    "tour.deviceCopy": "Your tutor, courses and learning record remain available without internet.",
    "tour.modelTitle": "Choose your local tutor",
    "tour.modelCopy": "Muta ships with a tutor model. You can add compatible GGUF models later.",
    "tour.styleTitle": "Choose how Muta teaches",
    "tour.styleCopy": "Use questions, worked examples, everyday analogies or hints. The explanation button describes each style.",
    "tour.learnTitle": "Open Learn",
    "tour.learnCopy": "Read interactive books, practise, play short learning games and use the playground.",
    "tour.settingsTitle": "Settings and teacher controls",
    "tour.settingsCopy": "Change language and appearance, manage files, replay this tour and configure Host Mode.",
    "tour.askTitle": "Ask in your own words",
    "tour.askCopy": "Type, speak, attach a photo or add a textbook. Muta can make mistakes, so use the correctness trail for important claims.",
    "settings.gettingStarted": "Getting started",
    "settings.tourHelp": "Replay the guided tour of chat, learning tools and offline controls.",
    "settings.showTour": "Show tour",
    "nav.class": "Class",
    "course.label": "Course",
    "course.noCourse": "No course",
    "course.setByTeacher": "Set by your teacher",
    "course.withholding": "Final answers are withheld",
    "course.loadFailed": "Couldn’t load courses.",
    "course.style.socratic": "Guide me",
    "course.style.subgoal": "Show me how",
    "course.style.analogy": "Everyday examples",
    "course.style.hints": "Hints only",
    "host.courses": "Courses",
    "host.coursesHelp": "Set how Muta teaches in each class.",
    "host.courseAdd": "Add course",
    "host.courseEdit": "Edit course",
    "host.courseName": "Course name",
    "host.courseStyle": "Teaching style",
    "host.courseLock": "Lock style",
    "host.courseWithhold": "Withhold final answers",
    "host.courseNote": "Teacher note",
    "host.courseNoteHelp": "Muta may repeat this instruction; include no private information · {count}/400",
    "host.courseSave": "Save course",
    "host.courseCancel": "Cancel",
    "host.courseEmpty": "No courses yet.",
    "host.courseLoadFailed": "Couldn’t load courses.",
    "host.courseSaveFailed": "Couldn’t save that course.",
    "host.courseDelete": "Delete course",
    "host.courseDeleteConfirm": "Delete {name}? Learners will no longer be able to select it.",
    "host.courseDeleteFailed": "Couldn’t delete that course.",
    "class.title": "Class board",
    "class.description": "Ask classmates and your teacher when you want a second check.",
    "class.refresh": "Refresh",
    "class.newQuestion": "Ask the class",
    "class.questionLabel": "Your question",
    "class.questionHint": "Include the problem and the step you want checked.",
    "class.askTeacher": "Ask the teacher too",
    "class.post": "Post question",
    "class.posting": "Posting…",
    "class.posted": "Question posted.",
    "class.listLabel": "Class questions",
    "class.loading": "Loading the class board…",
    "class.empty": "No questions yet. Start the first one.",
    "class.loadFailed": "Couldn’t load the class board.",
    "class.by": "Asked by {name}",
    "class.replyCount": "{count} replies",
    "class.replyCountOne": "1 reply",
    "class.addressedTeacher": "Teacher asked",
    "class.back": "Back to questions",
    "class.replyLabel": "Your reply",
    "class.replyHint": "Explain the next step without taking over their work.",
    "class.sendReply": "Post reply",
    "class.sendingReply": "Posting reply…",
    "class.replied": "Reply posted.",
    "class.teacherVerified": "Teacher-verified",
    "class.verify": "Mark teacher-verified",
    "class.unverify": "Remove teacher verification",
    "class.verifyFailed": "Couldn’t update teacher verification.",
    "class.delete": "Delete question",
    "class.deleteConfirm": "Delete this question and all of its replies?",
    "class.deleteFailed": "Couldn’t delete that question.",
    "class.writeFailed": "Couldn’t post that yet.",
    "class.verifyFallback": "Muta couldn’t verify this one.",
    "class.askTeacherAction": "Ask your teacher",
    "class.askClassAction": "Ask your class",
    "resources.sections": "{count} sections",
    "resources.attachDocument": "Attach a PDF, Markdown or text file",
    "rag.passage": "passage {page}",
    "rag.sectionMeta": "Notes · {section}",
    "rag.openSection": "Open {title} at {section}",
    "rag.citationSection": "Citation {number}: {title}, {section}",
    "reader.kicker": "From your files",
    "reader.close": "Close reader",
    "reader.loading": "Opening…",
    "reader.failed": "Couldn’t open this file.",
    "rag.sourcesConsulted": "Sources consulted"
  });

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
    const value = catalogs[normalized]?.[key]
      ?? catalogs[DEFAULT_LOCALE][key]
      ?? additiveEnglishCatalog[key]
      ?? key;
    return interpolate(value, variables);
  }

  const translatableAttributes = ["title", "aria-label", "alt", "placeholder", "data-placeholder"];

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
      "model.textTutor": messages["model.localTutor"],
      "model.imageTutor": `${messages["model.localTutor"]} · ${attach}`,
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
    const styleMessages = Object.fromEntries(
      STYLE_KEYS.map((key, index) => [key, STYLE_MESSAGES[definition.tag]?.[index]])
        .filter(([, value]) => Boolean(value)),
    );
    const combined = { ...(catalogs[definition.tag] || {}), ...messages, ...styleMessages };
    // Retired visible copy must not reappear when older checked-in locale snapshots register.
    delete combined["settings.limits"];
    for (const key of ENGLISH_FALLBACK_KEYS) {
      if (!combined[key] && catalogs.en[key]) combined[key] = catalogs.en[key];
    }
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
    ENGLISH_FALLBACK_KEYS,
    catalogs,
    additiveEnglishCatalog,
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
