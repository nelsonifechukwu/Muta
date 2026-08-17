#!/bin/bash
# Usage: run_acc.sh <label> <gguf>
LABEL=$1; GGUF=$2
R=/Users/timii/Developer/Muta/muta-iq/opt/results/requant
LOCK=/Users/timii/Developer/Muta/muta-iq/opt/scripts/with_lock.py
PY=/Users/timii/miniforge3/envs/ai/bin/python
CMD="$PY -c \"from pathlib import Path; from adtc_profiler import accuracy; print(accuracy.run_benchmark(Path('$GGUF'), task='arc_easy', limit=50, seed=42))\""
echo "### acc-$LABEL $(date '+%F %T')" >> $R/commands.log
echo "$LOCK --tag acc-$LABEL -- $CMD" >> $R/commands.log
$LOCK --tag acc-$LABEL -- $PY -c "from pathlib import Path; from adtc_profiler import accuracy; print(accuracy.run_benchmark(Path('$GGUF'), task='arc_easy', limit=50, seed=42))" > $R/acc_$LABEL.log 2>&1
echo "EXIT $?" >> $R/acc_$LABEL.log
grep -E "benchmark|EXIT" $R/acc_$LABEL.log | tail -2
