#!/bin/zsh
# Second locked pass: spectra of the row-normalized (pure ternary {-1,0,1}) patterns for the same 25 matrices.
set -u
PY=/Users/timii/miniforge3/envs/ai/bin/python
S=/Users/timii/Developer/Muta/muta-iq/opt/scripts/svd
R=/Users/timii/Developer/Muta/muta-iq/opt/results/svd
cd /tmp
echo "== rownorm $(date +%T)"
$PY $S/svd_spectrum.py --row-normalize --out $R/layers_rownorm.jsonl --svdir $R/sv_rownorm \
  blk.0.ffn_gate.weight blk.0.ffn_up.weight blk.0.ffn_down.weight blk.0.attn_q.weight blk.0.attn_output.weight \
  blk.8.ffn_gate.weight blk.8.ffn_up.weight blk.8.ffn_down.weight blk.8.attn_q.weight blk.8.attn_output.weight \
  blk.16.ffn_gate.weight blk.16.ffn_up.weight blk.16.ffn_down.weight blk.16.attn_q.weight blk.16.attn_output.weight \
  blk.24.ffn_gate.weight blk.24.ffn_up.weight blk.24.ffn_down.weight blk.24.attn_q.weight blk.24.attn_output.weight \
  blk.31.ffn_gate.weight blk.31.ffn_up.weight blk.31.ffn_down.weight blk.31.attn_q.weight blk.31.attn_output.weight
echo "== done $(date +%T)"
