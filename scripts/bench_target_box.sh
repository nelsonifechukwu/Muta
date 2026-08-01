#!/usr/bin/env bash
# Target-box benchmark driver — run the pinned engine inside a container shaped like the
# competition deploy box: Ubuntu 22.04, AVX2-only engine, 8 GiB hard memory cap (swap
# denied), 6 physical cores + SMT siblings when the host can pin them. What a cgroup
# cannot fake (DDR4 bandwidth, clocks) the harness measures and records instead —
# docs/benchmarking-target-box.md is the fidelity contract.
#
#   scripts/bench_target_box.sh                       # fingerprint + bandwidth + llama-bench
#   scripts/bench_target_box.sh --skip-build -- --sweep WINNER
#   scripts/bench_target_box.sh --cores 6 --mem 8g -- --reps 5
#
# Everything after `--` is passed to `python -m bench.target_box` inside the container.
# Results land in bench/.artifacts/target-box/ (the bench/ mount writes them back out).
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

info() { printf '\033[36m▸\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

CORES=6          # physical cores of the target box (i5 10th–12th gen / Ryzen 5 3000–5000)
MEM=8g           # its DDR4 complement; hard cap, swap denied (an over-budget config must fail loudly)
SKIP_BUILD=0
IMAGE=muta-backend:latest
MODULE_ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --cores)      CORES=$2; shift ;;
        --mem)        MEM=$2; shift ;;
        --skip-build) SKIP_BUILD=1 ;;
        --image)      IMAGE=$2; shift ;;
        --)           shift; MODULE_ARGS=("$@"); break ;;
        -h|--help)    sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)            die "unknown option: $1  (try --help; module args go after --)" ;;
    esac
    shift
done

command -v docker >/dev/null 2>&1 || die "docker not found"
docker info >/dev/null 2>&1 || die "docker daemon isn't running"

if [ "$SKIP_BUILD" = 0 ]; then
    info "building the backend image (cached; carries the pinned AVX2-only engine)"
    docker compose build backend || die "backend image build failed"
fi

MODEL=models/core/Qwen3.5-4B-Q4_K_M.gguf
if [ ! -e "$MODEL" ]; then
    warn "$MODEL absent — fingerprint + bandwidth still run; llama-bench/sweeps will be skipped."
    warn "fetch it with: docker compose run --rm --no-deps backend python3.10 scripts/fetch_models.py --only core"
    case " ${MODULE_ARGS[*]-} " in *" --sweep "*)
        die "--sweep needs the model present" ;;
    esac
fi

# ---------------------------------------------------------------------------
# CPU shape. Topology is read INSIDE a container (on Docker Desktop the VM's CPUs are
# the ones that matter, not the host's). Preference order:
#   1. cpuset of $CORES physical cores + their SMT siblings — real core boundaries,
#      like the target box has;
#   2. a cfs quota of the same logical count when the runtime can't do cpusets —
#      throttling, not pinning; the report records which one it got.
# ---------------------------------------------------------------------------
topo=$(docker run --rm --platform linux/amd64 "$IMAGE" sh -c \
    'for c in /sys/devices/system/cpu/cpu[0-9]*; do
         printf "%s %s:%s\n" "${c##*/cpu}" \
             "$(cat "$c/topology/physical_package_id" 2>/dev/null || echo 0)" \
             "$(cat "$c/topology/core_id" 2>/dev/null || echo "${c##*/cpu}")"
     done') || die "topology probe failed"

CPUSET="" ; PHYS=0 ; LOGICAL=0
declare -A picked=()
while read -r cpu key; do
    [ -n "${picked[$key]:-}" ] || { [ "$PHYS" -ge "$CORES" ] && continue; picked[$key]=1; PHYS=$((PHYS+1)); }
    CPUSET="${CPUSET:+$CPUSET,}$cpu"
    LOGICAL=$((LOGICAL+1))
done <<<"$topo"
[ "$PHYS" -ge "$CORES" ] || warn "host grants only $PHYS physical cores (target: $CORES) — numbers are a LOWER bound"

CPU_ARGS=(--cpuset-cpus "$CPUSET")
probe=$(docker run --rm "${CPU_ARGS[@]}" --platform linux/amd64 "$IMAGE" true 2>&1) || probe="error: $probe"
if [ -n "$probe" ]; then
    warn "cpuset unavailable here (${probe%%$'\n'*}) — falling back to a cfs quota of $LOGICAL CPUs"
    CPU_ARGS=(--cpus "$LOGICAL")
fi

info "cpu: $PHYS cores / $LOGICAL threads (${CPU_ARGS[*]}); mem: $MEM hard, no swap"
info "llama-bench threads: $PHYS (decode-shaped) and $LOGICAL (all)"

docker run --rm --platform linux/amd64 \
    "${CPU_ARGS[@]}" --memory "$MEM" --memory-swap "$MEM" \
    -v "$PWD/models:/app/models:ro" \
    -v "$PWD/bench:/app/bench" \
    -e PYTHONUNBUFFERED=1 \
    "$IMAGE" \
    python3.10 -m bench.target_box --threads "$PHYS,$LOGICAL" "${MODULE_ARGS[@]}"
