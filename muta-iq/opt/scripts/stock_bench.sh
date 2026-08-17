#!/bin/bash
# Profiler-identical llama-bench (Homebrew stock binary, -p 512 -n 128, no flags) + RSS sampling for a list of GGUFs.
M=/Users/timii/Developer/Muta/muta-iq
PY=/Users/timii/miniforge3/envs/ai/bin/python
OUT=$M/opt/results/stock_bench.tsv
[ -f $OUT ] || echo -e "tag\tfile\tpp_tok_s\ttg_tok_s\ttg_std\tpeak_rss_mb\tsteady_rss_mb\twall_s" > $OUT
BIN=${BIN:-/opt/homebrew/bin/llama-bench}
for f in "$@"; do
  tag=$(basename $f .gguf)-$(basename $(dirname $BIN))
  $PY $M/opt/scripts/bench_rss.py --tag "$tag" --out $M/opt/results/bench_log.jsonl -- $BIN -m $f -p 512 -n 128 -ngl 0 --output json 2>&1 | grep "@@RESULT" > /tmp/muta_stock_res.txt
  $PY - "$tag" "$f" "$OUT" <<PY
import sys, json
tag, f, out = sys.argv[1:4]
d = json.loads(open("/tmp/muta_stock_res.txt").read().split("@@RESULT ",1)[1])
pp = next((b for b in d.get("bench",[]) if b.get("n_prompt",0)>0), {})
tg = next((b for b in d.get("bench",[]) if b.get("n_gen",0)>0), {})
row = [tag, f.split("/")[-1], f"{pp.get('avg_ts',0):.2f}", f"{tg.get('avg_ts',0):.2f}", f"{tg.get('stddev_ts',0):.2f}", str(d.get("peak_rss_mb")), str(d.get("steady_rss_mb")), str(d.get("wall_s"))]
open(out,"a").write("\t".join(row)+"\n"); print("\t".join(row))
PY
done
