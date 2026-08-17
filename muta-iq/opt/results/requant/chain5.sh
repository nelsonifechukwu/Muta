#!/bin/bash
R=/Users/timii/Developer/Muta/muta-iq/opt/results/requant
until grep -q "REBENCH DONE" $R/rebench.out; do sleep 15; done
$R/run_acc.sh v6 /Users/timii/Developer/Muta/muta-iq/opt/models/bitcpm4-8b-tq2_0-oq4_k-eq3_k.gguf
$R/run_acc.sh v5 /Users/timii/Developer/Muta/muta-iq/opt/models/bitcpm4-8b-tq2_0-oq5_0-eq4_k.gguf
echo "ACC2 DONE $(date '+%T')"
