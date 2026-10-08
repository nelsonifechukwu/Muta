"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

global.window = globalThis;
const classroom = require("../classroom.js");

const COURSE = {
  id: "0123456789abcdef0123456789abcdef",
  name: "SS2 Mathematics",
  teaching_style: "hints",
  lock_style: true,
  withhold_final_answers: true,
  teacher_note: "Ask for the learner's reasoning.",
  created_at: "2026-10-06T10:00:00+00:00",
  updated_at: "2026-10-06T10:00:00+00:00",
};

test("course metadata sends only the opaque id and server-checkable mode", () => {
  assert.deepEqual(classroom.courseChatMetadata(COURSE, "analogy"), {
    course_id: COURSE.id,
    mode: "hints",
  });
  assert.deepEqual(
    classroom.courseChatMetadata({ ...COURSE, lock_style: false }, "analogy"),
    { course_id: COURSE.id, mode: "analogy" },
  );
  assert.equal("teacher_note" in classroom.courseChatMetadata(COURSE), false);
  assert.deepEqual(classroom.courseChatMetadata({ ...COURSE, id: "../course" }), {});
});

test("class board rich text delegates to the shared sanitized math renderer", () => {
  const calls = [];
  global.MutaMath = {
    render(element, source) {
      calls.push({ element, source });
      element.rendered = true;
      return { fallback: false, mathCount: 1 };
    },
  };
  const element = { textContent: "" };
  const result = classroom.renderBoardMarkdown(
    element,
    "Try **factoring** $x^2$. <img src=x onerror=bad()>",
  );
  assert.deepEqual(result, { fallback: false, mathCount: 1 });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].element, element);
  assert.match(calls[0].source, /onerror/);
  assert.equal(element.rendered, true);
});

test("class board rendering fails closed to text without the shared renderer", () => {
  delete global.MutaMath;
  const element = { textContent: "" };
  const source = "<script>alert(1)</script> $x$";
  assert.deepEqual(classroom.renderBoardMarkdown(element, source), {
    fallback: true,
    mathCount: 0,
  });
  assert.equal(element.textContent, source);
});

test("board helpers produce bounded excerpts and encoded endpoints", () => {
  assert.equal(classroom.excerpt("## Check **this** step", 80), "Check this step");
  assert.equal(classroom.excerpt("abcdefgh", 5), "abcd…");
  assert.equal(
    classroom.postEndpoint("post/id"),
    "/v1/share/class/posts/post%2Fid",
  );
  assert.equal(
    classroom.replyVerificationEndpoint("reply/id"),
    "/v1/share/host/class/replies/reply%2Fid/verification",
  );
});

test("a stale thread response cannot replace the active thread", () => {
  const current = {
    requestedPostId: "post-b",
    activePostId: "post-b",
    payloadPostId: "post-b",
    requestVersion: 2,
    currentVersion: 2,
  };
  assert.equal(classroom.acceptsThreadResponse(current), true);
  assert.equal(
    classroom.acceptsThreadResponse({ ...current, requestedPostId: "post-a" }),
    false,
  );
  assert.equal(
    classroom.acceptsThreadResponse({ ...current, payloadPostId: "post-a" }),
    false,
  );
  assert.equal(
    classroom.acceptsThreadResponse({ ...current, requestVersion: 1 }),
    false,
  );
});

test("verification fallback preserves the learner question and maths for a class post", () => {
  assert.equal(
    classroom.verificationFallbackDraft("Solve $x+1=3$", "I get $x=9$."),
    "Question:\nSolve $x+1=3$\n\nMuta's reply to check:\nI get $x=9$.",
  );
  assert.equal(classroom.verificationFallbackDraft("1234", "5678", 12).length, 12);
});
