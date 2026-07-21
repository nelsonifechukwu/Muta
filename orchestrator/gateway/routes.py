"""The public `/v1` contract surface.

Defined as a router so it can be included on the assembled app (`orchestrator.main`) and
on the standalone gateway app (`orchestrator.gateway.app`) without duplication. Handlers
are stubbed `501` for now — the shapes come from `contracts`, so the OpenAPI document is
already complete and correct even though the behaviour is not built yet.
"""

from __future__ import annotations

import json
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from contracts.models import (
    ChatRequest,
    ChatResponse,
    DiagnoseRequest,
    DiagnoseResponse,
    GenerateQuestionRequest,
    GenerateQuestionResponse,
    HealthResponse,
    MasteryResponse,
    ReadyResponse,
    Subject,
    VerifyRequest,
    VerifyResponse,
)
from orchestrator import bench_metrics
from orchestrator.gateway.deps import get_engine, load_prompt
from runtime.chat import ChatEngine
from runtime.client import Generation

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

    Emits Server-Sent Events: one `{"delta": "..."}` per token, then a final
    `{"done": true, "conversation_id", "completion_tokens", "elapsed_s", "tokens_per_second"}`.
    """
    cid, tokens = engine.stream_chat(
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
            for delta in tokens:
                now = time.monotonic()
                if n == 0:
                    t_first = now
                t_last = now
                n += 1
                yield f"data: {json.dumps({'delta': delta})}\n\n"
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
def verify(req: VerifyRequest) -> VerifyResponse:
    # TODO(Lane B, 25 Jul): delegate to the math service (SymPy/NumPy). Cheapest
    # hallucination fix available (ROADMAP §3).
    raise _todo("verify")
