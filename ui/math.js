/* Markdown + TeX rendering shared by streamed and restored assistant replies. */
"use strict";

((global) => {
  const PLACEHOLDER_CLOSE = "\uE001";

  // Longest/specific openers first. AMS environments are included because small local models
  // frequently emit them directly instead of wrapping them in \[...\].
  const SPAN_DELIMITERS = [
    ["\\begin{equation*}", "\\end{equation*}", true, false],
    ["\\begin{equation}", "\\end{equation}", true, false],
    ["\\begin{alignat*}", "\\end{alignat*}", true, false],
    ["\\begin{alignat}", "\\end{alignat}", true, false],
    ["\\begin{align*}", "\\end{align*}", true, false],
    ["\\begin{align}", "\\end{align}", true, false],
    ["\\begin{gather*}", "\\end{gather*}", true, false],
    ["\\begin{gather}", "\\end{gather}", true, false],
    ["\\begin{CD}", "\\end{CD}", true, false],
    ["$$", "$$", true, false],
    ["\\[", "\\]", true, false],
    ["\\(", "\\)", false, false],
    ["$", "$", false, true],
  ];

  function isEscaped(text, index) {
    let slashes = 0;
    for (let i = index - 1; i >= 0 && text[i] === "\\"; i -= 1) slashes += 1;
    return slashes % 2 === 1;
  }

  function runLength(text, index, character) {
    let end = index;
    while (text[end] === character) end += 1;
    return end - index;
  }

  function lineEnd(text, index) {
    const newline = text.indexOf("\n", index);
    return newline < 0 ? text.length : newline + 1;
  }

  function fencedCodeEnd(text, lineStart) {
    let markerAt = lineStart;
    while (markerAt < lineStart + 3 && text[markerAt] === " ") markerAt += 1;
    const marker = text[markerAt];
    if (marker !== "`" && marker !== "~") return -1;
    const openerLength = runLength(text, markerAt, marker);
    if (openerLength < 3) return -1;
    const openerEnd = lineEnd(text, markerAt + openerLength);
    if (marker === "`" && text.slice(markerAt + openerLength, openerEnd).includes("`")) {
      return -1;
    }

    let candidateLine = openerEnd;
    while (candidateLine < text.length) {
      let candidateAt = candidateLine;
      while (candidateAt < candidateLine + 3 && text[candidateAt] === " ") candidateAt += 1;
      const closeLength = runLength(text, candidateAt, marker);
      const candidateEnd = lineEnd(text, candidateAt + closeLength);
      const trailing = text.slice(candidateAt + closeLength, candidateEnd).trim();
      if (closeLength >= openerLength && trailing === "") return candidateEnd;
      candidateLine = candidateEnd;
    }
    // CommonMark treats an unclosed fence as code through the end of the document.
    return text.length;
  }

  function inlineCodeEnd(text, openerAt) {
    const openerLength = runLength(text, openerAt, "`");
    let cursor = openerAt + openerLength;
    while (cursor < text.length) {
      const found = text.indexOf("`", cursor);
      if (found < 0) return -1;
      const closeLength = runLength(text, found, "`");
      if (closeLength === openerLength) return found + closeLength;
      cursor = found + closeLength;
    }
    return -1;
  }

  function indentationColumns(text, lineStart, end) {
    let columns = 0;
    let cursor = lineStart;
    while (cursor < end) {
      if (text[cursor] === " ") columns += 1;
      else if (text[cursor] === "\t") columns += 4 - (columns % 4);
      else break;
      cursor += 1;
    }
    return columns;
  }

  function indentedCodeEnd(text, blockStart) {
    const firstEnd = lineEnd(text, blockStart);
    const firstLine = text.slice(blockStart, firstEnd).replace(/[\r\n]+$/, "");
    if (!firstLine.trim() || indentationColumns(text, blockStart, firstEnd) < 4) return -1;

    let blockEnd = firstEnd;
    let candidateStart = firstEnd;
    while (candidateStart < text.length) {
      const candidateEnd = lineEnd(text, candidateStart);
      const candidate = text.slice(candidateStart, candidateEnd).replace(/[\r\n]+$/, "");
      if (candidate.trim() && indentationColumns(text, candidateStart, candidateEnd) < 4) break;
      blockEnd = candidateEnd;
      candidateStart = candidateEnd;
    }
    return blockEnd;
  }

  function htmlCodeEnd(text, openerAt) {
    if (text.startsWith("<!--", openerAt)) {
      const closeAt = text.indexOf("-->", openerAt + 4);
      return closeAt < 0 ? text.length : closeAt + 3;
    }
    const opener = text
      .slice(openerAt)
      .match(/^<(pre|code|script|style|textarea|noscript|option|title)\b[^>]*>/i);
    if (!opener) return -1;
    const closePattern = new RegExp(`</${opener[1]}\\s*>`, "ig");
    closePattern.lastIndex = openerAt + opener[0].length;
    const close = closePattern.exec(text);
    return close ? close.index + close[0].length : text.length;
  }

  function codeRanges(text) {
    const ranges = [];
    let cursor = 0;
    while (cursor < text.length) {
      if (cursor === 0 || text[cursor - 1] === "\n") {
        const fenceEnd = fencedCodeEnd(text, cursor);
        if (fenceEnd >= 0) {
          ranges.push([cursor, fenceEnd, true]);
          cursor = fenceEnd;
          continue;
        }
        const indentedEnd = indentedCodeEnd(text, cursor);
        if (indentedEnd >= 0) {
          // Absolute indentation is only a soft boundary: after a list marker CommonMark may
          // treat this as normal list content. Complete math may extract inside it, but an
          // unmatched opener must not search beyond the end of the indented region.
          ranges.push([cursor, indentedEnd, false]);
          cursor = indentedEnd;
          continue;
        }
      }
      if (text[cursor] === "`") {
        const codeEnd = inlineCodeEnd(text, cursor);
        if (codeEnd >= 0) {
          ranges.push([cursor, codeEnd, true]);
          cursor = codeEnd;
          continue;
        }
      }
      if (text[cursor] === "<") {
        const codeEnd = htmlCodeEnd(text, cursor);
        if (codeEnd >= 0) {
          ranges.push([cursor, codeEnd, true]);
          cursor = codeEnd;
          continue;
        }
      }
      cursor += 1;
    }
    return ranges;
  }

  function findClose(text, from, close, singleDollar, sourceRanges) {
    let cursor = from;
    let braceDepth = 0;
    const originRange = sourceRanges.findIndex(
      ([start, end]) => start <= from && from < end
    );
    const searchEnd =
      originRange >= 0 && !sourceRanges[originRange][2]
        ? sourceRanges[originRange][1]
        : text.length;
    const firstRange = sourceRanges.findIndex(([, end]) => end > from);
    let rangeIndex = firstRange < 0 ? sourceRanges.length : firstRange;
    while (cursor < searchEnd) {
      while (
        rangeIndex < sourceRanges.length &&
        sourceRanges[rangeIndex][1] <= cursor
      ) {
        rangeIndex += 1;
      }
      if (rangeIndex < sourceRanges.length) {
        const [rangeStart, rangeEnd, blockMath] = sourceRanges[rangeIndex];
        if (cursor >= rangeStart && cursor < rangeEnd && blockMath) {
          return -1;
        }
      }
      if (singleDollar && text[cursor] === "\n") return -1;
      if (braceDepth === 0 && text.startsWith(close, cursor) && !isEscaped(text, cursor)) {
        if (!singleDollar) return cursor;
        const before = text[cursor - 1] || "";
        const after = text[cursor + 1] || "";
        // Pandoc-style dollar rules avoid turning “$20 and $30” into accidental math while
        // retaining normal $x$, $20$, and $x + 1$ notation.
        if (!/\s/.test(before) && !/\d/.test(after)) return cursor;
        // This is another dollar opener, not a plausible closer. Do not skip across it and
        // swallow the prose up to some much later equation.
        return -1;
      }
      if (!isEscaped(text, cursor)) {
        if (text[cursor] === "{") braceDepth += 1;
        if (text[cursor] === "}" && braceDepth > 0) braceDepth -= 1;
      }
      cursor += 1;
    }
    return -1;
  }

  function placeholderOpenFor(text) {
    let token = "\uE000MUTA_MATH_";
    while (text.includes(token)) token = `\uE000${token}`;
    return token;
  }

  function openerAt(text, index) {
    for (const delimiter of SPAN_DELIMITERS) {
      const [open, , , singleDollar] = delimiter;
      if (!text.startsWith(open, index) || isEscaped(text, index)) continue;
      if (singleDollar) {
        if (text[index + 1] === "$" || /\s/.test(text[index + 1] || "")) continue;
      }
      return delimiter;
    }
    return null;
  }

  /** Replace complete TeX spans with inert text before CommonMark can consume backslashes. */
  function extractMath(source) {
    const text = String(source ?? "");
    const expressions = [];
    const placeholderOpen = placeholderOpenFor(text);
    const sourceRanges = codeRanges(text);
    let rangeIndex = 0;
    let protectedSource = "";
    let cursor = 0;

    while (cursor < text.length) {
      while (rangeIndex < sourceRanges.length && sourceRanges[rangeIndex][1] <= cursor) {
        rangeIndex += 1;
      }
      if (
        rangeIndex < sourceRanges.length &&
        cursor === sourceRanges[rangeIndex][0] &&
        sourceRanges[rangeIndex][2]
      ) {
        const [, rangeEnd] = sourceRanges[rangeIndex];
        protectedSource += text.slice(cursor, rangeEnd);
        cursor = rangeEnd;
        rangeIndex += 1;
        continue;
      }
      const delimiter = openerAt(text, cursor);
      if (!delimiter) {
        protectedSource += text[cursor];
        cursor += 1;
        continue;
      }
      const [open, close, , singleDollar] = delimiter;
      const contentStart = cursor + open.length;
      const closeAt = findClose(text, contentStart, close, singleDollar, sourceRanges);
      if (closeAt < 0 || closeAt === contentStart) {
        // Streaming commonly reaches an opener before its closer. Leave it readable for this
        // frame; the next full render will extract it as soon as the closing delimiter lands.
        protectedSource += text[cursor];
        cursor += 1;
        continue;
      }
      const expression = text.slice(cursor, closeAt + close.length);
      const index = expressions.push(expression) - 1;
      protectedSource += `${placeholderOpen}${index}${PLACEHOLDER_CLOSE}`;
      cursor = closeAt + close.length;
    }
    return { protectedSource, expressions, placeholderOpen };
  }

  function restoreMath(root, expressions, placeholderOpen) {
    if (!expressions.length || typeof document === "undefined") return [];
    const escapedOpen = placeholderOpen.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const placeholderRe = new RegExp(`${escapedOpen}(\\d+)${PLACEHOLDER_CLOSE}`, "g");
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    const slots = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      if (!node.data.includes(placeholderOpen)) continue;
      const fragment = document.createDocumentFragment();
      let copiedThrough = 0;
      for (const match of node.data.matchAll(placeholderRe)) {
        fragment.append(node.data.slice(copiedThrough, match.index));
        const expression = expressions[Number(match[1])];
        if (expression != null) {
          const slot = document.createElement("span");
          slot.className = "math-source";
          slot.textContent = expression;
          fragment.append(slot);
          slots.push({ slot, expression });
        }
        copiedThrough = match.index + match[0].length;
      }
      fragment.append(node.data.slice(copiedThrough));
      node.replaceWith(fragment);
    }
    return slots;
  }

  function katexInput(expression) {
    for (const [open, close, displayMode] of SPAN_DELIMITERS) {
      if (!expression.startsWith(open) || !expression.endsWith(close)) continue;
      const environment = open.startsWith("\\begin{");
      return {
        tex: environment ? expression : expression.slice(open.length, -close.length),
        displayMode,
      };
    }
    return null;
  }

  function plainTextFallback(root, source) {
    root.textContent = String(source ?? "");
    return { mathCount: 0, fallback: true };
  }

  function render(root, source) {
    const markdown = String(source ?? "");
    if (!global.marked?.parse || !global.DOMPurify?.sanitize) {
      return plainTextFallback(root, markdown);
    }

    const { protectedSource, expressions, placeholderOpen } = extractMath(markdown);
    try {
      root.innerHTML = global.DOMPurify.sanitize(global.marked.parse(protectedSource));
    } catch {
      return plainTextFallback(root, markdown);
    }
    let slots;
    try {
      slots = restoreMath(root, expressions, placeholderOpen);
    } catch {
      return plainTextFallback(root, markdown);
    }

    if (!expressions.length || typeof global.katex?.render !== "function") {
      return { mathCount: 0, fallback: expressions.length > 0 };
    }
    let mathCount = 0;
    for (const { slot, expression } of slots) {
      // Markdown code is deliberately literal, even if its contents look like TeX.
      if (slot.closest("pre, code, script, style, textarea, noscript, option, title")) continue;
      const input = katexInput(expression);
      if (!input) continue;
      slot.classList.add(input.displayMode ? "display-math" : "inline-math");
      try {
        global.katex.render(input.tex, slot, {
          displayMode: input.displayMode,
          throwOnError: false,
          strict: "ignore",
          trust: false,
        });
        mathCount += 1;
      } catch {
        // Keep this one expression as readable TeX and continue rendering the rest.
      }
    }
    return { mathCount, fallback: mathCount < expressions.length };
  }

  global.MutaMath = Object.freeze({ extractMath, render });
})(globalThis);
