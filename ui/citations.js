/* Safe inline resource-citation decoration after Markdown sanitization. */
"use strict";

((global) => {
  const REFERENCE = /\[R([1-9]\d*)\]/gi;
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
    planClaimCitations,
    segmentReferences,
    sentenceRanges,
  };
  global.MutaCitations = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : window);
