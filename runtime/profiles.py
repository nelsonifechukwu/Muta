"""Serving profiles — the exact llama-server invocations (TDD §6.2, §6.3, §6.4, §6.7, §7.6).

    python -m runtime.profiles print core --profile classroom
    python -m runtime.profiles exec  core            # what the systemd unit runs
    python -m runtime.profiles table                 # the thread allocation for this box

Every flag in §6.2 is here with its reason attached, because the flags *are* the memory
budget: `-c` divided by `--parallel` is the commodity RAM buys (§5.2), and a value picked
casually costs slots that the classroom demo needs. Nothing else in the codebase may
hardcode a context size, a slot count or a thread count — if it is a knob, it is here.

Profiles are data, not code paths: `PROFILE=solo-demo` in `etc/profile.env` switches the
whole system (TDD §10.5).
"""

from __future__ import annotations

import argparse
import os
import shlex
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

from runtime.paths import data_root, model_root, resource_root

# ---------------------------------------------------------------------------------------
# Profiles (§5.2 slot budget table)
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ServingProfile:
    """One row of the §5.2 slot budget table plus the serving knobs it implies."""

    name: str
    n_ctx: int  # TOTAL context budget, divided across slots
    n_parallel: int  # slots
    cache_type: str = "q8_0"  # D6 default; the f16→q8_0→q5_1 ladder is bench week
    batch: int = 2048
    ubatch: int = 512  # sweep {128,256,512} on target (T13); lower shrinks compute buffers
    cache_reuse: int = 256  # chunk-level KV reuse — what makes the §7.3 prompt layout cheap
    cache_ram_mib: int = 512  # warmed prefixes beyond live slots; inside CORE-TEXT's cap
    defrag_thold: float = 0.10
    context_shift: bool = True  # upstream default is now OFF; tutoring dialogs must not stop
    mlock: bool = False  # D9: off in classroom (reclaim pathologies under a strict cap)
    tts_engine: str = "piper"  # D5: Kokoro is solo-demo only, and only if RSS allows
    vision_enabled: bool = True

    @property
    def ctx_per_slot(self) -> int:
        return self.n_ctx // self.n_parallel

    def kv_bytes(self, per_token_bytes: float) -> int:
        """Total KV bytes at this profile, given the model's per-token cost (§5.2)."""
        return int(per_token_bytes * self.n_ctx)


#: TDD §5.2. `classroom` is the default row — 30 phones share 6 slots via suspend/resume
#: (§8.3), so slots × context is sized for the *working set*, not the roster.
PROFILES: dict[str, ServingProfile] = {
    "classroom": ServingProfile(name="classroom", n_ctx=12288, n_parallel=6),  # Classroom-6-short
    "classroom-6": ServingProfile(name="classroom-6", n_ctx=24576, n_parallel=6),
    "classroom-8": ServingProfile(name="classroom-8", n_ctx=32768, n_parallel=8),
    "solo-demo": ServingProfile(
        name="solo-demo",
        n_ctx=8192,
        n_parallel=2,
        mlock=True,  # D9: safe here — no classroom-scale cgroup pressure
        tts_engine="kokoro",
    ),
}
DEFAULT_PROFILE = "classroom"

#: Full separately-weighted CORE-VISION process reserve. The 1,100 MiB marginal estimate is
#: valid only when the resident text server maps the exact same 4B GGUF. Native/model-switcher
#: deployments serve smaller text models while vision retains its paired 4B weights + mmproj.
#: The shipped files (2,614 + 641 MiB), q8 KV/recurrent state (~236 MiB), and provisional
#: -ub 256 compute buffer (~300 MiB) total ~3,791 MiB before allocator/engine overhead. Keep
#: MemoryHigh above that analytical floor and MemoryMax another 10% above MemoryHigh.
VISION_FULL_RSS_RESERVE_MIB = 4352


def vision_full_rss_reserve_mib() -> int:
    """Return the enforced full-process vision ceiling.

    Keep the previous Host-planner override as a compatibility fallback, but make the runtime
    variable authoritative so admission planning and the transient cgroup share one value.
    Invalid/non-positive overrides fail safe to the measured default.
    """
    raw = os.environ.get(
        "MUTA_RT_VISION_MEMORY_MAX_MIB",
        os.environ.get("MUTA_SHARE_VISION_RSS_RESERVE_MIB", str(VISION_FULL_RSS_RESERVE_MIB)),
    )
    try:
        value = int(raw)
    except ValueError:
        return VISION_FULL_RSS_RESERVE_MIB
    return value if value > 0 else VISION_FULL_RSS_RESERVE_MIB


def get_profile(name: str | None = None) -> ServingProfile:
    key = (name or os.environ.get("PROFILE") or DEFAULT_PROFILE).strip()
    if key not in PROFILES:
        raise KeyError(f"unknown profile {key!r}; known: {sorted(PROFILES)}")
    profile = PROFILES[key]
    # Open gates are env-switchable so a decision can be flipped on the target box without a
    # rebuild (TDD §14): D6 KV type, D9 mlock, D5 TTS engine.
    overrides: dict[str, object] = {}
    if kv := os.environ.get("TUTOR_KV_TYPE"):
        overrides["cache_type"] = kv
    if (mlock := os.environ.get("TUTOR_MLOCK")) is not None and mlock != "":
        overrides["mlock"] = mlock not in ("0", "false", "no")
    if tts := os.environ.get("TUTOR_TTS_ENGINE"):
        overrides["tts_engine"] = tts
    return replace(profile, **overrides) if overrides else profile


# ---------------------------------------------------------------------------------------
# Threads (§6.4)
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ThreadPlan:
    cores: int
    core_threads: int  # decode: bandwidth-bound, more threads than cores HURTS
    core_threads_batch: int  # prefill: compute-bound, may exceed decode threads
    vision_threads: int
    audio_threads: int = 1
    http_threads: int = 2
    from_table: bool = True


#: The published table (physical cores → assignment). Never count SMT siblings: bandwidth-
#: bound decode gains nothing from a hyperthread and loses cache to it.
_THREAD_TABLE: dict[int, tuple[int, int, int, int]] = {
    4: (3, 4, 2, 1),
    6: (4, 6, 3, 1),
    8: (6, 8, 4, 2),
}


def physical_cores() -> int:
    try:
        import psutil

        return psutil.cpu_count(logical=False) or os.cpu_count() or 4
    except Exception:  # noqa: BLE001 — psutil is a dev dependency; never fail on counting
        return os.cpu_count() or 4


def thread_plan(cores: int | None = None) -> ThreadPlan:
    """Assignment for this box. Off-table core counts are extrapolated conservatively and
    flagged, so a 12-core dev laptop never silently becomes the number in the report."""
    cores = cores or physical_cores()
    if cores in _THREAD_TABLE:
        t, tb, tv, ta = _THREAD_TABLE[cores]
        return ThreadPlan(cores, t, tb, tv, ta)
    if cores < 4:
        t, tb, tv, ta = _THREAD_TABLE[4]
        return ThreadPlan(cores, min(t, max(1, cores - 1)), min(tb, cores), 1, 1, from_table=False)
    # Between/above table rows: leave 2 cores for gateway+audio, prefill may use them all.
    return ThreadPlan(cores, max(2, cores - 2), cores, max(2, cores // 2), 2, from_table=False)


def _env_threads(plan: ThreadPlan) -> ThreadPlan:
    """`TUTOR_*_THREADS=0` means 'derive from the table' (etc/profile.env)."""

    def pick(name: str, fallback: int) -> int:
        raw = os.environ.get(name, "0").strip() or "0"
        value = int(raw)
        return value if value > 0 else fallback

    return replace(
        plan,
        core_threads=pick("TUTOR_CORE_THREADS", plan.core_threads),
        core_threads_batch=pick("TUTOR_CORE_THREADS_BATCH", plan.core_threads_batch),
        vision_threads=pick("TUTOR_VISION_THREADS", plan.vision_threads),
    )


# ---------------------------------------------------------------------------------------
# Bundle paths (§10.1)
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class BundlePaths:
    root: Path
    mutable_root: Path | None = None
    model_storage: Path | None = None

    @classmethod
    def from_env(cls) -> BundlePaths:
        return cls(resource_root(), data_root(), model_root())

    @property
    def data(self) -> Path:
        # Direct construction is used throughout the existing tests and older tools. Preserve
        # their `<root>/data` layout while packaged launches pass the explicit mutable root.
        return self.mutable_root or self.root / "data"

    @property
    def models(self) -> Path:
        return (self.model_storage or self.root) / "models"

    @property
    def core_model(self) -> Path:
        return _one_gguf(self.models / "core", exclude="mmproj")

    @property
    def mmproj(self) -> Path:
        return _one_gguf(self.models / "core", include="mmproj")

    @property
    def draft_model(self) -> Path:
        return _one_gguf(self.models / "draft")

    @property
    def embed_model(self) -> Path:
        return _one_gguf(self.models / "embed")

    @property
    def adapters(self) -> list[Path]:
        d = self.models / "adapters"
        return sorted(d.glob("*.gguf")) if d.is_dir() else []

    @property
    def slot_dir(self) -> Path:
        return self.data / "kv-slots"

    @property
    def log_dir(self) -> Path:
        return self.data / "logs"

    @property
    def api_key_file(self) -> Path:
        return self.data / "api.key"

    def engine_bin(self) -> str:
        explicit = os.environ.get("TUTOR_LLAMA_SERVER_BIN")
        if explicit:
            return explicit
        candidate = self.root / "bin" / "llama-server-core"
        if candidate.exists():
            return str(candidate)
        # Dev fallback: the same search runtime/server.py uses (build dir, then PATH).
        from runtime.config import RuntimeConfig
        from runtime.server import find_binary  # local import: avoids an import cycle

        return find_binary(RuntimeConfig())


def _one_gguf(directory: Path, *, include: str | None = None, exclude: str | None = None) -> Path:
    """Resolve exactly one GGUF in a bundle directory.

    Deliberately not a hardcoded filename: the core file's name changes with the D1 bake-off
    winner, and a stale constant would silently serve last week's quant.
    """
    if not directory.is_dir():
        raise FileNotFoundError(f"{directory} does not exist — bundle not staged?")
    files = [f for f in sorted(directory.glob("*.gguf")) if f.is_file()]
    if include:
        files = [f for f in files if include in f.name]
    if exclude:
        files = [f for f in files if exclude not in f.name]
    if not files:
        raise FileNotFoundError(f"no matching GGUF in {directory}")
    if len(files) > 1:
        raise RuntimeError(
            f"{directory} holds {len(files)} candidate GGUFs: {[f.name for f in files]}"
        )
    return files[0]


def port(name: str, default: int) -> int:
    return int(os.environ.get(f"TUTOR_{name}_PORT", default))


# ---------------------------------------------------------------------------------------
# Invocations
# ---------------------------------------------------------------------------------------


@dataclass
class Invocation:
    argv: list[str]
    describe: str = ""
    notes: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return " ".join(shlex.quote(a) for a in self.argv)


def core_text_command(
    paths: BundlePaths | None = None,
    profile: ServingProfile | None = None,
    plan: ThreadPlan | None = None,
    *,
    model: Path | None = None,
) -> Invocation:
    """CORE-TEXT, the resident reasoner (TDD §6.2)."""
    paths = paths or BundlePaths.from_env()
    profile = profile or get_profile()
    plan = _env_threads(plan or thread_plan())
    model = model or paths.core_model
    notes: list[str] = []

    argv = [
        paths.engine_bin(),
        "-m",
        str(model),
        "--alias",
        "core",
        "--host",
        "127.0.0.1",  # loopback only; the gateway is the sole LAN surface (§13)
        "--port",
        str(port("CORE", 8081)),
        # The primary RAM knob: total context divided across slots (§5.2). --parallel is set
        # explicitly because auto-sizing fights the cgroup cap.
        "-c",
        str(profile.n_ctx),
        "--parallel",
        str(profile.n_parallel),
        "--kv-unified",  # one shared KV buffer: a long solo session can borrow idle budget
        "--cont-batching",
        # Halves KV vs f16 at no measurable quality cost for this model size (D6).
        "--cache-type-k",
        profile.cache_type,
        "--cache-type-v",
        profile.cache_type,
        # Forced on, not auto: stable bench numbers, O(N)→ attention working set, and a
        # prerequisite for quantized V cache.
        "--flash-attn",
        "on",
        "-b",
        str(profile.batch),
        "-ub",
        str(profile.ubatch),
        "--threads",
        str(plan.core_threads),
        "--threads-batch",
        str(plan.core_threads_batch),
        "--threads-http",
        str(plan.http_threads),
        "--cache-reuse",
        str(profile.cache_reuse),
        "--cache-ram",
        str(profile.cache_ram_mib),
        "--slot-save-path",
        str(paths.slot_dir),  # the suspend/resume mechanism (§8.3)
        # KV fragmentation defrag trigger. Unified KV + churny classroom slots make
        # fragmentation real, not theoretical; 0.10 is the conservative end.
        "--defrag-thold",
        f"{profile.defrag_thold:.2f}",
    ]
    if profile.context_shift:
        argv.append("--context-shift")
    if profile.mlock:
        argv.append("--mlock")
        notes.append("mlock ON (D9) — only valid after staging to local disk (C-4)")

    adapters = paths.adapters
    if adapters:
        # Loaded but inactive; activation is per-request, so a plain turn pays nothing (§7.4).
        argv.append("--lora-init-without-apply")
        for a in adapters:
            argv += ["--lora", str(a)]
    else:
        notes.append("no LoRA adapters found — persona/marking modes fall back to prompts")

    argv += [
        "--jinja",  # the model's own chat template, tool tokens included — never hand-rolled
        "--metrics",
        "--slots",
        "--props",
        "--no-webui",
        "--seed",
        "-1",  # per-request override to 4242 for anything scored (§6.5)
    ]

    key = paths.api_key_file
    if key.is_file():
        argv += ["--api-key", key.read_text().strip()]
    else:
        notes.append(f"no API key at {key} — engine is unauthenticated (install.sh mints one)")

    if os.environ.get("TUTOR_SPECULATION", "c") == "b":
        argv += _speculation_flags(paths, plan, notes)

    log = paths.log_dir / "core.jsonl"
    argv += ["--log-file", str(log)]
    if _numa_nodes() > 1:
        argv += ["--numa", "distribute"]
        notes.append("multi-node NUMA detected — added --numa distribute (§6.2)")
    return Invocation(
        argv,
        describe=f"CORE-TEXT [{profile.name}] {profile.n_parallel}×{profile.ctx_per_slot}",
        notes=notes,
    )


def _speculation_flags(paths: BundlePaths, plan: ThreadPlan, notes: list[str]) -> list[str]:
    """D2-b: draft-model speculation. Admitted only if it clears 1.43 tok/s per GiB spent —
    that is a measurement, not a preference, so this path stays off until the bench says so."""
    try:
        draft = paths.draft_model
    except (FileNotFoundError, RuntimeError) as e:
        notes.append(f"TUTOR_SPECULATION=b but no draft model ({e}) — falling back to D2-c (none)")
        return []
    notes.append("D2-b active: re-run the -ub sweep, speculation multiplies verify-batch work")
    # NOTE: inert at pin b10035 — speculation requires --spec-type (docs/engine-flags.md);
    # flags kept for the main-branch launch path.
    return [
        "--spec-draft-model",
        str(draft),
        "--spec-draft-n-max",
        "8",
        "--spec-draft-n-min",
        "1",
        "--spec-draft-p-min",
        "0.75",
        "--threads-draft",
        str(max(1, plan.core_threads // 2)),
    ]


def core_vision_command(
    paths: BundlePaths | None = None,
    profile: ServingProfile | None = None,
    plan: ThreadPlan | None = None,
) -> Invocation:
    """CORE-VISION, spawned on demand and TTL-killed (TDD §6.3).

    Same binary, same weight file — the OS page cache shares the read-only weight pages, so
    the marginal cost is mmproj + this instance's KV and buffers, not a second 2.5 GiB copy.
    That sharing argument holds ONLY for mmap'd pages: the engine's default weight repack
    copies Q4-family tensors into PRIVATE anonymous buffers (+~2.5 GiB per instance —
    x86 AVX2 repack is a prefill-only win, tg128 −2%, PR #12332), so a repacked vision
    spike on top of the repacked chat server busts the 8 GB box's 7 GB ceiling.
    `--no-repack` keeps this instance's weights on the shared page cache.

    Deliberately WITHOUT `--cache-reuse`, `--slot-save-path` and `--context-shift`: loading
    an mmproj sets the multimodal capability flag on every slot, which disables all three
    (upstream #21133). Requesting them anyway would assert at startup.
    """
    paths = paths or BundlePaths.from_env()
    profile = profile or get_profile()
    plan = _env_threads(plan or thread_plan())
    argv = [
        paths.engine_bin(),
        "-m",
        str(paths.core_model),
        "--mmproj",
        str(paths.mmproj),
        "--alias",
        "core-vision",
        "--host",
        "127.0.0.1",
        "--port",
        str(port("VISION", 8082)),
        "-c",
        "8192",
        "--parallel",
        "2",
        "--cache-type-k",
        profile.cache_type,
        "--cache-type-v",
        profile.cache_type,
        "--flash-attn",
        "on",
        "-b",
        "1024",
        "-ub",
        "256",
        # The engine warns at load that Qwen-VL needs ≥ 1024 image tokens to read accurately
        # (upstream #16842); without the floor a 1280 px photo encodes to ~58 tokens and the
        # "transcription" is confident garbage. Costs prefill time, buys correctness.
        "--image-min-tokens",
        "1024",
        # Explicit because -ngl defaults to *auto* at this pin: a Metal host would otherwise
        # offload silently. run.sh native GPU mode sets the env to "all".
        "--n-gpu-layers",
        os.environ.get("MUTA_RT_N_GPU_LAYERS", "0"),
        "--threads",
        str(plan.vision_threads),
        "--threads-http",
        "1",
        "--no-repack",
        "--jinja",
        "--metrics",
        "--slots",
        "--props",
        "--no-webui",
        "--log-file",
        str(paths.log_dir / "vision.jsonl"),
    ]
    key = paths.api_key_file
    if key.is_file():
        argv += ["--api-key", key.read_text().strip()]
    return Invocation(argv, describe="CORE-VISION (ephemeral, TTL 120s)")


def embed_command(paths: BundlePaths | None = None) -> Invocation:
    """EMBED — bge-small on its own server (TDD §6.7).

    `--pooling cls` is not optional: the BGE family is trained with CLS pooling and
    mean-pooling degrades retrieval *silently* — no error, just worse top-k.
    """
    paths = paths or BundlePaths.from_env()
    argv = [
        paths.engine_bin(),
        "-m",
        str(paths.embed_model),
        "--embeddings",
        "--pooling",
        "cls",
        "--alias",
        "embed",
        "--host",
        "127.0.0.1",
        "--port",
        str(port("EMBED", 8083)),
        "-c",
        "512",
        "-np",
        "2",
        "--threads",
        "1",
        "--no-webui",
        "--log-file",
        str(paths.log_dir / "embed.jsonl"),
    ]
    key = paths.api_key_file
    if key.is_file():
        argv += ["--api-key", key.read_text().strip()]
    return Invocation(argv, describe="EMBED (bge-small, cls pooling)")


def draft_command(paths: BundlePaths | None = None) -> Invocation:
    """Hint-mode server (TDD §7.6) — only exists when D2-b put a draft model in RAM anyway.
    Serving instant Socratic nudges from it is what makes its ΔRAM admissible."""
    paths = paths or BundlePaths.from_env()
    argv = [
        paths.engine_bin(),
        "-m",
        str(paths.draft_model),
        "--alias",
        "hint",
        "--host",
        "127.0.0.1",
        "--port",
        str(port("DRAFT", 8086)),
        "-c",
        "2048",
        "-np",
        "2",
        "--flash-attn",
        "on",
        "--jinja",
        "--no-webui",
    ]
    return Invocation(argv, describe="HINT (draft model, D2-b only)")


def _numa_nodes() -> int:
    nodes = Path("/sys/devices/system/node")
    if not nodes.is_dir():
        return 1
    return max(1, len(list(nodes.glob("node[0-9]*"))))


COMMANDS = {
    "core": core_text_command,
    "vision": core_vision_command,
    "embed": embed_command,
    "draft": draft_command,
}


# ---------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("print", "exec"):
        s = sub.add_parser(name, help=f"{name} a service invocation")
        s.add_argument("service", choices=sorted(COMMANDS))
        s.add_argument("--profile", default=None)
    sub.add_parser("table", help="show the profile + thread allocation for this box")
    args = p.parse_args(argv)

    if args.cmd == "table":
        plan = _env_threads(thread_plan())
        profile = get_profile()
        print(f"profile           {profile.name}")
        print(
            f"  -c / --parallel {profile.n_ctx} / {profile.n_parallel}  ({profile.ctx_per_slot} ctx per slot)"
        )
        print(
            f"  KV cache type   {profile.cache_type}   mlock={profile.mlock}  tts={profile.tts_engine}"
        )
        print(
            f"physical cores    {plan.cores}"
            + ("" if plan.from_table else "   (off-table: extrapolated, see §6.4)")
        )
        print(f"  core threads    {plan.core_threads} decode / {plan.core_threads_batch} prefill")
        print(
            f"  vision / audio  {plan.vision_threads} / {plan.audio_threads}   http {plan.http_threads}"
        )
        return 0

    build = COMMANDS[args.service]
    kwargs = {"profile": get_profile(args.profile)} if args.service in ("core", "vision") else {}
    try:
        inv = build(**kwargs)
    except (FileNotFoundError, RuntimeError, KeyError) as e:
        print(f"cannot build {args.service} invocation: {e}", file=sys.stderr)
        return 1

    for note in inv.notes:
        print(f"note: {note}", file=sys.stderr)
    if args.cmd == "print":
        print(str(inv))
        return 0

    paths = BundlePaths.from_env()
    for d in (paths.log_dir, paths.slot_dir):
        d.mkdir(parents=True, exist_ok=True)
    os.execv(inv.argv[0], inv.argv)  # replace this process: systemd supervises the engine itself
    return 0  # unreachable


if __name__ == "__main__":
    raise SystemExit(main())
