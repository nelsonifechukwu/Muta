/* Pure helpers for the Muta Share course chip and class board. */
"use strict";

(() => {
  const root = typeof window !== "undefined" ? window : globalThis;
  const STYLES = new Set(["socratic", "subgoal", "analogy", "hints"]);

  function normalizeCourse(course) {
    if (!course || typeof course !== "object") return null;
    const id = String(course.id || "");
    const teachingStyle = String(course.teaching_style || "");
    if (!/^[0-9a-f]{32}$/.test(id) || !STYLES.has(teachingStyle)) return null;
    return {
      id,
      name: String(course.name || "").slice(0, 80),
      teaching_style: teachingStyle,
      lock_style: course.lock_style === true,
      withhold_final_answers: course.withhold_final_answers === true,
      teacher_note: String(course.teacher_note || "").slice(0, 400),
      created_at: String(course.created_at || ""),
      updated_at: String(course.updated_at || ""),
    };
  }

  function courseChatMetadata(course, requestedMode = null) {
    const normalized = normalizeCourse(course);
    if (!normalized) return {};
    const proposed = STYLES.has(requestedMode) ? requestedMode : normalized.teaching_style;
    return {
      course_id: normalized.id,
      mode: normalized.lock_style ? normalized.teaching_style : proposed,
    };
  }

  function renderBoardMarkdown(element, source) {
    if (!element) return { fallback: true, mathCount: 0 };
    // This is the one board rendering path. MutaMath protects TeX, parses Markdown, sanitizes
    // with DOMPurify, then invokes KaTeX with trust:false.
    if (root.MutaMath?.render) return root.MutaMath.render(element, String(source || ""));
    element.textContent = String(source || "");
    return { fallback: true, mathCount: 0 };
  }

  function excerpt(source, maxLength = 140) {
    const text = String(source || "")
      .replace(/<[^>]*>/g, " ")
      .replace(/[`*_#>\[\]]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    return text.length <= maxLength ? text : `${text.slice(0, Math.max(1, maxLength - 1))}…`;
  }

  function verificationFallbackDraft(question, reply, maxLength = 4000) {
    const parts = [
      `Question:\n${String(question || "").trim()}`,
      `Muta's reply to check:\n${String(reply || "").trim()}`,
    ];
    return parts.join("\n\n").slice(0, Math.max(1, maxLength));
  }

  function postEndpoint(postId) {
    return `/v1/share/class/posts/${encodeURIComponent(String(postId || ""))}`;
  }

  function replyVerificationEndpoint(replyId) {
    return `/v1/share/host/class/replies/${encodeURIComponent(String(replyId || ""))}/verification`;
  }

  function acceptsThreadResponse({
    requestedPostId,
    activePostId,
    payloadPostId,
    requestVersion,
    currentVersion,
  }) {
    return Boolean(
      requestedPostId
      && requestedPostId === activePostId
      && requestedPostId === payloadPostId
      && requestVersion === currentVersion,
    );
  }

  const api = {
    normalizeCourse,
    courseChatMetadata,
    renderBoardMarkdown,
    excerpt,
    verificationFallbackDraft,
    postEndpoint,
    replyVerificationEndpoint,
    acceptsThreadResponse,
    openComposer: null,
  };
  root.MutaClassroom = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
