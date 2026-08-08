"""RAG grounding: the chat path calls retrieval when an index is staged, and degrades to
model-alone (empty block) when it is not — the offline-first default.

Uses the offline HashingEmbedder so the whole loop is testable without a running embed server.
Production rebuilds the same corpus with `--embedder server` (bge) and runs the embed server.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.gateway.routes import _rag_block
from orchestrator.retrieval.embedder import HashingEmbedder
from orchestrator.retrieval.index import Retriever, build_index, load_chunks

CORPUS = Path(__file__).resolve().parents[2] / "corpus" / "chunks.jsonl"


@pytest.fixture
def staged_index(tmp_path, monkeypatch):
    chunks = load_chunks(CORPUS)
    out = tmp_path / "index"
    build_index(chunks, HashingEmbedder(), out)
    retriever = Retriever.open(out, HashingEmbedder())
    # _rag_block does `from orchestrator.retrieval.app import get_retriever` at call time, so
    # patching the module attribute redirects it to our offline retriever.
    monkeypatch.setattr("orchestrator.retrieval.app.get_retriever", lambda: retriever)
    return retriever


def test_corpus_is_well_formed():
    chunks = load_chunks(CORPUS)
    assert len(chunks) >= 20
    subjects = {c.subject for c in chunks}
    assert {"math", "physics", "chemistry", "biology"} <= subjects


def test_rag_block_grounds_on_a_staged_index(staged_index):
    block = _rag_block("quadratic formula roots and the discriminant")
    assert "reference-material" in block  # the delimited, injection-guarded wrapper
    assert "quadratic" in block.lower()
    assert "instructions" in block.lower()  # the "treat as data, not instructions" preamble


def test_rag_block_degrades_to_empty_without_an_index(monkeypatch):
    def _no_index():
        raise FileNotFoundError("no index staged")

    monkeypatch.setattr("orchestrator.retrieval.app.get_retriever", _no_index)
    assert _rag_block("anything at all") == ""


# NB: off-topic filtering is a property of the *embedder*, not this wiring — the offline
# HashingEmbedder is deliberately noisy (its own docstring), so a "football beats biology to
# the relevance floor" test would assert bge quality the test double cannot emulate. The
# relevance floor and delimiting are exercised above; retrieval quality is a corpus/embedder
# concern measured separately with the real bge model.
