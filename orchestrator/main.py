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

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from orchestrator.bench_metrics import PIDFILE
from orchestrator.bench_metrics import app as bench_app
from orchestrator.exam.app import app as exam_app
from orchestrator.gateway.audio_routes import router as audio_router
from orchestrator.gateway.deps import get_generation_manager, get_vision, set_model_manager
from orchestrator.gateway.routes import router as gateway_router
from orchestrator.logging_config import configure_logging
from orchestrator.math.app import app as math_app
from orchestrator.pedagogy.app import app as pedagogy_app
from orchestrator.retrieval.app import app as retrieval_app
from orchestrator.telemetry import get_hub
from orchestrator.version import git_sha
from runtime.config import RuntimeConfig
from runtime.model_catalog import ModelManager
from runtime.server import LlamaServer

configure_logging()  # make muta.* logs visible in the container before anything logs

API_PREFIX = "/v1"
VISION_REAP_INTERVAL_S = 30.0
# How often the supervisor checks the engine is still alive, and the backoff bounds for a
# respawn after a crash (e.g. an OOM-kill on the 8GB box — the exact risk the ladder exists
# for). Bounded so a persistently-failing engine does not busy-loop.
ENGINE_POLL_INTERVAL_S = 5.0
ENGINE_RESPAWN_BACKOFF_MIN_S = 2.0
ENGINE_RESPAWN_BACKOFF_MAX_S = 60.0

log = logging.getLogger("muta.orchestrator.main")

# Restart bookkeeping the readiness probe can surface, so a crash-looping engine is visible
# from outside the container.
_engine_state: dict[str, object] = {"restarts": 0, "last_exit_code": None, "supervising": False}


def engine_state() -> dict[str, object]:
    return dict(_engine_state)


def _start_engine_thread(
    server: LlamaServer, log_file: Path | None, *, stop: threading.Event | None = None
) -> tuple[threading.Thread, threading.Event]:
    """Supervise llama-server for the life of the process, not just at boot.

    The old version called `ensure()` once and let the thread exit — so an engine that was
    OOM-killed or segfaulted mid-semester left every request 503ing forever with no restart.
    This loops: (re)start the engine, wait on the child, and when it dies (or fails to start)
    respawn with capped exponential backoff. A daemon thread + a stop Event so lifespan
    shutdown ends it cleanly. ``stop`` is injectable for tests.
    """
    stop = stop or threading.Event()

    def _run() -> None:
        _engine_state["supervising"] = True
        backoff = ENGINE_RESPAWN_BACKOFF_MIN_S
        while not stop.is_set():
            try:
                _, managed = server.ensure(log_file=log_file)
            except Exception:  # noqa: BLE001 — a start failure is degraded, not fatal
                log.exception("llama-server failed to start; retrying in %.0fs", backoff)
                if stop.wait(backoff):
                    break
                backoff = min(backoff * 2, ENGINE_RESPAWN_BACKOFF_MAX_S)
                continue
            backoff = ENGINE_RESPAWN_BACKOFF_MIN_S  # a clean start resets the backoff
            if not managed:
                # Attached to an externally-run engine (dev) — we don't own its lifecycle.
                log.info("attached to external llama-server; supervision loop idle")
                return
            proc = server.process
            if proc is None:
                return
            # Block until the child exits, checking the stop flag periodically.
            while not stop.is_set():
                try:
                    code = proc.wait(timeout=ENGINE_POLL_INTERVAL_S)
                except Exception:  # noqa: BLE001 — TimeoutExpired and friends
                    continue
                _engine_state["last_exit_code"] = code
                if stop.is_set():
                    return
                planned = getattr(server, "consume_planned_exit", lambda _: False)(proc)
                if planned:
                    log.info("llama-server stopped for a requested model change")
                    break
                _engine_state["restarts"] = int(_engine_state["restarts"]) + 1  # type: ignore[arg-type]
                log.error(
                    "llama-server exited with code %s — respawning (restart #%s)",
                    code,
                    _engine_state["restarts"],
                )
                break  # fall back to the outer loop to restart

    thread = threading.Thread(target=_run, name="engine-supervisor", daemon=True)
    thread.start()
    return thread, stop


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

    from orchestrator.gateway.connectivity import get_connectivity

    get_connectivity().start()  # ~1/min online/offline verdict for /v1/ready and the UI

    # Load + warm the TTFT preamble model at boot (no-op unless MUTA_RT_TTFT_PREAMBLE=1).
    # Doing it lazily would put its ~50 ms load and 32 ms cold generation on the first
    # student's first turn — the exact request the preamble exists to make feel instant.
    with contextlib.suppress(Exception):
        from orchestrator.gateway.deps import get_preamble_writer

        get_preamble_writer()

    cfg = RuntimeConfig()
    engine_server: ModelManager | None = None
    engine_stop: threading.Event | None = None
    reaper_task: asyncio.Task | None = None
    if cfg.autostart:
        root = Path(os.environ.get("TUTOR_ROOT", "/opt/tutor"))
        for sub in ("data/logs", "data/kv-slots"):
            # CORE-VISION's --log-file dies at startup if data/logs is missing.
            with contextlib.suppress(OSError):
                (root / sub).mkdir(parents=True, exist_ok=True)
        engine_server = ModelManager(
            cfg,
            root=root,
            log_file=root / "data" / "logs" / "llama-server.log",
            server_factory=LlamaServer,
        )
        set_model_manager(engine_server)
        _, engine_stop = _start_engine_thread(
            engine_server, root / "data" / "logs" / "llama-server.log"
        )
        reaper_task = asyncio.create_task(_vision_reaper())

    try:
        yield
    finally:
        try:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(get_generation_manager().shutdown)
        finally:
            # A FastAPI app can run more than one lifespan in an in-process test/embedding.
            # Never hand the next lifespan a registry that correctly refuses post-shutdown work.
            get_generation_manager.cache_clear()
        with contextlib.suppress(Exception):
            get_connectivity().stop()
        if engine_stop is not None:
            engine_stop.set()  # tell the supervisor to stop respawning before we kill the child
        if reaper_task is not None:
            reaper_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reaper_task
        if cfg.autostart:
            with contextlib.suppress(Exception):
                get_vision().stop()
        if engine_server is not None:
            with contextlib.suppress(Exception):
                engine_server.stop()  # no-op when we only attached to an external engine
        set_model_manager(None)
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

@app.middleware("http")
async def _request_id(request, call_next):
    """Accept an inbound X-Request-ID (from nginx / a client) or mint one, expose it to every
    log line via the contextvar, and echo it back so a caller can quote it in a bug report."""
    import uuid

    from orchestrator.request_context import request_id_var

    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    token = request_id_var.set(rid)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = rid
    # `/chat` is a small, local bundle. Do not retain it: conditional Last-Modified handling can
    # otherwise accept a stale authored asset after a same-second export or a rollback, combining
    # a new index.html with an old app.js/stylesheet (the unauthenticated-client + huge-SVG bug).
    if request.url.path == "/chat" or request.url.path.startswith("/chat/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["X-Muta-UI-Revision"] = git_sha()
    return response


# Public contract: the ONLY surface clients address.
app.include_router(gateway_router, prefix=API_PREFIX)
app.include_router(audio_router, prefix=API_PREFIX)  # /v1/audio/transcribe + WS /v1/audio/voice

# Logical services, collapsed into this process. Internal — not part of the /v1 contract.
app.mount("/internal/math", math_app)
app.mount("/internal/retrieval", retrieval_app)
app.mount("/internal/pedagogy", pedagogy_app)
app.mount("/internal/exam", exam_app)
app.mount("/internal/bench", bench_app)




# Static browser surfaces, mounted only when their checked-in bundles are present. The app
# stays the first client of /v1, not a privileged one. Mount the public landing page last so
# its root catch-all cannot shadow the API, docs, internal services, or the app at /chat.
_ui_root = Path(__file__).resolve().parent.parent / "ui"
_ui_dist = _ui_root / "dist"
_ui_assets = _ui_dist if _ui_dist.is_dir() else _ui_root


def _redirect_with_query(request: Request, target: str) -> RedirectResponse:
    query = request.url.query
    url = f"{target}?{query}" if query else target
    return RedirectResponse(url=url, status_code=308)


@app.get("/chat", include_in_schema=False)
def chat_root(request: Request) -> RedirectResponse:
    """Give the canonical app route its trailing slash so relative assets resolve correctly."""
    return _redirect_with_query(request, "/chat/")


if (_ui_assets / "index.html").is_file():
    app.mount("/chat", StaticFiles(directory=str(_ui_assets), html=True), name="chat")


@app.get("/ui", include_in_schema=False)
def legacy_ui_root(request: Request) -> RedirectResponse:
    """Keep old bookmarks working after the public tutor moved to `/chat/`."""
    return _redirect_with_query(request, "/chat/")


@app.get("/ui/{asset_path:path}", include_in_schema=False)
def legacy_ui_path(asset_path: str, request: Request) -> RedirectResponse:
    """Preserve legacy deep asset paths without exposing a second copy of the app."""
    return _redirect_with_query(request, f"/chat/{asset_path.lstrip('/')}")

_landing_assets = Path(__file__).resolve().parent.parent / "landing"
if (_landing_assets / "index.html").is_file():
    app.mount("/", StaticFiles(directory=str(_landing_assets), html=True), name="landing")
