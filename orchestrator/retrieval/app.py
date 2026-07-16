"""`retrieval` service — FAISS over past papers / formula sheets, plus context assembly.

The one service with a real memory footprint of its own (index + embedder), so it counts
directly against the 7 GB budget. `SearchRequest` is internal — retrieval is not part of
the public `/v1` contract, so its shapes live here, not in `contracts`.
"""

from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, Field

from orchestrator._common import make_service

app = make_service("retrieval")


class SearchRequest(BaseModel):
    query: str
    k: int = Field(5, ge=1, le=50)


@app.post("/search", tags=["retrieval"])
def search(req: SearchRequest):
    # TODO(Lane B, 27 Jul): embed the query, FAISS top-k, assemble context. Scored on
    # whether it earns its RAM (ROADMAP central thesis).
    raise HTTPException(status_code=501, detail="retrieval.search not implemented")
