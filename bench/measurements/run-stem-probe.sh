#!/bin/bash
# Decisive probe for the 4B-vs-2B model-class decision: does the accuracy gap WIDEN on
# harder STEM tasks? (The 4-task proxy is easy-task-heavy; the hidden ADTC set is
# math_scientific_reasoning.) Waits for the imatrix pass to release the CPU first.
cd /Users/oxowolabi/Developer/personal/Muta
while pgrep -f llama-imatrix > /dev/null; do sleep 30; done
OUT=bench/.artifacts/bakeoff.jsonl
TASKS=mmlu_college_mathematics:100,mmlu_high_school_mathematics:100,mmlu_college_physics:100
for m in models/core/Qwen3.5-4B-Q4_K_M.gguf models/core/candidates/Qwen3.5-2B-Q4_K_M.gguf; do
  python3 -m bench.adtc_bakeoff --models "$m" --accuracy --tasks "$TASKS" --out $OUT 2>&1 | grep -E "^\[|->"
done
echo STEM_PROBE_COMPLETE
