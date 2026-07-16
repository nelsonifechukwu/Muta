"""Shared helper for the internal sub-apps.

Each logical service is a full FastAPI app (not just a router) so it can run standalone
in development and be `app.mount()`-ed into one process at deploy — the collapse the
architecture depends on (ROADMAP A.2).
"""

from __future__ import annotations

from fastapi import FastAPI

from contracts.models import HealthResponse


def make_service(name: str) -> FastAPI:
    app = FastAPI(title=f"muta-{name}", version="0.1.0")

    @app.get("/health", response_model=HealthResponse, tags=["ops"])
    def health() -> HealthResponse:
        return HealthResponse(service=name)

    return app
