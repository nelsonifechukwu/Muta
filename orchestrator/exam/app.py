"""`exam` service — question generator, marking schemes, WAEC-Bench.

Independently testable against known-good items (ROADMAP A.2). The generator also feeds
the contamination probe's real-vs-generated gap (ROADMAP 18 Jul, Decision 3).
"""

from __future__ import annotations

from fastapi import HTTPException

from contracts.models import GenerateQuestionRequest, GenerateQuestionResponse
from orchestrator._common import make_service

app = make_service("exam")


@app.post("/generate_question", response_model=GenerateQuestionResponse, tags=["exam"])
def generate_question(req: GenerateQuestionRequest) -> GenerateQuestionResponse:
    # TODO(Lane C, 24 Jul): WASSCE-style item + worked solution + difficulty + marking scheme.
    raise HTTPException(status_code=501, detail="exam.generate_question not implemented")
