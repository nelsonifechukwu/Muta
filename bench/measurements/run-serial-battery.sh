#!/bin/bash
# Serial accuracy battery — one eval process at a time, priority order.
cd /Users/oxowolabi/Developer/personal/Muta
OUT=bench/.artifacts/bakeoff.jsonl
P() { python3 -m bench.adtc_bakeoff --accuracy --out $OUT "$@" 2>&1 | grep -E "^\[|->"; }
P --models models/core/Qwen3.5-4B-Q4_K_M.gguf --tasks gsm8k:40
P --models models/draft/Qwen3.5-0.8B-Q4_K_M.gguf --tasks gsm8k:40
P --models models/core/candidates/Qwen3.5-2B-Q4_K_M.gguf --tasks arc_easy:100,arc_challenge:100,sciq:100,gsm8k:40
P --models models/core/candidates/Qwen3.5-4B-Q4_0.gguf --tasks arc_easy:100,gsm8k:40
P --models models/core/candidates/Qwen3.5-4B-UD-Q4_K_XL.gguf --tasks arc_easy:100,gsm8k:40
P --models models/core/candidates/Qwen3.5-4B-UD-Q3_K_XL.gguf --tasks arc_easy:100,gsm8k:40
P --models models/core/candidates/Qwen3.5-4B-IQ4_XS.gguf --tasks arc_easy:100,gsm8k:40
echo SERIAL_BATTERY_COMPLETE
