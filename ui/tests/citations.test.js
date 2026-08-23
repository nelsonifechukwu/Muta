"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  fallbackSentenceRanges,
  planClaimCitations,
  segmentReferences,
  sentenceRanges,
} = require("../citations.js");

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

test("places omitted server-owned citations beside the best matching claim", () => {
  const claims = [
    "A microcontroller contains a processor and memory.",
    "A robot uses input and output pins.",
  ];
  const records = [
    { excerpt: "A microcontroller contains a processor and memory. It is an integrated circuit." },
    { excerpt: "A robot uses input and output pins. These pins can control motors." },
  ];
  assert.deepEqual(planClaimCitations(claims, records), [
    { claimIndex: 0, number: 1 },
    { claimIndex: 1, number: 2 },
  ]);
});

test("keeps explicit markers authoritative and leaves unsupported sources in the source panel", () => {
  const claims = ["First supported claim.", "Second supported claim.", "Third supported claim."];
  const records = [{ excerpt: "" }, { excerpt: "" }, { excerpt: "" }];
  assert.deepEqual(planClaimCitations(claims, records, [{ claimIndex: 1, number: 2 }]), []);
});

test("does not promote a retrieval hit from one shared generic term", () => {
  const cases = [
    ["Energy drinks can contain caffeine.", "Solar energy is converted into electricity."],
    ["A student studies chemistry.", "A student studies medieval poetry."],
    ["Le système utilise une batterie.", "Le manuel utilise une table des matières."],
  ];
  for (const [claim, excerpt] of cases) {
    assert.deepEqual(planClaimCitations([claim], [{ excerpt }]), []);
  }
});

test("fails closed on negation and opposite predicates", () => {
  const cases = [
    ["Caffeine is safe for children.", "Caffeine is not safe for children."],
    ["Battery voltage increases during discharge.", "Battery voltage decreases during discharge."],
    ["Insulin raises blood glucose.", "Insulin lowers blood glucose."],
  ];
  for (const [claim, excerpt] of cases) {
    assert.deepEqual(planClaimCitations([claim], [{ excerpt }]), []);
  }
});

test("fails closed on contractions and multilingual negation", () => {
  const cases = [
    ["Caffeine is safe for children.", "Caffeine isn’t safe for children."],
    ["The battery can charge safely.", "The battery cannot charge safely."],
    ["Koffein ist sicher für Kinder.", "Koffein ist nicht sicher für Kinder."],
    ["الكافيين آمن للأطفال.", "الكافيين ليس آمن للأطفال."],
    ["कैफीन बच्चों के लिए सुरक्षित है।", "कैफीन बच्चों के लिए सुरक्षित नहीं है।"],
  ];
  for (const [claim, excerpt] of cases) {
    assert.deepEqual(planClaimCitations([claim], [{ excerpt }]), []);
  }
});

test("fails closed on quantifier and numeric disagreement", () => {
  const cases = [
    ["All students passed the assessment.", "Some students passed the assessment."],
    ["Some cells contain chloroplasts.", "All cells contain chloroplasts."],
    ["The battery lasts 10 hours.", "The battery lasts 20 hours."],
  ];
  for (const [claim, excerpt] of cases) {
    assert.deepEqual(planClaimCitations([claim], [{ excerpt }]), []);
  }
});

test("fails closed on scientific units, signs, and comparison operators", () => {
  const cases = [
    ["Force is 10 N.", "Force is 10 J."],
    ["Temperature is 20 C.", "Temperature is 20 F."],
    ["Wavelength is 500 nm.", "Wavelength is 500 cm."],
    ["The object travels at 10 m per second.", "The object travels at 10 s per second."],
    ["Acceleration is +10 m per second squared.", "Acceleration is −10 m per second squared."],
    ["The measured value is > 10.", "The measured value is < 10."],
  ];
  for (const [claim, excerpt] of cases) {
    assert.deepEqual(planClaimCitations([claim], [{ excerpt }]), []);
  }
});

test("fails closed when grouping or semantic punctuation changes meaning", () => {
  const cases = [
    ["The expression is (a + b) × c.", "The expression is a + b × c."],
    ["The fraction is a / (b + c).", "The fraction is a / b + c."],
    ["Let’s eat, children.", "Let’s eat children."],
  ];
  for (const [claim, excerpt] of cases) {
    assert.deepEqual(planClaimCitations([claim], [{ excerpt }]), []);
  }
});

test("can place the same supporting source beside multiple matching claims", () => {
  const claims = [
    "A microcontroller contains a processor.",
    "A microcontroller contains memory.",
  ];
  const records = [{
    excerpt: "A microcontroller contains a processor. A microcontroller contains memory.",
  }];
  assert.deepEqual(planClaimCitations(claims, records), [
    { claimIndex: 0, number: 1 },
    { claimIndex: 1, number: 1 },
  ]);
});

test("an explicit marker suppresses only the same claim-source pair", () => {
  const claims = [
    "A microcontroller contains a processor.",
    "A microcontroller contains memory.",
  ];
  const records = [{
    excerpt: "A microcontroller contains a processor. A microcontroller contains memory.",
  }];
  assert.deepEqual(
    planClaimCitations(claims, records, [{ claimIndex: 0, number: 1 }]),
    [{ claimIndex: 1, number: 1 }],
  );
});

test("an explicit inline marker does not block another source for the same claim", () => {
  const claim = "A microcontroller contains a processor .";
  const records = [
    { excerpt: "A microcontroller contains a processor." },
    { excerpt: "A microcontroller contains a processor." },
  ];
  assert.deepEqual(
    planClaimCitations([claim], records, [{ claimIndex: 0, number: 1 }]),
    [{ claimIndex: 0, number: 2 }],
  );
});

test("matches unsegmented CJK evidence without inventing an unrelated citation", () => {
  const claims = ["微控制器包含处理器和存储器。", "学习电子系统。"];
  const records = [
    { excerpt: "微控制器包含处理器和存储器。它控制电子设备。" },
    { excerpt: "完全不相关的天气预报。" },
  ];
  assert.deepEqual(planClaimCitations(claims, records), [
    { claimIndex: 0, number: 1 },
  ]);
});

test("segments claim endings used across Muta interface languages", () => {
  const text = "Arabic؟ Urdu۔ Hindi। Sanskrit॥ Armenian։ Ethiopic። Next፧ CJK。";
  assert.deepEqual(
    sentenceRanges(text).map(([start, end]) => text.slice(start, end).trim()),
    ["Arabic؟", "Urdu۔", "Hindi।", "Sanskrit॥", "Armenian։", "Ethiopic።", "Next፧", "CJK。"],
  );
});

test("fallback segmentation splits strong punctuation without spaces", () => {
  const text = "第一句。第二句。最初です。次です。第一句！第二句？";
  assert.deepEqual(
    fallbackSentenceRanges(text).map(([start, end]) => text.slice(start, end).trim()),
    ["第一句。", "第二句。", "最初です。", "次です。", "第一句！", "第二句？"],
  );
});
