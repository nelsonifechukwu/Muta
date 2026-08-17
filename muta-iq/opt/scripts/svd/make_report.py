#!/usr/bin/env python
"""Build svd_report.md tables from layers.jsonl / vocab.jsonl / recon.json."""
import json, os, sys
import numpy as np
R = '/Users/timii/Developer/Muta/muta-iq/opt/results/svd'
RANKS = [256, 512, 1024, 1536, 2048, 2560, 3072, 3584, 4096]

def load(fn):
    p = os.path.join(R, fn)
    if not os.path.exists(p): return []
    return [json.loads(l) for l in open(p) if l.strip()]

layers = load('layers.jsonl'); vocab = load('vocab.jsonl'); rown = load('layers_rownorm.jsonl')
mp = json.load(open(os.path.join(R, 'mp_baseline.json'))) if os.path.exists(os.path.join(R, 'mp_baseline.json')) else {}
recon = json.load(open(os.path.join(R, 'recon.json'))) if os.path.exists(os.path.join(R, 'recon.json')) else None

def short(n): return n.replace('.weight', '').replace('blk.', 'L')

out = []
W = out.append
W('# SVD low-rank feasibility for bitcpm4-8b-tq2_0.gguf\n')
W('Question: can W[out,in] ~= A[out,r] B[r,in] cut bytes/token or RAM without wrecking accuracy?\n')
W('Method: exact singular values from the float64 Gram matrix (chunked; validated vs `np.linalg.svd` to 1e-6 in energy), '
  'energy_r = sum_{i<=r} s_i^2 / sum s_i^2, rel. Frobenius error = sqrt(1-energy_r). '
  'Bytes: dense TQ2_0 = out*in*2.0625/8; factor pair = (out+in)*r*bpw_f/8. Break-even rank r* = out*in*bpw_dense/((out+in)*bpw_f).\n')

# ---- Table 1: energy per tensor
W('## 1. Layer matrices (TQ2_0): Frobenius energy captured at rank r\n')
W('| tensor | shape | ' + ' | '.join(f'E@{r}' for r in RANKS) + ' |')
W('|---|---|' + '---|' * len(RANKS))
for d in layers:
    W(f"| {short(d['name'])} | {d['out']}x{d['in']} | " + ' | '.join(f"{d['energy'][str(r)]:.3f}" for r in RANKS) + ' |')
for k, v in mp.items():
    if k in ('4096x4096', '16384x4096'):
        W(f"| *i.i.d. random baseline (Marchenko-Pastur)* | {k} | " + ' | '.join(f"{v['energy'][str(r)]:.3f}" for r in RANKS) + ' |')
W('')
W('Relative Frobenius reconstruction error sqrt(1-E) at the same ranks:\n')
W('| tensor | ' + ' | '.join(f'err@{r}' for r in RANKS) + ' |')
W('|---|' + '---|' * len(RANKS))
for d in layers:
    W(f"| {short(d['name'])} | " + ' | '.join(f"{d['rel_err'][str(r)]:.3f}" for r in RANKS) + ' |')
W('')
W('## 2. Rank statistics, ternary statistics, break-even\n')
W('| tensor | s_max | s_min | stable rank | eff. rank (entropy) | num.rank (s>1e-3 s_max) | zero frac | +1 frac | -1 frac | zero rows/cols | r* TQ2_0 factors (err) | r* F16 factors (err) |')
W('|---|---|---|---|---|---|---|---|---|---|---|---|')
for d in layers:
    b = d['breakeven']
    W(f"| {short(d['name'])} | {d['s_max']:.1f} | {d['s_min']:.4f} | {d['stable_rank']:.1f} | {d['effective_rank']:.0f} | {d['num_rank_1e-3']} | "
      f"{d['frac_zero']:.3f} | {d['frac_pos']:.3f} | {d['frac_neg']:.3f} | {d.get('zero_rows',0)}/{d.get('zero_cols',0)} | "
      f"{b['TQ2_0']['r_used']} ({b['TQ2_0']['rel_err']:.3f}) | {b['F16']['r_used']} ({b['F16']['rel_err']:.3f}) |")
W('')
# per-class summary
def cls(n):
    if 'ffn' in n: return 'FFN'
    if 'attn' in n: return 'ATTN'
    return n
W('Per-class averages (energy at rank r, and error at the TQ2_0-factor break-even rank):\n')
W('| class | n | ' + ' | '.join(f'E@{r}' for r in RANKS) + ' | mean stable rank | mean eff. rank | mean err @ r*_TQ2 | mean err @ r*_F16 |')
W('|---|---|' + '---|' * (len(RANKS) + 4))
for c in ['FFN', 'ATTN']:
    ds = [d for d in layers if cls(d['name']) == c]
    if not ds: continue
    W(f"| {c} | {len(ds)} | " + ' | '.join(f"{np.mean([d['energy'][str(r)] for d in ds]):.3f}" for r in RANKS)
      + f" | {np.mean([d['stable_rank'] for d in ds]):.1f} | {np.mean([d['effective_rank'] for d in ds]):.0f}"
      + f" | {np.mean([d['breakeven']['TQ2_0']['rel_err'] for d in ds]):.3f} | {np.mean([d['breakeven']['F16']['rel_err'] for d in ds]):.3f} |")
W('')
if rown:
    W('## 2b. Same matrices with every row divided by its per-row scale (pure {-1,0,1} ternary pattern)\n')
    W('TQ2_0 stores the scales anyway, so this is the structure a ternary factor pair must actually reproduce; it removes the effect of a few huge-scale rows on the Frobenius energy.\n')
    W('| tensor | ' + ' | '.join(f'E@{r}' for r in RANKS) + ' | stable rank | eff. rank | err @ r*_TQ2 | err @ r*_F16 |')
    W('|---|' + '---|' * (len(RANKS) + 4))
    for d in rown:
        b = d['breakeven']
        W(f"| {short(d['name'])} | " + ' | '.join(f"{d['energy'][str(r)]:.3f}" for r in RANKS) + f" | {d['stable_rank']:.0f} | {d['effective_rank']:.0f} | {b['TQ2_0']['rel_err']:.3f} | {b['F16']['rel_err']:.3f} |")
    for k, v in mp.items():
        if k in ('4096x4096', '16384x4096'):
            W(f"| *i.i.d. random {k}* | " + ' | '.join(f"{v['energy'][str(r)]:.3f}" for r in RANKS) + f" | {v['stable_rank']:.0f} | - | - | - |")
    W('')
    W('| class | n | ' + ' | '.join(f'E@{r}' for r in RANKS) + ' | mean stable rank | mean eff. rank | mean err @ r*_TQ2 | mean err @ r*_F16 |')
    W('|---|---|' + '---|' * (len(RANKS) + 4))
    for c in ['FFN', 'ATTN']:
        ds = [d for d in rown if cls(d['name']) == c]
        if not ds: continue
        W(f"| {c} (row-normalized) | {len(ds)} | " + ' | '.join(f"{np.mean([d['energy'][str(r)] for d in ds]):.3f}" for r in RANKS)
          + f" | {np.mean([d['stable_rank'] for d in ds]):.0f} | {np.mean([d['effective_rank'] for d in ds]):.0f}"
          + f" | {np.mean([d['breakeven']['TQ2_0']['rel_err'] for d in ds]):.3f} | {np.mean([d['breakeven']['F16']['rel_err'] for d in ds]):.3f} |")
    W('')
# ---- vocab
if vocab:
    W('## 3. output.weight (Q6_K) and token_embd.weight (Q4_K), 73448x4096\n')
    W('| tensor | ' + ' | '.join(f'E@{r}' for r in RANKS) + ' | stable rank | eff. rank | num.rank |')
    W('|---|' + '---|' * (len(RANKS) + 3))
    for d in vocab:
        W(f"| {d['name']} | " + ' | '.join(f"{d['energy'][str(r)]:.3f}" for r in RANKS) + f" | {d['stable_rank']:.1f} | {d['effective_rank']:.0f} | {d['num_rank_1e-3']} |")
    if '73448x4096' in mp:
        v = mp['73448x4096']; W(f"| *i.i.d. random 73448x4096* | " + ' | '.join(f"{v['energy'][str(r)]:.3f}" for r in RANKS) + f" | {v['stable_rank']:.0f} | - | - |")
    W('')
    W('| tensor | ' + ' | '.join(f'err@{r}' for r in RANKS) + ' |')
    W('|---|' + '---|' * len(RANKS))
    for d in vocab:
        W(f"| {d['name']} | " + ' | '.join(f"{d['rel_err'][str(r)]:.3f}" for r in RANKS) + ' |')
    W('')
    W('Break-even vs current storage (dense bytes / MiB, r*, and error at r*):\n')
    W('| tensor | dense | F16 factors r* (err) | Q8_0 factors r* (err) | bytes at r=1024 F16 / Q8_0 | err@1024 |')
    W('|---|---|---|---|---|---|')
    for d in vocab:
        b = d['breakeven']
        W(f"| {d['name']} ({d['qtype']}) | {d['dense_bytes']/2**20:.0f} MiB | {b['F16']['r_used']} ({b['F16']['rel_err']:.3f}) | {b['Q8_0']['r_used']} ({b['Q8_0']['rel_err']:.3f}) | "
          f"{d['bytes_factor_F16']['1024']/2**20:.0f} / {d['bytes_factor_Q8_0']['1024']/2**20:.0f} MiB | {d['rel_err']['1024']:.3f} |")
    W('')
# ---- recon
if recon:
    W(f"## 4. Sanity check: {recon['name']} [{recon['out']}x{recon['in']}] rank-r reconstruction with quantized factors\n")
    W('| rank | SVD-optimal err (theory) | FP32 factors | FP16 factors | ternary absmean, A=US,B=Vt | ternary absmean, balanced sqrt(S) | ternary TQ2_0-style (per-256 absmax), balanced | ternary A only | ternary B only | bytes ratio TQ2_0 factors / dense | bytes ratio F16 factors / dense |')
    W('|---|---|---|---|---|---|---|---|---|---|---|')
    for rk, x in recon['ranks'].items():
        W(f"| {rk} | {x['err_svd_theory']:.3f} | {x['err_fp32_factors']:.3f} | {x['err_fp16_factors']:.3f} | {x['err_tern_absmean_US_Vt']:.3f} | {x['err_tern_absmean_balanced']:.3f} | {x['err_tern_tq2_0_balanced']:.3f} | {x['err_tern_absmean_A_only']:.3f} | {x['err_tern_absmean_B_only']:.3f} | {x['bytes_ratio_TQ2_0']:.2f} | {x['bytes_ratio_F16']:.2f} |")
    W('')
open(os.path.join(R, 'svd_report_tables.md'), 'w').write('\n'.join(out))
print('\n'.join(out))
