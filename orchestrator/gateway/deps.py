"""Gateway dependencies: the shared ChatEngine, the mode → system-prompt loader, and the
process-wide objects the gateway owns (ladder, sessions, vision manager, tool pools — §7.1).

`get_*` are FastAPI dependencies (so tests can override them with fakes) and each builds one
process-wide instance. Construction touches no network and forks nothing — only the first
real request reaches llama-server or starts a sandbox worker — so importing the app stays
cheap and offline.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from functools import lru_cache
from pathlib import Path

from orchestrator.gateway.ladder import DegradationLadder
from orchestrator.gateway.sessions import SessionManager
from orchestrator.pedagogy.twin import TwinStore
from orchestrator.tools.renderer import DiagramRenderer
from orchestrator.tools.sandbox import ToolPools
from orchestrator.tools.verifier import AnswerVerifier
from runtime.chat import ChatEngine
from runtime.client import InferenceClient
from runtime.config import RuntimeConfig
from runtime.memory import ConversationStore
from runtime.profiles import BundlePaths, get_profile
from runtime.slots import SlotClient, SnapshotReaper
from runtime.vision import VisionManager

log = logging.getLogger("muta.gateway.deps")

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


@lru_cache(maxsize=8)
def load_prompt(mode: str) -> str:
    """Read a persona/system prompt for the mode, stripping the authoring comment header."""
    path = _PROMPTS_DIR / f"{mode}.md"
    if not path.exists():
        path = _PROMPTS_DIR / "socratic.md"
    return _COMMENT.sub("", path.read_text()).strip()


@lru_cache(maxsize=1)
def get_engine() -> ChatEngine:
    cfg = RuntimeConfig()
    client = InferenceClient(
        cfg.base_url,
        model=cfg.model_alias,
        enable_thinking=cfg.enable_thinking,
        timeout=cfg.request_timeout_s,
    )
    # Cloud boost (design P3, 2026-08-08): all three vars set = enabled. Two of three is
    # a misconfiguration, not a half-enabled cloud. The wrap only ever engages while the
    # connectivity probe says online; every failure path lands back on the local engine.
    cloud_url = os.environ.get("MUTA_CLOUD_URL")
    cloud_model = os.environ.get("MUTA_CLOUD_MODEL")
    cloud_key = os.environ.get("MUTA_CLOUD_API_KEY")
    if cloud_url and cloud_model and cloud_key:
        from orchestrator.gateway.connectivity import get_connectivity
        from runtime.cloud import CloudFallbackClient

        cloud = InferenceClient(
            cloud_url,
            model=cloud_model,
            api_key=cloud_key,
            template_kwargs=False,  # strict providers 400 on llama-server-only fields
            timeout=cfg.request_timeout_s,
        )
        client = CloudFallbackClient(
            cloud=cloud, local=client, online=lambda: get_connectivity().online()
        )
    store = ConversationStore(cfg.db_url)
    return ChatEngine(client, store, max_history_messages=cfg.max_history_messages)


@lru_cache(maxsize=1)
def get_ladder() -> DegradationLadder:
    """The memory ladder (§5.3). `core_rss_probe` is wired to the engine process: without it
    L4 — core server approaching its own cgroup cap — can never fire, and that is the one
    level that catches the dangerous case."""
    return DegradationLadder(core_rss_probe=core_rss_bytes)


def core_rss_bytes() -> int:
    """RSS of the llama-server process tree. RSS, not PSS: it is the unit the competition
    profiler scores (docs/rules-digest.md), so it is the unit the ladder reacts to."""
    try:
        import psutil
    except ImportError:
        return 0
    total = 0
    for process in psutil.process_iter(["name"]):
        try:
            if "llama-server" in (process.info.get("name") or "").lower():
                total += process.memory_info().rss
        except Exception:  # noqa: BLE001 — psutil raises several process-vanished flavours
            continue
    return total


@lru_cache(maxsize=1)
def get_slot_client() -> SlotClient:
    port = os.environ.get("TUTOR_CORE_PORT", "8081")
    key_file = BundlePaths.from_env().api_key_file
    api_key = key_file.read_text().strip() if key_file.is_file() else None
    return SlotClient(base_url=f"http://127.0.0.1:{port}", api_key=api_key)


@lru_cache(maxsize=1)
def get_reaper() -> SnapshotReaper:
    return SnapshotReaper(BundlePaths.from_env().slot_dir)


@lru_cache(maxsize=1)
def get_sessions() -> SessionManager:
    """Admission control (§8.2), wired to real suspend/resume and to the ladder."""
    profile = get_profile()
    ladder = get_ladder()
    slots = get_slot_client()
    reaper = get_reaper()
    manager: SessionManager

    def suspend(slot_index: int, session_id: str) -> None:
        slots.save(slot_index, session_id)
        # Reap after writing, protecting everything currently suspended: the directory cap is
        # 4 GiB and a full disk turns the next suspend into a failed write mid-lesson.
        reaper.reap(keep=set(manager.suspended) | {session_id})

    def resume(slot_index: int, session_id: str) -> bool:
        if not reaper.has(session_id):
            return False  # restore-miss → summary re-prefill (§8.3), not a cold start
        slots.restore(slot_index, session_id)
        reaper.touch(session_id)
        return True

    manager = SessionManager(
        slots_count=profile.n_parallel,
        suspend_hook=suspend,
        resume_hook=resume,
        effective_slots=lambda: ladder.evaluate().effective_slots(profile.n_parallel),
        accepts_new_sessions=lambda: ladder.evaluate().accepts_new_sessions,
    )
    return manager


@lru_cache(maxsize=1)
def get_vision() -> VisionManager:
    return VisionManager(admit=lambda: get_ladder().may_spawn_vision())


@lru_cache(maxsize=1)
def get_tool_pools() -> ToolPools:
    """Warm sandbox workers, created lazily: importing the app must not fork four Python
    interpreters, and a text-only deployment should never pay for the renderer at all."""
    return ToolPools()


@lru_cache(maxsize=1)
def get_verifier() -> AnswerVerifier:
    return AnswerVerifier(get_tool_pools().verifier)


@lru_cache(maxsize=1)
def get_twin_store() -> TwinStore:
    """The learning twin lives under TUTOR_ROOT/data/twins (atomic JSON per student). It is the
    personalisation + session-summary layer (pedagogy/twin.py); wiring it here is what turns
    the orphaned module into live adaptivity. A real deploy sets TUTOR_ROOT=/app (writable);
    if the configured path is not writable (e.g. the default /opt/tutor in a dev shell) the
    store degrades to an ephemeral temp dir rather than 500ing the pedagogy endpoints."""
    target = Path(os.environ.get("TUTOR_ROOT", "/opt/tutor")) / "data" / "twins"
    try:
        return TwinStore(target)
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "muta-twins"
        log.warning("twin dir %s not writable — using ephemeral %s (set TUTOR_ROOT)", target, fallback)
        return TwinStore(fallback)


@lru_cache(maxsize=1)
def get_renderer() -> DiagramRenderer:
    return DiagramRenderer(get_tool_pools().renderer)
