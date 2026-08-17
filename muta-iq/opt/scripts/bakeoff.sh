#!/bin/bash
# Full bake-off battery for one GGUF (run under with_lock): profiler-identical llama-bench (stock Homebrew),
# audit-proxy generic-kernel tg (llama.cpp-generic build, MUTA_FORCE_GENERIC=1, no repack), GSM8K-40 + tutoring
# samples via llama-cpp-python (with the tutoring system prompt), arc_easy(50) via the profiler's own code.
# Usage: bakeoff.sh <model.gguf> [tag] [gsm_n]
set -u
M=/Users/timii/Developer/Muta/muta-iq
PY=/Users/timii/miniforge3/envs/ai/bin/python
MODEL=$1; TAG=${2:-$(basename $MODEL .gguf)}; GN=${3:-40}
OUT=$M/opt/results/bakeoff.tsv
[ -f $OUT ] || echo -e "tag\tfile_mb\tpp_tok_s\ttg_tok_s\tpeak_rss_mb\tgeneric_tg\tgsm8k_acc\tgen_tok_s\tarc_easy50" > $OUT
FMB=$(stat -f %z "$MODEL" | awk '{printf "%.0f", $1/1e6}')
# 1. stock profiler-identical bench + RSS
$PY $M/opt/scripts/bench_rss.py --tag "bake-$TAG" --out $M/opt/results/bench_log.jsonl -- /opt/homebrew/bin/llama-bench -m $MODEL -p 512 -n 128 -ngl 0 --output json 2>&1 | grep "@@RESULT" > /tmp/bake_bench.txt
read PP TG RSS <<< $($PY - <<PYX
import json
d=json.loads(open('/tmp/bake_bench.txt').read().split('@@RESULT ',1)[1])
pp=next((b for b in d.get('bench',[]) if b.get('n_prompt',0)>0),{}); tg=next((b for b in d.get('bench',[]) if b.get('n_gen',0)>0),{})
print(f"{pp.get('avg_ts',0):.2f} {tg.get('avg_ts',0):.2f} {d.get('peak_rss_mb')}")
PYX
)
# 2. audit-proxy generic tg (no repack, forced generic kernels)
GEN=$(MUTA_FORCE_GENERIC=1 MUTA_NO_REPACK=1 $M/opt/llama.cpp-generic/build/bin/llama-bench -m $MODEL -p 0 -n 64 -r 2 -t 4 -ngl 0 -o json 2>/dev/null | $PY -c "import sys,json; r=json.load(sys.stdin); print(f\"{[x for x in r if x['n_gen']>0][0]['avg_ts']:.2f}\")")
# 3. GSM8K + tutoring samples
EV=$($PY $M/opt/scripts/eval_math.py --model $MODEL --n $GN --tag "$TAG" --samples --max-tokens 400 2>/dev/null | grep "@@EVAL")
read GACC GTOK <<< $($PY -c "import json,sys; d=json.loads('''$EV'''.split('@@EVAL ',1)[1]); print(f\"{d['gsm8k_acc']:.3f} {d['gen_tok_s']:.1f}\")")
# 4. arc_easy 50 (profiler's own path)
ARC=$($PY -c "
from pathlib import Path
from adtc_profiler import accuracy
r=accuracy.run_benchmark(Path('$MODEL'), task='arc_easy', limit=50, seed=42); print(r['score'])" 2>/dev/null | tail -1)
echo -e "$TAG\t$FMB\t$PP\t$TG\t$RSS\t$GEN\t$GACC\t$GTOK\t$ARC" | tee -a $OUT
