"""The public `/v1` contract surface.

Defined as a router so it can be included on the assembled app (`orchestrator.main`) and
on the standalone gateway app (`orchestrator.gateway.app`) without duplication. Shapes come
from `contracts`, so the OpenAPI document is generated from the models. Every endpoint here
is implemented (chat, vision, audio, conversations, verify, diagnose, generate_question,
mastery, exam/answer) — the internal math/pedagogy sub-apps under `/internal/*` still hold
their own stubs, but nothing on the public `/v1` surface returns 501.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, StreamingResponse

from contracts.models import (
    AnswerCheckRequest,
    AnswerCheckResponse,
    AttachmentRef,
    AuthTokenRequest,
    AuthTokenResponse,
    ChatRequest,
    ChatResponse,
    ChatTurn,
    ConversationDeleted,
    ConversationList,
    ConversationOut,
    DiagnoseRequest,
    DiagnoseResponse,
    ExamAnswerRequest,
    GeneratedQuestion,
    GenerateQuestionRequest,
    GenerateQuestionResponse,
    HealthResponse,
    MasteryResponse,
    MessageList,
    MessageOut,
    ReadyResponse,
    RenderRequest,
    RenderResponse,
    SessionActionResponse,
    StudentErased,
    Subject,
    SystemStatus,
    TelemetrySnapshot,
    TutorMode,
    TutorReply,
    VerifyRequest,
    VerifyResponse,
    VisionReply,
)
from orchestrator import bench_metrics
from orchestrator.gateway.auth import caller_from_token, mint_token, require_caller
from orchestrator.gateway.deps import (
    get_engine,
    get_ladder,
    get_renderer,
    get_sessions,
    get_slot_client,
    get_twin_store,
    get_verifier,
    get_vision,
    load_prompt,
)
from orchestrator.gateway.images import ImageRejected, prepare_image
from orchestrator.gateway.ladder import DegradationLadder
from orchestrator.gateway.prompting import assemble_system_prompt
from orchestrator.gateway.sampling import params_for_mode
from orchestrator.gateway.selfcheck import scan_claims, self_check
from orchestrator.gateway.sessions import Admission, SessionManager
from orchestrator.gateway.websearch import fetch_snippets
from orchestrator.telemetry import get_hub
from orchestrator.tools.renderer import DiagramRenderer
from orchestrator.tools.verifier import AnswerVerifier
from runtime.chat import ChatEngine
from runtime.client import Generation
from runtime.config import RuntimeConfig
from runtime.slots import SlotError
from runtime.vision import VisionDenied, VisionManager
from runtime.vision_client import VisionClient, VisionResponseError

router = APIRouter()

log = logging.getLogger("muta.gateway.routes")

# SSE through a proxy: no caching, and tell nginx not to buffer the stream.
_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

# Serve stored attachments as inert downloads: never let a browser MIME-sniff or render bytes
# a student uploaded (an audio/HTML polyglot with a client-set text/html type was a stored-XSS
# vector). Constrain the served type to a known-safe allowlist, too.
_ATTACHMENT_HEADERS = {"X-Content-Type-Options": "nosniff", "Content-Disposition": "attachment"}
_SAFE_ATTACHMENT_MIME = {
    "image/jpeg", "image/png", "image/webp",
    "audio/webm", "audio/ogg", "audio/mpeg", "audio/mp4", "audio/wav", "audio/x-wav",
}


def _close_events(events) -> None:
    """Deterministically close the engine's event generator so its finally (partial-reply
    persist) runs on this thread, now — not via GC after a client disconnect. A no-op for a
    plain iterator (e.g. a test double), which holds nothing to release."""
    close = getattr(events, "close", None)
    if close is not None:
        close()


def _engine_unreachable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="the tutor is starting up or busy — give it a moment and try again",
    )


def _handle_engine_error(exc: httpx.HTTPError, *, where: str) -> HTTPException:
    """Map any llama-server failure to a friendly, student-safe 503 — and record the real
    cause server-side so an operator can diagnose it. A 400 is almost always context overflow
    (a long conversation), which the student can act on; transport errors mean the engine is
    down or slow."""
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 400:
        log.warning("engine rejected request at %s: %s", where, exc)
        return HTTPException(
            status_code=503,
            detail="this conversation got long — start a new chat and I'll keep up",
        )
    log.warning("engine unreachable at %s: %r", where, exc)
    return _engine_unreachable()


@router.get("/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    from orchestrator.version import git_sha, version

    return HealthResponse(service="gateway", version=version(), git_sha=git_sha())


@router.get("/ready", response_model=ReadyResponse, tags=["ops"])
def ready() -> ReadyResponse:
    """Probes engine + db directly from config, never through `get_engine()` — readiness
    must report a down dependency, not hang constructing a store against it. Always HTTP
    200; the compose healthcheck greps the body for `"ready":true`."""
    cfg = RuntimeConfig()
    checks = {
        "gateway": True,
        "inference": _url_up(f"{cfg.base_url}/health"),
        "db": _db_up(cfg.db_url),
    }
    from orchestrator.gateway.connectivity import get_connectivity

    return ReadyResponse(
        ready=all(checks.values()), checks=checks, online=get_connectivity().online()
    )


def _url_up(url: str) -> bool:
    try:
        return httpx.get(url, timeout=2.0).status_code == 200
    except httpx.HTTPError:
        return False


def _db_up(dsn: str) -> bool:
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=2) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:  # noqa: BLE001 — any failure means "not ready", never a crash
        return False


def _twin_summary(student_id: str) -> str:
    """The learning-twin session summary for this student, best-effort (never fails a turn)."""
    try:
        return get_twin_store().load(student_id).prompt_summary()
    except Exception:  # noqa: BLE001 — personalisation is a nicety, not a dependency
        log.warning("twin load failed for %s", student_id, exc_info=True)
        return ""


def _touch_twin(student_id: str, subject: str, message: str) -> None:
    """Record activity after a turn: a turn count and a compact 'what they asked' summary that
    seeds the next turn's context. Deliberately does NOT fabricate mastery — mastery only moves
    on real evidence (a checked exam answer), never on free-chat volume."""
    try:
        store = get_twin_store()
        twin = store.load(student_id)
        twin.bump("turns")
        snippet = " ".join(message.split())[:60]
        if snippet:
            twin.add_summary(f"asked about {subject}: {snippet}")
        store.save(twin)
    except Exception:  # noqa: BLE001
        log.warning("twin update failed for %s", student_id, exc_info=True)


#: Extended thinking gives the answer more room; the reasoning budget itself is a launch flag
#: (docs/engine-flags.md), so 'extended' buys a fuller answer rather than a deeper trace.
_EXTENDED_MAX_TOKENS = 3000


def _apply_thinking(params: dict, thinking: str | None) -> dict:
    """Fold the request's thinking level into the sampling params the engine receives. `off`
    disables the Qwen3 thinking phase (a direct, faster answer); `extended` keeps it on and
    widens the token budget; `auto`/None leave the server default. Per-request enable_thinking
    is honoured by runtime.client._payload."""
    if thinking == "off":
        params["enable_thinking"] = False
    elif thinking == "auto":
        params["enable_thinking"] = True
    elif thinking == "extended":
        params["enable_thinking"] = True
        params["max_tokens"] = max(int(params.get("max_tokens") or 0), _EXTENDED_MAX_TOKENS)
    return params


def _rag_block(query: str, *, k: int = 4) -> str:
    """Retrieved syllabus chunks for a query, rendered as a delimited reference block — or ""
    when RAG is not available (no index staged, embed server down). Degradation is the design:
    the offline-first default answers from the model alone, and grounding is a bonus when the
    corpus has been indexed on this box."""
    try:
        from orchestrator.gateway.prompt_layout import RetrievedChunk, render_chunks
        from orchestrator.retrieval.app import get_retriever

        # A modest relevance floor keeps unrelated chunks out of the prompt (they cost context
        # and can mislead); the real bge embedder's cosine scores clear it easily for on-topic
        # material.
        hits = get_retriever().search(query, k, min_score=0.1)
        if not hits:
            return ""
        chunks = [
            RetrievedChunk(doc_id=h.doc_id, chunk_id=h.chunk_id, text=h.text, score=h.score)
            for h in hits
        ]
        log.info("rag: grounded on %d chunks", len(chunks))
        return render_chunks(chunks)
    except Exception:  # noqa: BLE001 — any retrieval failure = answer from the model alone
        return ""


def _run_self_check(reply: str) -> tuple[bool | None, str]:
    """Symbolic self-check of a completed reply. Returns (verified, note): verified is None
    when nothing was checkable (the common case), True/False otherwise. The verifier (which
    forks a sandbox) is only constructed when the cheap scan finds explicit equations."""
    try:
        if not scan_claims(reply):
            return None, ""
        result = self_check(get_verifier(), reply)
        if not result.checked:
            return None, ""
        return result.verified, result.note
    except Exception:  # noqa: BLE001 — a self-check failure must never break the reply
        log.warning("self-check failed", exc_info=True)
        return None, ""


def _link_attachments(engine: ChatEngine, ids: list[int], cid: str, message_id: int | None) -> None:
    """Bind previously-uploaded attachments to the persisted user turn. Unknown ids are a
    no-op UPDATE, not an error — the message must never fail over a stale attachment ref."""
    for aid in ids:
        try:
            engine.store.link_attachment(aid, cid, message_id)
        except Exception:  # noqa: BLE001 — linking is best-effort metadata
            log.warning("failed to link attachment %s to conversation %s", aid, cid, exc_info=True)
            continue


@router.post("/chat", response_model=ChatResponse, tags=["tutor"])
def chat(req: ChatRequest, engine: ChatEngine = Depends(get_engine)) -> ChatResponse:
    """Multi-turn tutoring turn. Memory is keyed by `conversation_id`; omit it to start a
    new thread. The mode selects the system prompt (ROADMAP 18 Jul, stable-prefix design)."""
    system_prompt = assemble_system_prompt(
        load_prompt(req.mode.value),
        persona=req.persona.value,
        language=req.language,
        subject=req.subject.value,
        twin_summary=_twin_summary(req.student_id),
    )
    try:
        result = engine.chat(
            student_id=req.student_id,
            message=req.message,
            conversation_id=req.conversation_id,
            system_prompt=system_prompt,
            mode=req.mode.value,
            persona=req.persona.value,
            subject=req.subject.value,
            language=req.language,
            title=req.message[:80],
            **_apply_thinking(params_for_mode(req.mode.value), req.thinking),
        )
    except httpx.HTTPError as e:
        raise _handle_engine_error(e, where="/chat") from e
    if req.attachment_ids:
        _link_attachments(engine, req.attachment_ids, result.conversation_id, result.user_message_id)
    # Telemetry for the external HUD (bench/monitor.py), which never sees a generation itself.
    if result.generation is not None:
        bench_metrics.record(result.generation)
    # Verified-tool-calls thesis: self-check the model's explicit arithmetic/algebra, append an
    # honest caution when a step contradicts itself, and record the turn on the learning twin.
    verified, note = _run_self_check(result.reply)
    reply = result.reply if not note else f"{result.reply}\n\n{note}"
    _touch_twin(req.student_id, req.subject.value, req.message)
    return ChatResponse(
        student_id=req.student_id,
        conversation_id=result.conversation_id,
        mode=req.mode,
        reply=reply,
        verified=bool(verified),
    )


@router.post(
    "/chat/stream",
    tags=["tutor"],
    responses={200: {"content": {"text/event-stream": {}}, "description": "SSE token stream"}},
)
def chat_stream(
    req: ChatRequest,
    engine: ChatEngine = Depends(get_engine),
    sessions: SessionManager = Depends(get_sessions),
    ladder: DegradationLadder = Depends(get_ladder),
) -> StreamingResponse:
    """Token-streaming twin of `/chat` — the browser UI's primary path.

    Emits Server-Sent Events: a leading `{"conversation_id": "..."}`, then
    `{"reasoning": "..."}` for Qwen3 thinking tokens and `{"delta": "..."}` for answer
    tokens, then a final
    `{"done": true, "conversation_id", "completion_tokens", "elapsed_s", "tokens_per_second"}`.

    Admission-controlled on the student's session so the classroom demo (30 phones, 2 engine
    slots) queues gracefully with a 'you're next' message instead of piling unbounded
    concurrent streams onto the engine — the exact path production traffic takes.
    """
    state = ladder.evaluate()
    decision = sessions.acquire(req.student_id)
    if decision.admission is Admission.REFUSED:
        raise HTTPException(status_code=503, detail=decision.message or ladder.busy_message())

    # Web grounding (P4): RAG-style, opt-in, fail-silent. All three gates or nothing —
    # the ungrounded request must stay byte-identical to what the tutor already serves.
    sources: list[dict] = []
    web_lines = ""
    search_url = os.environ.get("MUTA_SEARCH_URL")
    if req.use_web and search_url:
        from orchestrator.gateway.connectivity import get_connectivity

        if get_connectivity().online() is True:
            snippets = fetch_snippets(req.message, base_url=search_url)
            if snippets:
                web_lines = "\n".join(
                    f"[{i}] {s.title} — {s.snippet}" for i, s in enumerate(snippets, start=1)
                )
                sources = [{"title": s.title, "url": s.url} for s in snippets]

    # Retrieval grounding (RAG): syllabus corpus chunks, when an index is staged. Degrades
    # silently to model-alone when there is no index (the offline-first default).
    rag_block = _rag_block(req.message)

    system_prompt = assemble_system_prompt(
        load_prompt(req.mode.value),
        persona=req.persona.value,
        language=req.language,
        subject=req.subject.value,
        twin_summary=_twin_summary(req.student_id),
        web_lines=web_lines,
        rag_block=rag_block,
    )

    try:
        cid, user_message_id, events = engine.stream_events_chat(
            student_id=req.student_id,
            message=req.message,
            conversation_id=req.conversation_id,
            system_prompt=system_prompt,
            mode=req.mode.value,
            persona=req.persona.value,
            subject=req.subject.value,
            language=req.language,
            title=req.message[:80],
            regenerate=req.regenerate,  # 'answer now' re-runs this turn without a new user msg
            # §6.5 sampling profiles apply to the UI's primary path too — without them the
            # stream ran at llama-server defaults with NO max_tokens (an unbounded turn is one
            # student holding a slot indefinitely, and with thinking on it filled the context).
            **_apply_thinking(params_for_mode(req.mode.value), req.thinking),
        )
    except Exception:
        # The slot is released in the SSE generator's finally, which only runs once streaming
        # starts. A failure before that (store down, bad prompt) must free the lane here.
        sessions.release(req.student_id)
        raise
    if req.attachment_ids:
        _link_attachments(engine, req.attachment_ids, cid, user_message_id)

    def _sse():
        n = 0
        t_first = t_last = 0.0
        reply_parts: list[str] = []  # answer content only, for the post-stream self-check
        hub = get_hub()
        hub.begin(cid)
        # The id leads the stream rather than arriving only at `done`: a client that stops
        # generation early (human-in-the-loop stop/steer) must already know which conversation
        # its partial reply landed in, or stopping the first reply of a new chat forks a
        # second thread on the next message.
        yield f"data: {json.dumps({'conversation_id': cid})}\n\n"
        try:
            for kind, text in events:
                now = time.monotonic()
                if n == 0:
                    t_first = now
                t_last = now
                n += 1  # reasoning and content both count: the engine decodes both
                hub.tick(cid)  # feeds the live tok/s in the telemetry strip
                key = "reasoning" if kind == "reasoning" else "delta"
                if kind != "reasoning":
                    reply_parts.append(text)
                yield f"data: {json.dumps({key: text})}\n\n"
        except httpx.HTTPError as e:
            log.warning("engine error mid-stream at /chat/stream: %r", e)
            yield f"data: {json.dumps({'error': 'the tutor dropped the connection — try again'})}\n\n"
            return
        finally:
            hub.end(cid)
            # Deterministically close the source generator so its finally (partial-reply
            # persist) runs HERE, on this threadpool thread, the moment the stream ends —
            # instead of waiting for GC after a client disconnect, which could stall every
            # other stream and let an abandoned llama-server slot stay busy. Idempotent.
            _close_events(events)
            sessions.release(req.student_id)  # free the admission slot for the next student
        # Deltas approximate tokens (llama-server streams ~one token per chunk). Rate is the
        # DECODE window — first token to last — so it excludes prefill/time-to-first-token and
        # reads close to the engine's own generation rate rather than being dragged down by a
        # short reply's startup. Still wall-clock (from_wall_clock=True); the engine-true rate
        # is what `/chat` records. Feed the shared window so `make monitor` stays live too.
        elapsed = t_last - t_first
        rate = (n - 1) / elapsed if n > 1 and elapsed > 0 else 0.0
        if rate > 0:
            bench_metrics.record(
                Generation(
                    text="",
                    prompt_tokens=0,
                    completion_tokens=n,
                    elapsed_s=elapsed,
                    tokens_per_second=rate,
                    from_wall_clock=True,
                )
            )
        # Post-stream: self-check the model's explicit arithmetic/algebra and record the turn
        # on the learning twin. Runs here (threadpool, after the stream) so it never adds
        # latency to a token and never blocks the event loop. `verified` is null when nothing
        # was checkable — the UI shows a "✓ checked" badge only on a real True.
        verified, check_note = _run_self_check("".join(reply_parts))
        _touch_twin(req.student_id, req.subject.value, req.message)
        yield "data: " + json.dumps(
            {
                "done": True,
                "conversation_id": cid,
                "completion_tokens": n,
                "elapsed_s": round(elapsed, 3),
                "tokens_per_second": round(rate, 2),
                # Student text leaving the device must never be silent (P3): the UI
                # badges any answer a cloud backend produced.
                "source": getattr(getattr(engine, "client", None), "last_source", None)
                or "local",
                # Grounding sources (P4): empty unless web context shaped this answer.
                "sources": sources,
                # Verified-tool-calls (self-check): True/False when a step was checkable,
                # null otherwise; check_note carries a friendly caution on a contradiction.
                "verified": verified,
                "check_note": check_note,
                # Admission/degradation state, so the UI can show "you're next" and a
                # reduced-capacity notice under classroom load.
                "queued": decision.admission is Admission.QUEUED,
                "queue_position": decision.queue_position,
                "degradation_level": f"L{int(state.level)}",
            }
        ) + "\n\n"

    return StreamingResponse(_sse(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.get("/conversations", response_model=ConversationList, tags=["conversations"])
def conversations(
    student_id: str,
    engine: ChatEngine = Depends(get_engine),
    caller: str = Depends(require_caller),
) -> ConversationList:
    """A student's threads, most recently active first — the UI sidebar. A caller only sees
    their own threads; the query id must match the authenticated identity."""
    if student_id != caller:
        raise HTTPException(status_code=403, detail="you can only list your own conversations")
    rows = engine.store.list_conversations(student_id)
    return ConversationList(
        conversations=[
            ConversationOut(
                id=r["id"],
                student_id=r["student_id"],
                title=r.get("title"),
                mode=r.get("mode"),
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=MessageList,
    tags=["conversations"],
)
def conversation_messages(
    conversation_id: str,
    engine: ChatEngine = Depends(get_engine),
    caller: str = Depends(require_caller),
) -> MessageList:
    """Full history with attachment refs — how the UI reloads a thread after a restart. Scoped
    to the owner: a thread the caller does not own is indistinguishable from a missing one."""
    convo = engine.store.get_conversation(conversation_id)
    if convo is None or convo.get("student_id") != caller:
        raise HTTPException(status_code=404, detail="unknown conversation")
    rows = engine.store.list_messages(conversation_id)
    return MessageList(
        conversation_id=conversation_id,
        messages=[
            MessageOut(
                id=m["id"],
                role=m["role"],
                content=m["content"],
                created_at=m["created_at"],
                attachments=[AttachmentRef(**a) for a in m["attachments"]],
            )
            for m in rows
        ],
    )


@router.get(
    "/conversations/{conversation_id}/telemetry",
    response_model=TelemetrySnapshot,
    tags=["ops"],
)
def conversation_telemetry(conversation_id: str) -> TelemetrySnapshot:
    """One-shot telemetry snapshot (curl-able twin of the SSE stream below)."""
    return TelemetrySnapshot(**get_hub().snapshot(conversation_id))


@router.get(
    "/conversations/{conversation_id}/telemetry/stream",
    tags=["ops"],
    responses={200: {"content": {"text/event-stream": {}}, "description": "1 Hz SSE telemetry"}},
)
async def conversation_telemetry_stream(conversation_id: str) -> StreamingResponse:
    """1 Hz telemetry SSE. Async generator on purpose: a sync generator would pin a
    threadpool thread per open strip. GET, so the browser's native EventSource works."""

    async def _gen():
        while True:
            yield f"data: {json.dumps(get_hub().snapshot(conversation_id))}\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(_gen(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.delete(
    "/conversations/{conversation_id}", response_model=ConversationDeleted, tags=["conversations"]
)
def conversation_delete(
    conversation_id: str,
    engine: ChatEngine = Depends(get_engine),
    caller: str = Depends(require_caller),
) -> ConversationDeleted:
    """Delete one of the caller's own threads. 404 (not a false success) when the caller does
    not own it or it does not exist — a client cannot destroy another student's history."""
    if not engine.store.delete_conversation(conversation_id, owner_id=caller):
        raise HTTPException(status_code=404, detail="unknown conversation")
    return ConversationDeleted(id=conversation_id)


@router.get(
    "/attachments/{attachment_id}",
    tags=["conversations"],
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}, "description": "Raw bytes"}},
)
def attachment(
    attachment_id: int,
    engine: ChatEngine = Depends(get_engine),
    caller: str = Depends(caller_from_token),
) -> Response:
    """Serve an attachment the caller owns. Ownership is checked at the store (owner or the
    owner of the linked conversation); a miss is a 404, so ids stay non-probeable. Served as an
    inert `nosniff` download with a whitelisted content type (never the client-set one)."""
    row = engine.store.get_attachment(attachment_id, owner_id=caller)
    if row is None:
        raise HTTPException(status_code=404, detail="unknown attachment")
    mime = row["mime"] if row["mime"] in _SAFE_ATTACHMENT_MIME else "application/octet-stream"
    return Response(content=bytes(row["data"]), media_type=mime, headers=_ATTACHMENT_HEADERS)


@router.post("/auth/session", response_model=AuthTokenResponse, tags=["ops"])
def auth_session(req: AuthTokenRequest) -> AuthTokenResponse:
    """Mint a bearer token for a per-device learner id. With MUTA_AUTH_SECRET set the token is
    HMAC-signed (unforgeable); without it the token is the id itself (opaque per-device
    secret). The client sends it as `Authorization: Bearer <token>` on data endpoints."""
    try:
        token = mint_token(req.student_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return AuthTokenResponse(student_id=req.student_id, token=token)


@router.delete("/students/{student_id}", response_model=StudentErased, tags=["ops"])
def student_erase(
    student_id: str,
    engine: ChatEngine = Depends(get_engine),
    caller: str = Depends(require_caller),
) -> StudentErased:
    """Data-subject erasure: delete everything owned by a student (conversations + cascaded
    messages/attachments, owned orphan attachments, settings). A caller may only erase their
    own data. Returns the removed counts as a receipt."""
    if caller != student_id:
        raise HTTPException(status_code=403, detail="you can only erase your own data")
    counts = engine.store.delete_student(student_id)
    log.info("erased data for student %s: %s", student_id, counts)
    return StudentErased(student_id=student_id, **counts)


@router.post("/diagnose", response_model=DiagnoseResponse, tags=["tutor"])
def diagnose(req: DiagnoseRequest, caller: str = Depends(require_caller)) -> DiagnoseResponse:
    """A student's weak spots + a concrete practice plan, from their learning twin. Mastery is
    only ever populated by real evidence (checked exam answers, §exam/answer), so a brand-new
    student gets a fundamentals-first starter plan rather than an invented weakness."""
    if req.student_id != caller:
        raise HTTPException(status_code=403, detail="you can only diagnose your own progress")
    twin = get_twin_store().load(req.student_id)
    weak = twin.weakest(3)
    if not weak:
        weak = [req.topic] if req.topic else [f"{req.subject.value} fundamentals"]
    plan = [f"Day {i + 1}: focused practice on {topic}" for i, topic in enumerate(weak)]
    plan.append("Day 4: mixed review of the above, no hints")
    plan.append("Day 5: a timed past-paper set on your weakest topic")
    return DiagnoseResponse(student_id=req.student_id, weak_topics=weak, plan=plan)


@router.post("/generate_question", response_model=GenerateQuestionResponse, tags=["exam"])
def generate_question(req: GenerateQuestionRequest) -> GenerateQuestionResponse:
    """WAEC/WASSCE-style items from the offline question bank (orchestrator/exam/bank.py),
    filtered by subject/topic/difficulty. Deterministic for a given request."""
    from orchestrator.exam.bank import generate as generate_from_bank

    items = generate_from_bank(
        req.subject.value, req.topic, req.difficulty, req.exam_board, req.count
    )
    return GenerateQuestionResponse(questions=[GeneratedQuestion(**it) for it in items])


@router.get("/mastery/{student_id}", response_model=MasteryResponse, tags=["tutor"])
def mastery(
    student_id: str, subject: Subject = Subject.math, caller: str = Depends(require_caller)
) -> MasteryResponse:
    """The student's mastery map + next-best topic, from their learning twin."""
    if student_id != caller:
        raise HTTPException(status_code=403, detail="you can only view your own mastery")
    twin = get_twin_store().load(student_id)
    weakest = twin.weakest(1)
    return MasteryResponse(
        student_id=student_id,
        subject=subject,
        mastery=twin.mastery,
        next_topic=weakest[0] if weakest else None,
    )


@router.post("/exam/answer", response_model=AnswerCheckResponse, tags=["exam"])
def exam_answer(
    req: ExamAnswerRequest,
    verifier: AnswerVerifier = Depends(get_verifier),
    caller: str = Depends(require_caller),
) -> AnswerCheckResponse:
    """Score a student's answer against the known-correct one and move their mastery on that
    topic — the honest evidence path that makes /mastery and /diagnose real. Mastery only
    changes when the sandbox actually returned a verdict (checked); an undecidable check
    leaves the record untouched rather than punishing the student for the tool's limits."""
    if req.student_id != caller:
        raise HTTPException(status_code=403, detail="you can only submit your own answers")
    outcome = verifier.check_text(req.candidate, req.expected, tolerance=req.tolerance)
    if outcome.checked:
        try:
            store = get_twin_store()
            twin = store.load(req.student_id)
            twin.record_mastery(req.topic, 1.0 if outcome.verified else 0.0)
            if not outcome.verified:
                twin.record_error(req.topic)
            store.save(twin)
        except Exception:  # noqa: BLE001 — a twin write must not fail the student's submission
            log.warning("mastery update failed for %s", req.student_id, exc_info=True)
    return AnswerCheckResponse(
        verified=outcome.verified,
        checked=outcome.checked,
        normalized_candidate=outcome.normalized_candidate,
        normalized_expected=outcome.normalized_expected,
        detail=outcome.detail,
    )


@router.post("/verify", response_model=VerifyResponse, tags=["math"])
def verify(req: VerifyRequest, verifier: AnswerVerifier = Depends(get_verifier)) -> VerifyResponse:
    """Check a claim of the form `lhs == rhs` (or `lhs = rhs`) in the SymPy sandbox.

    The single-expression shape this endpoint has always had; `/tutor/verify` is the
    two-sided form the tool loop uses.
    """
    text = req.expression.strip()
    parts = re.split(r"==|(?<![<>!=])=(?!=)", text, maxsplit=1)
    if len(parts) != 2 or not all(p.strip() for p in parts):
        return VerifyResponse(
            verified=False,
            detail="expected a claim of the form 'lhs == rhs' (e.g. 'd/dx(x^2) == 2*x')",
        )
    outcome = verifier.check(parts[0], parts[1])
    return VerifyResponse(
        verified=outcome.verified,
        normalized=outcome.normalized_candidate or None,
        detail=outcome.detail or (None if outcome.checked else "verifier unavailable"),
    )


# --- TDD §7.2 surface --------------------------------------------------------------------


@router.post("/tutor/chat", response_model=TutorReply, tags=["tutor"])
def tutor_chat(
    turn: ChatTurn,
    engine: ChatEngine = Depends(get_engine),
    sessions: SessionManager = Depends(get_sessions),
    ladder: DegradationLadder = Depends(get_ladder),
) -> TutorReply:
    """One tutoring turn, admission-controlled (§8.2) and ladder-aware (§5.3).

    Set `stream: false` for this JSON shape; `stream: true` (the default) is served by
    `/tutor/chat/stream`, which speaks SSE. Both take the same body.
    """
    state = ladder.evaluate()
    decision = sessions.acquire(turn.session_id)
    if decision.admission is Admission.REFUSED:
        # 503 with a human message, not an error page: judges are non-technical (C-7).
        raise HTTPException(status_code=503, detail=decision.message or ladder.busy_message())

    student_id = turn.student_id or turn.session_id
    try:
        result = engine.chat(
            student_id=student_id,
            message=turn.text,
            conversation_id=turn.session_id,
            system_prompt=load_prompt(_prompt_for(turn.mode)),
            mode=turn.mode.value,
            language=turn.lang,
            **params_for_mode(turn.mode.value),
        )
    except httpx.HTTPError as e:
        raise _handle_engine_error(e, where="/tutor/chat") from e
    finally:
        sessions.release(turn.session_id)

    if result.generation is not None:
        bench_metrics.record(result.generation)
    return TutorReply(
        session_id=turn.session_id,
        reply=result.reply,
        mode=turn.mode,
        queued=decision.admission is Admission.QUEUED,
        queue_position=decision.queue_position,
        degradation_level=f"L{int(state.level)}",
    )


def _prompt_for(mode: TutorMode) -> str:
    return {"dialogue": "socratic", "solution": "subgoal", "marking": "subgoal", "hint": "socratic"}[
        mode.value
    ]


@router.post(
    "/tutor/chat/stream",
    tags=["tutor"],
    responses={200: {"content": {"text/event-stream": {}}, "description": "SSE token stream"}},
)
def tutor_chat_stream(
    turn: ChatTurn,
    engine: ChatEngine = Depends(get_engine),
    sessions: SessionManager = Depends(get_sessions),
    ladder: DegradationLadder = Depends(get_ladder),
) -> StreamingResponse:
    """Token-streaming twin of `/tutor/chat` (§7.2: the tutoring turn is SSE).

    Events: `{"reasoning": …}` while the model thinks, `{"delta": …}` per answer token, then
    a final `{"done": true, …}`. Time-to-first-token is the number a student feels (SC-3:
    < 2.5 s), so the stream starts before the answer is finished, not after.
    """
    state = ladder.evaluate()
    decision = sessions.acquire(turn.session_id)
    if decision.admission is Admission.REFUSED:
        raise HTTPException(status_code=503, detail=decision.message or ladder.busy_message())

    try:
        cid, _user_message_id, events = engine.stream_events_chat(
            student_id=turn.student_id or turn.session_id,
            message=turn.text,
            conversation_id=turn.session_id,
            system_prompt=load_prompt(_prompt_for(turn.mode)),
            mode=turn.mode.value,
            language=turn.lang,
            **params_for_mode(turn.mode.value),
        )
    except Exception:
        # The generator's finally releases the slot only once streaming starts; a failure
        # before that (store down, bad prompt) must not consume a decode lane forever.
        sessions.release(turn.session_id)
        raise

    def _sse():
        started = time.monotonic()
        first_token_at = 0.0
        count = 0
        try:
            for kind, text in events:
                if count == 0:
                    first_token_at = time.monotonic()
                count += 1
                key = "reasoning" if kind == "reasoning" else "delta"
                yield f"data: {json.dumps({key: text})}\n\n"
        except httpx.HTTPError as e:
            log.warning("engine error mid-stream at /tutor/chat/stream: %r", e)
            yield f"data: {json.dumps({'error': 'the tutor dropped the connection — try again'})}\n\n"
            return
        finally:
            sessions.release(turn.session_id)
            _close_events(events)  # deterministic partial-persist off the event loop (see /chat/stream)
        yield "data: " + json.dumps(
            {
                "done": True,
                "session_id": cid,
                "completion_tokens": count,
                "ttft_s": round(first_token_at - started, 3) if count else None,
                "degradation_level": f"L{int(state.level)}",
            }
        ) + "\n\n"

    return StreamingResponse(_sse(), media_type="text/event-stream", headers=_SSE_HEADERS)


_IMAGE_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


@router.post("/tutor/vision", response_model=VisionReply, tags=["tutor"])
async def tutor_vision(
    session_id: str = Form(...),
    image: UploadFile = File(...),
    conversation_id: str | None = Form(None),
    vision: VisionManager = Depends(get_vision),
    engine: ChatEngine = Depends(get_engine),
) -> VisionReply:
    """Photo of handwritten work → transcription (S2).

    Two refusals, both friendly: the image guard (too big, wrong format) and the ladder
    (no memory for a vision instance). Neither is an error — the student is told to type the
    problem instead, and the tutor keeps working.
    """
    raw = await image.read()
    try:
        prepared = prepare_image(raw)
    except ImageRejected as e:
        return VisionReply(session_id=session_id, accepted=False, detail=str(e))

    # Persist the (guard-normalised) image so the thread's history can re-render it. Storage
    # failure must not block tutoring — the transcription path continues without an id.
    attachment_id: int | None = None
    try:
        attachment_id = await run_in_threadpool(
            engine.store.add_attachment,
            "image",
            _IMAGE_MIME.get(prepared.format, "application/octet-stream"),
            prepared.data,
            conversation_id=conversation_id,
            owner_id=session_id,
        )
    except Exception:  # noqa: BLE001 — best-effort persistence
        log.warning("failed to persist vision attachment for session %s", session_id, exc_info=True)
        attachment_id = None

    # Both `ensure()` (polls for up to MUTA_RT_VISION_STARTUP_S on a cold spawn) and
    # `transcribe()` (a blocking httpx.post, up to request_timeout_s) are synchronous. This
    # handler is async, so run them in the threadpool — otherwise one vision request freezes
    # the single event loop and stalls every other phone in the classroom mid-stream.
    try:
        base_url = await run_in_threadpool(vision.ensure)  # spawns CORE-VISION if needed
    except VisionDenied as e:
        return VisionReply(
            session_id=session_id, accepted=False, detail=str(e), attachment_id=attachment_id
        )

    # The vision instance is stateless and TTL-killable by design: it returns a transcription,
    # and the *text* session carries the conversation (§6.3, S2). A transport failure OR a
    # malformed-but-200 reply is S2's honest fallback, never a 500 in a non-technical judge's face.
    # The same per-request budget the text engine gets: a real photo at the Qwen-VL
    # 1024-image-token floor needs minutes of prefill on a slow box, and the client's 120 s
    # default silently cut every one of them off mid-read. `in_use()` keeps the TTL reaper
    # off a server that is mid-transcription for exactly as long.
    def _read() -> str:
        with vision.in_use():
            client = VisionClient(base_url, timeout=RuntimeConfig().request_timeout_s)
            return client.transcribe(prepared.data, prepared.format)

    try:
        transcription = await run_in_threadpool(_read)
    except (httpx.HTTPError, VisionResponseError):
        return VisionReply(
            session_id=session_id,
            accepted=False,
            detail="the image reader didn't respond — type the problem and I'll work through it",
            attachment_id=attachment_id,
        )
    return VisionReply(
        session_id=session_id,
        transcription=transcription,
        accepted=True,
        attachment_id=attachment_id,
    )


@router.post("/tutor/verify", response_model=AnswerCheckResponse, tags=["math"])
def tutor_verify(
    req: AnswerCheckRequest, verifier: AnswerVerifier = Depends(get_verifier)
) -> AnswerCheckResponse:
    """Candidate vs expected, via SymPy in the sandbox (§7.5).

    `checked=False` means no verdict was possible (no answer found, sandbox down) — the
    caller must not report that as "wrong".
    """
    outcome = verifier.check_text(req.candidate, req.expected, tolerance=req.tolerance)
    return AnswerCheckResponse(
        verified=outcome.verified,
        checked=outcome.checked,
        normalized_candidate=outcome.normalized_candidate,
        normalized_expected=outcome.normalized_expected,
        detail=outcome.detail,
    )


@router.post("/tutor/render", response_model=RenderResponse, tags=["tutor"])
def tutor_render(
    req: RenderRequest, renderer: DiagramRenderer = Depends(get_renderer)
) -> RenderResponse:
    """Model-emitted plotting code → SVG, sandboxed (§7.5, S5). A failure returns `ok=False`
    with the error, never a broken image."""
    outcome = renderer.render(req.code, kind=req.kind)
    return RenderResponse(
        svg=outcome.svg,
        ok=outcome.ok,
        error=outcome.error,
        fallback_text=outcome.fallback_text,
    )


@router.post("/session/{session_id}/suspend", response_model=SessionActionResponse, tags=["ops"])
def session_suspend(
    session_id: str, sessions: SessionManager = Depends(get_sessions)
) -> SessionActionResponse:
    """Persist a session's KV and free its slot (§8.3)."""
    ok = sessions.evict(session_id)
    return SessionActionResponse(
        session_id=session_id,
        action="suspend",
        ok=ok,
        detail="" if ok else "session held no slot",
    )


@router.post("/session/{session_id}/resume", response_model=SessionActionResponse, tags=["ops"])
def session_resume(
    session_id: str, sessions: SessionManager = Depends(get_sessions)
) -> SessionActionResponse:
    """Bind a slot for a session, restoring its snapshot when one survives."""
    decision = sessions.acquire(session_id)
    if decision.admission is Admission.REFUSED:
        raise HTTPException(status_code=503, detail=decision.message)
    return SessionActionResponse(
        session_id=session_id,
        action="resume",
        ok=decision.admitted,
        detail=decision.message or decision.admission.value,
    )


@router.get("/metrics", response_model=SystemStatus, tags=["ops"])
def metrics(
    ladder: DegradationLadder = Depends(get_ladder),
    sessions: SessionManager = Depends(get_sessions),
    vision: VisionManager = Depends(get_vision),
) -> SystemStatus:
    """Local health panel data (§12). All local: no exporter, no network, no dashboards."""
    engine: dict = {}
    try:
        engine = {"slots": get_slot_client().slots()}
    except SlotError as e:
        engine = {"error": str(e)}
    return SystemStatus(
        degradation=ladder.evaluate().as_dict(),
        sessions=sessions.status(),
        vision=vision.status(),
        engine=engine,
    )
