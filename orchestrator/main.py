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

import asyncio
import contextlib
import logging
import os
import threading
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from orchestrator.bench_metrics import PIDFILE
from orchestrator.bench_metrics import app as bench_app
from orchestrator.exam.app import app as exam_app
from orchestrator.gateway.audio_routes import router as audio_router
from orchestrator.gateway.deps import get_vision
from orchestrator.gateway.routes import router as gateway_router
from orchestrator.math.app import app as math_app
from orchestrator.pedagogy.app import app as pedagogy_app
from orchestrator.retrieval.app import app as retrieval_app
from orchestrator.telemetry import get_hub
from runtime.config import RuntimeConfig
from runtime.server import LlamaServer

API_PREFIX = "/v1"
VISION_REAP_INTERVAL_S = 30.0

log = logging.getLogger("muta.orchestrator.main")


def _start_engine_thread(server: LlamaServer, log_file: Path) -> threading.Thread:
    """Start llama-server from a daemon thread, not inline: the model load can take minutes
    on an emulated box, and a raise inside lifespan would crash-loop the container. The
    gateway binds immediately; `/v1/ready` reports `inference:false` until the engine is up.
    """

    def _run() -> None:
        try:
            server.ensure(log_file=log_file)
        except Exception:  # noqa: BLE001 — startup failure is a degraded state, not a crash
            log.exception("llama-server failed to start; /v1/ready stays false")

    thread = threading.Thread(target=_run, name="engine-supervisor", daemon=True)
    thread.start()
    return thread


async def _vision_reaper() -> None:
    """Tick the CORE-VISION idle reaper: without it the ~3.3 GB ephemeral vision instance
    lives forever after the first image."""
    while True:
        await asyncio.sleep(VISION_REAP_INTERVAL_S)
        with contextlib.suppress(Exception):
            get_vision().reap_if_idle()


@contextlib.asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Pidfile for bench/monitor.py, plus (when MUTA_RT_AUTOSTART=1, i.e. in the backend
    container) engine supervision and the vision idle reaper.

    Pidfile on the lifespan hook rather than at import, because import happens BEFORE the
    socket is bound: a second instance that loses the race for the port would otherwise
    clobber the running instance's pidfile and then delete it on the way out. Failure to
    write is never fatal.
    """
    with contextlib.suppress(OSError):
        PIDFILE.parent.mkdir(parents=True, exist_ok=True)
        PIDFILE.write_text(f"{os.getpid()}\n")

    get_hub().start()  # 1 Hz RSS/temp sampling for /v1/conversations/{id}/telemetry

    cfg = RuntimeConfig()
    engine_server: LlamaServer | None = None
    reaper_task: asyncio.Task | None = None
    if cfg.autostart:
        root = Path(os.environ.get("TUTOR_ROOT", "/opt/tutor"))
        for sub in ("data/logs", "data/kv-slots"):
            # CORE-VISION's --log-file dies at startup if data/logs is missing.
            with contextlib.suppress(OSError):
                (root / sub).mkdir(parents=True, exist_ok=True)
        engine_server = LlamaServer(cfg)
        _start_engine_thread(engine_server, root / "data" / "logs" / "llama-server.log")
        reaper_task = asyncio.create_task(_vision_reaper())

    try:
        yield
    finally:
        if reaper_task is not None:
            reaper_task.cancel()
        if cfg.autostart:
            with contextlib.suppress(Exception):
                get_vision().stop()
        if engine_server is not None:
            with contextlib.suppress(Exception):
                engine_server.stop()  # no-op when we only attached to an external engine
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
app.include_router(audio_router, prefix=API_PREFIX)  # /v1/audio/transcribe + WS /v1/audio/voice

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
