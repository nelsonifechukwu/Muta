"""Turn learner documents into citeable retrieval chunks (PDF, Markdown, plain text).

Every chunk carries a locator a learner can follow back: a physical PDF page, or for text
resources a section ordinal plus its heading path ("Unit 2 › Forces"). The ordinal rides in
the existing ``page`` field so citations, de-duplication and storage keep one shape;
``section`` is None for PDFs and a heading path (possibly "") for text resources.

Design notes live in docs/rag-resources.md: chunk size, the header/footer heuristic, the
contents-page penalty and the overview selection were each measured on a real 68-page PDF.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

PDF_MIME = "application/pdf"
MARKDOWN_MIME = "text/markdown"
TEXT_MIME = "text/plain"
TEXT_MIMES = frozenset({MARKDOWN_MIME, TEXT_MIME})
RESOURCE_MIMES = frozenset({PDF_MIME, *TEXT_MIMES})

#: Bumped whenever chunk boundaries or chunk text change. It is part of every resource's
#: stored index identity, so a new chunker re-prepares old resources instead of mixing
#: incompatible chunk shapes in one ranking.
CHUNKER_VERSION = "chunks-v2"
#: ~200–250 tokens of English: small enough that one evidence block is one idea and several
#: fit a 4,096-token lane beside the tutor prompt; large enough to hold a worked step.
CHUNK_CHARS = 900
CHUNK_OVERLAP_CHARS = 150
#: Text files are read whole into memory and re-parsed for the reader view.
MAX_TEXT_RESOURCE_BYTES = 4 * 1024 * 1024
SECTION_SEPARATOR = " › "
#: Well inside `ResourceCitation.section` (max 400) so stored citations always validate.
MAX_SECTION_LABEL = 240

_SPACE = re.compile(r"[ \t\f\v]+")
_BLANKS = re.compile(r"\n{3,}")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_DIGITS = re.compile(r"\d+")
_PAGE_NUMBER_LINE = re.compile(
    r"^(?:page\s*)?[\divxlc]{1,6}(?:\s*(?:of|/)\s*\d{1,5})?$", re.IGNORECASE
)
_CONTENTS_LINE = re.compile(r"^(?P<title>.{3,}?)(?:\s*[.·…_\-]{2,}\s*|\s+)(?P<page>\d{1,4})$")
_CONTENTS_HEADING = re.compile(r"^\s*(?:table of\s+)?contents\s*$", re.IGNORECASE | re.MULTILINE)
_OVERVIEW = re.compile(
    r"\b(?:summari[sz](?:e|es|ing|ation)|summary|overview|outline|synopsis|gist|tl;?dr|"
    r"main\s+(?:points?|ideas?|topics?|themes?|arguments?|takeaways?)|"
    r"key\s+(?:points?|ideas?|topics?|themes?|takeaways?|concepts?)|"
    r"what(?:'s|\s+is|\s+does)\s+(?:this|the)\s+(?:document|book|paper|file|pdf|chapter|"
    r"article|text|note|notes|reading)\s+(?:about|cover|say)|"
    r"structure\s+of\s+(?:this|the)|table\s+of\s+contents)\b",
    re.IGNORECASE,
)

_ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_FRONT_MATTER = re.compile(r"\A---[ \t]*\n.*?\n(?:---|\.\.\.)[ \t]*(?:\n|\Z)", re.DOTALL)
_BLOCK_START = re.compile(r"^ {0,3}(?:[-+*]\s|\d+[.)]\s|>|\||<)")
_INLINE_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_INLINE_MARK = re.compile(r"[*_`~]+")


# --- uploads ---------------------------------------------------------------------------


def classify_upload(filename: str | None, content_type: str | None, head: bytes) -> str | None:
    """The resource type an upload really is, from its bytes and name; None if unsupported.

    A PDF is recognised by its signature alone. Text types are accepted only by an explicit
    `.md`/`.markdown`/`.txt` name or a text/* declared type, then validated as UTF-8 later.
    """
    if head.startswith(b"%PDF-"):
        return PDF_MIME
    suffix = Path(filename or "").suffix.lower()
    declared = (content_type or "").split(";", 1)[0].strip().lower()
    if suffix in {".md", ".markdown"} or declared in {"text/markdown", "text/x-markdown"}:
        return MARKDOWN_MIME
    if suffix == ".txt" or declared == "text/plain":
        return TEXT_MIME
    return None


def decode_text(data: bytes) -> str:
    """Strict UTF-8 (BOM tolerated) with normalised newlines; binary files are refused."""
    if b"\x00" in data:
        raise ValueError("this file is not plain text")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("text files must be saved as UTF-8") from exc
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return _CONTROL.sub("", text)


# --- PDF pages ---------------------------------------------------------------------------


def normalise_page(text: str) -> str:
    lines = [_SPACE.sub(" ", line).strip() for line in text.replace("\x00", "").splitlines()]
    return _BLANKS.sub("\n\n", "\n".join(lines)).strip()


def _edge_key(line: str) -> str:
    return _DIGITS.sub("#", line.lower()).strip()


def clean_pdf_pages(pages: Sequence[str], *, edge_lines: int = 2) -> list[str]:
    """Remove running headers/footers and bare page numbers from extracted PDF pages.

    A line is boilerplate when the same text (digits ignored, so "Page 3"/"Page 4" match)
    sits within ``edge_lines`` of the top or bottom of at least 40% of the text pages, with a
    floor of three pages. Without this, every chunk of a long report shares "Company
    Confidential · Prompt Engineering · 14", which inflates lexical and semantic matches for
    any query that happens to mention the title.
    """
    normalised = [normalise_page(page) for page in pages]
    split = [page.split("\n") if page else [] for page in normalised]
    text_pages = sum(1 for lines in split if lines)
    counts: Counter[str] = Counter()
    for lines in split:
        edges = {
            _edge_key(line) for line in lines[:edge_lines] + lines[-edge_lines:] if line.strip()
        }
        counts.update(edges)
    threshold = max(3, int(text_pages * 0.4 + 0.999))
    repeated = {key for key, count in counts.items() if count >= threshold and len(key) <= 160}
    cleaned: list[str] = []
    for lines in split:
        kept = list(lines)

        def boilerplate(line: str) -> bool:
            stripped = line.strip()
            return bool(stripped) and (
                _edge_key(stripped) in repeated or bool(_PAGE_NUMBER_LINE.match(stripped))
            )

        # One more than the counted edge: a page number commonly sits just inside the
        # running header ("Report title / Month year / 14").
        for _ in range(edge_lines + 1):
            if kept and boilerplate(kept[0]):
                kept.pop(0)
            if kept and boilerplate(kept[-1]):
                kept.pop()
        cleaned.append(_BLANKS.sub("\n\n", "\n".join(kept)).strip())
    return cleaned


def chunk_pages(
    pages: Sequence[str],
    *,
    target_chars: int = CHUNK_CHARS,
    overlap_chars: int = CHUNK_OVERLAP_CHARS,
) -> list[dict]:
    """Make overlapping chunks that never cross a physical PDF page boundary."""
    chunks: list[dict] = []
    ordinal = 0
    for page_number, raw in enumerate(pages, start=1):
        text = normalise_page(raw)
        if not text:
            continue
        for body in _windows(text, target_chars, overlap_chars):
            chunks.append({"chunk_index": ordinal, "page": page_number, "text": body})
            ordinal += 1
    return chunks


def _windows(text: str, target_chars: int, overlap_chars: int) -> list[str]:
    bodies: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + target_chars)
        if end < len(text):
            # Prefer a readable boundary without allowing tiny chunks.
            boundary = max(
                text.rfind("\n", start + target_chars // 2, end),
                text.rfind(". ", start + target_chars // 2, end),
            )
            if boundary > start:
                end = boundary + 1
        body = text[start:end].strip()
        if body:
            bodies.append(body)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap_chars)
    return bodies


def is_contents_page(text: str) -> bool:
    """A table-of-contents chunk: mostly "Title ....... 12" lines, or a Contents heading."""
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return False
    entries = sum(1 for line in lines if _CONTENTS_LINE.match(line))
    if _CONTENTS_HEADING.search(text) and entries >= 3:
        return True
    return entries >= 5 and entries >= 0.4 * len(lines)


_INTRO = re.compile(
    r"^\s*(?:§ [^\n]*\n)?\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\.?\s+)?"
    r"(?:introduction|overview|abstract|executive summary|preface|about this "
    r"(?:book|guide|document|course))\b",
    re.IGNORECASE | re.MULTILINE,
)
_OUTRO = re.compile(
    r"^\s*(?:§ [^\n]*\n)?\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\.?\s+)?"
    r"(?:summary|conclusions?|in summary|to conclude|concluding remarks|final thoughts|"
    r"key takeaways|wrap[- ]?up)\b",
    re.IGNORECASE | re.MULTILINE,
)
_BACK_MATTER = re.compile(
    r"^\s*(?:§ [^\n]*\n)?\s*(?:#+\s*)?(?:endnotes|references|bibliography|index|"
    r"acknowledg(?:e)?ments|appendix|about the authors?|further reading|notes)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


_INTRO_HEADING = re.compile(
    r"^\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\.?\s+)?(?:introduction|overview|abstract|"
    r"executive summary|preface)\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_OUTRO_HEADING = re.compile(
    r"^\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\.?\s+)?(?:summary|conclusions?|in summary|"
    r"concluding remarks|final thoughts|key takeaways)\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def is_intro(text: str) -> bool:
    """Opens with an introduction, or contains an "Introduction"-style heading line."""
    return bool(_INTRO.search(text[:400]) or _INTRO_HEADING.search(text))


def is_outro(text: str) -> bool:
    """Opens with a conclusion, or contains a "Summary"/"Conclusion" heading line."""
    return bool(_OUTRO.search(text[:400]) or _OUTRO_HEADING.search(text))


def is_back_matter(text: str) -> bool:
    """Endnotes, references, acknowledgements: real text, but no help summarising a document."""
    return bool(_BACK_MATTER.search(text[:200]))


def wants_overview(query: str) -> bool:
    """A request about the whole document rather than one fact in it."""
    return bool(_OVERVIEW.search(query or ""))


# --- Markdown and plain text ---------------------------------------------------------------


@dataclass
class TextSection:
    ordinal: int
    path: list[str]
    level: int
    body: str

    @property
    def label(self) -> str:
        return section_label(self.path)


def section_label(path: Sequence[str]) -> str:
    """Heading path for citations, at most `MAX_SECTION_LABEL` characters.

    Six levels of 120-character headings would exceed the citation contract's 400-character
    bound and make every later read of that conversation fail validation. Deep paths keep
    their innermost headings, which are the ones that locate the passage.
    """
    parts = list(path)
    label = SECTION_SEPARATOR.join(parts)
    while len(label) > MAX_SECTION_LABEL and len(parts) > 1:
        parts = parts[1:]
        label = "…" + SECTION_SEPARATOR + SECTION_SEPARATOR.join(parts)
    return label[:MAX_SECTION_LABEL]


def _heading_title(raw: str) -> str:
    title = _INLINE_LINK.sub(r"\1", raw or "")
    title = _INLINE_MARK.sub("", title)
    title = _SPACE.sub(" ", title).strip()
    return title[:120]


def split_text_sections(
    text: str, *, markdown: bool, passage_chars: int = CHUNK_CHARS
) -> list[TextSection]:
    """Split a text resource into addressable sections.

    Markdown headings (ATX `#` and one-line setext) open sections whose path is the heading
    stack. Text outside any heading — a plain .txt file, or a Markdown preamble — becomes
    numbered passages of about ``passage_chars`` split at paragraph boundaries. Fenced code
    is opaque: a `#` comment inside it is never a heading.
    """
    if markdown:
        text = _FRONT_MATTER.sub("", text, count=1)
    lines = text.split("\n")
    raw: list[tuple[list[str], int, list[str]]] = []
    stack: list[tuple[int, str]] = []
    current: list[str] = []
    current_path: list[str] = []
    current_level = 0
    fence: str | None = None

    def flush() -> None:
        if any(line.strip() for line in current):
            raw.append((list(current_path), current_level, list(current)))
        current.clear()

    index = 0
    while index < len(lines):
        line = lines[index]
        if markdown:
            opener = _FENCE.match(line)
            if fence is not None:
                current.append(line)
                if (
                    opener
                    and opener.group(1)[0] == fence[0]
                    and len(opener.group(1)) >= len(fence)
                    and not line.strip()[len(opener.group(1)) :].strip()
                ):
                    fence = None
                index += 1
                continue
            if opener:
                fence = opener.group(1)
                current.append(line)
                index += 1
                continue
            level = 0
            title = ""
            consumed = 1
            atx = _ATX.match(line)
            if atx:
                level, title = len(atx.group(1)), _heading_title(atx.group(2) or "")
            elif (
                line.strip()
                and index + 1 < len(lines)
                and _SETEXT.match(lines[index + 1])
                and not _BLOCK_START.match(line)
                and not line.startswith(("    ", "\t"))
                and (index == 0 or not lines[index - 1].strip())
            ):
                marker = lines[index + 1].strip()[0]
                level, title, consumed = (1 if marker == "=" else 2), _heading_title(line), 2
            if level and title:
                flush()
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, title))
                current_path = [entry[1] for entry in stack]
                current_level = level
                current.extend(lines[index : index + consumed])
                index += consumed
                continue
        current.append(line)
        index += 1
    flush()

    sections: list[TextSection] = []
    for path, level, body_lines in raw:
        body = _BLANKS.sub("\n\n", "\n".join(body_lines)).strip()
        if not body:
            continue
        if path:
            sections.append(TextSection(len(sections) + 1, path, level, body))
            continue
        for passage in _paragraph_groups(body, passage_chars):
            sections.append(TextSection(len(sections) + 1, [], 0, passage))
    return sections


def _paragraph_groups(text: str, limit: int) -> list[str]:
    """Greedy paragraph packing; a paragraph longer than ``limit`` is windowed on its own."""
    groups: list[str] = []
    current = ""
    for paragraph in (part.strip() for part in re.split(r"\n\s*\n", text)):
        if not paragraph:
            continue
        if len(paragraph) > limit:
            if current:
                groups.append(current)
                current = ""
            groups.extend(_windows(paragraph, limit, 0))
            continue
        if current and len(current) + 2 + len(paragraph) > limit:
            groups.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        groups.append(current)
    return groups


def chunk_text_resource(text: str, *, markdown: bool) -> tuple[list[dict], int]:
    """Chunks for a Markdown/plain-text resource plus its section count.

    Each chunk's retrieval text starts with "§ <heading path>" so both scorers see the
    section a passage belongs to (a paragraph under "Photosynthesis › Light reactions"
    rarely repeats those words itself). Citations strip that prefix from the excerpt.
    """
    sections = split_text_sections(text, markdown=markdown)
    chunks: list[dict] = []
    for section in sections:
        prefix = f"§ {section.label}\n" if section.path else ""
        for body in _paragraph_groups(section.body, CHUNK_CHARS):
            chunks.append(
                {
                    "chunk_index": len(chunks),
                    "page": section.ordinal,
                    "section": section.label,
                    "text": prefix + body,
                }
            )
    return chunks, len(sections)


def excerpt_text(text: str, section: str | None, limit: int = 420) -> str:
    """Learner-facing excerpt: whitespace-collapsed, without the retrieval-only § prefix or
    the section's own heading line (the citation already names the section)."""
    if section is not None:
        if text.startswith("§ "):
            text = text.split("\n", 1)[1] if "\n" in text else ""
        lines = text.split("\n")
        if lines and _ATX.match(lines[0]):
            lines = lines[1:]
        elif len(lines) > 1 and _SETEXT.match(lines[1]):
            lines = lines[2:]
        text = "\n".join(lines)
    return " ".join(text.split())[:limit]


def locator(hit: dict) -> str:
    """How an evidence block names its place in the source, for the model's prompt."""
    section = hit.get("section")
    if section is None:
        return f"PDF page {hit['page']}"
    if section:
        return f"§ {section}"
    return f"passage {hit['page']}"
