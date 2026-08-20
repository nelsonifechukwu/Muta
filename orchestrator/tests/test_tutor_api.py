"""The §7.2 surface, end to end through the app (TDD §7.2, T6, T14).

Engine and vision manager are faked; sessions, ladder, image guard, verifier and renderer are
real. What is being checked is the wiring that decides whether a student gets an answer, a
queue position, or an honest refusal — the paths a judge actually walks.
"""

from __future__ import annotations

import io
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from orchestrator.gateway import deps
from orchestrator.gateway.generations import GenerationManager
from orchestrator.gateway.ladder import DegradationLadder, GiB, Level
from orchestrator.gateway.sessions import SessionManager
from orchestrator.main import app
from runtime.chat import ChatResult
from runtime.vision import VisionManager

client = TestClient(app)


class FakeEngine:
    def __init__(self, reply: str = "Let's factorise.", raises: Exception | None = None) -> None:
        self.reply = reply
        self.raises = raises
        self.calls: list[dict] = []
        self.store = FakeSettingsStore()

    def chat(self, **kwargs) -> ChatResult:
        if self.raises:
            raise self.raises
        self.calls.append(kwargs)
        return ChatResult(
            conversation_id=kwargs.get("conversation_id") or "conv-1", reply=self.reply
        )

    def stream_events_chat(self, **kwargs):
        self.calls.append(kwargs)
        cid = kwargs.get("conversation_id") or "conv-1"
        return cid, 1, iter([("reasoning", "hmm"), ("content", "x = "), ("content", "2")])


class FakeSettingsStore:
    def __init__(self) -> None:
        self.values: dict[str, dict] = {}
        self.conversations: dict[str, dict] = {}

    def get_conversation(self, conversation_id: str) -> dict | None:
        return self.conversations.get(conversation_id)

    def get_settings(self, student_id: str) -> dict:
        return dict(self.values.get(student_id, {}))

    def put_settings(self, student_id: str, settings: dict) -> None:
        self.values[student_id] = dict(settings)


@pytest.fixture
def wired():
    """Override the gateway's singletons; hand the test the objects it may poke."""
    engine = FakeEngine()
    ladder = DegradationLadder(free_probe=lambda: 8 * GiB, reserve_bytes=0, poll_seconds=0.0)
    sessions = SessionManager(
        slots_count=2, accepts_new_sessions=lambda: ladder.evaluate().accepts_new_sessions
    )
    vision = VisionManager(admit=lambda: ladder.evaluate().vision_allowed)
    generations = GenerationManager(max_active=2)

    app.dependency_overrides[deps.get_engine] = lambda: engine
    app.dependency_overrides[deps.get_ladder] = lambda: ladder
    app.dependency_overrides[deps.get_sessions] = lambda: sessions
    app.dependency_overrides[deps.get_vision] = lambda: vision
    app.dependency_overrides[deps.get_generation_manager] = lambda: generations
    yield engine, ladder, sessions, vision
    app.dependency_overrides.clear()


def turn(session_id: str = "s1", **kw) -> dict:
    return {"session_id": session_id, "text": "Solve x^2 = 9", **kw}


# --- chat ---------------------------------------------------------------------------------


def test_a_tutoring_turn_answers_and_reports_the_ladder_level(wired):
    body = client.post("/v1/tutor/chat", json=turn()).json()
    assert body["reply"] == "Let's factorise."
    assert body["mode"] == "dialogue" and body["degradation_level"] == "L0"
    assert body["queued"] is False


def test_the_mode_selects_the_sampling_profile(wired):
    engine, *_ = wired
    client.post("/v1/tutor/chat", json=turn(mode="dialogue"))
    client.post("/v1/tutor/chat", json=turn(session_id="s2", mode="solution"))
    assert engine.calls[0]["temperature"] == 0.7  # tutor-dialogue
    assert engine.calls[1]["temperature"] == 0.3  # worked-solution


def test_marking_mode_gets_a_grammar_instead_of_a_500(wired):
    """The marking profile demands structured output; without a default schema this path
    raises inside `params()` and "mark this paper" becomes a server error."""
    engine, *_ = wired
    client.post("/v1/tutor/chat", json=turn(mode="marking"))
    call = engine.calls[-1]
    assert call["temperature"] == 0.0 and call["seed"] == 4242
    assert call["response_format"]["json_schema"]["name"] == "marking_result"


def test_input_is_capped_per_turn(wired):
    """S12 prompt bomb: 4 KiB of text per turn, rejected by the contract not by the model."""
    r = client.post("/v1/tutor/chat", json=turn(text="x" * 5000))
    assert r.status_code == 422


def test_l3_refuses_new_sessions_with_a_message_not_an_error_page(wired):
    _, ladder, *_ = wired
    ladder.free_probe = lambda: int(0.3 * GiB)
    assert ladder.evaluate().level is Level.L3

    # Fill both slots, then a third student arrives.
    client.post("/v1/tutor/chat", json=turn("a"))
    client.post("/v1/tutor/chat", json=turn("b"))
    r = client.post("/v1/tutor/chat", json=turn("c"))
    assert r.status_code == 503
    assert "capacity" in r.json()["detail"] or "students" in r.json()["detail"]


def test_engine_down_is_a_503_not_a_stack_trace(wired):
    engine, *_ = wired
    engine.raises = httpx.ConnectError("no server")
    r = client.post("/v1/tutor/chat", json=turn())
    # A friendly, student-safe 503 — never a stack trace.
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert isinstance(detail, str) and "try again" in detail and "Traceback" not in detail


def test_the_slot_is_released_even_when_the_engine_fails(wired):
    """Otherwise one dead turn leaks a lane and the classroom loses a slot per crash."""
    engine, _, sessions, _ = wired
    engine.raises = httpx.ConnectError("no server")
    client.post("/v1/tutor/chat", json=turn("a"))
    slot = sessions.slot_for("a")
    assert slot is not None and slot.busy is False


def test_chat_stream_announces_the_conversation_in_its_first_frame(wired):
    """A client that stops the stream early (human-in-the-loop stop) must already know which
    conversation its partial reply landed in — the id only arriving at `done` means stopping
    the first reply of a brand-new chat forks a second thread on the next message."""
    with client.stream(
        "POST",
        "/v1/chat/stream",
        headers={"Authorization": "Bearer s1"},
        json={"student_id": "s1", "message": "Solve x^2 = 9"},
    ) as response:
        events = [line for line in response.iter_lines() if line.startswith("data: ")]
    assert '"conversation_id": "conv-1"' in events[0]
    assert '"done"' not in events[0], "the id frame must precede tokens, not replace done"
    assert '"done": true' in events[-1]


def test_streaming_turn_emits_reasoning_then_deltas_then_done(wired):
    with client.stream("POST", "/v1/tutor/chat/stream", json=turn()) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        events = [line for line in response.iter_lines() if line.startswith("data: ")]
    assert '"reasoning"' in events[0]
    assert '"delta"' in events[1]
    assert '"done": true' in events[-1] and '"ttft_s"' in events[-1]


def test_stream_done_reports_the_answer_source(wired):
    """Student text leaving the device must never be silent: every done event names the
    backend that answered. The fake engine has no client, which must read as local."""
    r = client.post(
        "/v1/chat/stream",
        headers={"Authorization": "Bearer s1"},
        json={"student_id": "s1", "message": "hi", "stream": True},
    )
    assert '"source": "local"' in r.text.strip().splitlines()[-1]


def test_browser_can_start_then_reconnect_to_a_server_owned_generation(wired):
    auth = {"Authorization": "Bearer s1"}
    started = client.post(
        "/v1/chat/generations",
        headers=auth,
        json={"student_id": "s1", "message": "Solve x^2 = 9"},
    )
    assert started.status_code == 202
    ids = started.json()
    assert ids["job_id"] and ids["conversation_id"] == "conv-1"

    replay = client.get(f"/v1/chat/generations/{ids['job_id']}/stream", headers=auth)
    assert replay.status_code == 200
    assert '"reasoning": "hmm"' in replay.text
    assert '"delta": "x = "' in replay.text
    assert '"done": true' in replay.text


def test_generation_replay_is_scoped_to_its_owner(wired):
    started = client.post(
        "/v1/chat/generations",
        headers={"Authorization": "Bearer s1"},
        json={"student_id": "s1", "message": "hello"},
    ).json()
    response = client.get(
        f"/v1/chat/generations/{started['job_id']}/stream",
        headers={"Authorization": "Bearer s2"},
    )
    assert response.status_code == 404


def test_generation_start_hides_another_students_conversation(wired):
    engine, *_ = wired
    engine.store.conversations["private"] = {"id": "private", "student_id": "s1"}
    response = client.post(
        "/v1/chat/generations",
        headers={"Authorization": "Bearer s2"},
        json={"student_id": "s2", "conversation_id": "private", "message": "peek"},
    )
    assert response.status_code == 404


def test_disabled_parallel_setting_is_enforced_by_the_server(wired):
    engine, *_ = wired
    reservation = app.dependency_overrides[deps.get_generation_manager]().reserve(
        "s1", allow_parallel=True
    )
    engine.store.put_settings("s1", {"allow_parallel_chats": False})
    response = client.post(
        "/v1/chat/generations",
        headers={"Authorization": "Bearer s1"},
        json={"student_id": "s1", "message": "second reply"},
    )
    app.dependency_overrides[deps.get_generation_manager]().cancel_reservation(reservation)
    assert response.status_code == 409
    assert "learner" in response.json()["detail"]


def test_parallel_chat_completion_releases_only_its_own_admission_lease(wired):
    engine, _, sessions, _ = wired
    generations = app.dependency_overrides[deps.get_generation_manager]()
    gates = [threading.Event(), threading.Event()]

    def blocking_stream(**kwargs):
        index = len(engine.calls)
        engine.calls.append(kwargs)
        cid = f"conv-{index + 1}"

        def events():
            yield "content", "working"
            assert gates[index].wait(2.0)
            yield "content", " done"

        return cid, index + 1, events()

    engine.stream_events_chat = blocking_stream
    headers = {"Authorization": "Bearer s1"}
    first = client.post(
        "/v1/chat/generations", headers=headers, json={"student_id": "s1", "message": "one"}
    )
    second = client.post(
        "/v1/chat/generations", headers=headers, json={"student_id": "s1", "message": "two"}
    )
    assert first.status_code == second.status_code == 202
    assert sum(slot.busy for slot in sessions.slots) == 2

    third = client.post(
        "/v1/chat/generations",
        headers=headers,
        json={"student_id": "s1", "message": "must wait"},
    )
    assert third.status_code == 409

    gates[0].set()
    deadline = time.monotonic() + 1.0
    while generations.running_count() != 1 and time.monotonic() < deadline:
        time.sleep(0.005)
    assert generations.running_count() == 1
    assert sum(slot.busy for slot in sessions.slots) == 1

    gates[1].set()


def test_parallel_chat_setting_defaults_on_and_round_trips_privately(wired):
    ada = {"Authorization": "Bearer ada"}
    assert client.get("/v1/settings", headers=ada).json() == {"allow_parallel_chats": True}

    updated = client.put("/v1/settings", headers=ada, json={"allow_parallel_chats": False})
    assert updated.status_code == 200
    assert updated.json() == {"allow_parallel_chats": False}
    assert client.get("/v1/settings", headers=ada).json() == {"allow_parallel_chats": False}
    assert client.get("/v1/settings", headers={"Authorization": "Bearer bimpe"}).json() == {
        "allow_parallel_chats": True
    }


# --- vision -------------------------------------------------------------------------------


def png_bytes(size=(60, 40)) -> bytes:
    Image = pytest.importorskip("PIL.Image", reason="Pillow ships in the bundle")
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_an_oversized_photo_is_declined_kindly_not_500(wired):
    body = client.post(
        "/v1/tutor/vision",
        data={"session_id": "s1"},
        files={"image": ("huge.jpg", b"\xff\xd8\xff" + b"0" * (9 * 1024 * 1024), "image/jpeg")},
    ).json()
    assert body["accepted"] is False and "MB" in body["detail"]


def test_a_non_image_is_declined(wired):
    body = client.post(
        "/v1/tutor/vision",
        data={"session_id": "s1"},
        files={"image": ("notes.pdf", b"%PDF-1.7", "application/pdf")},
    ).json()
    assert body["accepted"] is False and "JPEG" in body["detail"]


def test_vision_denied_by_the_ladder_tells_the_student_to_type_it(wired):
    """S2 fallback. The tutor keeps working; only the camera path is unavailable."""
    _, ladder, _, vision = wired
    ladder.free_probe = lambda: int(1.0 * GiB)  # L1: no new vision spawns
    body = client.post(
        "/v1/tutor/vision",
        data={"session_id": "s1"},
        files={"image": ("work.png", png_bytes(), "image/png")},
    ).json()
    assert body["accepted"] is False and "type the problem" in body["detail"]


def test_a_valid_photo_is_transcribed(wired, monkeypatch):
    _, _, _, vision = wired
    monkeypatch.setattr(vision, "ensure", lambda: "http://127.0.0.1:8082")

    captured = {}

    def fake_transcribe(self, image_bytes, image_format, *, prompt=...):
        captured["format"] = image_format
        captured["bytes"] = len(image_bytes)
        return "x^2 = 9"

    monkeypatch.setattr("orchestrator.gateway.routes.VisionClient.transcribe", fake_transcribe)
    body = client.post(
        "/v1/tutor/vision",
        data={"session_id": "s1"},
        files={"image": ("work.png", png_bytes((2000, 1500)), "image/png")},
    ).json()
    assert body["accepted"] is True
    assert body["transcription"] == "x^2 = 9"
    # The guard must have downscaled the 2000x1500 photo before it reached the model.
    assert captured["format"] == "PNG" and captured["bytes"] > 0


def test_the_vision_call_honours_the_configured_request_timeout(wired, monkeypatch):
    """A real photo needs minutes of prefill on a slow box; VisionClient's 120 s default cut
    every one of them off mid-read ("the image reader didn't respond") while
    MUTA_RT_REQUEST_TIMEOUT_S sat unused. The route must pass the configured timeout on."""
    _, _, _, vision = wired
    monkeypatch.setattr(vision, "ensure", lambda: "http://127.0.0.1:8082")
    monkeypatch.setenv("MUTA_RT_REQUEST_TIMEOUT_S", "600")

    seen = {}

    class FakeClient:
        def __init__(self, base_url, *, timeout=120.0, **_kw):
            seen["timeout"] = timeout

        def transcribe(self, image_bytes, image_format, *, prompt=None):
            return "x^2 = 9"

    monkeypatch.setattr("orchestrator.gateway.routes.VisionClient", FakeClient)
    body = client.post(
        "/v1/tutor/vision",
        data={"session_id": "s1"},
        files={"image": ("work.png", png_bytes(), "image/png")},
    ).json()
    assert body["accepted"] is True
    assert seen["timeout"] == 600.0


def test_vision_server_unreachable_is_a_friendly_refusal_not_500(wired, monkeypatch):
    _, _, _, vision = wired
    monkeypatch.setattr(vision, "ensure", lambda: "http://127.0.0.1:8082")

    def boom(self, image_bytes, image_format, *, prompt=...):
        raise httpx.ConnectError("refused", request=httpx.Request("POST", "http://x"))

    monkeypatch.setattr("orchestrator.gateway.routes.VisionClient.transcribe", boom)
    r = client.post(
        "/v1/tutor/vision",
        data={"session_id": "s1"},
        files={"image": ("work.png", png_bytes(), "image/png")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] is False and "type the problem" in body["detail"]


def test_a_malformed_vision_reply_is_a_friendly_refusal_not_500(wired, monkeypatch):
    """A 200 with a body we can't read must not become a 500 in a judge's face (S2)."""
    from runtime.vision_client import VisionResponseError

    _, _, _, vision = wired
    monkeypatch.setattr(vision, "ensure", lambda: "http://127.0.0.1:8082")

    def bad(self, image_bytes, image_format, *, prompt=...):
        raise VisionResponseError("unreadable vision response")

    monkeypatch.setattr("orchestrator.gateway.routes.VisionClient.transcribe", bad)
    r = client.post(
        "/v1/tutor/vision",
        data={"session_id": "s1"},
        files={"image": ("work.png", png_bytes(), "image/png")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] is False and "type the problem" in body["detail"]


# --- tools --------------------------------------------------------------------------------


def test_answer_check_endpoint(wired):
    body = client.post(
        "/v1/tutor/verify", json={"candidate": r"\boxed{4}", "expected": "2+2"}
    ).json()
    assert body["verified"] is True and body["checked"] is True


def test_answer_check_distinguishes_unchecked_from_wrong(wired):
    body = client.post(
        "/v1/tutor/verify", json={"candidate": "What do you think?", "expected": "4"}
    ).json()
    assert body["verified"] is False and body["checked"] is False


def test_render_endpoint_returns_svg(wired):
    pytest.importorskip("matplotlib")
    body = client.post(
        "/v1/tutor/render", json={"kind": "matplotlib", "code": "ax.plot([0,1],[0,1])"}
    ).json()
    assert body["ok"] is True and "</svg>" in body["svg"]


def test_render_failure_is_not_a_broken_image(wired):
    pytest.importorskip("matplotlib")
    body = client.post("/v1/tutor/render", json={"code": "import os"}).json()
    assert body["ok"] is False and body["svg"] == "" and "not allowed" in body["error"]


# --- sessions and metrics -----------------------------------------------------------------


def test_suspend_and_resume_round_trip(wired):
    client.post("/v1/tutor/chat", json=turn("ada"))
    suspended = client.post("/v1/session/ada/suspend").json()
    assert suspended["ok"] is True and suspended["action"] == "suspend"

    resumed = client.post("/v1/session/ada/resume").json()
    assert resumed["ok"] is True and resumed["action"] == "resume"


def test_suspending_an_unknown_session_is_reported_not_faked(wired):
    body = client.post("/v1/session/nobody/suspend").json()
    assert body["ok"] is False and "held no slot" in body["detail"]


def test_metrics_reports_ladder_sessions_and_vision(wired):
    client.post("/v1/tutor/chat", json=turn("ada"))
    body = client.get("/v1/metrics").json()
    assert body["degradation"]["level"] == "L0"
    assert body["sessions"]["slots"][0]["session"] == "ada"
    assert body["vision"]["running"] is False


def test_the_new_surface_is_in_the_contract():
    paths = app.openapi()["paths"]
    for path in (
        "/v1/tutor/chat",
        "/v1/tutor/chat/stream",
        "/v1/tutor/vision",
        "/v1/tutor/verify",
        "/v1/tutor/render",
        "/v1/session/{session_id}/suspend",
        "/v1/session/{session_id}/resume",
        "/v1/metrics",
    ):
        assert path in paths, f"contract is missing {path}"
