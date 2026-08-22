"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { segmentReferences } = require("../citations.js");

test("links only reference numbers backed by server-owned citation records", () => {
  assert.deepEqual(segmentReferences("Claim [R1], unknown [R4], then [R2].", 2), [
    { type: "text", value: "Claim " },
    { type: "citation", number: 1 },
    { type: "text", value: ", unknown " },
    { type: "text", value: "[R4]" },
    { type: "text", value: ", then " },
    { type: "citation", number: 2 },
    { type: "text", value: "." },
  ]);
});

test("supports repeated and lower-case model references without changing prose", () => {
  assert.deepEqual(segmentReferences("A [r1] and again [R1]", 1), [
    { type: "text", value: "A " },
    { type: "citation", number: 1 },
    { type: "text", value: " and again " },
    { type: "citation", number: 1 },
  ]);
});

test("leaves ordinary bracketed text and zero-padded pseudo references untouched", () => {
  assert.deepEqual(segmentReferences("Array [1], [R01], and [R0].", 5), [
    { type: "text", value: "Array [1], [R01], and [R0]." },
  ]);
});

test("does not make any model reference clickable when no citations were returned", () => {
  assert.deepEqual(segmentReferences("Unsupported [R1].", 0), [
    { type: "text", value: "Unsupported " },
    { type: "text", value: "[R1]" },
    { type: "text", value: "." },
  ]);
});
