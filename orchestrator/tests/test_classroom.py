"""Adversarial teacher-course and host-local class-board boundaries."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from contracts.models import ChatRequest
from orchestrator.gateway import auth, share_routes, sharing
from orchestrator.gateway import routes as gateway_routes
from orchestrator.gateway.auth import AuthPrincipal
from orchestrator.gateway.course_policy import (
    CourseAccessError,
    CourseNotFoundError,
    append_course_context,
    resolve_course_policy,
)
from orchestrator.gateway.deps import load_prompt
from orchestrator.gateway.prompting import assemble_system_prompt
from orchestrator.gateway.quality import CombinedReplyGuard
from orchestrator.gateway.share_routes import router
from orchestrator.gateway.sharing import SharingService
from runtime.chat import ChatEngine


def _approved_member(service: SharingService, username: str, key: str):
    service.signup(username, "private classroom password", throttle_key=f"signup-{key}")
    user_id = next(row["id"] for row in service.users() if row["username"] == username)
    service.approve(user_id)
    issued = service.login(
        username,
        "private classroom password",
        throttle_key=f"login-{key}",
    )
    return user_id, issued


def _share_app(monkeypatch, service: SharingService) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    monkeypatch.setattr(share_routes, "get_sharing_service", lambda: service)
    monkeypatch.setattr(auth, "get_sharing_service", lambda: service)
    return app


def _member_client(app: FastAPI, token: str) -> TestClient:
    client = TestClient(
        app,
        base_url="https://muta.test:8443",
        client=("192.168.1.20", 51000),
    )
    client.cookies.set("muta_share_session", token)
    return client


def _host_client(app: FastAPI, token: str) -> TestClient:
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 51001))
    client.cookies.set("muta_share_session", token)
    return client


def _course_payload(**overrides):
    return {
        "name": "SS2 Mathematics",
        "teaching_style": "hints",
        "lock_style": True,
        "withhold_final_answers": True,
        "teacher_note": "Ask for the learner's reasoning.",
        **overrides,
    }


def test_course_policy_is_server_resolved_and_locked_mode_ignores_client(tmp_path):
    service = SharingService(tmp_path / "share.sqlite3")
    course = service.create_course(
        **_course_payload(teacher_note="<b>Use balance models.</b>\nNever rush.")
    )
    principal = AuthPrincipal(
        subject="member-one",
        role="member",
        session_id="session-one",
        auth_kind="share",
    )

    policy = resolve_course_policy(
        requested_mode="subgoal",
        course_id=course["id"],
        principal=principal,
        service=service,
    )

    assert policy.effective_mode == "hints"
    assert policy.withhold_final_answers is True
    assert policy.teacher_note == "Use balance models. Never rush."
    prompt = append_course_context("stable prefix\n\n--- per-student context ---", policy)
    assert prompt.startswith("stable prefix\n\n--- per-student context ---")
    assert "Teacher course" in prompt
    assert "withheld" in prompt
    assert "<b>" not in prompt

    unlocked = service.create_course(**_course_payload(name="Physics", lock_style=False))
    unlocked_policy = resolve_course_policy(
        requested_mode="analogy",
        course_id=unlocked["id"],
        principal=principal,
        service=service,
    )
    assert unlocked_policy.effective_mode == "analogy"

    for invalid_principal in (
        None,
        AuthPrincipal(subject="legacy", role="legacy"),
        AuthPrincipal(
            subject="operator", role="host", session_id="host", auth_kind="share"
        ),
    ):
        with pytest.raises(CourseAccessError):
            resolve_course_policy(
                requested_mode="socratic",
                course_id=course["id"],
                principal=invalid_principal,
                service=service,
            )

    other_host = SharingService(tmp_path / "other-host.sqlite3")
    with pytest.raises(CourseNotFoundError):
        resolve_course_policy(
            requested_mode="socratic",
            course_id=course["id"],
            principal=principal,
            service=other_host,
        )


def test_chat_request_hook_resolves_locked_course_from_host_database(monkeypatch, tmp_path):
    service = SharingService(tmp_path / "share.sqlite3")
    course = service.create_course(**_course_payload())
    principal = AuthPrincipal(
        subject="member-one",
        role="member",
        session_id="session-one",
        auth_kind="share",
    )
    monkeypatch.setattr(gateway_routes, "get_sharing_service", lambda: service)
    monkeypatch.setattr(gateway_routes, "principal_from_request", lambda _request: principal)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/chat/generations",
            "headers": [],
            "query_string": b"",
            "scheme": "https",
            "server": ("muta.test", 8443),
            "client": ("192.168.1.20", 51000),
        }
    )

    policy = gateway_routes._request_course_policy(
        ChatRequest(
            student_id="member-one",
            message="Help me solve this",
            mode="subgoal",
            course_id=course["id"],
        ),
        request,
    )

    assert policy.effective_mode == "hints"
    assert policy.teacher_note == "Ask for the learner's reasoning."


def test_locked_course_policy_survives_long_context_fitting(tmp_path):
    service = SharingService(tmp_path / "share.sqlite3")
    course = service.create_course(
        **_course_payload(teacher_note="Always ask for a balance drawing.")
    )
    principal = AuthPrincipal(
        subject="member-one",
        role="member",
        session_id="session-one",
        auth_kind="share",
    )
    policy = resolve_course_policy(
        requested_mode="subgoal",
        course_id=course["id"],
        principal=principal,
        service=service,
    )
    system_prompt = append_course_context(
        assemble_system_prompt(
            load_prompt("hints"),
            twin_summary=" ".join(["older context"] * 1000),
        ),
        policy,
    )
    instruction = gateway_routes._trusted_turn_instruction(
        "Solve x + 3 = 8",
        "en",
        CombinedReplyGuard(gateway_routes.IntegrityGuard()),
        policy,
    )
    engine = ChatEngine(
        object(), object(), context_window_tokens=900, context_safety_tokens=50
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": "Solve x + 3 = 8\n\n"
            "[MUTA RUNTIME INSTRUCTION — not part of the learner's message]\n"
            + instruction,
        },
    ]

    fitted, _params = engine._fit_request(messages, {"max_tokens": 256})
    protected_tail = fitted[-1]["content"]

    assert "locked to hints" in protected_tail
    assert "Withhold the final answer" in protected_tail
    assert "Always ask for a balance drawing" in protected_tail


def test_course_crud_requires_local_host_and_csrf(monkeypatch, tmp_path):
    service = SharingService(tmp_path / "share.sqlite3")
    service.update_settings(enabled=True, memory_mode="competition")
    _user_id, member_session = _approved_member(service, "Ada", "ada")
    app = _share_app(monkeypatch, service)
    member = _member_client(app, member_session.token)
    host_session = service.issue_host_session("operator")
    host = _host_client(app, host_session.token)
    remote_host = _member_client(app, host_session.token)
    anonymous = TestClient(
        app,
        base_url="https://muta.test:8443",
        client=("192.168.1.21", 51002),
    )

    assert anonymous.get("/v1/share/courses").status_code == 401
    assert member.post("/v1/share/host/courses", json=_course_payload()).status_code == 403
    assert remote_host.get("/v1/share/courses").status_code == 403
    assert host.post("/v1/share/host/courses", json=_course_payload()).status_code == 403
    assert (
        host.post(
            "/v1/share/host/courses",
            json=_course_payload(),
            headers={"X-Muta-CSRF": "wrong"},
        ).status_code
        == 403
    )

    created = host.post(
        "/v1/share/host/courses",
        json=_course_payload(),
        headers={"X-Muta-CSRF": host_session.csrf_token},
    )
    assert created.status_code == 200
    course = created.json()
    assert course["teacher_note"] == "Ask for the learner's reasoning."
    assert member.get("/v1/share/courses").json()["courses"] == [course]

    updated = host.put(
        f"/v1/share/host/courses/{course['id']}",
        json=_course_payload(name="SS2 Physics", teaching_style="analogy"),
        headers={"X-Muta-CSRF": host_session.csrf_token},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "SS2 Physics"
    assert updated.json()["teaching_style"] == "analogy"

    deleted = host.delete(
        f"/v1/share/host/courses/{course['id']}",
        headers={"X-Muta-CSRF": host_session.csrf_token},
    )
    assert deleted.json() == {"id": course["id"], "deleted": True}
    assert member.get("/v1/share/courses").json() == {"courses": []}


def test_class_board_authorization_verification_and_delete_boundaries(monkeypatch, tmp_path):
    service = SharingService(tmp_path / "share.sqlite3")
    service.update_settings(enabled=True, memory_mode="competition")
    ada_id, ada_session = _approved_member(service, "Ada", "ada")
    _kwame_id, kwame_session = _approved_member(service, "Kwame", "kwame")
    app = _share_app(monkeypatch, service)
    ada = _member_client(app, ada_session.token)
    kwame = _member_client(app, kwame_session.token)
    host_session = service.issue_host_session("operator")
    host = _host_client(app, host_session.token)
    remote_host = _member_client(app, host_session.token)
    anonymous = TestClient(app, base_url="https://muta.test:8443")
    legacy = TestClient(app, base_url="https://muta.test:8443")

    assert anonymous.get("/v1/share/class/posts").status_code == 401
    assert (
        legacy.get(
            "/v1/share/class/posts", headers={"Authorization": "Bearer legacy-student"}
        ).status_code
        == 403
    )
    assert remote_host.get("/v1/share/class/posts").status_code == 403
    assert host.post(
        "/v1/share/class/posts", json={"body": "Host spoof"}
    ).status_code == 403

    created = ada.post(
        "/v1/share/class/posts",
        json={
            "body": "Why does $3(x-2)$ distribute to both terms? <script>bad()</script>",
            "addressed_to_teacher": True,
        },
    )
    assert created.status_code == 200
    post = created.json()
    assert post["author"] == {"id": ada_id, "username": "Ada"}
    assert post["addressed_to_teacher"] is True
    assert "<script>" in post["body"], "storage remains plain text; the UI sanitizer owns HTML"

    replied = kwame.post(
        f"/v1/share/class/posts/{post['id']}/replies",
        json={"body": "Try multiplying $3$ by each term."},
    )
    assert replied.status_code == 200
    reply = replied.json()
    assert reply["teacher_verified"] is False
    assert ada.put(
        f"/v1/share/host/class/replies/{reply['id']}/verification",
        json={"verified": True},
    ).status_code == 403
    assert host.put(
        f"/v1/share/host/class/replies/{reply['id']}/verification",
        json={"verified": True},
    ).status_code == 403

    verified = host.put(
        f"/v1/share/host/class/replies/{reply['id']}/verification",
        json={"verified": True},
        headers={"X-Muta-CSRF": host_session.csrf_token},
    )
    assert verified.status_code == 200
    assert verified.json()["teacher_verified"] is True
    thread = host.get(f"/v1/share/class/posts/{post['id']}").json()
    assert thread["post"]["reply_count"] == 1
    assert thread["post"]["verified_reply_count"] == 1

    assert ada.delete(f"/v1/share/host/class/posts/{post['id']}").status_code == 403
    deleted = host.delete(
        f"/v1/share/host/class/posts/{post['id']}",
        headers={"X-Muta-CSRF": host_session.csrf_token},
    )
    assert deleted.json() == {"id": post["id"], "deleted": True}
    assert kwame.get(f"/v1/share/class/posts/{post['id']}").status_code == 404


def test_class_board_is_scoped_to_one_host_database_and_erased_with_member(
    monkeypatch, tmp_path
):
    first = SharingService(tmp_path / "first.sqlite3")
    first.update_settings(enabled=True, memory_mode="competition")
    user_id, first_session = _approved_member(first, "Amina", "first")
    with first.member_write(user_id):
        post = first.create_class_post(user_id, body="Private to this classroom")

    second = SharingService(tmp_path / "second.sqlite3")
    second.update_settings(enabled=True, memory_mode="competition")
    app = _share_app(monkeypatch, second)
    wrong_host = _member_client(app, first_session.token)
    assert wrong_host.get("/v1/share/class/posts").status_code == 401
    assert second.class_thread(post["id"]) is None

    first.begin_removal(user_id)
    first.finalize_removal(user_id)
    assert first.class_thread(post["id"]) is None


def test_class_thread_bounds_replies_to_the_newest_window(tmp_path):
    service = SharingService(tmp_path / "share.sqlite3")
    service.update_settings(enabled=True, memory_mode="competition")
    user_id, _session = _approved_member(service, "Bounded", "bounded")
    post = service.create_class_post(user_id, body="Keep this thread bounded")

    with service._lock, service._conn:  # avoid an O(n²) route setup loop in this storage test
        for index in range(205):
            stamp = f"2026-10-06T10:{index // 60:02d}:{index % 60:02d}+00:00"
            service._conn.execute(
                "INSERT INTO share_class_replies "
                "(id, post_id, author_user_id, body, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (f"{index:032x}", post["id"], user_id, f"reply {index}", stamp, stamp),
            )

    thread = service.class_thread(post["id"])
    assert len(thread["replies"]) == 200
    assert thread["replies"][0]["body"] == "reply 5"
    assert thread["replies"][-1]["body"] == "reply 204"


def test_class_board_applies_per_member_storage_quotas(monkeypatch, tmp_path):
    monkeypatch.setattr(sharing, "_MAX_BOARD_POSTS_PER_MEMBER", 1)
    monkeypatch.setattr(sharing, "_MAX_BOARD_REPLIES_PER_MEMBER", 1)
    service = SharingService(tmp_path / "share.sqlite3")
    service.update_settings(enabled=True, memory_mode="competition")
    user_id, _session = _approved_member(service, "Quota", "quota")
    post = service.create_class_post(user_id, body="first")
    with pytest.raises(ValueError, match="question limit"):
        service.create_class_post(user_id, body="second")
    service.create_class_reply(post["id"], user_id, body="first reply")
    with pytest.raises(ValueError, match="reply limit"):
        service.create_class_reply(post["id"], user_id, body="second reply")
