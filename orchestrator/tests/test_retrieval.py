"""Retrieval tests (TDD §6.7, T11).

Scope note, stated up front because it is easy to over-claim: these tests exercise the
*plumbing* — chunking, vectors, top-k, persistence, the embedder-identity guard — using a
deterministic hashing embedder. Retrieval **quality** is a property of bge-small and the real
corpus, and its acceptance number (top-3 recall ≥ 90% on 50 seeded queries against the real
index) belongs to bench week with the embed server running. What is checked here is that a
correct embedder would be correctly served.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from orchestrator.retrieval.embedder import HashingEmbedder, ServerEmbedder, normalize
from orchestrator.retrieval.index import (
    Chunk,
    ChunkStore,
    FlatIndex,
    IndexMismatch,
    Retriever,
    build_index,
    load_chunks,
    main,
)

pytest.importorskip("numpy", reason="the index is vectors")

TOPICS = [
    ("quadratic", "Solve quadratic equations by factorising, completing the square, or the formula."),
    ("simultaneous", "Simultaneous linear equations are solved by substitution or elimination."),
    ("indices", "Laws of indices: multiply powers by adding exponents, divide by subtracting."),
    ("logarithms", "Logarithms convert products to sums; log of a product equals the sum of logs."),
    ("surds", "Surds are irrational roots; rationalise the denominator to simplify them."),
    ("trigonometry", "Sine, cosine and tangent ratios relate angles to sides in right triangles."),
    ("bearings", "Bearings are measured clockwise from north as three-figure angles."),
    ("mensuration", "Mensuration covers area, perimeter and volume of common solids."),
    ("statistics", "Mean, median and mode summarise a distribution of marks."),
    ("probability", "Probability of independent events multiplies; mutually exclusive events add."),
    ("vectors", "Vectors have magnitude and direction and add by the triangle rule."),
    ("matrices", "Matrix multiplication is row by column; the determinant decides invertibility."),
    ("calculus", "Differentiation gives the gradient function; integration reverses it."),
    ("sequences", "Arithmetic sequences add a common difference; geometric sequences multiply."),
    ("geometry", "Angles in a triangle sum to 180 degrees and in a quadrilateral to 360."),
]


def corpus() -> list[Chunk]:
    chunks: list[Chunk] = []
    for topic, sentence in TOPICS:
        for i in range(4):  # four chunks per topic: retrieval has to discriminate within a doc
            chunks.append(
                Chunk(
                    doc_id=f"waec-{topic}",
                    chunk_id=i,
                    text=f"{sentence} Worked example {i + 1} on {topic}.",
                    subject="math",
                )
            )
    return chunks


@pytest.fixture
def built(tmp_path):
    embedder = HashingEmbedder()
    index = build_index(corpus(), embedder, tmp_path / "index")
    return tmp_path / "index", embedder, index


# --- store and index ---------------------------------------------------------------------


def test_store_round_trips_chunks(tmp_path):
    store = ChunkStore(tmp_path / "chunks.sqlite")
    assert store.add_all(corpus()) == 60
    assert len(store) == 60
    first = store.get(0)
    assert first is not None and first.doc_id.startswith("waec-") and first.key.endswith(":0")
    assert store.get(9999) is None


def test_index_persists_and_reloads(built):
    directory, embedder, index = built
    reloaded = FlatIndex.load(directory)
    assert len(reloaded) == len(index) == 60
    assert reloaded.embedder_identity == embedder.identity
    assert json.loads((directory / "index.json").read_text())["count"] == 60


def test_search_finds_the_right_topic(built):
    directory, embedder, _ = built
    retriever = Retriever.open(directory, embedder)
    hits = retriever.search("how do I solve a quadratic by completing the square", k=3)
    assert hits and hits[0].doc_id == "waec-quadratic"
    assert hits[0].score > 0


def test_top_3_recall_over_seeded_queries(built):
    """T11's shape: 50 seeded queries, recall@3 ≥ 90%.

    Read the number carefully. The embedder here is lexical, so this measures the retrieval
    *path* (embed → top-k → chunk lookup) against queries that carry the target's distinctive
    vocabulary, which is what a student's question usually does. It is NOT bge-small's recall
    on the real corpus — that measurement needs the embed server and belongs to bench week,
    and it is the one that counts for acceptance.
    """
    directory, embedder, _ = built
    retriever = Retriever.open(directory, embedder)

    queries: list[tuple[str, str]] = []
    for topic, sentence in TOPICS:
        content = [w.strip(".,;:").lower() for w in sentence.split() if len(w) > 5]
        for phrasing in (
            f"{topic} {content[0]}",
            f"how do I do {topic} {content[1] if len(content) > 1 else content[0]}",
            " ".join(content[:3]),
            f"{topic} worked example",
        ):
            queries.append((phrasing, f"waec-{topic}"))
    queries = queries[:50]
    assert len(queries) == 50

    missed = [q for q, doc in queries if doc not in {h.doc_id for h in retriever.search(q, k=3)}]
    recall = 1 - len(missed) / len(queries)
    assert recall >= 0.9, f"recall@3 = {recall:.0%}, missed: {missed}"


def test_results_are_ordered_by_score(built):
    directory, embedder, _ = built
    hits = Retriever.open(directory, embedder).search("probability of independent events", k=5)
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_min_score_filters_weak_matches(built):
    directory, embedder, _ = built
    retriever = Retriever.open(directory, embedder)
    assert retriever.search("bearings measured clockwise", k=5, min_score=0.99) == []


def test_empty_query_returns_nothing(built):
    directory, embedder, _ = built
    assert Retriever.open(directory, embedder).search("   ") == []


def test_k_larger_than_the_corpus_is_not_an_error(tmp_path):
    embedder = HashingEmbedder()
    build_index(corpus()[:2], embedder, tmp_path / "small")
    assert len(Retriever.open(tmp_path / "small", embedder).search("quadratic", k=50)) == 2


def test_an_empty_corpus_still_produces_a_loadable_index(tmp_path):
    embedder = HashingEmbedder()
    build_index([], embedder, tmp_path / "empty")
    assert Retriever.open(tmp_path / "empty", embedder).search("anything") == []


# --- the invariant -----------------------------------------------------------------------


def test_querying_with_a_different_embedder_is_refused(built):
    """An index built by one model and queried by another returns plausible nonsense — no
    error, no crash, just worse retrieval that reads as the model being dim."""
    directory, _, _ = built
    with pytest.raises(IndexMismatch, match="plausible nonsense"):
        Retriever.open(directory, ServerEmbedder())


def test_hashing_embedder_declares_itself_in_the_index(built):
    directory, _, _ = built
    assert json.loads((directory / "index.json").read_text())["embedder"] == HashingEmbedder().identity


def test_vectors_are_unit_length_so_inner_product_is_cosine():
    (vector,) = HashingEmbedder().embed(["quadratic equations"])
    assert sum(x * x for x in vector) == pytest.approx(1.0, abs=1e-6)
    assert normalize([0.0, 0.0]) == [0.0, 0.0]  # a zero vector must not divide by zero


# --- corpus io and CLI --------------------------------------------------------------------


def test_load_chunks_reads_the_corpus_lane_format(tmp_path):
    path = tmp_path / "chunks.jsonl"
    path.write_text(
        json.dumps({"doc_id": "d", "chunk_id": 0, "text": "hello", "subject": "physics"}) + "\n\n"
        + json.dumps({"doc_id": "d", "text": "world"}) + "\n"
    )
    chunks = load_chunks(path)
    assert [c.subject for c in chunks] == ["physics", "math"]
    assert chunks[1].chunk_id == 1  # missing chunk_id falls back to position


def test_cli_build_then_search(tmp_path, capsys):
    corpus_path = tmp_path / "chunks.jsonl"
    corpus_path.write_text(
        "\n".join(json.dumps({"doc_id": c.doc_id, "chunk_id": c.chunk_id, "text": c.text}) for c in corpus())
    )
    out = tmp_path / "index"
    assert main(["build", "--corpus", str(corpus_path), "--out", str(out), "--embedder", "hashing"]) == 0
    assert main(["search", "--index", str(out), "--query", "logarithms", "--embedder", "hashing"]) == 0
    printed = capsys.readouterr().out
    assert "waec-logarithms" in printed


def test_cli_search_refuses_a_mismatched_embedder(tmp_path, capsys):
    corpus_path = tmp_path / "chunks.jsonl"
    corpus_path.write_text(json.dumps({"doc_id": "d", "chunk_id": 0, "text": "x"}))
    out = tmp_path / "index"
    main(["build", "--corpus", str(corpus_path), "--out", str(out), "--embedder", "hashing"])
    # No --embedder: defaults to the server embedder, which did not build this index.
    assert main(["search", "--index", str(out), "--query", "x"]) == 1
    assert "refused" in capsys.readouterr().err


# --- service -----------------------------------------------------------------------------


def test_service_returns_503_when_no_index_is_staged(tmp_path, monkeypatch):
    """RAG off is not RAG empty: an empty result set reads as "that topic is not in the
    syllabus", which is a different and worse lie."""
    from orchestrator.retrieval import app as retrieval_app

    retrieval_app.get_retriever.cache_clear()
    monkeypatch.setenv("TUTOR_INDEX_DIR", str(tmp_path / "absent"))
    client = TestClient(retrieval_app.app)
    response = client.post("/search", json={"query": "quadratics"})
    assert response.status_code == 503 and "no index" in response.json()["detail"]
    retrieval_app.get_retriever.cache_clear()


def test_service_search_shape(tmp_path, monkeypatch, built):
    from orchestrator.retrieval import app as retrieval_app

    directory, embedder, _ = built
    retrieval_app.get_retriever.cache_clear()
    monkeypatch.setattr(retrieval_app, "get_retriever", lambda: Retriever.open(directory, embedder))
    client = TestClient(retrieval_app.app)
    body = client.post("/search", json={"query": "matrices determinant", "k": 3}).json()
    assert len(body["hits"]) == 3
    assert body["hits"][0]["cite"].startswith("[waec-")
    assert body["backend"] in ("faiss", "numpy")
