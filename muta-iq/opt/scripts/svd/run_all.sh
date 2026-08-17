#!/bin/zsh
# One lock acquisition for the whole SVD study: 25 layer matrices, 2 vocab matrices, recon check.
set -u
PY=/Users/timii/miniforge3/envs/ai/bin/python
S=/Users/timii/Developer/Muta/muta-iq/opt/scripts/svd
R=/Users/timii/Developer/Muta/muta-iq/opt/results/svd
cd /tmp
echo "== layers $(date +%T)"
$PY $S/svd_spectrum.py --out $R/layers.jsonl --svdir $R/sv \
  blk.0.ffn_gate.weight blk.0.ffn_up.weight blk.0.ffn_down.weight blk.0.attn_q.weight blk.0.attn_output.weight \
  blk.8.ffn_gate.weight blk.8.ffn_up.weight blk.8.ffn_down.weight blk.8.attn_q.weight blk.8.attn_output.weight \
  blk.16.ffn_gate.weight blk.16.ffn_up.weight blk.16.ffn_down.weight blk.16.attn_q.weight blk.16.attn_output.weight \
  blk.24.ffn_gate.weight blk.24.ffn_up.weight blk.24.ffn_down.weight blk.24.attn_q.weight blk.24.attn_output.weight \
  blk.31.ffn_gate.weight blk.31.ffn_up.weight blk.31.ffn_down.weight blk.31.attn_q.weight blk.31.attn_output.weight
echo "== vocab $(date +%T)"
$PY $S/svd_spectrum.py --out $R/vocab.jsonl --svdir $R/sv output.weight token_embd.weight
echo "== recon $(date +%T)"
$PY $S/recon_check.py --name blk.16.ffn_down.weight --rank 2048 --rank 3072 --out $R/recon.json
echo "== done $(date +%T)"
