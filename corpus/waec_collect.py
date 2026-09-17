#!/usr/bin/env python3
"""Build a source-attributed WAEC study corpus from public HTML and PDF pages.

The collector is intentionally conservative: requests are sequential, delayed, cached, and
never attempt to bypass access controls. Publisher-provided answers are kept distinct from any
future generated solution.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

import httpx

USER_AGENT = "Muta educational corpus builder/1.0 (+local personal study; sequential requests)"
WAEC_ROOT = "https://www.waeconline.org.ng/e-learning/"
WAEC_SUBJECTS = {
    "mathematics": urljoin(WAEC_ROOT, "Mathematics/mathsmain.html"),
    "physics": urljoin(WAEC_ROOT, "Physics/physmain.html"),
    "chemistry": urljoin(WAEC_ROOT, "Chemistry/chemmain.html"),
    "biology": urljoin(WAEC_ROOT, "Biology/Biomain.html"),
}
CHEETAH_INDEX = "https://cheetahwaec.com/past-papers"
CHEETAH_PDFS = {
    year: {
        "questions": f"https://cheetahwaec.com/assets/past-papers/{year}allproblems.pdf",
        "answers": f"https://cheetahwaec.com/assets/past-papers/{year}solutions.pdf",
    }
    for year in range(2019, 2026)
}
COPYRIGHT = {
    "waec_html": "Copyright West African Examinations Council. All rights reserved.",
    "cheetah_pdf": (
        "Cheetah WAEC terms reserve original explanations; third-party rights remain with "
        "their owners. Local educational use only."
    ),
}
BLOCK_TAGS = {
    "address",
    "article",
    "blockquote",
    "div",
    "dl",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "ul",
}
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_id(*parts: object) -> str:
    joined = "\x1f".join(str(part) for part in parts)
    return "waec-" + hashlib.sha256(joined.encode("utf-8")).hexdigest()[:24]


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def atomic_json(path: Path, value: Any, *, pretty: bool = True) -> None:
    indent = 2 if pretty else None
    suffix = "\n" if pretty else ""
    atomic_write(
        path,
        (json.dumps(value, ensure_ascii=False, indent=indent, sort_keys=pretty) + suffix).encode(
            "utf-8"
        ),
    )


@dataclass
class Element:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[Element | str] = field(default_factory=list)
    parent: Element | None = field(default=None, repr=False)

    def walk(self) -> Iterator[Element]:
        yield self
        for child in self.children:
            if isinstance(child, Element):
                yield from child.walk()

    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    def find_all(
        self,
        tag: str | None = None,
        *,
        class_name: str | None = None,
    ) -> list[Element]:
        return [
            node
            for node in self.walk()
            if (tag is None or node.tag == tag)
            and (class_name is None or class_name in node.classes())
        ]

    def find_first(
        self,
        tag: str | None = None,
        *,
        class_name: str | None = None,
    ) -> Element | None:
        for node in self.walk():
            if (tag is None or node.tag == tag) and (
                class_name is None or class_name in node.classes()
            ):
                return node
        return None


class TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("document")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Element(tag.lower(), {key.lower(): value or "" for key, value in attrs})
        node.parent = self.stack[-1]
        self.stack[-1].children.append(node)
        if node.tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag.lower():
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def parse_html(document: str) -> Element:
    parser = TreeParser()
    parser.feed(document)
    parser.close()
    return parser.root


def clean_text(value: str) -> str:
    value = html.unescape(value).replace("\xa0", " ").replace("\r", "")
    lines: list[str] = []
    for raw_line in value.splitlines():
        line = re.sub(r"[\t \f\v]+", " ", raw_line).strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        lines.append(line)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def element_text(node: Element, image_paths: dict[str, str] | None = None) -> str:
    image_paths = image_paths or {}

    def row_belongs_to_table(row: Element, table: Element) -> bool:
        parent = row.parent
        while parent is not None and parent is not table:
            if parent.tag == "table":
                return False
            parent = parent.parent
        return parent is table

    def render(item: Element | str) -> str:
        if isinstance(item, str):
            return item
        if item.tag in {"script", "style", "noscript"}:
            return ""
        if item.tag == "br":
            return "\n"
        if item.tag == "img":
            src = item.attrs.get("src", "")
            label = image_paths.get(src) or item.attrs.get("alt") or src or "unlabelled image"
            return f"\n[asset: {label}]\n"
        if item.tag == "table":
            rows: list[str] = []
            # A parent table's descendant search also finds rows in every nested
            # table. Rendering all of them here repeats legacy WAEC question and
            # observation blocks many times. Only render rows owned by this table;
            # nested tables are still rendered once through their containing cell.
            for row in (
                candidate
                for candidate in item.find_all("tr")
                if row_belongs_to_table(candidate, item)
            ):
                cells = [
                    clean_text("".join(render(child) for child in cell.children))
                    for cell in row.children
                    if isinstance(cell, Element) and cell.tag in {"td", "th"}
                ]
                if cells and any(cells):
                    rows.append(" | ".join(cells))
            return "\n" + "\n".join(rows) + "\n"
        body = "".join(render(child) for child in item.children)
        if item.tag == "li":
            return "\n- " + body.strip() + "\n"
        if item.tag in BLOCK_TAGS:
            return "\n" + body + "\n"
        return body

    return clean_text(render(node))


def relative_to(path: Path | None, root: Path) -> str | None:
    if path is None:
        return None
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


@dataclass
class FetchResult:
    data: bytes
    content_type: str
    cache_path: Path


class Fetcher:
    def __init__(
        self,
        raw_dir: Path,
        *,
        delay: float = 0.75,
        timeout: float = 45.0,
        retries: int = 3,
        refresh: bool = False,
        offline: bool = False,
    ) -> None:
        self.raw_dir = raw_dir
        self.delay = max(0.0, delay)
        self.retries = max(0, retries)
        self.refresh = refresh
        self.offline = offline
        self._last_request_at = 0.0
        self.client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            follow_redirects=True,
            timeout=httpx.Timeout(timeout),
        )

    def close(self) -> None:
        self.client.close()

    def _cache_path(self, url: str) -> Path:
        parsed = urlparse(url)
        suffix = Path(unquote(parsed.path)).suffix.lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
            suffix = ".bin"
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        host = re.sub(r"[^a-zA-Z0-9.-]+", "_", parsed.netloc)
        return self.raw_dir / "http" / host / digest[:2] / f"{digest}{suffix}"

    def get(self, url: str) -> FetchResult:
        cache_path = self._cache_path(url)
        metadata_path = cache_path.with_suffix(cache_path.suffix + ".meta.json")
        if cache_path.exists() and metadata_path.exists() and not self.refresh:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            return FetchResult(
                data=cache_path.read_bytes(),
                content_type=metadata.get("content_type", "application/octet-stream"),
                cache_path=cache_path,
            )
        if self.offline:
            raise FileNotFoundError(f"not present in local HTTP cache: {url}")

        response: httpx.Response | None = None
        for attempt in range(self.retries + 1):
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
            try:
                response = self.client.get(url)
                self._last_request_at = time.monotonic()
                if response.status_code not in {429, 500, 502, 503, 504}:
                    response.raise_for_status()
                    break
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in {429, 500, 502, 503, 504}:
                    raise
                if attempt >= self.retries:
                    raise
                time.sleep(min(30.0, 2.0 ** (attempt + 1)))
            except httpx.TransportError:
                if attempt >= self.retries:
                    raise
                time.sleep(min(30.0, 2.0 ** (attempt + 1)))
        if response is None:  # pragma: no cover - defensive guard
            raise RuntimeError(f"no response from {url}")
        data = response.content
        if not data:
            raise ValueError(f"empty response from {url}")
        content_type = response.headers.get("content-type", "application/octet-stream").split(
            ";", 1
        )[0]
        atomic_write(cache_path, data)
        atomic_json(
            metadata_path,
            {
                "content_type": content_type,
                "fetched_at": utc_now(),
                "final_url": str(response.url),
                "sha256": sha256_bytes(data),
                "source_url": url,
            },
        )
        return FetchResult(data=data, content_type=content_type, cache_path=cache_path)


def decode_html(result: FetchResult) -> str:
    for encoding in ("utf-8", "windows-1252", "iso-8859-1"):
        try:
            return result.data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return result.data.decode("utf-8", errors="replace")


def parse_years(value: str | None) -> set[int] | None:
    if not value:
        return None
    years: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            start_text, end_text = part.split(":", 1)
            start, end = int(start_text), int(end_text)
            years.update(range(min(start, end), max(start, end) + 1))
        else:
            years.add(int(part))
    return years


def discover_waec_papers(document: str, home_url: str) -> list[dict[str, Any]]:
    root = parse_html(document)
    papers: list[dict[str, Any]] = []
    for panel in root.find_all("div", class_name="panel"):
        heading = panel.find_first(class_name="panel-heading")
        if heading is None:
            continue
        session = element_text(heading)
        year_match = re.search(r"\b(19|20)\d{2}\b", session)
        year = int(year_match.group(0)) if year_match else None
        for anchor in panel.find_all("a", class_name="list-group-item"):
            href = anchor.attrs.get("href", "").strip()
            label = element_text(anchor)
            if not href or "paper" not in label.lower():
                continue
            papers.append(
                {
                    "url": urljoin(home_url, href),
                    "paper": label,
                    "session": session,
                    "year": year,
                }
            )
    unique = {paper["url"]: paper for paper in papers}
    return sorted(
        unique.values(),
        key=lambda item: (item.get("year") or 0, item.get("session") or "", item["url"]),
    )


def discover_waec_questions(document: str, paper_url: str) -> list[str]:
    root = parse_html(document)
    menu = root.find_first("ul", class_name="pagenum")
    search_root = menu or root
    questions: list[str] = []
    for anchor in search_root.find_all("a"):
        href = anchor.attrs.get("href", "").strip()
        label = element_text(anchor).strip()
        if not href or not re.fullmatch(r"\d+[A-Za-z]?", label):
            continue
        if menu is None and not re.search(r"q\d+[A-Za-z]?\.html?$", href, re.IGNORECASE):
            continue
        questions.append(urljoin(paper_url, href))
    return list(dict.fromkeys(questions))


def extract_title(root: Element) -> str:
    top_menu = root.find_first("div", class_name="TopMenu")
    if top_menu is not None:
        heading = top_menu.find_first("h3")
        if heading is not None:
            return element_text(heading)
    title = root.find_first("title")
    return element_text(title) if title is not None else ""


def extract_image_urls(node: Element, page_url: str) -> list[tuple[str, str]]:
    urls: list[tuple[str, str]] = []
    for image in node.find_all("img"):
        src = image.attrs.get("src", "").strip()
        if not src or src.startswith("data:"):
            continue
        urls.append((src, urljoin(page_url, src)))
    return list(dict.fromkeys(urls))


def suffix_for_asset(url: str, content_type: str) -> str:
    suffix = Path(unquote(urlparse(url).path)).suffix.lower()
    if re.fullmatch(r"\.(png|jpe?g|gif|webp|svg)", suffix):
        return suffix
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
    }.get(content_type, ".bin")


def split_observation_and_answer(text: str) -> tuple[str | None, str | None]:
    patterns = [
        r"\bthe expected answers? (?:are|is)(?: as follows)?\s*:?",
        r"\bthe expected responses?\s*:?",
        r"\bexpected answers?\s*:?",
        r"\bexpected responses?\s*:?",
        (
            r"\b(?:they|candidates?)\s+(?:were|was)\s+expected\s+to\s+"
            r"(?:solve|answer|respond)[^:\n]*\s*:"
        ),
        r"\b(?:they|candidates?)\s+(?:were|was)\s+expected\s+to\s+",
        r"\bsolution\s*:?",
        r"\bthe\s+expected\s+answers?\s+(?:are|is)(?:\s+as\s+follows)?\s*:?\s*",
        r"\bthe\s+expected\s+responses?\s*(?:are|were|is|was)?(?:\s+as\s+follows)?\s*:?\s*",
        r"\bexpected\s+answers?\s*:?\s*",
        r"\bexpected\s+responses?\s*(?:are|were|is|was)?(?:\s+as\s+follows)?\s*:?\s*",
        r"\bother\s+correct\s+answers?\s+include\s*:?\s*",
        r"\bcorrect\s+answers?\s+(?:include|are|is)\s*:?\s*",
        (
            r"\bthe\s+expected\s+(?:calculations?|table|diagram|graph|working|method|"
            r"values?)[^\n:.]{0,80}(?:was|were|is|are)(?:\s+as\s+follows)?\s*:?\s*"
        ),
        (
            r"\b(?:in\s+(?:part|section)\s+[^,\n]{0,40},\s*)?(?:the\s+)?"
            r"candidates?[’']?\s+(?:were\s+)?expected\s+to\s+"
        ),
        (
            r"\b(?:in\s+(?:part|section)\s+[^,\n]{0,40},\s*)?"
            r"(?:they|candidates?[’']?)\s+(?:did|solved|responded)\s+as\s+expected\s+by\s+"
        ),
        r"\bit\s+was\s+expected\s+(?:that|if)\s+",
        (
            r"\bthe\s+(?:required|correct)\s+(?:solution|answer|response|table|diagram|"
            r"graph)\s+(?:was|is)\s*:?\s*"
        ),
        r"\bcandidates?[’']?\s+correctly\s+",
    ]
    match: re.Match[str] | None = None
    for pattern in patterns:
        candidate = re.search(pattern, text, flags=re.IGNORECASE)
        if candidate is not None and (match is None or candidate.start() < match.start()):
            match = candidate
    if match is None:
        return (text or None), None
    observation = clean_text(text[: match.start()]) or None
    answer = clean_text(text[match.end() :]) or None
    return observation, answer


def question_number_from(text: str, url: str) -> str:
    match = re.search(r"\b(?:question|problem)\s+([0-9]+[A-Za-z]?)", text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    name = Path(urlparse(url).path).stem
    match = re.search(r"q([0-9]+[A-Za-z]?)$", name, re.IGNORECASE)
    return match.group(1).upper() if match else name


def strip_question_heading(text: str) -> str:
    return clean_text(
        re.sub(
            r"^\s*(?:question|problem)\s+[0-9]+[A-Za-z]?\s*[:.-]?\s*",
            "",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
    )


def extract_options(
    text: str, *, require_heading: bool = False
) -> tuple[str, list[dict[str, str]]]:
    heading_match = re.search(r"\bPossible Answers?\s*:\s*", text, re.IGNORECASE)
    if require_heading and heading_match is None:
        return clean_text(text), []

    option_text = text[heading_match.end() :] if heading_match else text
    pattern = re.compile(
        r"(?:^|[;\n])\s*([A-D])\s*[.)]\s*(.+?)"
        r"(?=(?:[;\n]\s*[A-D]\s*[.)]\s*)|\Z)",
        re.DOTALL,
    )
    matches = list(pattern.finditer(option_text))
    if [match.group(1) for match in matches] != list("ABCD"):
        return clean_text(text), []
    options = [{"label": match.group(1), "text": clean_text(match.group(2))} for match in matches]
    question = text[: heading_match.start()] if heading_match else option_text[: matches[0].start()]
    return clean_text(question), options


def extract_cheetah_options(
    text: str, *, question_kind: str | None
) -> tuple[str, list[dict[str, str]]]:
    if question_kind == "frq":
        return clean_text(text), []
    return extract_options(text, require_heading=question_kind != "mcq")


def extract_marks(text: str) -> int | None:
    marks = [
        int(value)
        for value in re.findall(r"\[\s*(\d+)\s*marks?\s*\]", text, re.IGNORECASE)
    ]
    return sum(marks) if marks else None


def infer_format(paper: str | None, options: list[dict[str, str]], text: str) -> str:
    if options:
        return "multiple_choice"
    if paper and re.search(r"paper\s*3", paper, re.IGNORECASE):
        return "practical"
    if re.search(r"\bapparatus\b|\bexperiment\b", text, re.IGNORECASE):
        return "practical"
    if text:
        return "free_response"
    return "unknown"


def parse_waec_question(
    document: str,
    *,
    page_url: str,
    paper_url: str,
    subject: str,
    paper: str | None,
    session: str | None,
    year: int | None,
    fetcher: Fetcher,
    output_dir: Path,
    metadata_only: bool,
    failures: list[dict[str, Any]],
) -> dict[str, Any]:
    root = parse_html(document)
    top = root.find_first("div", class_name="topcontent")
    bottom = root.find_first("div", class_name="bottomcontent")
    legacy_layout = top is None
    title = extract_title(root)
    if year is None:
        year_match = re.search(r"\b(19|20)\d{2}\b", title)
        year = int(year_match.group(0)) if year_match else None

    image_map: dict[str, str] = {}
    assets: list[dict[str, Any]] = []
    legacy_observation_offset = None
    if legacy_layout:
        legacy_observation_match = re.search(r"\bObservation\b", document, re.IGNORECASE)
        if legacy_observation_match:
            legacy_observation_offset = legacy_observation_match.start()
    asset_containers = (
        (("legacy", root),)
        if legacy_layout
        else (("question", top), ("answer", bottom))
    )
    for container_role, container in asset_containers:
        if container is None:
            continue
        for source_attr, asset_url in extract_image_urls(container, page_url):
            role = container_role
            if legacy_layout:
                source_offset = document.find(source_attr)
                role = (
                    "answer"
                    if legacy_observation_offset is not None
                    and source_offset > legacy_observation_offset
                    else "question"
                )
            parsed_asset_url = urlparse(asset_url)
            basename = Path(unquote(parsed_asset_url.path)).name.lower()
            if parsed_asset_url.scheme not in {"http", "https"}:
                failures.append(
                    {
                        "stage": "waec_asset",
                        "url": asset_url,
                        "error": "unsupported non-HTTP asset URL published in source HTML",
                    }
                )
                continue
            if basename in {"waechead.png", "waechead.jpg", "logo.png", "e-learning.png"}:
                continue
            local_path: Path | None = None
            digest: str | None = None
            if not metadata_only:
                try:
                    result = fetcher.get(asset_url)
                    digest = sha256_bytes(result.data)
                    suffix = suffix_for_asset(asset_url, result.content_type)
                    local_path = output_dir / "assets" / subject / f"{digest}{suffix}"
                    if not local_path.exists():
                        atomic_write(local_path, result.data)
                except Exception as exc:  # noqa: BLE001 - failure belongs in the manifest
                    failures.append(
                        {
                            "stage": "waec_asset",
                            "url": asset_url,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
            relative = relative_to(local_path, output_dir)
            image_map[source_attr] = relative or asset_url
            assets.append(
                {"url": asset_url, "local_path": relative, "role": role, "sha256": digest}
            )

    if legacy_layout:
        page_text = element_text(root, image_map)
        heading_matches = list(
            re.finditer(
                r"\bQuestion\s+\d+[A-Za-z]?\b",
                page_text,
                re.IGNORECASE,
            )
        )
        heading_match = heading_matches[0] if heading_matches else None
        observation_match = (
            re.search(r"\bObservation\b", page_text[heading_match.end() :], re.IGNORECASE)
            if heading_match
            else None
        )
        if heading_match and observation_match:
            observation_start = heading_match.end() + observation_match.start()
            observation_end = heading_match.end() + observation_match.end()
            top_text = page_text[heading_match.start() : observation_start]
            bottom_text = page_text[observation_end:]
        elif heading_match:
            top_text = page_text[heading_match.start() :]
            bottom_text = ""
        else:
            top_text = ""
            bottom_text = ""
        bottom_text = re.split(
            r"(?:^|\n)\s*(?:Powered by|Copyright ©)",
            bottom_text,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
    else:
        top_text = element_text(top, image_map) if top is not None else ""
        bottom_text = element_text(bottom, image_map) if bottom is not None else ""
    referenced_assets = set(re.findall(r"\[asset: ([^\]]+)\]", top_text + "\n" + bottom_text))
    assets = [
        asset
        for asset in assets
        if (asset["local_path"] or asset["url"]) in referenced_assets
    ]
    number = question_number_from(top_text, page_url)
    question_text = strip_question_heading(top_text)
    question_text, options = extract_options(question_text)
    observation, published_answer = split_observation_and_answer(bottom_text)
    warnings: list[str] = []
    answer_assets = [asset for asset in assets if asset["role"] == "answer"]
    if published_answer is None and answer_assets:
        published_answer = clean_text(
            "Publisher-provided visual answer:\n"
            + "\n".join(
                f"[asset: {asset['local_path'] or asset['url']}]" for asset in answer_assets
            )
        )
        warnings.append("published_answer_is_visual_asset")
    if not question_text:
        warnings.append("question_text_missing")
    if not bottom_text:
        warnings.append("answer_section_missing")
    elif published_answer is None:
        warnings.append("published_answer_not_identified")
    if assets:
        warnings.append("visual_assets_require_review")
    if any(asset["local_path"] is None for asset in assets):
        warnings.append("one_or_more_assets_not_downloaded")

    if not question_text or (not bottom_text and not assets):
        content_status = "incomplete"
    elif assets:
        content_status = "needs_visual_review"
    elif published_answer:
        content_status = "complete"
    else:
        content_status = "incomplete"

    source_cache = fetcher._cache_path(page_url)  # deterministic path; may already exist
    return {
        "record_id": stable_id("waec_html", page_url, number),
        "exam_board": "WAEC/WASSCE",
        "year": year,
        "subject": subject,
        "question_number": number,
        "question_text": question_text,
        "options": options,
        "correct_answer": None,
        "worked_solution": published_answer,
        "topic_tags": [],
        "difficulty": None,
        "marking_scheme": published_answer,
        "examiner_observation": observation,
        "marks": extract_marks(question_text),
        "paper": paper,
        "session": session,
        "question_format": infer_format(paper, options, question_text),
        "source": {
            "publisher": "West African Examinations Council",
            "page_url": page_url,
            "question_url": page_url,
            "answer_url": page_url,
            "source_type": "waec_html",
            "copyright_notice": COPYRIGHT["waec_html"],
            "retrieved_at": utc_now(),
            "local_question_file": relative_to(source_cache, output_dir),
            "local_answer_file": relative_to(source_cache, output_dir),
        },
        "assets": assets,
        "extraction_warnings": sorted(set(warnings)),
        "content_status": content_status,
        "answer_status": "published" if published_answer else "missing",
        "generated_solution": None,
    }


def collect_waec(
    *,
    subjects: Iterable[str],
    years: set[int] | None,
    fetcher: Fetcher,
    output_dir: Path,
    max_questions: int | None,
    metadata_only: bool,
    failures: list[dict[str, Any]],
    progress: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    discovered_papers = 0
    discovered_questions = 0
    for subject in subjects:
        home_url = WAEC_SUBJECTS[subject]
        if progress:
            print(f"[waec] discover {subject}: {home_url}", file=sys.stderr)
        try:
            home_result = fetcher.get(home_url)
            papers = discover_waec_papers(decode_html(home_result), home_url)
        except Exception as exc:  # noqa: BLE001
            failures.append(
                {
                    "stage": "waec_subject",
                    "url": home_url,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        if years is not None:
            papers = [paper for paper in papers if paper.get("year") in years]
        discovered_papers += len(papers)

        for paper_meta in papers:
            if max_questions is not None and len(records) >= max_questions:
                break
            paper_url = paper_meta["url"]
            try:
                paper_result = fetcher.get(paper_url)
                question_urls = discover_waec_questions(decode_html(paper_result), paper_url)
            except Exception as exc:  # noqa: BLE001
                failures.append(
                    {
                        "stage": "waec_paper",
                        "url": paper_url,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue
            discovered_questions += len(question_urls)
            for question_url in question_urls:
                if max_questions is not None and len(records) >= max_questions:
                    break
                if progress:
                    print(f"[waec] {subject} {paper_meta.get('year')} {question_url}", file=sys.stderr)
                try:
                    question_result = fetcher.get(question_url)
                    record = parse_waec_question(
                        decode_html(question_result),
                        page_url=question_url,
                        paper_url=paper_url,
                        subject=subject,
                        paper=paper_meta.get("paper"),
                        session=paper_meta.get("session"),
                        year=paper_meta.get("year"),
                        fetcher=fetcher,
                        output_dir=output_dir,
                        metadata_only=metadata_only,
                        failures=failures,
                    )
                    records.append(record)
                except Exception as exc:  # noqa: BLE001
                    failures.append(
                        {
                            "stage": "waec_question",
                            "url": question_url,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
        if max_questions is not None and len(records) >= max_questions:
            break
    return records, {
        "papers_discovered": discovered_papers,
        "questions_discovered": discovered_questions,
        "records": len(records),
    }


def split_pdf_question_entries(text: str) -> dict[str, tuple[str, str | None]]:
    marker = re.compile(
        r"(?im)^\s*(?:question|problem)\s+([0-9]+)"
        r"(?:\s*\((mcq|frq)\))?\s*$"
    )
    matches = list(marker.finditer(text))
    entries: dict[str, tuple[str, str | None]] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = clean_text(text[match.end() : end])
        if block:
            question_kind = match.group(2).lower() if match.group(2) else None
            entries[match.group(1)] = (block, question_kind)
    return entries


def split_pdf_questions(text: str) -> dict[str, str]:
    return {
        number: block
        for number, (block, _question_kind) in split_pdf_question_entries(text).items()
    }


def clean_pdf_block(text: str) -> str:
    lines: list[str] = []
    for line in clean_text(text).splitlines():
        if re.search(
            r"cheetah\s*waec|t\.me/cheetahwaecbot", line, re.IGNORECASE
        ):
            continue
        if re.fullmatch(r"\d+", line.strip()):
            continue
        lines.append(line)
    return clean_text("\n".join(lines))


def extract_pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - exercised only in a broken environment
        raise RuntimeError("pypdf is required for Cheetah PDF extraction") from exc
    reader = PdfReader(BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def parse_answer_block(block: str) -> tuple[str | None, str | None, str]:
    answer_match = re.search(r"(?im)^\s*(?:correct\s+answer|answer)\s*:\s*([^\n]+)", block)
    answer = clean_text(answer_match.group(1)) if answer_match else None
    solution_match = re.search(r"(?im)^\s*solution\s*[.:]?\s*", block)
    if solution_match:
        solution = clean_pdf_block(block[solution_match.end() :]) or None
    elif answer_match:
        # The 2025 answer PDF omits a literal "Solution:" heading. Its worked
        # explanation starts immediately after the answer line.
        solution = clean_pdf_block(block[answer_match.end() :]) or None
    else:
        solution = None
    question_end = None
    if answer_match:
        question_end = answer_match.start()
    elif solution_match:
        question_end = solution_match.start()
    question = clean_pdf_block(block[:question_end] if question_end is not None else block)
    return answer, solution, question


def parse_cheetah_year(
    *,
    year: int,
    question_data: bytes,
    answer_data: bytes,
    question_url: str,
    answer_url: str,
    local_question_file: Path,
    local_answer_file: Path,
    output_dir: Path,
) -> list[dict[str, Any]]:
    question_entries = split_pdf_question_entries(extract_pdf_text(question_data))
    answer_entries = split_pdf_question_entries(extract_pdf_text(answer_data))
    records: list[dict[str, Any]] = []
    for number in sorted(set(question_entries) | set(answer_entries), key=lambda item: int(item)):
        raw_question_block, question_kind = question_entries.get(number, ("", None))
        answer_block, answer_kind = answer_entries.get(number, ("", None))
        question_kind = question_kind or answer_kind
        raw_question = clean_pdf_block(raw_question_block)
        correct_answer, solution, answer_question = parse_answer_block(answer_block)
        candidate = raw_question or answer_question
        question_text, options = extract_cheetah_options(candidate, question_kind=question_kind)
        if not question_text and answer_question:
            question_text, fallback_options = extract_cheetah_options(
                answer_question, question_kind=question_kind
            )
            options = options or fallback_options
        warnings = ["pdf_text_requires_visual_verification"]
        if not question_text:
            warnings.append("question_text_missing")
        if not solution and not correct_answer:
            warnings.append("published_answer_not_identified")
        content_status = "needs_visual_review" if question_text else "incomplete"
        records.append(
            {
                "record_id": stable_id("cheetah_pdf", year, number, question_url),
                "exam_board": "WAEC/WASSCE",
                "year": year,
                "subject": "mathematics",
                "question_number": number,
                "question_text": question_text,
                "options": options,
                "correct_answer": correct_answer,
                "worked_solution": solution,
                "topic_tags": [],
                "difficulty": None,
                "marking_scheme": solution,
                "examiner_observation": None,
                "marks": None,
                "paper": None,
                "session": None,
                "question_format": (
                    "multiple_choice"
                    if question_kind == "mcq"
                    else infer_format(None, options, question_text)
                ),
                "source": {
                    "publisher": "Cheetah WAEC",
                    "page_url": CHEETAH_INDEX,
                    "question_url": question_url,
                    "answer_url": answer_url,
                    "source_type": "cheetah_pdf",
                    "copyright_notice": COPYRIGHT["cheetah_pdf"],
                    "retrieved_at": utc_now(),
                    "local_question_file": relative_to(local_question_file, output_dir),
                    "local_answer_file": relative_to(local_answer_file, output_dir),
                },
                "assets": [],
                "extraction_warnings": warnings,
                "content_status": content_status,
                "answer_status": (
                    "published" if solution is not None or correct_answer is not None else "missing"
                ),
                "generated_solution": None,
            }
        )
    return records


def collect_cheetah(
    *,
    years: set[int] | None,
    fetcher: Fetcher,
    output_dir: Path,
    max_questions: int | None,
    metadata_only: bool,
    failures: list[dict[str, Any]],
    progress: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    selected_years = [year for year in CHEETAH_PDFS if years is None or year in years]
    downloaded = 0
    for year in selected_years:
        if max_questions is not None and len(records) >= max_questions:
            break
        urls = CHEETAH_PDFS[year]
        if progress:
            print(f"[cheetah] {year} questions and solutions", file=sys.stderr)
        if metadata_only:
            continue
        try:
            question_result = fetcher.get(urls["questions"])
            answer_result = fetcher.get(urls["answers"])
            if not question_result.data.startswith(b"%PDF"):
                raise ValueError("question download is not a PDF")
            if not answer_result.data.startswith(b"%PDF"):
                raise ValueError("answer download is not a PDF")
            question_path = output_dir / "raw" / "cheetah" / f"{year}-questions.pdf"
            answer_path = output_dir / "raw" / "cheetah" / f"{year}-answers.pdf"
            atomic_write(question_path, question_result.data)
            atomic_write(answer_path, answer_result.data)
            downloaded += 2
            year_records = parse_cheetah_year(
                year=year,
                question_data=question_result.data,
                answer_data=answer_result.data,
                question_url=urls["questions"],
                answer_url=urls["answers"],
                local_question_file=question_path,
                local_answer_file=answer_path,
                output_dir=output_dir,
            )
            if max_questions is not None:
                year_records = year_records[: max_questions - len(records)]
            records.extend(year_records)
        except Exception as exc:  # noqa: BLE001
            failures.append(
                {
                    "stage": "cheetah_pdf_pair",
                    "url": urls["questions"],
                    "answer_url": urls["answers"],
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return records, {
        "years_discovered": selected_years,
        "pdfs_downloaded": downloaded,
        "records": len(records),
    }


def validate_record(record: dict[str, Any], schema: dict[str, Any] | None = None) -> None:
    required = {
        "record_id",
        "exam_board",
        "year",
        "subject",
        "question_number",
        "question_text",
        "options",
        "correct_answer",
        "worked_solution",
        "topic_tags",
        "difficulty",
        "marking_scheme",
        "examiner_observation",
        "paper",
        "session",
        "source",
        "assets",
        "extraction_warnings",
        "content_status",
        "answer_status",
        "generated_solution",
    }
    missing = sorted(required - record.keys())
    if missing:
        raise ValueError(f"record {record.get('record_id')} missing fields: {missing}")
    if not isinstance(record["options"], list) or not isinstance(record["assets"], list):
        raise TypeError(f"record {record['record_id']} has non-list options/assets")
    if schema is not None:
        try:
            import jsonschema
        except ImportError:
            return
        jsonschema.validate(record, schema)


def coverage(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_subject: dict[str, int] = {}
    by_source: dict[str, int] = {}
    by_year: dict[str, int] = {}
    status: dict[str, int] = {}
    for record in records:
        subject = record["subject"]
        source = record["source"]["source_type"]
        year = str(record["year"] or "unknown")
        content_status = record["content_status"]
        by_subject[subject] = by_subject.get(subject, 0) + 1
        by_source[source] = by_source.get(source, 0) + 1
        by_year[year] = by_year.get(year, 0) + 1
        status[content_status] = status.get(content_status, 0) + 1
    return {
        "total_records": len(records),
        "by_subject": dict(sorted(by_subject.items())),
        "by_source": dict(sorted(by_source.items())),
        "by_year": dict(sorted(by_year.items())),
        "by_content_status": dict(sorted(status.items())),
        "with_published_answer": sum(
            record["answer_status"] == "published" for record in records
        ),
        "with_assets": sum(bool(record["assets"]) for record in records),
    }


def write_outputs(
    output_dir: Path,
    records: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    def question_sort_key(value: object) -> tuple[int, int | str]:
        text = str(value)
        return (0, int(text)) if text.isdigit() else (1, text)

    records = sorted(
        records,
        key=lambda item: (
            item["subject"],
            item["year"] or 0,
            item["source"]["source_type"],
            question_sort_key(item["question_number"]),
        ),
    )
    schema_path = Path(__file__).with_name("waec") / "schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8")) if schema_path.exists() else None
    for record in records:
        validate_record(record, schema)
    atomic_json(output_dir / "questions.json", records)
    lines = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    atomic_write(output_dir / "questions.jsonl", lines.encode("utf-8"))
    manifest["coverage"] = coverage(records)
    atomic_json(output_dir / "manifest.json", manifest)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=("waec", "cheetah"),
        default=("waec", "cheetah"),
    )
    parser.add_argument(
        "--subjects",
        nargs="+",
        choices=tuple(WAEC_SUBJECTS),
        default=tuple(WAEC_SUBJECTS),
    )
    parser.add_argument(
        "--years",
        help="Comma-separated years and inclusive ranges, for example 2019:2023,2025",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("corpus/waec"))
    parser.add_argument("--delay", type=float, default=0.75)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--max-questions", type=int)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="read only cached downloads and record cache misses without making network requests",
    )
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="replace existing normalized records instead of merging with them",
    )
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    years = parse_years(args.years)
    failures: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    existing_records = 0
    existing_questions = output_dir / "questions.json"
    if existing_questions.exists() and not args.replace:
        loaded = json.loads(existing_questions.read_text(encoding="utf-8"))
        if not isinstance(loaded, list):
            raise TypeError(f"{existing_questions} must contain a JSON array")
        records.extend(loaded)
        existing_records = len(loaded)
    sources: dict[str, Any] = {}
    fetcher = Fetcher(
        output_dir / "raw",
        delay=args.delay,
        timeout=args.timeout,
        retries=args.retries,
        refresh=args.refresh,
        offline=args.offline,
    )
    started_at = utc_now()
    try:
        if "waec" in args.sources:
            waec_records, waec_stats = collect_waec(
                subjects=args.subjects,
                years=years,
                fetcher=fetcher,
                output_dir=output_dir,
                max_questions=args.max_questions,
                metadata_only=args.metadata_only,
                failures=failures,
                progress=not args.quiet,
            )
            records.extend(waec_records)
            sources["waec"] = waec_stats
        if "cheetah" in args.sources:
            remaining = None
            if args.max_questions is not None:
                remaining = max(0, args.max_questions - len(records))
            cheetah_records, cheetah_stats = collect_cheetah(
                years=years,
                fetcher=fetcher,
                output_dir=output_dir,
                max_questions=remaining,
                metadata_only=args.metadata_only,
                failures=failures,
                progress=not args.quiet,
            )
            records.extend(cheetah_records)
            sources["cheetah"] = cheetah_stats
    finally:
        fetcher.close()

    unique = {record["record_id"]: record for record in records}
    manifest = {
        "schema_version": 1,
        "started_at": started_at,
        "finished_at": utc_now(),
        "collector": "corpus/waec_collect.py",
        "user_agent": USER_AGENT,
        "sources_requested": list(args.sources),
        "subjects_requested": list(args.subjects),
        "years_requested": sorted(years) if years is not None else "all published",
        "metadata_only": args.metadata_only,
        "merged_existing_records": existing_records,
        "request_delay_seconds": args.delay,
        "request_retries": args.retries,
        "sources": sources,
        "failures": failures,
        "limitations": [
            "Publisher copyright and attribution remain in force; local educational use only.",
            "Records with visual assets or PDF extraction warnings require visual review.",
            "Generated answers are never represented as publisher-provided answers.",
        ],
    }
    write_outputs(output_dir, list(unique.values()), manifest)
    if not args.quiet:
        print(json.dumps(manifest["coverage"], indent=2, sort_keys=True))
        if failures:
            print(f"Recorded {len(failures)} fetch/parse failures in manifest.json", file=sys.stderr)
    return 0 if unique else 2


if __name__ == "__main__":
    raise SystemExit(main())
