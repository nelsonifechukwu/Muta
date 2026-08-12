#!/usr/bin/env bash
# scripts/milestone_a.sh — Milestone A run matrix (pilot/v2, STREAMING_IMPL_PLAN.md
# task MA). The headline question: does Qwen3.5-4B (2.61 GiB Q4_K_M) stream-decode
# under a 2 GiB cgroup cap, and at what tok/s?
#
# Runs, all container / serialized / fresh container per run, reusing
# scripts/stream_env.sh's cgrun+drop_caches:
#   ma1    observed:  cgrun 3g,     --stream-weights --max-ram-mib 2048, standard
#                      prompt, -n 64, memwatch.sh sidecar (1 Hz CSV).
#   ma1b   observed:  same as ma1 but a ~600-token prompt and -n 16 — the first
#                      run to exercise a full 512-token prefill ubatch.
#   ma2    enforced:  cgrun 2048m, same flags as ma1, no sidecar (hard cap IS the
#                      test).
#   ma3    unmanaged: cgrun 2048m, two A/B arms with NO --stream-weights —
#                      kernel-fair (--no-repack -c 4096) and naive-default
#                      (-c 4096 only). Either may OOMKill; that is a legitimate
#                      recorded result, not a bug.
#   all    runs ma1, ma1b, ma2, ma3 in that order.
#   table  (re)renders bench/.artifacts/milestone_a/results_table.md from
#          whichever *.env files already exist — does not run anything.
#
# Idempotent: each arm writes fixed-name log/env files under
# bench/.artifacts/milestone_a/, overwritten on re-run, so any single arm can be
# re-run in isolation without disturbing the others. MA-4 (callback overhead) is
# satisfied by reference to task-B3-report.md / docs/WORKLOG.md — no run here.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STREAM_ENV="${REPO_ROOT}/scripts/stream_env.sh"
IMAGE="${IMAGE:-muta-stream}"
MODELS_VOLUME="${MODELS_VOLUME:-muta-models}"
ARTIFACTS_DIR="${REPO_ROOT}/bench/.artifacts/milestone_a"
mkdir -p "$ARTIFACTS_DIR"

MODEL_NAME="Qwen3.5-4B-Q4_K_M.gguf"
MODEL_IN_CONTAINER="/models/${MODEL_NAME}"
STD_PROMPT="Explain the photoelectric effect in three sentences."
FIXED_ARGS=(-no-cnv --temp 0 --seed 42 -c 4096 -t 6)
DISK_GBPS="2.977"
MAX_RAM_MIB="2048"
CAP_BYTES=$((2048 * 1024 * 1024))

# The ~600-token MA-1b prompt: bench/prompts/hard.txt (20 lines) is not long
# enough on its own (493 tokens, verified below); repeating its first 5 lines
# crosses 600 (623 tokens, verified with llama.cpp/build-noblas/bin/llama-tokenize
# — see docs/WORKLOG.md's MA entry). Both source files are checked in, so this
# construction is deterministic and reproducible.
MA1B_PROMPT_FILE="${ARTIFACTS_DIR}/ma1b_prompt.txt"

log()  { echo "milestone_a: $*" >&2; }
die()  { echo "milestone_a: ERROR: $*" >&2; exit 1; }

# --- environment readiness (fast no-ops when already current/present) ---
ensure_ready() {
    if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
        log "image $IMAGE missing, building..."
        "$STREAM_ENV" image
    fi
    log "verifying container build is current (no-ops fast if so)..."
    "$STREAM_ENV" build >/dev/null
    if ! docker run --rm -v "${MODELS_VOLUME}:/models:ro" "$IMAGE" \
        bash -c "[[ -f ${MODEL_IN_CONTAINER} ]]" 2>/dev/null; then
        log "model missing from ${MODELS_VOLUME}, copying..."
        "$STREAM_ENV" models
    fi
}

# --- MA-1b prompt construction + verification ---
ensure_ma1b_prompt() {
    local hard="${REPO_ROOT}/bench/prompts/hard.txt"
    [[ -f "$hard" ]] || die "missing $hard"
    { cat "$hard"; head -n 5 "$hard"; } > "$MA1B_PROMPT_FILE"

    local tok="${REPO_ROOT}/llama.cpp/build-noblas/bin/llama-tokenize"
    if [[ -x "$tok" ]]; then
        local count
        count="$("$tok" -m "${REPO_ROOT}/models/${MODEL_NAME}" -f "$MA1B_PROMPT_FILE" \
            --show-count 2>/dev/null | grep -oE '[0-9]+$' | tail -1 || true)"
        [[ -n "$count" ]] || die "llama-tokenize produced no count for $MA1B_PROMPT_FILE"
        log "MA-1b prompt: $(wc -l < "$MA1B_PROMPT_FILE" | tr -d ' ') lines, ${count} tokens (host tokenizer)"
        [[ "$count" -ge 600 ]] || die "MA-1b prompt is only ${count} tokens (need >=600) -- bench/prompts/hard.txt changed; adjust the repeat count above"
        echo "$count" > "${ARTIFACTS_DIR}/ma1b_prompt_tokens.txt"
    else
        log "WARNING: $tok not built; skipping live token-count verification." \
            "Last verified count was 623 tokens (25 lines: hard.txt's 20 + its first 5 repeated)," \
            "recorded in docs/WORKLOG.md's MA entry. Proceeding on that basis."
        echo "623 (unverified this run -- host llama-tokenize absent)" > "${ARTIFACTS_DIR}/ma1b_prompt_tokens.txt"
    fi
}

# --- perf-line parsing (matches llama.cpp's common_perf_print output) ---
# Each helper isolates one unique line, then pulls the number that follows a
# fixed label out of it. "eval time =" is a substring of "prompt eval time =",
# so the decode line is found by excluding the prefill line explicitly.
# Every helper ends in `|| true`: under `set -euo pipefail` a `grep` that finds
# no match exits 1 and (via pipefail) fails the whole pipeline even when a
# later stage in it exits 0 -- and "no match" is a legitimate, expected outcome
# here (an OOMKilled run never reaches the perf-print block at all).
perf_load_ms() {
    grep 'common_perf_print:.*load time =' "$1" | grep -oE '= *[0-9]+\.[0-9]+ ms' | grep -oE '[0-9.]+' || true
}
perf_prefill_line()   { grep 'common_perf_print: prompt eval time =' "$1" || true; }
perf_decode_line()    { grep 'common_perf_print:.*eval time =' "$1" | grep -v 'prompt eval time =' || true; }
line_total_ms()        { printf '%s' "$1" | grep -oE '= *[0-9]+\.[0-9]+ ms' | head -1 | grep -oE '[0-9.]+' || true; }
line_ms_per_tok()       { printf '%s' "$1" | grep -oE '[0-9]+\.[0-9]+ ms per token' | grep -oE '^[0-9.]+' || true; }
line_toks_per_s()       { printf '%s' "$1" | grep -oE '[0-9]+\.[0-9]+ tokens per second' | grep -oE '^[0-9.]+' || true; }
predicted_s_per_tok()   { grep -oE 'predicted s/token = [0-9]+\.[0-9]+' "$1" | grep -oE '[0-9]+\.[0-9]+' | head -1 || true; }
ledger_block()          { grep -E ' I residency: ' "$1" || true; }
mem_peak_bytes()        { awk '/--- memory\.peak ---/{getline; print; exit}' "$1" || true; }
cgrun_oomkilled()       { grep -oE 'OOMKilled=[a-z]+' "$1" | tail -1 | cut -d= -f2 || true; }
cgrun_exit_status()     { grep -oE 'exit_status=[0-9-]+' "$1" | tail -1 | cut -d= -f2 || true; }
majflt()                { grep 'Major (requiring I/O) page faults:' "$1" | grep -oE '[0-9]+$' || true; }

# max(current_bytes) over a memwatch.sh CSV embedded between the
# "=== memwatch.csv ===" marker this script prints and cgrun's own
# "--- memory.peak ---" trailer.
memwatch_max_col() {
    local log="$1" col="$2"
    awk -F, -v c="$col" '
        /=== memwatch\.csv ===/ { flag=1; next }
        /--- memory\.peak ---/  { flag=0 }
        flag && NR>1 && $c+0>max { max=$c+0 }
        END { print max+0 }
    ' "$log"
}

bytes_to_mib() { awk -v b="$1" 'BEGIN{printf "%.1f", b/1048576}'; }

# ms -> seconds at the given precision, or "--" when ms is empty (an arm that
# never reached common_perf_print -- e.g. SIGKILLed before load finished --
# has no load/prefill time to report, and "0.00" would misreport that as a
# measured near-zero time rather than "never logged").
ms_to_s_or_dash() {
    local ms="$1" prec="${2:-2}"
    if [[ -z "$ms" ]]; then
        echo "--"
    else
        awk -v m="$ms" -v p="$prec" 'BEGIN{printf "%." p "f", m/1000}'
    fi
}

# --- MA-1: observed, 3g cap, memwatch sidecar ---
run_ma1() {
    log "MA-1 (observed): drop_caches, cgrun 3g, --stream-weights --max-ram-mib ${MAX_RAM_MIB}, -n 64, memwatch sidecar"
    "$STREAM_ENV" drop_caches >/dev/null

    local inner="
/work/scripts/memwatch.sh 1 > /tmp/memwatch.csv &
MWPID=\$!
/build/bin/llama-completion -m ${MODEL_IN_CONTAINER} --stream-weights --max-ram-mib ${MAX_RAM_MIB} \
  --stream-disk-gbps ${DISK_GBPS} ${FIXED_ARGS[*]} -n 64 -lv 4 -p \"${STD_PROMPT}\"
status=\$?
kill \$MWPID 2>/dev/null || true
wait \$MWPID 2>/dev/null || true
echo '=== memwatch.csv ==='
cat /tmp/memwatch.csv
exit \$status
"

    set +e
    "$STREAM_ENV" cgrun 3g bash -c "$inner" > "${ARTIFACTS_DIR}/ma1.log" 2>&1
    local status=$?
    set -e

    local log="${ARTIFACTS_DIR}/ma1.log"
    local peak; peak="$(mem_peak_bytes "$log")"
    local mw_max; mw_max="$(memwatch_max_col "$log" 2)"
    local decode_line; decode_line="$(perf_decode_line "$log")"
    local prefill_line; prefill_line="$(perf_prefill_line "$log")"
    local load_ms; load_ms="$(perf_load_ms "$log")"
    local decode_ms_tok; decode_ms_tok="$(line_ms_per_tok "$decode_line")"
    local decode_tps; decode_tps="$(line_toks_per_s "$decode_line")"
    local predicted; predicted="$(predicted_s_per_tok "$log")"
    local oomkilled; oomkilled="$(cgrun_oomkilled "$log")"

    local decode_s_tok ratio verdict
    if [[ -n "$decode_ms_tok" && -n "$predicted" ]]; then
        decode_s_tok=$(awk -v m="$decode_ms_tok" 'BEGIN{printf "%.4f", m/1000}')
        ratio=$(awk -v d="$decode_s_tok" -v p="$predicted" 'BEGIN{printf "%.3f", d/p}')
    else
        decode_s_tok=""; ratio=""
    fi

    verdict="FAIL"
    if [[ "$status" -eq 0 && -n "$peak" && -n "$mw_max" && -n "$ratio" ]]; then
        if [[ "$peak" -lt "$CAP_BYTES" && "$mw_max" -lt "$CAP_BYTES" ]] \
            && awk -v r="$ratio" 'BEGIN{exit !(r>=0.7 && r<=1.3)}'; then
            verdict="PASS"
        fi
    fi

    {
        echo "ARM=MA-1"
        echo "CAP_MODE=observed"
        echo "CAP_MIB=3072"
        echo "EXIT_STATUS=${status}"
        echo "OOMKILLED=${oomkilled}"
        echo "PEAK_BYTES=${peak}"
        echo "PEAK_MIB=$(bytes_to_mib "${peak:-0}")"
        echo "MEMWATCH_MAX_CURRENT_BYTES=${mw_max}"
        echo "MEMWATCH_MAX_CURRENT_MIB=$(bytes_to_mib "${mw_max:-0}")"
        echo "LOAD_MS=${load_ms}"
        echo "LOAD_S=$(ms_to_s_or_dash "$load_ms" 2)"
        echo "PREFILL_MS_TOTAL=$(line_total_ms "$prefill_line")"
        echo "PREFILL_MS_TOK=$(line_ms_per_tok "$prefill_line")"
        echo "DECODE_MS_TOK=${decode_ms_tok}"
        echo "DECODE_S_TOK=${decode_s_tok}"
        echo "DECODE_TOKS=${decode_tps}"
        echo "PREDICTED_S_TOK=${predicted}"
        echo "RATIO=${ratio}"
        echo "VERDICT=${verdict}"
    } > "${ARTIFACTS_DIR}/ma1.env"
    ledger_block "$log" > "${ARTIFACTS_DIR}/ma1.ledger.txt"

    log "MA-1 done: exit=${status} peak=$(bytes_to_mib "${peak:-0}")MiB mw_max=$(bytes_to_mib "${mw_max:-0}")MiB decode=${decode_ms_tok}ms/tok predicted=${predicted}s/tok ratio=${ratio} verdict=${verdict}"
}

# --- MA-1b: observed, 3g cap, full-ubatch prefill, memwatch sidecar ---
run_ma1b() {
    ensure_ma1b_prompt
    log "MA-1b (full-ubatch prefill): drop_caches, cgrun 3g, same flags as MA-1, long prompt, -n 16, memwatch sidecar"
    "$STREAM_ENV" drop_caches >/dev/null

    local rel_prompt="bench/.artifacts/milestone_a/ma1b_prompt.txt"
    local inner="
/work/scripts/memwatch.sh 1 > /tmp/memwatch.csv &
MWPID=\$!
/build/bin/llama-completion -m ${MODEL_IN_CONTAINER} --stream-weights --max-ram-mib ${MAX_RAM_MIB} \
  --stream-disk-gbps ${DISK_GBPS} ${FIXED_ARGS[*]} -n 16 -lv 4 -f /work/${rel_prompt}
status=\$?
kill \$MWPID 2>/dev/null || true
wait \$MWPID 2>/dev/null || true
echo '=== memwatch.csv ==='
cat /tmp/memwatch.csv
exit \$status
"
    set +e
    "$STREAM_ENV" cgrun 3g bash -c "$inner" > "${ARTIFACTS_DIR}/ma1b.log" 2>&1
    local status=$?
    set -e

    local log="${ARTIFACTS_DIR}/ma1b.log"
    local peak; peak="$(mem_peak_bytes "$log")"
    local mw_max_current; mw_max_current="$(memwatch_max_col "$log" 2)"
    local mw_max_anon; mw_max_anon="$(memwatch_max_col "$log" 4)"
    local prefill_line; prefill_line="$(perf_prefill_line "$log")"
    local load_ms; load_ms="$(perf_load_ms "$log")"
    local n_prompt; n_prompt="$(cat "${ARTIFACTS_DIR}/ma1b_prompt_tokens.txt" 2>/dev/null | grep -oE '^[0-9]+' || true)"

    local verdict="FAIL"
    if [[ "$status" -eq 0 && -n "$peak" && -n "$mw_max_current" ]] \
        && [[ "$peak" -lt "$CAP_BYTES" && "$mw_max_current" -lt "$CAP_BYTES" ]]; then
        verdict="PASS"
    fi

    # Analytical prediction, recorded for comparison but not gated on:
    # ceil(n_prompt/512) ubatches x 1508.8 MiB streamed / (2.977 GB/s in MiB/s).
    local predicted_prefill_s=""
    if [[ -n "$n_prompt" ]]; then
        predicted_prefill_s=$(awk -v np="$n_prompt" -v gbps="$DISK_GBPS" 'BEGIN{
            ubatches = int((np + 511) / 512);
            mibps = gbps * 1000000000 / 1048576;
            printf "%.3f", (ubatches * 1508.8) / mibps
        }')
    fi

    {
        echo "ARM=MA-1b"
        echo "CAP_MODE=observed"
        echo "CAP_MIB=3072"
        echo "N_PROMPT_TOKENS=${n_prompt}"
        echo "EXIT_STATUS=${status}"
        echo "OOMKILLED=$(cgrun_oomkilled "$log")"
        echo "PEAK_BYTES=${peak}"
        echo "PEAK_MIB=$(bytes_to_mib "${peak:-0}")"
        echo "MEMWATCH_MAX_CURRENT_MIB=$(bytes_to_mib "${mw_max_current:-0}")"
        echo "MEMWATCH_MAX_ANON_BYTES=${mw_max_anon}"
        echo "MEMWATCH_MAX_ANON_MIB=$(bytes_to_mib "${mw_max_anon:-0}")"
        echo "LOAD_MS=${load_ms}"
        echo "LOAD_S=$(ms_to_s_or_dash "$load_ms" 2)"
        echo "PREFILL_MS_TOTAL=$(line_total_ms "$prefill_line")"
        echo "PREFILL_S=$(ms_to_s_or_dash "$(line_total_ms "$prefill_line")" 3)"
        echo "PREDICTED_PREFILL_S=${predicted_prefill_s}"
        echo "VERDICT=${verdict}"
    } > "${ARTIFACTS_DIR}/ma1b.env"
    ledger_block "$log" > "${ARTIFACTS_DIR}/ma1b.ledger.txt"

    log "MA-1b done: exit=${status} n_prompt=${n_prompt} peak=$(bytes_to_mib "${peak:-0}")MiB anon_peak=$(bytes_to_mib "${mw_max_anon:-0}")MiB prefill=$(line_total_ms "$prefill_line")ms verdict=${verdict}"
}

# --- MA-2: enforced, 2048m cap, same flags as MA-1, no sidecar ---
run_ma2() {
    log "MA-2 (enforced): drop_caches, cgrun ${MAX_RAM_MIB}m, same flags as MA-1, -n 64"
    "$STREAM_ENV" drop_caches >/dev/null

    set +e
    "$STREAM_ENV" cgrun "${MAX_RAM_MIB}m" \
        /build/bin/llama-completion -m "$MODEL_IN_CONTAINER" --stream-weights --max-ram-mib "$MAX_RAM_MIB" \
        --stream-disk-gbps "$DISK_GBPS" "${FIXED_ARGS[@]}" -n 64 -lv 4 -p "$STD_PROMPT" \
        > "${ARTIFACTS_DIR}/ma2.log" 2>&1
    local status=$?
    set -e

    local log="${ARTIFACTS_DIR}/ma2.log"
    local peak; peak="$(mem_peak_bytes "$log")"
    local decode_line; decode_line="$(perf_decode_line "$log")"
    local decode_tps; decode_tps="$(line_toks_per_s "$decode_line")"
    local decode_ms_tok; decode_ms_tok="$(line_ms_per_tok "$decode_line")"
    local load_ms; load_ms="$(perf_load_ms "$log")"
    local predicted; predicted="$(predicted_s_per_tok "$log")"
    local oomkilled; oomkilled="$(cgrun_oomkilled "$log")"

    # tok/s-within-15%-of-MA-1 check, only meaningful once ma1.env exists.
    local ma1_tps="" pct_diff="" verdict="FAIL"
    if [[ -f "${ARTIFACTS_DIR}/ma1.env" ]]; then
        ma1_tps="$(grep '^DECODE_TOKS=' "${ARTIFACTS_DIR}/ma1.env" | cut -d= -f2 || true)"
    fi
    if [[ "$status" -eq 0 && "$oomkilled" == "false" && -n "$decode_tps" && -n "$ma1_tps" ]]; then
        pct_diff=$(awk -v a="$decode_tps" -v b="$ma1_tps" 'BEGIN{printf "%.3f", (a-b)/b}')
        if awk -v p="$pct_diff" 'BEGIN{v=p; if(v<0)v=-v; exit !(v<=0.15)}'; then
            verdict="PASS"
        fi
    fi

    {
        echo "ARM=MA-2"
        echo "CAP_MODE=enforced"
        echo "CAP_MIB=${MAX_RAM_MIB}"
        echo "EXIT_STATUS=${status}"
        echo "OOMKILLED=${oomkilled}"
        echo "PEAK_BYTES=${peak}"
        echo "PEAK_MIB=$(bytes_to_mib "${peak:-0}")"
        echo "LOAD_MS=${load_ms}"
        echo "LOAD_S=$(ms_to_s_or_dash "$load_ms" 2)"
        echo "DECODE_MS_TOK=${decode_ms_tok}"
        echo "DECODE_TOKS=${decode_tps}"
        echo "PREDICTED_S_TOK=${predicted}"
        echo "MA1_DECODE_TOKS=${ma1_tps}"
        echo "PCT_DIFF_VS_MA1=${pct_diff}"
        echo "VERDICT=${verdict}"
    } > "${ARTIFACTS_DIR}/ma2.env"

    log "MA-2 done: exit=${status} OOMKilled=${oomkilled} peak=$(bytes_to_mib "${peak:-0}")MiB decode_tok/s=${decode_tps} (MA-1=${ma1_tps}, diff=${pct_diff}) verdict=${verdict}"
}

# --- MA-3: unmanaged A/B, 2048m cap, two arms, no --stream-weights ---
run_ma3_arm() {
    local name="$1"; shift
    local log="${ARTIFACTS_DIR}/ma3_${name}.log"
    log "MA-3 ${name} arm: drop_caches, cgrun ${MAX_RAM_MIB}m, $*"
    "$STREAM_ENV" drop_caches >/dev/null

    set +e
    "$STREAM_ENV" cgrun "${MAX_RAM_MIB}m" /usr/bin/time -v \
        /build/bin/llama-completion -m "$MODEL_IN_CONTAINER" "$@" "${FIXED_ARGS[@]}" -n 64 -lv 4 -p "$STD_PROMPT" \
        > "$log" 2>&1
    local status=$?
    set -e

    local peak; peak="$(mem_peak_bytes "$log")"
    local decode_line; decode_line="$(perf_decode_line "$log")"
    local decode_tps; decode_tps="$(line_toks_per_s "$decode_line")"
    local decode_ms_tok; decode_ms_tok="$(line_ms_per_tok "$decode_line")"
    local load_ms; load_ms="$(perf_load_ms "$log")"
    local oomkilled; oomkilled="$(cgrun_oomkilled "$log")"
    local mf; mf="$(majflt "$log")"

    local fate="ran to completion"
    [[ "$status" -ne 0 ]] && fate="exit=${status}"
    [[ "$oomkilled" == "true" ]] && fate="OOMKilled"

    {
        echo "ARM=MA-3-${name}"
        echo "CAP_MODE=enforced"
        echo "CAP_MIB=${MAX_RAM_MIB}"
        echo "EXIT_STATUS=${status}"
        echo "OOMKILLED=${oomkilled}"
        echo "FATE=${fate}"
        echo "PEAK_BYTES=${peak}"
        echo "PEAK_MIB=$(bytes_to_mib "${peak:-0}")"
        echo "LOAD_MS=${load_ms}"
        echo "LOAD_S=$(ms_to_s_or_dash "$load_ms" 2)"
        echo "DECODE_MS_TOK=${decode_ms_tok}"
        echo "DECODE_TOKS=${decode_tps}"
        echo "MAJFLT=${mf}"
    } > "${ARTIFACTS_DIR}/ma3_${name}.env"

    log "MA-3 ${name} done: fate=${fate} peak=$(bytes_to_mib "${peak:-0}")MiB decode_tok/s=${decode_tps} majflt=${mf}"
}

run_ma3() {
    run_ma3_arm kernelfair --no-repack
    run_ma3_arm naive
    local kf_tps naive_fate ratio_line
    kf_tps="$(grep '^DECODE_TOKS=' "${ARTIFACTS_DIR}/ma3_kernelfair.env" | cut -d= -f2 || true)"
    local ma2_tps=""
    [[ -f "${ARTIFACTS_DIR}/ma2.env" ]] && ma2_tps="$(grep '^DECODE_TOKS=' "${ARTIFACTS_DIR}/ma2.env" | cut -d= -f2 || true)"
    naive_fate="$(grep '^FATE=' "${ARTIFACTS_DIR}/ma3_naive.env" | cut -d= -f2- || true)"

    if [[ -n "$kf_tps" && -n "$ma2_tps" ]]; then
        ratio_line="managed(MA-2)/unmanaged(kernel-fair) = $(awk -v a="$ma2_tps" -v b="$kf_tps" 'BEGIN{printf "%.3f", a/b}')"
    else
        ratio_line="managed/unmanaged ratio: N/A -- unmanaged kernel-fair arm did not complete (see ma3_kernelfair.env FATE)"
    fi
    echo "$ratio_line" > "${ARTIFACTS_DIR}/ma3_ratio.txt"
    echo "naive-default arm fate: ${naive_fate}" >> "${ARTIFACTS_DIR}/ma3_ratio.txt"
    log "MA-3 summary: ${ratio_line}"
    log "MA-3 naive-default fate: ${naive_fate}"
}

# --- table: render the markdown results table from whatever *.env files exist ---
env_get() { local f="$1" k="$2"; [[ -f "$f" ]] && grep "^${k}=" "$f" | cut -d= -f2- || true; }

write_table() {
    local out="${ARTIFACTS_DIR}/results_table.md"
    {
        echo "| arm | cap-mode | cap MiB | memory.peak MiB | load s | prefill s | decode tok/s | predicted s/tok | meas/pred | verdict |"
        echo "|---|---|---|---|---|---|---|---|---|---|"

        local f="${ARTIFACTS_DIR}/ma1.env"
        if [[ -f "$f" ]]; then
            echo "| MA-1 observed | $(env_get "$f" CAP_MODE) | $(env_get "$f" CAP_MIB) | $(env_get "$f" PEAK_MIB) | $(env_get "$f" LOAD_S) | -- | $(env_get "$f" DECODE_TOKS) | $(env_get "$f" PREDICTED_S_TOK) | $(env_get "$f" RATIO) | $(env_get "$f" VERDICT) |"
        else
            echo "| MA-1 observed | (not yet run) | | | | | | | | |"
        fi

        f="${ARTIFACTS_DIR}/ma1b.env"
        if [[ -f "$f" ]]; then
            echo "| MA-1b observed (full ubatch) | $(env_get "$f" CAP_MODE) | $(env_get "$f" CAP_MIB) | $(env_get "$f" PEAK_MIB) | $(env_get "$f" LOAD_S) | $(env_get "$f" PREFILL_S) | -- | -- | -- | $(env_get "$f" VERDICT) |"
        else
            echo "| MA-1b observed (full ubatch) | (not yet run) | | | | | | | | |"
        fi

        f="${ARTIFACTS_DIR}/ma2.env"
        if [[ -f "$f" ]]; then
            echo "| MA-2 enforced | $(env_get "$f" CAP_MODE) | $(env_get "$f" CAP_MIB) | $(env_get "$f" PEAK_MIB) | $(env_get "$f" LOAD_S) | -- | $(env_get "$f" DECODE_TOKS) | $(env_get "$f" PREDICTED_S_TOK) | -- | $(env_get "$f" VERDICT) |"
        else
            echo "| MA-2 enforced | (not yet run) | | | | | | | | |"
        fi

        f="${ARTIFACTS_DIR}/ma3_kernelfair.env"
        if [[ -f "$f" ]]; then
            echo "| MA-3 unmanaged kernel-fair (--no-repack) | enforced | $(env_get "$f" CAP_MIB) | $(env_get "$f" PEAK_MIB) | $(env_get "$f" LOAD_S) | -- | $(env_get "$f" DECODE_TOKS) | -- | -- | $(env_get "$f" FATE) |"
        else
            echo "| MA-3 unmanaged kernel-fair (--no-repack) | (not yet run) | | | | | | | | |"
        fi

        f="${ARTIFACTS_DIR}/ma3_naive.env"
        if [[ -f "$f" ]]; then
            echo "| MA-3 unmanaged naive-default | enforced | $(env_get "$f" CAP_MIB) | $(env_get "$f" PEAK_MIB) | $(env_get "$f" LOAD_S) | -- | $(env_get "$f" DECODE_TOKS) | -- | -- | $(env_get "$f" FATE) |"
        else
            echo "| MA-3 unmanaged naive-default | (not yet run) | | | | | | | | |"
        fi

        echo ""
        [[ -f "${ARTIFACTS_DIR}/ma3_ratio.txt" ]] && cat "${ARTIFACTS_DIR}/ma3_ratio.txt"
        echo ""
        echo "MA-4 (callback overhead): by reference, not a new run -- best-of-8 callback-invocation"
        echo "overhead -0.008%, gate cost ~0.06% at 4B streamed scale (gatecb-vs-noopcb -7.64% on"
        echo "SmolLM2 scale). See task-B3-report.md and docs/WORKLOG.md's Task B3 fix round."
    } > "$out"
    cat "$out"
}

usage() {
    cat <<'EOF'
usage: scripts/milestone_a.sh <arm>

arms:
  ma1     observed,  3g cap,     --stream-weights --max-ram-mib 2048, -n 64, memwatch
  ma1b    observed,  3g cap,     same as ma1, ~600-token prompt, -n 16, memwatch
  ma2     enforced,  2048m cap,  same flags as ma1, -n 64, no sidecar
  ma3     unmanaged, 2048m cap,  A/B: kernel-fair (--no-repack) + naive-default
  all     ma1, ma1b, ma2, ma3 in order
  table   (re)render the markdown results table from existing *.env files
EOF
}

main() {
    [[ $# -ge 1 ]] || { usage >&2; exit 1; }
    local arm="$1"
    [[ "$arm" == "table" ]] || ensure_ready
    case "$arm" in
        ma1)   run_ma1 ;;
        ma1b)  run_ma1b ;;
        ma2)   run_ma2 ;;
        ma3)   run_ma3 ;;
        all)   run_ma1; run_ma1b; run_ma2; run_ma3 ;;
        table) : ;;
        -h|--help) usage; exit 0 ;;
        *) echo "milestone_a.sh: unknown arm: $arm" >&2; usage >&2; exit 1 ;;
    esac
    write_table
}

main "$@"
