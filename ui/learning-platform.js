(function initMutaLearningPlatform(global) {
  "use strict";

  const COURSE_VERSION = 2;
  const MAX_FILE_BYTES = 2 * 1024 * 1024;
  const MAX_EVENTS = 2500;
  const DB_NAME = "muta-learning-library";
  const DB_VERSION = 1;
  const STORE_NAME = "courses";
  const EVENT_KEY = "muta-learning-events-v1";
  const TOUR_KEY = "muta-first-tour-v1";
  const CORE_COURSES = Object.freeze([
    { file: "ai-foundations.muta", symbol: "AI" },
    { file: "mathematics-waec-jamb.muta", symbol: "ƒx" },
    { file: "physical-science.muta", symbol: "F" },
    { file: "life-science.muta", symbol: "DNA" },
    { file: "west-african-history.muta", symbol: "AD" },
  ]);
  const SUBJECT_SYMBOLS = Object.freeze({
    "Artificial Intelligence": "AI",
    Mathematics: "ƒx",
    "Physical Science": "F",
    "Life Science": "DNA",
    History: "AD",
  });
  const ALLOWED_SUBJECTS = new Set(Object.keys(SUBJECT_SYMBOLS));
  const ALLOWED_BLOCKS = new Set(["markdown", "callout", "visualization", "activity"]);
  const ALLOWED_ACTIVITY_TYPES = new Set(["mcq", "numeric"]);

  const state = {
    courses: [],
    currentCourse: null,
    currentChapter: 0,
    tab: "library",
    activeSince: 0,
    game: null,
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const text = (key, variables = {}) => global.MutaI18n.t(key, variables);
  const learningText = (key, variables = {}) => text(`learning.${key}`, variables);
  const view = () => $("#learning-view");
  const resetViewScroll = () => {
    const reset = () => {
      view()?.scrollTo({ top: 0, left: 0, behavior: "auto" });
      $("#learning-center .learning-shell")?.scrollTo({ top: 0, left: 0, behavior: "auto" });
    };
    reset();
    global.requestAnimationFrame?.(reset);
  };
  const status = (message) => { const node = $("#learning-status"); if (node) node.textContent = message || ""; };
  const boundedText = (value, max, required = true) => (
    typeof value === "string" && value.length <= max && (!required || value.trim().length > 0)
  );
  const safeId = (value) => typeof value === "string" && /^[a-z0-9][a-z0-9-]{0,79}$/.test(value);
  const safePartId = (value) => typeof value === "string" && /^[a-z0-9][a-z0-9_-]{0,79}$/.test(value);
  const plainRecord = (value) => value && typeof value === "object" && !Array.isArray(value);
  const onlyKeys = (value, keys) => plainRecord(value) && Object.keys(value).every((key) => keys.includes(key));
  const noExecutableMarkup = (value) => typeof value !== "string" || !/<\s*\/?\s*(?:script|iframe|object|embed|style|link|meta|form)\b/i.test(value);

  function validHttpsUrl(value) {
    try { return new URL(value).protocol === "https:"; } catch { return false; }
  }

  function validVisualization(spec) {
    return plainRecord(spec) && Boolean(global.MutaViz?.validateSpec(spec).ok);
  }

  function validActivity(activity, conceptIds) {
    if (!onlyKeys(activity, [
      "id", "type", "concept_id", "prompt", "options", "answer", "tolerance",
      "explanation", "exam_style", "difficulty",
    ])) return false;
    if (!safePartId(activity.id) || !ALLOWED_ACTIVITY_TYPES.has(activity.type)) return false;
    if (!conceptIds.has(activity.concept_id) || !boundedText(activity.prompt, 1600)) return false;
    if (!boundedText(activity.explanation, 2000) || !noExecutableMarkup(activity.explanation)) return false;
    if (activity.exam_style != null && !["WAEC-style", "JAMB-style", "Course practice"].includes(activity.exam_style)) return false;
    if (activity.type === "mcq") {
      return Array.isArray(activity.options)
        && activity.options.length >= 2 && activity.options.length <= 6
        && activity.options.every((option) => boundedText(option, 500) && noExecutableMarkup(option))
        && Number.isInteger(activity.answer)
        && activity.answer >= 0 && activity.answer < activity.options.length;
    }
    return typeof activity.answer === "number"
      && (activity.tolerance == null || (typeof activity.tolerance === "number" && activity.tolerance >= 0));
  }

  function validGame(game, conceptIds) {
    if (!onlyKeys(game, ["id", "type", "title", "description", "concept_id", "rounds"])) return false;
    return safePartId(game.id) && game.type === "challenge"
      && boundedText(game.title, 160) && boundedText(game.description, 600)
      && conceptIds.has(game.concept_id)
      && Array.isArray(game.rounds) && game.rounds.length >= 3 && game.rounds.length <= 12
      && game.rounds.every((round) => onlyKeys(round, ["prompt", "options", "answer", "explanation"])
        && boundedText(round.prompt, 1000)
        && Array.isArray(round.options) && round.options.length >= 2 && round.options.length <= 6
        && round.options.every((option) => boundedText(option, 300))
        && Number.isInteger(round.answer) && round.answer >= 0 && round.answer < round.options.length
        && boundedText(round.explanation, 1000));
  }

  function validCourse(course) {
    if (!onlyKeys(course, [
      "version", "kind", "id", "title", "subject", "level", "description",
      "estimated_minutes", "exams", "author", "license", "concepts", "chapters",
      "activities", "games", "playgrounds", "sources",
    ])) return false;
    if (course.version !== COURSE_VERSION || course.kind !== "course" || !safeId(course.id)) return false;
    if (!boundedText(course.title, 180) || !boundedText(course.description, 700)) return false;
    if (!ALLOWED_SUBJECTS.has(course.subject) || !boundedText(course.level, 100)) return false;
    if (!Number.isInteger(course.estimated_minutes) || course.estimated_minutes < 5 || course.estimated_minutes > 600) return false;
    if (!Array.isArray(course.exams) || course.exams.length > 8 || !course.exams.every((item) => boundedText(item, 40))) return false;
    if (!onlyKeys(course.author, ["name", "url"]) || !boundedText(course.author.name, 120)) return false;
    if (course.author.url && !validHttpsUrl(course.author.url)) return false;
    if (!onlyKeys(course.license, ["name", "url"]) || !boundedText(course.license.name, 120)) return false;
    if (course.license.url && !validHttpsUrl(course.license.url)) return false;
    if (!Array.isArray(course.concepts) || !course.concepts.length || course.concepts.length > 80) return false;
    const conceptIds = new Set();
    for (const concept of course.concepts) {
      if (!onlyKeys(concept, ["id", "title", "prerequisites"]) || !safePartId(concept.id)
        || conceptIds.has(concept.id) || !boundedText(concept.title, 140)
        || !Array.isArray(concept.prerequisites) || concept.prerequisites.length > 12
        || !concept.prerequisites.every(safePartId)) return false;
      conceptIds.add(concept.id);
    }
    if (course.concepts.some((concept) => concept.prerequisites.some((item) => !conceptIds.has(item)))) return false;
    if (!Array.isArray(course.activities) || course.activities.length < 3 || course.activities.length > 120
      || !course.activities.every((item) => validActivity(item, conceptIds))) return false;
    const activityIds = new Set(course.activities.map((item) => item.id));
    if (activityIds.size !== course.activities.length) return false;
    if (!Array.isArray(course.chapters) || !course.chapters.length || course.chapters.length > 30) return false;
    const chapterIds = new Set();
    for (const chapter of course.chapters) {
      if (!onlyKeys(chapter, ["id", "title", "summary", "concept_ids", "blocks"])
        || !safePartId(chapter.id) || chapterIds.has(chapter.id)
        || !boundedText(chapter.title, 180) || !boundedText(chapter.summary, 600)
        || !Array.isArray(chapter.concept_ids) || !chapter.concept_ids.length
        || !chapter.concept_ids.every((id) => conceptIds.has(id))
        || !Array.isArray(chapter.blocks) || !chapter.blocks.length || chapter.blocks.length > 40) return false;
      chapterIds.add(chapter.id);
      for (const block of chapter.blocks) {
        if (!plainRecord(block) || !ALLOWED_BLOCKS.has(block.type)) return false;
        if (block.type === "markdown" && (!onlyKeys(block, ["type", "text"]) || !boundedText(block.text, 14000) || !noExecutableMarkup(block.text))) return false;
        if (block.type === "callout" && (!onlyKeys(block, ["type", "title", "text"]) || !boundedText(block.title, 140) || !boundedText(block.text, 3000) || !noExecutableMarkup(block.text))) return false;
        if (block.type === "visualization" && (!onlyKeys(block, ["type", "spec"]) || !validVisualization(block.spec))) return false;
        if (block.type === "activity" && (!onlyKeys(block, ["type", "activity_id"]) || !activityIds.has(block.activity_id))) return false;
      }
    }
    if (!Array.isArray(course.games) || course.games.length > 20 || !course.games.every((game) => validGame(game, conceptIds))) return false;
    if (!Array.isArray(course.playgrounds) || course.playgrounds.length > 20
      || !course.playgrounds.every((playground) => onlyKeys(playground, ["id", "title", "description", "concept_id", "spec"])
        && safePartId(playground.id) && boundedText(playground.title, 160)
        && boundedText(playground.description, 600) && conceptIds.has(playground.concept_id)
        && validVisualization(playground.spec))) return false;
    return Array.isArray(course.sources) && course.sources.length >= 1 && course.sources.length <= 30
      && course.sources.every((source) => onlyKeys(source, ["title", "url", "note", "license"])
        && boundedText(source.title, 300) && validHttpsUrl(source.url)
        && boundedText(source.note, 1000, false) && boundedText(source.license, 120, false));
  }

  function canonicalCourse(course) {
    return JSON.parse(JSON.stringify(course));
  }

  function openDatabase() {
    return new Promise((resolve, reject) => {
      if (!global.indexedDB) { resolve(null); return; }
      const request = global.indexedDB.open(DB_NAME, DB_VERSION);
      request.addEventListener("upgradeneeded", () => {
        const database = request.result;
        if (!database.objectStoreNames.contains(STORE_NAME)) database.createObjectStore(STORE_NAME, { keyPath: "id" });
      });
      request.addEventListener("success", () => resolve(request.result));
      request.addEventListener("error", () => reject(request.error));
    });
  }

  async function storedCourses() {
    const database = await openDatabase();
    if (!database) return [];
    return new Promise((resolve, reject) => {
      const request = database.transaction(STORE_NAME, "readonly").objectStore(STORE_NAME).getAll();
      request.addEventListener("success", () => resolve(request.result || []));
      request.addEventListener("error", () => reject(request.error));
    });
  }

  async function storeCourse(course) {
    const database = await openDatabase();
    if (!database) throw new Error(learningText("storageUnavailable"));
    return new Promise((resolve, reject) => {
      const request = database.transaction(STORE_NAME, "readwrite").objectStore(STORE_NAME).put(canonicalCourse(course));
      request.addEventListener("success", resolve);
      request.addEventListener("error", () => reject(request.error));
    });
  }

  async function deleteStoredCourse(id) {
    const database = await openDatabase();
    if (!database) return;
    return new Promise((resolve, reject) => {
      const request = database.transaction(STORE_NAME, "readwrite").objectStore(STORE_NAME).delete(id);
      request.addEventListener("success", resolve);
      request.addEventListener("error", () => reject(request.error));
    });
  }

  function readEvents() {
    try {
      const parsed = JSON.parse(global.localStorage.getItem(EVENT_KEY) || "[]");
      return Array.isArray(parsed) ? parsed.slice(-MAX_EVENTS) : [];
    } catch { return []; }
  }

  function recordEvent(type, detail = {}) {
    const event = { type, at: new Date().toISOString(), ...detail };
    const events = [...readEvents(), event].slice(-MAX_EVENTS);
    try { global.localStorage.setItem(EVENT_KEY, JSON.stringify(events)); } catch { /* best effort */ }
    global.dispatchEvent(new CustomEvent("muta:learning-event", { detail: event }));
  }

  function activeCourseEvent(type, detail = {}) {
    if (!state.currentCourse) return;
    recordEvent(type, { course_id: state.currentCourse.id, subject: state.currentCourse.subject, ...detail });
  }

  function renderMarkdown(target, markdown) {
    // Course prose is TeX-bearing ($f(x)=2x+1$). Use the chat's math-aware renderer, which
    // shields TeX from Markdown before KaTeX runs; there was never a global renderMath.
    if (global.MutaMath?.render) {
      global.MutaMath.render(target, String(markdown || ""));
      return;
    }
    const raw = global.marked?.parse(String(markdown || ""), { breaks: true }) || String(markdown || "");
    target.innerHTML = global.DOMPurify?.sanitize(raw, { USE_PROFILES: { html: true } }) || "";
  }

  async function loadCourses() {
    const core = [];
    for (const descriptor of CORE_COURSES) {
      const response = await fetch(`courses/${descriptor.file}`, { cache: "no-store" });
      const course = await response.json();
      if (!response.ok || !validCourse(course)) throw new Error(learningText("invalidBundled", { file: descriptor.file }));
      core.push({ ...course, _origin: "core", _symbol: descriptor.symbol });
    }
    let imported = [];
    try {
      imported = (await storedCourses())
        .filter(validCourse)
        .map((course) => ({ ...course, _origin: "imported", _symbol: SUBJECT_SYMBOLS[course.subject] }));
    } catch { status(learningText("importLoadFailed")); }
    const coreIds = new Set(core.map((course) => course.id));
    state.courses = [...core, ...imported.filter((course) => !coreIds.has(course.id))];
    return state.courses;
  }

  function courseEvents(courseId) { return readEvents().filter((event) => event.course_id === courseId); }
  function courseProgress(course) {
    const attempted = new Set(courseEvents(course.id).filter((event) => event.type === "assessment" && event.correct).map((event) => event.activity_id));
    return course.activities.length ? attempted.size / course.activities.length : 0;
  }
  function masteryFor(course, conceptId) {
    const relevant = courseEvents(course.id).filter((event) => event.type === "assessment" && event.concept_id === conceptId);
    if (!relevant.length) return 0;
    const recent = relevant.slice(-5);
    return recent.filter((event) => event.correct).length / recent.length;
  }

  function heading(title, copy) {
    const header = document.createElement("header");
    header.className = "learning-section-heading";
    const h3 = document.createElement("h3"); h3.textContent = title;
    const p = document.createElement("p"); p.textContent = copy;
    header.append(h3, p);
    return header;
  }

  function button(label, className, handler) {
    const node = document.createElement("button");
    node.type = "button"; node.className = className; node.textContent = label;
    node.addEventListener("click", handler);
    return node;
  }

  function exportCourse(course) {
    const clean = canonicalCourse(course); delete clean._origin; delete clean._symbol;
    const blob = new Blob([`${JSON.stringify(clean, null, 2)}\n`], { type: "application/vnd.muta.course+json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = `${course.id}.muta`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    recordEvent("course_export", { course_id: course.id, subject: course.subject });
  }

  function renderLibrary() {
    const root = view(); root.replaceChildren();
    root.append(heading(learningText("libraryTitle"), learningText("libraryHelp")));
    const grid = document.createElement("div"); grid.className = "course-grid";
    const filter = $("#learning-filter")?.value || "all";
    const courses = state.courses.filter((course) => filter === "all" || course.subject === filter);
    for (const course of courses) {
      const card = document.createElement("article"); card.className = "course-card"; card.dataset.subject = course.subject;
      const top = document.createElement("div"); top.className = "course-card-top";
      const symbol = document.createElement("span"); symbol.className = "course-symbol"; symbol.textContent = course._symbol || SUBJECT_SYMBOLS[course.subject];
      const labels = document.createElement("div");
      const subject = document.createElement("span"); subject.className = "course-subject"; subject.textContent = course.subject;
      const origin = document.createElement("span"); origin.className = "course-origin"; origin.textContent = learningText(course._origin === "core" ? "included" : "imported");
      labels.append(subject, origin); top.append(symbol, labels);
      const body = document.createElement("div");
      const title = document.createElement("h4"); title.textContent = course.title;
      const copy = document.createElement("p"); copy.textContent = course.description;
      const meta = document.createElement("div"); meta.className = "course-card-meta";
      meta.textContent = learningText("courseMeta", {
        chapters: course.chapters.length,
        minutes: course.estimated_minutes,
        exams: course.exams.length ? learningText("exams", { exams: course.exams.join(" + ") }) : "",
      });
      const progress = document.createElement("div"); progress.className = "course-progress";
      const fill = document.createElement("span"); fill.style.width = `${Math.round(courseProgress(course) * 100)}%`; progress.append(fill);
      body.append(title, copy, meta, progress);
      const actions = document.createElement("div"); actions.className = "course-card-actions";
      actions.append(button(learningText(courseProgress(course) ? "continue" : "openCourse"), "course-open", () => openCourse(course)));
      actions.append(button(learningText("export"), "course-export", () => exportCourse(course)));
      if (course._origin === "imported") actions.append(button(learningText("remove"), "course-remove", async () => {
        if (!global.confirm(learningText("removeConfirm", { title: course.title }))) return;
        await deleteStoredCourse(course.id); await loadCourses(); renderLibrary();
      }));
      card.append(top, body, actions); grid.append(card);
    }
    if (!courses.length) {
      const empty = document.createElement("p"); empty.textContent = learningText("noCourses"); grid.append(empty);
    }
    root.append(grid);
  }

  function openCourse(course, chapterIndex = 0) {
    state.currentCourse = course;
    state.currentChapter = Math.max(0, Math.min(course.chapters.length - 1, chapterIndex));
    state.tab = "reader";
    recordEvent("course_open", { course_id: course.id, subject: course.subject });
    renderReader();
    resetViewScroll();
  }

  function renderActivity(activity, { compact = false, course = state.currentCourse } = {}) {
    const form = document.createElement("form"); form.className = compact ? "practice-card reader-block-activity" : "practice-card";
    const meta = document.createElement("div"); meta.className = "practice-meta";
    meta.textContent = `${activity.exam_style || learningText("coursePractice")}${activity.difficulty ? ` · ${activity.difficulty}` : ""}`;
    const prompt = document.createElement("h4"); prompt.textContent = activity.prompt;
    const options = document.createElement("div"); options.className = "practice-options";
    let input;
    if (activity.type === "mcq") {
      activity.options.forEach((option, index) => {
        const label = document.createElement("label"); label.className = "practice-option";
        input = document.createElement("input"); input.type = "radio"; input.name = activity.id; input.value = String(index); input.required = true;
        const copy = document.createElement("span"); copy.textContent = option;
        label.append(input, copy); options.append(label);
      });
    } else {
      input = document.createElement("input"); input.type = "number"; input.name = activity.id; input.required = true; input.step = "any";
      input.className = "practice-option"; input.setAttribute("aria-label", learningText("numericAnswer")); options.append(input);
    }
    const feedback = document.createElement("p"); feedback.className = "practice-feedback"; feedback.setAttribute("role", "status");
    const submit = document.createElement("button"); submit.type = "submit"; submit.className = "practice-submit"; submit.textContent = learningText("checkAnswer");
    form.append(meta, prompt, options, submit, feedback);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const data = new FormData(form);
      const raw = data.get(activity.id);
      const correct = activity.type === "mcq"
        ? Number(raw) === activity.answer
        : Math.abs(Number(raw) - activity.answer) <= (activity.tolerance || 0);
      feedback.className = `practice-feedback ${correct ? "correct" : "incorrect"}`;
      feedback.textContent = `${learningText(correct ? "correct" : "notYet")}${activity.explanation}`;
      submit.textContent = learningText(correct ? "checked" : "tryAgain");
      if (course) {
        recordEvent("assessment", {
          course_id: course.id,
          subject: course.subject,
          activity_id: activity.id,
          concept_id: activity.concept_id,
          correct,
        });
      }
    });
    return form;
  }

  function renderReader() {
    const course = state.currentCourse;
    if (!course) { renderLibrary(); return; }
    const chapter = course.chapters[state.currentChapter];
    const root = view(); root.replaceChildren();
    const toolbar = document.createElement("div"); toolbar.className = "reader-toolbar";
    const title = document.createElement("div");
    const subject = document.createElement("small"); subject.textContent = learningText("readerChapter", { subject: course.subject, chapter: state.currentChapter + 1, total: course.chapters.length });
    const name = document.createElement("strong"); name.textContent = chapter.title; title.append(subject, name);
    const nav = document.createElement("div"); nav.className = "reader-chapter-nav";
    const previous = button("←", "reader-secondary", () => openCourse(course, state.currentChapter - 1)); previous.disabled = state.currentChapter === 0; previous.setAttribute("aria-label", learningText("previousChapter"));
    const all = button(text("learning.tabLibrary"), "reader-secondary", () => setTab("library"));
    const next = button("→", "reader-secondary", () => openCourse(course, state.currentChapter + 1)); next.disabled = state.currentChapter === course.chapters.length - 1; next.setAttribute("aria-label", learningText("nextChapter"));
    nav.append(previous, all, next); toolbar.append(title, nav);
    const layout = document.createElement("div"); layout.className = "reader-layout";
    const book = document.createElement("article"); book.className = "reader-book reader-prose";
    const chapterTitle = document.createElement("h3"); chapterTitle.textContent = chapter.title; book.append(chapterTitle);
    const stage = document.createElement("aside"); stage.className = "reader-stage"; stage.setAttribute("aria-label", learningText("interactiveExplanation"));
    let hasStage = false;
    for (const block of chapter.blocks) {
      if (block.type === "markdown") { const prose = document.createElement("div"); renderMarkdown(prose, block.text); book.append(prose); }
      if (block.type === "callout") {
        const callout = document.createElement("aside"); callout.className = "reader-callout";
        const h4 = document.createElement("h4"); h4.textContent = block.title;
        const copy = document.createElement("div"); renderMarkdown(copy, block.text); callout.append(h4, copy); book.append(callout);
      }
      if (block.type === "activity") {
        const activity = course.activities.find((item) => item.id === block.activity_id);
        if (activity) book.append(renderActivity(activity, { compact: true, course }));
      }
      if (block.type === "visualization") {
        const mount = document.createElement("div"); stage.append(mount);
        global.MutaViz?.renderAll(mount, [block.spec]); hasStage = true;
      }
    }
    if (!hasStage) {
      const empty = document.createElement("div"); empty.className = "reader-stage-empty";
      empty.textContent = learningText("readerEmpty"); stage.append(empty);
    }
    layout.append(book, stage); root.append(toolbar, layout);
    activeCourseEvent("chapter_open", { chapter_id: chapter.id, concept_ids: chapter.concept_ids });
    root.focus({ preventScroll: true });
  }

  function renderPractice() {
    const root = view(); root.replaceChildren();
    root.append(heading(learningText("practiceTitle"), learningText("practiceHelp")));
    const grid = document.createElement("div"); grid.className = "practice-grid";
    const activities = state.courses.flatMap((course) => course.activities.map((activity) => ({ course, activity })));
    for (const item of activities.slice(0, 30)) {
      const node = renderActivity(item.activity, { course: item.course });
      node.dataset.courseId = item.course.id;
      grid.append(node);
    }
    root.append(grid);
  }

  function studioCourse() {
    const id = $("#studio-course")?.value;
    return state.courses.find((course) => course.id === id) || state.courses[0] || null;
  }

  function studioTutorPrompt(kind, topic) {
    const requests = {
      lesson: learningText("studioPromptLesson"),
      quiz: learningText("studioPromptQuiz"),
      flashcards: learningText("studioPromptFlashcards"),
      diagram: learningText("studioPromptDiagram"),
      infographic: learningText("studioPromptInfographic"),
    };
    return learningText("studioPromptSuffix", { request: requests[kind] || requests.lesson, topic });
  }

  function openTutorFromStudio(kind, topic) {
    const input = $("#input");
    if (!input || !topic.trim()) return;
    input.textContent = studioTutorPrompt(kind, topic.trim());
    input.dataset.empty = "false";
    input.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: input.textContent }));
    setOpen(false);
    input.focus();
  }

  function renderFlashcards(course, output) {
    const deck = document.createElement("div"); deck.className = "studio-flashcard-grid";
    course.concepts.forEach((concept) => {
      const chapter = course.chapters.find((item) => item.concept_ids.includes(concept.id));
      const card = button(concept.title, "studio-flashcard", (event) => {
        const revealed = event.currentTarget.dataset.revealed === "true";
        event.currentTarget.dataset.revealed = revealed ? "false" : "true";
        event.currentTarget.textContent = revealed ? concept.title : (chapter?.summary || learningText("reviewConcept"));
      });
      card.dataset.revealed = "false"; deck.append(card);
    });
    output.replaceChildren(heading(learningText("flashcardsTitle", { title: course.title }), learningText("flashcardsHelp")), deck);
  }

  function renderInfographic(course, output) {
    const grid = document.createElement("div"); grid.className = "studio-infographic";
    course.concepts.forEach((concept, index) => {
      const card = document.createElement("article");
      const number = document.createElement("span"); number.textContent = String(index + 1).padStart(2, "0");
      const title = document.createElement("h4"); title.textContent = concept.title;
      const dependency = document.createElement("p"); dependency.textContent = concept.prerequisites.length
        ? learningText("buildsOn", { concepts: concept.prerequisites.map((id) => course.concepts.find((item) => item.id === id)?.title || id).join(", ") })
        : learningText("startingConcept");
      card.append(number, title, dependency); grid.append(card);
    });
    output.replaceChildren(heading(learningText("atGlance", { title: course.title }), learningText("atGlanceHelp")), grid);
  }

  function buildStudioArtifact(kind) {
    const course = studioCourse(); const output = $("#studio-output");
    if (!course || !output) return;
    state.currentCourse = course;
    if (kind === "lesson") { openCourse(course); return; }
    if (kind === "quiz") {
      const grid = document.createElement("div"); grid.className = "practice-grid";
      course.activities.forEach((activity) => grid.append(renderActivity(activity, { course })));
      output.replaceChildren(heading(learningText("coursePracticeTitle", { title: course.title }), learningText("coursePracticeHelp")), grid);
      return;
    }
    if (kind === "flashcards") { renderFlashcards(course, output); return; }
    if (kind === "diagram") {
      const playground = course.playgrounds[0];
      if (playground) openPlayground(course, playground);
      return;
    }
    renderInfographic(course, output);
  }

  function renderStudio() {
    const root = view(); root.replaceChildren();
    root.append(heading(learningText("studioTitle"), learningText("studioHelp")));
    const form = document.createElement("section"); form.className = "studio-builder";
    const topicLabel = document.createElement("label"); topicLabel.htmlFor = "studio-topic"; topicLabel.textContent = learningText("newTopic");
    const topic = document.createElement("input"); topic.id = "studio-topic"; topic.placeholder = learningText("topicPlaceholder"); topic.maxLength = 180;
    const courseLabel = document.createElement("label"); courseLabel.htmlFor = "studio-course"; courseLabel.textContent = learningText("installedCourse");
    const select = document.createElement("select"); select.id = "studio-course";
    state.courses.forEach((course) => { const option = document.createElement("option"); option.value = course.id; option.textContent = course.title; select.append(option); });
    const cards = document.createElement("div"); cards.className = "studio-mode-grid";
    const modes = [
      ["lesson", learningText("guidedLesson"), learningText("guidedLessonHelp")],
      ["quiz", learningText("practiceQuiz"), learningText("practiceQuizHelp")],
      ["flashcards", learningText("flashcards"), learningText("flashcardsModeHelp")],
      ["diagram", learningText("diagram"), learningText("diagramHelp")],
      ["infographic", learningText("infographic"), learningText("infographicHelp")],
    ];
    modes.forEach(([id, title, copy]) => {
      const card = button("", "studio-mode-card", () => buildStudioArtifact(id)); card.dataset.mode = id;
      const strong = document.createElement("strong"); strong.textContent = title;
      const p = document.createElement("span"); p.textContent = copy; card.append(strong, p); cards.append(card);
    });
    const create = button(learningText("createWithTutor"), "course-open studio-tutor-button", () => openTutorFromStudio("lesson", topic.value));
    const hint = document.createElement("p"); hint.className = "studio-hint"; hint.textContent = learningText("studioEvidence");
    form.append(topicLabel, topic, create, courseLabel, select, cards, hint);
    const output = document.createElement("section"); output.id = "studio-output"; output.className = "studio-output";
    root.append(form, output);
  }

  function renderGames() {
    state.game = null;
    const root = view(); root.replaceChildren();
    root.append(heading(learningText("gamesTitle"), learningText("gamesHelp")));
    const grid = document.createElement("div"); grid.className = "game-grid";
    for (const course of state.courses) for (const game of course.games) {
      const card = document.createElement("article"); card.className = "game-card";
      const h4 = document.createElement("h4"); h4.textContent = game.title;
      const p = document.createElement("p"); p.textContent = game.description;
      const start = button(learningText("play"), "course-open", () => startGame(course, game));
      card.append(h4, p, start); grid.append(card);
    }
    root.append(grid);
    resetViewScroll();
  }

  function startGame(course, game) {
    state.currentCourse = course; state.game = { game, round: 0, score: 0 }; renderGameRound();
  }
  function renderGameRound() {
    const root = view(); root.replaceChildren();
    const { game, round, score } = state.game;
    if (round >= game.rounds.length) {
      root.append(heading(learningText("gameComplete"), learningText("gameResult", { score, total: game.rounds.length })));
      root.append(button(learningText("backGames"), "course-open", renderGames));
      activeCourseEvent("game_complete", { game_id: game.id, concept_id: game.concept_id, score, total: game.rounds.length });
      resetViewScroll();
      return;
    }
    const item = game.rounds[round];
    const session = document.createElement("section"); session.className = "game-session";
    const scoreLine = document.createElement("div"); scoreLine.className = "game-score"; scoreLine.textContent = learningText("gameScore", { round: round + 1, total: game.rounds.length, score });
    const prompt = document.createElement("div"); prompt.className = "game-prompt";
    const h3 = document.createElement("h3"); h3.textContent = item.prompt;
    const options = document.createElement("div"); options.className = "game-options";
    item.options.forEach((label, index) => {
      const option = button(label, "game-option", () => {
        const correct = index === item.answer;
        option.classList.add(correct ? "correct" : "incorrect");
        if (correct) state.game.score += 1;
        [...options.querySelectorAll("button")].forEach((node) => { node.disabled = true; if (Number(node.dataset.index) === item.answer) node.classList.add("correct"); });
        const explanation = document.createElement("p"); explanation.className = `practice-feedback ${correct ? "correct" : "incorrect"}`; explanation.textContent = item.explanation;
        const next = button(learningText(round + 1 === game.rounds.length ? "seeResult" : "nextRound"), "course-open", () => { state.game.round += 1; renderGameRound(); });
        prompt.append(explanation, next);
      });
      option.dataset.index = String(index); options.append(option);
    });
    prompt.append(h3, options); session.append(scoreLine, prompt); root.append(session);
    resetViewScroll();
  }

  function renderPlayground() {
    const root = view(); root.replaceChildren();
    root.append(heading(learningText("playgroundTitle"), learningText("playgroundHelp")));
    const grid = document.createElement("div"); grid.className = "playground-grid";
    for (const course of state.courses) for (const playground of course.playgrounds) {
      const card = document.createElement("article"); card.className = "playground-card";
      const h4 = document.createElement("h4"); h4.textContent = playground.title;
      const p = document.createElement("p"); p.textContent = playground.description;
      card.append(h4, p, button(learningText("openExperiment"), "course-open", () => openPlayground(course, playground))); grid.append(card);
    }
    root.append(grid);
    resetViewScroll();
  }
  function openPlayground(course, playground) {
    state.currentCourse = course;
    const root = view(); root.replaceChildren();
    const toolbar = document.createElement("div"); toolbar.className = "reader-toolbar";
    const h = document.createElement("div"); const small = document.createElement("small"); small.textContent = course.subject; const strong = document.createElement("strong"); strong.textContent = playground.title; h.append(small, strong);
    toolbar.append(h, button(learningText("allExperiments"), "reader-secondary", renderPlayground));
    const workspace = document.createElement("div"); workspace.className = "playground-workspace";
    const description = document.createElement("div"); description.className = "playground-description"; const copy = document.createElement("p"); copy.textContent = playground.description; description.append(copy);
    const canvas = document.createElement("div"); canvas.className = "playground-canvas"; global.MutaViz?.renderAll(canvas, [playground.spec]);
    workspace.append(description, canvas); root.append(toolbar, workspace);
    activeCourseEvent("playground_open", { playground_id: playground.id, concept_id: playground.concept_id });
    resetViewScroll();
  }

  function localDay(iso) { return new Date(iso).toLocaleDateString(); }
  function renderTracker() {
    const root = view(); root.replaceChildren();
    root.append(heading(learningText("trackerTitle"), learningText("trackerHelp")));
    const events = readEvents(); const today = new Date().toLocaleDateString();
    const todayEvents = events.filter((event) => localDay(event.at) === today);
    const seconds = todayEvents.filter((event) => event.type === "active_time").reduce((sum, event) => sum + Number(event.seconds || 0), 0);
    const assessed = events.filter((event) => event.type === "assessment");
    const correct = assessed.filter((event) => event.correct).length;
    const subjects = new Set(todayEvents.map((event) => event.subject).filter(Boolean));
    const stats = document.createElement("div"); stats.className = "tracker-grid";
    [[learningText("timeToday"), learningText("minutes", { minutes: Math.round(seconds / 60) })], [learningText("topicsToday"), String(subjects.size)], [learningText("checkedAttempts"), String(assessed.length)], [learningText("evidenceAccuracy"), assessed.length ? `${Math.round(correct / assessed.length * 100)}%` : learningText("noEvidence")]].forEach(([label, value]) => {
      const card = document.createElement("article"); card.className = "learning-stat-card"; const small = document.createElement("small"); small.textContent = label; const strong = document.createElement("strong"); strong.textContent = value; card.append(small, strong); stats.append(card);
    });
    root.append(stats);
    const graphTitle = heading(learningText("graphTitle"), learningText("graphHelp")); graphTitle.style.marginTop = "28px"; root.append(graphTitle);
    root.append(renderKnowledgeGraph());
    const timelineTitle = heading(learningText("todayTitle"), learningText("todayHelp")); timelineTitle.style.marginTop = "28px"; root.append(timelineTitle);
    const timeline = document.createElement("div"); timeline.className = "learning-timeline";
    for (const event of todayEvents.slice(-12).reverse()) {
      if (!event.course_id) continue;
      const course = state.courses.find((item) => item.id === event.course_id);
      const row = document.createElement("div"); row.className = "learning-timeline-item";
      const dot = document.createElement("span"); dot.className = "learning-timeline-dot";
      const copy = document.createElement("div"); const strong = document.createElement("strong"); strong.textContent = course?.title || event.course_id;
      const p = document.createElement("p"); p.textContent = event.type === "assessment" ? `${learningText(event.correct ? "correctEvidence" : "needsReview")} · ${event.concept_id}` : event.type.replaceAll("_", " ");
      copy.append(strong, p); row.append(dot, copy); timeline.append(row);
    }
    if (!timeline.children.length) timeline.textContent = learningText("noTimeline");
    root.append(timeline);
  }

  function renderKnowledgeGraph() {
    const wrap = document.createElement("div"); wrap.className = "knowledge-graph";
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg"); svg.setAttribute("viewBox", "0 0 900 300"); svg.setAttribute("role", "img"); svg.setAttribute("aria-label", learningText("graphLabel"));
    const concepts = state.courses.flatMap((course) => course.concepts.slice(0, 4).map((concept) => ({ course, concept, key: `${course.id}:${concept.id}` }))).slice(0, 18);
    const positions = new Map(concepts.map((item, index) => [item.key, { x: 75 + (index % 6) * 150, y: 65 + Math.floor(index / 6) * 100 }]));
    for (const item of concepts) for (const prereq of item.concept.prerequisites) {
      const from = positions.get(`${item.course.id}:${prereq}`); const to = positions.get(item.key); if (!from || !to) continue;
      const line = document.createElementNS(svg.namespaceURI, "line"); line.setAttribute("x1", from.x); line.setAttribute("y1", from.y); line.setAttribute("x2", to.x); line.setAttribute("y2", to.y); svg.append(line);
    }
    for (const item of concepts) {
      const position = positions.get(item.key); const group = document.createElementNS(svg.namespaceURI, "g");
      const circle = document.createElementNS(svg.namespaceURI, "circle"); circle.setAttribute("cx", position.x); circle.setAttribute("cy", position.y); circle.setAttribute("r", "25"); if (masteryFor(item.course, item.concept.id) >= .6) circle.classList.add("secure");
      const text = document.createElementNS(svg.namespaceURI, "text"); text.setAttribute("x", position.x); text.setAttribute("y", position.y + 42); text.setAttribute("text-anchor", "middle"); text.textContent = item.concept.title.slice(0, 18); group.append(circle, text); svg.append(group);
    }
    wrap.append(svg); return wrap;
  }

  function renderCorrectness() {
    const root = view(); root.replaceChildren();
    root.append(heading(learningText("correctnessTitle"), learningText("correctnessHelp")));
    const grid = document.createElement("div"); grid.className = "correctness-grid";
    [
      [learningText("computed"), learningText("computedHelp")],
      [learningText("sourceBacked"), learningText("sourceBackedHelp")],
      [learningText("crossChecked"), learningText("crossCheckedHelp")],
      [learningText("needsReview"), learningText("needsReviewHelp")],
    ].forEach(([title, copy], index) => {
      const card = document.createElement("article"); card.className = "correctness-card correctness-tier";
      const number = document.createElement("span"); number.className = "correctness-tier-index"; number.textContent = String(index + 1);
      const body = document.createElement("div"); const h4 = document.createElement("h4"); h4.textContent = title; const p = document.createElement("p"); p.textContent = copy; body.append(h4, p); card.append(number, body); grid.append(card);
    });
    root.append(grid);
    const warning = document.createElement("div"); warning.className = "correctness-warning";
    const warningTitle = document.createElement("strong"); warningTitle.textContent = learningText("correctnessBoundaryTitle");
    warning.append(warningTitle, document.createElement("br"), document.createTextNode(learningText("correctnessBoundary")));
    root.append(warning);
    const sources = heading(learningText("sourcesTitle"), learningText("sourcesHelp")); sources.style.marginTop = "28px"; root.append(sources);
    const list = document.createElement("div"); list.className = "course-grid";
    for (const course of state.courses) {
      const card = document.createElement("article"); card.className = "correctness-card"; const h4 = document.createElement("h4"); h4.textContent = course.title;
      const ul = document.createElement("ul"); course.sources.slice(0, 4).forEach((source) => { const li = document.createElement("li"); const a = document.createElement("a"); a.href = source.url; a.target = "_blank"; a.rel = "noopener noreferrer"; a.textContent = source.title; li.append(a); ul.append(li); }); card.append(h4, ul); list.append(card);
    }
    root.append(list);
  }

  function setTab(tab) {
    state.tab = tab;
    document.querySelectorAll("[data-learning-tab]").forEach((node) => node.setAttribute("aria-current", node.dataset.learningTab === tab ? "page" : "false"));
    $(".learning-actions").hidden = tab !== "library";
    if (tab === "library") renderLibrary();
    if (tab === "studio") renderStudio();
    if (tab === "practice") renderPractice();
    if (tab === "games") renderGames();
    if (tab === "playground") renderPlayground();
    if (tab === "tracker") renderTracker();
    if (tab === "correctness") renderCorrectness();
    resetViewScroll();
  }

  async function importFile(file) {
    if (!file || file.size > MAX_FILE_BYTES) throw new Error(learningText("fileTooLarge"));
    let course;
    try { course = JSON.parse(await file.text()); }
    catch { throw new Error(learningText("invalidFile")); }
    if (!validCourse(course)) throw new Error(learningText("invalidFile"));
    if (CORE_COURSES.some((item) => item.file === `${course.id}.muta`)) throw new Error(learningText("coreConflict"));
    await storeCourse(course); await loadCourses(); recordEvent("course_import", { course_id: course.id, subject: course.subject });
    setTab("library"); status(learningText("importedStatus", { title: course.title }));
  }

  let learningOpener = null;
  const LEARNING_TABS = new Set(["library", "studio", "practice", "games", "playground", "tracker", "correctness"]);

  // `tab` lets a shortcut (the home Practice card) land on a section. It is applied only after
  // the courses load, because every section renders from them.
  function setOpen(open, tab = "library") {
    const center = $("#learning-center"); center.hidden = !open;
    const app = $("#app"); if (app) app.inert = open;
    const initialTab = LEARNING_TABS.has(tab) ? tab : "library";
    if (open) {
      // Return focus to whatever opened Learn (a home card, or the rail link). On phones the
      // rail link lives in a closed drawer, where focus would be invisible.
      const active = document.activeElement;
      learningOpener = active && active !== document.body && !center.contains(active) ? active : null;
      loadCourses().then(() => setTab(initialTab)).catch((error) => status(error.message)); $("#learning-close")?.focus();
    } else {
      global.MutaViz?.cleanup(view());
      const target = learningOpener?.isConnected && learningOpener.getClientRects().length
        && !learningOpener.closest("[inert]") ? learningOpener : $("#unit-open");
      learningOpener = null;
      target?.focus();
    }
  }

  const TOUR_STEPS = Object.freeze([
    { selector: ".brand", title: "tour.deviceTitle", copy: "tour.deviceCopy" },
    { selector: "#model-trigger", title: "tour.modelTitle", copy: "tour.modelCopy" },
    { selector: "#teaching-style", title: "tour.styleTitle", copy: "tour.styleCopy" },
    { selector: "#unit-open", title: "tour.learnTitle", copy: "tour.learnCopy" },
    { selector: "#settings-open", title: "tour.settingsTitle", copy: "tour.settingsCopy" },
    { selector: "#composer", title: "tour.askTitle", copy: "tour.askCopy" },
  ]);
  let tourIndex = 0;
  function positionTour() {
    const step = TOUR_STEPS[tourIndex]; const target = $(step.selector); const highlight = $("#muta-tour-highlight"); const card = $(".muta-tour-card");
    $("#muta-tour-step").textContent = text("tour.step", { step: tourIndex + 1, total: TOUR_STEPS.length });
    $("#muta-tour-title").textContent = text(step.title); $("#muta-tour-copy").textContent = text(step.copy);
    $("#muta-tour-back").disabled = tourIndex === 0; $("#muta-tour-next").textContent = text(tourIndex === TOUR_STEPS.length - 1 ? "tour.finish" : "tour.next");
    if (!target) { highlight.hidden = true; card.style.left = "50%"; card.style.top = "50%"; return; }
    const rect = target.getBoundingClientRect(); const pad = 7; highlight.hidden = false;
    Object.assign(highlight.style, { left: `${Math.max(4, rect.left - pad)}px`, top: `${Math.max(4, rect.top - pad)}px`, width: `${rect.width + pad * 2}px`, height: `${rect.height + pad * 2}px` });
    // Clamp with the card's measured size: copy length varies by language and the card's type.
    const cardWidth = card.offsetWidth || 366; const cardHeight = card.offsetHeight || 250;
    const left = Math.min(global.innerWidth - cardWidth - 14, Math.max(14, rect.right + 18));
    const top = Math.min(global.innerHeight - cardHeight - 14, Math.max(14, rect.top));
    Object.assign(card.style, { left: `${left}px`, top: `${top}px` });
  }
  function startTour({ replay = false } = {}) {
    if (!replay && global.localStorage.getItem(TOUR_KEY)) return;
    setOpen(false); tourIndex = 0; $("#muta-tour").hidden = false; $("#app").inert = true; positionTour(); $("#muta-tour-next").focus();
  }
  function endTour(result) { $("#muta-tour").hidden = true; $("#app").inert = false; global.localStorage.setItem(TOUR_KEY, result); $("#new-chat")?.focus(); }

  function bind() {
    $("#learning-close")?.addEventListener("click", () => setOpen(false));
    $("#learning-center")?.addEventListener("click", (event) => { if (event.target.id === "learning-center") setOpen(false); });
    $("#learning-center")?.addEventListener("keydown", (event) => { if (event.key === "Escape") setOpen(false); });
    $("#learning-tabs")?.addEventListener("click", (event) => { const tab = event.target.closest("[data-learning-tab]")?.dataset.learningTab; if (tab) setTab(tab); });
    $("#learning-filter")?.addEventListener("change", renderLibrary);
    $("#learning-import")?.addEventListener("click", () => $("#file-course")?.click());
    $("#file-course")?.addEventListener("change", async (event) => { const file = event.target.files?.[0]; event.target.value = ""; try { await importFile(file); } catch (error) { status(error.message); } });
    $("#replay-tour")?.addEventListener("click", () => { $("#settings-close")?.click(); startTour({ replay: true }); });
    $("#muta-tour-skip")?.addEventListener("click", () => endTour("skipped"));
    $("#muta-tour-back")?.addEventListener("click", () => { tourIndex = Math.max(0, tourIndex - 1); positionTour(); });
    $("#muta-tour-next")?.addEventListener("click", () => { if (tourIndex === TOUR_STEPS.length - 1) endTour("completed"); else { tourIndex += 1; positionTour(); } });
    document.addEventListener?.("muta:localechange", () => {
      if (!$("#learning-center")?.hidden) {
        if (state.tab === "reader") renderReader();
        else if (state.game && state.tab === "games") renderGameRound();
        else setTab(state.tab);
      }
      if (!$("#muta-tour")?.hidden) positionTour();
    });
    global.addEventListener("resize", () => { if (!$("#muta-tour")?.hidden) positionTour(); });
    global.setInterval(() => {
      if ($("#learning-center")?.hidden || document.visibilityState !== "visible" || !state.currentCourse) return;
      activeCourseEvent("active_time", { seconds: 15 });
    }, 15000);
  }

  global.MutaLearning = Object.freeze({
    open: (tab) => setOpen(true, tab), close: () => setOpen(false), startTour,
    validateCourse: validCourse, canonicalCourse, importFile,
    _state: state,
  });

  bind();
  let tourStartChecks = 0;
  const waitForReadyTour = global.setInterval(() => {
    // First launch can also ask for analytics consent. Let the learner answer that dialog
    // before the tour dims the screen over it; time spent deciding does not use up the window.
    if ($("#product-consent-modal")?.hidden === false) return;
    tourStartChecks += 1;
    const app = $("#app");
    if (app && !app.hidden && !app.inert) {
      global.clearInterval(waitForReadyTour);
      startTour();
    } else if (tourStartChecks >= 30) {
      global.clearInterval(waitForReadyTour);
    }
  }, 500);
})(globalThis);
