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
# Kept bash-3.2-clean (no declare -A / mapfile): macOS system bash is a supported host.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

info() { printf '\033[36m▸\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

CORES=6          # physical cores of the target box (i5 10th–12th gen / Ryzen 5 3000–5000)
MEM=8g           # its DDR4 complement; hard cap, swap denied (an over-budget config must fail loudly)
SKIP_BUILD=0
IMAGE=""         # --image overrides; otherwise resolved from compose after the build step
MODULE_ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --cores)      CORES=${2:?--cores needs a value}; shift ;;
        --mem)        MEM=${2:?--mem needs a value}; shift ;;
        --skip-build) SKIP_BUILD=1 ;;
        --image)      IMAGE=${2:?--image needs a value}; shift ;;
        --)           shift; MODULE_ARGS=("$@"); break ;;
        -h|--help)    sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
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
if [ -z "$IMAGE" ]; then
    # The compose-derived image name depends on the checkout directory / project name —
    # assuming muta-backend would silently benchmark a stale image from another checkout.
    # `config --images backend` also lists depends_on images (db), in no fixed order —
    # select the backend-derived name, not line 1.
    IMAGE=$(docker compose config --images backend 2>/dev/null | grep -m1 -- '-backend' || true)
    [ -n "$IMAGE" ] || IMAGE=muta-backend:latest
fi
docker image inspect "$IMAGE" >/dev/null 2>&1 || die "image $IMAGE not found — run without --skip-build"

MODEL=models/core/Qwen3.5-4B-Q4_K_M.gguf
if [ ! -e "$MODEL" ]; then
    warn "$MODEL absent — fingerprint + bandwidth still run; llama-bench/sweeps will be skipped."
    warn "fetch it with: docker compose run --rm --no-deps backend python3.10 scripts/fetch_models.py --only core"
    case " ${MODULE_ARGS[*]-} " in *" --sweep "*|*" --sweep="*)
        die "--sweep needs the model present" ;;
    esac
fi

# ---------------------------------------------------------------------------
# CPU shape. Topology is read INSIDE a container (on Docker Desktop the VM's CPUs are
# the ones that matter, not the host's); offline CPUs (nosmt) are skipped, and the list
# is sorted numerically — glob order is lexicographic (cpu0,cpu1,cpu10,…), which on big
# hosts would silently pick a cross-socket set. Preference order:
#   1. cpuset of $CORES physical cores + their SMT siblings, all on ONE package — real
#      core boundaries on one socket, like the target box;
#   2. a cfs quota of the same logical count when the runtime can't do cpusets —
#      throttling, not pinning; the report records which one it got.
# ---------------------------------------------------------------------------
topo=$(docker run --rm --platform linux/amd64 "$IMAGE" sh -c \
    'for c in /sys/devices/system/cpu/cpu[0-9]*; do
         n=${c##*/cpu}
         if [ -e "$c/online" ] && [ "$(cat "$c/online")" = "0" ]; then continue; fi
         printf "%s %s %s\n" "$n" \
             "$(cat "$c/topology/physical_package_id" 2>/dev/null || echo 0)" \
             "$(cat "$c/topology/core_id" 2>/dev/null || echo "$n")"
     done | sort -n') || die "topology probe failed"

CPUSET="" ; PHYS=0 ; LOGICAL=0 ; SEEN="," ; PKG=""
while read -r cpu pkg core; do
    key="$pkg:$core"
    case "$SEEN" in
        *",$key,"*) ;;                        # SMT sibling of an already-picked core
        *)
            [ "$PHYS" -ge "$CORES" ] && continue
            [ -n "$PKG" ] || PKG=$pkg
            [ "$pkg" = "$PKG" ] || continue   # stay on one socket, like the target box
            SEEN="$SEEN$key," ; PHYS=$((PHYS+1)) ;;
    esac
    CPUSET="${CPUSET:+$CPUSET,}$cpu"
    LOGICAL=$((LOGICAL+1))
done <<<"$topo"
[ "$PHYS" -ge "$CORES" ] || warn "only $PHYS physical cores granted (target: $CORES; single socket preferred) — numbers are a LOWER bound"

# Trust what the container actually sees, not the daemon's exit status: a kernel that
# can't do cpusets still exits 0 and just warns, so compare the resulting CPU count.
CPU_ARGS=(--cpuset-cpus "$CPUSET")
got=$(docker run --rm "${CPU_ARGS[@]}" --platform linux/amd64 "$IMAGE" nproc 2>/dev/null || echo 0)
if [ "$got" != "$LOGICAL" ]; then
    warn "cpuset not honored here (container sees $got CPUs, wanted $LOGICAL) — falling back to a cfs quota of $LOGICAL CPUs"
    CPU_ARGS=(--cpus "$LOGICAL")
fi

info "cpu: $PHYS cores / $LOGICAL threads (${CPU_ARGS[*]}); mem: $MEM hard, no swap"
info "llama-bench threads: $PHYS (decode-shaped) and $LOGICAL (all)"

# --user: artifacts land on the bench/ mount; written as root they would break every
# later host-side bench run (native_sweep appends, this harness mkdirs).
docker run --rm --platform linux/amd64 \
    "${CPU_ARGS[@]}" --memory "$MEM" --memory-swap "$MEM" \
    --user "$(id -u):$(id -g)" \
    -v "$PWD/models:/app/models:ro" \
    -v "$PWD/bench:/app/bench" \
    -e PYTHONUNBUFFERED=1 \
    "$IMAGE" \
    python3.10 -m bench.target_box --threads "$PHYS,$LOGICAL" ${MODULE_ARGS[@]+"${MODULE_ARGS[@]}"}
