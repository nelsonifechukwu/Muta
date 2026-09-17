#!/usr/bin/env bash
# Promotion-gate pipeline on muta-vm: reference audits → accuracy battery → judge prompts.
# One measurement at a time (the VM is otherwise idle); resumable (finished artifacts are skipped).
# Usage: nohup ~/adtc-prune/gate_pipeline.sh > ~/adtc-prune/logs/gate-pipeline.log 2>&1 &
set -u
ROOT=$HOME/adtc-prune; SEMIS=$HOME/adtc-semis; IMG=adtc-profiler:latest
CANDS="${CANDS:-heal-24L-contiguous-lr5e5-1000 heal-21L-contiguous-lr5e5-1000 heal-21L-contiguous-lr2e5-1000}"
CONTROL="${CONTROL:-control-28L-hybrid-lr5e5-1000}"
TASKS="${TASKS:-arc_easy:500,arc_challenge:100,gsm8k:40}"
cd "$ROOT" && mkdir -p logs artifacts
ts() { date -u +%FT%TZ; }

battery() {  # sub-name — runs the profiler's own accuracy function inside the reference image
  local n=$1 m
  m=$(ls "subs/$n/model/"*.gguf | head -1)
  if [ -f "artifacts/battery-$n.json" ] && python3 -c "import json,sys;sys.exit(0 if json.load(open('artifacts/battery-$n.json')).get('complete') else 1)"; then
    echo "skip battery $n"; return
  fi
  echo "=== battery $n start $(ts) ==="
  sudo docker run --rm --memory=7.5g -v "$ROOT:/w" -v "$ROOT/hfcache:/root/.cache/huggingface" \
    --entrypoint python "$IMG" /w/accuracy_battery.py --model "/w/$m" --tasks "$TASKS" \
    --output "/w/artifacts/battery-$n.json" > "logs/battery-$n.log" 2>&1
  echo "battery $n exit=$? end $(ts)"
}

judge() {  # sub-name — the ten Round-1 judge prompts via llama-server, semi-final protocol
  local n=$1
  if [ -f "$SEMIS/artifacts/responses-$n.json" ] && grep -q GEN_DONE "logs/generate-$n.log" 2>/dev/null; then
    echo "skip judge $n"; return
  fi
  mkdir -p "$SEMIS/subs/$n/model" && cp "subs/$n/metadata.json" "$SEMIS/subs/$n/"
  ln -f "subs/$n/model/"*.gguf "$SEMIS/subs/$n/model/" 2>/dev/null || cp "subs/$n/model/"*.gguf "$SEMIS/subs/$n/model/"
  echo "=== generate $n start $(ts) ==="
  python3 "$SEMIS/generate.py" "$n" > "logs/generate-$n.log" 2>&1
  echo "generate $n exit=$? end $(ts)"
}

echo "PIPELINE_START $(ts)"
while pgrep -f run_screen.sh > /dev/null; do sleep 30; done
./run_screen.sh >> logs/gate-audits.log 2>&1        # audits every sub without an audit JSON
echo "AUDITS_DONE $(ts)"
for n in $CANDS published-28L; do battery "$n"; done
echo "BATTERY_CANDIDATES_DONE $(ts)"
for n in $CANDS $CONTROL; do judge "$n"; done
echo "JUDGE_DONE $(ts)"
for n in $CONTROL rebuilt-28L; do battery "$n"; done
echo "PIPELINE_DONE $(ts)"
