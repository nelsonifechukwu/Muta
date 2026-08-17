#!/usr/bin/env python
"""Assemble svd_report.md: narrative + compact tables from the JSON results, full tables appended."""
import json, os, numpy as np
R = '/Users/timii/Developer/Muta/muta-iq/opt/results/svd'
def load(fn):
    p = os.path.join(R, fn); return [json.loads(l) for l in open(p) if l.strip()] if os.path.exists(p) else []
layers, vocab, rown = load('layers.jsonl'), load('vocab.jsonl'), load('layers_rownorm.jsonl')
recon = json.load(open(f'{R}/recon.json')); mp = json.load(open(f'{R}/mp_baseline.json'))
def cls(n): return 'FFN' if 'ffn' in n else 'ATTN'
def short(n): return n.replace('.weight', '').replace('blk.', 'L')
ffn = [d for d in layers if cls(d['name']) == 'FFN']; att = [d for d in layers if cls(d['name']) == 'ATTN']
def rng(ds, f): v = [f(d) for d in ds]; return f'{min(v):.2f}-{max(v):.2f}'
def mean(ds, f): return float(np.mean([f(d) for d in ds]))
out_w = next(d for d in vocab if d['name'] == 'output.weight'); emb = next(d for d in vocab if d['name'] == 'token_embd.weight')
r2048, r3072 = recon['ranks']['2048'], recon['ranks']['3072']
L = []
W = L.append
W('# Can SVD low-rank factorization shrink bitcpm4-8b-tq2_0? — No (measured)\n')
W(f'Model: `/Users/timii/Developer/Muta/muta-iq/model/bitcpm4-8b-tq2_0.gguf` (minicpm, 32 layers, 4096 hidden, 16384 ffn, GQA k/v 4096->256; blk.* TQ2_0 with one f16 scale per row; output Q6_K, token_embd Q4_K, vocab 73448). Bytes per token read: FFN 1584 MiB (70%), attention 280 MiB (12%), output head 235 MiB (10%); token_embd (161 MiB) is only read row-wise.\n')
W('## Verdict per tensor class\n')
W('| class | evidence | verdict |')
W('|---|---|---|')
W(f"| **FFN** (gate/up/down, TQ2_0, 16384x4096) | spectra are flat and indistinguishable from an i.i.d. random matrix (E@2048 = {rng(ffn, lambda d: d['energy']['2048'])} vs Marchenko-Pastur {mp['16384x4096']['energy']['2048']:.2f}; effective rank {min(d['effective_rank'] for d in ffn):.0f}-{max(d['effective_rank'] for d in ffn):.0f} of 4096; all 4096 s.v. > 1e-3 s_max). "
  f"Break-even for TQ2_0 factor pairs is r*=3276 (no byte saving below it) and even there the FP32-optimal error is {rng(ffn, lambda d: d['breakeven']['TQ2_0']['rel_err'])}; at the FP16-factor break-even r*=422 the error is {rng(ffn, lambda d: d['breakeven']['F16']['rel_err'])}. "
  f"Real ternary factors are far worse: blk.16.ffn_down @ r=2048 (62% of dense bytes) -> rel. Frobenius error {r2048['err_tern_absmean_balanced']:.2f} (BitNet absmean) / {r2048['err_tern_tq2_0_balanced']:.2f} (llama.cpp TQ2_0 quantizer, i.e. worse than an all-zero matrix); FP16 factors {r2048['err_fp16_factors']:.2f} at 4.85x the bytes. | **NO.** Not a rank problem that SVD can exploit; any rank that saves bytes destroys the matrix. |")
W(f"| **Attention** (attn_q / attn_output, TQ2_0, 4096x4096) | slightly more structured than random (E@2048 = {rng(att, lambda d: d['energy']['2048'])} vs MP {mp['4096x4096']['energy']['2048']:.2f}; eff. rank {min(d['effective_rank'] for d in att if d['effective_rank']>100):.0f}-{max(d['effective_rank'] for d in att):.0f}), but numerically full-rank ({min(d['num_rank_1e-3'] for d in att)}-{max(d['num_rank_1e-3'] for d in att)} s.v. > 1e-3 s_max). "
  f"Break-even r*=2048 (TQ2_0 factors) gives error {rng([d for d in att if 'blk.0.attn_output' not in d['name']], lambda d: d['breakeven']['TQ2_0']['rel_err'])} for zero saving; r=1024 (half the bytes) error {rng([d for d in att if 'blk.0.attn_output' not in d['name']], lambda d: d['rel_err']['1024'])}; FP16 factors break even at r*=264 (error {rng([d for d in att if 'blk.0.attn_output' not in d['name']], lambda d: d['breakeven']['F16']['rel_err'])}). "
  f"blk.0.attn_output looks low-rank (E@256=0.87, stable rank 1.4) only because <=8 rows carry ~50x the median row scale and 73% of the Frobenius energy - a scale artifact: with rows normalized to the pure ternary pattern it is ordinary (E@256=0.50, eff. rank 1186, err 0.22 at break-even). Attention is only 12% of per-token bytes anyway. | **NO.** |")
W(f"| **Output head** (Q6_K, 73448x4096, read fully every token) | more structured than random (E@1024 = {out_w['energy']['1024']:.2f}, E@2048 = {out_w['energy']['2048']:.2f} vs MP {mp['73448x4096']['energy']['1024']:.2f}/{mp['73448x4096']['energy']['2048']:.2f}; one dominant direction with 5% of the energy) but numerically full-rank (all 4096 s.v. > 1e-3 s_max, eff. rank {out_w['effective_rank']:.0f}). "
  f"vs Q6_K storage (235 MiB): FP16 factors break even at r*={out_w['breakeven']['F16']['r_used']} with error {out_w['breakeven']['F16']['rel_err']:.2f}; Q8_0 factors at r*={out_w['breakeven']['Q8_0']['r_used']} with error {out_w['breakeven']['Q8_0']['rel_err']:.2f}. A 'useful' saving (r=1024: 151 MiB FP16 / 80 MiB Q8_0) costs error {out_w['rel_err']['1024']:.2f}. | **NO** for the head as a bandwidth lever. (Cheaper route to the same MiB is a lower K-quant of the head, e.g. Q4_K/Q5_K, ~5-10% error class - being tested elsewhere in this repo.) |")
W(f"| **Token embedding** (Q4_K, 73448x4096, only touched rows read) | same picture (E@1024 = {emb['energy']['1024']:.2f}, E@2048 = {emb['energy']['2048']:.2f}, eff. rank {emb['effective_rank']:.0f}); FP16 factors break even at r*={emb['breakeven']['F16']['r_used']} (error {emb['breakeven']['F16']['rel_err']:.2f}), Q8_0 at r*={emb['breakeven']['Q8_0']['r_used']} (error {emb['breakeven']['Q8_0']['rel_err']:.2f}). Does not affect per-token bandwidth at all (get_rows), only file size / RSS if mmapped-and-touched. | **NO** (and irrelevant to tok/s). |")
W('')
W('Bottom line: every tensor class is numerically full-rank with a flat spectrum (the row-normalized pure {-1,0,1} patterns - the thing a TQ2_0 factor pair would have to reproduce, since scales are stored anyway - are within a few % of an i.i.d. random matrix: FFN E@2048 0.75 vs 0.71 random, attention 0.94 vs 0.89). The only ranks that reduce bytes (r < r*) sit at 25-90% relative Frobenius error, versus a 0% baseline (TQ2_0 stores the trained ternary weights exactly). SVD factor pairs cannot reduce bytes/token or RAM for this model without wrecking it. Drop the SVD line of work.\n')
W('## Method\n')
W('- Dequantize with `gguf.quants.dequantize` (numpy shape = [out, in]; verified per-row scale: 1 unique f16 scale per row for TQ2_0). Singular values from the float64 Gram matrix (W^T W or W W^T, accumulated over 4096-row/column chunks) + `np.linalg.eigvalsh`; validated against `np.linalg.svd(compute_uv=False)` on blk.0.attn_q and blk.0.ffn_gate (energy@1024 agrees to 1e-6, singular values median rel. diff 2e-6, tail max 2e-4). Chosen because gesdd on 16384x4096 f32 peaked at 1.6 GB RSS and the vocab matrices would need ~2.5 GB.')
W('- Peak RSS: layer passes 1.75 GB (transient temporaries in the wide 4096x16384 ffn_down case - a float64 copy and the ternary-stat arrays; both row-chunked in the script afterwards, so future runs peak ~1.0 GB), vocab 1.3 GB, recon 1.4 GB. Wall: 25 layer matrices 6 min (x2 passes), vocab 40 s, recon 30 s. All heavy runs under `with_lock.py --tag svd` (waited 8-9 min per lock acquisition behind bench/quantize/perplexity jobs).')
W('- energy_r = sum_{i<=r} s_i^2 / sum s_i^2; rel. Frobenius error = sqrt(1-energy_r) (this is the FP32-optimal error - any quantized factor is worse). Bytes: dense = out*in*bpw/8; factor pair = (out+in)*r*bpw_f/8; break-even r* = out*in*bpw_dense/((out+in)*bpw_f) -> FFN 3276 (TQ2_0 factors) / 422 (F16); attn 2048 / 264; output.weight vs Q6_K 6.5625 bpw: 1591 (F16) / 2995 (Q8_0); token_embd vs Q4_K 4.5 bpw: 1091 / 2053.')
W('- Random baseline: Marchenko-Pastur top-r energy for an i.i.d. matrix of the same shape (`mp_baseline.py`), i.e. what "no structure at all" looks like.')
W('- Ternary stats from sign(W / row scale). Zero fraction 0.28-0.43 (rises with depth), +1/-1 balanced to 3 decimals; no all-zero rows or columns.\n')
W('## Compact tables\n')
W('Per-class means (energy captured at rank r; MP = i.i.d. random matrix of the same shape):\n')
RK = ['256', '512', '1024', '1536', '2048', '2560', '3072', '3584']
W('| class | ' + ' | '.join(f'E@{r}' for r in RK) + ' | stable rank | eff. rank | err @ r*(TQ2_0 factors) | err @ r*(F16 factors) |')
W('|---|' + '---|' * (len(RK) + 4))
for name, ds, key in [('FFN (15)', ffn, '16384x4096'), ('ATTN (10)', att, '4096x4096')]:
    W(f'| {name} | ' + ' | '.join(f"{mean(ds, lambda d: d['energy'][r]):.3f}" for r in RK) + f" | {mean(ds, lambda d: d['stable_rank']):.0f} | {mean(ds, lambda d: d['effective_rank']):.0f} | {mean(ds, lambda d: d['breakeven']['TQ2_0']['rel_err']):.3f} | {mean(ds, lambda d: d['breakeven']['F16']['rel_err']):.3f} |")
    W(f'| *MP random {key}* | ' + ' | '.join(f"{mp[key]['energy'][r]:.3f}" for r in RK) + f" | {mp[key]['stable_rank']:.0f} | - | - | - |")
W(f'| output.weight | ' + ' | '.join(f"{out_w['energy'][r]:.3f}" for r in RK) + f" | {out_w['stable_rank']:.0f} | {out_w['effective_rank']:.0f} | F16 r*={out_w['breakeven']['F16']['r_used']}: {out_w['breakeven']['F16']['rel_err']:.3f} | Q8_0 r*={out_w['breakeven']['Q8_0']['r_used']}: {out_w['breakeven']['Q8_0']['rel_err']:.3f} |")
W(f'| token_embd.weight | ' + ' | '.join(f"{emb['energy'][r]:.3f}" for r in RK) + f" | {emb['stable_rank']:.0f} | {emb['effective_rank']:.0f} | F16 r*={emb['breakeven']['F16']['r_used']}: {emb['breakeven']['F16']['rel_err']:.3f} | Q8_0 r*={emb['breakeven']['Q8_0']['r_used']}: {emb['breakeven']['Q8_0']['rel_err']:.3f} |")
W(f"| *MP random 73448x4096* | " + ' | '.join(f"{mp['73448x4096']['energy'][r]:.3f}" for r in RK) + f" | {mp['73448x4096']['stable_rank']:.0f} | - | - | - |")
W('')
W('Per-tensor (rel. Frobenius error at selected ranks; err@r*: FP32-optimal error at the TQ2_0-factor break-even rank; nrank: # s.v. > 1e-3 s_max):\n')
W('| tensor | err@1024 | err@2048 | err@3072 | err@r*(TQ2) | err@r*(F16) | stable rk | eff. rk | nrank | zero frac |')
W('|---|---|---|---|---|---|---|---|---|---|')
for d in layers:
    W(f"| {short(d['name'])} | {d['rel_err']['1024']:.3f} | {d['rel_err']['2048']:.3f} | {d['rel_err']['3072']:.3f} | {d['breakeven']['TQ2_0']['rel_err']:.3f} | {d['breakeven']['F16']['rel_err']:.3f} | {d['stable_rank']:.0f} | {d['effective_rank']:.0f} | {d['num_rank_1e-3']} | {d['frac_zero']:.3f} |")
W('')
W(f"Sanity check, `blk.16.ffn_down` [4096x16384] reconstructed at rank r (factors from the exact SVD; ternary = per-row absmean BitNet quantizer on A=U*sqrt(S), B=sqrt(S)*Vt; 'TQ2_0-style' = llama.cpp `quantize_row_tq2_0` per-256-block absmax, which is what `llama-quantize` would actually do to FP factors):\n")
W('| r | bytes vs dense TQ2_0 (TQ2_0 factors / F16 factors) | FP32 factors | FP16 factors | ternary absmean (both) | ternary A only | ternary B only | TQ2_0-style ternary |')
W('|---|---|---|---|---|---|---|---|')
for rk, x in recon['ranks'].items():
    W(f"| {rk} | {x['bytes_ratio_TQ2_0']:.2f}x / {x['bytes_ratio_F16']:.2f}x | {x['err_fp32_factors']:.3f} | {x['err_fp16_factors']:.3f} | {x['err_tern_absmean_balanced']:.3f} (US/Vt split {x['err_tern_absmean_US_Vt']:.3f}) | {x['err_tern_absmean_A_only']:.3f} | {x['err_tern_absmean_B_only']:.3f} | {x['err_tern_tq2_0_balanced']:.3f} |")
W('')
W('Reading: FP16 factors reproduce the SVD-optimal error exactly (0.47 @ 2048) but cost 4.85x the bytes; ternary factors at r=2048 (0.62x bytes) lose 80% of the matrix norm; the llama.cpp TQ2_0 quantizer applied to real-valued factors zeroes ~85% of entries (absmax/2 threshold) and gives error > 1. Ternarizing either factor alone already costs 0.57-0.67. There is no rank at which a ternary factor pair is both smaller and recognisable.\n')
if rown:
    W('Row-normalized (pure {-1,0,1} pattern, i.e. what a TQ2_0 factor pair must reproduce since scales are free) - per-class means:\n')
    W('| class | ' + ' | '.join(f'E@{r}' for r in RK) + ' | stable rank | eff. rank | err @ r*(TQ2_0) |')
    W('|---|' + '---|' * (len(RK) + 3))
    for name, c in [('FFN', 'FFN'), ('ATTN', 'ATTN')]:
        ds = [d for d in rown if cls(d['name']) == c]
        if ds: W(f'| {name} row-normalized ({len(ds)}) | ' + ' | '.join(f"{mean(ds, lambda d: d['energy'][r]):.3f}" for r in RK) + f" | {mean(ds, lambda d: d['stable_rank']):.0f} | {mean(ds, lambda d: d['effective_rank']):.0f} | {mean(ds, lambda d: d['breakeven']['TQ2_0']['rel_err']):.3f} |")
    d0 = next((d for d in rown if d['name'] == 'blk.0.attn_output.weight'), None)
    if d0: W(f"| L0.attn_output row-normalized | " + ' | '.join(f"{d0['energy'][r]:.3f}" for r in RK) + f" | {d0['stable_rank']:.0f} | {d0['effective_rank']:.0f} | {d0['breakeven']['TQ2_0']['rel_err']:.3f} |")
    W('')
else:
    W('Row-normalized pass (pure ternary pattern spectra, `run_rownorm.sh`): queued behind other lock holders at report time; results land in `layers_rownorm.jsonl` and can be folded in with `make_report.py`/`write_report.py`. It can only make the verdict stronger (removing the scale outliers flattens the spectra further, cf. blk.0.attn_output).\n')
W('## Files\n')
W('Scripts (`/Users/timii/Developer/Muta/muta-iq/opt/scripts/svd/`): `svd_spectrum.py` (spectra/energy/ternary stats/break-even, `--row-normalize`), `recon_check.py` (rank-r reconstruction with FP16/ternary factors), `mp_baseline.py` (Marchenko-Pastur baseline), `probe_timing.py` (svd-vs-Gram validation), `run_all.sh` / `run_rownorm.sh` (locked runs), `make_report.py` (full tables), `write_report.py` (this file).')
W('Results (`/Users/timii/Developer/Muta/muta-iq/opt/results/svd/`): `layers.jsonl`, `vocab.jsonl`, `recon.json`, `mp_baseline.json`, `sv/*.npy` (all singular values), `run_all.log`, `svd_report_tables.md` (full per-tensor energy/error tables), this report.\n')
W('## Appendix: full tables\n')
tabs = open(f'{R}/svd_report_tables.md').read().split('\n', 6)[-1]   # drop the header/method lines
W(tabs)
open(f'{R}/svd_report.md', 'w').write('\n'.join(L))
print('wrote', f'{R}/svd_report.md', len(' '.join(L).split()), 'words')
