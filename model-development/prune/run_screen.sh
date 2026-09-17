#!/usr/bin/env bash
# Sequential reference-image audits for every submission dir under $ROOT/subs.
# Usage (on muta-vm): ROOT=~/adtc-prune ./run_screen.sh
set -u
ROOT=${ROOT:-$HOME/adtc-prune}
IMG=${IMG:-adtc-profiler:latest}
mkdir -p "$ROOT/artifacts" "$ROOT/logs" "$ROOT/hfcache"
ts() { date -u +%FT%TZ; }
sudo docker image inspect --format '{{.Id}}' "$IMG" > "$ROOT/artifacts/image-id.txt"
for sub in "$ROOT"/subs/*/; do
  name=$(basename "$sub")
  [ -f "$ROOT/artifacts/audit-$name.json" ] && { echo "skip $name (audit exists)"; continue; }
  echo "=== audit $name start $(ts) ==="
  sudo docker run --rm --memory=7.5g \
    -v "$sub:/submission:ro" -v "$ROOT/artifacts:/artifacts" -v "$ROOT/hfcache:/root/.cache/huggingface" \
    "$IMG" run --submission /submission --mode audit --output "/artifacts/audit-$name.json" --seed 42 \
    > "$ROOT/logs/audit-$name.log" 2>&1
  echo "audit $name exit=$? end $(ts)"
done
echo "SCREEN_DONE $(ts)"
