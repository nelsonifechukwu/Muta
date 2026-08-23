"""The Host-mode planner prices complete profiles against real effective memory."""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

from orchestrator.gateway import deps
from orchestrator.gateway.auxiliary import (
    AuxiliaryQueueFull,
    OwnerWorkManager,
    auxiliary_slot,
)
from orchestrator.gateway.capacity import CapacityPlanner, GiB, MiB
from orchestrator.gateway.deps import RuntimeCapacityController
from orchestrator.gateway.ladder import DegradationLadder, Level
from runtime.config import RuntimeConfig
from runtime.profiles import VISION_FULL_RSS_RESERVE_MIB


def _plan(total_gib: int, mode: str):
    planner = CapacityPlanner(
        memory_probe=lambda: (total_gib * GiB, total_gib * GiB, None),
        available_probe=lambda: total_gib * GiB,
        core_probe=lambda: 12,
        resident_probe=lambda: 0,
    )
    cfg = RuntimeConfig(
        model_dir="missing-model-dir",
        model_file="missing.gguf",
        n_ctx=2048,
        n_parallel=2,
        cache_ram_mib=256,
        auto_download=False,
        no_repack=True,
        _env_file=None,
    )
    return planner.plan(mode, cfg)


def test_system_capacity_is_monotonic_and_cpu_bounded():
    small = _plan(8, "system")
    medium = _plan(16, "system")
    large = _plan(32, "system")

    assert 1 <= small.n_parallel <= medium.n_parallel <= large.n_parallel <= 12
    assert small.n_ctx == small.n_parallel * small.context_per_chat
    assert medium.estimated_peak_bytes <= medium.memory_ceiling_bytes
    assert large.estimated_peak_bytes <= large.memory_ceiling_bytes


def test_competition_mode_never_uses_the_product_ram_or_slot_budget():
    profile = _plan(32, "competition")

    assert profile.n_parallel <= 2
    assert profile.memory_ceiling_bytes <= int(6.6 * GiB)
    assert profile.auxiliary_reserve_bytes >= int(3.3 * GiB)
    assert profile.memory_mode == "competition"


def test_cgroup_effective_memory_is_what_the_plan_reports():
    planner = CapacityPlanner(
        memory_probe=lambda: (8 * GiB, 32 * GiB, 8 * GiB),
        available_probe=lambda: 32 * GiB,
        core_probe=lambda: 8,
        resident_probe=lambda: 0,
    )
    cfg = RuntimeConfig(auto_download=False, _env_file=None)

    profile = planner.plan("system", cfg)

    assert profile.physical_ram_bytes == 32 * GiB
    assert profile.cgroup_limit_bytes == 8 * GiB
    assert profile.effective_ram_bytes == 8 * GiB
    assert profile.memory_ceiling_bytes == 8 * GiB


def test_system_capacity_is_bounded_by_currently_available_ram(tmp_path):
    planner = CapacityPlanner(
        memory_probe=lambda: (16 * GiB, 16 * GiB, None),
        available_probe=lambda: 2 * GiB,
        core_probe=lambda: 16,
        resident_probe=lambda: 2 * GiB,
    )
    cfg = RuntimeConfig(
        model_dir=tmp_path,
        model_file="missing.gguf",
        auto_download=False,
        no_repack=True,
        _env_file=None,
    )

    profile = planner.plan("system", cfg)

    assert profile.available_ram_bytes == 2 * GiB
    assert profile.memory_ceiling_bytes == int(3.5 * GiB)
    assert profile.memory_ceiling_bytes < int(16 * GiB * 0.85)


def test_measured_resident_floor_can_reject_a_file_size_only_fit(monkeypatch, tmp_path):
    monkeypatch.setenv("MUTA_SHARE_FALLBACK_WEIGHTS_MIB", "256")
    monkeypatch.setenv("MUTA_SHARE_AUXILIARY_RESERVE_MIB", "0")
    planner = CapacityPlanner(
        memory_probe=lambda: (8 * GiB, 8 * GiB, None),
        core_probe=lambda: 8,
        resident_probe=lambda: int(7.5 * GiB),
    )
    cfg = RuntimeConfig(
        model_dir=tmp_path,
        model_file="missing.gguf",
        n_parallel=2,
        n_ctx=2048,
        cache_ram_mib=64,
        no_repack=True,
        auto_download=False,
        _env_file=None,
    )

    profile = planner.plan("system", cfg)

    assert profile.weights_bytes == 256 * MiB
    assert profile.measured_resident_bytes == int(7.5 * GiB)
    assert profile.resident_base_bytes > profile.weights_bytes
    assert profile.fits is False
    assert "measured tree 7.50 GiB" in profile.calculation


def test_auxiliary_reserve_remains_additive_when_measured_base_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("MUTA_SHARE_FALLBACK_WEIGHTS_MIB", "128")
    monkeypatch.setenv("MUTA_SHARE_AUXILIARY_RESERVE_MIB", "1100")
    planner = CapacityPlanner(
        memory_probe=lambda: (16 * GiB, 16 * GiB, None),
        core_probe=lambda: 4,
        resident_probe=lambda: 8 * GiB,
    )
    cfg = RuntimeConfig(
        model_dir=tmp_path,
        model_file="missing.gguf",
        no_repack=True,
        auto_download=False,
        _env_file=None,
    )

    profile = planner.plan("system", cfg)
    variable = (
        profile.kv_bytes
        + profile.recurrent_state_bytes
        + profile.prompt_cache_bytes
        + profile.compute_buffer_bytes
    )

    assert profile.resident_base_bytes >= (
        profile.measured_resident_bytes - variable + profile.auxiliary_reserve_bytes
    )


def test_system_mode_reserves_full_vision_rss_when_text_uses_different_weights(
    monkeypatch, tmp_path
):
    core_dir = tmp_path / "models" / "core"
    draft_dir = tmp_path / "models" / "draft"
    core_dir.mkdir(parents=True)
    draft_dir.mkdir(parents=True)
    (core_dir / "vision-core.gguf").write_bytes(b"core")
    (core_dir / "mmproj-F16.gguf").write_bytes(b"projector")
    active = draft_dir / "small.gguf"
    active.write_bytes(b"small")
    monkeypatch.setenv("TUTOR_ROOT", str(tmp_path))
    planner = CapacityPlanner(
        memory_probe=lambda: (16 * GiB, 16 * GiB, None),
        available_probe=lambda: 16 * GiB,
        core_probe=lambda: 8,
        resident_probe=lambda: 0,
    )
    cfg = RuntimeConfig(
        model_dir=active.parent,
        model_file=active.name,
        auto_download=False,
        no_repack=True,
        _env_file=None,
    )

    profile = planner.plan("system", cfg)

    assert profile.auxiliary_reserve_bytes == VISION_FULL_RSS_RESERVE_MIB * MiB


def test_core_guard_reserves_gateway_and_auxiliary_before_whole_ceiling():
    profile = _plan(8, "competition")
    core_cap = (
        profile.memory_ceiling_bytes
        - profile.gateway_reserve_bytes
        - profile.auxiliary_reserve_bytes
    )
    # Core alone is below the whole-process ceiling, but one byte over its apportioned cap.
    ladder = DegradationLadder(
        free_probe=lambda: 8 * GiB,
        core_rss_probe=lambda: core_cap + 1,
        core_cap_bytes=core_cap,
        poll_seconds=0,
    )

    assert ladder.evaluate().level is Level.L4


def test_default_8gb_docker_profile_transitions_to_installed_competition_model(
    monkeypatch, tmp_path
):
    """The shipped 4B default must not make the Settings Host toggle unusable."""
    large = tmp_path / "Qwen3.5-4B-IQ4_XS.gguf"
    small = tmp_path / "Qwen3.5-0.8B-Q4_K_M.gguf"
    with large.open("wb") as stream:
        stream.truncate(2_650_000_000)
    with small.open("wb") as stream:
        stream.truncate(532_517_120)
    active = RuntimeConfig(
        model_dir=tmp_path,
        model_file=large.name,
        n_parallel=2,
        n_ctx=2048,
        auto_download=False,
        _env_file=None,
    )

    class Manager:
        cfg = active
        switched: tuple[str, int, int] | None = None

        def candidate_config(self, model_id):
            assert model_id == "qwen3.5-0.8b-q4_k_m"
            return self.cfg.model_copy(update={"model_dir": tmp_path, "model_file": small.name})

        def switch(self, model_id, *, n_parallel, n_ctx):
            self.switched = (model_id, n_parallel, n_ctx)
            self.cfg = self.candidate_config(model_id).model_copy(
                update={"n_parallel": n_parallel, "n_ctx": n_ctx}
            )

    class Generations:
        def run_when_idle(self, operation):
            operation()

        def status(self):
            return {"running": 0, "queued": 0, "reservations": 0}

    manager = Manager()
    generations = Generations()
    planner = CapacityPlanner(
        memory_probe=lambda: (int(6.8 * GiB), 8 * GiB, int(6.8 * GiB)),
        available_probe=lambda: 8 * GiB,
        core_probe=lambda: 4,
        resident_probe=lambda: 0,
    )
    controller = RuntimeCapacityController(planner)
    monkeypatch.setattr(deps, "get_model_manager", lambda: manager)
    monkeypatch.setattr(deps, "active_runtime_config", lambda: manager.cfg)
    monkeypatch.setattr(deps, "get_generation_manager", lambda: generations)
    monkeypatch.setattr(
        deps, "get_vision", lambda: SimpleNamespace(stop_for_reconfigure=lambda: True)
    )
    monkeypatch.setattr(deps, "refresh_engine_dependencies", lambda _profile: None)

    status = controller.apply("competition")

    assert manager.switched is not None
    assert manager.switched[0] == "qwen3.5-0.8b-q4_k_m"
    assert status["fits"] is True
    assert status["active_parallel"] == manager.cfg.n_parallel


def test_auxiliary_queue_waiters_do_not_occupy_the_worker_pool():
    async def exercise():
        slots = threading.BoundedSemaphore(1)
        assert slots.acquire(blocking=False)

        async def wait_for_slot():
            try:
                async with auxiliary_slot(slots, timeout_s=0.02):
                    pass
            except AuxiliaryQueueFull:
                return "busy"
            return "entered"

        waiters = [asyncio.create_task(wait_for_slot()) for _ in range(50)]
        # This heartbeat shares the event loop with the flood. It would miss its deadline if
        # each waiter synchronously occupied an AnyIO worker before admission.
        await asyncio.wait_for(asyncio.sleep(0.001), timeout=0.01)
        results = await asyncio.gather(*waiters)
        slots.release()
        return results

    assert set(asyncio.run(exercise())) == {"busy"}


def test_owner_work_removal_cancels_and_joins_auxiliary_inference():
    manager = OwnerWorkManager()
    started = threading.Event()
    finished = threading.Event()

    def work():
        with manager.track("learner") as cancelled:
            started.set()
            assert cancelled.wait(timeout=1)
        finished.set()

    worker = threading.Thread(target=work)
    worker.start()
    assert started.wait(timeout=1)

    assert manager.stop_owner("learner", timeout=1) is True
    worker.join(timeout=1)

    assert finished.is_set()
