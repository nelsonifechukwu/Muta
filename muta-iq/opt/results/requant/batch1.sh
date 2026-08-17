#!/bin/bash
R=/Users/timii/Developer/Muta/muta-iq/opt/results/requant
SRC=/Users/timii/Developer/Muta/muta-iq/model/bitcpm4-8b-tq2_0.gguf
$R/run_variant.sh bitcpm4-8b-tq2_0-oq5_k-eq4_k   $SRC TQ2_0 Q5_K   Q4_K
$R/run_variant.sh bitcpm4-8b-tq2_0-oq4_k-eq4_k   $SRC TQ2_0 Q4_K   Q4_K
$R/run_variant.sh bitcpm4-8b-tq2_0-oiq4_xs-eq4_k $SRC TQ2_0 IQ4_XS Q4_K
$R/run_variant.sh bitcpm4-8b-tq2_0-oq5_0-eq4_k   $SRC TQ2_0 Q5_0   Q4_K
echo "BATCH1 DONE $(date '+%T')"
