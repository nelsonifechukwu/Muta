#!/bin/bash
R=/Users/timii/Developer/Muta/muta-iq/opt/results/requant
until grep -q "BATCH1 DONE" $R/batch1.out; do sleep 15; done
rm -f /Users/timii/Developer/Muta/muta-iq/opt/models/bitcpm4-8b-tq2_0-oq5_k-eq4_k.gguf
echo "deleted V2 (metrics recorded) $(date '+%T')" >> $R/commands.log
df -h /Users/timii/Developer/Muta/muta-iq/opt | tail -1
$R/batch2.sh
