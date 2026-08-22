"""Standalone gateway app for split-mode development (`uvicorn orchestrator.gateway.app:app`).

At deploy the same router is included on `orchestrator.main` under `/v1`.
"""

from __future__ import annotations

from fastapi import FastAPI

from orchestrator.gateway.body_limit import RequestBodyLimitMiddleware
from orchestrator.gateway.firewall import enforce_share_firewall
from orchestrator.gateway.routes import router
from orchestrator.gateway.share_routes import router as share_router

app = FastAPI(title="muta-gateway", version="0.1.0")
app.add_middleware(RequestBodyLimitMiddleware)
app.include_router(router)
app.include_router(share_router)


@app.middleware("http")
async def _sharing_firewall(request, call_next):
    return await enforce_share_firewall(request, call_next, api_prefix="")
