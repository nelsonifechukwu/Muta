"""`math` service — verified computation (SymPy/NumPy), sandboxed and timeout-bounded.

A hang here must not take the gateway down; keep it isolated (ROADMAP A.2).
"""

from __future__ import annotations

from fastapi import HTTPException

from contracts.models import VerifyRequest, VerifyResponse
from orchestrator._common import make_service

app = make_service("math")


@app.post("/verify", response_model=VerifyResponse, tags=["math"])
def verify(req: VerifyRequest) -> VerifyResponse:
    # TODO(Lane B, 25 Jul): route arithmetic/algebra/calculus through SymPy; enforce a
    # subprocess timeout so a pathological expression cannot hang the service.
    raise HTTPException(status_code=501, detail="math.verify not implemented")
