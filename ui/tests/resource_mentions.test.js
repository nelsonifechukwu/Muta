"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  append,
  hasTriggerBoundary,
  nameFor,
  removeTrigger,
  segment,
  tokenFor,
} = require("../resource-mentions.js");

test("segments canonical document mentions without changing surrounding prose", () => {
  assert.deepEqual(segment("Read @{Algebra.pdf}, then @{Physics notes.pdf}."), [
    { type: "text", value: "Read " },
    { type: "resource", name: "Algebra.pdf" },
    { type: "text", value: ", then " },
    { type: "resource", name: "Physics notes.pdf" },
    { type: "text", value: "." },
  ]);
});

test("ordinary at signs and malformed tokens remain ordinary text", () => {
  assert.deepEqual(segment("Email me@example.org or type @book and @{unfinished"), [
    { type: "text", value: "Email me@example.org or type @book and @{unfinished" },
  ]);
  for (const source of ["Used @{notes}chapter.pdf}", "@{partial}suffix", "@{notes}.pdf}"]) {
    assert.deepEqual(segment(source), [{ type: "text", value: source }], source);
  }
});

test("an unfinished typed opener cannot swallow a selected canonical mention", () => {
  const composed = append("Explain @{unfinished", [{ id: "a", name: "Physics.pdf" }]);
  assert.equal(composed, "Explain @{unfinished @{Physics.pdf}");
  assert.deepEqual(segment(composed), [
    { type: "text", value: "Explain @{unfinished " },
    { type: "resource", name: "Physics.pdf" },
  ]);
});

test("appends selected resources once while preserving typed legacy mentions", () => {
  assert.equal(
    append("Compare @{Algebra.pdf}", [
      { id: "a", name: "Algebra.pdf" },
      { id: "b", name: "Physics.pdf" },
      { id: "b", name: "Physics.pdf" },
    ]),
    "Compare @{Algebra.pdf} @{Physics.pdf}",
  );
});

test("normalizes unsafe token delimiters in document names", () => {
  assert.equal(tokenFor({ name: "notes}\nchapter.pdf" }), "@{notes chapter.pdf}");
  assert.equal(nameFor({ name: "notes}\nchapter.pdf" }), "notes chapter.pdf");
  assert.equal(nameFor({ name: "notes\u202Efdp.exe" }), "notesfdp.exe");
  assert.deepEqual(segment("@{notes\u2067chapter.pdf}"), [
    { type: "resource", name: "noteschapter.pdf" },
  ]);
  assert.equal(nameFor({ name: "{}" }), "resource.pdf");
  assert.equal(tokenFor({ name: "\u202e" }), "@{resource.pdf}");
  assert.equal(append("", [{ id: "a", name: "{}" }]), "@{resource.pdf}");
});

test("requires a Unicode-aware token boundary before opening the picker", () => {
  for (const source of ["hello@physics", "مرحبا@فيزياء", "δοκιμή@βιβλίο", "用户@物理"]) {
    assert.equal(hasTriggerBoundary(source, source.indexOf("@")), false, source);
  }
  assert.equal(hasTriggerBoundary("Ask @physics", 4), true);
});

test("removes a picker query without leaving broken prose or a misplaced caret", () => {
  const cases = [
    ["Compare @phys with chemistry", "Compare with chemistry", 8],
    ["Read @phys, then", "Read, then", 4],
    ["@phys then", "then", 0],
  ];
  for (const [source, expected, expectedCaret] of cases) {
    const at = source.indexOf("@");
    const caret = source.indexOf("phys") + "phys".length;
    assert.deepEqual(removeTrigger(source, at, caret), {
      text: expected,
      caret: expectedCaret,
    });
  }
});
