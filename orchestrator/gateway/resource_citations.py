"""Finalize learner-resource references without trusting model-authored destinations.

The model sees numbered evidence blocks, but only the gateway owns the corresponding resource
records. This module canonicalizes the model's small syntax variations and returns exactly the
records that are referenced in the finalized answer, renumbered by first appearance.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

_SELF_CHECK = re.compile(
    r"\s*(?:\*{0,2}[\[(]?\s*)?(?:citation check|self[- ]check)\s*\*{0,2}\s*:"
    r"(?=[^.!?。！？؟۔।॥։።፧｡]*(?:\[\s*R[1-9]\d*\s*\]|"
    r"\(\s*R[1-9]\d*\s*\)|\bR[1-9]\d*\b|based\s+on\s+R[1-9]\d*|citation\s+check))"
    r".*$",
    re.IGNORECASE | re.DOTALL,
)
_TERMINAL_AUDIT = re.compile(
    r"\s*(?:\*{0,2}[\[(]?\s*)?(?:citation check|self[- ]check)\s*\*{0,2}\s*:"
    r"\s*(?:all\s+(?:sources|citations|claims|references)\s+"
    r"(?:(?:are|were)\s+)?(?:cited|present|covered|included|supported|used)|"
    r"(?:the\s+)?(?:citation\s+check\s+)?(?:is\s+)?(?:complete|passed|done|ok(?:ay)?)|"
    r"yes)\s*[.!?。！？؟۔।॥։።፧｡]*\s*[\])]*\*{0,2}\s*$",
    re.IGNORECASE,
)
_REFERENCE = re.compile(
    r"\[\s*R([1-9]\d*)\s*\]|\(\s*R([1-9]\d*)\s*\)",
    re.IGNORECASE,
)
_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([,.;:!?\])])")
_MARKDOWN_LINE_PREFIX = re.compile(
    r"^[ \t]{0,3}(?:(?:#{1,6}|[-+*>]|\d+[.)])\s+)+", re.MULTILINE
)
_SENTENCE_END = re.compile(
    r'(?:[。！？؟۔।॥։።፧｡]+(?:["\'”’)\]]*)?|[.!?]+(?:["\'”’)\]]*)?(?=\s|$))'
)
_TERMINAL_PUNCTUATION = '.!?。！？؟۔।॥։።፧｡"\'”’)]'
_BARE_TERMINAL_REFERENCE = re.compile(
    rf"\s+\bR([1-9]\d*)\b(?=\s*[{re.escape(_TERMINAL_PUNCTUATION)}]*\s*$)",
    re.IGNORECASE,
)
_BASED_ON_SUFFIX = re.compile(
    rf"\s*,?\s*based\s+on\s+R([1-9]\d*)\b(?=\s*[{re.escape(_TERMINAL_PUNCTUATION)}]*\s*$)",
    re.IGNORECASE,
)
_BASED_ON_PREFIX = re.compile(r"^(\s*)based\s+on\s+R([1-9]\d*)\s*,?\s*", re.IGNORECASE)
_MARKDOWN_DECORATION = re.compile(r"[*_`~]")
_STOP_WORDS = {
    "about", "after", "again", "also", "and", "are", "because", "been", "before",
    "being", "between", "both", "but", "can", "could", "does", "each", "for", "from",
    "had", "has", "have", "how", "into", "its", "may", "more", "most", "not", "only",
    "other", "our", "out", "over", "same", "should", "some", "such", "than", "that",
    "the", "their", "then", "there", "these", "they", "this", "those", "through", "under",
    "use", "used", "using", "very", "was", "were", "what", "when", "where", "which",
    "while", "who", "will", "with", "would", "you", "your",
}
_CLAIM_MODIFIERS = {
    "all", "any", "both", "each", "every", "few", "many", "most", "neither",
    "never", "no", "none", "nor", "not", "only", "several", "some", "without",
}
_PROTECTED_MARKDOWN = (
    re.compile(
        r"^ {0,3}(?:`{3,}|~{3,})[^\n]*\n.*?^ {0,3}(?:`{3,}|~{3,})[ \t]*$",
        re.MULTILINE | re.DOTALL,
    ),
    re.compile(r"^ {0,3}(?:`{3,}|~{3,})[^\n]*(?:\n.*)?$", re.MULTILINE | re.DOTALL),
    re.compile(r"^(?:(?: {4}|\t).*?(?:\n|$))+", re.MULTILINE),
    re.compile(r"\[(?:[^\[\]\n]|\[[^\[\]\n]*\])*\]\[[^\]\n]+\]"),
    re.compile(
        r"^[ \t]{0,3}(?:(?:>[ \t]{0,3}|[-+*][ \t]+|\d+[.)][ \t]+))*"
        r"\[[^\]\n]+\]:[^\n]*$",
        re.MULTILINE,
    ),
    re.compile(r"\[(?:[^\[\]\n]|\[[^\[\]\n]*\])*\]\([^\n)]*\)"),
    re.compile(r"\\(?:\[\s*R[1-9]\d*\s*\]|\(\s*R[1-9]\d*\s*\))", re.IGNORECASE),
    re.compile(
        r"\\begin\{(equation\*?|alignat\*?|align\*?|gather\*?|CD)\}.*?"
        r"\\end\{\1\}",
        re.DOTALL,
    ),
    re.compile(r"\\begin\{(?:equation\*?|alignat\*?|align\*?|gather\*?|CD)\}.*$", re.DOTALL),
    re.compile(r"\$\$.*?\$\$|\$[^\n$]+\$|\\\(.*?\\\)|\\\[.*?\\\]", re.DOTALL),
    re.compile(r"\$\$.*$|\\\[.*$|\\\(.*$", re.DOTALL),
    re.compile(
        r"<(a|button|code|kbd|pre|samp|script|style|textarea)\b[^>]*>.*?</\1\s*>",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"<(?:a|button|code|kbd|pre|samp|script|style|textarea)\b[^>]*>.*$",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r'<([a-z][\w:-]*)\b[^>]*class\s*=\s*(["\'])[^"\']*\b(?:katex(?:-display)?|math-source)\b[^"\']*\2[^>]*>.*?</\1\s*>',
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r'<[a-z][\w:-]*\b[^>]*class\s*=\s*(["\'])[^"\']*\b(?:katex(?:-display)?|math-source)\b[^"\']*\1[^>]*>.*$',
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(r"<[^>\n]+>"),
)

_REFERENCE_DEFINITION = re.compile(
    r"^[ \t]{0,3}(?:(?:>[ \t]{0,3}|[-+*][ \t]+|\d+[.)][ \t]+))*"
    r"\[([^\]\n]+)\]:[^\n]*$",
    re.MULTILINE | re.IGNORECASE,
)


def _protect_inline_code(text: str, protect) -> str:
    """Protect CommonMark code spans, whose closing run must equal the opener length."""

    pieces: list[str] = []
    cursor = 0
    scan = 0
    while scan < len(text):
        if text[scan] != "`":
            scan += 1
            continue
        opener_end = scan + 1
        while opener_end < len(text) and text[opener_end] == "`":
            opener_end += 1
        opener_size = opener_end - scan
        closer = opener_end
        matched_end = None
        while closer < len(text):
            closer = text.find("`", closer)
            if closer < 0:
                break
            closer_end = closer + 1
            while closer_end < len(text) and text[closer_end] == "`":
                closer_end += 1
            if closer_end - closer == opener_size:
                matched_end = closer_end
                break
            closer = closer_end
        if matched_end is None:
            scan = opener_end
            continue
        pieces.append(text[cursor:scan])
        pieces.append(protect(text[scan:matched_end]))
        cursor = matched_end
        scan = matched_end
    pieces.append(text[cursor:])
    return "".join(pieces)


def _protect_markdown(text: str) -> tuple[str, list[tuple[str, str]]]:
    protected: list[tuple[str, str]] = []
    prefix = "\ufff0MUTA_REFERENCE_LITERAL_"
    while prefix in text:
        prefix += "X"
    def protect(literal: str) -> str:
        token = f"{prefix}{len(protected)}\ufff1"
        protected.append((token, literal))
        return token

    def replace(match: re.Match[str]) -> str:
        return protect(match.group(0))

    # Remove block code first, then scan exact-length inline code delimiters. This mirrors
    # CommonMark and accepts differing backtick runs inside a valid code span.
    for pattern in _PROTECTED_MARKDOWN[:3]:
        text = pattern.sub(replace, text)
    text = _protect_inline_code(text, protect)

    # A reference definition can turn citation-looking text into a model-owned external link.
    # Protect every full/collapsed/shortcut use of the defined label before citation parsing.
    labels = {match.group(1).strip() for match in _REFERENCE_DEFINITION.finditer(text)}
    text = _REFERENCE_DEFINITION.sub(replace, text)
    nested_label = r"(?:[^\[\]\n]|\[[^\[\]\n]*\])*"
    for label in labels:
        flexible_label = r"\s+".join(re.escape(part) for part in label.split())
        if not flexible_label:
            continue
        for usage in (
            re.compile(rf"\[{nested_label}\]\[\s*{flexible_label}\s*\]", re.IGNORECASE),
            re.compile(rf"\[\s*{flexible_label}\s*\]\[\]", re.IGNORECASE),
            re.compile(rf"\[\s*{flexible_label}\s*\]", re.IGNORECASE),
        ):
            text = usage.sub(replace, text)

    for pattern in _PROTECTED_MARKDOWN[3:]:
        text = pattern.sub(replace, text)
    return text, protected


def _sentence_ranges(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    start = 0
    for match in _SENTENCE_END.finditer(text):
        ranges.append((start, match.end()))
        start = match.end()
    if start < len(text):
        ranges.append((start, len(text)))
    return ranges


def _normalized_evidence(text: str) -> str:
    value = unicodedata.normalize("NFKC", _REFERENCE.sub("", str(text or ""))).lower()
    value = _MARKDOWN_LINE_PREFIX.sub("", value)
    value = _MARKDOWN_DECORATION.sub("", value)
    value = re.sub(r"\s+", " ", value)
    value = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", value).strip()
    return value.rstrip(_TERMINAL_PUNCTUATION).strip()


def _enough_evidence_units(text: str) -> bool:
    words = [word.lower() for word in _unicode_words(text)]
    meaningful = {
        word
        for word in words
        if word in _CLAIM_MODIFIERS or (len(word) > 2 and word not in _STOP_WORDS)
    }
    if len(meaningful) >= 3:
        return True
    # Match the browser's conservative no-space-script fallback without promoting short generic
    # English claims. A single long non-ASCII run yields at least three overlapping trigrams.
    return any(len(word) >= 5 and any(ord(character) > 127 for character in word) for word in words)


def _unicode_words(text: str) -> list[str]:
    r"""Tokenize letters/numbers with their combining marks, matching browser ``\p{M}``."""

    words: list[str] = []
    current: list[str] = []
    for character in text:
        category = unicodedata.category(character)
        if category[0] in {"L", "N"} or (current and (category[0] == "M" or character in "'’-")):
            current.append(character)
        elif current:
            words.append("".join(current))
            current = []
    if current:
        words.append("".join(current))
    return words


def _source_supports_claim(source: dict, claim: str) -> bool:
    if not _enough_evidence_units(claim):
        return False
    excerpt = str(source.get("excerpt") or "")
    return claim in {
        _normalized_evidence(excerpt[start:end]) for start, end in _sentence_ranges(excerpt)
    }


def _append_reference_to_sentence(sentence: str, number: int) -> str:
    offset = len(sentence)
    while offset and sentence[offset - 1] in _TERMINAL_PUNCTUATION:
        offset -= 1
    return sentence[:offset].rstrip() + f" [R{number}]" + sentence[offset:]


def _canonicalize_supported_bare_references(text: str, sources: Sequence[dict]) -> str:
    """Canonicalize only a terminal bare ``R#`` whose adjacent claim exactly matches its source.

    This accepts the small model's ``claim R3.`` variant without turning ordinary electronics
    prose such as ``resistor R1`` into a citation.
    """

    replacements: list[tuple[int, int, str]] = []
    for start, end in _sentence_ranges(text):
        sentence = text[start:end]
        phrase = _BASED_ON_PREFIX.search(sentence)
        phrase_number_group = 2
        if phrase is None:
            phrase = _BASED_ON_SUFFIX.search(sentence)
            phrase_number_group = 1
        if phrase is not None:
            number = int(phrase.group(phrase_number_group))
            cleaned = sentence[: phrase.start()] + sentence[phrase.end() :]
            cleaned = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", cleaned).lstrip()
            claim = _normalized_evidence(cleaned)
            if 1 <= number <= len(sources) and _source_supports_claim(
                sources[number - 1], claim
            ):
                cleaned = _append_reference_to_sentence(cleaned, number)
            # `based on R#` is always model citation machinery, never learner-facing prose.
            replacements.append((start, end, cleaned))
            continue
        match = _BARE_TERMINAL_REFERENCE.search(sentence)
        if match is None:
            continue
        number = int(match.group(1))
        if not 1 <= number <= len(sources):
            continue
        claim = _normalized_evidence(sentence[: match.start()] + sentence[match.end() :])
        if _source_supports_claim(sources[number - 1], claim):
            replacements.append((start + match.start(), start + match.end(), f" [R{number}]"))
    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]
    return text


def _add_exact_missing_references(text: str, sources: Sequence[dict]) -> str:
    present = {
        int(next(group for group in match.groups() if group is not None))
        for match in _REFERENCE.finditer(text)
    }
    claims = []
    for start, end in _sentence_ranges(text):
        citation_offset = end
        while citation_offset > start and text[citation_offset - 1] in _TERMINAL_PUNCTUATION:
            citation_offset -= 1
        claims.append((citation_offset, _normalized_evidence(text[start:end])))
    insertions: dict[int, list[int]] = {}
    for old_number, source in enumerate(sources, start=1):
        if old_number in present:
            continue
        evidence_sentences = {
            _normalized_evidence(str(source.get("excerpt") or "")[start:end])
            for start, end in _sentence_ranges(str(source.get("excerpt") or ""))
        }
        evidence_sentences = {
            sentence for sentence in evidence_sentences if _enough_evidence_units(sentence)
        }
        for citation_offset, claim in claims:
            if claim in evidence_sentences:
                insertions.setdefault(citation_offset, []).append(old_number)
                break
    for end in sorted(insertions, reverse=True):
        markers = "".join(f" [R{number}]" for number in insertions[end])
        text = text[:end] + markers + text[end:]
    return text


def finalize_resource_reply(
    reply: str, sources: Sequence[dict]
) -> tuple[str, list[dict]]:
    """Return canonical answer text plus only the server records it actually cites.

    Sparse references such as ``(R5)`` become sequential ``[R1]`` markers paired with the fifth
    server-owned record. Unknown numbers never become links. The source records are shallow-copied
    so callers can safely retain their original retrieval result for telemetry/debugging.
    """

    text, protected = _protect_markdown(str(reply or ""))
    text = _TERMINAL_AUDIT.sub(" ", text)
    text = _SELF_CHECK.sub(" ", text)
    text = _canonicalize_supported_bare_references(text, sources)
    text = _add_exact_missing_references(text, sources)
    old_to_new: dict[int, int] = {}
    cited: list[dict] = []

    def replace(match: re.Match[str]) -> str:
        raw = next(group for group in match.groups() if group is not None)
        old_number = int(raw)
        if not 1 <= old_number <= len(sources):
            return ""
        new_number = old_to_new.get(old_number)
        if new_number is None:
            new_number = len(cited) + 1
            old_to_new[old_number] = new_number
            cited.append(dict(sources[old_number - 1]))
        return f"[R{new_number}]"

    text = _REFERENCE.sub(replace, text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    for token, literal in reversed(protected):
        text = text.replace(token, literal)
    return text, cited


def retain_persisted_resource_sources(
    reply: str, sources: Sequence[dict], persisted: Sequence[dict]
) -> tuple[str, list[dict]]:
    """Remove or renumber canonical markers whose resource disappeared before persistence."""

    def key(source: dict) -> tuple[object, object, object]:
        return (source.get("resource_id"), source.get("page"), source.get("chunk_index"))

    persisted_by_key = {key(source): dict(source) for source in persisted}
    old_to_new: dict[int, int] = {}
    retained: list[dict] = []

    def replace(match: re.Match[str]) -> str:
        old_number = int(next(group for group in match.groups() if group is not None))
        if not 1 <= old_number <= len(sources):
            return ""
        record = persisted_by_key.get(key(sources[old_number - 1]))
        if record is None:
            return ""
        new_number = old_to_new.get(old_number)
        if new_number is None:
            new_number = len(retained) + 1
            old_to_new[old_number] = new_number
            retained.append(record)
        return f"[R{new_number}]"

    text, protected = _protect_markdown(str(reply or ""))
    text = _REFERENCE.sub(replace, text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", text)
    text = text.strip()
    for token, literal in reversed(protected):
        text = text.replace(token, literal)
    return text, retained
