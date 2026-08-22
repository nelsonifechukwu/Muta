from __future__ import annotations

import threading

from fastapi.testclient import TestClient

from orchestrator.gateway import deps, routes
from orchestrator.main import app
from orchestrator.retrieval.resources import (
    ResourceService,
    ResourceUnavailable,
    chunk_pages,
    safe_resource_name,
)
from runtime.chat import ChatResult
from runtime.memory import ConversationStore


def test_chunks_never_cross_physical_pages():
    chunks = chunk_pages(["alpha " * 500, "kinetic energy is the energy of motion"])
    assert {chunk["page"] for chunk in chunks} == {1, 2}
    assert all("kinetic energy" not in chunk["text"] for chunk in chunks if chunk["page"] == 1)
    assert any("kinetic energy" in chunk["text"] for chunk in chunks if chunk["page"] == 2)


def test_resource_names_remain_visible_and_safe_for_inline_mentions():
    assert safe_resource_name("{}") == "resource.pdf"
    assert safe_resource_name("\u202e\u2067") == "resource.pdf"
    assert safe_resource_name("notes{chapter}.pdf") == "notes chapter.pdf"


def test_private_resources_search_and_citations_are_owner_scoped(tmp_path):
    store = ConversationStore(f"sqlite:///{tmp_path / 'muta.sqlite3'}")
    a_ready = store.create_resource("a", "science.pdf", "application/pdf", b"%PDF-fake")
    a_waiting = store.create_resource("a", "new-book.pdf", "application/pdf", b"%PDF-fake")
    b_ready = store.create_resource("b", "private.pdf", "application/pdf", b"%PDF-fake")
    service = ResourceService(store, workers=1, resume_pending=False)
    # Prepare explicit chunks to keep duplicate fake bytes from obscuring owner assertions.
    embedder = service.embedder
    for resource_id, owner, text in (
        (a_ready, "a", "Kinetic energy is the energy of a moving object."),
        (b_ready, "b", "This belongs only to learner B."),
    ):
        store.replace_resource_chunks(
            resource_id,
            owner_id=owner,
            chunks=[
                {
                    "chunk_index": 0,
                    "page": 2,
                    "text": text,
                    "embedding": embedder.embed([text])[0],
                }
            ],
            page_count=2,
            embedder_identity=embedder.identity,
        )

    assert store.get_resource(b_ready, owner_id="a") is None
    assert store.get_resource_chunks([b_ready], owner_id="a") == []
    hits = service.search("a", [a_ready], "What is kinetic energy?")
    assert hits and hits[0]["resource_id"] == a_ready and hits[0]["page"] == 2
    assert service.search("a", [a_ready], "Explain the derivative of tan x") == []
    try:
        service.search("a", [a_waiting], "anything")
    except ResourceUnavailable as exc:
        assert "still being prepared" in str(exc)
    else:
        raise AssertionError("a processing resource must be rejected")

    cid = store.create_conversation("a")
    store.add_message(cid, "user", "Explain kinetic energy")
    assistant_id = store.add_message(cid, "assistant", "It is motion energy [1].")
    store.add_message_sources(assistant_id, hits)
    replay = store.list_messages(cid)[-1]
    assert replay["resource_citations"][0]["page"] == 2
    assert replay["resource_citations"][0]["resource_id"] == a_ready
    service.shutdown()
    store.close()


class _Engine:
    def __init__(self, store) -> None:
        self.store = store
        self.calls = 0

    def chat(self, **kwargs) -> ChatResult:
        self.calls += 1
        cid = kwargs.get("conversation_id") or self.store.create_conversation(kwargs["student_id"])
        user_id = self.store.add_message(cid, "user", kwargs["message"])
        assistant_id = self.store.add_message(cid, "assistant", "grounded")
        return ChatResult(
            conversation_id=cid,
            reply="grounded",
            user_message_id=user_id,
            assistant_message_id=assistant_id,
        )

    def stream_events_chat(self, **kwargs):
        self.calls += 1
        raise AssertionError("resource preflight should reject before streaming starts")


class _ConcurrentStreamEngine:
    def __init__(self, store, conversation_id) -> None:
        self.store = store
        self.conversation_id = conversation_id
        self.unrelated_id = None
        self.owned_id = None

    def stream_events_chat(self, **kwargs):
        user_id = self.store.add_message(self.conversation_id, "user", kwargs["message"])
        owner = self

        class _Events:
            def __init__(self):
                self.done = False

            @property
            def assistant_message_id(self):
                return owner.owned_id

            def __iter__(self):
                return self

            def __next__(self):
                if self.done:
                    raise StopIteration
                self.done = True
                # Simulate a second writer winning the ordering race before this stream's
                # exact reply row is flushed.
                owner.unrelated_id = owner.store.add_message(
                    owner.conversation_id, "assistant", "unrelated concurrent answer"
                )
                owner.owned_id = owner.store.add_message(
                    owner.conversation_id, "assistant", "grounded streamed answer"
                )
                return "content", "grounded streamed answer"

            def close(self):
                return None

        return self.conversation_id, user_id, _Events()


def test_processing_preflight_happens_before_inference_or_transcript(tmp_path):
    store = ConversationStore(f"sqlite:///{tmp_path / 'route.sqlite3'}")
    resource_id = store.create_resource("a", "preparing.pdf", "application/pdf", b"%PDF-fake")
    engine = _Engine(store)
    service = ResourceService(store, workers=1, resume_pending=False)
    app.dependency_overrides[deps.get_engine] = lambda: engine
    original = routes.get_resource_service
    routes.get_resource_service = lambda: service
    try:
        response = TestClient(app).post(
            "/v1/chat/generations",
            headers={"Authorization": "Bearer a"},
            json={
                "student_id": "a",
                "message": "Use my book",
                "use_rag": True,
                "resource_ids": [resource_id],
            },
        )
        conversations = store.list_conversations("a")
    finally:
        routes.get_resource_service = original
        app.dependency_overrides.clear()
        service.shutdown()
        store.close()
    assert response.status_code == 409
    assert "still being prepared" in response.json()["detail"]
    assert engine.calls == 0
    assert conversations == []


def test_rag_off_never_resolves_uploaded_resources(tmp_path):
    store = ConversationStore(f"sqlite:///{tmp_path / 'off.sqlite3'}")
    engine = _Engine(store)

    def _unexpected_service():
        raise AssertionError("RAG-off chat must not instantiate resource retrieval")

    app.dependency_overrides[deps.get_engine] = lambda: engine
    original = routes.get_resource_service
    routes.get_resource_service = _unexpected_service
    try:
        response = TestClient(app).post(
            "/v1/chat",
            json={"student_id": "a", "message": "Hello without resource retrieval"},
        )
    finally:
        routes.get_resource_service = original
        app.dependency_overrides.clear()
        store.close()

    assert response.status_code == 200
    assert engine.calls == 1


def test_streamed_citations_bind_to_the_streams_exact_assistant_row(tmp_path):
    store = ConversationStore(f"sqlite:///{tmp_path / 'citation-race.sqlite3'}")
    resource_id = store.create_resource("a", "science.pdf", "application/pdf", b"%PDF-fake")
    service = ResourceService(store, workers=1, resume_pending=False)
    text = "Kinetic energy is the energy of a moving object."
    store.replace_resource_chunks(
        resource_id,
        owner_id="a",
        chunks=[
            {
                "chunk_index": 0,
                "page": 2,
                "text": text,
                "embedding": service.embedder.embed([text])[0],
            }
        ],
        page_count=2,
        embedder_identity=service.embedder.identity,
    )
    conversation_id = store.create_conversation("a")
    engine = _ConcurrentStreamEngine(store, conversation_id)
    app.dependency_overrides[deps.get_engine] = lambda: engine
    original = routes.get_resource_service
    routes.get_resource_service = lambda: service
    try:
        response = TestClient(app).post(
            "/v1/chat/stream",
            headers={"Authorization": "Bearer a"},
            json={
                "student_id": "a",
                "conversation_id": conversation_id,
                "message": "Explain kinetic energy",
                "use_rag": True,
                "resource_ids": [resource_id],
            },
        )
        replay = {message["id"]: message for message in store.list_messages(conversation_id)}
    finally:
        routes.get_resource_service = original
        app.dependency_overrides.clear()
        service.shutdown()
        store.close()

    assert response.status_code == 200
    assert replay[engine.unrelated_id]["resource_citations"] == []
    assert replay[engine.owned_id]["resource_citations"][0]["page"] == 2


def test_resource_content_is_hidden_from_other_owners(tmp_path):
    store = ConversationStore(f"sqlite:///{tmp_path / 'content.sqlite3'}")
    resource_id = store.create_resource("a", "book.pdf", "application/pdf", b"%PDF-test")
    engine = _Engine(store)
    service = ResourceService(store, workers=1, resume_pending=False)
    app.dependency_overrides[deps.get_engine] = lambda: engine
    app.dependency_overrides[deps.get_resource_service] = lambda: service
    client = TestClient(app)
    try:
        own = client.get(
            f"/v1/resources/{resource_id}/content",
            headers={"Authorization": "Bearer a"},
        )
        foreign = client.get(
            f"/v1/resources/{resource_id}/content",
            headers={"Authorization": "Bearer b"},
        )
    finally:
        app.dependency_overrides.clear()
        service.shutdown()
        store.close()
    assert own.status_code == 200 and own.content == b"%PDF-test"
    assert own.headers["content-type"].startswith("application/pdf")
    assert foreign.status_code == 404


def test_resource_list_retry_and_delete_are_owner_scoped(tmp_path):
    store = ConversationStore(f"sqlite:///{tmp_path / 'resource-routes.sqlite3'}")
    own_id = store.create_resource("a", "mine.pdf", "application/pdf", b"%PDF-own")
    foreign_id = store.create_resource("b", "private.pdf", "application/pdf", b"%PDF-private")
    engine = _Engine(store)
    service = ResourceService(store, workers=1, resume_pending=False)
    app.dependency_overrides[deps.get_engine] = lambda: engine
    app.dependency_overrides[deps.get_resource_service] = lambda: service
    client = TestClient(app)
    try:
        listed = client.get("/v1/resources", headers={"Authorization": "Bearer a"})
        retry = client.post(
            f"/v1/resources/{foreign_id}/retry", headers={"Authorization": "Bearer a"}
        )
        deleted = client.delete(
            f"/v1/resources/{foreign_id}", headers={"Authorization": "Bearer a"}
        )
    finally:
        app.dependency_overrides.clear()
        service.shutdown()
        store.close()

    assert listed.status_code == 200
    assert [resource["id"] for resource in listed.json()["resources"]] == [own_id]
    assert retry.status_code == 404
    assert deleted.status_code == 404


def test_deleting_resource_mid_reply_skips_late_citation_without_fk_failure(tmp_path):
    store = ConversationStore(f"sqlite:///{tmp_path / 'delete-race.sqlite3'}")
    resource_id = store.create_resource("a", "book.pdf", "application/pdf", b"%PDF-test")
    conversation_id = store.create_conversation("a")
    assistant_id = store.add_message(conversation_id, "assistant", "A reply already persisted.")
    citation = {
        "resource_id": resource_id,
        "title": "book.pdf",
        "page": 12,
        "chunk_index": 3,
        "excerpt": "The cited passage.",
    }

    assert store.delete_resource(resource_id, owner_id="a")
    store.add_message_sources(assistant_id, [citation])

    replay = store.list_messages(conversation_id)[-1]
    assert replay["resource_citations"] == []
    store.close()


def test_resource_service_shutdown_waits_for_running_preparation():
    started = threading.Event()
    release = threading.Event()
    stopped = threading.Event()

    class _SlowResourceService(ResourceService):
        def _prepare(
            self,
            resource_id,
            owner_id,
            *,
            owns_running_slot=True,
            cancel_event=None,
        ):
            _ = cancel_event
            started.set()
            release.wait(timeout=2)
            if owns_running_slot:
                with self._lock:
                    self._running.discard(resource_id)

    service = _SlowResourceService(object(), workers=1, resume_pending=False)
    assert service.submit("book", "a")
    assert started.wait(timeout=1)
    shutdown = threading.Thread(target=lambda: (service.shutdown(), stopped.set()))
    shutdown.start()
    assert not stopped.wait(timeout=0.05)

    release.set()
    shutdown.join(timeout=1)

    assert stopped.is_set()
    assert not service.submit("another-book", "a")


def test_immediate_resource_completion_clears_all_submission_bookkeeping():
    class EmptyStore:
        def get_resource(self, *_args, **_kwargs):
            return None

    service = ResourceService(EmptyStore(), workers=1, resume_pending=False)
    assert service.submit("already-gone", "a")
    for _ in range(100):
        with service._lock:
            if "already-gone" not in service._running:
                break
        threading.Event().wait(0.005)

    with service._lock:
        assert "already-gone" not in service._running
        assert "already-gone" not in service._owners
        assert "already-gone" not in service._cancellations
        assert "already-gone" not in service._futures
    service.shutdown()


def test_retry_during_worker_cleanup_does_not_orphan_processing_status(tmp_path):
    store = ConversationStore(f"sqlite:///{tmp_path / 'retry-race.sqlite3'}")
    resource_id = store.create_resource("a", "book.pdf", "application/pdf", b"%PDF-test")
    store.mark_resource_failed(resource_id, owner_id="a", error="bad PDF")
    service = ResourceService(store, workers=1, resume_pending=False)
    with service._lock:
        service._running.add(resource_id)

    assert not service.retry(resource_id, "a")
    assert store.get_resource(resource_id, owner_id="a")["status"] == "failed"

    with service._lock:
        service._running.discard(resource_id)
    service.shutdown()
    store.close()


def test_student_erasure_deletes_owned_resources(tmp_path):
    store = ConversationStore(f"sqlite:///{tmp_path / 'erase.sqlite3'}")
    resource_id = store.create_resource("a", "private.pdf", "application/pdf", b"%PDF-test")

    erased = store.delete_student("a")

    assert erased["resources"] == 1
    assert store.get_resource(resource_id, owner_id="a") is None
    store.close()
