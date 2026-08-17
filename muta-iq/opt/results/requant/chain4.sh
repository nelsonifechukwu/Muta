#!/bin/bash
R=/Users/timii/Developer/Muta/muta-iq/opt/results/requant
B=/Users/timii/Developer/Muta/muta-iq/opt/llama.cpp/build-cpu/bin
LOCK=/Users/timii/Developer/Muta/muta-iq/opt/scripts/with_lock.py
M=/Users/timii/Developer/Muta/muta-iq/opt/models
until grep -q "ACC DONE" $R/acc.out; do sleep 15; done
echo "### rebench (confirmation, back-to-back) $(date '+%F %T')" >> $R/commands.log
for spec in "v8:$M/bitcpm4-8b-tq1_0-oq4_k-eq4_k.gguf:5" "base:/Users/timii/Developer/Muta/muta-iq/model/bitcpm4-8b-tq2_0.gguf:3" "v6:$M/bitcpm4-8b-tq2_0-oq4_k-eq3_k.gguf:3"; do
  IFS=: read tag gguf reps <<< "$spec"
  echo "$LOCK --tag rebench-$tag -- $B/llama-bench -m $gguf -p 0 -n 128 -r $reps -t 4 -ngl 0 -o json" >> $R/commands.log
  $LOCK --tag rebench-$tag -- $B/llama-bench -m $gguf -p 0 -n 128 -r $reps -t 4 -ngl 0 -o json > $R/rebench_$tag.json 2> $R/rebench_$tag.err
  echo "rebench $tag done $(date '+%T')"
done
echo "REBENCH DONE $(date '+%T')"
