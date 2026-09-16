#!/usr/bin/env bash
# Sequential measurement pipeline: wait for the reference image, run the
# official profiler in audit mode for each model, then generate judge-prompt
# answers for each model. Nothing runs concurrently — CPU contention would
# corrupt the throughput numbers.
set -u
W=$HOME/adtc-semis
LOG=$W/logs
IMG=adtc-profiler:latest
MODELS="qwen35-0.8b qwen25-1.5b"

ts() { date -u +%FT%TZ; }

while ! sudo docker image inspect "$IMG" >/dev/null 2>&1; do
  if ! pgrep -f "docker build -t $IMG" >/dev/null; then
    echo "image missing and no build running — aborting $(ts)"
    exit 1
  fi
  sleep 20
done
echo "image ready $(ts)"
sudo docker image inspect --format '{{.Id}}' "$IMG" > "$W/artifacts/image-id.txt"
mkdir -p "$W/hfcache"

for m in $MODELS; do
  echo "=== audit $m start $(ts) ==="
  sudo docker run --rm --memory=7.5g \
    -v "$W/subs/$m:/submission:ro" \
    -v "$W/artifacts:/artifacts" \
    -v "$W/hfcache:/root/.cache/huggingface" \
    "$IMG" run --submission /submission --mode audit \
      --output "/artifacts/audit-$m.json" --seed 42 \
    > "$LOG/audit-$m.log" 2>&1
  echo "audit $m exit=$? end $(ts)"
done

for m in $MODELS; do
  echo "=== generate $m start $(ts) ==="
  python3 "$W/generate.py" "$m" > "$LOG/generate-$m.log" 2>&1
  echo "generate $m exit=$? end $(ts)"
done

echo "PIPELINE_DONE $(ts)"
