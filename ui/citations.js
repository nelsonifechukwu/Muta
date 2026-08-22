/* Safe inline resource-citation decoration after Markdown sanitization. */
"use strict";

((global) => {
  const REFERENCE = /\[R([1-9]\d*)\]/gi;
  const EXCLUDED = [
    "a", "button", "code", "pre", "kbd", "samp", "textarea",
    ".katex", ".katex-display", ".math-source", ".resource-sources",
  ].join(", ");

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

  /** Replace [R1] prose text with exact-page links after marked + DOMPurify have completed. */
  function decorate(root, records, { hrefFor, labelFor, copy, onActive }) {
    if (!root || !global.document || !global.NodeFilter) return [];
    const nodes = [];
    const walker = global.document.createTreeWalker(root, global.NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (!node.data.includes("[") || node.parentElement?.closest(EXCLUDED)) continue;
      const parts = segmentReferences(node.data, records.length);
      if (parts.some((part) => part.type === "citation")) nodes.push([node, parts]);
    }

    const markers = [];
    for (const [node, parts] of nodes) {
      const fragment = global.document.createDocumentFragment();
      for (const part of parts) {
        if (part.type === "text") {
          fragment.appendChild(global.document.createTextNode(part.value));
          continue;
        }
        const record = records[part.number - 1];
        const link = global.document.createElement("a");
        link.className = "resource-citation-marker";
        link.href = hrefFor(record);
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.dataset.resourceCitation = String(part.number);
        link.setAttribute("aria-label", labelFor(record, part.number));
        const number = global.document.createElement("span");
        number.className = "resource-citation-marker-number";
        number.setAttribute("aria-hidden", "true");
        number.textContent = String(part.number);
        link.append(number, preview(record, part.number, copy));
        link.addEventListener("mouseenter", () => onActive(part.number, true));
        link.addEventListener("mouseleave", () => onActive(part.number, false));
        link.addEventListener("focus", () => onActive(part.number, true));
        link.addEventListener("blur", () => onActive(part.number, false));
        fragment.appendChild(link);
        markers.push(link);
      }
      node.replaceWith(fragment);
    }
    return markers;
  }

  const api = { decorate, segmentReferences };
  global.MutaCitations = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : window);
