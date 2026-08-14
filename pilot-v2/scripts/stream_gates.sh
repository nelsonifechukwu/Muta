#!/usr/bin/env bash
# scripts/stream_gates.sh — S5.1 gate orchestration (G8–G12) for the weight-streaming
# pilot. All runs in-container (stream_env.sh cgrun), serialized, drop_caches before
# every cap-relevant measurement. Results land under bench/.runs/stream/ as one log
# per run plus gates.tsv (peak/exit/oom per run) for the results.md §5 table.
#
#   scripts/stream_gates.sh g8|g9|g10|g11|g12|all
#
# Configs of record:
#   RECORD  (G8/G9/G11/G12): --ctx-expert 4096 --tier-ctx easy=4096 -ub 128, draftless
#   AMORT   (G10):           --ctx-expert 2048 --tier-ctx easy=2048 --ctx-front 2048
#                            -ub 32 --draft-tier easy   (the config the ledger accepts
#                            with the draft resident; see WORKLOG S4.1)
# Both carry --no-repack: the accuracy-reference kernel set, and the C5 fix for the
# SmolLM2 front (default tau=0 routing is only meaningful on these kernels).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
ENV=scripts/stream_env.sh
OUT=bench/.runs/stream
mkdir -p "$OUT"
TSV="$OUT/gates.tsv"
D="${D:-2.977}"

BASE="--bundle /models/muta-trio.gguf --no-repack -t 6"
STREAM="--stream-weights --max-ram-mib 2048 --disk-gbps $D"
RECORD="--ctx-expert 4096 --tier-ctx easy=4096 -ub 128"
AMORT="--ctx-expert 2048 --tier-ctx easy=2048 --ctx-front 2048 -ub 32 --draft-tier easy"

P_EASY="What is the capital of Nigeria?"
P_HARD="Solve 3x + 5 = 20 and explain each step."
P_ESC="Explain Newton's second law with an example."

tsv_init() {
    if [[ ! -f "$TSV" ]]; then
        printf "gate\trun\tcap\tpeak_mib\texit\toomkilled\tnote\n" > "$TSV"
    fi
}

# run GATE NAME CAP EXTRA_NOTE -- duo-args...
run() {
    local gate="$1" name="$2" cap="$3" note="$4"; shift 4
    [[ "$1" == "--" ]] && shift
    local log="$OUT/$gate-$name.log"
    echo "== [$gate] $name (cap=$cap)"
    bash "$ENV" drop_caches >/dev/null 2>&1 || true
    set +e
    bash "$ENV" cgrun "$cap" /build/bin/llama-duo $BASE "$@" > "$log" 2>&1
    local st=$?
    set -e
    local peak oom
    peak=$(grep -A1 -- "--- memory.peak ---" "$log" | tail -1)
    oom=$(sed -n 's/.*OOMKilled=\([a-z]*\).*/\1/p' "$log" | tail -1)
    local peak_mib="n/a"
    [[ "$peak" =~ ^[0-9]+$ ]] && peak_mib=$(awk "BEGIN{printf \"%.1f\", $peak/1048576}")
    printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$gate" "$name" "$cap" "$peak_mib" "$st" "$oom" "$note" >> "$TSV"
    echo "   peak=${peak_mib} MiB exit=$st oom=$oom"
}

g8() {
    tsv_init
    for cap in 3g 2048m; do
        run g8 "router-easy-$cap"  "$cap" "" -- $STREAM $RECORD -n 96  -p "$P_EASY"
        run g8 "router-hard-$cap"  "$cap" "" -- $STREAM $RECORD -n 96  -p "$P_HARD"
        run g8 "conf-esc-$cap"     "$cap" "route-threshold 99 + carry" -- $STREAM $RECORD --route-threshold 99 --carry-draft -n 96 -p "$P_ESC"
        run g8 "codraft-$cap"      "$cap" "codraft easy,mid" -- $STREAM $RECORD --mode codraft --codraft-tiers easy,mid -n 96 -p "$P_ESC"
        run g8 "perf-multiturn-$cap" "$cap" "6-turn perf.txt (plan said 10; file has 6)" -- $STREAM $RECORD -n 64 --prompts-file /work/bench/prompts/perf.txt
    done
}

g9() {
    tsv_init
    # forced hard (tau=-99 routes everything hard), draftless, -n 64: the [seg]
    # author=expert ms/tokens against the ledger's predicted s/token
    run g9 "latency-model" 2048m "forced-hard; compare seg ms/token vs ledger predicted" -- \
        $STREAM $RECORD --route-threshold -99 -n 64 -p "$P_HARD"
    grep -E "predicted|residency:|\[seg" "$OUT/g9-latency-model.log" | tail -6 || true
}

g10() {
    tsv_init
    # K curve on the amortizer config; K=none is the same config minus --draft-tier
    # (duo clamps verify-draft elsewhere; a draftless run IS the K=0 row)
    run g10 "k-none" 2048m "amortizer config, draftless baseline" -- \
        $STREAM --ctx-expert 2048 --tier-ctx easy=2048 --ctx-front 2048 -ub 32 \
        --route-threshold -99 -n 128 -p "$P_HARD"
    for k in 4 8 16; do
        bash "$ENV" drop_caches >/dev/null 2>&1 || true
        echo "== [g10] k=$k perf.txt sweep"
        python3 scripts/spec_accept.py \
            --template "bash $ENV cgrun 2048m bash -c '/build/bin/llama-duo $BASE $STREAM $AMORT --draft-k {k} --route-threshold -99 -n 128 --json-trace /tmp/j.json -p \"\$0\"; s=\$?; echo JSONTRACE-BEGIN; cat /tmp/j.json; exit \$s' {prompt}" \
            --k "$k" --prompts bench/prompts/perf.txt \
            --out "$OUT/acceptance.tsv" --label "g10-streamed-2048m" \
            2>&1 | tee "$OUT/g10-k$k.log" | tail -3
    done
}

g11() {
    tsv_init
    # cold-start TTFT: drop caches, then measure exec -> first answer byte from
    # OUTSIDE the process (python wrapper inside the enforced container). duo's own
    # [ttft] line gives the in-process breakdown for the same run.
    bash "$ENV" drop_caches >/dev/null 2>&1 || true
    local log="$OUT/g11-ttft-cold.log"
    set +e
    bash "$ENV" cgrun 2048m python3 -c "
import subprocess, sys, time
cmd = ['/build/bin/llama-duo'] + '''$BASE $STREAM $RECORD --stream -n 32'''.split() + ['-p', 'Explain the water cycle briefly.']
t0 = time.time()
p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
b = p.stdout.read(1)
print('EXTERNAL_TTFB_MS %.1f' % ((time.time() - t0) * 1e3), flush=True)
p.stdout.read(); p.wait()
" > "$log" 2>&1
    set -e
    grep -E "EXTERNAL_TTFB_MS" "$log" || echo "g11: no TTFB line; see $log"
    # in-process breakdown run (trace on stderr), same cold protocol
    bash "$ENV" drop_caches >/dev/null 2>&1 || true
    run g11 "ttft-trace" 2048m "in-process [ttft] breakdown" -- $STREAM $RECORD --stream -n 32 -p "Explain the water cycle briefly."
    grep -E "\[ttft\]" "$OUT/g11-ttft-trace.log" || true
}

g12() {
    tsv_init
    run g12 "managed"   2048m "with --stream-weights" -- $STREAM $RECORD --route-threshold -99 -n 32 -p "$P_HARD"
    run g12 "unmanaged" 2048m "same config, NO --stream-weights" -- $RECORD --route-threshold -99 -n 32 -p "$P_HARD"
}

case "${1:-all}" in
    g8) g8 ;;
    g9) g9 ;;
    g10) g10 ;;
    g11) g11 ;;
    g12) g12 ;;
    all) g8; g9; g10; g11; g12 ;;
    *) echo "usage: $0 g8|g9|g10|g11|g12|all" >&2; exit 1 ;;
esac
echo "gates done; table: $TSV"
