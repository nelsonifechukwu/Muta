#!/usr/bin/env bash
set -euo pipefail

benchmark_pid="${1:?usage: gcp_isolation_watchdog.sh BENCHMARK_PID}"
paused=1

benchmark_children() {
    pgrep -P "$benchmark_pid" || true
}

pause_benchmark() {
    local children
    children="$(benchmark_children)"
    kill -STOP "$benchmark_pid" 2>/dev/null || true
    if [[ -n "$children" ]]; then
        # shellcheck disable=SC2086
        kill -STOP $children 2>/dev/null || true
    fi
}

resume_benchmark() {
    local children
    children="$(benchmark_children)"
    if [[ -n "$children" ]]; then
        # shellcheck disable=SC2086
        kill -CONT $children 2>/dev/null || true
    fi
    kill -CONT "$benchmark_pid" 2>/dev/null || true
}

while kill -0 "$benchmark_pid" 2>/dev/null; do
    if pgrep -f '[n]pm run tauri|[t]auri build|[r]ustc|[c]argo build' >/dev/null; then
        pause_benchmark
        if [[ "$paused" -eq 0 ]]; then
            printf '%s paused: competing packaging process detected\n' "$(date -u +%FT%TZ)"
        fi
        paused=1
    else
        resume_benchmark
        if [[ "$paused" -eq 1 ]]; then
            printf '%s resumed: no competing packaging process\n' "$(date -u +%FT%TZ)"
        fi
        paused=0
    fi
    sleep 2
done

printf '%s stopped: benchmark process exited\n' "$(date -u +%FT%TZ)"
