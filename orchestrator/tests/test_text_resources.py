"""Markdown/plain-text resources, cleaner PDF chunks, and degraded retrieval (2026-10-09)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from orchestrator.gateway import deps, routes
from orchestrator.main import app
from orchestrator.retrieval.documents import (
    CHUNKER_VERSION,
    chunk_text_resource,
    classify_upload,
    clean_pdf_pages,
    decode_text,
    is_contents_page,
    split_text_sections,
    wants_overview,
)
from orchestrator.retrieval.embedder import HashingEmbedder
from orchestrator.retrieval.resources import ResourceService
from runtime.memory import ConversationStore

NOTES = """---
title: Physics notes
---
These notes cover forces and energy for the term.

# Unit 1: Forces

A force is a push or a pull.

```python
# a comment, not a heading
force = mass * acceleration
```

## Newton's laws

An object stays at rest or keeps moving at constant velocity unless a net force acts on it.

# Unit 2: Energy

Kinetic energy is the energy of motion.
"""


class _Engine:
    def __init__(self, store) -> None:
        self.store = store


def _client(store, service):
    app.dependency_overrides[deps.get_engine] = lambda: _Engine(store)
    app.dependency_overrides[deps.get_resource_service] = lambda: service
    return TestClient(app)


def test_markdown_sections_follow_headings_and_ignore_code_comments():
    sections = split_text_sections(NOTES, markdown=True)
    labels = [section.label for section in sections]
    assert labels == ["", "Unit 1: Forces", "Unit 1: Forces › Newton's laws", "Unit 2: Energy"]
    assert "title: Physics notes" not in sections[0].body
    chunks, count = chunk_text_resource(NOTES, markdown=True)
    assert count == 4
    newton = next(chunk for chunk in chunks if "constant velocity" in chunk["text"])
    assert newton["page"] == 3 and newton["section"] == "Unit 1: Forces › Newton's laws"
    assert newton["text"].startswith("§ Unit 1: Forces › Newton's laws\n")


def test_plain_text_becomes_numbered_passages():
    text = "\n\n".join(f"Paragraph {index} " + "word " * 60 for index in range(12))
    sections = split_text_sections(text, markdown=False)
    assert len(sections) > 1 and all(section.path == [] for section in sections)
    assert [section.ordinal for section in sections] == list(range(1, len(sections) + 1))


def test_uploads_are_classified_by_bytes_and_name_and_must_be_utf8():
    assert classify_upload("notes.md", "application/octet-stream", b"# Hi") == "text/markdown"
    assert classify_upload("notes.txt", "", b"hello") == "text/plain"
    assert classify_upload("renamed.md", "text/markdown", b"%PDF-1.7") == "application/pdf"
    assert classify_upload("report.docx", "application/octet-stream", b"PK\x03\x04") is None
    assert decode_text("﻿café\r\nline".encode()) == "café\nline"
    for bad in (b"\xff\xfe\x00h", "café".encode("latin-1")):
        try:
            decode_text(bad)
        except ValueError:
            continue
        raise AssertionError("non-UTF-8 or binary text must be refused")


def test_running_headers_footers_and_page_numbers_are_removed():
    topics = ["force", "energy", "motion", "power", "waves", "light", "heat"]
    pages = [
        f"Physics Handbook\n{topic.title()} is introduced on this page.\n"
        f"Worked example about {topic}.\nSchool Edition · {number}"
        for number, topic in enumerate(topics, start=1)
    ]
    cleaned = clean_pdf_pages(pages)
    assert all("Physics Handbook" not in page and "School Edition" not in page for page in cleaned)
    assert cleaned[1] == "Energy is introduced on this page.\nWorked example about energy."


def test_contents_pages_and_overview_questions_are_recognised():
    contents = "Contents\nIntroduction ........ 1\nForces ....... 4\nEnergy ...... 9\nWaves 14"
    assert is_contents_page(contents)
    assert not is_contents_page("Kinetic energy is the energy of motion, measured in joules.")
    assert wants_overview("Can you summarise this PDF?")
    assert wants_overview("What is this document about?")
    assert not wants_overview("What is kinetic energy?")


def test_markdown_upload_prepares_sections_and_cites_them(tmp_path):
    store = ConversationStore(f"sqlite:///{tmp_path / 'notes.sqlite3'}")
    service = ResourceService(store, workers=1, resume_pending=False)
    client = _client(store, service)
    try:
        uploaded = client.post(
            "/v1/resources",
            headers={"Authorization": "Bearer a"},
            files={"file": ("physics notes.md", NOTES.encode(), "text/markdown")},
        )
        resource_id = uploaded.json()["id"]
        service.prepare_now(resource_id, "a")
        listed = client.get("/v1/resources", headers={"Authorization": "Bearer a"}).json()
        sections = client.get(
            f"/v1/resources/{resource_id}/sections", headers={"Authorization": "Bearer a"}
        )
        content = client.get(
            f"/v1/resources/{resource_id}/content", headers={"Authorization": "Bearer a"}
        )
        hits = service.search("a", [resource_id], "What does Newton's first law say?")
        rendered = service.render_context(hits, [{"name": "physics notes.md"}])
    finally:
        app.dependency_overrides.clear()
        service.shutdown()
        store.close()

    assert uploaded.status_code == 202 and uploaded.json()["mime"] == "text/markdown"
    resource = listed["resources"][0]
    assert resource["status"] == "ready" and resource["page_count"] == 4
    assert sections.status_code == 200
    body = sections.json()
    assert [section["ordinal"] for section in body["sections"]] == [1, 2, 3, 4]
    assert body["sections"][2]["path"] == ["Unit 1: Forces", "Newton's laws"]
    assert content.headers["content-type"].startswith("text/plain")
    assert content.headers["x-content-type-options"] == "nosniff"
    assert hits[0]["section"] == "Unit 1: Forces › Newton's laws" and hits[0]["page"] == 3
    assert not hits[0]["excerpt"].startswith("§")
    assert "[R1] physics notes.md, § Unit 1: Forces › Newton's laws" in rendered


def test_unsupported_and_invalid_text_uploads_are_refused(tmp_path):
    store = ConversationStore(f"sqlite:///{tmp_path / 'refuse.sqlite3'}")
    service = ResourceService(store, workers=1, resume_pending=False)
    client = _client(store, service)
    headers = {"Authorization": "Bearer a"}
    try:
        docx = client.post(
            "/v1/resources",
            headers=headers,
            files={"file": ("essay.docx", b"PK\x03\x04", "application/octet-stream")},
        )
        latin = client.post(
            "/v1/resources",
            headers=headers,
            files={"file": ("notes.txt", "café".encode("latin-1"), "text/plain")},
        )
        image = client.post(
            "/v1/resources", headers=headers, files={"file": ("a.png", b"\x89PNG", "image/png")}
        )
        pdf_sections = client.get(
            f"/v1/resources/{store.create_resource('a', 'b.pdf', 'application/pdf', b'%PDF-')}"
            "/sections",
            headers=headers,
        )
    finally:
        app.dependency_overrides.clear()
        service.shutdown()
        store.close()
    assert docx.status_code == 422
    assert latin.status_code == 422 and "UTF-8" in latin.json()["detail"]
    assert image.status_code == 415
    assert pdf_sections.status_code == 409


class _BrokenEmbedder:
    identity = "server:bge-small-en-v1.5-q8_0"
    dimensions = 384

    def __init__(self) -> None:
        self.working = False

    def embed(self, texts):
        if not self.working:
            raise RuntimeError("sidecar down")
        return HashingEmbedder(dimensions=384).embed(texts)


def test_retrieval_degrades_to_lexical_scoring_when_bge_is_unavailable(tmp_path):
    store = ConversationStore(f"sqlite:///{tmp_path / 'degraded.sqlite3'}")
    embedder = _BrokenEmbedder()
    service = ResourceService(store, embedder=embedder, workers=1, resume_pending=False)
    resource_id = store.create_resource("a", "notes.md", "text/markdown", NOTES.encode())
    try:
        service.prepare_now(resource_id, "a")
        row = store.get_resource(resource_id, owner_id="a")
        hits = service.search("a", [resource_id], "kinetic energy motion")
        # The resource stays usable and is queued for a bge re-index once the sidecar works.
        stale = store.list_stale_resources(service.index_identity)
        embedder.working = True
        service.prepare_now(resource_id, "a")
        upgraded = store.get_resource(resource_id, owner_id="a")
    finally:
        service.shutdown()
        store.close()
    assert row["status"] == "ready"
    assert row["embedder_identity"] == f"hashing:384+{CHUNKER_VERSION}"
    assert hits and hits[0]["section"] == "Unit 2: Energy"
    assert [item["id"] for item in stale] == [resource_id]
    assert upgraded["embedder_identity"] == service.index_identity


def test_overview_questions_draw_from_the_whole_document(tmp_path):
    store = ConversationStore(f"sqlite:///{tmp_path / 'overview.sqlite3'}")
    service = ResourceService(store, workers=1, resume_pending=False)
    chapters = "\n\n".join(
        f"# Chapter {number}\n\n" + f"Chapter {number} explains topic {number}. " * 30
        for number in range(1, 13)
    )
    resource_id = store.create_resource("a", "book.md", "text/markdown", chapters.encode())
    try:
        service.prepare_now(resource_id, "a")
        hits = service.search("a", [resource_id], "Summarise this book for me")
        # Fitting keeps the highest priorities (introduction, conclusion, spread) and then
        # presents the survivors in reading order.
        fitted = service.fit_evidence(hits, 2400)
        hits = service.fit_evidence(hits, None)
    finally:
        service.shutdown()
        store.close()
    sections = [hit["section"] for hit in hits]
    assert sections[0] == "Chapter 1" and sections[-1] == "Chapter 12"
    assert len(set(sections)) >= 4
    assert [hit["chunk_index"] for hit in hits] == sorted(hit["chunk_index"] for hit in hits)
    assert [hit["section"] for hit in fitted][:1] == ["Chapter 1"]
    assert "Chapter 12" in [hit["section"] for hit in fitted]
    assert [hit["chunk_index"] for hit in fitted] == sorted(hit["chunk_index"] for hit in fitted)


def test_overview_citations_follow_the_prompt_reading_order(tmp_path, monkeypatch):
    store = ConversationStore(f"sqlite:///{tmp_path / 'overview-citations.sqlite3'}")
    service = ResourceService(store, workers=1, resume_pending=False)
    chapters = "\n\n".join(
        f"# Chapter {number}\n\n" + f"Chapter {number} covers lesson {number}. " * 20
        for number in range(1, 9)
    )
    resource_id = store.create_resource("a", "book.md", "text/markdown", chapters.encode())

    class RoomyEngine:
        image_token_budget = 0

        @staticmethod
        def prompt_room_tokens(*_args, **_kwargs):
            return None

    try:
        service.prepare_now(resource_id, "a")
        hits = service.search("a", [resource_id], "Summarise this book")
        shown = service.fit_evidence(hits, None)
        assert [hit["chunk_index"] for hit in hits] != [hit["chunk_index"] for hit in shown]
        monkeypatch.setattr(routes, "get_resource_service", lambda: service)
        prompt, citations, _ = routes._grounded_system_prompt(
            lambda context: context,
            routes._ResourceEvidence(hits=hits, selected=service.preflight("a", [resource_id])),
            engine=RoomyEngine(),
            user_text="Summarise this book",
            params={},
        )
    finally:
        service.shutdown()
        store.close()

    assert [source["chunk_index"] for source in citations] == [
        hit["chunk_index"] for hit in shown
    ]
    for index, source in enumerate(citations, 1):
        assert f"[R{index}] book.md" in prompt
        assert source["section"] == shown[index - 1]["section"]


def test_deep_heading_paths_still_validate_as_citations():
    """Review finding: six levels of long headings made a >400-char label, and the stored
    citation then failed validation on every later load of the conversation (HTTP 500)."""
    from contracts.models import ResourceCitation

    deep = (
        "\n\n".join(
            f"{'#' * level} {'Very long heading words ' * 4}{level}" for level in range(1, 7)
        )
        + "\n\nThe passage text."
    )
    chunks, _count = chunk_text_resource(deep, markdown=True)
    label = chunks[-1]["section"]
    assert len(label) <= 240 and label.endswith("6")
    ResourceCitation(
        resource_id="a" * 32, title="t.md", page=1, chunk_index=0, excerpt="x", section=label
    )


def test_a_hashing_indexed_file_is_not_hidden_by_bge_scores(tmp_path):
    """Review finding: the semantic window, computed from bge cosines, removed an exact
    lexical match from a file still on the hashing index."""
    from orchestrator.retrieval.embedder import normalize

    class _Bge:
        identity = "server:bge-small-en-v1.5-q8_0"
        dimensions = 384

        def embed(self, texts):
            return [normalize([1.0, 0.5, 0.2] + [0.0] * 381) for _ in texts]

    store = ConversationStore(f"sqlite:///{tmp_path / 'mixed.sqlite3'}")
    bge, hashing = _Bge(), HashingEmbedder(dimensions=384)
    service = ResourceService(store, embedder=bge, fallback_embedder=hashing, resume_pending=False)
    physics = store.create_resource("a", "physics.pdf", "application/pdf", b"%PDF-")
    chemistry = store.create_resource("a", "chem.pdf", "application/pdf", b"%PDF-")
    store.replace_resource_chunks(
        physics,
        owner_id="a",
        chunks=[
            {
                "chunk_index": 0,
                "page": 1,
                "text": "Velocity describes motion.",
                "embedding": bge.embed(["x"])[0],
            }
        ],
        page_count=1,
        embedder_identity=service.index_identity,
    )
    text = "Titration measures acid concentration with an indicator."
    store.replace_resource_chunks(
        chemistry,
        owner_id="a",
        chunks=[{"chunk_index": 0, "page": 1, "text": text, "embedding": hashing.embed([text])[0]}],
        page_count=1,
        embedder_identity=f"{hashing.identity}+{CHUNKER_VERSION}",
    )
    try:
        hits = service.search("a", [physics, chemistry], "How does titration measure acid?")
    finally:
        service.shutdown()
        store.close()
    assert "chem.pdf" in [hit["title"] for hit in hits[:2]]


def test_overviews_of_several_files_cover_each_file_within_a_small_budget(tmp_path):
    store = ConversationStore(f"sqlite:///{tmp_path / 'multi.sqlite3'}")
    service = ResourceService(store, workers=1, resume_pending=False)
    ids = []
    for name in ("biology.md", "chemistry.md"):
        body = "\n\n".join(
            f"# {name} chapter {n}\n\n" + f"{name} chapter {n} content. " * 25 for n in range(8)
        )
        ids.append(store.create_resource("a", name, "text/markdown", body.encode()))
    try:
        for resource_id in ids:
            service.prepare_now(resource_id, "a")
        hits = service.search("a", ids, "Give me an overview of these notes")
        fitted = service.fit_evidence(hits, 2600)
    finally:
        service.shutdown()
        store.close()
    assert {hit["title"] for hit in fitted} == {"biology.md", "chemistry.md"}


def test_refresh_never_downgrades_a_semantic_index_to_hashing(tmp_path):
    store = ConversationStore(f"sqlite:///{tmp_path / 'refresh.sqlite3'}")
    service = ResourceService(store, workers=1, resume_pending=False)  # hashing primary
    try:
        assert not service._worth_refreshing("server:bge-small-en-v1.5-q8_0+chunks-v2")
        assert service._worth_refreshing("hashing:384")
        assert not service._worth_refreshing(service.index_identity)
    finally:
        service.shutdown()
        store.close()


def test_model_planning_reads_each_gguf_header_once(tmp_path, monkeypatch):
    """Regression: `/v1/models` re-parsed every installed GGUF header (~185 ms each) on
    every page load, so returning from the About page showed "Loading models…" for ~3 s."""
    from orchestrator.gateway import capacity

    model = tmp_path / "m.gguf"
    model.write_bytes(b"GGUF")
    calls = []

    class _Md:
        pass

    monkeypatch.setattr(capacity, "read_metadata", lambda path: calls.append(path) or _Md())
    monkeypatch.setattr(
        capacity.KVCost, "from_metadata",
        classmethod(lambda cls, md, k, v: type("C", (), {"bytes_per_token": 1024})()),
    )
    monkeypatch.setattr(capacity.RecurrentStateCost, "from_metadata", staticmethod(lambda md: None))
    capacity._MODEL_COST_CACHE.clear()
    assert capacity._model_costs(model, "q8_0") == (1024.0, 0)
    assert capacity._model_costs(model, "q8_0") == (1024.0, 0)
    assert len(calls) == 1
    model.write_bytes(b"GGUF-replaced")  # a re-exported file is parsed again
    capacity._model_costs(model, "q8_0")
    assert len(calls) == 2


def test_claim_attribution_is_conservative_and_leaves_code_and_maths_alone():
    from orchestrator.gateway.citation_attribution import attribute_claims

    passages = [
        "Photosynthesis converts light energy into chemical energy stored in glucose.",
        "The Calvin cycle fixes carbon dioxide using ATP and NADPH in the stroma.",
    ]
    reply = (
        "## Overview\n"
        "Photosynthesis converts light energy into chemical energy stored as glucose.\n"
        "The Calvin cycle uses ATP and NADPH to fix carbon dioxide in the stroma [R2].\n"
        "Volcanoes erupt when magma pressure builds beneath the crust of the earth.\n"
        "`light energy chemical energy glucose photosynthesis` and $E = mc^2$.\n"
    )
    out = attribute_claims(reply, passages)
    assert "## Overview\n" in out
    assert "stored as glucose [R1]." in out
    assert out.count("[R2]") == 1  # an existing marker is not duplicated
    assert "crust of the earth.\n" in out  # unsupported claim stays unmarked
    assert "`light energy chemical energy glucose photosynthesis` and $E = mc^2$." in out
    assert attribute_claims(reply, []) == reply
    bracketed = attribute_claims(
        "Photosynthesis converts light energy into chemical energy stored in glucose (sugar).",
        passages,
    )
    assert bracketed.endswith("glucose (sugar) [R1].")
