"""The public `/v1` contract surface.

Defined as a router so it can be included on the assembled app (`orchestrator.main`) and
on the standalone gateway app (`orchestrator.gateway.app`) without duplication. Handlers
are stubbed `501` for now — the shapes come from `contracts`, so the OpenAPI document is
already complete and correct even though the behaviour is not built yet.
"""

from __future__ import annotations

import json
import re
import time

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from contracts.models import (
    AnswerCheckRequest,
    AnswerCheckResponse,
    ChatRequest,
    ChatResponse,
    ChatTurn,
    DiagnoseRequest,
    DiagnoseResponse,
    GenerateQuestionRequest,
    GenerateQuestionResponse,
    HealthResponse,
    MasteryResponse,
    ReadyResponse,
    RenderRequest,
    RenderResponse,
    SessionActionResponse,
    Subject,
    SystemStatus,
    TutorMode,
    TutorReply,
    VerifyRequest,
    VerifyResponse,
    VisionReply,
)
from orchestrator import bench_metrics
from orchestrator.gateway.deps import (
    get_engine,
    get_ladder,
    get_renderer,
    get_sessions,
    get_slot_client,
    get_verifier,
    get_vision,
    load_prompt,
)
from orchestrator.gateway.images import ImageRejected, prepare_image
from orchestrator.gateway.ladder import DegradationLadder
from orchestrator.gateway.sampling import params_for_mode
from orchestrator.gateway.sessions import Admission, SessionManager
from orchestrator.tools.renderer import DiagramRenderer
from orchestrator.tools.verifier import AnswerVerifier
from runtime.chat import ChatEngine
from runtime.client import Generation
from runtime.slots import SlotError
from runtime.vision import VisionDenied, VisionManager

router = APIRouter()


def _todo(what: str) -> HTTPException:
    return HTTPException(status_code=501, detail=f"{what} not implemented")


@router.get("/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    return HealthResponse(service="gateway")


@router.get("/ready", response_model=ReadyResponse, tags=["ops"])
def ready(engine: ChatEngine = Depends(get_engine)) -> ReadyResponse:
    checks = {"gateway": True, "inference": _inference_up(engine)}
    return ReadyResponse(ready=all(checks.values()), checks=checks)


def _inference_up(engine: ChatEngine) -> bool:
    try:
        return httpx.get(f"{engine.client.base_url}/health", timeout=2.0).status_code == 200
    except httpx.HTTPError:
        return False


@router.post("/chat", response_model=ChatResponse, tags=["tutor"])
def chat(req: ChatRequest, engine: ChatEngine = Depends(get_engine)) -> ChatResponse:
    """Multi-turn tutoring turn. Memory is keyed by `conversation_id`; omit it to start a
    new thread. The mode selects the system prompt (ROADMAP 18 Jul, stable-prefix design)."""
    try:
        result = engine.chat(
            student_id=req.student_id,
            message=req.message,
            conversation_id=req.conversation_id,
            system_prompt=load_prompt(req.mode.value),
            mode=req.mode.value,
            persona=req.persona.value,
            subject=req.subject.value,
            language=req.language,
        )
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
        raise HTTPException(
            status_code=503,
            detail="inference engine unreachable — start llama-server (see RUN.md)",
        ) from e
    # Telemetry for the external HUD (bench/monitor.py), which never sees a generation itself.
    if result.generation is not None:
        bench_metrics.record(result.generation)
    return ChatResponse(
        student_id=req.student_id,
        conversation_id=result.conversation_id,
        mode=req.mode,
        reply=result.reply,
    )


@router.post("/chat/stream", include_in_schema=False)
def chat_stream(req: ChatRequest, engine: ChatEngine = Depends(get_engine)) -> StreamingResponse:
    """Token-streaming twin of `/chat`, for the terminal TUI (bench/tui.py).

    Deliberately `include_in_schema=False`: it is NOT part of the frozen `/v1` contract, so
    `contracts/openapi.yaml` stays byte-identical and no client may bind to it. It exists only
    so a local dev client can render tokens as they arrive; the blocking `/chat` remains the
    one contract surface. Same prompt/persona wiring as `/chat`, so tutoring behaviour matches.

    Emits Server-Sent Events: `{"reasoning": "..."}` for Qwen3 thinking tokens and
    `{"delta": "..."}` for answer tokens, then a final
    `{"done": true, "conversation_id", "completion_tokens", "elapsed_s", "tokens_per_second"}`.
    """
    cid, events = engine.stream_events_chat(
        student_id=req.student_id,
        message=req.message,
        conversation_id=req.conversation_id,
        system_prompt=load_prompt(req.mode.value),
        mode=req.mode.value,
        persona=req.persona.value,
        subject=req.subject.value,
        language=req.language,
    )

    def _sse():
        n = 0
        t_first = t_last = 0.0
        try:
            for kind, text in events:
                now = time.monotonic()
                if n == 0:
                    t_first = now
                t_last = now
                n += 1  # reasoning and content both count: the engine decodes both
                key = "reasoning" if kind == "reasoning" else "delta"
                yield f"data: {json.dumps({key: text})}\n\n"
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout):
            yield f"data: {json.dumps({'error': 'inference engine unreachable'})}\n\n"
            return
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
        yield "data: " + json.dumps(
            {
                "done": True,
                "conversation_id": cid,
                "completion_tokens": n,
                "elapsed_s": round(elapsed, 3),
                "tokens_per_second": round(rate, 2),
            }
        ) + "\n\n"

    return StreamingResponse(_sse(), media_type="text/event-stream")


@router.post("/diagnose", response_model=DiagnoseResponse, tags=["tutor"])
def diagnose(req: DiagnoseRequest) -> DiagnoseResponse:
    raise _todo("diagnose")


@router.post("/generate_question", response_model=GenerateQuestionResponse, tags=["exam"])
def generate_question(req: GenerateQuestionRequest) -> GenerateQuestionResponse:
    raise _todo("generate_question")


@router.get("/mastery/{student_id}", response_model=MasteryResponse, tags=["tutor"])
def mastery(student_id: str, subject: Subject = Subject.math) -> MasteryResponse:
    raise _todo("mastery")


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
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
        raise HTTPException(status_code=503, detail="inference engine unreachable") from e
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

    cid, events = engine.stream_events_chat(
        student_id=turn.student_id or turn.session_id,
        message=turn.text,
        conversation_id=turn.session_id,
        system_prompt=load_prompt(_prompt_for(turn.mode)),
        mode=turn.mode.value,
        language=turn.lang,
        **params_for_mode(turn.mode.value),
    )

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
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout):
            yield f"data: {json.dumps({'error': 'inference engine unreachable'})}\n\n"
            return
        finally:
            sessions.release(turn.session_id)
        yield "data: " + json.dumps(
            {
                "done": True,
                "session_id": cid,
                "completion_tokens": count,
                "ttft_s": round(first_token_at - started, 3) if count else None,
                "degradation_level": f"L{int(state.level)}",
            }
        ) + "\n\n"

    return StreamingResponse(_sse(), media_type="text/event-stream")


@router.post("/tutor/vision", response_model=VisionReply, tags=["tutor"])
async def tutor_vision(
    session_id: str = Form(...),
    image: UploadFile = File(...),
    vision: VisionManager = Depends(get_vision),
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

    try:
        vision.ensure()
    except VisionDenied as e:
        return VisionReply(session_id=session_id, accepted=False, detail=str(e))

    # The vision instance is stateless and TTL-killable by design: it returns a transcription,
    # and the *text* session carries the conversation (§6.3, S2). Wiring the mtmd completion
    # call is Lane C's next step; the guard, the spawn and the fallbacks are what this
    # endpoint owes the rest of the system.
    raise HTTPException(
        status_code=501,
        detail=(
            f"image accepted ({prepared.width}x{prepared.height}, {prepared.bytes} bytes) and "
            "CORE-VISION is up; the mtmd completion call is not wired yet"
        ),
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
