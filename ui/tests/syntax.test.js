"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const syntax = require("../syntax.js");

test("normalizes common declared-language aliases", () => {
  assert.equal(syntax.canonicalLanguage("language-js"), "javascript");
  assert.equal(syntax.canonicalLanguage("PY"), "python");
  assert.equal(syntax.canonicalLanguage("c++"), "cpp");
  assert.equal(syntax.canonicalLanguage("brainfuck"), "");
});

test("highlights common languages without changing source text", () => {
  const fixtures = [
    ["javascript", "const answer = greet(42); // safe", ["keyword", "function", "number", "comment"]],
    ["python", "def solve(value):\n    return value + 1", ["keyword", "function", "number"]],
    ["sql", "SELECT name FROM students WHERE score >= 80", ["keyword", "number"]],
    ["html", "<button title=\"safe\">Learn</button>", ["tag"]],
    ["json", "{\"ready\": true, \"progress\": 100}", ["string", "number"]],
  ];
  fixtures.forEach(([language, source, expected]) => {
    const parts = syntax.highlightParts(source, language);
    assert.equal(parts.map((part) => part.value).join(""), source);
    expected.forEach((type) => assert.ok(parts.some((part) => part.type === type), `${language} ${type}`));
  });
});

test("unknown languages remain exact literal text", () => {
  const source = `<img src=x onerror="globalThis.pwned=true"> & \\u003cscript>`;
  assert.deepEqual(syntax.highlightParts(source, "unknown-language"), [{ type: "plain", value: source }]);
});

test("token output is data, never generated markup", () => {
  const source = `const html = "<script>alert('no')</script>";`;
  const parts = syntax.highlightParts(source, "js");
  assert.equal(parts.map((part) => part.value).join(""), source);
  assert.ok(parts.every((part) => Object.keys(part).sort().join(",") === "type,value"));
  assert.equal(globalThis.pwned, undefined);
});
