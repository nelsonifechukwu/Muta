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
import contextlib
import ipaddress
import json
import logging
import os
import re
import threading
import time
import unicodedata
import uuid
from functools import lru_cache

import httpx
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
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
    GenerationList,
    GenerationStarted,
    GenerationStatus,
    GenerationStopped,
    HealthResponse,
    LearningResource,
    MasteryResponse,
    MessageList,
    MessageOut,
    ModelCatalogResponse,
    ModelSelectRequest,
    ModelSelectResponse,
    PowerStatus,
    ReadyResponse,
    RenderRequest,
    RenderResponse,
    ResourceDeleted,
    ResourceList,
    SessionActionResponse,
    StudentErased,
    Subject,
    SystemStatus,
    TelemetrySnapshot,
    TutorMode,
    TutorReply,
    UserSettings,
    VerifyRequest,
    VerifyResponse,
    VisionReply,
)
from orchestrator import bench_metrics
from orchestrator.gateway.auth import (
    caller_from_token,
    is_operator_request,
    member_write_lease,
    mint_token,
    operator_student_id,
    optional_caller,
    principal_from_request,
    request_token,
    require_caller,
    resolve_principal,
)
from orchestrator.gateway.auxiliary import (
    AuxiliaryQueueFull,
    OwnerWorkRejected,
    auxiliary_slot,
    get_owner_work_manager,
)
from orchestrator.gateway.deps import (
    get_capacity_controller,
    get_engine,
    get_generation_manager,
    get_ladder,
    get_model_manager,
    get_power_governor,
    get_preamble_writer,
    get_renderer,
    get_resource_service,
    get_sessions,
    get_slot_client,
    get_twin_store,
    get_verifier,
    get_vision,
    load_prompt,
    refresh_engine_dependencies,
    runtime_lifecycle,
)
from orchestrator.gateway.generations import (
    GenerationCapacityError,
    GenerationJob,
    GenerationManager,
)
from orchestrator.gateway.images import MAX_UPLOAD_BYTES as MAX_IMAGE_UPLOAD_BYTES
from orchestrator.gateway.images import ImageRejected, prepare_image
from orchestrator.gateway.ladder import DegradationLadder
from orchestrator.gateway.power import PowerGovernor
from orchestrator.gateway.preamble import with_preamble
from orchestrator.gateway.prompting import assemble_system_prompt, response_language_instruction
from orchestrator.gateway.sampling import params_for_mode
from orchestrator.gateway.selfcheck import scan_claims, self_check
from orchestrator.gateway.sessions import Admission, SessionManager
from orchestrator.gateway.share_routes import strict_share_security, verify_host_csrf
from orchestrator.gateway.sharing import SESSION_COOKIE, AuthenticationError, get_sharing_service
from orchestrator.gateway.visualizations import (
    append_visualization,
    generate_visualization,
    turn_instruction,
    wants_live_visual,
)
from orchestrator.gateway.websearch import fetch_snippets
from orchestrator.retrieval.resources import (
    ResourceNotFound,
    ResourceSelectionRequired,
    ResourceService,
    ResourceUnavailable,
    safe_resource_name,
)
from orchestrator.telemetry import get_hub
from orchestrator.tools.renderer import DiagramRenderer
from orchestrator.tools.verifier import AnswerVerifier
from runtime.chat import ChatEngine, strip_visualization_protocol
from runtime.client import Generation, InferenceStreamError
from runtime.config import RuntimeConfig
from runtime.model_catalog import ModelSwitchError
from runtime.slots import SlotError
from runtime.ttft import PreambleWriter
from runtime.vision import VisionDenied, VisionManager
from runtime.vision_client import VisionClient, VisionResponseError

router = APIRouter()

log = logging.getLogger("muta.gateway.routes")

# SSE through a proxy: no caching, and tell nginx not to buffer the stream.
_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

_CONVERSATION_TITLE_LIMIT = 80
_TITLE_RESOURCE_MENTION = re.compile(r"@\{([^{}\n]+)\}")
_TITLE_BIDI_CONTROLS = re.compile(r"[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]")
_TITLE_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([.,;:!?\])])")


def _title_resource_name(value: str) -> str:
    """Mirror `resource-mentions.js` display normalization for public-API title text."""
    name = _TITLE_BIDI_CONTROLS.sub("", value)
    name = "".join(" " if ord(char) < 32 or ord(char) == 127 else char for char in name)
    name = name.replace("{", " ").replace("}", " ").replace("\n", " ")
    name = re.sub(r"\s+", " ", name)
    name = _TITLE_SPACE_BEFORE_PUNCTUATION.sub(r"\1", name).strip()
    return name or "resource.pdf"


def _compact_title_resource_name(name: str, limit: int) -> str:
    if len(name) <= limit:
        return name
    cut = max(0, limit - 1)
    # Never leave a joiner, combining mark, variation selector, or skin-tone modifier dangling
    # before the ellipsis. This is a conservative grapheme boundary for document-title previews.
    while cut and (
        name[cut - 1] == "\u200d"
        or unicodedata.category(name[cut - 1]).startswith("M")
        or "\ufe00" <= name[cut - 1] <= "\ufe0f"
        or "\U0001f3fb" <= name[cut - 1] <= "\U0001f3ff"
    ):
        cut -= 1
    return name[:cut].rstrip() + "…"


def _title_resource_mentions(source: str):
    """Yield the same complete mention grammar accepted by the browser's Unicode parser."""
    for match in _TITLE_RESOURCE_MENTION.finditer(source):
        end = match.end()
        following = source[end : end + 1]
        category = unicodedata.category(following) if following else ""
        if following == "_" or category[:1] in {"L", "N", "M"}:
            continue
        after_dot = source[end + 1 : end + 2] if following == "." else ""
        dot_category = unicodedata.category(after_dot) if after_dot else ""
        if following == "." and dot_category[:1] in {"L", "N"}:
            continue
        yield match


def _has_title_resource_mention(source: str) -> bool:
    return next(_title_resource_mentions(source), None) is not None


def _conversation_title(message: str) -> str:
    """Compact a first turn without cutting through its resource-mention transport token."""
    # Parse before presentation compaction. Normalizing a newline inside malformed ordinary text
    # such as `@{not\na document}` would otherwise synthesize a valid resource mention.
    source = message.strip()
    output: list[str] = []
    used = 0
    cursor = 0
    for match in _title_resource_mentions(source):
        plain = source[cursor : match.start()]
        remaining = _CONVERSATION_TITLE_LIMIT - used
        if len(plain) >= remaining:
            output.append(plain[:remaining])
            return "".join(output)
        output.append(plain)
        used += len(plain)
        remaining = _CONVERSATION_TITLE_LIMIT - used
        name = _title_resource_name(match.group(1))
        token = f"@{{{name}}}"
        if len(token) > remaining:
            name_limit = remaining - 3
            if name_limit < 1:
                return "".join(output)
            compact_name = _compact_title_resource_name(name, name_limit)
            output.append(f"@{{{compact_name}}}")
            return "".join(output)
        output.append(token)
        used += len(token)
        cursor = match.end()
    output.append(source[cursor : cursor + (_CONVERSATION_TITLE_LIMIT - used)])
    return "".join(output)


def _listed_conversation_title(row: dict, store) -> str | None:
    """Repair titles created before mention-aware compaction, without guessing malformed text."""
    title = row.get("title")
    if not isinstance(title, str) or len(title) != _CONVERSATION_TITLE_LIMIT:
        return title
    opener = title.rfind("@{")
    if opener < 0 or "}" in title[opener + 2 :]:
        return title
    message = store.get_first_user_message(row["id"])
    if message is not None and _has_title_resource_mention(message.get("content", "")):
        return _conversation_title(message.get("content", ""))
    return title

# Serve stored attachments as inert downloads: never let a browser MIME-sniff or render bytes
# a student uploaded (an audio/HTML polyglot with a client-set text/html type was a stored-XSS
# vector). Constrain the served type to a known-safe allowlist, too.
_ATTACHMENT_HEADERS = {"X-Content-Type-Options": "nosniff", "Content-Disposition": "attachment"}
_SAFE_ATTACHMENT_MIME = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "audio/webm",
    "audio/ogg",
    "audio/mpeg",
    "audio/mp4",
    "audio/wav",
    "audio/x-wav",
}

_MAX_RESOURCE_BYTES = 32 * 1024 * 1024
_PDF_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Disposition": "inline",
    "Cache-Control": "private, no-store",
    "Referrer-Policy": "no-referrer",
}


def _resource_model(row: dict) -> LearningResource:
    return LearningResource(
        id=row["id"],
        name=row["name"],
        mime=row["mime"],
        status=row["status"],
        page_count=row.get("page_count"),
        error=row.get("error"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _resource_grounding(
    req: ChatRequest, *, owner_id: str, service: ResourceService
) -> tuple[str, list[dict]]:
    if not req.use_rag:
        return "", []
    try:
        selected = service.preflight(owner_id, req.resource_ids)
        hits = service.search(owner_id, req.resource_ids, req.message)
    except ResourceSelectionRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ResourceUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ResourceNotFound as exc:
        raise HTTPException(status_code=404, detail="unknown resource") from exc
    citations = [
        {
            "kind": "resource",
            "resource_id": hit["resource_id"],
            "title": hit["title"],
            "page": hit["page"],
            "chunk_index": hit["chunk_index"],
            "excerpt": hit["excerpt"],
        }
        for hit in hits
    ]
    return service.render_context(hits, selected), citations


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


def _incomplete_stream_message(*, partial_saved: bool) -> str:
    if partial_saved:
        return "The tutor could not resume automatically. Your partial answer is saved."
    return "The tutor could not complete that answer automatically. Please try again."


def _handle_engine_error(exc: Exception, *, where: str) -> HTTPException:
    """Map any llama-server failure to a friendly, student-safe 503 — and record the real
    cause server-side so an operator can diagnose it. A 400 is almost always context overflow
    (a long conversation), which the student can act on; transport errors mean the engine is
    down or slow."""
    if isinstance(exc, InferenceStreamError):
        log.warning("engine returned an incomplete answer at %s: %s", where, exc)
        return HTTPException(
            status_code=503,
            detail=(
                "the tutor could not finish this answer automatically — the partial reply is saved"
                if exc.partial_text
                else "the tutor could not finish this answer automatically — please try again"
            ),
        )
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


def _is_loopback_peer(peer_host: str) -> bool:
    try:
        return ipaddress.ip_address(peer_host).is_loopback
    except ValueError:
        return False


def _model_switch_allowed(source: Request | str) -> bool:
    if os.environ.get("MUTA_ALLOW_MODEL_SWITCH") != "1":
        return False
    if isinstance(source, str):
        return _is_loopback_peer(source)
    return is_operator_request(source)


def _unified_loopback_identity(peer_host: str) -> bool:
    return os.environ.get("MUTA_UNIFY_LOOPBACK_CHATS") == "1" and _is_loopback_peer(peer_host)


@router.get("/models", response_model=ModelCatalogResponse, tags=["runtime"])
def models(request: Request) -> ModelCatalogResponse:
    manager = get_model_manager()
    if manager is None:
        return ModelCatalogResponse()
    status = manager.status()
    principal = principal_from_request(request)
    status["selection_enabled"] = bool(
        _model_switch_allowed(request)
        and (not strict_share_security() or (principal and principal.role == "host"))
    )
    return ModelCatalogResponse.model_validate(status)


@router.post("/models/select", response_model=ModelSelectResponse, tags=["runtime"])
def select_model(
    request: Request,
    req: ModelSelectRequest,
    csrf: str | None = Header(default=None, alias="X-Muta-CSRF"),
    generations: GenerationManager = Depends(get_generation_manager),
) -> ModelSelectResponse:
    manager = get_model_manager()
    if manager is None:
        raise HTTPException(status_code=409, detail="model switching is unavailable in this mode")
    if not _model_switch_allowed(request):
        raise HTTPException(
            status_code=403,
            detail="only the laptop operator can change the shared tutor model",
        )
    if strict_share_security():
        principal = principal_from_request(request)
        if (
            principal is None
            or principal.role != "host"
            or not principal.session_id
            or not get_sharing_service().verify_csrf(principal.session_id, csrf)
        ):
            raise HTTPException(status_code=403, detail="invalid host request token")
    try:
        profile = None

        def replace_model():
            nonlocal profile
            if not get_vision().stop_for_reconfigure():
                raise GenerationCapacityError(
                    "wait for the active image reading before changing models"
                )
            if strict_share_security() and hasattr(manager, "candidate_config"):
                # Read the persisted mode and hash/price the target only after idle admission
                # is locked. A concurrent Host setting change cannot install a stale profile.
                mode = get_sharing_service().settings()["memory_mode"]
                candidate = manager.candidate_config(req.model_id)
                profile = get_capacity_controller().planner.plan(mode, candidate)
                if not profile.fits:
                    raise GenerationCapacityError(
                        "that model cannot fit safely under the active Host memory policy"
                    )
                status = manager.switch(
                    req.model_id,
                    n_parallel=profile.n_parallel,
                    n_ctx=profile.n_ctx,
                )
            else:
                status = manager.switch(req.model_id)
            refresh_engine_dependencies(profile)
            return status

        with runtime_lifecycle():
            status = generations.run_when_idle(replace_model)
    except GenerationCapacityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ModelSwitchError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    status["selection_enabled"] = True
    return ModelSelectResponse.model_validate(status)


def _url_up(url: str) -> bool:
    try:
        return httpx.get(url, timeout=2.0).status_code == 200
    except httpx.HTTPError:
        return False


def _db_up(dsn: str) -> bool:
    if dsn.startswith("sqlite:///"):
        try:
            from runtime.sqlite_memory import SQLiteConversationStore

            store = SQLiteConversationStore(dsn)
            try:
                return store.ping()
            finally:
                store.close()
        except Exception:
            return False
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=2) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


def _twin_summary(student_id: str) -> str:
    """The learning-twin session summary for this student, best-effort (never fails a turn)."""
    try:
        return get_twin_store().load(student_id).prompt_summary()
    except Exception:
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
    except Exception:
        log.warning("twin update failed for %s", student_id, exc_info=True)


#: Extended thinking widens the answer's token room so a longer trace + answer isn't clipped.
_EXTENDED_MAX_TOKENS = 3000


@lru_cache(maxsize=1)
def _extended_reasoning_budget() -> int:
    """The per-request thinking cap for 'Extended', from RuntimeConfig (cached — it's fixed at
    boot)."""
    return RuntimeConfig().reasoning_budget_extended


@lru_cache(maxsize=1)
def _preamble_opts() -> dict:
    """Decode settings for the TTFT preamble. Cached for the same reason as above, and with
    more reason: parsing BaseSettings per request on the path whose entire purpose is to
    shave milliseconds off first paint would be self-defeating."""
    cfg = RuntimeConfig()
    return {
        "seed_text": cfg.ttft_seed_text,
        "max_tokens": cfg.ttft_max_tokens,
        "temperature": cfg.ttft_temperature,
    }


def _apply_thinking(
    params: dict, thinking: str | None, *, extended_budget: int | None = None
) -> dict:
    """Fold the request's thinking level into the sampling params the engine receives. `off`
    disables the Qwen3 thinking phase (a direct, faster answer); `auto`/None leave the launch
    default reasoning budget; `extended` keeps thinking on, raises the PER-REQUEST reasoning
    budget (`reasoning_budget_tokens`, no engine relaunch), and widens the answer's token room.
    Per-request enable_thinking + reasoning_budget_tokens are applied by runtime.client._payload
    (local engine only)."""
    if thinking == "off":
        params["enable_thinking"] = False
    elif thinking == "auto":
        params["enable_thinking"] = True
    elif thinking == "extended":
        params["enable_thinking"] = True
        params["reasoning_budget_tokens"] = (
            extended_budget if extended_budget is not None else _extended_reasoning_budget()
        )
        params["max_tokens"] = max(int(params.get("max_tokens") or 0), _EXTENDED_MAX_TOKENS)
    return params


def _power_enabled(engine: ChatEngine, student_id: str) -> bool:
    """Private per-learner preference; an unreadable store keeps the safe default on."""
    try:
        return engine.store.get_settings(student_id).get("power_optimization_enabled", True)
    except Exception:
        return True


def _sampling_for_request(
    mode: str,
    thinking: str | None,
    *,
    power: PowerGovernor,
    power_enabled: bool,
    visualizations: bool = False,
) -> dict:
    params = _apply_thinking(params_for_mode(mode), thinking)
    # On the 2,048-token decode lane, Qwen3-0.6B can spend the whole fitted completion budget on
    # hidden reasoning before it reaches the required JSON. Visual turns reserve that budget for
    # the visible prose; the declarative payload is generated by the constrained second pass.
    adjusted = power.adjust_sampling(
        params,
        enabled=power_enabled,
        requested_thinking=thinking,
    )
    if visualizations:
        adjusted["enable_thinking"] = False
        adjusted.pop("reasoning_budget_tokens", None)
    return adjusted


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
    except Exception:
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
    except Exception:
        log.warning("self-check failed", exc_info=True)
        return None, ""


def _link_attachments(
    engine: ChatEngine,
    ids: list[int],
    cid: str,
    message_id: int | None,
    *,
    owner_id: str,
) -> None:
    """Bind previously-uploaded attachments to the persisted user turn. Unknown ids are a
    no-op UPDATE, not an error — the message must never fail over a stale attachment ref."""
    for aid in ids:
        try:
            engine.store.link_attachment(aid, cid, message_id, owner_id=owner_id)
        except Exception:
            log.warning("failed to link attachment %s to conversation %s", aid, cid, exc_info=True)
            continue


@router.get("/resources", response_model=ResourceList, tags=["resources"])
def resources(
    engine: ChatEngine = Depends(get_engine),
    caller: str = Depends(require_caller),
) -> ResourceList:
    return ResourceList(
        resources=[_resource_model(row) for row in engine.store.list_resources(caller)]
    )


@router.post(
    "/resources",
    response_model=LearningResource,
    status_code=202,
    tags=["resources"],
)
async def resource_upload(
    request: Request,
    file: UploadFile = File(...),
    engine: ChatEngine = Depends(get_engine),
    service: ResourceService = Depends(get_resource_service),
    caller: str = Depends(require_caller),
) -> LearningResource:
    """Durably accept one PDF, then prepare it outside the request thread."""
    write_principal = principal_from_request(request)
    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=415, detail="only PDF resources are supported")
    payload = bytearray()
    while True:
        block = await file.read(1024 * 1024)
        if not block:
            break
        payload.extend(block)
        if len(payload) > _MAX_RESOURCE_BYTES:
            raise HTTPException(status_code=413, detail="PDFs must be 32 MB or smaller")
    if not bytes(payload[:5]).startswith(b"%PDF-"):
        raise HTTPException(status_code=422, detail="this file is not a valid PDF")
    try:
        with member_write_lease(write_principal):
            resource_id = engine.store.create_resource(
                caller,
                safe_resource_name(file.filename),
                "application/pdf",
                bytes(payload),
            )
    except AuthenticationError as exc:
        raise HTTPException(status_code=403, detail="this account is being removed") from exc
    service.submit(resource_id, caller)
    row = engine.store.get_resource(resource_id, owner_id=caller)
    return _resource_model(row)


@router.post("/resources/{resource_id}/retry", response_model=LearningResource, tags=["resources"])
def resource_retry(
    resource_id: str,
    engine: ChatEngine = Depends(get_engine),
    service: ResourceService = Depends(get_resource_service),
    caller: str = Depends(require_caller),
) -> LearningResource:
    if not service.retry(resource_id, caller):
        raise HTTPException(status_code=404, detail="unknown resource")
    row = engine.store.get_resource(resource_id, owner_id=caller)
    return _resource_model(row)


@router.delete("/resources/{resource_id}", response_model=ResourceDeleted, tags=["resources"])
def resource_delete(
    resource_id: str,
    engine: ChatEngine = Depends(get_engine),
    caller: str = Depends(require_caller),
) -> ResourceDeleted:
    if not engine.store.delete_resource(resource_id, owner_id=caller):
        raise HTTPException(status_code=404, detail="unknown resource")
    return ResourceDeleted(id=resource_id)


@router.get(
    "/resources/{resource_id}/content",
    response_class=Response,
    tags=["resources"],
    responses={200: {"content": {"application/pdf": {}}, "description": "Inline PDF"}},
)
def resource_content(
    resource_id: str,
    engine: ChatEngine = Depends(get_engine),
    caller: str = Depends(caller_from_token),
) -> Response:
    row = engine.store.get_resource(resource_id, owner_id=caller, include_data=True)
    if row is None:
        raise HTTPException(status_code=404, detail="unknown resource")
    return Response(content=bytes(row["data"]), media_type="application/pdf", headers=_PDF_HEADERS)


@router.post("/chat", response_model=ChatResponse, tags=["tutor"])
def chat(
    req: ChatRequest,
    request: Request,
    engine: ChatEngine = Depends(get_engine),
    power: PowerGovernor = Depends(get_power_governor),
    generations: GenerationManager = Depends(get_generation_manager),
    sessions: SessionManager = Depends(get_sessions),
    ladder: DegradationLadder = Depends(get_ladder),
    caller: str | None = Depends(optional_caller),
) -> ChatResponse:
    """Multi-turn tutoring turn. Memory is keyed by `conversation_id`; omit it to start a
    new thread. The mode selects the system prompt (ROADMAP 18 Jul, stable-prefix design)."""
    strict = strict_share_security()
    turn_cancel = threading.Event() if strict else None
    write_principal = principal_from_request(request)
    if strict and caller is None:
        raise HTTPException(status_code=401, detail="sign in to continue")
    if caller is not None and caller != req.student_id:
        raise HTTPException(status_code=403, detail="you can only chat as yourself")
    resource_block = ""
    resource_sources: list[dict] = []
    if req.use_rag:
        if caller is None:
            raise HTTPException(status_code=401, detail="sign in to use private resources")
        if caller != req.student_id:
            raise HTTPException(status_code=403, detail="you can only use your own resources")
        resource_block, resource_sources = _resource_grounding(
            req, owner_id=caller, service=get_resource_service()
        )
    visual_requested = wants_live_visual(req.message)
    system_prompt = assemble_system_prompt(
        load_prompt(req.mode.value),
        persona=req.persona.value,
        language=req.language,
        subject=req.subject.value,
        twin_summary=_twin_summary(req.student_id),
        rag_block=resource_block,
    )

    def _run_chat():
        chat_result = engine.chat(
            student_id=req.student_id,
            message=req.message,
            conversation_id=req.conversation_id,
            system_prompt=system_prompt,
            turn_instruction=turn_instruction(
                req.message, response_language_instruction(req.language)
            ),
            mode=req.mode.value,
            persona=req.persona.value,
            subject=req.subject.value,
            language=req.language,
            title=_conversation_title(req.message),
            regenerate=req.regenerate,
            cancel_event=turn_cancel,
            **_sampling_for_request(
                req.mode.value,
                req.thinking,
                power=power,
                power_enabled=_power_enabled(engine, req.student_id),
                visualizations=visual_requested,
            ),
        )
        if visual_requested:
            spec = generate_visualization(
                engine,
                req.message,
                chat_result.reply,
                on_generation=bench_metrics.record,
            )
            if spec is not None:
                chat_result.reply = append_visualization(chat_result.reply, spec)
                if chat_result.assistant_message_id is not None:
                    engine.store.update_message(chat_result.assistant_message_id, chat_result.reply)
        # Keep all durable post-processing inside the GenerationManager job. Host removal
        # drains this operation before deleting the account, so nothing can recreate data
        # after the erase barrier.
        with member_write_lease(write_principal):
            if req.attachment_ids:
                _link_attachments(
                    engine,
                    req.attachment_ids,
                    chat_result.conversation_id,
                    chat_result.user_message_id,
                    owner_id=req.student_id,
                )
            if resource_sources and chat_result.assistant_message_id is not None:
                engine.store.add_message_sources(chat_result.assistant_message_id, resource_sources)
            _touch_twin(req.student_id, req.subject.value, req.message)
        return chat_result

    try:
        if strict:
            admission_id = f"generation:blocking:{uuid.uuid4().hex}"

            def _claim_session() -> bool:
                decision = sessions.acquire(admission_id)
                if decision.admission is Admission.REFUSED:
                    raise HTTPException(
                        status_code=503,
                        detail=decision.message or ladder.busy_message(),
                    )
                return decision.admitted

            def _run_admitted_chat():
                try:
                    return _run_chat()
                finally:
                    sessions.release(admission_id)

            result, _was_queued, _queue_position = generations.execute(
                student_id=req.student_id,
                operation=_run_admitted_chat,
                conversation_id=req.conversation_id,
                client_request_id=req.client_request_id,
                queued_cleanup=lambda: sessions.release(admission_id),
                before_start=_claim_session,
                cancel_event=turn_cancel,
            )
        else:
            result = _run_chat()
    except GenerationCapacityError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except (httpx.HTTPError, InferenceStreamError) as e:
        raise _handle_engine_error(e, where="/chat") from e
    # Telemetry for the external HUD (bench/monitor.py), which never sees a generation itself.
    if result.generation is not None:
        bench_metrics.record(result.generation)
    # Verified-tool-calls thesis: self-check the model's explicit arithmetic/algebra, append an
    # honest caution when a step contradicts itself, and record the turn on the learning twin.
    verified, note = _run_self_check(strip_visualization_protocol(result.reply))
    reply = result.reply if not note else f"{result.reply}\n\n{note}"
    return ChatResponse(
        student_id=req.student_id,
        conversation_id=result.conversation_id,
        mode=req.mode,
        reply=reply,
        verified=bool(verified),
        resource_citations=resource_sources,
    )


def _start_chat_generation(
    req: ChatRequest,
    *,
    engine: ChatEngine,
    sessions: SessionManager,
    ladder: DegradationLadder,
    preamble: PreambleWriter | None,
    generations: GenerationManager,
    allow_parallel: bool,
    power: PowerGovernor,
    power_enabled: bool,
) -> GenerationJob:
    """Prepare one turn and hand its iterator to the process-owned generation registry.

    The worker, rather than an HTTP response iterator, owns `_sse()`. Consequently the
    generator's persistence and session-release finalizers run even when every browser
    subscriber disconnects.
    """
    if req.conversation_id:
        conversation = engine.store.get_conversation(req.conversation_id)
        if conversation is None or conversation.get("student_id") != req.student_id:
            raise HTTPException(status_code=404, detail="unknown conversation")

    # Private-resource readiness/ownership is checked before reserving capacity or writing a
    # turn. A preparing book therefore cannot consume a classroom slot or create a ghost row.
    if req.use_rag:
        resource_block, resource_sources = _resource_grounding(
            req, owner_id=req.student_id, service=get_resource_service()
        )
    else:
        resource_block, resource_sources = "", []
    try:
        reservation_id = generations.reserve(
            req.student_id,
            allow_parallel=allow_parallel,
            conversation_id=req.conversation_id,
            client_request_id=req.client_request_id,
        )
    except GenerationCapacityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # A learner may own several simultaneous chats, so admission is leased per generation,
    # not per student. Otherwise two replies reuse one busy SessionManager slot and the first
    # completion falsely releases it while the second is still decoding.
    admission_id = f"generation:{reservation_id}"
    state = ladder.evaluate()

    # Web grounding (P4): RAG-style, opt-in, fail-silent. All three gates or nothing —
    # the ungrounded request must stay byte-identical to what the tutor already serves.
    sources: list[dict] = list(resource_sources)
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
                sources.extend({"title": snippet.title, "url": snippet.url} for snippet in snippets)

    visual_requested = wants_live_visual(req.message)
    system_prompt = assemble_system_prompt(
        load_prompt(req.mode.value),
        persona=req.persona.value,
        language=req.language,
        subject=req.subject.value,
        twin_summary=_twin_summary(req.student_id),
        web_lines=web_lines,
        rag_block=resource_block,
    )
    cancel_event = threading.Event()
    sampling_params = _sampling_for_request(
        req.mode.value,
        req.thinking,
        power=power,
        power_enabled=power_enabled,
        visualizations=visual_requested,
    )
    structured_response = "response_format" in sampling_params

    try:
        cid, user_message_id, events = engine.stream_events_chat(
            student_id=req.student_id,
            message=req.message,
            conversation_id=req.conversation_id,
            system_prompt=system_prompt,
            turn_instruction=turn_instruction(
                req.message, response_language_instruction(req.language)
            ),
            mode=req.mode.value,
            persona=req.persona.value,
            subject=req.subject.value,
            language=req.language,
            title=_conversation_title(req.message),
            regenerate=req.regenerate,  # 'answer now' re-runs this turn without a new user msg
            cancel_event=cancel_event,
            # §6.5 sampling profiles apply to the UI's primary path too — without them the
            # stream ran at llama-server defaults with NO max_tokens (an unbounded turn is one
            # student holding a slot indefinitely, and with thinking on it filled the context).
            **sampling_params,
        )
    except ValueError as exc:
        generations.cancel_reservation(reservation_id)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        # Physical admission happens only at FIFO-head promotion, after preparation succeeds.
        # At this point only the bounded registry reservation needs to be released.
        generations.cancel_reservation(reservation_id)
        raise
    if req.attachment_ids:
        _link_attachments(
            engine,
            req.attachment_ids,
            cid,
            user_message_id,
            owner_id=req.student_id,
        )

    # TTFT preamble (docs/ttft-preamble.md): fills the prefill window with a distinct,
    # non-answer `preamble` event. A no-op when disabled or unprovisioned.
    streamed = with_preamble(events, preamble, **_preamble_opts())

    def _sse():
        n = 0
        t_first = t_last = 0.0
        t_preamble = 0.0
        reply_parts: list[str] = []  # answer content only, for the post-stream self-check
        hub = get_hub()
        started = time.monotonic()
        reply_source = "local"
        try:
            hub.begin(cid)
            # Keep the leading id inside the cleanup boundary: Stop can land after this first
            # yield, and closing there must still release telemetry and the physical slot.
            yield f"data: {json.dumps({'conversation_id': cid})}\n\n"
            for kind, text in streamed:
                now = time.monotonic()
                if kind == "source":
                    # Sticky per-job provenance: parallel jobs cannot overwrite it, and a
                    # cloud prefix resumed locally must still disclose cloud involvement.
                    if text == "cloud":
                        reply_source = "cloud"
                    # Provenance must reach replay/UI before any cloud content. A later Stop
                    # or terminal recovery failure may bypass this route's successful done.
                    yield f"data: {json.dumps({'source': reply_source})}\n\n"
                    continue
                if kind == "recovering":
                    yield f"data: {json.dumps({'recovering': text})}\n\n"
                    continue
                # The preamble is filler from a 1 M-parameter model, not the tutor speaking:
                # it gets its own event key, is excluded from the token count and the tok/s
                # window, and never joins reply_parts (so it cannot reach the self-check or
                # the store). Everything below this branch is the engine's own output.
                if kind == "preamble":
                    if not t_preamble:
                        t_preamble = now
                    yield f"data: {json.dumps({'preamble': text})}\n\n"
                    continue
                if not structured_response:
                    if n == 0:
                        t_first = now
                    t_last = now
                    n += 1  # reasoning and content both count: the engine decodes both
                    hub.tick(cid)  # feeds the live tok/s in the telemetry strip
                key = "reasoning" if kind == "reasoning" else "delta"
                if kind != "reasoning":
                    reply_parts.append(text)
                yield f"data: {json.dumps({key: text})}\n\n"
            if visual_requested and reply_parts and not cancel_event.is_set():
                prose_reply = "".join(reply_parts)
                spec = generate_visualization(
                    engine,
                    req.message,
                    prose_reply,
                    cancel_event=cancel_event,
                    on_generation=bench_metrics.record,
                )
                if spec is not None:
                    complete_reply = append_visualization(prose_reply, spec)
                    suffix = complete_reply[len(prose_reply) :]
                    assistant_message_id = getattr(events, "assistant_message_id", None)
                    if assistant_message_id is not None:
                        engine.store.update_message(assistant_message_id, complete_reply)
                    yield f"data: {json.dumps({'delta': suffix})}\n\n"
        except (httpx.HTTPError, InferenceStreamError) as e:
            log.warning("engine error mid-stream at /chat/stream: %r", e)
            error = {"error": _incomplete_stream_message(partial_saved=bool(reply_parts))}
            yield f"data: {json.dumps(error)}\n\n"
            return
        finally:
            hub.end(cid)
            # Deterministically close the source generator so its finally (partial-reply
            # persist) runs HERE, on this threadpool thread, the moment the stream ends —
            # instead of waiting for GC after a client disconnect, which could stall every
            # other stream and let an abandoned llama-server slot stay busy. Idempotent.
            #
            # ORDER IS LOAD-BEARING: the preamble wrapper is closed first because it owns a
            # thread that may be sitting inside `next(events)` during prefill. Closing
            # `events` while that thread is in it raises "generator already executing" —
            # which, from this finally, would skip the `sessions.release()` below and leak
            # an admission slot on every disconnect during the prefill window.
            try:
                try:
                    _close_events(streamed)
                finally:
                    _close_events(events)
                if resource_sources:
                    # The stream writer owns an exact assistant row. Never rediscover it by
                    # ordering: another generation can persist into this conversation while
                    # this one is decoding.
                    assistant_message_id = getattr(events, "assistant_message_id", None)
                    if assistant_message_id is not None:
                        engine.store.add_message_sources(assistant_message_id, resource_sources)
            finally:
                # Cleanup failures must never strand the one physical inference admission.
                sessions.release(admission_id)
        # Deltas approximate tokens (llama-server streams ~one token per chunk). Rate is the
        # DECODE window — first token to last — so it excludes prefill/time-to-first-token and
        # reads close to the engine's own generation rate rather than being dragged down by a
        # short reply's startup. Still wall-clock (from_wall_clock=True); the engine-true rate
        # is what `/chat` records. Feed the shared window so `make monitor` stays live too.
        elapsed = t_last - t_first if not structured_response else 0.0
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
        yield (
            "data: "
            + json.dumps(
                {
                    "done": True,
                    "conversation_id": cid,
                    # Structured output is buffered until one complete schema root exists.
                    # Replaying that buffer is not decode and must never become a fake TPS sample.
                    "completion_tokens": None if structured_response else n,
                    "elapsed_s": None if structured_response else round(elapsed, 3),
                    "tokens_per_second": None if structured_response else round(rate, 2),
                    # Two first-token numbers, deliberately separate. `ttft_s` is and stays the
                    # engine's own — what the tutor took to speak. `preamble_ttft_s` is when the
                    # pane stopped being empty. Collapsing them into one figure would be the
                    # dishonest version of this feature.
                    "ttft_s": (
                        round(t_first - started, 3) if n and not structured_response else None
                    ),
                    "preamble_ttft_s": round(t_preamble - started, 3) if t_preamble else None,
                    # Student text leaving the device must never be silent (P3): the UI
                    # badges any answer a cloud backend produced.
                    "source": reply_source,
                    # Grounding sources (P4): empty unless web context shaped this answer.
                    "sources": sources,
                    # Verified-tool-calls (self-check): True/False when a step was checkable,
                    # null otherwise; check_note carries a friendly caution on a contradiction.
                    "verified": verified,
                    "check_note": check_note,
                    # Admission/degradation state, so the UI can show "you're next" and a
                    # reduced-capacity notice under classroom load.
                    "queued": False,
                    "queue_position": 0,
                    "degradation_level": f"L{int(state.level)}",
                }
            )
            + "\n\n"
        )

    def _cleanup_while_queued() -> None:
        # A generator closed before its first `next()` never enters its own `finally`.
        # Explicit queued cancellation therefore owns the otherwise-unreachable resources.
        _close_events(streamed)
        _close_events(events)
        sessions.release(admission_id)

    def _claim_inference_session() -> bool:
        # GenerationManager owns the FIFO, while SessionManager mirrors the actual physical
        # slot. A queued job must bind that freed slot before its worker is allowed to run.
        promoted = sessions.acquire(admission_id)
        if promoted.admission is Admission.REFUSED:
            # L3 is the memory/thermal emergency brake, not ordinary classroom contention.
            # Keeping the FIFO head parked here would block every later job indefinitely.
            raise HTTPException(
                status_code=503,
                detail=promoted.message or ladder.busy_message(),
            )
        return promoted.admitted

    try:
        return generations.start(
            student_id=req.student_id,
            conversation_id=cid,
            producer=_sse(),
            reservation_id=reservation_id,
            client_request_id=req.client_request_id,
            queued_cleanup=_cleanup_while_queued,
            before_start=_claim_inference_session,
            cancel_event=cancel_event,
        )
    except Exception:
        _close_events(streamed)
        _close_events(events)
        sessions.release(admission_id)
        generations.cancel_reservation(reservation_id)
        raise


def _job_stream(job: GenerationJob, *, after: int = 0) -> StreamingResponse:
    return StreamingResponse(
        job.subscribe(after=after), media_type="text/event-stream", headers=_SSE_HEADERS
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
    preamble: PreambleWriter | None = Depends(get_preamble_writer),
    generations: GenerationManager = Depends(get_generation_manager),
    power: PowerGovernor = Depends(get_power_governor),
    caller: str = Depends(require_caller),
) -> StreamingResponse:
    """Backwards-compatible streaming start; disconnecting no longer cancels inference."""
    if caller != req.student_id:
        raise HTTPException(status_code=403, detail="you can only start your own generation")
    job = _start_chat_generation(
        req,
        engine=engine,
        sessions=sessions,
        ladder=ladder,
        preamble=preamble,
        generations=generations,
        allow_parallel=False,
        power=power,
        power_enabled=_power_enabled(engine, caller),
    )
    return _job_stream(job)


@router.post(
    "/chat/generations",
    response_model=GenerationStarted,
    status_code=202,
    tags=["tutor"],
)
def generation_start(
    req: ChatRequest,
    engine: ChatEngine = Depends(get_engine),
    sessions: SessionManager = Depends(get_sessions),
    ladder: DegradationLadder = Depends(get_ladder),
    preamble: PreambleWriter | None = Depends(get_preamble_writer),
    generations: GenerationManager = Depends(get_generation_manager),
    power: PowerGovernor = Depends(get_power_governor),
    caller: str = Depends(require_caller),
) -> GenerationStarted:
    """Start a durable browser turn and return its ids before subscribing to tokens."""
    if caller != req.student_id:
        raise HTTPException(status_code=403, detail="you can only start your own generation")
    job = _start_chat_generation(
        req,
        engine=engine,
        sessions=sessions,
        ladder=ladder,
        preamble=preamble,
        generations=generations,
        allow_parallel=engine.store.get_settings(caller).get("allow_parallel_chats", True),
        power=power,
        power_enabled=_power_enabled(engine, caller),
    )
    snapshot = job.snapshot()
    return GenerationStarted(
        job_id=job.id,
        conversation_id=job.conversation_id,
        client_request_id=job.client_request_id,
        state="queued" if snapshot.state == "queued" else "running",
        queue_position=snapshot.queue_position,
    )


@router.get("/chat/generations", response_model=GenerationList, tags=["tutor"])
def generation_list(
    client_request_id: str | None = None,
    generations: GenerationManager = Depends(get_generation_manager),
    caller: str = Depends(require_caller),
) -> GenerationList:
    """List the caller's live jobs so a refreshed UI can reconnect to each one."""
    rows = (
        generations.matching(caller, client_request_id)
        if client_request_id
        else generations.active(caller)
    )
    return GenerationList(
        generations=[
            GenerationStatus(
                job_id=row.job_id,
                conversation_id=row.conversation_id,
                state=row.state,
                created_at=row.created_at,
                client_request_id=row.client_request_id,
                queue_position=row.queue_position,
            )
            for row in rows
        ]
    )


@router.get(
    "/chat/generations/{job_id}/stream",
    tags=["tutor"],
    responses={200: {"content": {"text/event-stream": {}}, "description": "SSE token stream"}},
)
def generation_stream(
    job_id: str,
    after: int = 0,
    generations: GenerationManager = Depends(get_generation_manager),
    caller: str = Depends(require_caller),
) -> StreamingResponse:
    """Replay and tail a live or recently-completed job from a frame offset."""
    if after < 0:
        raise HTTPException(status_code=422, detail="after must be non-negative")
    job = generations.get(job_id, student_id=caller)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown generation")
    return _job_stream(job, after=after)


@router.delete("/chat/generations/{job_id}", response_model=GenerationStopped, tags=["tutor"])
def generation_stop(
    job_id: str,
    generations: GenerationManager = Depends(get_generation_manager),
    caller: str = Depends(require_caller),
) -> GenerationStopped:
    """Explicit Stop is the only browser action that cancels a server-owned generation."""
    job = generations.get(job_id, student_id=caller)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown generation")
    return GenerationStopped(job_id=job.id, stopping=job.request_stop())


@router.get("/settings", response_model=UserSettings, tags=["conversations"])
def user_settings(
    engine: ChatEngine = Depends(get_engine),
    caller: str = Depends(require_caller),
) -> UserSettings:
    """Return private learner preferences, with contract defaults for an untouched account."""
    return UserSettings(**engine.store.get_settings(caller))


@router.put("/settings", response_model=UserSettings, tags=["conversations"])
def user_settings_update(
    request: Request,
    requested: UserSettings,
    engine: ChatEngine = Depends(get_engine),
    caller: str = Depends(require_caller),
) -> UserSettings:
    """Atomically update supplied settings while preserving sibling and future keys."""
    # The browser saves switches independently. One SQL transaction/statement prevents two
    # tabs toggling different controls from losing each other's updates.
    write_principal = principal_from_request(request)
    try:
        with member_write_lease(write_principal):
            values = engine.store.patch_settings(caller, requested.model_dump(exclude_unset=True))
    except AuthenticationError as exc:
        raise HTTPException(status_code=403, detail="this account is being removed") from exc
    return UserSettings(**values)


@router.get("/power/status", response_model=PowerStatus, tags=["runtime"])
def power_status(
    engine: ChatEngine = Depends(get_engine),
    power: PowerGovernor = Depends(get_power_governor),
    caller: str = Depends(require_caller),
) -> PowerStatus:
    """Power state of the serving laptop, not the browser/phone making this request."""
    return PowerStatus.model_validate(power.status(enabled=_power_enabled(engine, caller)))


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
                title=_listed_conversation_title(r, engine.store),
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
                resource_citations=m.get("resource_citations", []),
            )
            for m in rows
        ],
    )


@router.get(
    "/conversations/{conversation_id}/telemetry",
    response_model=TelemetrySnapshot,
    tags=["ops"],
)
def conversation_telemetry(
    conversation_id: str, caller: str | None = Depends(optional_caller)
) -> TelemetrySnapshot:
    """One-shot telemetry snapshot (curl-able twin of the SSE stream below)."""
    if strict_share_security():
        conversation = get_engine().store.get_conversation(conversation_id)
        if caller is None or conversation is None or conversation.get("student_id") != caller:
            raise HTTPException(status_code=404, detail="unknown conversation")
    return TelemetrySnapshot(**get_hub().snapshot(conversation_id))


@router.get(
    "/conversations/{conversation_id}/telemetry/stream",
    tags=["ops"],
    responses={200: {"content": {"text/event-stream": {}}, "description": "1 Hz SSE telemetry"}},
)
async def conversation_telemetry_stream(
    request: Request,
    conversation_id: str,
    caller: str | None = Depends(optional_caller),
) -> StreamingResponse:
    """1 Hz telemetry SSE. Async generator on purpose: a sync generator would pin a
    threadpool thread per open strip. GET, so the browser's native EventSource works."""

    if strict_share_security():
        conversation = get_engine().store.get_conversation(conversation_id)
        if caller is None or conversation is None or conversation.get("student_id") != caller:
            raise HTTPException(status_code=404, detail="unknown conversation")
    token = request_token(
        request.headers.get("authorization"),
        request.cookies.get(SESSION_COOKIE),
        request.query_params.get("token"),
    )

    async def _gen():
        while True:
            if strict_share_security():
                current = resolve_principal(token)
                if current is None or current.subject != caller:
                    return
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
def auth_session(request: Request, response: Response, req: AuthTokenRequest) -> AuthTokenResponse:
    """Mint a bearer token for a per-device learner id. With MUTA_AUTH_SECRET set the token is
    HMAC-signed (unforgeable); without it the token is the id itself (opaque per-device
    secret). Native loopback mode replaces port-scoped browser ids with one persistent operator
    id. The client sends the token as `Authorization: Bearer <token>` on data endpoints."""
    if strict_share_security():
        if not is_operator_request(request):
            raise HTTPException(status_code=403, detail="host access is local only")
        student_id = operator_student_id()
        issued = get_sharing_service().issue_host_session(student_id)
        response.set_cookie(
            SESSION_COOKIE,
            issued.token,
            max_age=30 * 24 * 60 * 60,
            httponly=True,
            secure=False,
            samesite="strict",
            path="/",
        )
        return AuthTokenResponse(
            student_id=student_id,
            token=issued.token,
            role="host",
            csrf_token=issued.csrf_token,
        )
    peer = request.client.host if request.client else ""
    student_id = operator_student_id() if _unified_loopback_identity(peer) else req.student_id
    try:
        token = mint_token(student_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return AuthTokenResponse(student_id=student_id, token=token)


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
    request: Request,
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
    write_principal = principal_from_request(request)
    outcome = verifier.check_text(req.candidate, req.expected, tolerance=req.tolerance)
    if outcome.checked:
        try:
            with member_write_lease(write_principal):
                store = get_twin_store()
                twin = store.load(req.student_id)
                twin.record_mastery(req.topic, 1.0 if outcome.verified else 0.0)
                if not outcome.verified:
                    twin.record_error(req.topic)
                store.save(twin)
        except AuthenticationError as exc:
            raise HTTPException(status_code=403, detail="this account is being removed") from exc
        except Exception:
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
    generations: GenerationManager = Depends(get_generation_manager),
    ladder: DegradationLadder = Depends(get_ladder),
    power: PowerGovernor = Depends(get_power_governor),
    caller: str | None = Depends(optional_caller),
) -> TutorReply:
    """One tutoring turn, admission-controlled (§8.2) and ladder-aware (§5.3).

    Set `stream: false` for this JSON shape; `stream: true` (the default) is served by
    `/tutor/chat/stream`, which speaks SSE. Both take the same body.
    """
    if strict_share_security() and caller is None:
        raise HTTPException(status_code=401, detail="sign in to continue")
    if caller is not None and turn.student_id not in {None, caller}:
        raise HTTPException(status_code=403, detail="you can only chat as yourself")
    student_id = caller or turn.student_id or turn.session_id
    state = ladder.evaluate()
    strict = strict_share_security()
    turn_cancel = threading.Event() if strict else None
    decision = None if strict else sessions.acquire(turn.session_id)
    if decision is not None and decision.admission is Admission.REFUSED:
        # 503 with a human message, not an error page: judges are non-technical (C-7).
        raise HTTPException(status_code=503, detail=decision.message or ladder.busy_message())
    visual_requested = wants_live_visual(turn.text)
    sampling_params = power.adjust_sampling(
        params_for_mode(turn.mode.value),
        enabled=_power_enabled(engine, student_id),
    )
    if visual_requested:
        sampling_params["enable_thinking"] = False

    def _run_tutor_turn():
        chat_result = engine.chat(
            student_id=student_id,
            message=turn.text,
            conversation_id=turn.session_id,
            system_prompt=assemble_system_prompt(
                load_prompt(_prompt_for(turn.mode)),
                language=turn.lang,
            ),
            turn_instruction=turn_instruction(turn.text, response_language_instruction(turn.lang)),
            mode=turn.mode.value,
            language=turn.lang,
            cancel_event=turn_cancel,
            **sampling_params,
        )
        if visual_requested:
            spec = generate_visualization(
                engine,
                turn.text,
                chat_result.reply,
                on_generation=bench_metrics.record,
            )
            if spec is not None:
                chat_result.reply = append_visualization(chat_result.reply, spec)
                if chat_result.assistant_message_id is not None:
                    engine.store.update_message(chat_result.assistant_message_id, chat_result.reply)
        return chat_result

    try:
        if strict:
            admission_id = f"generation:blocking-tutor:{uuid.uuid4().hex}"

            def _claim_session() -> bool:
                admission = sessions.acquire(admission_id)
                if admission.admission is Admission.REFUSED:
                    raise HTTPException(
                        status_code=503,
                        detail=admission.message or ladder.busy_message(),
                    )
                return admission.admitted

            def _run_admitted_turn():
                try:
                    return _run_tutor_turn()
                finally:
                    sessions.release(admission_id)

            result, was_queued, queue_position = generations.execute(
                student_id=student_id,
                operation=_run_admitted_turn,
                conversation_id=turn.session_id,
                queued_cleanup=lambda: sessions.release(admission_id),
                before_start=_claim_session,
                cancel_event=turn_cancel,
            )
        else:
            result = _run_tutor_turn()
            was_queued = decision.admission is Admission.QUEUED
            queue_position = decision.queue_position
    except GenerationCapacityError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except (httpx.HTTPError, InferenceStreamError) as e:
        raise _handle_engine_error(e, where="/tutor/chat") from e
    finally:
        if not strict:
            assert decision is not None
            sessions.release(turn.session_id)

    if result.generation is not None:
        bench_metrics.record(result.generation)
    return TutorReply(
        session_id=turn.session_id,
        reply=result.reply,
        mode=turn.mode,
        queued=was_queued,
        queue_position=queue_position,
        degradation_level=f"L{int(state.level)}",
    )


def _prompt_for(mode: TutorMode) -> str:
    return {
        "dialogue": "socratic",
        "solution": "subgoal",
        "marking": "subgoal",
        "hint": "socratic",
    }[mode.value]


@router.post(
    "/tutor/chat/stream",
    tags=["tutor"],
    responses={200: {"content": {"text/event-stream": {}}, "description": "SSE token stream"}},
)
def tutor_chat_stream(
    turn: ChatTurn,
    engine: ChatEngine = Depends(get_engine),
    sessions: SessionManager = Depends(get_sessions),
    generations: GenerationManager = Depends(get_generation_manager),
    ladder: DegradationLadder = Depends(get_ladder),
    preamble: PreambleWriter | None = Depends(get_preamble_writer),
    power: PowerGovernor = Depends(get_power_governor),
    caller: str | None = Depends(optional_caller),
) -> StreamingResponse:
    """Token-streaming twin of `/tutor/chat` (§7.2: the tutoring turn is SSE).

    Events: `{"reasoning": …}` while the model thinks, `{"delta": …}` per answer token, then
    a final `{"done": true, …}`. Time-to-first-token is the number a student feels (SC-3:
    < 2.5 s), so the stream starts before the answer is finished, not after.
    """
    if strict_share_security() and caller is None:
        raise HTTPException(status_code=401, detail="sign in to continue")
    if caller is not None and turn.student_id not in {None, caller}:
        raise HTTPException(status_code=403, detail="you can only chat as yourself")
    student_id = caller or turn.student_id or turn.session_id
    state = ladder.evaluate()
    strict = strict_share_security()
    turn_cancel = threading.Event() if strict else None
    reservation_id: str | None = None
    if strict:
        try:
            reservation_id = generations.reserve(
                student_id,
                allow_parallel=True,
                conversation_id=turn.session_id,
            )
        except GenerationCapacityError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        admission_id = f"generation:blocking-tutor-stream:{reservation_id}"
    else:
        decision = sessions.acquire(turn.session_id)
        if decision.admission is Admission.REFUSED:
            raise HTTPException(status_code=503, detail=decision.message or ladder.busy_message())
        admission_id = turn.session_id
    visual_requested = wants_live_visual(turn.text)
    sampling_params = power.adjust_sampling(
        params_for_mode(turn.mode.value),
        enabled=_power_enabled(engine, student_id),
    )
    if visual_requested:
        sampling_params["enable_thinking"] = False
    structured_response = "response_format" in sampling_params

    try:
        cid, _user_message_id, events = engine.stream_events_chat(
            student_id=student_id,
            message=turn.text,
            conversation_id=turn.session_id,
            system_prompt=assemble_system_prompt(
                load_prompt(_prompt_for(turn.mode)),
                language=turn.lang,
            ),
            turn_instruction=turn_instruction(turn.text, response_language_instruction(turn.lang)),
            mode=turn.mode.value,
            language=turn.lang,
            cancel_event=turn_cancel,
            **sampling_params,
        )
    except Exception:
        # The generator's finally releases the slot only once streaming starts; a failure
        # before that (store down, bad prompt) must not consume a decode lane forever.
        if reservation_id is not None:
            generations.cancel_reservation(reservation_id)
        sessions.release(admission_id)
        raise

    streamed = with_preamble(events, preamble, **_preamble_opts())

    def _sse():
        started = time.monotonic()
        first_token_at = 0.0
        preamble_at = 0.0
        count = 0
        content_count = 0
        reply_parts: list[str] = []
        try:
            for kind, text in streamed:
                if kind == "source":
                    continue
                if kind == "recovering":
                    yield f"data: {json.dumps({'recovering': text})}\n\n"
                    continue
                if kind == "preamble":
                    # Filler, not tutoring: own event key, excluded from count and ttft_s.
                    if not preamble_at:
                        preamble_at = time.monotonic()
                    yield f"data: {json.dumps({'preamble': text})}\n\n"
                    continue
                if not structured_response:
                    if count == 0:
                        first_token_at = time.monotonic()
                    count += 1
                key = "reasoning" if kind == "reasoning" else "delta"
                if kind != "reasoning":
                    content_count += 1
                    reply_parts.append(text)
                yield f"data: {json.dumps({key: text})}\n\n"
            if visual_requested and reply_parts:
                prose_reply = "".join(reply_parts)
                spec = generate_visualization(
                    engine, turn.text, prose_reply, on_generation=bench_metrics.record
                )
                if spec is not None:
                    complete_reply = append_visualization(prose_reply, spec)
                    suffix = complete_reply[len(prose_reply) :]
                    assistant_message_id = getattr(events, "assistant_message_id", None)
                    if assistant_message_id is not None:
                        engine.store.update_message(assistant_message_id, complete_reply)
                    yield f"data: {json.dumps({'delta': suffix})}\n\n"
        except (httpx.HTTPError, InferenceStreamError) as e:
            log.warning("engine error mid-stream at /tutor/chat/stream: %r", e)
            error = {"error": _incomplete_stream_message(partial_saved=content_count > 0)}
            yield f"data: {json.dumps(error)}\n\n"
            return
        finally:
            sessions.release(admission_id)
            # Preamble wrapper first, then the engine's generator — same load-bearing order
            # as /chat/stream: its helper thread may still be inside `next(events)`.
            _close_events(streamed)
            _close_events(
                events
            )  # deterministic partial-persist off the event loop (see /chat/stream)
        yield (
            "data: "
            + json.dumps(
                {
                    "done": True,
                    "session_id": cid,
                    "completion_tokens": None if structured_response else count,
                    "ttft_s": (
                        round(first_token_at - started, 3)
                        if count and not structured_response
                        else None
                    ),
                    "preamble_ttft_s": round(preamble_at - started, 3) if preamble_at else None,
                    "degradation_level": f"L{int(state.level)}",
                }
            )
            + "\n\n"
        )

    if strict:
        assert reservation_id is not None

        def _claim_session() -> bool:
            admission = sessions.acquire(admission_id)
            if admission.admission is Admission.REFUSED:
                raise HTTPException(
                    status_code=503,
                    detail=admission.message or ladder.busy_message(),
                )
            return admission.admitted

        def _queued_cleanup() -> None:
            try:
                _close_events(streamed)
            finally:
                _close_events(events)
                sessions.release(admission_id)

        try:
            job = generations.start(
                student_id=student_id,
                conversation_id=cid,
                producer=_sse(),
                reservation_id=reservation_id,
                queued_cleanup=_queued_cleanup,
                before_start=_claim_session,
                cancel_event=turn_cancel,
            )
        except Exception:
            _queued_cleanup()
            raise
        return StreamingResponse(
            job.subscribe(), media_type="text/event-stream", headers=_SSE_HEADERS
        )
    return StreamingResponse(_sse(), media_type="text/event-stream", headers=_SSE_HEADERS)


_IMAGE_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
_VISION_SLOTS = threading.BoundedSemaphore(1)


@router.post("/tutor/vision", response_model=VisionReply, tags=["tutor"])
async def tutor_vision(
    request: Request,
    session_id: str = Form(...),
    image: UploadFile = File(...),
    conversation_id: str | None = Form(None),
    vision: VisionManager = Depends(get_vision),
    engine: ChatEngine = Depends(get_engine),
    caller: str | None = Depends(optional_caller),
) -> VisionReply:
    """Photo of handwritten work → transcription (S2).

    Two refusals, both friendly: the image guard (too big, wrong format) and the ladder
    (no memory for a vision instance). Neither is an error — the student is told to type the
    problem instead, and the tutor keeps working.
    """
    if strict_share_security() and caller is None:
        raise HTTPException(status_code=401, detail="sign in to continue")
    write_principal = principal_from_request(request)
    if caller is not None and conversation_id:
        conversation = engine.store.get_conversation(conversation_id)
        if conversation is not None and conversation.get("student_id") != caller:
            raise HTTPException(status_code=403, detail="you can only use your own conversation")
    owner_id = caller or session_id
    raw = await image.read(MAX_IMAGE_UPLOAD_BYTES + 1)
    try:
        prepared = prepare_image(raw)
    except ImageRejected as e:
        return VisionReply(session_id=session_id, accepted=False, detail=str(e))

    # Persist the (guard-normalised) image so the thread's history can re-render it. Storage
    # failure must not block tutoring — the transcription path continues without an id.
    attachment_id: int | None = None
    try:
        with member_write_lease(write_principal):
            attachment_id = await run_in_threadpool(
                engine.store.add_attachment,
                "image",
                _IMAGE_MIME.get(prepared.format, "application/octet-stream"),
                prepared.data,
                conversation_id=conversation_id,
                owner_id=owner_id,
            )
    except AuthenticationError as exc:
        raise HTTPException(status_code=403, detail="this account is being removed") from exc
    except Exception:
        log.warning("failed to persist vision attachment for session %s", session_id, exc_info=True)
        attachment_id = None

    # Both `ensure()` (polls for up to MUTA_RT_VISION_STARTUP_S on a cold spawn) and
    # `transcribe()` (a blocking httpx.post, up to request_timeout_s) are synchronous. This
    # handler is async, so run them in the threadpool — otherwise one vision request freezes
    # the single event loop and stalls every other phone in the classroom mid-stream.
    # The vision instance is stateless and TTL-killable by design: it returns a transcription,
    # and the *text* session carries the conversation (§6.3, S2). A transport failure OR a
    # malformed-but-200 reply is S2's honest fallback, never a 500 in a non-technical judge's face.
    # The same per-request budget the text engine gets: a real photo at the Qwen-VL
    # 1024-image-token floor needs minutes of prefill on a slow box, and the client's 120 s
    # default silently cut every one of them off mid-read. `in_use()` keeps the TTL reaper
    # off a server that is mid-transcription for exactly as long.
    def _read(cancel_event: threading.Event | None = None) -> str:
        with vision.in_use():
            base_url = vision.ensure()  # spawns CORE-VISION if needed
            client = VisionClient(base_url, timeout=RuntimeConfig().request_timeout_s)
            if cancel_event is None:
                return client.transcribe(prepared.data, prepared.format)
            return client.transcribe(prepared.data, prepared.format, cancel_event=cancel_event)

    try:
        if write_principal is not None and write_principal.role == "member":
            tracked = get_owner_work_manager().track(write_principal.subject)
        else:
            tracked = contextlib.nullcontext(None)
        with tracked as cancel_event:
            async with auxiliary_slot(_VISION_SLOTS):
                transcription = await run_in_threadpool(_read, cancel_event)
    except OwnerWorkRejected:
        raise HTTPException(status_code=403, detail="this account is being removed") from None
    except AuxiliaryQueueFull:
        return VisionReply(
            session_id=session_id,
            accepted=False,
            detail="the image reader is busy — type the problem or try again shortly",
            attachment_id=attachment_id,
        )
    except VisionDenied as e:
        return VisionReply(
            session_id=session_id, accepted=False, detail=str(e), attachment_id=attachment_id
        )
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
    request: Request,
    session_id: str,
    sessions: SessionManager = Depends(get_sessions),
    csrf: str | None = Header(default=None, alias="X-Muta-CSRF"),
) -> SessionActionResponse:
    """Persist a session's KV and free its slot (§8.3)."""
    if strict_share_security():
        principal = principal_from_request(request)
        if principal is None or principal.role != "host" or not is_operator_request(request):
            raise HTTPException(status_code=403, detail="session controls are host-only")
        verify_host_csrf(principal, csrf)
    ok = sessions.evict(session_id)
    return SessionActionResponse(
        session_id=session_id,
        action="suspend",
        ok=ok,
        detail="" if ok else "session held no slot",
    )


@router.post("/session/{session_id}/resume", response_model=SessionActionResponse, tags=["ops"])
def session_resume(
    request: Request,
    session_id: str,
    sessions: SessionManager = Depends(get_sessions),
    csrf: str | None = Header(default=None, alias="X-Muta-CSRF"),
) -> SessionActionResponse:
    """Bind a slot for a session, restoring its snapshot when one survives."""
    if strict_share_security():
        principal = principal_from_request(request)
        if principal is None or principal.role != "host" or not is_operator_request(request):
            raise HTTPException(status_code=403, detail="session controls are host-only")
        verify_host_csrf(principal, csrf)
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
    request: Request,
    ladder: DegradationLadder = Depends(get_ladder),
    sessions: SessionManager = Depends(get_sessions),
    vision: VisionManager = Depends(get_vision),
) -> SystemStatus:
    """Local health panel data (§12). All local: no exporter, no network, no dashboards."""
    if strict_share_security():
        principal = principal_from_request(request)
        if principal is None or principal.role != "host" or not is_operator_request(request):
            raise HTTPException(status_code=403, detail="host access is local only")
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
