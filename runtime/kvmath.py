"""KV cache arithmetic — the slot budget table, derived from real metadata (TDD T5, §5.2).

    python -m runtime.kvmath models/core/*.gguf                 # the table for this model
    python -m runtime.kvmath models/core/*.gguf --markdown docs/kv-budget.md

`slots × context is the commodity RAM buys`. This module is where that sentence becomes a
number, so the §5.2 table in the TDD stops being a worked example with representative values
and becomes a measurement of the file we actually ship.

Per-token KV bytes = n_layer × n_kv_head × (head_dim_k × B_k + head_dim_v × B_v), where B is
bytes-per-element for the cache quantization. Note it is NOT `2 × …` when K and V have
different head dims — the factor of two in the TDD's formula is exactly the K + V sum.

One number here is deliberately *not* measured: the compute buffer. It is flagged
PROVISIONAL and overridable with `--buffers-mib`, because inventing a measurement is worse
than carrying an honest planning value (TDD §0.2).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from runtime.gguf import GGUFMetadata, read_metadata
from runtime.profiles import PROFILES, ServingProfile

MiB = 1024**2
GiB = 1024**3

#: Bytes per element for each llama.cpp KV cache type. Quantized types are block-based:
#: q8_0 is 34 bytes per 32 elements, q5_1 is 24, q4_0 is 18 — so the "bits" in the name is
#: never the whole story and rounding it to 1.0/0.625 misprices a slot by ~6%.
CACHE_TYPE_BYTES: dict[str, float] = {
    "f32": 4.0,
    "f16": 2.0,
    "bf16": 2.0,
    "q8_0": 34 / 32,
    "q5_1": 24 / 32,
    "q5_0": 22 / 32,
    "q4_1": 20 / 32,
    "q4_0": 18 / 32,
    "iq4_nl": 18 / 32,
}

#: TDD §5.2 quotes ~0.6 GiB of compute buffers at -b 2048 / -ub 512. Scaled linearly with
#: ubatch here, which is the right *shape* (activations are per-physical-batch) but an
#: unmeasured constant. [MEASURE: RSS delta across a -ub sweep on the target box, T13.]
COMPUTE_BUFFER_MIB_AT_UB512 = 600
COMPUTE_BUFFER_PROVISIONAL = True

#: CORE-TEXT's cgroup cap (TDD §5.1). The table's whole purpose is "does this row fit".
CORE_TEXT_CAP_MIB = 4300


def cache_type_bytes(name: str) -> float:
    try:
        return CACHE_TYPE_BYTES[name.lower()]
    except KeyError:
        raise KeyError(
            f"unknown KV cache type {name!r}; known: {sorted(CACHE_TYPE_BYTES)}. "
            "(tq3_0 appears in the D6 ladder but is not a mainline KV type — verify at pin.)"
        ) from None


@dataclass(frozen=True)
class KVCost:
    """Per-token KV cost of one model at one cache quantization. `n_layer` counts only the
    layers whose KV grows with tokens (= all layers on classic transformers,
    `block_count // full_attention_interval` on hybrids)."""

    n_layer: int
    n_kv_head: int
    head_dim_k: int
    head_dim_v: int
    cache_type_k: str
    cache_type_v: str

    @classmethod
    def from_metadata(cls, md: GGUFMetadata, cache_type: str = "q8_0", cache_type_v: str | None = None):
        if not (md.n_layer and md.n_kv_head and md.head_dim_k):
            raise ValueError(
                f"{md.path.name}: metadata is missing block_count/head_count_kv/key_length "
                "— cannot derive the KV budget, and guessing it would put the OOM risk on "
                "the target box (TDD §0.2)"
            )
        return cls(
            n_layer=md.n_attn_layer,
            n_kv_head=md.n_kv_head,
            head_dim_k=md.head_dim_k,
            head_dim_v=md.head_dim_v,
            cache_type_k=cache_type,
            cache_type_v=cache_type_v or cache_type,
        )

    @property
    def elements_per_token(self) -> int:
        """K and V elements per token, summed over layers."""
        return self.n_layer * self.n_kv_head * (self.head_dim_k + self.head_dim_v)

    @property
    def bytes_per_token(self) -> float:
        bk = cache_type_bytes(self.cache_type_k)
        bv = cache_type_bytes(self.cache_type_v)
        return self.n_layer * self.n_kv_head * (self.head_dim_k * bk + self.head_dim_v * bv)

    @property
    def kib_per_token(self) -> float:
        return self.bytes_per_token / 1024

    def mib_for(self, n_tokens: int) -> float:
        return self.bytes_per_token * n_tokens / MiB


@dataclass(frozen=True)
class RecurrentStateCost:
    """Constant-size f32 state of a hybrid model's recurrent (SSM / gated-delta-net)
    layers. Charged PER SLOT — and per context checkpoint, which is why
    `--ctx-checkpoints` is a RAM knob (runtime/config.py). Formula validated against the
    engine's own 'restored context checkpoint ... 50.251 MiB' log line for Qwen3.5-4B."""

    n_layers: int  # recurrent layers = block_count - n_attn_layer
    conv_kernel: int
    d_inner: int
    d_state: int
    n_groups: int

    @classmethod
    def from_metadata(cls, md: GGUFMetadata) -> "RecurrentStateCost | None":
        if not md.is_hybrid:
            return None
        return cls(
            n_layers=md.n_layer - md.n_attn_layer,
            conv_kernel=md.ssm_conv_kernel,
            d_inner=md.ssm_inner_size,
            d_state=md.ssm_state_size,
            n_groups=md.ssm_group_count,
        )

    @property
    def bytes_per_slot(self) -> int:
        conv = (self.conv_kernel - 1) * (self.d_inner + 2 * self.n_groups * self.d_state)
        delta = self.d_state * self.d_inner
        return self.n_layers * (conv + delta) * 4  # f32

    @property
    def mib_per_slot(self) -> float:
        return self.bytes_per_slot / MiB


@dataclass(frozen=True)
class SlotBudget:
    """One row of the §5.2 table: does this profile fit under CORE-TEXT's cap?"""

    profile: ServingProfile
    weights_mib: float
    kv_mib: float
    buffers_mib: float
    state_mib: float = 0.0
    cap_mib: int = CORE_TEXT_CAP_MIB

    @property
    def total_mib(self) -> float:
        return self.weights_mib + self.kv_mib + self.buffers_mib + self.state_mib

    @property
    def fits(self) -> bool:
        return self.total_mib <= self.cap_mib

    @property
    def headroom_mib(self) -> float:
        return self.cap_mib - self.total_mib


def compute_buffer_mib(profile: ServingProfile) -> float:
    return COMPUTE_BUFFER_MIB_AT_UB512 * (profile.ubatch / 512)


def budget(
    cost: KVCost,
    profile: ServingProfile,
    *,
    weights_mib: float,
    buffers_mib: float | None = None,
    cap_mib: int = CORE_TEXT_CAP_MIB,
    state_bytes_per_slot: int = 0,
) -> SlotBudget:
    return SlotBudget(
        profile=profile,
        weights_mib=weights_mib,
        kv_mib=cost.mib_for(profile.n_ctx),
        buffers_mib=compute_buffer_mib(profile) if buffers_mib is None else buffers_mib,
        state_mib=state_bytes_per_slot * profile.n_parallel / MiB,
        cap_mib=cap_mib,
    )


def budget_table(
    md: GGUFMetadata,
    *,
    cache_type: str = "q8_0",
    profiles: dict[str, ServingProfile] | None = None,
    buffers_mib: float | None = None,
    cap_mib: int = CORE_TEXT_CAP_MIB,
) -> tuple[KVCost, list[SlotBudget]]:
    cost = KVCost.from_metadata(md, cache_type)
    weights_mib = md.file_bytes / MiB
    state = RecurrentStateCost.from_metadata(md)
    rows = [
        budget(
            cost,
            p,
            weights_mib=weights_mib,
            buffers_mib=buffers_mib,
            cap_mib=cap_mib,
            state_bytes_per_slot=state.bytes_per_slot if state else 0,
        )
        for p in (profiles or PROFILES).values()
    ]
    return cost, rows


def _round_half_up(value: float, ndigits: int = 1) -> float:
    """`f"{x:.1f}"` alone is round-half-to-even. That is not a fixture-only curiosity: the
    shipped Qwen3.5-4B's own ssm.* dims (128, 4096, 4, 16) make `RecurrentStateCost`'s
    formula land on exactly 50.25 MiB per slot — an exact tie that plain `.1f` renders as
    "50.2", the wrong side of the engine's measured 50.251 MiB checkpoint log. Round half up
    instead, as a human reading a RAM budget expects."""
    factor = 10**ndigits
    return int(value * factor + 0.5) / factor


def render_markdown(md: GGUFMetadata, cost: KVCost, rows: list[SlotBudget]) -> str:
    ladder = "\n".join(
        f"| {name} | {KVCost.from_metadata(md, name).kib_per_token:.1f} KiB | "
        f"{KVCost.from_metadata(md, name).mib_for(4096):.0f} MiB |"
        for name in ("f16", "q8_0", "q5_1")
    )
    table = "\n".join(
        f"| {r.profile.name} | {r.profile.n_ctx} | {r.profile.n_parallel} | "
        f"{r.profile.ctx_per_slot} | {r.kv_mib:.0f} MiB | {r.state_mib:.0f} MiB | "
        f"{r.weights_mib:.0f} MiB | {r.buffers_mib:.0f} MiB | {r.total_mib:.0f} MiB | "
        f"{'yes' if r.fits else f'**NO** (over by {-r.headroom_mib:.0f} MiB)'} |"
        for r in rows
    )
    provisional = (
        "\n> Compute-buffer column is PROVISIONAL "
        f"({COMPUTE_BUFFER_MIB_AT_UB512} MiB at `-ub 512`, scaled linearly). "
        "[MEASURE: RSS delta across the `-ub` sweep on the target box, T13] — "
        "re-run with `--buffers-mib` once measured.\n"
        if COMPUTE_BUFFER_PROVISIONAL
        else ""
    )
    state = RecurrentStateCost.from_metadata(md)
    hybrid_note = (
        f"\nHybrid layout: **{md.n_attn_layer} attention** layers (token-growing KV) + "
        f"**{md.n_layer - md.n_attn_layer} recurrent** layers at a constant "
        f"**{_round_half_up(state.mib_per_slot):.1f} MiB f32 per slot** (and per context checkpoint). "
        "Slot totals below charge the state ONCE per slot; each context checkpoint copies it "
        "again — worst case per slot = state × (1 + ctx_checkpoints), engine default 32, "
        "capped to 2 via `MUTA_RT_CTX_CHECKPOINTS` on the gateway path (`runtime/profiles.py` "
        "launch paths pass no cap).\n"
        if state
        else ""
    )
    return f"""# KV budget — {md.path.name}

Generated by `python -m runtime.kvmath {md.path}` (TDD T5, §5.2). Do not hand-edit: this
table is derived from the shipped file's own metadata, which is the entire point — the TDD's
version used representative Qwen-family values, and representative is not measured.

Model: arch `{md.architecture}`, {md.n_layer} layers, {md.n_kv_head} KV heads,
head_dim {md.head_dim_k}{'' if md.head_dim_v == md.head_dim_k else f'/{md.head_dim_v}'},
trained context {md.trained_context}, file {md.file_bytes / GiB:.2f} GiB.

Per-token KV = n_layer × n_kv_head × (head_dim_k × B_k + head_dim_v × B_v)
= {cost.n_layer} × {md.n_kv_head} × ({md.head_dim_k} + {md.head_dim_v}) elements
= **{cost.elements_per_token:,} elements/token**.
{hybrid_note}
## KV quantization ladder (D6)

| cache type | per token | 4096-token slot |
|---|---|---|
{ladder}

## Slot budget vs the CORE-TEXT cap ({rows[0].cap_mib} MiB)

| profile | `-c` | `-np` | ctx/slot | KV | state | weights | buffers | total | fits? |
|---|---|---|---|---|---|---|---|---|---|
{table}
{provisional}
"""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("model", help="path to the GGUF whose budget to compute")
    p.add_argument("--cache-type", default="q8_0", help="KV quantization (D6 default: q8_0)")
    p.add_argument("--buffers-mib", type=float, default=None, help="measured compute-buffer size")
    p.add_argument("--cap-mib", type=int, default=CORE_TEXT_CAP_MIB, help="CORE-TEXT cgroup cap")
    p.add_argument("--markdown", default=None, help="write the table to this path")
    args = p.parse_args(argv)

    md = read_metadata(args.model)
    try:
        cost, rows = budget_table(
            md, cache_type=args.cache_type, buffers_mib=args.buffers_mib, cap_mib=args.cap_mib
        )
    except (ValueError, KeyError) as e:
        print(str(e), file=sys.stderr)
        return 1

    doc = render_markdown(md, cost, rows)
    if args.markdown:
        Path(args.markdown).write_text(doc)
        print(f"wrote {args.markdown}")
    else:
        print(doc)

    if not any(r.fits for r in rows):
        print("no profile fits the cap — pick a smaller -c or a cheaper KV type", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
