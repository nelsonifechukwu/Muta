"""Request/response models for the public `/v1` surface — the source of truth.

Kept deliberately small: the minimum endpoint surface from ROADMAP.md (16 Jul). The
`subject` axis carries physics/chemistry/biology from day one (the competition domain is
Math *and* Scientific Reasoning), so downstream consumers never have to retrofit it.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


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


class ReadyResponse(BaseModel):
    ready: bool
    checks: dict[str, bool] = Field(
        default_factory=dict, description="Per-dependency readiness (llama-server, sub-apps)."
    )


# --- /chat -----------------------------------------------------------------------------


class ChatRequest(BaseModel):
    student_id: str = Field(description="Stable per-learner id; keys the learning twin.")
    message: str
    conversation_id: str | None = Field(
        None, description="Omit to start a new thread; pass to continue one (multi-turn memory)."
    )
    mode: TutoringMode = TutoringMode.socratic
    persona: Persona = Persona.teacher
    subject: Subject = Subject.math
    language: str = Field("en", description="BCP-47-ish tag: en, fr, ha, yo, ig, sw, ar, am, zu.")
    stream: bool = Field(
        False, description="When true the server replies with an SSE token stream instead."
    )


class ChatResponse(BaseModel):
    student_id: str
    conversation_id: str = Field(description="Pass back in the next request to continue the thread.")
    mode: TutoringMode
    reply: str
    verified: bool = Field(
        False, description="Whether math in the reply was checked by the `math` service."
    )
    citations: list[str] = Field(default_factory=list, description="RAG source references.")


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
    lang: str = "en"
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
    reply: str
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
