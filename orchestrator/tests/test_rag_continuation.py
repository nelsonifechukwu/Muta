"""Grounded answers that stop early keep their sources and continue in place (2026-10-09).

Regression context: a 68-page PDF question produced a 64-token answer, the automatic retries
re-sent identical prompts, the saved partial lost its citations, and "Continue reply" sent a
visible "continue" message with no document, so the model invented the rest.
"""

from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient

from orchestrator.gateway import deps, routes
from orchestrator.main import app
from orchestrator.retrieval.resources import ResourceService
from runtime.chat import ChatEngine
from runtime.client import InferenceStreamError
from runtime.memory import ConversationStore

_PASSAGES = (
    (0, 2, "Kinetic energy is the energy an object has because of its motion."),
    (1, 3, "Potential energy is stored energy that depends on an object's position."),
)


def _ready_resource(store, service) -> str:
    resource_id = store.create_resource("a", "energy.pdf", "application/pdf", b"%PDF-fake")
    store.replace_resource_chunks(
        resource_id,
        owner_id="a",
        chunks=[
            {
                "chunk_index": index,
                "page": page,
                "text": text,
                "embedding": service.embedder.embed([text])[0],
            }
            for index, page, text in _PASSAGES
        ],
        page_count=3,
        embedder_identity=service.embedder.identity,
    )
    return resource_id


def _events(response) -> list[dict]:
    return [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]


class _Scripted:
    """Engine client double: each call pops one scripted turn of (chunks, error)."""

    def __init__(self, turns) -> None:
        self.turns = list(turns)
        self.requests: list[list[dict]] = []

    def stream_events(self, messages, **params):
        assert not [
            key
            for key in params
            if key.startswith("_muta_")
            and key != "_muta_cancel_event"
            and key != "_muta_min_reply_tokens"
        ]
        self.requests.append(messages)
        chunks, error = self.turns.pop(0)
        for chunk in chunks:
            yield "content", chunk
        if error is not None:
            raise error


def _run(store, service, client, body):
    engine = ChatEngine(client, store, persist_interval_s=0.0, stream_retry_attempts=0)
    app.dependency_overrides[deps.get_engine] = lambda: engine
    original = routes.get_resource_service
    routes.get_resource_service = lambda: service
    try:
        return TestClient(app).post(
            "/v1/chat/stream", headers={"Authorization": "Bearer a"}, json=body
        )
    finally:
        routes.get_resource_service = original
        app.dependency_overrides.clear()


def test_interrupted_grounded_answer_keeps_its_cited_sources(tmp_path):
    store = ConversationStore(f"sqlite:///{tmp_path / 'partial.sqlite3'}")
    service = ResourceService(store, workers=1, resume_pending=False)
    resource_id = _ready_resource(store, service)
    client = _Scripted(
        [
            (
                ["Kinetic energy is the energy of motion (R1). Next, "],
                InferenceStreamError("engine stopped", retryable=False),
            )
        ]
    )
    try:
        response = _run(
            store,
            service,
            client,
            {
                "student_id": "a",
                "message": "Explain kinetic energy @{energy.pdf}",
                "use_rag": True,
                "resource_ids": [resource_id],
            },
        )
        events = _events(response)
        cid = next(event["conversation_id"] for event in events if "conversation_id" in event)
        row = store.list_messages(cid)[-1]
    finally:
        service.shutdown()
        store.close()

    error = next(event for event in events if "error" in event)
    assert error["partial_saved"] is True and error["recoverable"] is True
    assert [source["page"] for source in error["sources"]] == [2]
    assert row["role"] == "assistant" and row["completion_state"] == "failed"
    assert "[R1]" in row["content"] and "(R1)" not in row["content"]
    assert [source["page"] for source in row["resource_citations"]] == [2]


def test_continue_reply_resumes_in_place_with_the_same_numbered_evidence(tmp_path):
    store = ConversationStore(f"sqlite:///{tmp_path / 'continue.sqlite3'}")
    service = ResourceService(store, workers=1, resume_pending=False)
    resource_id = _ready_resource(store, service)
    cid = store.create_conversation("a")
    question = "Compare kinetic and potential energy @{energy.pdf}"
    store.add_message(cid, "user", question)
    partial = "Kinetic energy comes from motion [R1]. By contrast,"
    partial_id = store.add_message(cid, "assistant", partial, completion_state="failed")
    store.add_message_sources(
        partial_id,
        [
            {
                "resource_id": resource_id,
                "title": "energy.pdf",
                "page": 2,
                "chunk_index": 0,
                "excerpt": _PASSAGES[0][2],
            }
        ],
    )
    client = _Scripted([([" potential energy is stored by position (R2)."], None)])
    try:
        response = _run(
            store,
            service,
            client,
            {
                "student_id": "a",
                "conversation_id": cid,
                "message": "Continue the reply @{energy.pdf}",
                "continue_reply": True,
                "use_rag": True,
                "resource_ids": [resource_id],
            },
        )
        events = _events(response)
        rows = store.list_messages(cid)
    finally:
        service.shutdown()
        store.close()

    assert response.status_code == 200
    # The stored answer arrives first, so every client (and every replay) shows one bubble.
    first_body = next(event for event in events if "replace" in event or "delta" in event)
    assert first_body == {"replace": partial}
    # No learner message was added, and the same assistant row now holds the whole answer.
    assert [row["role"] for row in rows] == ["user", "assistant"]
    assert rows[-1]["id"] == partial_id
    assert rows[-1]["completion_state"] == "complete"
    assert rows[-1]["content"] == (
        "Kinetic energy comes from motion [R1]. By contrast, potential energy is stored by "
        "position [R2]."
    )
    assert [source["page"] for source in rows[-1]["resource_citations"]] == [2, 3]
    request = client.requests[0]
    system = request[0]["content"]
    # The pinned passage keeps number 1, so the partial's [R1] still means the same page.
    assert system.index("[R1] energy.pdf, PDF page 2") < system.index("[R2] energy.pdf, PDF page 3")
    assert request[-1] == {"role": "assistant", "content": partial}
    assert request[-2]["role"] == "user" and request[-2]["content"].startswith(question)
    assert "Continue the reply" not in json.dumps(request)


def test_continue_reply_is_refused_without_an_interrupted_answer(tmp_path):
    store = ConversationStore(f"sqlite:///{tmp_path / 'refuse.sqlite3'}")
    service = ResourceService(store, workers=1, resume_pending=False)
    cid = store.create_conversation("a")
    store.add_message(cid, "user", "Q")
    store.add_message(cid, "assistant", "A finished answer.", completion_state="complete")
    client = _Scripted([])
    try:
        response = _run(
            store,
            service,
            client,
            {
                "student_id": "a",
                "conversation_id": cid,
                "message": "Continue",
                "continue_reply": True,
            },
        )
        rows = store.list_messages(cid)
    finally:
        service.shutdown()
        store.close()
    assert response.status_code == 409
    assert len(rows) == 2 and client.requests == []


def _passages(store, service, name, passages):
    resource_id = store.create_resource("a", name, "application/pdf", b"%PDF-fake")
    store.replace_resource_chunks(
        resource_id,
        owner_id="a",
        chunks=[
            {
                "chunk_index": index,
                "page": page,
                "text": text,
                "embedding": service.embedder.embed([text])[0],
            }
            for index, page, text in passages
        ],
        page_count=9,
        embedder_identity=service.embedder.identity,
    )
    return resource_id


def test_deleting_a_cited_file_never_repoints_a_resumed_answers_markers(tmp_path):
    """Review finding: with waves.pdf deleted, the stored "[R2]" silently became a citation
    of an unrelated energy.pdf passage once fresh hits took its number."""
    store = ConversationStore(f"sqlite:///{tmp_path / 'drift.sqlite3'}")
    service = ResourceService(store, workers=1, resume_pending=False)
    energy = _passages(
        store,
        service,
        "energy.pdf",
        [
            (0, 2, "Kinetic energy is the energy an object has because of its motion."),
            (1, 7, "Friction converts kinetic energy into heat energy in the surfaces."),
        ],
    )
    waves = _passages(
        store, service, "waves.pdf", [(0, 4, "Sound energy travels as a longitudinal wave.")]
    )
    cid = store.create_conversation("a")
    store.add_message(cid, "user", "Explain energy @{energy.pdf} @{waves.pdf}")
    partial = "Kinetic energy is motion energy [R1]. Sound travels as a wave [R2]. Also"
    partial_id = store.add_message(cid, "assistant", partial, completion_state="failed")
    store.add_message_sources(
        partial_id,
        [
            {
                "resource_id": energy,
                "title": "energy.pdf",
                "page": 2,
                "chunk_index": 0,
                "excerpt": "Kinetic energy is the energy an object has",
            },
            {
                "resource_id": waves,
                "title": "waves.pdf",
                "page": 4,
                "chunk_index": 0,
                "excerpt": "Sound energy travels as a longitudinal wave.",
            },
        ],
    )
    store.delete_resource(waves, owner_id="a")
    client = _Scripted([([" friction turns it into heat [R1]."], None)])
    try:
        _run(
            store,
            service,
            client,
            {
                "student_id": "a",
                "conversation_id": cid,
                "message": "Continue",
                "continue_reply": True,
                "use_rag": True,
                "resource_ids": [energy],
            },
        )
        row = store.list_messages(cid)[-1]
    finally:
        service.shutdown()
        store.close()
    # The orphaned "[R2]" is gone instead of now meaning an energy.pdf page.
    assert "Sound travels as a wave." in row["content"]
    assert "wave [R" not in row["content"]
    citations = row["resource_citations"]
    assert all(source["title"] == "energy.pdf" for source in citations)
    markers = sorted({int(n) for n in re.findall(r"\[R(\d+)\]", row["content"])})
    assert markers == list(range(1, len(citations) + 1))


def test_resumed_markers_stay_valid_when_the_prompt_cannot_show_every_pin(tmp_path):
    """Review finding: pinned passages that did not fit the prompt dropped out of the citation
    list, so re-finalizing deleted the saved answer's valid [R2]/[R3] markers."""
    store = ConversationStore(f"sqlite:///{tmp_path / 'pins.sqlite3'}")
    service = ResourceService(store, workers=1, resume_pending=False)
    text = "Kinetic energy grows with the square of speed and depends on mass. " * 12
    resource_id = _passages(
        store, service, "energy.pdf", [(i, i + 2, f"Passage {i}: {text}") for i in range(3)]
    )
    cid = store.create_conversation("a")
    store.add_message(cid, "user", "Explain kinetic energy @{energy.pdf}")
    partial = "First claim [R1]. Second claim [R2]. Third claim [R3]. " + "Detail. " * 600
    partial_id = store.add_message(cid, "assistant", partial, completion_state="failed")
    store.add_message_sources(
        partial_id,
        [
            {
                "resource_id": resource_id,
                "title": "energy.pdf",
                "page": i + 2,
                "chunk_index": i,
                "excerpt": f"Passage {i}: Kinetic energy grows",
            }
            for i in range(3)
        ],
    )
    client = _Scripted([([" And so on [R1]."], None)])
    engine = ChatEngine(
        client,
        store,
        persist_interval_s=0.0,
        stream_retry_attempts=0,
        context_window_tokens=4500,
    )
    app.dependency_overrides[deps.get_engine] = lambda: engine
    original = routes.get_resource_service
    routes.get_resource_service = lambda: service
    try:
        TestClient(app).post(
            "/v1/chat/stream",
            headers={"Authorization": "Bearer a"},
            json={
                "student_id": "a",
                "conversation_id": cid,
                "message": "Continue",
                "continue_reply": True,
                "use_rag": True,
                "resource_ids": [resource_id],
            },
        )
        row = store.list_messages(cid)[-1]
    finally:
        routes.get_resource_service = original
        app.dependency_overrides.clear()
        service.shutdown()
        store.close()
    assert "Second claim [R2]. Third claim [R3]." in row["content"]
    assert [source["page"] for source in row["resource_citations"]] == [2, 3, 4]


def test_interrupted_grounded_answer_never_persists_a_model_visualization(tmp_path):
    store = ConversationStore(f"sqlite:///{tmp_path / 'viz.sqlite3'}")
    service = ResourceService(store, workers=1, resume_pending=False)
    resource_id = _ready_resource(store, service)
    fence = '\n\n```muta-viz\n{"version": 1, "kind": "graph"}\n```\n\nNext,'
    client = _Scripted(
        [
            (
                ["Kinetic energy is the energy of motion (R1)." + fence],
                InferenceStreamError("engine stopped", retryable=False),
            )
        ]
    )
    try:
        response = _run(
            store,
            service,
            client,
            {
                "student_id": "a",
                "message": "Explain kinetic energy",
                "use_rag": True,
                "resource_ids": [resource_id],
            },
        )
        cid = next(e["conversation_id"] for e in _events(response) if "conversation_id" in e)
        content = store.list_messages(cid)[-1]["content"]
    finally:
        service.shutdown()
        store.close()
    assert "muta-viz" not in content
    assert content.startswith("Kinetic energy is the energy of motion [R1].")


def test_a_grounded_answer_without_markers_keeps_its_consulted_passages(tmp_path):
    """Small models often answer correctly from the evidence but write no [R#] marker; the
    reply used to carry no sources at all. The strongest passages shown are kept instead."""
    store = ConversationStore(f"sqlite:///{tmp_path / 'consulted.sqlite3'}")
    service = ResourceService(store, workers=1, resume_pending=False)
    resource_id = _ready_resource(store, service)
    # A loose paraphrase no passage clearly supports: attribution must not invent a number.
    client = _Scripted([(["Things that go fast carry a lot of oomph, roughly speaking."], None)])
    try:
        response = _run(
            store,
            service,
            client,
            {"student_id": "a", "message": "What is kinetic energy?", "use_rag": True,
             "resource_ids": [resource_id]},
        )
        events = _events(response)
        cid = next(e["conversation_id"] for e in events if "conversation_id" in e)
        row = store.list_messages(cid)[-1]
    finally:
        service.shutdown()
        store.close()
    done = next(event for event in events if event.get("done"))
    assert "[R" not in row["content"]
    assert [source["page"] for source in row["resource_citations"]][:1] == [2]
    assert [source["page"] for source in done["sources"]] == [
        source["page"] for source in row["resource_citations"]
    ]


def test_unmarked_claims_get_the_number_of_the_passage_that_supports_them(tmp_path):
    """Small models rarely write [R#]; supported sentences are numbered after generation."""
    store = ConversationStore(f"sqlite:///{tmp_path / 'attribution.sqlite3'}")
    service = ResourceService(store, workers=1, resume_pending=False)
    resource_id = _ready_resource(store, service)
    answer = (
        "Kinetic energy is the energy an object has because of its motion.\n\n"
        "- Potential energy is stored energy that depends on an object's position.\n"
        "- Feel free to ask me anything else about energy!"
    )
    client = _Scripted([([answer], None)])
    try:
        response = _run(
            store,
            service,
            client,
            {"student_id": "a", "message": "Explain kinetic and potential energy",
             "use_rag": True, "resource_ids": [resource_id]},
        )
        events = _events(response)
        cid = next(e["conversation_id"] for e in events if "conversation_id" in e)
        row = store.list_messages(cid)[-1]
    finally:
        service.shutdown()
        store.close()
    content = row["content"]
    assert "because of its motion [R" in content
    assert "position [R" in content
    assert "anything else about energy!" in content and "energy! [R" not in content
    pages = {source["page"] for source in row["resource_citations"]}
    assert pages == {2, 3}
    replace = [event["replace"] for event in events if "replace" in event]
    assert replace and replace[-1] == content
