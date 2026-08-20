"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

require("../math.js");

const { extractMath } = globalThis.MutaMath;

test("protects every delimiter form shown in generated tutoring answers", () => {
  const source = [
    "# Mitosis Equation",
    "",
    "\\[ \\text{Number of chromosomes in daughter cells} = \\frac{N}{2} \\]",
    "",
    "If the parent has \\(N = 20\\), each daughter has $N/2$ chromosomes.",
    "",
    "$$\\frac{20}{2} = 10$$",
  ].join("\n");

  const { protectedSource, expressions } = extractMath(source);
  assert.deepEqual(expressions, [
    "\\[ \\text{Number of chromosomes in daughter cells} = \\frac{N}{2} \\]",
    "\\(N = 20\\)",
    "$N/2$",
    "$$\\frac{20}{2} = 10$$",
  ]);
  assert.match(protectedSource, /^# Mitosis Equation/m);
  assert.doesNotMatch(protectedSource, /\\(?:text|frac)/);
});

test("protects common unwrapped AMS equation environments", () => {
  const source = "\\begin{align*}a &= b + c \\\\ d &= e\\end{align*}";
  const result = extractMath(source);
  assert.deepEqual(result.expressions, [source]);
});

test("does not close on a dollar inside TeX braces", () => {
  const source = "$\\text{cost $5} + x$";
  assert.deepEqual(extractMath(source).expressions, [source]);
});

test("leaves an incomplete streamed expression visible until its closer arrives", () => {
  const source = "Working: \\[\\frac{a}{b}";
  const result = extractMath(source);
  assert.equal(result.protectedSource, source);
  assert.deepEqual(result.expressions, []);
});

test("does not mistake ordinary currency or escaped dollars for equations", () => {
  const source = "The books cost $20 and $30; write \\$5 literally, then solve $x + 1$.";
  const { expressions } = extractMath(source);
  assert.deepEqual(expressions, ["$x + 1$"]);
});

test("an unclosed opener does not hide a later complete equation", () => {
  const source = "Stray \\[ prose, then $x + 1$.";
  assert.deepEqual(extractMath(source).expressions, ["$x + 1$"]);
});

test("placeholder-looking model text cannot alias an extracted expression", () => {
  const source = "\uE000MUTA_MATH_0\uE001 and \\(x\\)";
  const result = extractMath(source);
  assert.notEqual(result.placeholderOpen, "\uE000MUTA_MATH_");
  assert.match(result.protectedSource, /^\uE000MUTA_MATH_0\uE001 and /);
  assert.deepEqual(result.expressions, ["\\(x\\)"]);
});

test("never extracts TeX inside fenced code", () => {
  const source = "```tex\n\\[x^2\\]\n```\nOutside: \\[y^2\\]";
  const { protectedSource, expressions } = extractMath(source);
  assert.deepEqual(expressions, ["\\[y^2\\]"]);
  assert.match(protectedSource, /^```tex\n\\\[x\^2\\\]\n```\nOutside: /s);
});

test("an unmatched opener in fenced code cannot consume an outside equation", () => {
  const source = "```tex\n\\[\n```\nOutside:\n\\[x\\]";
  const result = extractMath(source);
  assert.deepEqual(result.expressions, ["\\[x\\]"]);
  assert.match(result.protectedSource, /^```tex\n\\\[\n```\nOutside:\n/s);
});

test("an opener in inline code cannot consume an outside equation", () => {
  const source = "Inline `\\[` then \\[x\\]";
  const result = extractMath(source);
  assert.deepEqual(result.expressions, ["\\[x\\]"]);
  assert.match(result.protectedSource, /^Inline `\\\[` then /);
});

test("raw HTML code regions cannot consume following math", () => {
  const source = "<pre>\\[</pre> then \\(x\\)";
  const result = extractMath(source);
  assert.deepEqual(result.expressions, ["\\(x\\)"]);
  assert.match(result.protectedSource, /^<pre>\\\[<\/pre> then /);
});

test("an opener in indented CommonMark code cannot consume outside math", () => {
  const source = "    \\[\nOutside: \\[x\\]";
  const result = extractMath(source);
  assert.deepEqual(result.expressions, ["\\[x\\]"]);
  assert.match(result.protectedSource, /^    \\\[\nOutside: /);
});

test("a complete equation indented beneath a list item still extracts", () => {
  const source = "- item\n    \\[x\\]";
  assert.deepEqual(extractMath(source).expressions, ["\\[x\\]"]);
});

test("multiline display equations may contain indented bodies", () => {
  const bracketed = "\\[\n    x + y\n\\]";
  const dollars = "$$\n    \\frac{a}{b}\n$$";
  const inList = "- step\n  \\[\n      x + y\n  \\]";
  assert.deepEqual(extractMath(bracketed).expressions, [bracketed]);
  assert.deepEqual(extractMath(dollars).expressions, [dollars]);
  assert.deepEqual(extractMath(inList).expressions, ["\\[\n      x + y\n  \\]"]);
});

test("literal and sanitizable HTML regions cannot consume outside math", () => {
  for (const tag of ["script", "style", "textarea", "noscript", "title"]) {
    const source = `<${tag}>\\[</${tag}> then \\[x\\]`;
    const result = extractMath(source);
    assert.deepEqual(result.expressions, ["\\[x\\]"], tag);
    assert.ok(result.protectedSource.startsWith(`<${tag}>\\[</${tag}> then `), tag);
  }
  const comment = "<!-- \\[ --> then \\(x\\)";
  assert.deepEqual(extractMath(comment).expressions, ["\\(x\\)"]);
});
