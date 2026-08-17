#!/bin/bash
# Finalize a candidate GGUF into the submission model:
#   bake persona template (+ sampling defaults, name) -> verify (minja + llama-cpp-python) -> link into model/
# Usage: finalize_model.sh <in.gguf> <out-name.gguf> <think:off|on|plain|keep> [system_prompt_file]
set -euo pipefail
M=/Users/timii/Developer/Muta/muta-iq
PY=/Users/timii/miniforge3/envs/ai/bin/python
IN=$1; OUT=$M/model/$2; THINK=${3:-off}; SYS=${4:-$M/opt/eval/system_prompt.txt}
NAME=${NAME:-"Muta Tutor"}
SAMP=${SAMP:-"temp=0.4,top_p=0.9,min_p=0.05,penalty_repeat=1.05"}
if [ "$THINK" = "keep" ]; then
  $PY $M/opt/scripts/bake_system_prompt.py "$IN" "$OUT" --system "$SYS" --set-name "$NAME" --sampling "$SAMP" --set-languages en
else
  $PY $M/opt/scripts/bake_system_prompt.py "$IN" "$OUT" --system "$SYS" --replace-chatml "$THINK" --set-name "$NAME" --sampling "$SAMP" --set-languages en
fi
echo "== minja render check (llama-completion --jinja, single turn)"
$M/opt/llama.cpp/build-cpu/bin/llama-completion -m "$OUT" --jinja -p "What is 25% of 80? Answer briefly." -cnv -st -n 120 --temp 0 -t 4 2>/tmp/fin_err.txt | tail -c 400; echo
grep -E "chat template|thinking" /tmp/fin_err.txt | head -3 || true
echo "== llama-cpp-python (profiler accuracy stack) loads + chat"
$PY - "$OUT" <<'PY'
import sys
from llama_cpp import Llama
llm = Llama(model_path=sys.argv[1], n_ctx=2048, n_threads=4, verbose=False)
r = llm.create_chat_completion(messages=[{"role":"user","content":"What is 25% of 80? Answer briefly."}], max_tokens=80, temperature=0)
print(repr(r["choices"][0]["message"]["content"][:300]))
PY
shasum -a 256 "$OUT"
