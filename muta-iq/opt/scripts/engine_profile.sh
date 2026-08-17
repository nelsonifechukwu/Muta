#!/bin/bash
# Profiler-identical llama-bench (-p 512 -n 128, no flags) with OUR engine under several env configs.
M=/Users/timii/Developer/Muta/muta-iq
PY=/Users/timii/miniforge3/envs/ai/bin/python
BIN=$M/opt/llama.cpp/build-cpu/bin/llama-bench
OUT=$M/opt/results/engine_profile.tsv
[ -f $OUT ] || echo -e "tag\tfile\tpp_tok_s\ttg_tok_s\ttg_std\tpeak_rss_mb\tsteady_rss_mb\twall_s\tstats" > $OUT
run() { # tag model env...
  local tag=$1; local f=$2; shift 2
  env "$@" $PY $M/opt/scripts/bench_rss.py --tag "$tag" --out $M/opt/results/bench_log.jsonl -- $BIN -m $f -p 512 -n 128 -ngl 0 --output json 2>&1 | grep "@@RESULT" > /tmp/muta_prof_res.txt
  $PY - "$tag" "$f" "$OUT" <<PY
import sys, json
tag, f, out = sys.argv[1:4]
d = json.loads(open("/tmp/muta_prof_res.txt").read().split("@@RESULT ",1)[1])
pp = next((b for b in d.get("bench",[]) if b.get("n_prompt",0)>0), {})
tg = next((b for b in d.get("bench",[]) if b.get("n_gen",0)>0), {})
stats = [l.strip() for l in d.get("stderr_tail","").splitlines() if "muta-residency: graphs" in l]
row = [tag, f.split("/")[-1], f"{pp.get('avg_ts',0):.2f}", f"{tg.get('avg_ts',0):.2f}", f"{tg.get('stddev_ts',0):.2f}", str(d.get("peak_rss_mb")), str(d.get("steady_rss_mb")), str(d.get("wall_s")), (stats[0] if stats else "")]
open(out,"a").write("\t".join(row)+"\n"); print("\t".join(row))
PY
}
BASE=$M/model/bitcpm4-8b-tq2_0.gguf
ENV=$M/opt/models/bitcpm4-8b-tq2_0-envocab.gguf
S="MUTA_STREAM=1 MUTA_STREAM_STATS=1 MUTA_STREAM_PREFETCH=0 MUTA_STREAM_W=0 MUTA_STREAM_HELPERS=1 MUTA_NO_REPACK=1"
run ours-default            $BASE MUTA_STREAM=0
run ours-lazy-norepack      $BASE MUTA_STREAM=0 MUTA_MMAP_LAZY=1 MUTA_NO_REPACK=1
run ours-lazy-norepack-ub128 $BASE MUTA_STREAM=0 MUTA_MMAP_LAZY=1 MUTA_NO_REPACK=1 MUTA_UBATCH=128
run ours-stream-all-ub128   $BASE $S MUTA_UBATCH=128
run ours-stream-pin1200-ub128 $BASE $S MUTA_UBATCH=128 MUTA_STREAM_PIN_MB=1200
run envocab-ours-lazy-norepack-ub128 $ENV MUTA_STREAM=0 MUTA_MMAP_LAZY=1 MUTA_NO_REPACK=1 MUTA_UBATCH=128
run envocab-ours-stream-all-ub128 $ENV $S MUTA_UBATCH=128
run envocab-ours-stream-pin1100-ub128 $ENV $S MUTA_UBATCH=128 MUTA_STREAM_PIN_MB=1100
