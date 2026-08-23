/* Safe inline resource-citation decoration after Markdown sanitization. */
"use strict";

((global) => {
  const REFERENCE = /\[R([1-9]\d*)\]/gi;
  const MODEL_REFERENCE = /\[\s*R([1-9]\d*)\s*\]|\(\s*R([1-9]\d*)\s*\)/giu;
  const SELF_CHECK = /\s*(?:\*{0,2}[\[(]?\s*)?(?:citation check|self[- ]check)\s*\*{0,2}\s*:(?=[^.!?。！？؟۔।॥։።፧｡]*(?:\[\s*R[1-9]\d*\s*\]|\(\s*R[1-9]\d*\s*\)|\bR[1-9]\d*\b|based\s+on\s+R[1-9]\d*|citation\s+check)).*$/isu;
  const TERMINAL_AUDIT = /\s*(?:\*{0,2}[\[(]?\s*)?(?:citation check|self[- ]check)\s*\*{0,2}\s*:\s*(?:all\s+(?:sources|citations|claims|references)\s+(?:(?:are|were)\s+)?(?:cited|present|covered|included|supported|used)|(?:the\s+)?(?:citation\s+check\s+)?(?:is\s+)?(?:complete|passed|done|ok(?:ay)?)|yes)\s*[.!?。！？؟۔।॥։።፧｡]*\s*[\])]*\*{0,2}\s*$/iu;
  const PROTECTED_MARKDOWN = [
    /^ {0,3}(?:`{3,}|~{3,})[^\n]*\n.*?^ {0,3}(?:`{3,}|~{3,})[ \t]*$/gmsu,
    /^ {0,3}(?:`{3,}|~{3,})[^\n]*(?:\n.*)?$/gmsu,
    /^(?:(?: {4}|\t).*?(?:\n|$))+/gmu,
    /\[(?:[^\[\]\n]|\[[^\[\]\n]*\])*\]\[[^\]\n]+\]/gu,
    /^[ \t]{0,3}(?:(?:>[ \t]{0,3}|[-+*][ \t]+|\d+[.)][ \t]+))*\[[^\]\n]+\]:[^\n]*$/gmu,
    /\[(?:[^\[\]\n]|\[[^\[\]\n]*\])*\]\([^\n)]*\)/gu,
    /\\(?:\[\s*R[1-9]\d*\s*\]|\(\s*R[1-9]\d*\s*\))/giu,
    /\\begin\{(equation\*?|alignat\*?|align\*?|gather\*?|CD)\}.*?\\end\{\1\}/gsu,
    /\\begin\{(?:equation\*?|alignat\*?|align\*?|gather\*?|CD)\}.*$/gsu,
    /\$\$.*?\$\$|\$[^\n$]+\$|\\\(.*?\\\)|\\\[.*?\\\]/gsu,
    /\$\$.*$|\\\[.*$|\\\(.*$/gsu,
    /<(a|button|code|kbd|pre|samp|script|style|textarea)\b[^>]*>.*?<\/\1\s*>/gisu,
    /<(?:a|button|code|kbd|pre|samp|script|style|textarea)\b[^>]*>.*$/gisu,
    /<([a-z][\w:-]*)\b[^>]*class\s*=\s*(["'])[^"']*\b(?:katex(?:-display)?|math-source)\b[^"']*\2[^>]*>.*?<\/\1\s*>/gisu,
    /<[a-z][\w:-]*\b[^>]*class\s*=\s*(["'])[^"']*\b(?:katex(?:-display)?|math-source)\b[^"']*\1[^>]*>.*$/gisu,
    /<[^>\n]+>/gu,
  ];
  const MARKDOWN_LINE_PREFIX = /^[ \t]{0,3}(?:(?:#{1,6}|[-+*>]|\d+[.)])\s+)+/gmu;
  const REFERENCE_DEFINITION = /^[ \t]{0,3}(?:(?:>[ \t]{0,3}|[-+*][ \t]+|\d+[.)][ \t]+))*\[([^\]\n]+)\]:[^\n]*$/gimu;
  const TERMINAL_PUNCTUATION = '.!?。！？؟۔।॥։።፧｡"\'”’)]';
  const TERMINAL_CLASS = TERMINAL_PUNCTUATION.replace(/[\\\]^-]/gu, "\\$&");
  const TERMINAL_END = new RegExp(`[${TERMINAL_CLASS}]+$`, "u");
  const BARE_TERMINAL_REFERENCE = new RegExp(
    `\\s+\\bR([1-9]\\d*)\\b(?=\\s*[${TERMINAL_CLASS}]*\\s*$)`,
    "iu",
  );
  const BASED_ON_SUFFIX = new RegExp(
    `\\s*,?\\s*based\\s+on\\s+R([1-9]\\d*)\\b(?=\\s*[${TERMINAL_CLASS}]*\\s*$)`,
    "iu",
  );
  const BASED_ON_PREFIX = /^(\s*)based\s+on\s+R([1-9]\d*)\s*,?\s*/iu;
  const LEGACY_NUMERIC_REFERENCE = /\[\s*([1-9]\d*)\s*\]/gu;
  const EXCLUDED = [
    "a", "button", "code", "pre", "kbd", "samp", "textarea",
    ".katex", ".katex-display", ".math-source", ".resource-sources",
  ].join(", ");
  const CLAIM_BLOCK = "p, li, blockquote, dd, td";
  const WORD = /[\p{L}\p{N}][\p{L}\p{N}\p{M}'’\-]*/gu;
  const NO_SPACE_SCRIPT = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Thai}\p{Script=Lao}\p{Script=Khmer}\p{Script=Myanmar}]/u;
  const SENTENCE_END = /(?:[。！？؟۔।॥։።፧｡]+(?:["'”’)\]]*)?|[.!?]+(?:["'”’)\]]*)?(?=\s|$))/gu;
  const sentenceSegmenter = global.Intl?.Segmenter
    ? new global.Intl.Segmenter(undefined, { granularity: "sentence" })
    : null;
  const STOP_WORDS = new Set([
    "about", "after", "again", "also", "and", "are", "because", "been", "before",
    "being", "between", "both", "but", "can", "could", "does", "each", "for", "from",
    "had", "has", "have", "how", "into", "its", "may", "more", "most", "not", "only",
    "other", "our", "out", "over", "same", "should", "some", "such", "than", "that",
    "the", "their", "then", "there", "these", "they", "this", "those", "through", "under",
    "use", "used", "using", "very", "was", "were", "what", "when", "where", "which",
    "while", "who", "will", "with", "would", "you", "your",
  ]);
  const CLAIM_MODIFIERS = new Set([
    "all", "any", "both", "each", "every", "few", "many", "most", "neither",
    "never", "no", "none", "nor", "not", "only", "several", "some", "without",
  ]);
  const POLARITY = new Set(["neither", "never", "no", "none", "nor", "not", "without"]);

  /** Split model text into ordinary text and only the server-backed references it may open. */
  function segmentReferences(text, available) {
    const limit = Math.max(0, Number(available) || 0);
    const parts = [];
    let cursor = 0;
    REFERENCE.lastIndex = 0;
    for (let match = REFERENCE.exec(text); match; match = REFERENCE.exec(text)) {
      const number = Number(match[1]);
      if (match.index > cursor) parts.push({ type: "text", value: text.slice(cursor, match.index) });
      if (number <= limit) parts.push({ type: "citation", number });
      else parts.push({ type: "text", value: match[0] });
      cursor = match.index + match[0].length;
    }
    if (cursor < text.length) parts.push({ type: "text", value: text.slice(cursor) });
    return parts;
  }

  function protectInlineCode(text, protect) {
    const pieces = [];
    let cursor = 0;
    let scan = 0;
    while (scan < text.length) {
      if (text[scan] !== "`") {
        scan += 1;
        continue;
      }
      let openerEnd = scan + 1;
      while (openerEnd < text.length && text[openerEnd] === "`") openerEnd += 1;
      const openerSize = openerEnd - scan;
      let closer = openerEnd;
      let matchedEnd = -1;
      while (closer < text.length) {
        closer = text.indexOf("`", closer);
        if (closer < 0) break;
        let closerEnd = closer + 1;
        while (closerEnd < text.length && text[closerEnd] === "`") closerEnd += 1;
        if (closerEnd - closer === openerSize) {
          matchedEnd = closerEnd;
          break;
        }
        closer = closerEnd;
      }
      if (matchedEnd < 0) {
        scan = openerEnd;
        continue;
      }
      pieces.push(text.slice(cursor, scan), protect(text.slice(scan, matchedEnd)));
      cursor = matchedEnd;
      scan = matchedEnd;
    }
    pieces.push(text.slice(cursor));
    return pieces.join("");
  }

  function protectReferenceLinks(text, protect) {
    const labels = new Set();
    REFERENCE_DEFINITION.lastIndex = 0;
    for (let match = REFERENCE_DEFINITION.exec(text); match;
      match = REFERENCE_DEFINITION.exec(text)) {
      labels.add(match[1].trim());
    }
    REFERENCE_DEFINITION.lastIndex = 0;
    text = text.replace(REFERENCE_DEFINITION, (literal) => protect(literal));
    const nestedLabel = String.raw`(?:[^\[\]\n]|\[[^\[\]\n]*\])*`;
    for (const label of labels) {
      const flexible = label.split(/\s+/u).filter(Boolean)
        .map((part) => part.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"))
        .join(String.raw`\s+`);
      if (!flexible) continue;
      for (const pattern of [
        new RegExp(String.raw`\[${nestedLabel}\]\[\s*${flexible}\s*\]`, "giu"),
        new RegExp(String.raw`\[\s*${flexible}\s*\]\[\]`, "giu"),
        new RegExp(String.raw`\[\s*${flexible}\s*\]`, "giu"),
      ]) {
        text = text.replace(pattern, (literal) => protect(literal));
      }
    }
    return text;
  }

  /** Canonicalize model-authored labels against the server-owned source array.
   * Only records cited by the completed answer survive, in first-appearance order. */
  function normalizeReferences(text, records, { legacyNumeric = false } = {}) {
    const available = Array.isArray(records) ? records : [];
    const oldToNew = new Map();
    const cited = [];
    let source = String(text || "");
    const protectedLiterals = [];
    let prefix = "\uFFF0MUTA_REFERENCE_LITERAL_";
    while (source.includes(prefix)) prefix += "X";
    const protect = (literal) => {
      const token = `${prefix}${protectedLiterals.length}\uFFF1`;
      protectedLiterals.push([token, literal]);
      return token;
    };
    for (const pattern of PROTECTED_MARKDOWN.slice(0, 3)) {
      source = source.replace(pattern, (literal) => protect(literal));
    }
    source = protectInlineCode(source, protect);
    source = protectReferenceLinks(source, protect);
    for (const pattern of PROTECTED_MARKDOWN.slice(3)) {
      source = source.replace(pattern, (literal) => protect(literal));
    }
    source = source.replace(TERMINAL_AUDIT, " ").replace(SELF_CHECK, " ");
    if (legacyNumeric) source = canonicalizeSupportedLegacyReferences(source, available);
    source = canonicalizeSupportedBareReferences(source, available);
    source = addExactMissingReferences(source, available);
    let normalized = source.replace(
      MODEL_REFERENCE,
      (whole, square, round) => {
        const oldNumber = Number(square || round);
        if (oldNumber < 1 || oldNumber > available.length) {
          return "";
        }
        if (!oldToNew.has(oldNumber)) {
          oldToNew.set(oldNumber, cited.length + 1);
          cited.push(available[oldNumber - 1]);
        }
        return `[R${oldToNew.get(oldNumber)}]`;
      },
    ).replace(/[ \t]{2,}/gu, " ")
      .replace(/\s+([,.;:!?\])])/gu, "$1")
      .replace(/\n{3,}/gu, "\n\n")
      .trim();
    for (const [token, literal] of [...protectedLiterals].reverse()) {
      normalized = normalized.replaceAll(token, () => literal);
    }
    return { text: normalized, records: cited };
  }

  function exactEvidence(value) {
    return normalizeEvidence(
      String(value || "")
        .replace(MODEL_REFERENCE, "")
        .replace(MARKDOWN_LINE_PREFIX, "")
        .replace(/[*_`~]/gu, ""),
    ).toLowerCase().replace(TERMINAL_END, "").trim();
  }

  function enoughEvidenceUnits(value) {
    const words = String(value || "").normalize("NFKC").toLowerCase().match(WORD) || [];
    const meaningful = new Set(words.filter((word) => (
      CLAIM_MODIFIERS.has(word) || (word.length > 2 && !STOP_WORDS.has(word))
    )));
    if (meaningful.size >= 3) return true;
    return words.some((word) => [...word].length >= 5 && /[^\x00-\x7F]/u.test(word));
  }

  function canonicalizeSupportedBareReferences(text, records) {
    const replacements = [];
    for (const [start, end] of sentenceRanges(text)) {
      const sentence = text.slice(start, end);
      const phrase = BASED_ON_PREFIX.exec(sentence) || BASED_ON_SUFFIX.exec(sentence);
      if (phrase) {
        const number = Number(phrase[2] || phrase[1]);
        let cleaned = sentence.slice(0, phrase.index)
          + sentence.slice(phrase.index + phrase[0].length);
        cleaned = normalizeEvidence(cleaned).replace(/^\s+/u, "");
        const claim = exactEvidence(cleaned);
        if (number >= 1 && number <= records.length
          && sourceSupportsClaim(records[number - 1], claim)) {
          cleaned = appendReferenceToSentence(cleaned, number);
        }
        replacements.push([start, end, cleaned]);
        continue;
      }
      const match = BARE_TERMINAL_REFERENCE.exec(sentence);
      if (!match) continue;
      const number = Number(match[1]);
      if (number < 1 || number > records.length) continue;
      const claim = exactEvidence(sentence.slice(0, match.index)
        + sentence.slice(match.index + match[0].length));
      if (sourceSupportsClaim(records[number - 1], claim)) {
        replacements.push([start + match.index, start + match.index + match[0].length, ` [R${number}]`]);
      }
    }
    for (const [start, end, replacement] of replacements.reverse()) {
      text = text.slice(0, start) + replacement + text.slice(end);
    }
    return text;
  }

  function sourceSupportsClaim(record, claim) {
    if (!enoughEvidenceUnits(claim)) return false;
    const excerpt = String(record?.excerpt || "");
    return sentenceRanges(excerpt).some(([start, end]) => (
      exactEvidence(excerpt.slice(start, end)) === claim
    ));
  }

  function appendReferenceToSentence(sentence, number) {
    let offset = sentence.length;
    while (offset && TERMINAL_PUNCTUATION.includes(sentence[offset - 1])) offset -= 1;
    return `${sentence.slice(0, offset).trimEnd()} [R${number}]${sentence.slice(offset)}`;
  }

  function canonicalizeSupportedLegacyReferences(text, records) {
    const replacements = [];
    for (const [start, end] of sentenceRanges(text)) {
      const sentence = text.slice(start, end);
      const claim = exactEvidence(sentence.replace(LEGACY_NUMERIC_REFERENCE, ""));
      if (!enoughEvidenceUnits(claim)) continue;
      LEGACY_NUMERIC_REFERENCE.lastIndex = 0;
      for (let match = LEGACY_NUMERIC_REFERENCE.exec(sentence); match;
        match = LEGACY_NUMERIC_REFERENCE.exec(sentence)) {
        const number = Number(match[1]);
        if (number < 1 || number > records.length) continue;
        const excerpt = String(records[number - 1]?.excerpt || "");
        const evidence = new Set(sentenceRanges(excerpt)
          .map(([evidenceStart, evidenceEnd]) => (
            exactEvidence(excerpt.slice(evidenceStart, evidenceEnd))
          )));
        if (evidence.has(claim)) {
          replacements.push([start + match.index, start + match.index + match[0].length, `[R${number}]`]);
        }
      }
    }
    for (const [start, end, replacement] of replacements.reverse()) {
      text = text.slice(0, start) + replacement + text.slice(end);
    }
    return text;
  }

  function addExactMissingReferences(text, records) {
    const present = new Set();
    MODEL_REFERENCE.lastIndex = 0;
    for (let match = MODEL_REFERENCE.exec(text); match; match = MODEL_REFERENCE.exec(text)) {
      present.add(Number(match[1] || match[2]));
    }
    const claims = sentenceRanges(text).map(([start, end]) => {
      let citationOffset = end;
      while (citationOffset > start
        && TERMINAL_PUNCTUATION.includes(text[citationOffset - 1])) {
        citationOffset -= 1;
      }
      return { citationOffset, normalized: exactEvidence(text.slice(start, end)) };
    });
    const insertions = new Map();
    records.forEach((record, index) => {
      const oldNumber = index + 1;
      if (present.has(oldNumber)) return;
      const excerpt = String(record?.excerpt || "");
      const evidence = new Set(sentenceRanges(excerpt)
        .map(([start, end]) => exactEvidence(excerpt.slice(start, end)))
        .filter((sentence) => enoughEvidenceUnits(sentence)));
      const claim = claims.find(({ normalized }) => evidence.has(normalized));
      if (!claim) return;
      if (!insertions.has(claim.citationOffset)) insertions.set(claim.citationOffset, []);
      insertions.get(claim.citationOffset).push(oldNumber);
    });
    for (const [end, numbers] of [...insertions.entries()].sort((a, b) => b[0] - a[0])) {
      const markers = numbers.map((number) => ` [R${number}]`).join("");
      text = text.slice(0, end) + markers + text.slice(end);
    }
    return text;
  }

  function terms(value) {
    const words = String(value || "").normalize("NFKC").toLowerCase().match(WORD) || [];
    const units = new Map();
    for (const word of words) {
      const requiredModifier = CLAIM_MODIFIERS.has(word);
      if (!requiredModifier && (word.length <= 2 || STOP_WORDS.has(word))) continue;
      if (!NO_SPACE_SCRIPT.test(word)) {
        units.set(word, Math.max(2, 1 + Math.min(3, Math.floor(word.length / 5))));
        continue;
      }
      const characters = [...word];
      if (characters.length < 3) units.set(word, 2);
      for (let index = 0; index + 2 < characters.length; index += 1) {
        units.set(characters.slice(index, index + 3).join(""), 1);
      }
    }
    return units;
  }

  function profile(value, allowed) {
    const words = String(value || "").normalize("NFKC").toLowerCase().match(WORD) || [];
    return [...new Set(words.filter((word) => allowed.has(word)))].sort().join("|");
  }

  function numberProfile(value) {
    return [...new Set(String(value || "").normalize("NFKC").match(/\p{N}+/gu) || [])]
      .sort().join("|");
  }

  function normalizeEvidence(value) {
    return String(value || "").normalize("NFKC")
      .replace(/\s+/gu, " ")
      .replace(/\s+([,.;:!?。！？؟۔।॥։።፧｡\p{Pe}\p{Pf}])/gu, "$1")
      .trim();
  }

  function overlapScore(claim, record) {
    const claimTerms = terms(claim);
    const claimWords = String(claim || "").normalize("NFKC").match(WORD) || [];
    const tokenCount = Math.max(claimTerms.size, claimWords.length);
    if (!claimTerms.size || tokenCount < 3) return { exact: false, tokenCount: 0 };
    const excerpt = String(record?.excerpt || "");
    for (const [start, end] of sentenceRanges(excerpt)) {
      const evidence = excerpt.slice(start, end);
      if (normalizeEvidence(claim) !== normalizeEvidence(evidence)) continue;
      return {
        exact: true,
        sameModifiers: profile(claim, CLAIM_MODIFIERS) === profile(evidence, CLAIM_MODIFIERS),
        sameNumbers: numberProfile(claim) === numberProfile(evidence),
        samePolarity: profile(claim, POLARITY) === profile(evidence, POLARITY),
        tokenCount,
      };
    }
    return { exact: false, tokenCount };
  }

  /** Assign every server-owned record missing an explicit [R#] to a rendered claim.
   * A missing number is linked only when the adjacent claim overlaps its server-owned excerpt;
   * unused or irrelevant retrieval hits remain honestly available in the Sources panel. */
  function planClaimCitations(claims, records, explicit = []) {
    if (!claims.length || !records.length) return [];
    const used = new Set(explicit.map(({ claimIndex, number }) => `${claimIndex}:${number}`));
    const assignments = [];
    claims.forEach((claim, claimIndex) => {
      records.forEach((record, index) => {
        const number = index + 1;
        if (used.has(`${claimIndex}:${number}`)) return;
        const evidence = overlapScore(claim, record);
        if (evidence.exact && evidence.tokenCount >= 3
          && evidence.sameModifiers && evidence.sameNumbers && evidence.samePolarity) {
          assignments.push({ claimIndex, number });
        }
      });
    });
    return assignments.sort((a, b) => a.claimIndex - b.claimIndex || a.number - b.number);
  }

  function preview(record, number, copy) {
    const tooltip = global.document.createElement("span");
    tooltip.className = "resource-citation-preview";
    tooltip.setAttribute("role", "tooltip");
    tooltip.setAttribute("aria-hidden", "true");

    const eyebrow = global.document.createElement("span");
    eyebrow.className = "resource-citation-preview-label";
    eyebrow.textContent = copy.previewLabel(number);
    const title = global.document.createElement("strong");
    title.dir = "auto";
    title.textContent = record.title;
    const meta = global.document.createElement("span");
    meta.textContent = copy.meta(record.page);
    tooltip.append(eyebrow, title, meta);
    if (record.excerpt) {
      const excerpt = global.document.createElement("span");
      excerpt.className = "resource-citation-preview-excerpt";
      excerpt.dir = "auto";
      excerpt.textContent = record.excerpt;
      tooltip.appendChild(excerpt);
    }
    return tooltip;
  }

  function marker(record, number, { hrefFor, labelFor, copy, onActive }) {
    const link = global.document.createElement("a");
    link.className = "resource-citation-marker";
    link.href = hrefFor(record);
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.dataset.resourceCitation = String(number);
    link.setAttribute("aria-label", labelFor(record, number));
    const label = global.document.createElement("span");
    label.className = "resource-citation-marker-number";
    label.setAttribute("aria-hidden", "true");
    label.textContent = String(number);
    link.append(label, preview(record, number, copy));
    link.addEventListener("mouseenter", () => onActive(number, true));
    link.addEventListener("mouseleave", () => onActive(number, false));
    link.addEventListener("focus", () => onActive(number, true));
    link.addEventListener("blur", () => onActive(number, false));
    return link;
  }

  function textEntries(block, rootFallback = false) {
    const entries = [];
    let cursor = 0;
    const walker = global.document.createTreeWalker(block, global.NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (node.parentElement?.closest(EXCLUDED)) continue;
      const owner = node.parentElement?.closest(CLAIM_BLOCK);
      if (rootFallback ? owner : owner !== block) continue;
      entries.push({ node, start: cursor, end: cursor + node.data.length });
      cursor += node.data.length;
    }
    return entries;
  }

  function fallbackSentenceRanges(text) {
    const ranges = [];
    let start = 0;
    SENTENCE_END.lastIndex = 0;
    for (let match = SENTENCE_END.exec(text); match; match = SENTENCE_END.exec(text)) {
      ranges.push([start, match.index + match[0].length]);
      start = match.index + match[0].length;
    }
    if (start < text.length) ranges.push([start, text.length]);
    return ranges;
  }

  function sentenceRanges(text) {
    if (sentenceSegmenter) {
      return [...sentenceSegmenter.segment(text)].map(({ index, segment }) => (
        [index, index + segment.length]
      ));
    }
    return fallbackSentenceRanges(text);
  }

  function collectClaimAnchors(root, includeUnmatched = false) {
    const blocks = [...root.querySelectorAll(CLAIM_BLOCK)];
    const rootFallback = !blocks.length;
    if (rootFallback) blocks.push(root);
    const claims = [];
    let order = 0;
    for (const block of blocks) {
      const entries = textEntries(block, rootFallback);
      if (!entries.length) continue;
      const text = entries.map(({ node }) => node.data).join("");
      for (const [rawStart, rawEnd] of sentenceRanges(text)) {
        let start = rawStart;
        let end = rawEnd;
        while (start < end && /\s/u.test(text[start])) start += 1;
        while (end > start && /\s/u.test(text[end - 1])) end -= 1;
        const claim = text.slice(start, end);
        if (!includeUnmatched && !terms(claim).size) continue;
        const entry = [...entries].reverse().find(({ start: entryStart }) => entryStart < end);
        if (!entry) continue;
        claims.push({
          text: claim,
          node: entry.node,
          offset: Math.min(entry.node.data.length, end - entry.start),
          order: order++,
        });
      }
    }
    return claims;
  }

  function explicitClaimCitations(root, available) {
    const assignments = [];
    let previousMeaningful = -1;
    for (const claim of collectClaimAnchors(root, true)) {
      const parts = segmentReferences(claim.text, available);
      const numbers = parts.filter(({ type }) => type === "citation").map(({ number }) => number);
      const plain = parts.filter(({ type }) => type === "text").map(({ value }) => value).join("");
      const meaningful = terms(plain).size > 0;
      const startsWithReference = /^\s*\[R[1-9]\d*\]/iu.test(claim.text);
      const prior = previousMeaningful;
      if (meaningful) previousMeaningful += 1;
      const claimIndex = startsWithReference && prior >= 0 ? prior : previousMeaningful;
      if (claimIndex < 0) continue;
      for (const number of numbers) assignments.push({ claimIndex, number });
    }
    return assignments;
  }

  function addFallbackMarkers(root, records, explicitAssignments, options, markers) {
    const claims = collectClaimAnchors(root);
    const assignments = planClaimCitations(
      claims.map(({ text }) => text),
      records,
      explicitAssignments,
    );
    const grouped = new Map();
    for (const assignment of assignments) {
      if (!grouped.has(assignment.claimIndex)) grouped.set(assignment.claimIndex, []);
      grouped.get(assignment.claimIndex).push(assignment.number);
    }
    // A text node can hold more than one sentence. Split from the end so earlier offsets remain
    // valid as each exact claim receives its marker links.
    const insertions = [...grouped.entries()].map(([claimIndex, numbers]) => ({
      claim: claims[claimIndex],
      numbers,
    })).sort((a, b) => b.claim.order - a.claim.order);
    for (const { claim, numbers } of insertions) {
      if (!claim.node.parentNode) continue;
      const tail = claim.node.splitText(claim.offset);
      const fragment = global.document.createDocumentFragment();
      for (const number of numbers) {
        const link = marker(records[number - 1], number, options);
        fragment.appendChild(link);
        markers.push(link);
      }
      claim.node.parentNode.insertBefore(fragment, tail);
    }
  }

  /** Replace [R1] prose text with exact-page links after marked + DOMPurify have completed. */
  function decorate(root, records, { hrefFor, labelFor, copy, onActive }) {
    if (!root || !global.document || !global.NodeFilter) return [];
    const explicitAssignments = explicitClaimCitations(root, records.length);
    const nodes = [];
    const walker = global.document.createTreeWalker(root, global.NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (!node.data.includes("[") || node.parentElement?.closest(EXCLUDED)) continue;
      const parts = segmentReferences(node.data, records.length);
      if (parts.some((part) => part.type === "citation")) nodes.push([node, parts]);
    }

    const markers = [];
    const options = { hrefFor, labelFor, copy, onActive };
    for (const [node, parts] of nodes) {
      const fragment = global.document.createDocumentFragment();
      for (const part of parts) {
        if (part.type === "text") {
          fragment.appendChild(global.document.createTextNode(part.value));
          continue;
        }
        const record = records[part.number - 1];
        const link = marker(record, part.number, options);
        fragment.appendChild(link);
        markers.push(link);
      }
      node.replaceWith(fragment);
    }
    addFallbackMarkers(root, records, explicitAssignments, options, markers);
    return [...root.querySelectorAll(".resource-citation-marker")];
  }

  const api = {
    decorate,
    fallbackSentenceRanges,
    normalizeReferences,
    planClaimCitations,
    segmentReferences,
    sentenceRanges,
  };
  global.MutaCitations = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : window);
