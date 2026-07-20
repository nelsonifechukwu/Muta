"""Deploy entrypoint — assembles the one process that ships (ROADMAP A.2/A.3).

    uvicorn orchestrator.main:app

- The public contract is the `/v1` router included on THIS app, so the whole surface is a
  single OpenAPI document at `/openapi.json` that clients bind to. Nothing bypasses it.
- The logical services are `app.mount()`-ed under `/internal/*`. They are implementation
  detail (absent from the `/v1` schema) and each also runs standalone in dev, e.g.
  `uvicorn orchestrator.math.app:app`. Mounting is what makes the collapse a config
  change, not a refactor.

Target topology on the deploy machine: two processes — `llama-server` and this app.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from orchestrator.bench_metrics import PIDFILE
from orchestrator.bench_metrics import app as bench_app
from orchestrator.exam.app import app as exam_app
from orchestrator.gateway.routes import router as gateway_router
from orchestrator.math.app import app as math_app
from orchestrator.pedagogy.app import app as pedagogy_app
from orchestrator.retrieval.app import app as retrieval_app

API_PREFIX = "/v1"


@contextlib.asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Write the pidfile that bench/monitor.py attaches by.

    On the lifespan hook rather than at import, because import happens BEFORE the socket is
    bound: a second instance that loses the race for the port would otherwise clobber the
    running instance's pidfile and then delete it on the way out. Uvicorn runs lifespan
    startup only after a successful bind.

    Failure to write is never fatal — this is telemetry convenience, and the monitor falls
    back to probing the port.
    """
    with contextlib.suppress(OSError):
        PIDFILE.parent.mkdir(parents=True, exist_ok=True)
        PIDFILE.write_text(f"{os.getpid()}\n")
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            if PIDFILE.is_file() and PIDFILE.read_text().strip() == str(os.getpid()):
                PIDFILE.unlink()


app = FastAPI(
    title="Muta — Offline Adaptive Tutor",
    version="0.1.0",
    description=(
        "ADTC 2026. The only public surface is the versioned /v1 contract; every client "
        "— browser, phones, eval.py, CLI — speaks only /v1."
    ),
    lifespan=_lifespan,
)

# Public contract: the ONLY surface clients address.
app.include_router(gateway_router, prefix=API_PREFIX)

# Logical services, collapsed into this process. Internal — not part of the /v1 contract.
app.mount("/internal/math", math_app)
app.mount("/internal/retrieval", retrieval_app)
app.mount("/internal/pedagogy", pedagogy_app)
app.mount("/internal/exam", exam_app)
app.mount("/internal/bench", bench_app)




@app.get("/", include_in_schema=False)
def root() -> JSONResponse:
    return JSONResponse(
        {"service": "muta", "contract": API_PREFIX, "docs": "/docs", "openapi": "/openapi.json"}
    )


# Static UI, served only once built (ROADMAP 18 Jul: bundled, no CDN). Mounted last so it
# can never shadow the API. The browser UI is the first client of /v1, not a privileged one.
_ui_dist = Path(__file__).resolve().parent.parent / "ui" / "dist"
if _ui_dist.is_dir():
    app.mount("/ui", StaticFiles(directory=str(_ui_dist), html=True), name="ui")
