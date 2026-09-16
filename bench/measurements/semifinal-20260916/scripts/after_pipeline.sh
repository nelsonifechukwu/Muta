#!/usr/bin/env bash
# Runs once the main pipeline is finished: 0.8B judge prompts with thinking disabled.
set -u
W=$HOME/adtc-semis
while ! grep -q PIPELINE_DONE "$W/logs/pipeline.log" 2>/dev/null; do sleep 30; done
echo "=== generate qwen35-0.8b --no-think start $(date -u +%FT%TZ) ===" >> "$W/logs/pipeline.log"
python3 "$W/generate.py" qwen35-0.8b --no-think > "$W/logs/generate-qwen35-0.8b-nothink.log" 2>&1
echo "generate qwen35-0.8b --no-think exit=$? end $(date -u +%FT%TZ)" >> "$W/logs/pipeline.log"
echo "PIPELINE2_DONE $(date -u +%FT%TZ)" >> "$W/logs/pipeline.log"
