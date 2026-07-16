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
