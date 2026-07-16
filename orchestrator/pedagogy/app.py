"""`pedagogy` service — curriculum DAG, learning twin, tutoring modes, personas.

Pure logic + SQLite; changes daily, so it benefits most from isolation (ROADMAP A.2).
"""

from __future__ import annotations

from fastapi import HTTPException

from contracts.models import DiagnoseRequest, DiagnoseResponse, MasteryResponse, Subject
from orchestrator._common import make_service

app = make_service("pedagogy")


@app.post("/diagnose", response_model=DiagnoseResponse, tags=["pedagogy"])
def diagnose(req: DiagnoseRequest) -> DiagnoseResponse:
    # TODO(Lane C): diagnose weak topics against the curriculum DAG; emit a concrete plan.
    raise HTTPException(status_code=501, detail="pedagogy.diagnose not implemented")


@app.get("/mastery/{student_id}", response_model=MasteryResponse, tags=["pedagogy"])
def mastery(student_id: str, subject: Subject = Subject.math) -> MasteryResponse:
    # TODO(Lane C): read the learning twin; return per-topic mastery + next-best lesson.
    raise HTTPException(status_code=501, detail="pedagogy.mastery not implemented")
