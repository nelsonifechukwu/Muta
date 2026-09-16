#!/usr/bin/env bash
# Finite continuation of the already-running STEM batch; not a recurring scheduler.
set -euo pipefail

repo="${1:?usage: run_judges_after_stem.sh REPO STEM_WRAPPER_PID}"
stem_pid="${2:?missing STEM wrapper PID}"
campaign="$repo/bench/measurements/campaign-20260913-balanced-models"
[[ "$stem_pid" =~ ^[0-9]+$ ]] || { echo "invalid PID" >&2; exit 1; }

exec 8>/tmp/muta-judges-continuation.lock
flock -n 8 || { echo "a judge continuation is already waiting" >&2; exit 1; }

if [[ -r "/proc/$stem_pid/cmdline" ]]; then
    tr '\0' ' ' < "/proc/$stem_pid/cmdline" | grep -F 'run_stem_vector_remainder.sh' >/dev/null || {
        echo "PID $stem_pid does not identify the expected STEM wrapper" >&2
        exit 1
    }
fi

printf '%s waiting for STEM wrapper %s\n' "$(date -u +%FT%TZ)" "$stem_pid"
while [[ -e "/proc/$stem_pid" ]]; do
    sleep 10
done
cd "$repo"
bench/.venv-profiler/bin/python -c '
import collections, json, pathlib, sys
from bench.stem_prompt_suite import prompts
root = pathlib.Path(sys.argv[1]) / "raw"
rows = [json.loads(line) for line in (root / "stem-responses-vector-remainder.jsonl").read_text().splitlines()]
expected_models = {"Qwen3.5-2B-Q4_K_M.gguf", "VibeThinker-1.5B-q4_k_m.gguf", "Falcon-H1R-0.6B-Q4_K_M.gguf", "nvidia_OpenReasoning-Nemotron-1.5B-Q4_K_M.gguf"}
expected = {(model, prompt.id) for model in expected_models for prompt in prompts()}
counts = collections.Counter((row["model"], row["id"]) for row in rows)
events = [json.loads(line) for line in (root / "stem-events-vector-remainder.jsonl").read_text().splitlines()]
if set(counts) != expected or any(count != 1 for count in counts.values()) or any(event.get("event") == "model_failure" for event in events):
    raise SystemExit("STEM batch incomplete or invalid; preserving results and withholding automatic judge dispatch")
print("Validated 400 unique STEM responses before judge dispatch")
' "$campaign"
printf '%s starting scalar judges on all thirteen models\n' "$(date -u +%FT%TZ)"
bash "$campaign/run_judges_suite.sh" "$repo"
printf '%s scalar judges stage ended; inspect response counts and failures\n' "$(date -u +%FT%TZ)"
