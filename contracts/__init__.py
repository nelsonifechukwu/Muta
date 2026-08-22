"""The frozen `/v1` API contract — the single cross-cutting artifact of the project.

Every client (the gateway, the internal sub-apps, `bench/eval.py`, `bench/cli.py`, and
the UI's type codegen) imports request/response shapes from here. `contracts/openapi.yaml`
is GENERATED from these Pydantic models via `python -m contracts.openapi` (`make contract`);
never hand-edit the YAML. See ROADMAP.md (Thu 16 Jul — "Freeze the API contract today").
"""

from contracts.models import (
    ChatRequest,
    ChatResponse,
    DiagnoseRequest,
    DiagnoseResponse,
    GeneratedQuestion,
    GenerateQuestionRequest,
    GenerateQuestionResponse,
    HealthResponse,
    MasteryResponse,
    Persona,
    PowerStatus,
    ReadyResponse,
    Subject,
    TutoringMode,
    UserSettings,
    VerifyRequest,
    VerifyResponse,
)

__all__ = [
    "ChatRequest",
    "ChatResponse",
    "DiagnoseRequest",
    "DiagnoseResponse",
    "GeneratedQuestion",
    "GenerateQuestionRequest",
    "GenerateQuestionResponse",
    "HealthResponse",
    "MasteryResponse",
    "Persona",
    "PowerStatus",
    "ReadyResponse",
    "Subject",
    "TutoringMode",
    "UserSettings",
    "VerifyRequest",
    "VerifyResponse",
]
