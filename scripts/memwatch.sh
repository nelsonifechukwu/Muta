#!/usr/bin/env bash
# scripts/memwatch.sh — 1 Hz CSV sampler of a cgroup v2 scope's
# memory.current / memory.peak / memory.stat (file, anon).
#
# Meant to run INSIDE a streaming-gate container (scripts/stream_env.sh cgrun ...,
# which runs with --cgroupns=private, so /sys/fs/cgroup inside the container IS
# that container's own memory scope root). Run it backgrounded alongside a
# gate/bench workload to get a residency trace over time; redirect stdout to a
# file to keep the trace.
#
# Usage: memwatch.sh [interval_seconds] [cgroup_root]
#   interval_seconds  default 1
#   cgroup_root       default /sys/fs/cgroup
#
# Output (CSV to stdout, one header row then one row per sample):
#   epoch_s,current_bytes,peak_bytes,anon_bytes,file_bytes
# Missing/unreadable fields are emitted as -1 rather than aborting the loop.
# Stop with Ctrl-C or SIGTERM.
set -euo pipefail

INTERVAL="${1:-1}"
CGROOT="${2:-/sys/fs/cgroup}"

read_file() {
    local path="$1"
    if [[ -r "$path" ]]; then
        cat "$path"
    else
        echo "-1"
    fi
}

read_stat_field() {
    local path="$1" field="$2"
    if [[ -r "$path" ]]; then
        awk -v f="$field" '$1==f{print $2; found=1} END{if(!found) print "-1"}' "$path"
    else
        echo "-1"
    fi
}

echo "epoch_s,current_bytes,peak_bytes,anon_bytes,file_bytes"

while true; do
    ts="$(date +%s)"
    current="$(read_file "${CGROOT}/memory.current")"
    peak="$(read_file "${CGROOT}/memory.peak")"
    anon="$(read_stat_field "${CGROOT}/memory.stat" anon)"
    file="$(read_stat_field "${CGROOT}/memory.stat" file)"
    echo "${ts},${current},${peak},${anon},${file}"
    sleep "$INTERVAL"
done
