"""`retrieval` service — FAISS over past papers / formula sheets, plus context assembly.

The one service with a real memory footprint of its own (index + embedder), so it counts
directly against the 7 GB budget. `SearchRequest` is internal — retrieval is not part of the
public `/v1` contract, so its shapes live here, not in `contracts`.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel, Field

from orchestrator._common import make_service
from orchestrator.retrieval.embedder import ServerEmbedder
from orchestrator.retrieval.index import IndexMismatch, Retriever

log = logging.getLogger("muta.retrieval")

app = make_service("retrieval")


def index_dir() -> Path:
    return Path(os.environ.get("TUTOR_INDEX_DIR") or Path(os.environ.get("TUTOR_ROOT", "/opt/tutor")) / "index")


@lru_cache(maxsize=1)
def get_retriever() -> Retriever:
    """One process-wide retriever. Cached because opening it mmaps the vectors, and the
    gateway's 600 MiB cap has no room for a second copy per request."""
    embedder = ServerEmbedder(
        base_url=f"http://127.0.0.1:{os.environ.get('TUTOR_EMBED_PORT', '8083')}"
    )
    return Retriever.open(index_dir(), embedder)


class SearchRequest(BaseModel):
    query: str
    k: int = Field(5, ge=1, le=50)
    min_score: float = Field(0.0, ge=-1.0, le=1.0)


class SearchHit(BaseModel):
    doc_id: str
    chunk_id: int
    text: str
    score: float
    cite: str


class SearchResponse(BaseModel):
    hits: list[SearchHit] = Field(default_factory=list)
    backend: str = ""


@app.post("/search", response_model=SearchResponse, tags=["retrieval"])
def search(req: SearchRequest) -> SearchResponse:
    try:
        retriever = get_retriever()
    except FileNotFoundError as e:
        # No index staged: RAG is off, and the tutor answers from the model alone. A 503 says
        # "not right now" rather than pretending the corpus is empty (which reads as "no such
        # topic in the syllabus").
        raise HTTPException(status_code=503, detail=f"no index at {index_dir()}: {e}") from e
    except IndexMismatch as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    hits = retriever.search(req.query, req.k, min_score=req.min_score)
    return SearchResponse(
        backend=retriever.index.backend,
        hits=[
            SearchHit(doc_id=h.doc_id, chunk_id=h.chunk_id, text=h.text, score=h.score, cite=h.cite)
            for h in hits
        ],
    )
