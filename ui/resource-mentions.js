/* Canonical learner-resource mention parsing and request composition. */
"use strict";

((global) => {
  const MENTION = /@\{([^{}\n]+)\}(?![\p{L}\p{N}\p{M}_]|\.[\p{L}\p{N}])/gu;
  const BIDI_CONTROLS = /[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]/g;
  const FALLBACK_NAME = "resource.pdf";

  function cleanName(value) {
    return String(value || "")
      .replace(BIDI_CONTROLS, "")
      .replace(/[{}\n]/g, " ")
      .replace(/\s+/g, " ")
      .replace(/\s+([.,;:!?\])])/g, "$1")
      .trim();
  }

  function hasTriggerBoundary(text, at) {
    const source = String(text || "");
    const end = Math.max(0, Math.min(source.length, Number(at) || 0));
    return !/[\p{L}\p{N}\p{M}_.-]$/u.test(source.slice(0, end));
  }

  function tokenFor(resource) {
    if (!resource || typeof resource.name !== "string") return "";
    return `@{${nameFor(resource)}}`;
  }

  function nameFor(resource) {
    return cleanName(resource?.name) || FALLBACK_NAME;
  }

  function removeTrigger(text, at, caret) {
    const source = String(text || "");
    const start = Math.max(0, Math.min(source.length, Number(at) || 0));
    const end = Math.max(start, Math.min(source.length, Number(caret) || start));
    const before = source.slice(0, start).replace(/[^\S\n]+$/g, "");
    const after = source.slice(end).replace(/^[^\S\n]+/g, "");
    const punctuationFollows = /^\p{P}/u.test(after);
    const openingPunctuationPrecedes = /[\p{Ps}\p{Pi}]$/u.test(before);
    const lineBoundary = /\n$/.test(before) || /^\n/.test(after);
    const join = before && after && !punctuationFollows && !openingPunctuationPrecedes &&
      !lineBoundary ? " " : "";
    return { text: before + join + after, caret: before.length + join.length };
  }

  function segment(text) {
    const source = String(text || "");
    const parts = [];
    let cursor = 0;
    MENTION.lastIndex = 0;
    for (let match = MENTION.exec(source); match; match = MENTION.exec(source)) {
      if (match.index > cursor) parts.push({ type: "text", value: source.slice(cursor, match.index) });
      parts.push({ type: "resource", name: cleanName(match[1]) || FALLBACK_NAME });
      cursor = match.index + match[0].length;
    }
    if (cursor < source.length) parts.push({ type: "text", value: source.slice(cursor) });
    return parts;
  }

  function append(text, resources) {
    let result = String(text || "").trim();
    const present = new Set(segment(result)
      .filter((part) => part.type === "resource")
      .map((part) => part.name));
    for (const resource of Array.isArray(resources) ? resources : []) {
      const name = nameFor(resource);
      const token = tokenFor(resource);
      if (!name || !token || present.has(name)) continue;
      result += `${result ? " " : ""}${token}`;
      present.add(name);
    }
    return result;
  }

  const api = { append, hasTriggerBoundary, nameFor, removeTrigger, segment, tokenFor };
  global.MutaResourceMentions = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : window);
