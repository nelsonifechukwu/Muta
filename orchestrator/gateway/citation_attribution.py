"""Attribute unmarked claims in a grounded reply to the passages the model was shown.

The tutor prompt requires an inline [R#] after every supported sentence, but the bundled
1.5B model usually answers correctly from the evidence and writes no marker. This pass runs
after generation: each factual sentence or list item without a marker is compared with the
passages in the prompt, and gets the number of the passage that clearly supports it. A
sentence no passage supports stays unmarked; inventing a citation is worse than none.

Support needs both signals when bge is available: cosine similarity between the sentence and
the passage, and lexical coverage (the share of the sentence's content words found in the
passage). Thresholds were set on real answers over the 68-page reference PDF
(docs/rag-resources.md, "Inline citations").
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Callable, Sequence

from orchestrator.gateway.resource_citations import _protect_markdown

Embed = Callable[[list[str]], list[list[float]]]

_REFERENCE = re.compile(r"\[\s*R[1-9]\d*\s*\]|\(\s*R[1-9]\d*\s*\)", re.IGNORECASE)
_SENTENCE_END = re.compile(r'[.!?。！？؟۔।॥։።፧｡]+["\'”’)\]]*(?=\s|$)')
#: Stepped back over when placing a marker: sentence punctuation only, so "(LLMs)." becomes
#: "(LLMs) [R1]." rather than "(LLMs [R1])." and a closing quote or bracket stays intact.
_TERMINAL = ".!?。！？؟۔।॥։።፧｡:;"
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_LIST_PREFIX = re.compile(r"^\s{0,3}(?:[-+*]|\d+[.)])\s+")
_DECORATION = re.compile(r"[*_`~]")
_PROTECTED_TOKEN = re.compile("\ufff0[^\ufff1]*\ufff1")
_STOP = frozenset(
    [
        "a",
        "about",
        "after",
        "again",
        "also",
        "am",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "both",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "doing",
        "each",
        "for",
        "from",
        "had",
        "has",
        "have",
        "having",
        "he",
        "her",
        "here",
        "hers",
        "him",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "itself",
        "just",
        "let",
        "like",
        "make",
        "makes",
        "me",
        "more",
        "most",
        "my",
        "no",
        "nor",
        "not",
        "now",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "our",
        "out",
        "over",
        "own",
        "same",
        "she",
        "should",
        "so",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "very",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
        "yours",
        "example",
        "examples",
        "step",
        "steps",
        "first",
        "second",
        "third",
        "next",
        "finally",
        "also",
        "use",
        "used",
        "using",
        "way",
        "ways",
        "help",
        "helps",
    ]
)
#: Minimum content words for a span to count as a claim worth citing.
_MIN_CLAIM_WORDS = 4
#: Semantic route (bge cosine). Unrelated prose still scores ~0.5 with bge-small, hence the high
#: bar plus a lexical floor so a fluent paraphrase of nothing in particular is not cited.
_MIN_COSINE = 0.70
_MIN_COVERAGE_WITH_COSINE = 0.30
#: Lexical-only route (no embedder): most of the sentence's content words appear in the passage.
_MIN_COVERAGE_ALONE = 0.60


def _content_words(text: str) -> set[str]:
    words = set()
    for word in _WORD.findall(unicodedata.normalize("NFKC", text).lower()):
        if len(word) < 3 or word in _STOP:
            continue
        # Light stemming: "prompts" ≈ "prompt", "models" ≈ "model".
        if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        words.add(word)
    return words


def _claim_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) of each sentence or list item that could carry a citation."""
    spans: list[tuple[int, int]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        stripped = body.strip()
        line_start = offset
        offset += len(line)
        if (
            not stripped
            or stripped.startswith(("#", "|", ">", "```", "~~~", "$$", "\\["))
            or set(stripped) <= set("-*_=|: ")
        ):
            continue
        prefix = _LIST_PREFIX.match(body)
        start = line_start + (prefix.end() if prefix else 0)
        cursor = start
        for match in _SENTENCE_END.finditer(text, start, line_start + len(body)):
            spans.append((cursor, match.end()))
            cursor = match.end()
        if cursor < line_start + len(body):
            spans.append((cursor, line_start + len(body)))
    return spans


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


def attribute_claims(reply: str, passages: Sequence[str], *, embed: Embed | None = None) -> str:
    """Return ``reply`` with [R#] added to unmarked claims a shown passage supports.

    ``passages[i]`` is evidence block R(i+1) exactly as the model saw it. Existing markers are
    kept; code, maths and links stay untouched (protected before segmentation).
    """
    if not reply or not passages:
        return reply
    protected, literals = _protect_markdown(str(reply))
    candidates: list[tuple[int, int, set[str], str]] = []
    for start, end in _claim_spans(protected):
        span = protected[start:end]
        if _REFERENCE.search(span):
            continue
        # Protected code/maths/link tokens are not words of the claim.
        plain = _DECORATION.sub("", _PROTECTED_TOKEN.sub(" ", span)).strip()
        if plain.endswith(("?", ":")):
            continue
        words = _content_words(plain)
        if len(words) < _MIN_CLAIM_WORDS:
            continue
        candidates.append((start, end, words, plain))
    if not candidates:
        return reply

    passage_words = [_content_words(passage) for passage in passages]
    cosines: list[list[float]] | None = None
    if embed is not None:
        try:
            vectors = embed([plain for *_rest, plain in candidates] + list(passages))
            if len(vectors) == len(candidates) + len(passages):
                claim_vectors, passage_vectors = (
                    vectors[: len(candidates)],
                    vectors[len(candidates) :],
                )
                cosines = [
                    [_cosine(claim, passage) for passage in passage_vectors]
                    for claim in claim_vectors
                ]
        except Exception:  # noqa: BLE001 — attribution degrades to the lexical route
            cosines = None

    insertions: list[tuple[int, int]] = []
    for index, (start, end, words, _plain) in enumerate(candidates):
        best_number = 0
        best_score = 0.0
        for number, vocabulary in enumerate(passage_words, start=1):
            coverage = len(words & vocabulary) / len(words)
            if cosines is not None:
                cosine = cosines[index][number - 1]
                if cosine < _MIN_COSINE or coverage < _MIN_COVERAGE_WITH_COSINE:
                    continue
                score = cosine + 0.5 * coverage
            else:
                if coverage < _MIN_COVERAGE_ALONE:
                    continue
                score = coverage
            if score > best_score:
                best_number, best_score = number, score
        if best_number:
            offset = end
            while offset > start and protected[offset - 1] in _TERMINAL + " \t":
                offset -= 1
            insertions.append((offset, best_number))

    if not insertions:
        return reply
    for offset, number in sorted(insertions, reverse=True):
        protected = protected[:offset] + f" [R{number}]" + protected[offset:]
    for token, literal in reversed(literals):
        protected = protected.replace(token, literal)
    return protected
