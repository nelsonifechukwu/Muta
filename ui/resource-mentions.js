/* Canonical learner-resource mention parsing and request composition. */
"use strict";

((global) => {
  const MENTION = /@\{([^{}\n]+)\}(?![\p{L}\p{N}\p{M}_]|\.[\p{L}\p{N}])/gu;
  const BIDI_CONTROLS = /[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]/g;
  const C0_CONTROLS = /[\x00-\x1f\x7f]/g;
  const NON_TEXT_C0_CONTROLS = /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g;
  const RESOURCE_ID = /^[0-9a-f]{32}$/;
  const FALLBACK_NAME = "resource.pdf";
  // Invisible, one-code-unit anchors preserve where a picker selection belongs without exposing
  // transport syntax in the textarea. C0 separators are internal-only, non-printing, removed
  // from uploaded names, and cannot alter shaping in Persian, Mongolian, or joined emoji.
  const PLACEMENT_MARKERS = Array.from({ length: 8 }, (_, index) =>
    String.fromCharCode(0x18 + index)
  );

  function cleanName(value) {
    return String(value || "")
      .replace(BIDI_CONTROLS, "")
      .replace(C0_CONTROLS, " ")
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

  function isPlacementMarker(marker) {
    return PLACEMENT_MARKERS.includes(marker);
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

  function place(text, at, caret, resources = []) {
    const source = String(text || "");
    const start = Math.max(0, Math.min(source.length, Number(at) || 0));
    const end = Math.max(start, Math.min(source.length, Number(caret) || start));
    const claimed = new Set((Array.isArray(resources) ? resources : [])
      .map((resource) => resource?.marker)
      .filter(isPlacementMarker));
    const marker = PLACEMENT_MARKERS.find((candidate) =>
      !claimed.has(candidate) && !source.includes(candidate)
    ) || "";
    if (!marker) return null;
    return {
      text: source.slice(0, start) + marker + source.slice(end),
      caret: start + marker.length,
      marker,
    };
  }

  function removeMarker(text, marker) {
    const source = String(text || "");
    return isPlacementMarker(marker) ? source.split(marker).join("") : source;
  }

  function sanitizeDraft(text, resources, limit = 8) {
    const candidates = (Array.isArray(resources) ? resources : []).filter((resource) =>
      resource &&
      typeof resource.id === "string" &&
      RESOURCE_ID.test(resource.id) &&
      typeof resource.name === "string"
    );
    const markerCounts = new Map();
    for (const resource of candidates) {
      if (!isPlacementMarker(resource.marker)) continue;
      markerCounts.set(resource.marker, (markerCounts.get(resource.marker) || 0) + 1);
    }
    const cleanResources = [];
    const ids = new Set();
    for (const resource of candidates) {
      if (ids.has(resource.id)) continue;
      ids.add(resource.id);
      const marker = isPlacementMarker(resource.marker) && markerCounts.get(resource.marker) === 1
        ? resource.marker
        : undefined;
      cleanResources.push({ id: resource.id, name: nameFor(resource), marker });
      if (cleanResources.length >= Math.max(0, Number(limit) || 0)) break;
    }
    const ownedMarkers = new Set(cleanResources.map((resource) => resource.marker).filter(Boolean));
    const cleanText = String(text || "").replace(NON_TEXT_C0_CONTROLS, (control) =>
      ownedMarkers.has(control) ? control : ""
    );
    return { text: cleanText, resources: cleanResources };
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

  function segmentConversationTitle(text, legacyLimit = 80) {
    const source = String(text || "");
    const parts = segment(source);

    // Before conversation titles became mention-aware, the gateway sliced the first turn at
    // exactly 80 characters. A long document reference therefore arrived as `@{filename...`
    // with no closing brace. Restrict this recovery to that historical boundary so ordinary
    // short malformed prose remains ordinary text while transport syntax never leaks in the list.
    if (Array.from(source).length !== Math.max(0, Number(legacyLimit) || 0)) return parts;
    const opener = source.lastIndexOf("@{");
    if (opener < 0 || source.indexOf("}", opener + 2) >= 0) return parts;
    const recovered = opener ? segment(source.slice(0, opener)) : [];
    const tail = source.slice(opener + 2);
    if (!tail.trim() || /[{}\r\n]/.test(tail)) {
      const plainTail = cleanName(tail);
      if (plainTail) recovered.push({ type: "text", value: plainTail });
      return recovered;
    }
    const name = cleanName(tail) || FALLBACK_NAME;
    recovered.push({ type: "resource", name, legacy: true });
    return recovered;
  }

  function append(text, resources) {
    let result = String(text || "").trim();
    const present = new Set(segment(result)
      .filter((part) => part.type === "resource")
      .map((part) => part.name));
    for (const resource of Array.isArray(resources) ? resources : []) {
      const name = nameFor(resource);
      const token = tokenFor(resource);
      const marker = isPlacementMarker(resource?.marker) ? resource.marker : "";
      if (marker && result.includes(marker)) {
        result = result.split(marker).join(token);
        present.add(name);
        continue;
      }
      if (!name || !token || present.has(name)) continue;
      result += `${result ? " " : ""}${token}`;
      present.add(name);
    }
    return result;
  }

  function resolveResources(text, selected, catalog, limit = 8) {
    const resolved = [];
    const ids = new Set();
    for (const resource of Array.isArray(selected) ? selected : []) {
      if (!resource || typeof resource.id !== "string" || ids.has(resource.id)) continue;
      ids.add(resource.id);
      resolved.push(resource);
      if (resolved.length >= Math.max(0, Number(limit) || 0)) return resolved;
    }
    const names = segment(text)
      .filter((part) => part.type === "resource")
      .map((part) => part.name);
    for (const name of names) {
      const matches = (Array.isArray(catalog) ? catalog : []).filter((resource) =>
        resource?.status === "ready" && nameFor(resource) === name
      );
      if (matches.length !== 1 || ids.has(matches[0].id)) continue;
      ids.add(matches[0].id);
      resolved.push({ id: matches[0].id, name });
      if (resolved.length >= Math.max(0, Number(limit) || 0)) break;
    }
    return resolved;
  }

  const api = {
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
    segmentConversationTitle,
    tokenFor,
  };
  global.MutaResourceMentions = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : window);
