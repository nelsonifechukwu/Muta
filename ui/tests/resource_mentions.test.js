"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  append,
  hasTriggerBoundary,
  isPlacementMarker,
  nameFor,
  place,
  removeMarker,
  removeTrigger,
  resolveResources,
  sanitizeDraft,
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
  assert.deepEqual(segment("Read @{a\rb}"), [
    { type: "text", value: "Read " },
    { type: "resource", name: "a b" },
  ]);
});

test("ordinary at signs and malformed tokens remain ordinary text", () => {
  for (const source of [
    "Email me@example.org or type @book and @{unfinished",
    "Explain @{not\na document}",
    "Read @{x}\u0301 now",
  ]) {
    assert.deepEqual(segment(source), [{ type: "text", value: source }]);
  }
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

test("preserves the picker position when composing the durable mention token", () => {
  const source = "For this implementation, our test file is @res. if there is more";
  const at = source.indexOf("@res");
  const placed = place(source, at, at + "@res".length, []);
  assert.ok(placed);
  const resource = { id: "a", name: "resource.pdf", marker: placed.marker };
  assert.equal(
    append(placed.text, [resource]),
    "For this implementation, our test file is @{resource.pdf}. if there is more",
  );
  assert.equal(removeMarker(placed.text, placed.marker),
    "For this implementation, our test file is . if there is more");
  assert.equal(isPlacementMarker(placed.marker), true);
});

test("uses distinct placement markers and replaces repeated references in place", () => {
  const first = place("Compare @one with @two", 8, 12, []);
  assert.ok(first);
  const firstResource = { id: "a", name: "One.pdf", marker: first.marker };
  const secondAt = first.text.indexOf("@two");
  const second = place(first.text, secondAt, secondAt + 4, [firstResource]);
  assert.ok(second);
  const secondResource = { id: "b", name: "Two.pdf", marker: second.marker };
  assert.notEqual(first.marker, second.marker);
  assert.equal(append(second.text, [firstResource, secondResource]),
    "Compare @{One.pdf} with @{Two.pdf}");
  assert.equal(append(`A${first.marker}B`, []), `A${first.marker}B`);
  const unicode = "می‌خواهم 👨‍👩‍👧‍👦᠎";
  assert.equal(append(unicode, []), unicode);
});

test("reconciles queued text with duplicate ids and marker ownership", () => {
  const a = "a".repeat(32);
  const b = "b".repeat(32);
  const first = place("@one", 0, 4, []);
  const second = place("@two", 0, 4, [{ marker: first.marker }]);
  assert.ok(first && second);

  const duplicateId = sanitizeDraft(`first${first.marker} second${second.marker}`, [
    { id: a, name: "One.pdf", marker: first.marker },
    { id: a, name: "Duplicate id.pdf", marker: second.marker },
  ]);
  assert.deepEqual(duplicateId.resources, [
    { id: a, name: "One.pdf", marker: first.marker },
  ]);
  assert.equal(duplicateId.text, `first${first.marker} second`);

  const sharedMarker = sanitizeDraft(`first${first.marker} second${first.marker}`, [
    { id: a, name: "One.pdf", marker: first.marker },
    { id: b, name: "Two.pdf", marker: first.marker },
  ]);
  assert.equal(sharedMarker.text, "first second");
  assert.deepEqual(sharedMarker.resources, [
    { id: a, name: "One.pdf", marker: undefined },
    { id: b, name: "Two.pdf", marker: undefined },
  ]);

  const invalid = sanitizeDraft(`valid\ntext${second.marker}\x17`, [
    { id: "not-a-resource-id", name: "Invalid.pdf", marker: second.marker },
  ]);
  assert.deepEqual(invalid, { text: "valid\ntext", resources: [] });
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

test("resolves typed legacy mentions only to one ready document", () => {
  const ready = { id: "a".repeat(32), name: "Physics.pdf", status: "ready" };
  const processing = { id: "b".repeat(32), name: "Physics.pdf", status: "processing" };
  const failed = { id: "c".repeat(32), name: "Failed.pdf", status: "failed" };
  assert.deepEqual(resolveResources("Read @{Physics.pdf}", [], [processing, ready], 8), [
    { id: ready.id, name: "Physics.pdf" },
  ]);
  assert.deepEqual(resolveResources("Read @{Failed.pdf}", [], [failed], 8), []);
  assert.deepEqual(resolveResources("Read @{Physics.pdf}", [], [ready, { ...ready, id: "d".repeat(32) }], 8), []);
  assert.deepEqual(resolveResources("Anything", [ready], [failed], 8), [ready]);
});
