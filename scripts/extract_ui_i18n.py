#!/usr/bin/env python3
"""Extract Muta's translatable UI surface into a deterministic release inventory.

The inventory is intentionally broader than the current canonical catalog. It records authored
HTML copy, accessibility attributes, runtime translation-key callsites, local feature-copy maps,
and literal JavaScript flowing directly into common UI sinks. During the dependency-gated phase,
literal candidates are explicit translation debt. The release phase must classify/remove them.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "ui"
OUTPUT = UI_ROOT / "i18n-source-inventory.json"

EXCLUDED_SOURCE_PARTS = {"dist", "tests", "vendor"}


def _authored(path: Path) -> bool:
    return not any(part in EXCLUDED_SOURCE_PARTS for part in path.relative_to(UI_ROOT).parts)


HTML_FILES = tuple(sorted(path for path in UI_ROOT.rglob("*.html") if _authored(path)))
JS_EXCLUDED = {
    "africa-languages.js",
    "i18n.js",
    "locale-bootstrap.js",
    "locale-fr.js",
    "locale-generated.js",
    "locale-manifest.js",
    "locales.js",
    "worklet.js",
}
JS_FILES = tuple(
    sorted(
        path
        for path in UI_ROOT.rglob("*.js")
        if _authored(path) and path.name not in JS_EXCLUDED
    )
)

TRANSLATABLE_ATTRIBUTES = ("aria-label", "title", "placeholder", "data-placeholder", "alt")
SKIP_TEXT_TAGS = {"script", "style", "svg", "path"}
HTML_TAG_NAMES = {
    "a",
    "article",
    "aside",
    "button",
    "canvas",
    "code",
    "div",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "header",
    "iframe",
    "img",
    "input",
    "label",
    "li",
    "main",
    "nav",
    "option",
    "p",
    "section",
    "select",
    "small",
    "span",
    "strong",
    "textarea",
}
COPY_MAP_RE = re.compile(
    r"const\s+(?P<name>[A-Z][A-Z0-9_]*_COPY)\s*=\s*Object\.freeze\(\{(?P<body>.*?)\}\);",
    re.DOTALL,
)
COPY_ENTRY_RE = re.compile(
    r"(?P<key>(?:[A-Za-z_$][\w$]*|[\"'][^\"']+[\"']))\s*:\s*"
    r"(?P<quote>[\"'`])(?P<value>(?:\\.|(?!\2).)*?)\2\s*,?",
    re.DOTALL,
)
JS_STRING_RE = re.compile(r"(?P<quote>[\"'`])(?P<value>(?:\\.|(?!\1).)*?)\1", re.DOTALL)
CANONICAL_KEY_RE = re.compile(r"\bt\(\s*([\"'])(?P<key>[^\"']+)\1")
LOCAL_KEY_RE = re.compile(r"\b(?P<helper>featureT|powerText)\(\s*([\"'])(?P<key>[^\"']+)\2")


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def collapse(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def placeholders(value: str) -> list[str]:
    return sorted(re.findall(r"\{[a-zA-Z][\w]*\}", value))


def line_at(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def strip_js_comments(source: str) -> str:
    """Blank comments while preserving strings, byte offsets, and line numbers."""

    result = list(source)
    index = 0
    state = "code"
    quote = ""
    while index < len(source):
        char = source[index]
        nxt = source[index + 1] if index + 1 < len(source) else ""
        if state == "code":
            if char in "\"'`":
                state = "string"
                quote = char
            elif char == "/" and nxt == "/":
                result[index] = result[index + 1] = " "
                state = "line-comment"
                index += 1
            elif char == "/" and nxt == "*":
                result[index] = result[index + 1] = " "
                state = "block-comment"
                index += 1
        elif state == "string":
            if char == "\\":
                index += 1
            elif char == quote:
                state = "code"
        elif state == "line-comment":
            if char == "\n":
                state = "code"
            else:
                result[index] = " "
        elif state == "block-comment":
            if char == "*" and nxt == "/":
                result[index] = result[index + 1] = " "
                state = "code"
                index += 1
            elif char != "\n":
                result[index] = " "
        index += 1
    return "".join(result)


def readable_js_literal(raw: str) -> str:
    value = collapse(raw)
    value = value.replace(r"\n", " ").replace(r"\t", " ")
    return collapse(value)


def looks_user_facing(value: str) -> bool:
    if not value or not re.search(r"[^\W\d_]", value, re.UNICODE):
        return False
    if value in {"use strict", "true", "false", "null", "undefined"}:
        return False
    if value.startswith(("#", ".", "[", "/v1/", "http://", "https://", "data:")):
        return False
    return re.fullmatch(r"[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)+", value) is None


class UIHTMLParser(HTMLParser):
    def __init__(self, path: Path) -> None:
        super().__init__(convert_charrefs=True)
        self.path = path
        self.stack: list[dict[str, Any]] = []
        self.keys: list[dict[str, Any]] = []
        self.literals: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name: value or "" for name, value in attrs}
        parent_translated = bool(self.stack and self.stack[-1]["translated"])
        translated = parent_translated or bool(attr_map.get("data-i18n"))
        line, _ = self.getpos()
        for name, value in attrs:
            if not value or not name.startswith("data-i18n") or name.endswith("-vars"):
                continue
            self.keys.append(
                {"file": relative(self.path), "line": line, "kind": f"html:{name}", "key": value}
            )
        for attribute in TRANSLATABLE_ATTRIBUTES:
            value = attr_map.get(attribute, "")
            if not value:
                continue
            i18n_attribute = f"data-i18n-{attribute}"
            if i18n_attribute in attr_map:
                continue
            self.literals.append(
                {
                    "file": relative(self.path),
                    "line": line,
                    "kind": f"html-attribute:{attribute}",
                    "text": collapse(value),
                }
            )
        self.stack.append({"tag": tag, "translated": translated})

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        text = collapse(data)
        if not text or not looks_user_facing(text):
            return
        if any(frame["tag"] in SKIP_TEXT_TAGS for frame in self.stack):
            return
        if self.stack and self.stack[-1]["translated"]:
            return
        line, _ = self.getpos()
        self.literals.append(
            {"file": relative(self.path), "line": line, "kind": "html-text", "text": text}
        )


def html_inventory(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    parser = UIHTMLParser(path)
    parser.feed(path.read_text())
    return parser.keys, parser.literals


def expression_literals(
    source: str, expression: str, start: int, *, file: Path, kind: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for match in JS_STRING_RE.finditer(expression):
        value = readable_js_literal(match.group("value"))
        if not looks_user_facing(value):
            continue
        rows.append(
            {
                "file": relative(file),
                "line": line_at(source, start + match.start()),
                "kind": kind,
                "text": value,
            }
        )
    return rows


def javascript_inventory(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source = path.read_text()
    code = strip_js_comments(source)
    keys = [
        {
            "file": relative(path),
            "line": line_at(source, match.start()),
            "kind": "js:t",
            "key": match.group("key"),
        }
        for match in CANONICAL_KEY_RE.finditer(code)
    ]
    for match in LOCAL_KEY_RE.finditer(code):
        keys.append(
            {
                "file": relative(path),
                "line": line_at(source, match.start()),
                "kind": f"js:{match.group('helper')}",
                "key": match.group("key"),
            }
        )

    literals: list[dict[str, Any]] = []
    for mapping in COPY_MAP_RE.finditer(code):
        body = mapping.group("body")
        body_start = mapping.start("body")
        for entry in COPY_ENTRY_RE.finditer(body):
            raw_key = entry.group("key")
            key = raw_key[1:-1] if raw_key[:1] in {"\"", "'"} else raw_key
            keys.append(
                {
                    "file": relative(path),
                    "line": line_at(source, body_start + entry.start("key")),
                    "kind": f"js-copy-definition:{mapping.group('name')}",
                    "key": key,
                }
            )
            value = readable_js_literal(entry.group("value"))
            if not looks_user_facing(value):
                continue
            literals.append(
                {
                    "file": relative(path),
                    "line": line_at(source, body_start + entry.start("value")),
                    "kind": f"js-copy-map:{mapping.group('name')}",
                    "text": value,
                }
            )

    patterns = (
        (
            "js-ui-assignment",
            re.compile(
                r"\.(?:textContent|innerText|innerHTML|title|alt|placeholder)\s*=\s*(?P<expr>[^;]+);",
                re.DOTALL,
            ),
        ),
        (
            "js-accessible-attribute",
            re.compile(
                r"\.setAttribute\(\s*[\"'](?:aria-label|title|placeholder|alt|data-placeholder)[\"']\s*,\s*(?P<expr>[^;]+?)\);",
                re.DOTALL,
            ),
        ),
        (
            "js-ui-call",
            re.compile(
                r"\b(?:toast|announce|fail|stopVoice|showShareAuth)\(\s*(?P<expr>[^;]+?)\);",
                re.DOTALL,
            ),
        ),
        (
            "js-ui-return",
            re.compile(r"\breturn\s+(?P<expr>[^;]+);", re.DOTALL),
        ),
        (
            "js-ui-variable",
            re.compile(
                r"\b(?:const|let)\s+(?:action|copy|description|detail|help|label|message|statusText|title)\s*=\s*(?P<expr>[^;]+);",
                re.DOTALL,
            ),
        ),
    )
    for kind, pattern in patterns:
        for match in pattern.finditer(code):
            literals.extend(
                expression_literals(
                    source,
                    match.group("expr"),
                    match.start("expr"),
                    file=path,
                    kind=kind,
                )
            )
    return keys, literals


def runtime_catalog() -> dict[str, Any]:
    script = r"""
globalThis.MutaAfricaLanguages=require('./ui/africa-languages.js');
globalThis.MutaInterfaceLocales=require('./ui/locale-manifest.js');
globalThis.MutaI18n=require('./ui/i18n.js');
globalThis.window=globalThis;
require('./ui/locale-fr.js');
require('./ui/locale-generated.js');
require('./ui/locales.js');
const en=MutaI18n.catalogs.en;
const visible=MutaI18n.supportedDefinitions();
process.stdout.write(JSON.stringify({
  english: en,
  visible: visible.map((locale) => ({ tag: locale.tag, direction: locale.direction })),
  placeholders: Object.fromEntries(Object.entries(en).map(([key, value]) => [
    key,
    [...value.matchAll(/\{[a-zA-Z][\w]*\}/g)].map((match) => match[0]).sort(),
  ])),
}));
"""
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def unique_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: tuple(str(value) for value in item.values())):
        marker = json.dumps(row, ensure_ascii=False, sort_keys=True)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(row)
    return result


def build_inventory() -> dict[str, Any]:
    key_references: list[dict[str, Any]] = []
    literal_candidates: list[dict[str, Any]] = []
    for path in HTML_FILES:
        keys, literals = html_inventory(path)
        key_references.extend(keys)
        literal_candidates.extend(literals)
    for path in JS_FILES:
        keys, literals = javascript_inventory(path)
        key_references.extend(keys)
        literal_candidates.extend(literals)

    catalog = runtime_catalog()
    english = catalog.pop("english")
    known_keys = set(english)
    known_keys.update(row["key"] for row in key_references)
    literal_candidates = [
        row
        for row in literal_candidates
        if row["kind"].startswith("js-copy-map:")
        or (
            row["text"] not in known_keys
            and row["text"] not in HTML_TAG_NAMES
            and not any(
                helper in row["text"]
                for helper in ("${t(", "featureT(", "powerText(")
            )
            and not re.fullmatch(r"[a-z][a-z0-9_-]*", row["text"])
            and not re.fullmatch(r"(?:http|https):", row["text"])
            and not re.fullmatch(r"(?:\$\{[^}]+\}|[\d.])+\s*(?:%|GB|[hms])?", row["text"])
        )
    ]
    for row in literal_candidates:
        row["status"] = "pending-i18n"
    return {
        "schema_version": 1,
        "phase": "awaiting-dependencies",
        "sources": {
            "html": [relative(path) for path in HTML_FILES],
            "javascript": [relative(path) for path in JS_FILES],
        },
        "catalog": {
            "english_key_count": len(english),
            "english_keys": sorted(english),
            "placeholders": catalog["placeholders"],
            "visible_locales": catalog["visible"],
        },
        "key_references": unique_rows(key_references),
        "literal_candidates": unique_rows(literal_candidates),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help=f"write {relative(OUTPUT)}")
    args = parser.parse_args()
    inventory = build_inventory()
    rendered = json.dumps(inventory, ensure_ascii=False, indent=2) + "\n"
    if args.write:
        OUTPUT.write_text(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
