#!/usr/bin/env python
"""Singular-value spectrum + low-rank energy tables for GGUF tensors (memory-frugal).

Method: singular values via the Gram matrix G = W^T W (or W W^T, whichever is 4096x4096),
accumulated in float64 over row/col chunks, then np.linalg.eigvalsh -> s_i = sqrt(lambda_i).
Validated against np.linalg.svd(compute_uv=False) on blk.0.attn_q / blk.0.ffn_gate
(probe_timing.py): energy@1024 agrees to 1e-6, singular values median rel diff ~2e-6.
Chosen over gesdd because np.linalg.svd on a 16384x4096 f32 peaked at 1.6 GB RSS and the
73448x4096 vocab matrices would need ~2.5 GB; the chunked Gram never holds more than one
64 MB chunk + the 128 MB Gram.

Usage: svd_spectrum.py --out results.jsonl --svdir sv/ tensor_name [tensor_name ...]
"""
import argparse, json, os, sys, time, resource
import numpy as np
from gguf import GGUFReader
from gguf.quants import dequantize

MODEL = '/Users/timii/Developer/Muta/muta-iq/model/bitcpm4-8b-tq2_0.gguf'
RANKS = [256, 512, 1024, 1536, 2048, 2560, 3072, 3584, 4096]
BPW = {'TQ2_0': 2.0625, 'Q6_K': 6.5625, 'Q4_K': 4.5, 'F16': 16.0, 'Q8_0': 8.5}
CHUNK_ROWS = 4096

def rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20

def dequant_rows(t, i, j):
    return dequantize(np.ascontiguousarray(t.data[i:j]), t.tensor_type)  # -> float32 [j-i, in]

ROW_NORMALIZE = False   # --row-normalize: divide each row by max|row| (its per-row ternary scale) -> pure {-1,0,1} pattern

def analyze(t):
    name, qtype = t.name, t.tensor_type.name
    n_out, n_in = int(t.data.shape[0]), int(t.shape[0])   # numpy rows = GGUF ne1 = out; ne0 = in
    t0 = time.time()
    small = min(n_out, n_in)
    G = np.zeros((small, small), dtype=np.float64)
    fro2 = 0.0
    n_zero = 0; n_pos = 0; n_neg = 0; zero_rows = 0
    col_nonzero = np.zeros(n_in, dtype=bool)
    if n_out < n_in:
        # wide (ffn_down): dequantize row-chunks into one preallocated f32 [out,in] to keep transients small
        Wfull = np.empty((n_out, n_in), dtype=np.float32)
        for i in range(0, n_out, 1024):
            Wfull[i:i + 1024] = dequant_rows(t, i, min(i + 1024, n_out))
    for i in range(0, n_out, CHUNK_ROWS):
        Wc = Wfull if n_out < n_in else dequant_rows(t, i, min(i + CHUNK_ROWS, n_out))   # [c, in] float32
        if ROW_NORMALIZE:
            rs = np.abs(Wc).max(axis=1, keepdims=True); rs[rs == 0] = 1.0
            Wc /= rs; del rs
        for j in range(0, Wc.shape[1], 4096):   # Frobenius norm^2 in f64, chunked (small temporaries)
            C = Wc[:, j:j + 4096].astype(np.float64).ravel(); fro2 += float(C @ C); del C
        # ternary stats (TQ2_0 only): per-row scale = max|row| (one scale per row in this model)
        if qtype == 'TQ2_0':
            for i0 in range(0, Wc.shape[0], 512):   # row-chunked so the wide (4096x16384) case has small temporaries
                Cc = Wc[i0:i0 + 512]
                s = np.abs(Cc).max(axis=1, keepdims=True); s[s == 0] = 1.0
                Q = np.rint(Cc / s).astype(np.int8)
                n_zero += int((Q == 0).sum()); n_pos += int((Q == 1).sum()); n_neg += int((Q == -1).sum())
                zero_rows += int((Q == 0).all(axis=1).sum()); col_nonzero |= (Q != 0).any(axis=0)
                del Q, s
        else:
            n_zero += int((Wc == 0).sum())
        if n_out >= n_in:   # tall: G = W^T W  [in,in], one row-chunk at a time in f64
            Wc64 = Wc.astype(np.float64); del Wc
            G += Wc64.T @ Wc64
            del Wc64
        else:               # wide (ffn_down, out=4096 <= CHUNK_ROWS so this is the whole W): G = W W^T [out,out]
            assert n_out <= CHUNK_ROWS, 'wide matrix with >CHUNK_ROWS rows not supported'
            for j in range(0, n_in, CHUNK_ROWS):   # column chunks cast to f64 one at a time
                Cc = np.ascontiguousarray(Wc[:, j:j + CHUNK_ROWS]).astype(np.float64)
                G += Cc @ Cc.T
                del Cc
            del Wc, Wfull
    ev = np.linalg.eigvalsh(G)[::-1]; del G
    ev = np.clip(ev, 0.0, None)
    s = np.sqrt(ev)
    total = float(ev.sum())
    cum = np.cumsum(ev)
    energy = {r: float(cum[min(r, len(ev)) - 1] / total) for r in RANKS}
    err = {r: float(np.sqrt(max(0.0, 1.0 - e))) for r, e in energy.items()}
    p = ev / total; p = p[p > 0]
    erank = float(np.exp(-np.sum(p * np.log(p))))
    srank = float(total / ev[0])
    nrank_1e3 = int(np.sum(s > 1e-3 * s[0])); nrank_1e2 = int(np.sum(s > 1e-2 * s[0]))
    dense_bpw = BPW[qtype]
    n = n_out * n_in
    def breakeven(fbpw):
        rstar = n * dense_bpw / ((n_out + n_in) * fbpw)
        rr = int(min(max(np.floor(rstar), 1), len(ev)))
        e = float(cum[rr - 1] / total)
        return {'r_star': float(rstar), 'r_used': rr, 'energy': e, 'rel_err': float(np.sqrt(max(0.0, 1 - e)))}
    be = {k: breakeven(BPW[k]) for k in ('TQ2_0', 'F16', 'Q8_0')}
    def bytes_factor(r, fbpw): return (n_out + n_in) * r * fbpw / 8
    rec = {
        'name': name, 'qtype': qtype, 'row_normalized': ROW_NORMALIZE, 'out': n_out, 'in': n_in, 'dense_bytes': n * dense_bpw / 8,
        'fro_norm': float(np.sqrt(fro2)), 's_max': float(s[0]), 's_min': float(s[-1]),
        'stable_rank': srank, 'effective_rank': erank, 'num_rank_1e-3': nrank_1e3, 'num_rank_1e-2': nrank_1e2,
        'energy': energy, 'rel_err': err,
        'bytes_factor_TQ2_0': {r: bytes_factor(r, BPW['TQ2_0']) for r in RANKS},
        'bytes_factor_F16': {r: bytes_factor(r, BPW['F16']) for r in RANKS},
        'bytes_factor_Q8_0': {r: bytes_factor(r, BPW['Q8_0']) for r in RANKS},
        'breakeven': be, 'seconds': time.time() - t0, 'maxrss_mb': rss_mb(),
    }
    if qtype == 'TQ2_0':
        rec.update({'frac_zero': n_zero / n, 'frac_pos': n_pos / n, 'frac_neg': n_neg / n,
                    'zero_rows': zero_rows, 'zero_cols': int((~col_nonzero).sum())})
    else:
        rec.update({'frac_zero': n_zero / n})
    return rec, s

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True); ap.add_argument('--svdir', required=True)
    ap.add_argument('--row-normalize', action='store_true')
    ap.add_argument('names', nargs='+')
    a = ap.parse_args()
    global ROW_NORMALIZE; ROW_NORMALIZE = a.row_normalize
    os.makedirs(a.svdir, exist_ok=True)
    r = GGUFReader(MODEL); tm = {t.name: t for t in r.tensors}
    for name in a.names:
        rec, s = analyze(tm[name])
        np.save(os.path.join(a.svdir, name + '.npy'), s.astype(np.float32))
        with open(a.out, 'a') as f: f.write(json.dumps(rec) + '\n')
        e = rec['energy']
        print(f"{name:26s} {rec['qtype']:6s} [{rec['out']}x{rec['in']}] srank={rec['stable_rank']:.1f} erank={rec['effective_rank']:.0f} "
              f"nrank1e-3={rec['num_rank_1e-3']} E@1024={e[1024]:.3f} E@2048={e[2048]:.3f} E@3072={e[3072]:.3f} "
              f"zero={rec.get('frac_zero',0):.3f} be_TQ2={rec['breakeven']['TQ2_0']['r_used']}(err {rec['breakeven']['TQ2_0']['rel_err']:.3f}) "
              f"{rec['seconds']:.0f}s rss={rec['maxrss_mb']:.0f}MB", flush=True)

if __name__ == '__main__':
    main()
