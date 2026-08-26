/* Offline fenced-code highlighting. The tokenizer is intentionally small and fail-safe: it
 * highlights familiar lexical shapes without ever parsing, evaluating, or trusting model code. */
(function (root) {
  "use strict";

  const ALIASES = Object.freeze({
    js: "javascript", jsx: "javascript", javascript: "javascript", mjs: "javascript",
    ts: "typescript", tsx: "typescript", typescript: "typescript",
    py: "python", python: "python",
    sh: "shell", shell: "shell", bash: "shell", zsh: "shell", console: "shell",
    json: "json",
    html: "markup", htm: "markup", xml: "markup", svg: "markup", markup: "markup",
    css: "css", scss: "css",
    sql: "sql",
    c: "c", h: "c", cpp: "cpp", "c++": "cpp", cc: "cpp", cxx: "cpp", hpp: "cpp",
    java: "java",
    rs: "rust", rust: "rust",
    yaml: "yaml", yml: "yaml",
  });

  const KEYWORDS = Object.freeze({
    javascript: "as async await break case catch class const continue debugger default delete do else export extends finally for from function get if import in instanceof let new of return set static super switch this throw try typeof var void while with yield true false null undefined",
    typescript: "abstract any as asserts async await bigint boolean break case catch class const constructor continue declare default delete do else enum export extends false finally for from function get if implements import in infer instanceof interface is keyof let module namespace never new null number object of override private protected public readonly require return set static string super switch symbol this throw true try type typeof undefined unique unknown var void while with yield",
    python: "and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return True try while with yield",
    shell: "case do done elif else esac export fi for function if in local readonly return set shift then time trap unset until while",
    sql: "add all alter and any as asc backup between by case check column constraint create database default delete desc distinct drop exec exists foreign from full group having in index inner insert into is join key left like limit not null on or order outer primary procedure right rownum select set table top truncate union unique update values view where",
    c: "auto break case char const continue default do double else enum extern float for goto if inline int long register restrict return short signed sizeof static struct switch typedef union unsigned void volatile while _Bool",
    cpp: "alignas alignof and and_eq asm auto bitand bitor bool break case catch char char16_t char32_t class compl concept const consteval constexpr constinit const_cast continue co_await co_return co_yield decltype default delete do double dynamic_cast else enum explicit export extern false float for friend goto if inline int long mutable namespace new noexcept not not_eq nullptr operator or or_eq private protected public register reinterpret_cast requires return short signed sizeof static static_assert static_cast struct switch template this thread_local throw true try typedef typeid typename union unsigned using virtual void volatile wchar_t while xor xor_eq",
    java: "abstract assert boolean break byte case catch char class const continue default do double else enum extends final finally float for goto if implements import instanceof int interface long native new package private protected public return short static strictfp super switch synchronized this throw throws transient try void volatile while true false null",
    rust: "as async await break const continue crate dyn else enum extern false fn for if impl in let loop match mod move mut pub ref return self Self static struct super trait true type unsafe use where while",
  });

  const keywordSets = new Map(Object.entries(KEYWORDS).map(([language, value]) => [
    language,
    new Set(value.toLowerCase().split(" ")),
  ]));
  const TOKEN = /(?:\/\/[^\n]*|\/\*[\s\S]*?\*\/|#[^\n]*|--[^\n]*|<!--[\s\S]*?-->|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|\b(?:0x[\da-f]+|\d+(?:\.\d+)?)\b|\b[A-Za-z_$][\w$]*(?=\s*\()|\b[A-Za-z_$][\w$]*\b|<\/?[A-Za-z][^>]*>|[{}()[\].,;:+*/%!=<>?&|^-]+)/gi;

  function canonicalLanguage(raw) {
    const key = String(raw || "").trim().toLowerCase().replace(/^language-/, "");
    return ALIASES[key] || "";
  }

  function classForToken(token, language) {
    if (/^(?:\/\/|\/\*|#|--|<!--)/.test(token)) return "comment";
    if (/^["'`]/.test(token)) return "string";
    if (/^(?:0x[\da-f]+|\d+(?:\.\d+)?)$/i.test(token)) return "number";
    if (/^<\/?[A-Za-z]/.test(token)) return "tag";
    if (keywordSets.get(language)?.has(token.toLowerCase())) return "keyword";
    if (/^[A-Za-z_$][\w$]*$/.test(token)) return "function";
    if (/^[{}()[\].,;:+*/%!=<>?&|^-]+$/.test(token)) return "operator";
    return "plain";
  }

  function highlightParts(source, declaredLanguage) {
    const text = String(source ?? "");
    const language = canonicalLanguage(declaredLanguage);
    if (!language || language === "json" || language === "markup" || language === "css" || language === "yaml") {
      // These languages still use the generic lexical pass; aliases without a keyword set are valid.
      if (!language) return [{ type: "plain", value: text }];
    }
    const parts = [];
    let cursor = 0;
    TOKEN.lastIndex = 0;
    let match;
    while ((match = TOKEN.exec(text))) {
      if (match.index > cursor) parts.push({ type: "plain", value: text.slice(cursor, match.index) });
      parts.push({ type: classForToken(match[0], language), value: match[0] });
      cursor = TOKEN.lastIndex;
    }
    if (cursor < text.length) parts.push({ type: "plain", value: text.slice(cursor) });
    return parts.length ? parts : [{ type: "plain", value: text }];
  }

  function declaredLanguage(code) {
    for (const name of code.classList || []) {
      if (name.startsWith("language-")) return name.slice(9);
    }
    return "";
  }

  async function copyText(text) {
    if (root.navigator?.clipboard?.writeText) {
      await root.navigator.clipboard.writeText(text);
      return;
    }
    const area = root.document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.className = "syntax-copy-fallback";
    root.document.body.appendChild(area);
    area.select();
    const copied = root.document.execCommand?.("copy");
    area.remove();
    if (!copied) throw new Error("copy unavailable");
  }

  function decorate(container, labels = {}) {
    if (!container?.querySelectorAll || !root.document) return;
    container.querySelectorAll("pre > code").forEach((code) => {
      if (code.closest(".code-block")) return;
      const pre = code.parentElement;
      const source = code.textContent || "";
      const rawLanguage = declaredLanguage(code);
      const language = canonicalLanguage(rawLanguage);
      const wrapper = root.document.createElement("div");
      wrapper.className = "code-block";
      const toolbar = root.document.createElement("div");
      toolbar.className = "code-toolbar";
      const languageLabel = root.document.createElement("span");
      languageLabel.className = "code-language";
      const localized = (key) => root.MutaI18n?.t?.(key) || key;
      languageLabel.textContent = language || labels.plainLabel || localized("code.text");
      const copy = root.document.createElement("button");
      copy.type = "button";
      copy.className = "code-copy";
      copy.dataset.i18n = "code.copy";
      copy.textContent = labels.copyLabel || localized("code.copy");
      copy.addEventListener("click", async () => {
        try {
          await copyText(source);
          copy.textContent = labels.copiedLabel || localized("code.copied");
        } catch (_) {
          copy.textContent = labels.failedLabel || localized("code.copyFailed");
        }
        root.setTimeout(() => { copy.textContent = labels.copyLabel || localized("code.copy"); }, 1600);
      });
      toolbar.append(languageLabel, copy);
      code.replaceChildren();
      highlightParts(source, rawLanguage).forEach((part) => {
        if (part.type === "plain") {
          code.appendChild(root.document.createTextNode(part.value));
        } else {
          const span = root.document.createElement("span");
          span.className = `syntax-${part.type}`;
          span.textContent = part.value;
          code.appendChild(span);
        }
      });
      pre.before(wrapper);
      wrapper.append(toolbar, pre);
    });
  }

  const api = { canonicalLanguage, highlightParts, decorate };
  root.MutaSyntax = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
