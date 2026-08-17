#!/bin/bash
R=/Users/timii/Developer/Muta/muta-iq/opt/results/requant
SRC=/Users/timii/Developer/Muta/muta-iq/model/bitcpm4-8b-tq2_0.gguf
SRC1=/Users/timii/Developer/Muta/muta-iq/opt/models/bitcpm4-8b-tq1_0.gguf
$R/run_variant.sh bitcpm4-8b-tq2_0-oq4_k-eq3_k   $SRC  TQ2_0 Q4_K Q3_K
$R/run_variant.sh bitcpm4-8b-tq2_0-oq4_k-eiq4_xs $SRC  TQ2_0 Q4_K IQ4_XS
$R/run_variant.sh bitcpm4-8b-tq1_0-oq4_k-eq4_k   $SRC1 TQ1_0 Q4_K Q4_K
echo "BATCH2 DONE $(date '+%T')"
