#!/bin/bash
# Audit-kernel proxy matrix: NEON vs forced-generic C vec_dot, repack vs no-repack.
# Every llama-bench invocation goes through with_lock.py (machine-wide exclusive lock).
set +u
OPT=/Users/timii/Developer/Muta/muta-iq/opt
BENCH=$OPT/llama.cpp-generic/build/bin/llama-bench
LOCK="/usr/bin/env python3 $OPT/scripts/with_lock.py"
OUT=$OPT/results/audit_proxy
TQ2=/Users/timii/Developer/Muta/muta-iq/model/bitcpm4-8b-tq2_0.gguf
TQ1=$OPT/models/bitcpm4-8b-tq1_0.gguf
mkdir -p "$OUT"

# run <tag> <envs...> -- <bench args...>
run() {
    local tag=$1; shift
    local envs=()
    while [ "$1" != "--" ]; do envs+=("$1"); shift; done; shift
    echo "=== $tag  env=[${envs[*]:-}]  args=[$*]  $(date +%H:%M:%S)"
    env ${envs[@]+"${envs[@]}"} $LOCK --tag "$tag" -- "$BENCH" "$@" -v -o json > "$OUT/$tag.json" 2> "$OUT/$tag.err"
    echo "    exit $?  $(date +%H:%M:%S)"
    grep -E "model buffer size|muta-audit-proxy" "$OUT/$tag.err" | sed 's/^/    /'
    python3 - "$OUT/$tag.json" <<'PY'
import json,sys
try:
    for r in json.load(open(sys.argv[1])):
        print(f"    {r['test'] if 'test' in r else ''} n_prompt={r['n_prompt']} n_gen={r['n_gen']} t={r['n_threads']} avg_ts={r['avg_ts']:.3f} std_ts={r['stddev_ts']:.3f}")
except Exception as e:
    print("    (json parse failed:", e, ")")
PY
}

COMMON="-p 0 -n 128 -r 3 -t 4 -ngl 0"

# --- TQ2_0 --------------------------------------------------------------
run tq2_neon_repack    -- -m "$TQ2" $COMMON
run tq2_neon_norepack  MUTA_NO_REPACK=1 -- -m "$TQ2" $COMMON
run tq2_gen_repack     MUTA_FORCE_GENERIC=1 -- -m "$TQ2" $COMMON
run tq2_gen_norepack   MUTA_FORCE_GENERIC=1 MUTA_NO_REPACK=1 -- -m "$TQ2" $COMMON
# --- TQ1_0 --------------------------------------------------------------
run tq1_neon_repack    -- -m "$TQ1" $COMMON
run tq1_neon_norepack  MUTA_NO_REPACK=1 -- -m "$TQ1" $COMMON
run tq1_gen_repack     MUTA_FORCE_GENERIC=1 -- -m "$TQ1" $COMMON
run tq1_gen_norepack   MUTA_FORCE_GENERIC=1 MUTA_NO_REPACK=1 -- -m "$TQ1" $COMMON
# --- extras --------------------------------------------------------------
run tq2_gen_norepack_t1  MUTA_FORCE_GENERIC=1 MUTA_NO_REPACK=1 -- -m "$TQ2" -p 0 -n 128 -r 1 -t 1 -ngl 0
run tq2_gen_norepack_pp512 MUTA_FORCE_GENERIC=1 MUTA_NO_REPACK=1 -- -m "$TQ2" -p 512 -n 0 -r 1 -t 4 -ngl 0
echo "=== ALL DONE $(date +%H:%M:%S)"
