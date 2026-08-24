"""RAM-aware serving-profile planning for Host mode.

This plans complete llama.cpp profiles rather than treating every chat as an invented linear
256 MiB slope.  It reuses the shipped GGUF metadata arithmetic for token-growing KV and hybrid
recurrent state, preserves a useful per-chat context, observes cgroup limits, and caps the result
by physical CPU cores because RAM-rich but bandwidth-bound laptops do not gain from 32 decoders.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import psutil

from runtime.config import RuntimeConfig
from runtime.gguf import GGUFError, read_metadata
from runtime.kvmath import KVCost, RecurrentStateCost, compute_buffer_mib
from runtime.paths import resource_root
from runtime.profiles import ServingProfile, physical_cores

MiB = 1024**2
GiB = 1024**3
_CGROUP_V2 = Path("/sys/fs/cgroup/memory.max")
_CGROUP_V1 = Path("/sys/fs/cgroup/memory/memory.limit_in_bytes")


def _read_limit(path: Path) -> int | None:
    try:
        raw = path.read_text().strip()
        if raw == "max":
            return None
        value = int(raw)
        # cgroup v1 often exposes a huge sentinel for "unlimited".
        return value if 0 < value < (1 << 60) else None
    except (OSError, ValueError):
        return None


def effective_memory_bytes(
    *,
    physical_probe: Callable[[], int] | None = None,
    cgroup_probe: Callable[[], int | None] | None = None,
) -> tuple[int, int, int | None]:
    physical = int((physical_probe or (lambda: psutil.virtual_memory().total))())
    if cgroup_probe is None:
        cgroup = _read_limit(_CGROUP_V2) or _read_limit(_CGROUP_V1)
    else:
        cgroup = cgroup_probe()
    effective = min(physical, cgroup) if cgroup else physical
    return effective, physical, cgroup


def process_tree_rss_bytes() -> int:
    """Current RSS for the gateway and every child it owns.

    A GGUF's file size is not its resident cost: llama.cpp may also keep anonymous repacked
    weights.  Sampling the live tree gives the planner a floor derived from the actual build
    and machine rather than relying only on file arithmetic.
    """
    try:
        process = psutil.Process()
        return int(
            process.memory_info().rss
            + sum(child.memory_info().rss for child in process.children(recursive=True))
        )
    except (psutil.Error, OSError):
        return 0


@dataclass(frozen=True)
class CapacityProfile:
    memory_mode: Literal["competition", "system"]
    n_parallel: int
    n_ctx: int
    context_per_chat: int
    effective_ram_bytes: int
    available_ram_bytes: int
    physical_ram_bytes: int
    cgroup_limit_bytes: int | None
    memory_ceiling_bytes: int
    estimated_peak_bytes: int
    weights_bytes: int
    kv_bytes: int
    recurrent_state_bytes: int
    prompt_cache_bytes: int
    compute_buffer_bytes: int
    gateway_reserve_bytes: int
    auxiliary_reserve_bytes: int
    repack_reserve_bytes: int
    measured_resident_bytes: int
    resident_base_bytes: int
    cpu_slot_cap: int
    fits: bool
    calculation: str

    def as_dict(self) -> dict:
        return asdict(self)


class CapacityPlanner:
    def __init__(
        self,
        *,
        memory_probe: Callable[[], tuple[int, int, int | None]] = effective_memory_bytes,
        available_probe: Callable[[], int] = lambda: int(psutil.virtual_memory().available),
        core_probe: Callable[[], int] = physical_cores,
        resident_probe: Callable[[], int] = process_tree_rss_bytes,
    ) -> None:
        self.memory_probe = memory_probe
        self.available_probe = available_probe
        self.core_probe = core_probe
        self.resident_probe = resident_probe

    def plan(
        self,
        mode: str,
        cfg: RuntimeConfig,
        *,
        root: Path | None = None,
        current_cfg: RuntimeConfig | None = None,
    ) -> CapacityProfile:
        if mode not in {"competition", "system"}:
            raise ValueError("memory mode must be competition or system")
        effective, physical, cgroup = self.memory_probe()
        available = max(0, int(self.available_probe()))
        root = (root or resource_root()).resolve()
        model_path = cfg.model_path
        if not model_path.is_absolute():
            model_path = root / model_path

        # Preserve the current guaranteed per-lane context. An image-capable candidate also
        # needs the projector ceiling plus 2048 tokens for the system/question/reply envelope;
        # product mode grows total -c with --parallel accordingly.
        media_context = cfg.image_max_tokens + 2048 if cfg.mmproj_path is not None else 1024
        min_context = max(
            int(os.environ.get("MUTA_SHARE_MIN_CONTEXT", str(media_context))),
            media_context,
            cfg.n_ctx // max(1, cfg.n_parallel),
        )
        product_bound = max(1, min(32, int(os.environ.get("MUTA_SHARE_MAX_CHATS", "32"))))
        cpu_cap = max(1, min(product_bound, self.core_probe()))
        if mode == "competition":
            # `run.sh` already gives Docker a 15% host reserve. Keep one safety boundary,
            # rather than shrinking 8 GiB to 85% and then applying another 82% here.
            ceiling = min(
                int(6.6 * GiB),
                effective if cgroup and cgroup < physical else int(effective * 0.82),
            )
            candidate_slots = min(2, max(1, cfg.n_parallel))
        else:
            # `run.sh` already places the backend in an 85%-of-host cgroup. Do not apply the
            # same reserve a second time: a real cgroup is the single product-mode ceiling.
            # Native mode has no such boundary, so it retains the 15% OS reserve here.
            ceiling = effective if cgroup and cgroup < physical else int(effective * 0.85)
            candidate_slots = cpu_cap

        model_weights = model_path.stat().st_size if model_path.is_file() else 0
        projector_path = cfg.mmproj_path
        if projector_path is not None and not projector_path.is_absolute():
            projector_path = root / projector_path
        projector_weights = (
            projector_path.stat().st_size
            if projector_path is not None and projector_path.is_file()
            else 0
        )
        gateway_reserve = int(os.environ.get("MUTA_SHARE_GATEWAY_RESERVE_MIB", "768")) * MiB
        # Image input is served by this selected llama-server. Price its exact paired projector
        # as resident weights; there is no second CORE-VISION process to reserve 1.1–4.3 GiB
        # for, and doing so made otherwise-safe model replacements fail their capacity gate.
        auxiliary_reserve = 0
        prompt_cache = cfg.cache_ram_mib * MiB
        kv_per_token = 0.0
        recurrent_per_slot = 0
        metadata_note = "fallback estimate (model metadata unavailable)"
        if model_path.is_file():
            try:
                md = read_metadata(model_path)
                # server.py sets K explicitly and leaves V at llama.cpp's f16 default.
                kv_per_token = KVCost.from_metadata(md, cfg.cache_type_k, "f16").bytes_per_token
                recurrent = RecurrentStateCost.from_metadata(md)
                recurrent_per_slot = recurrent.bytes_per_slot if recurrent else 0
                metadata_note = f"GGUF metadata from {model_path.name}"
            except (OSError, ValueError, KeyError, GGUFError):
                pass
        if not model_weights:
            model_weights = int(os.environ.get("MUTA_SHARE_FALLBACK_WEIGHTS_MIB", "3072")) * MiB
        weights = model_weights + projector_weights
        if not kv_per_token:
            kv_per_token = float(os.environ.get("MUTA_SHARE_FALLBACK_KV_BYTES_PER_TOKEN", "65536"))
        if not recurrent_per_slot:
            recurrent_per_slot = (
                int(os.environ.get("MUTA_SHARE_FALLBACK_STATE_MIB_PER_SLOT", "64")) * MiB
            )

        repack_reserve = 0
        if not cfg.no_repack:
            ratio = float(os.environ.get("MUTA_SHARE_REPACK_RATIO", "0.55"))
            minimum = int(os.environ.get("MUTA_SHARE_REPACK_MIN_MIB", "384")) * MiB
            repack_reserve = max(minimum, int(model_weights * max(0.0, ratio)))

        measured_resident = max(0, int(self.resident_probe()))
        # Installed RAM is not free RAM. Do not expand Muta toward a static 85% ceiling
        # while another application is already using the missing half of the machine.
        # Current Muta RSS remains usable during a restart; MemAvailable is the additional
        # headroom. Preserve a final reserve for short-lived OS/application allocations.
        available_reserve = int(os.environ.get("MUTA_SHARE_AVAILABLE_RESERVE_MIB", "512")) * MiB
        usable_now = measured_resident + max(0, available - available_reserve)
        ceiling = min(ceiling, usable_now)

        checkpoints_multiplier = 1 + max(0, cfg.ctx_checkpoints)

        def variable_price(slots: int) -> tuple[int, int, int, int, int]:
            n_ctx = min_context * slots
            kv = int(kv_per_token * n_ctx)
            state = recurrent_per_slot * slots * checkpoints_multiplier
            buffer = int(
                compute_buffer_mib(
                    ServingProfile(
                        name="muta-share-buffer",
                        n_ctx=n_ctx,
                        n_parallel=slots,
                        batch=cfg.n_batch,
                        ubatch=cfg.n_ubatch,
                    )
                )
                * MiB
            )
            variable = kv + state + prompt_cache + buffer
            return n_ctx, kv, state, buffer, variable

        current_variable = variable_price(max(1, cfg.n_parallel))[4]
        measured_base = max(0, measured_resident - current_variable)
        if current_cfg is not None and current_cfg.model_path.resolve() != model_path.resolve():
            current_model = current_cfg.model_path
            if not current_model.is_absolute():
                current_model = root / current_model
            current_model_weights = current_model.stat().st_size if current_model.is_file() else 0
            if not current_model_weights:
                current_model_weights = (
                    int(os.environ.get("MUTA_SHARE_FALLBACK_WEIGHTS_MIB", "3072")) * MiB
                )
            current_projector = current_cfg.mmproj_path
            if current_projector is not None and not current_projector.is_absolute():
                current_projector = root / current_projector
            current_projector_weights = (
                current_projector.stat().st_size
                if current_projector is not None and current_projector.is_file()
                else 0
            )
            current_weights = current_model_weights + current_projector_weights
            current_repack = 0
            if not current_cfg.no_repack:
                ratio = float(os.environ.get("MUTA_SHARE_REPACK_RATIO", "0.55"))
                minimum = int(os.environ.get("MUTA_SHARE_REPACK_MIN_MIB", "384")) * MiB
                current_repack = max(minimum, int(current_model_weights * max(0.0, ratio)))
            # Replace the old model's priced resident contribution with the candidate's.
            # Any unexplained live RSS remains in the floor instead of disappearing.
            measured_base = max(
                0,
                measured_base - current_weights - current_repack + weights + repack_reserve,
            )
        resident_base = (
            max(weights + repack_reserve + gateway_reserve, measured_base) + auxiliary_reserve
        )

        def price(slots: int) -> tuple[int, int, int, int, int]:
            n_ctx, kv, state, buffer, variable = variable_price(slots)
            return n_ctx, kv, state, buffer, resident_base + variable

        slots = candidate_slots
        if mode == "system":
            while slots > 1 and price(slots)[4] > ceiling:
                slots -= 1
        else:
            # Competition mode must fail closed on unusually large models/configurations.
            while slots > 1 and price(slots)[4] > ceiling:
                slots -= 1
        n_ctx, kv, state, buffer, estimated = price(slots)
        calculation = (
            f"{metadata_note}; {slots} lanes × {min_context} context; "
            f"ceiling {ceiling / GiB:.2f} GiB of effective {effective / GiB:.2f} GiB; "
            f"resident base {resident_base / GiB:.2f} GiB "
            f"(measured tree {measured_resident / GiB:.2f} GiB, "
            f"repack reserve {repack_reserve / GiB:.2f} GiB); CPU cap {cpu_cap}"
        )
        return CapacityProfile(
            memory_mode=mode,
            n_parallel=slots,
            n_ctx=n_ctx,
            context_per_chat=min_context,
            effective_ram_bytes=effective,
            available_ram_bytes=available,
            physical_ram_bytes=physical,
            cgroup_limit_bytes=cgroup,
            memory_ceiling_bytes=ceiling,
            estimated_peak_bytes=estimated,
            weights_bytes=weights,
            kv_bytes=kv,
            recurrent_state_bytes=state,
            prompt_cache_bytes=prompt_cache,
            compute_buffer_bytes=buffer,
            gateway_reserve_bytes=gateway_reserve,
            auxiliary_reserve_bytes=auxiliary_reserve,
            repack_reserve_bytes=repack_reserve,
            measured_resident_bytes=measured_resident,
            resident_base_bytes=resident_base,
            cpu_slot_cap=cpu_cap,
            fits=estimated <= ceiling,
            calculation=calculation,
        )
