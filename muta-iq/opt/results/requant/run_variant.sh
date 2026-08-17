#!/bin/bash
# Usage: run_variant.sh <name> <src.gguf> <FTYPE> <OUT_TYPE> <EMB_TYPE>
# Produces /Users/timii/Developer/Muta/muta-iq/opt/models/<name>.gguf and logs under results/requant/.
set -u
NAME=$1; SRC=$2; FTYPE=$3; OUTT=$4; EMBT=$5
B=/Users/timii/Developer/Muta/muta-iq/opt/llama.cpp/build-cpu/bin
LOCK=/Users/timii/Developer/Muta/muta-iq/opt/scripts/with_lock.py
R=/Users/timii/Developer/Muta/muta-iq/opt/results/requant
OUT=/Users/timii/Developer/Muta/muta-iq/opt/models/$NAME.gguf
PY=/Users/timii/miniforge3/envs/ai/bin/python
CORPUS=$R/ppl_corpus.txt
CMDLOG=$R/commands.log
echo "### $NAME  $(date '+%F %T')" >> $CMDLOG

if [ ! -s "$OUT" ] || [ -n "${FORCE:-}" ]; then
  QCMD="$B/llama-quantize --allow-requantize --output-tensor-type $OUTT --token-embedding-type $EMBT $SRC $OUT $FTYPE 8"
  echo "$LOCK --tag quant-$NAME -- $QCMD" >> $CMDLOG
  $LOCK --tag quant-$NAME -- $QCMD > $R/quant_$NAME.log 2>&1
  rc=$?
  echo "EXIT $rc" >> $R/quant_$NAME.log
  if [ $rc -ne 0 ]; then
    echo "[$NAME] quantize FAILED rc=$rc"; tail -5 $R/quant_$NAME.log; rm -f "$OUT"; echo "QUANT_FAIL" > $R/status_$NAME.txt; exit 1
  fi
else
  echo "[$NAME] reusing existing $OUT"
fi

# per-tensor-type bytes
$PY $R/tensor_bytes.py $OUT 2>&1 | grep -v Warning > $R/tensors_$NAME.txt
cat $R/tensors_$NAME.txt

# perplexity
PCMD="$B/llama-perplexity -m $OUT -f $CORPUS -c 512 -b 512 --chunks 12 -t 4"
echo "$LOCK --tag ppl-$NAME -- $PCMD" >> $CMDLOG
$LOCK --tag ppl-$NAME -- $PCMD > $R/ppl_$NAME.log 2>&1
grep -E "Final estimate" $R/ppl_$NAME.log || echo "[$NAME] PPL failed: $(tail -3 $R/ppl_$NAME.log)"

# bench
BCMD="$B/llama-bench -m $OUT -p 0 -n 128 -r 3 -t 4 -ngl 0 -o json"
echo "$LOCK --tag bench-$NAME -- $BCMD" >> $CMDLOG
$LOCK --tag bench-$NAME -- $BCMD > $R/bench_$NAME.json 2> $R/bench_$NAME.err
$PY - "$R/bench_$NAME.json" <<'PYEOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    for row in d:
        if row.get("n_gen") == 128:
            print(f"tg128 avg_ts={row['avg_ts']:.2f} +/- {row['stddev_ts']:.2f} tok/s")
except Exception as e:
    print("bench parse failed:", e)
PYEOF
echo "DONE" > $R/status_$NAME.txt
echo "[$NAME] done $(date '+%T')"
