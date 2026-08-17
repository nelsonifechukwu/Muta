#!/bin/bash
# Residency-window engine sweep: tg128 tok/s + peak RSS for a matrix of streaming configs.
# Runs as ONE locked batch (call via with_lock.py). Appends to opt/results/engine_sweep.tsv
M=/Users/timii/Developer/Muta/muta-iq
B=$M/opt/llama.cpp/build-cpu/bin/llama-bench
PY=/Users/timii/miniforge3/envs/ai/bin/python
MODEL=${MODEL:-$M/model/bitcpm4-8b-tq2_0.gguf}
OUT=$M/opt/results/engine_sweep.tsv
N=${N:-64}; R=${R:-2}
[ -f $OUT ] || echo -e "tag\tmodel\ttg_tok_s\ttg_std\tpeak_rss_mb\tsteady_rss_mb\twall_s\tstats" > $OUT
run() { # tag env...
  local tag=$1; shift
  local res
  env "$@" $PY $M/opt/scripts/bench_rss.py --tag "$tag" -- $B -m $MODEL -p 0 -n $N -r $R -t 4 -ngl 0 --output json 2>&1 | grep "@@RESULT" > /tmp/muta_sweep_res.txt
  $PY - "$tag" "$MODEL" "$OUT" <<PY
import sys, json
tag, model, out = sys.argv[1:4]
line = open("/tmp/muta_sweep_res.txt").read()
d = json.loads(line.split("@@RESULT ",1)[1])
b = (d.get("bench") or [{}])[0]
stats = [l for l in d.get("stderr_tail","").splitlines() if "muta-residency: graphs" in l]
row = [tag, model.split("/")[-1], f"{b.get('avg_ts',0):.2f}", f"{b.get('stddev_ts',0):.2f}", str(d.get("peak_rss_mb")), str(d.get("steady_rss_mb")), str(d.get("wall_s")), (stats[0].strip() if stats else "")]
open(out,"a").write("\t".join(row)+"\n")
print("\t".join(row))
PY
}
S="MUTA_STREAM=1 MUTA_STREAM_STATS=1"
run f1-noprefetch-W0-H1  $S MUTA_STREAM_PREFETCH=0 MUTA_STREAM_W=0 MUTA_STREAM_HELPERS=1
run f1-noprefetch-W0-H1-norepack $S MUTA_STREAM_PREFETCH=0 MUTA_STREAM_W=0 MUTA_STREAM_HELPERS=1 MUTA_NO_REPACK=1
run f1-touch-W2-H2       $S MUTA_STREAM_MODE=touch MUTA_STREAM_W=2 MUTA_STREAM_HELPERS=2
run f1-touch-W0-H1       $S MUTA_STREAM_MODE=touch MUTA_STREAM_W=0 MUTA_STREAM_HELPERS=1
run f1-touch-W0-H1-norepack $S MUTA_STREAM_MODE=touch MUTA_STREAM_W=0 MUTA_STREAM_HELPERS=1 MUTA_NO_REPACK=1
run f1-mlock-W6-H2       $S MUTA_STREAM_MODE=mlock MUTA_STREAM_W=6 MUTA_STREAM_HELPERS=2
run pin600-touch-W6-H2   $S MUTA_STREAM_MODE=touch MUTA_STREAM_W=6 MUTA_STREAM_HELPERS=2 MUTA_STREAM_PIN_MB=600
run pin900-touch-W6-H2   $S MUTA_STREAM_MODE=touch MUTA_STREAM_W=6 MUTA_STREAM_HELPERS=2 MUTA_STREAM_PIN_MB=900
run pin1200-touch-W6-H2  $S MUTA_STREAM_MODE=touch MUTA_STREAM_W=6 MUTA_STREAM_HELPERS=2 MUTA_STREAM_PIN_MB=1200
run pin1500-touch-W6-H2  $S MUTA_STREAM_MODE=touch MUTA_STREAM_W=6 MUTA_STREAM_HELPERS=2 MUTA_STREAM_PIN_MB=1500
run pin1200-mlock-W6-H2  $S MUTA_STREAM_MODE=mlock MUTA_STREAM_W=6 MUTA_STREAM_HELPERS=2 MUTA_STREAM_PIN_MB=1200
run pin1200-touch-W8-H3-qos0 $S MUTA_STREAM_MODE=touch MUTA_STREAM_W=8 MUTA_STREAM_HELPERS=3 MUTA_STREAM_PIN_MB=1200 MUTA_STREAM_QOS=0
run pin600-noprefetch    $S MUTA_STREAM_PREFETCH=0 MUTA_STREAM_W=0 MUTA_STREAM_HELPERS=1 MUTA_STREAM_PIN_MB=600
run pin1200-noprefetch   $S MUTA_STREAM_PREFETCH=0 MUTA_STREAM_W=0 MUTA_STREAM_HELPERS=1 MUTA_STREAM_PIN_MB=1200
