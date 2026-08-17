#!/bin/bash
R=/Users/timii/Developer/Muta/muta-iq/opt/results/requant
until grep -q "BATCH2 DONE" $R/batch2.out; do sleep 15; done
$R/run_acc.sh base /Users/timii/Developer/Muta/muta-iq/model/bitcpm4-8b-tq2_0.gguf
$R/run_acc.sh v3 /Users/timii/Developer/Muta/muta-iq/opt/models/bitcpm4-8b-tq2_0-oq4_k-eq4_k.gguf
$R/run_acc.sh v8 /Users/timii/Developer/Muta/muta-iq/opt/models/bitcpm4-8b-tq1_0-oq4_k-eq4_k.gguf
echo "ACC DONE $(date '+%T')"
