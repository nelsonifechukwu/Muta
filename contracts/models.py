"""Request/response models for the public `/v1` surface — the source of truth.

Kept deliberately small: the minimum endpoint surface from ROADMAP.md (16 Jul). The
`subject` axis carries physics/chemistry/biology from day one (the competition domain is
Math *and* Scientific Reasoning), so downstream consumers never have to retrofit it.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

ResourceId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]


class TutoringMode(str, Enum):
    """The two MVP tutoring modes (ROADMAP 14 Jul scope)."""

    socratic = "socratic"
    subgoal = "subgoal"


class Persona(str, Enum):
    teacher = "teacher"
    friend = "friend"
    professor = "professor"
    exam = "exam"  # minimal-hints exam mode


class Subject(str, Enum):
    math = "math"
    physics = "physics"
    chemistry = "chemistry"
    biology = "biology"


# --- Ops -------------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str = Field("0.0.0", description="Semantic version of the running build.")
    git_sha: str = Field("unknown", description="Commit the running image was built from.")


class ReadyResponse(BaseModel):
    ready: bool
    checks: dict[str, bool] = Field(
        default_factory=dict, description="Per-dependency readiness (llama-server, sub-apps)."
    )
    # Deliberately NOT a check: ready = all(checks), and an offline-but-healthy stack is
    # still ready — offline is a state, not a failure (design P2, 2026-08-08).
    online: bool | None = Field(
        None, description="Internet reachability; null until the first probe completes."
    )


class ModelBackend(BaseModel):
    """One fixed backend from the local model registry; browser clients never send paths."""

    id: str
    label: str
    kind: Literal["local", "cloud"]
    description: str
    available: bool
    active: bool
    disabled_reason: str | None = None
    size_bytes: int | None = None
    arc_easy: float | None = None
    audit_proxy_tps: float | None = None
    recommended: bool = False


class ModelCatalogResponse(BaseModel):
    active_id: str | None = None
    switching: bool = False
    selection_enabled: bool = False
    models: list[ModelBackend] = Field(default_factory=list)


class ModelSelectRequest(BaseModel):
    model_id: str = Field(min_length=1, max_length=128)


class ModelSelectResponse(ModelCatalogResponse):
    pass


# --- /chat -----------------------------------------------------------------------------


class ChatRequest(BaseModel):
    student_id: str = Field(
        max_length=128, description="Stable per-learner id; keys the learning twin."
    )
    # Input cap (prompt-bomb guard): the primary browser path was previously unbounded while
    # the sibling /tutor path capped its text — one multi-MB message blows the 2048-token
    # context and drives prefill RAM/CPU on the shared 8GB box, degrading every other student.
    message: str = Field(max_length=8000)
    conversation_id: str | None = Field(
        None,
        max_length=64,
        description="Omit to start a new thread; pass to continue one (multi-turn memory).",
    )
    client_request_id: str | None = Field(
        None,
        max_length=64,
        description=(
            "Browser-generated id for recovering a new-chat start across an immediate refresh."
        ),
    )
    mode: TutoringMode = TutoringMode.socratic
    persona: Persona = Persona.teacher
    subject: Subject = Subject.math
    language: str = Field(
        "en",
        min_length=2,
        max_length=16,
        pattern=r"^(?:auto|[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,2})$",
        description=(
            "Preferred response language as 'auto' or a BCP 47 tag (for example en, de, "
            "sw, ar, pga-Latn). Auto follows the primary language in the latest user "
            "message. The gateway places this preference in the system prompt; it does not "
            "modify the user's message."
        ),
    )
    stream: bool = Field(
        False, description="When true the server replies with an SSE token stream instead."
    )
    thinking: Literal["off", "auto", "extended"] | None = Field(
        None,
        description=(
            "Reasoning effort for this turn: 'off' answers directly (no thinking, fastest), "
            "'auto' thinks first (default behaviour), 'extended' thinks and gives a fuller "
            "answer. Null uses the server default."
        ),
    )
    regenerate: bool = Field(
        False,
        description=(
            "Re-answer the current last user turn WITHOUT adding a new user message. Used by "
            "'answer now' to replace an in-flight reply (e.g. skip the thinking phase)."
        ),
    )
    use_web: bool = Field(
        False,
        description=(
            "Opt-in web grounding: when the box is online and a search endpoint is "
            "configured, the answer is grounded with fresh snippets and their sources "
            "are returned. Ignored (silently) offline or unconfigured."
        ),
    )
    use_rag: bool = Field(
        False,
        description=(
            "Opt-in retrieval over learner-owned resources. When enabled, resource_ids must "
            "identify the ready files selected with the chat @ picker."
        ),
    )
    resource_ids: list[ResourceId] = Field(
        default_factory=list,
        max_length=8,
        description=(
            "Opaque ids of learner-owned resources selected for this turn. Display names are "
            "never used for authorization or retrieval scope."
        ),
    )
    attachment_ids: list[int] = Field(
        default_factory=list,
        max_length=32,
        description="Previously-uploaded attachments to link to this message.",
    )


class ResourceCitation(BaseModel):
    resource_id: ResourceId
    title: str
    page: int = Field(ge=1, description="One-based physical PDF page number.")
    chunk_index: int = Field(ge=0)
    excerpt: str = Field(max_length=500)


class ChatResponse(BaseModel):
    student_id: str
    conversation_id: str = Field(
        description="Pass back in the next request to continue the thread."
    )
    mode: TutoringMode
    reply: str = Field(
        description=(
            "Assistant Markdown. A visual text turn may end with one fenced `muta-viz` JSON "
            "object; clients may validate/render it as documented in docs/api/EXAMPLES.md."
        )
    )
    verified: bool = Field(
        False, description="Whether math in the reply was checked by the `math` service."
    )
    citations: list[str] = Field(default_factory=list, description="RAG source references.")
    resource_citations: list[ResourceCitation] = Field(
        default_factory=list,
        description="Structured, server-owned citations into uploaded learner resources.",
    )


class GenerationStarted(BaseModel):
    """A server-owned generation that can be re-subscribed after browser navigation."""

    job_id: str
    conversation_id: str
    client_request_id: str | None = None
    state: Literal["queued", "running"] = "running"
    queue_position: int = 0


class GenerationStatus(BaseModel):
    job_id: str
    conversation_id: str
    state: Literal["queued", "running", "completed", "failed", "stopped"]
    created_at: str
    client_request_id: str | None = None
    queue_position: int = 0


class GenerationList(BaseModel):
    generations: list[GenerationStatus] = Field(default_factory=list)


class GenerationStopped(BaseModel):
    job_id: str
    stopping: bool


class UserSettings(BaseModel):
    """Learner-facing product preferences stored with the existing private user record."""

    allow_parallel_chats: bool = Field(
        True,
        description=(
            "Allow a learner to use more than one of the operator-budgeted inference slots "
            "across separate conversations. This never changes the server's slot/RAM ceiling."
        ),
    )
    power_optimization_enabled: bool = Field(
        True,
        description=(
            "Use battery-aware response limits for this learner when the host is discharging. "
            "Memory, thermal and critical host safeguards cannot be disabled."
        ),
    )


# --- Muta Share (offline LAN accounts + host control) ---------------------------------


class ShareStatus(BaseModel):
    enabled: bool = False
    secure: bool = False
    authenticated: bool = False
    role: Literal["host", "member"] | None = None
    user_id: str | None = None
    username: str | None = None
    join_url: str | None = None
    message: str = ""


class ShareCredentials(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=256)


class ShareSignupResponse(BaseModel):
    enrollment_id: str
    enrollment_secret: str = Field(
        description="One-time secret used only to poll/exchange this approval request."
    )
    status: Literal["pending"] = "pending"
    username: str
    expires_at: str


class ShareEnrollmentExchange(BaseModel):
    secret: str = Field(min_length=32, max_length=128)


class ShareEnrollmentResponse(BaseModel):
    status: Literal["pending", "approved", "rejected", "removed", "expired"]
    username: str | None = None
    authenticated: bool = False
    user_id: str | None = None
    can_login: bool = False


class ShareSessionResponse(BaseModel):
    authenticated: bool = True
    user_id: str
    username: str
    role: Literal["member"] = "member"
    expires_at: str


class ShareLogoutResponse(BaseModel):
    logged_out: bool = True


class ShareUser(BaseModel):
    id: str
    username: str
    status: Literal["pending", "approved", "deleting"]
    created_at: str
    approved_at: str | None = None
    last_login_at: str | None = None


class ShareHostUpdate(BaseModel):
    enabled: bool
    memory_mode: Literal["competition", "system"] = "competition"


class ShareHostStatus(BaseModel):
    enabled: bool
    memory_mode: Literal["competition", "system"]
    listener_running: bool = False
    join_urls: list[str] = Field(default_factory=list)
    certificate_fingerprint: str | None = None
    users: list[ShareUser] = Field(default_factory=list)
    capacity: dict = Field(default_factory=dict)
    updated_at: str
    warning: str | None = None


class ShareUserAction(BaseModel):
    id: str
    status: Literal["approved", "rejected", "removed"]
    erased: dict[str, int] = Field(default_factory=dict)


class PowerStatus(BaseModel):
    """Battery state of the laptop serving Muta, plus the effective learner policy."""

    optimization_enabled: bool = True
    available: bool = False
    mode: Literal["normal", "eco", "critical"] = Field(
        "normal", description="Effective response policy for this learner."
    )
    host_mode: Literal["normal", "eco", "critical"] = Field(
        "normal", description="Shared serving laptop state before the learner preference."
    )
    on_battery: bool | None = None
    external_power_connected: bool | None = None
    charging: bool | None = None
    percentage: float | None = Field(None, ge=0, le=100)
    energy_wh: float | None = Field(None, ge=0)
    energy_full_wh: float | None = Field(None, ge=0)
    energy_rate_w: float | None = Field(None, ge=0)
    time_to_empty_s: int | None = Field(None, ge=0)
    source: str = "unavailable"
    actions: list[str] = Field(default_factory=list)


# --- /diagnose -------------------------------------------------------------------------


class DiagnoseRequest(BaseModel):
    student_id: str
    subject: Subject = Subject.math
    topic: str | None = Field(None, description="Optional focus; otherwise diagnose broadly.")


class DiagnoseResponse(BaseModel):
    student_id: str
    weak_topics: list[str] = Field(default_factory=list)
    plan: list[str] = Field(default_factory=list, description="Concrete next steps (e.g. 7-day).")


# --- /generate_question ----------------------------------------------------------------


class GenerateQuestionRequest(BaseModel):
    subject: Subject = Subject.math
    topic: str
    difficulty: int = Field(3, ge=1, le=5)
    exam_board: str = "WAEC"
    count: int = Field(1, ge=1, le=20)


class GeneratedQuestion(BaseModel):
    question_text: str
    options: list[str] | None = Field(None, description="Present for objective (Paper 1) items.")
    correct_answer: str
    worked_solution: str
    marking_scheme: str | None = Field(None, description="Method + answer marks (Paper 2).")
    topic_tags: list[str] = Field(default_factory=list)
    difficulty: int = Field(3, ge=1, le=5)


class GenerateQuestionResponse(BaseModel):
    questions: list[GeneratedQuestion] = Field(default_factory=list)


# --- /mastery/{student_id} -------------------------------------------------------------


class MasteryResponse(BaseModel):
    student_id: str
    subject: Subject
    mastery: dict[str, float] = Field(
        default_factory=dict, description="topic_id -> mastery in [0, 1] on the curriculum DAG."
    )
    next_topic: str | None = Field(None, description="Next-best lesson given prerequisites.")


# --- /verify (SymPy) -------------------------------------------------------------------


class VerifyRequest(BaseModel):
    expression: str = Field(description="A claim/step to check, e.g. 'd/dx(x^2) == 2*x'.")
    context: str | None = Field(None, description="Optional assumptions/variable domains.")


class VerifyResponse(BaseModel):
    verified: bool
    normalized: str | None = Field(None, description="Canonical form the checker computed.")
    detail: str | None = Field(None, description="Why it failed, when it did.")


# --- /tutor/* — the TDD §7.2 surface ----------------------------------------------------
# Added alongside the original endpoints rather than replacing them: the contract rule is
# additive-only from 2026-08-01, and existing clients (the TUI, bench/) already bind to
# /chat and /verify. Same shapes, different entry points.


class TutorMode(str, Enum):
    """TDD Appendix D. `dialogue` and `solution` differ in sampling (§6.5), `marking` also in
    grammar, `hint` also in which model answers (§7.6)."""

    dialogue = "dialogue"
    solution = "solution"
    marking = "marking"
    hint = "hint"


class ChatTurn(BaseModel):
    session_id: str = Field(description="One student's tutoring session; keys slot + twin.")
    text: str = Field(max_length=4096, description="Input cap per turn (S12: prompt-bomb guard).")
    mode: TutorMode = TutorMode.dialogue
    lang: str = Field(
        "en",
        min_length=2,
        max_length=16,
        pattern=r"^(?:auto|[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,2})$",
        description=(
            "Preferred response language as 'auto' or a BCP 47 tag. It is generation "
            "metadata and is never added to the learner's text."
        ),
    )
    student_id: str | None = Field(None, description="Defaults to session_id when omitted.")
    stream: bool = Field(
        False,
        description=(
            "Kept for client symmetry. Token streaming has its own path — POST "
            "/v1/tutor/chat/stream (text/event-stream) — because one operation cannot "
            "honestly declare two response media types in the schema."
        ),
    )


class TutorReply(BaseModel):
    session_id: str
    reply: str = Field(
        description="Assistant Markdown, optionally ending in one fenced `muta-viz` JSON object."
    )
    mode: TutorMode
    verified: bool = False
    citations: list[str] = Field(default_factory=list)
    queued: bool = Field(False, description="True when the turn waited for a slot (§8.2).")
    queue_position: int = 0
    degradation_level: str = Field("L0", description="Ladder level at the time of the turn (§5.3).")


class VisionReply(BaseModel):
    session_id: str
    transcription: str = Field("", description="What the model read from the image.")
    analysis: str = ""
    accepted: bool = Field(True, description="False when the image guard or the ladder refused.")
    detail: str = Field("", description="Why it was refused, in words a student can act on.")
    attachment_id: int | None = Field(
        None, description="Stored image attachment; pass in ChatRequest.attachment_ids."
    )


class AnswerCheckRequest(BaseModel):
    candidate: str = Field(description="The answer to check — bare, boxed, or inside prose.")
    expected: str
    tolerance: float = Field(0.0, ge=0.0, le=1.0, description="Relative tolerance; 0 = exact.")


class AnswerCheckResponse(BaseModel):
    verified: bool
    checked: bool = Field(description="False when no verdict was possible — not the same as wrong.")
    normalized_candidate: str = ""
    normalized_expected: str = ""
    detail: str = ""


class ExamAnswerRequest(BaseModel):
    """Score a student's answer to a known question and move their mastery on that topic. The
    expected answer comes from the question bank, so this is real evidence — unlike free-chat
    volume, which never touches mastery."""

    student_id: str = Field(max_length=128)
    topic: str = Field(max_length=80, description="Curriculum topic the answer scores mastery on.")
    candidate: str = Field(max_length=4096, description="The student's submitted answer.")
    expected: str = Field(max_length=4096, description="The correct answer (from the question).")
    tolerance: float = Field(0.0, ge=0.0, le=1.0)


class RenderRequest(BaseModel):
    kind: Literal["matplotlib", "svg"] = "matplotlib"
    code: str = Field(max_length=8192)


class RenderResponse(BaseModel):
    svg: str = ""
    ok: bool = True
    error: str = ""
    fallback_text: str = Field("", description="Description to show when rendering failed (S5).")


class SessionActionResponse(BaseModel):
    session_id: str
    action: Literal["suspend", "resume"]
    ok: bool
    detail: str = ""


class SystemStatus(BaseModel):
    """`/v1/metrics` — the local health panel's data (TDD §12). All local, no exporter."""

    degradation: dict = Field(default_factory=dict)
    sessions: dict = Field(default_factory=dict)
    vision: dict = Field(default_factory=dict)
    engine: dict = Field(default_factory=dict)


# --- conversations & attachments (web UI surface; additive) ----------------------------


class LearningResource(BaseModel):
    id: ResourceId
    name: str
    mime: Literal["application/pdf"] = "application/pdf"
    status: Literal["processing", "ready", "failed"]
    page_count: int | None = Field(None, ge=1)
    error: str | None = None
    created_at: str
    updated_at: str


class ResourceList(BaseModel):
    resources: list[LearningResource] = Field(default_factory=list)


class ResourceDeleted(BaseModel):
    id: ResourceId
    deleted: bool = True


class AttachmentRef(BaseModel):
    id: int
    kind: Literal["image", "audio"]
    mime: str


class MessageOut(BaseModel):
    id: int
    role: str
    content: str = Field(
        description=(
            "Persisted message text. Assistant messages may include the fenced `muta-viz` "
            "protocol described in docs/api/EXAMPLES.md."
        )
    )
    created_at: str
    attachments: list[AttachmentRef] = Field(default_factory=list)
    resource_citations: list[ResourceCitation] = Field(default_factory=list)


class ConversationOut(BaseModel):
    id: str
    student_id: str
    title: str | None = None
    mode: str | None = None
    created_at: str
    updated_at: str


class ConversationList(BaseModel):
    conversations: list[ConversationOut] = Field(default_factory=list)


class MessageList(BaseModel):
    conversation_id: str
    messages: list[MessageOut] = Field(default_factory=list)


class ConversationDeleted(BaseModel):
    id: str
    deleted: bool = True


# --- auth & data-subject rights (additive) ---------------------------------------------


class AuthTokenRequest(BaseModel):
    student_id: str = Field(max_length=128, description="The per-device learner id to bind.")


class AuthTokenResponse(BaseModel):
    student_id: str
    token: str = Field(
        description=(
            "Bearer token for the /v1 data endpoints. Send as `Authorization: Bearer <token>` "
            "(or `?token=` on attachment URLs). Opaque; treat as a per-device secret."
        )
    )
    role: Literal["host", "member", "legacy"] = "legacy"
    csrf_token: str | None = None


class StudentErased(BaseModel):
    """Result of a data-subject erasure — the counts removed, for an auditable receipt."""

    student_id: str
    conversations: int = 0
    orphan_attachments: int = 0
    resources: int = 0
    settings: int = 0


class TranscribeResponse(BaseModel):
    text: str = Field(description="What the ASR heard; empty when nothing was recognised.")
    attachment_id: int | None = Field(None, description="Stored copy of the uploaded audio.")


class TelemetrySnapshot(BaseModel):
    """Per-conversation live telemetry. Unmeasurable metrics are null (the UI shows —),
    never an error: Docker-on-macOS has no CPU temperature, for example."""

    rss_gb: float = Field(description="Current RSS of the whole backend process tree.")
    peak_rss_gb: float = Field(description="Peak tree RSS since the backend started.")
    cpu_temp_c: float | None = Field(None, description="CPU package temp; null if unreadable.")
    throttled: bool | None = Field(
        None, description="temp > 85 °C; null when the temperature is unreadable."
    )
    tokens_per_second: float | None = Field(
        None, description="Rolling decode rate of this conversation's active generation."
    )
    generating: bool = False
