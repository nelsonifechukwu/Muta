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
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from orchestrator.gateway.capacity import CapacityPlanner, CapacityProfile
from orchestrator.gateway.generations import GenerationCapacityError, GenerationManager
from orchestrator.gateway.ladder import DegradationLadder
from orchestrator.gateway.power import PowerGovernor
from orchestrator.gateway.sessions import SessionManager
from orchestrator.pedagogy.twin import TwinStore
from orchestrator.retrieval.resources import ResourceService
from orchestrator.tools.renderer import DiagramRenderer
from orchestrator.tools.sandbox import ToolPools
from orchestrator.tools.verifier import AnswerVerifier
from runtime.chat import ChatEngine
from runtime.client import InferenceClient
from runtime.config import RuntimeConfig
from runtime.memory import ConversationStore
from runtime.model_catalog import ModelManager, ModelSwitchError
from runtime.paths import data_root, resource_root
from runtime.profiles import BundlePaths
from runtime.slots import SlotClient, SnapshotReaper
from runtime.ttft import PreambleWriter
from runtime.vision import VisionManager

log = logging.getLogger("muta.gateway.deps")

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_model_manager: ModelManager | None = None
_runtime_lifecycle_lock = threading.RLock()


@contextmanager
def runtime_lifecycle() -> Iterator[None]:
    """Serialize Host memory policy, model replacement, and persisted settings."""
    with _runtime_lifecycle_lock:
        yield


def set_model_manager(manager: ModelManager | None) -> None:
    global _model_manager
    _model_manager = manager


def get_model_manager() -> ModelManager | None:
    return _model_manager


def active_runtime_config() -> RuntimeConfig:
    """The live engine profile, including Host-mode capacity changes."""
    manager = get_model_manager()
    cfg = getattr(manager, "cfg", None) if manager is not None else None
    return cfg if isinstance(cfg, RuntimeConfig) else RuntimeConfig()


def refresh_engine_dependencies(profile: CapacityProfile | None = None) -> None:
    """Drop every cache whose state belongs to the replaced llama-server process."""
    # ChatEngine stays: it owns the durable DB pool and addresses the same loopback URL plus
    # stable launch alias retained by ModelManager. Rebuilding it on every switch would
    # leak/interrupt persistence for no model-specific benefit.
    get_sessions.cache_clear()
    cfg = active_runtime_config()
    per_student = None
    if profile is not None:
        per_student = (
            1 if profile.memory_mode == "competition" else min(2, max(1, profile.n_parallel - 1))
        )
    get_generation_manager().set_max_active(cfg.n_parallel, max_active_per_student=per_student)
    # ChatEngine owns the durable store and loopback client, so keep it alive but update the
    # prompt budget that depends on the physical lane count.
    if get_engine.cache_info().currsize:
        engine = get_engine()
        engine.context_window_tokens = cfg.n_ctx // max(1, cfg.n_parallel)
        engine.image_token_budget = cfg.image_max_tokens
    if profile is not None:
        # The ladder probe measures llama-server RSS, while the planner's ceiling prices the
        # whole process tree. Reserve the gateway/ASR/TTS allowance before comparing core RSS
        # or the backend could cross 7 GiB while the engine-only signal still looked healthy.
        get_ladder().core_cap_bytes = max(
            1,
            profile.memory_ceiling_bytes
            - profile.gateway_reserve_bytes
            - profile.auxiliary_reserve_bytes,
        )
    removed = get_reaper().clear()
    if removed:
        log.info("removed %d model-specific KV snapshots after engine switch", len(removed))


class RuntimeCapacityController:
    """One authority for the slot/context/admission/ladder profile."""

    def __init__(self, planner: CapacityPlanner | None = None) -> None:
        self.planner = planner or CapacityPlanner()
        self._last_profile: CapacityProfile | None = None

    def plan(self, mode: str) -> CapacityProfile:
        cfg = active_runtime_config()
        return self.planner.plan(mode, cfg, current_cfg=cfg)

    def plan_config(
        self,
        mode: str,
        cfg: RuntimeConfig,
        *,
        current_cfg: RuntimeConfig | None = None,
    ) -> CapacityProfile:
        return self.planner.plan(mode, cfg, current_cfg=current_cfg)

    def status(self, mode: str) -> dict:
        planned = self.plan(mode)
        cfg = active_runtime_config()
        generations = get_generation_manager().status()
        payload = planned.as_dict()
        payload.update(
            {
                "active_parallel": cfg.n_parallel,
                "active_context": cfg.n_ctx,
                "restart_supported": get_model_manager() is not None,
                "running": generations["running"],
                "queued": generations["queued"],
                "reservations": generations["reservations"],
            }
        )
        return payload

    def snapshot(self) -> tuple[RuntimeConfig, str | None] | None:
        manager = get_model_manager()
        return manager.runtime_snapshot() if manager is not None else None

    def restore(self, snapshot: tuple[RuntimeConfig, str | None] | None, mode: str) -> dict:
        """Compensate a Host-settings saga with the exact prior model and capacity."""
        if snapshot is None:
            return self.apply(mode)
        with runtime_lifecycle():
            manager = get_model_manager()
            if manager is None:
                raise GenerationCapacityError("the supervised engine is no longer available")

            def restore_profile() -> None:
                manager.restore_runtime(snapshot)
                profile = self.plan_config(mode, snapshot[0], current_cfg=snapshot[0])
                self._last_profile = profile
                refresh_engine_dependencies(profile)

            try:
                get_generation_manager().run_when_idle(restore_profile)
            except ModelSwitchError as exc:
                raise GenerationCapacityError(str(exc)) from exc
        return self.status(mode)

    def apply(self, mode: str) -> dict:
        with runtime_lifecycle():
            return self._apply_locked(mode)

    def _apply_locked(self, mode: str) -> dict:
        manager = get_model_manager()
        applied: dict[str, CapacityProfile] = {}

        def replace_profile() -> None:
            # Image selection stores guarded bytes only. There is no auxiliary inference
            # process to drain; active chat generations are the sole replacement barrier.
            current_cfg = active_runtime_config()
            profile = self.plan_config(mode, current_cfg, current_cfg=current_cfg)
            target_model_id: str | None = None
            if mode == "competition" and not profile.fits and manager is not None:
                configured = os.environ.get("MUTA_SHARE_COMPETITION_MODEL_ID", "").strip()
                candidates = [configured] if configured else []
                candidates.extend(
                    model_id
                    for model_id in manager.local_model_ids_by_size()
                    if model_id not in candidates
                )
                for model_id in candidates:
                    try:
                        candidate = manager.candidate_config(model_id)
                    except ModelSwitchError:
                        continue
                    candidate_profile = self.plan_config(
                        mode, candidate, current_cfg=current_cfg
                    )
                    if candidate_profile.fits:
                        target_model_id = model_id
                        profile = candidate_profile
                        break
            if not profile.fits:
                raise GenerationCapacityError(
                    "Muta cannot fit one competition-safe chat in the RAM currently available; "
                    "close other applications or choose a smaller installed model"
                )
            applied["profile"] = profile
            cfg = active_runtime_config()
            if manager is None:
                if profile.n_parallel != cfg.n_parallel or profile.n_ctx != cfg.n_ctx:
                    raise GenerationCapacityError(
                        "this engine is externally managed; restart Muta with the requested "
                        "capacity"
                    )
                refresh_engine_dependencies(profile)
                return
            if target_model_id is not None:
                manager.switch(
                    target_model_id,
                    n_parallel=profile.n_parallel,
                    n_ctx=profile.n_ctx,
                    persist_selection=False,
                )
                refresh_engine_dependencies(profile)
                return
            if manager.cfg.n_parallel == profile.n_parallel and manager.cfg.n_ctx == profile.n_ctx:
                refresh_engine_dependencies(profile)
                return
            manager.reconfigure_capacity(
                n_parallel=profile.n_parallel,
                n_ctx=profile.n_ctx,
            )
            refresh_engine_dependencies(profile)

        try:
            get_generation_manager().run_when_idle(replace_profile)
        except ModelSwitchError as exc:
            raise GenerationCapacityError(str(exc)) from exc
        profile = applied["profile"]
        self._last_profile = profile
        return self.status(mode)


def wait_for_engine_ready(timeout_s: float | None = None) -> None:
    """Bound a transient supervisor/model-replacement gap before admitting a learner turn."""
    manager = get_model_manager()
    if manager is None or not hasattr(manager, "wait_until_ready"):
        return
    timeout = (
        float(os.environ.get("MUTA_ENGINE_ADMISSION_WAIT_S", "20"))
        if timeout_s is None
        else timeout_s
    )
    if not manager.wait_until_ready(max(0.0, timeout)):
        raise GenerationCapacityError(
            "the local tutor is still recovering — wait a moment and send again"
        )


@lru_cache(maxsize=1)
def get_capacity_controller() -> RuntimeCapacityController:
    return RuntimeCapacityController()


@lru_cache(maxsize=8)
def load_prompt(mode: str) -> str:
    """Read a persona/system prompt for the mode, stripping the authoring comment header."""
    path = _PROMPTS_DIR / f"{mode}.md"
    if not path.exists():
        path = _PROMPTS_DIR / "socratic.md"
    prompt = _COMMENT.sub("", path.read_text()).strip()
    return prompt


@lru_cache(maxsize=1)
def get_engine() -> ChatEngine:
    cfg = active_runtime_config()
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
    return ChatEngine(
        client,
        store,
        max_history_messages=cfg.max_history_messages,
        history_token_budget=cfg.history_token_budget,
        # --kv-unified lets an idle slot borrow the shared window, but two concurrent jobs
        # still draw from one total KV budget. Fit each admitted lane to its guaranteed share
        # so individually-valid prompts cannot overcommit the engine when both are active.
        context_window_tokens=cfg.n_ctx // max(1, cfg.n_parallel),
        context_safety_tokens=cfg.context_safety_tokens,
        image_token_budget=cfg.image_max_tokens,
        stream_retry_attempts=cfg.stream_retry_attempts,
        stream_retry_backoff_s=cfg.stream_retry_backoff_s,
    )


@lru_cache(maxsize=1)
def get_resource_service() -> ResourceService:
    """One bounded worker/search service over the engine's durable private resource store."""
    return ResourceService(get_engine().store)


@lru_cache(maxsize=1)
def get_generation_manager() -> GenerationManager:
    """Live replay buffers outlive browser requests but not the gateway process."""
    cfg = active_runtime_config()
    try:
        from orchestrator.gateway.sharing import get_sharing_service

        mode = get_sharing_service().settings()["memory_mode"]
    except Exception:
        mode = "competition"
    per_student = 1 if mode == "competition" else min(2, max(1, cfg.n_parallel - 1))
    return GenerationManager(
        max_active=cfg.n_parallel,
        max_active_per_student=per_student,
    )


@lru_cache(maxsize=1)
def get_ladder() -> DegradationLadder:
    """The memory ladder (§5.3). `core_rss_probe` is wired to the engine process: without it
    L4 — core server approaching its own cgroup cap — can never fire, and that is the one
    level that catches the dangerous case."""
    return DegradationLadder(core_rss_probe=core_rss_bytes)


@lru_cache(maxsize=1)
def get_power_governor() -> PowerGovernor:
    """Host battery policy. Construction reads nothing; the first status/request samples it."""
    cfg = RuntimeConfig()
    return PowerGovernor(
        globally_enabled=cfg.power_optimization,
        poll_interval_s=cfg.power_poll_interval_s,
        sensor_grace_s=cfg.power_sensor_grace_s,
        critical_percentage=cfg.power_critical_percentage,
        critical_time_s=cfg.power_critical_time_s,
        hysteresis_percentage=cfg.power_hysteresis_percentage,
        hysteresis_time_s=cfg.power_hysteresis_time_s,
        eco_reasoning_budget=cfg.power_eco_reasoning_budget,
        eco_max_tokens=cfg.power_eco_max_tokens,
        critical_max_tokens=cfg.power_critical_max_tokens,
    )


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
        except Exception:
            continue
    return total


@lru_cache(maxsize=1)
def get_slot_client() -> SlotClient:
    # The slot API lives on the SAME llama-server the gateway supervises. RuntimeConfig is the
    # one authority for its address — this used to point at a dead TUTOR_CORE_PORT (8081) while
    # the engine actually listens on RuntimeConfig.server_port (8080), so /v1/metrics.engine and
    # session suspend/resume always hit nothing (audit: config-split).
    cfg = active_runtime_config()
    key_file = BundlePaths.from_env().api_key_file
    api_key = key_file.read_text().strip() if key_file.is_file() else None
    return SlotClient(base_url=cfg.base_url, api_key=api_key)


@lru_cache(maxsize=1)
def get_reaper() -> SnapshotReaper:
    return SnapshotReaper(BundlePaths.from_env().slot_dir)


@lru_cache(maxsize=1)
def get_sessions() -> SessionManager:
    """Admission control (§8.2), wired to real suspend/resume and to the ladder.

    Slot count comes from RuntimeConfig.n_parallel — the SAME number the engine is launched
    with — so admission admits exactly as many concurrent sessions as the engine has slots.
    It previously sized from the classroom profile (6) against a 2-slot engine, so a third
    student queued invisibly inside llama-server instead of getting the designed message."""
    n_parallel = active_runtime_config().n_parallel
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
        slots_count=n_parallel,
        suspend_hook=suspend,
        resume_hook=resume,
        effective_slots=lambda: ladder.evaluate().effective_slots(n_parallel),
        accepts_new_sessions=lambda: ladder.evaluate().accepts_new_sessions,
    )
    return manager


@lru_cache(maxsize=1)
def get_vision() -> VisionManager:
    return VisionManager(
        admit=lambda: get_ladder().may_spawn_vision() and get_power_governor().vision_allowed()
    )


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
    target = data_root() / "twins"
    try:
        return TwinStore(target)
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "muta-twins"
        log.warning(
            "twin dir %s not writable — using ephemeral %s (set TUTOR_ROOT)", target, fallback
        )
        return TwinStore(fallback)


@lru_cache(maxsize=1)
def get_renderer() -> DiagramRenderer:
    return DiagramRenderer(get_tool_pools().renderer)


@lru_cache(maxsize=1)
def get_preamble_writer() -> PreambleWriter | None:
    """The TTFT preamble model, or None when it is switched off or not provisioned.

    Loaded once (≈55 ms, 15 MB) on first use rather than at import: a deployment that never
    turns the preamble on must not pay for it, and a missing model is a disabled feature,
    not a failed boot."""
    cfg = RuntimeConfig()
    if not cfg.ttft_preamble:
        return None
    root = resource_root()
    directory = cfg.ttft_model_dir
    if not directory.is_absolute():
        directory = root / directory
    writer = PreambleWriter.load(directory)
    if writer is None:
        log.warning(
            "MUTA_RT_TTFT_PREAMBLE=1 but no model at %s — run scripts/fetch_ttft_model.py",
            directory,
        )
        return None
    writer.warmup()  # the cold first generation must not land on a student (see warmup())
    return writer
