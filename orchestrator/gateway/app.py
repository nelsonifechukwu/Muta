"""Standalone gateway app for split-mode development (`uvicorn orchestrator.gateway.app:app`).

At deploy the same router is included on `orchestrator.main` under `/v1`.
"""

from __future__ import annotations

from fastapi import FastAPI

from orchestrator.gateway.routes import router

app = FastAPI(title="muta-gateway", version="0.1.0")
app.include_router(router)
