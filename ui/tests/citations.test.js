"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  fallbackSentenceRanges,
  normalizeReferences,
  planClaimCitations,
  segmentReferences,
  sentenceRanges,
} = require("../citations.js");

test("canonicalizes sparse model labels and keeps only cited server records", () => {
  const records = Array.from({ length: 5 }, (_value, index) => ({ page: index + 1 }));
  assert.deepEqual(
    normalizeReferences("First (R5). Second uses [R3]. Repeat [R5].", records),
    {
      text: "First [R1]. Second uses [R2]. Repeat [R1].",
      records: [{ page: 5 }, { page: 3 }],
    },
  );
});

test("removes printed citation audits and never authorizes unknown labels or resistor ids", () => {
  assert.deepEqual(
    normalizeReferences(
      "Answer [R2]. Unknown (R8). Connect resistor R1 to resistor R2. "
        + "*(Self-check: based on R2? Yes.)*",
      [{ page: 1 }, { page: 2 }],
    ),
    {
      text: "Answer [R1]. Unknown. Connect resistor R1 to resistor R2.",
      records: [{ page: 2 }],
    },
  );
});

test("recovers an omitted marker only for an exact supporting sentence", () => {
  assert.deepEqual(
    normalizeReferences(
      "Applicants should demonstrate leadership experience.",
      [
        { page: 1, excerpt: "Applicants should demonstrate leadership experience." },
        { page: 2, excerpt: "An unrelated discussion of engineering jobs." },
      ],
    ),
    {
      text: "Applicants should demonstrate leadership experience [R1].",
      records: [{ page: 1, excerpt: "Applicants should demonstrate leadership experience." }],
    },
  );
});

test("does not give generic exact fragments citation authority", () => {
  for (const text of ["It is possible.", "The cat is red."]) {
    assert.deepEqual(normalizeReferences(text, [{ page: 1, excerpt: text }]), {
      text,
      records: [],
    });
  }
});

test("matches exact evidence inside structural markdown blocks", () => {
  const record = {
    page: 1,
    excerpt: "Applicants should demonstrate leadership experience.",
  };
  for (const prefix of ["- ", "+ ", "> ", "## "]) {
    const result = normalizeReferences(
      `${prefix}Applicants should demonstrate leadership experience.`,
      [record],
    );
    assert.match(result.text, /\[R1\]/u);
    assert.deepEqual(result.records, [record]);
  }
});

test("matches exact evidence written with combining-script characters", () => {
  const text = "कैफीन बच्चों के लिए सुरक्षित है।";
  const record = { page: 1, excerpt: text };
  assert.deepEqual(normalizeReferences(text, [record]), {
    text: "कैफीन बच्चों के लिए सुरक्षित है [R1]।",
    records: [record],
  });
});

test("canonicalizes a supported terminal bare reference but leaves technical ids ordinary", () => {
  const record = {
    page: 1,
    excerpt: "Applicants should demonstrate leadership experience.",
  };
  assert.deepEqual(
    normalizeReferences("Applicants should demonstrate leadership experience R1.", [record]),
    {
      text: "Applicants should demonstrate leadership experience [R1].",
      records: [record],
    },
  );
  assert.deepEqual(normalizeReferences("Connect resistor R1 to resistor R2.", [record]), {
    text: "Connect resistor R1 to resistor R2.",
    records: [],
  });
  assert.deepEqual(
    normalizeReferences("Applicants should demonstrate leadership experience R1", [record]),
    {
      text: "Applicants should demonstrate leadership experience [R1]",
      records: [record],
    },
  );
});

test("turns supported based-on phrases into markers and removes unknown citation phrases", () => {
  const record = {
    page: 1,
    excerpt: "Applicants should demonstrate leadership experience.",
  };
  for (const text of [
    "Applicants should demonstrate leadership experience, based on R1.",
    "Based on R1, Applicants should demonstrate leadership experience.",
  ]) {
    assert.deepEqual(normalizeReferences(text, [record]), {
      text: "Applicants should demonstrate leadership experience [R1].",
      records: [record],
    });
  }
  assert.deepEqual(
    normalizeReferences(
      "Applicants should demonstrate leadership experience, based on R9.",
      [record],
    ),
    {
      text: "Applicants should demonstrate leadership experience [R1].",
      records: [record],
    },
  );
});

test("a later markdown link does not protect an earlier citation", () => {
  assert.deepEqual(
    normalizeReferences(
      "Supported claim [R1]. Read [more](https://example.test).",
      [{ page: 1 }],
    ),
    {
      text: "Supported claim [R1]. Read [more](https://example.test).",
      records: [{ page: 1 }],
    },
  );
});

test("removes multiline and nested citation self-check variants", () => {
  const variants = [
    "Answer. Self-check: [R1] is present and supported.",
    "Answer. **Self-check:** [R1] is present.",
    "Answer. (Self-check: claim 1 (R1) is covered.)",
    "Answer.\nCitation check:\n- R1 is present.",
    "Answer. [Self-check: [R1] is present.]",
  ];
  for (const variant of variants) {
    assert.deepEqual(normalizeReferences(variant, [{ page: 1 }]), {
      text: "Answer.",
      records: [],
    });
  }
});

test("removes terminal citation audit conclusions without reference labels", () => {
  for (const text of [
    "Answer. Citation check: all sources are cited.",
    "Answer. Self-check: all citations are present.",
    "Answer. Citation check: complete.",
  ]) {
    assert.deepEqual(normalizeReferences(text, []), { text: "Answer.", records: [] });
  }
});

test("references in code links html and math remain literal and authorize nothing", () => {
  const variants = [
    "Use `[R1]` as a literal.",
    "```text\n[R1]\n```",
    "Read [[R1]](https://example.test).",
    "The expression is $[R1]$.",
    "<code>[R1]</code>",
    "See [document][R1].\n\n[R1]: https://example.test",
    '<span title="[R1]">Claim</span>',
    "    [R1]\n",
    "\\begin{equation}[R1]\\end{equation}",
    "\\begin{align*}x &= [R1]\\end{align*}",
    "```text\n[R1]",
    "<code>[R1]",
    "<a href='https://evil.test'>[R1]",
    "$$\n[R1]",
    "Write \\[R1] to show the syntax.",
    "Write \\(R1) to show the syntax.",
    "[Use `[R1]`](https://example.test)",
    "<code>$[R1]$</code>",
    '<a href="https://example.test">`[R1]`</a>',
    "`example\n[R1]\ncontinued`",
    "``x[R1]`y``",
    "`x```[R1]y`",
    "[[R1] label][id]\n\n[id]: https://evil.test",
    "[label [R1]][id]\n\n[id]: https://evil.test",
    "Claim [R1].\n\n[R1]: https://evil.test",
    "Claim [R1][].\n\n[R1]: https://evil.test",
    "Claim [R1].\n\n> [R1]: https://evil.test",
    "Claim [R1].\n\n>   [R1]: https://evil.test",
    "Claim [R1].\n\n> >   [R1]: https://evil.test",
    "Claim [R1].\n\n- [R1]: https://evil.test",
  ];
  for (const variant of variants) {
    assert.deepEqual(normalizeReferences(variant, [{ page: 1 }]), {
      text: variant,
      records: [],
    });
  }
});

test("a citation before a later nested link remains authoritative", () => {
  const text = "Claim [R1]. Read [[R1]](https://example.test) literally.";
  assert.deepEqual(normalizeReferences(text, [{ page: 1 }]), {
    text,
    records: [{ page: 1 }],
  });
});

test("citation audit words inside literals do not truncate an answer", () => {
  const variants = [
    "Use `Self-check: [R1]` as a literal.",
    "```text\nCitation check: [R1]\n```\nContinue.",
    "<code>Self-check: [R1]</code> then explain.",
  ];
  for (const text of variants) {
    assert.deepEqual(normalizeReferences(text, [{ page: 1 }]), { text, records: [] });
  }
});

test("renderer-excluded subtrees keep reference examples literal", () => {
  const variants = [
    "<kbd>[R1]</kbd>",
    "<samp>[R1]</samp>",
    "<button>[R1]</button>",
    '<span class="katex">[R1]</span>',
    '<span class="math-source">[R1]</span>',
  ];
  for (const text of variants) {
    assert.deepEqual(normalizeReferences(text, [{ page: 1 }]), { text, records: [] });
  }
});

test("upgrades numeric citations only for legacy resource history", () => {
  const text = "Kinetic energy is the energy of a moving object [1].";
  const records = [{ page: 2, excerpt: "Kinetic energy is the energy of a moving object." }];
  assert.deepEqual(normalizeReferences(text, records), { text, records: [] });
  assert.deepEqual(normalizeReferences(text, records, { legacyNumeric: true }), {
    text: "Kinetic energy is the energy of a moving object [R1].",
    records,
  });
  assert.deepEqual(
    normalizeReferences("Array [1] contains the first element.", records, { legacyNumeric: true }),
    { text: "Array [1] contains the first element.", records: [] },
  );
});

test("keeps a legitimate pedagogical self-check in the answer", () => {
  const text = "A useful self-check: compute the dimensions. Then compare the units.";
  assert.deepEqual(normalizeReferences(text, [{ page: 1 }]), {
    text,
    records: [],
  });
});

test("keeps a legitimate self-check before a separately cited claim", () => {
  const text = "A useful self-check: compute the dimensions. The document recommends leadership [R1].";
  assert.deepEqual(
    normalizeReferences(text, [{ page: 1, excerpt: "The document recommends leadership." }]),
    { text, records: [{ page: 1, excerpt: "The document recommends leadership." }] },
  );
});

test("keeps legitimate citation-check teaching instructions", () => {
  const variants = [
    "In academic writing, perform a citation check: verify author and year. Then submit.",
    "A useful self-check: verify each citation against the bibliography. Then submit.",
  ];
  for (const text of variants) {
    assert.deepEqual(normalizeReferences(text, [{ page: 1 }]), { text, records: [] });
  }
});

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
