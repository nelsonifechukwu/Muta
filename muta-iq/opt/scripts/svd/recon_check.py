#!/usr/bin/env python
"""Sanity check: rank-r reconstruction of one TQ2_0 matrix with (a) FP32 factors, (b) FP16 factors,
(c) BitNet-style ternary factors (per-row absmean scale, q=clamp(round(x/s),-1,1)*s),
(d) TQ2_0-style ternary factors (llama.cpp quantize_row_tq2_0: per-256-block absmax scale).
Reports relative Frobenius error ||W - A_q B_q||_F / ||W||_F against the dense ternary original W.

Factors: W = U S V^T (via eigh of W W^T in float64 -> U, S; V^T = S^-1 U^T W), A = U_r S_r [out,r], B = V_r^T [r,in].
Also tries the balanced split A = U_r sqrt(S_r), B = sqrt(S_r) V_r^T (better for quantizing both factors).
Memory: W f32 (268 MB) + Gram/U f64 (128 MB each) + B (r x in f32) + one reconstruction (268 MB) ~< 1.1 GB.
Usage: recon_check.py --name blk.16.ffn_down.weight --rank 2048 [--rank 3072 ...] --out recon.json
"""
import argparse, json, time, resource
import numpy as np
from gguf import GGUFReader
from gguf.quants import dequantize
MODEL = '/Users/timii/Developer/Muta/muta-iq/model/bitcpm4-8b-tq2_0.gguf'

def rss_mb(): return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20

def tern_absmean_rows(X, rows=512):
    # row-chunked, in-place-ish to keep temporaries small (B can be 3072x16384 f32 = 200 MB)
    out = np.empty_like(X, dtype=np.float32)
    for i in range(0, X.shape[0], rows):
        C = X[i:i + rows]
        s = np.abs(C).mean(axis=1, keepdims=True); s[s == 0] = 1.0
        Q = np.rint(C / s); np.clip(Q, -1, 1, out=Q); Q *= s
        out[i:i + rows] = Q
    return out

def tern_tq2_blocks(X, bs=256, rows=512):
    # llama.cpp TQ2_0: per block of 256 along the row, d = max|x|, q = round(x/d) in {-1,0,1}, stored as f16 d
    r, c = X.shape; assert c % bs == 0
    out = np.empty_like(X, dtype=np.float32)
    for i in range(0, r, rows):
        Xb = X[i:i + rows].reshape(-1, c // bs, bs)
        d = np.abs(Xb).max(axis=2, keepdims=True).astype(np.float16).astype(np.float32); d[d == 0] = 1.0
        q = np.rint(Xb / d); np.clip(q, -1, 1, out=q); q *= d
        out[i:i + rows] = q.reshape(-1, c)
    return out

def rel_err(W, A, B, fro):
    # ||W - A B||_F computed in column chunks to avoid a second full-size copy
    acc = 0.0
    for j in range(0, W.shape[1], 2048):
        R = A @ B[:, j:j + 2048]; R -= W[:, j:j + 2048]
        R = R.astype(np.float64).ravel(); acc += float(R @ R); del R
    return float(np.sqrt(acc) / fro)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--name', required=True)
    ap.add_argument('--rank', type=int, action='append', required=True); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    r = GGUFReader(MODEL); t = {x.name: x for x in r.tensors}[a.name]
    n_out, n_in = int(t.data.shape[0]), int(t.shape[0])
    W = np.empty((n_out, n_in), dtype=np.float32)
    for i in range(0, n_out, 1024):
        W[i:i + 1024] = dequantize(np.ascontiguousarray(t.data[i:i + 1024]), t.tensor_type)
    fro = float(np.sqrt(sum(float(np.sum(W[:, j:j + 4096].astype(np.float64) ** 2)) for j in range(0, n_in, 4096))))
    print(f'{a.name} [{n_out}x{n_in}] ||W||_F={fro:.3f} rss={rss_mb():.0f}MB', flush=True)
    t0 = time.time()
    if n_out <= n_in:
        G = np.zeros((n_out, n_out), dtype=np.float64)
        for j in range(0, n_in, 4096):
            C = W[:, j:j + 4096].astype(np.float64); G += C @ C.T; del C
        ev, U = np.linalg.eigh(G); del G
        ev = ev[::-1]; U = U[:, ::-1]; s = np.sqrt(np.clip(ev, 0, None))
    else:
        raise SystemExit('tall case not needed here')
    print(f'eigh done {time.time()-t0:.1f}s s[0]={s[0]:.3f} s[{n_out-1}]={s[-1]:.4f} rss={rss_mb():.0f}MB', flush=True)
    results = {'name': a.name, 'out': n_out, 'in': n_in, 'fro': fro, 'ranks': {}}
    for rk in a.rank:
        Ur = U[:, :rk].astype(np.float32)                       # [out, r]
        sr = s[:rk].astype(np.float32)
        Bt = Ur.T @ W; Bt /= sr[:, None]                        # V_r^T [r, in]  (f32, in place)
        A = Ur * sr[None, :]                                    # U_r S_r [out, r]
        e_svd = float(np.sqrt(max(0.0, 1.0 - float(np.sum(s[:rk] ** 2)) / fro ** 2)))
        res = {'energy': 1 - e_svd ** 2, 'err_svd_theory': e_svd}
        res['err_fp32_factors'] = rel_err(W, A, Bt, fro)
        res['err_fp16_factors'] = rel_err(W, A.astype(np.float16).astype(np.float32), Bt.astype(np.float16).astype(np.float32), fro)
        # unbalanced split (A=U S, B=V^T) ternary
        res['err_tern_absmean_US_Vt'] = rel_err(W, tern_absmean_rows(A), tern_absmean_rows(Bt), fro)
        res['err_tern_tq2_0_US_Vt'] = rel_err(W, tern_tq2_blocks(A), tern_tq2_blocks(Bt), fro)
        # balanced split A=U sqrt(S), B=sqrt(S) V^T
        sq = np.sqrt(sr)
        A2 = Ur * sq[None, :]; B2 = Bt * sq[:, None]
        del A, Bt   # keep only the balanced pair from here on (A=U S, B=Vt results already recorded)
        res['err_tern_absmean_balanced'] = rel_err(W, tern_absmean_rows(A2), tern_absmean_rows(B2), fro)
        res['err_tern_tq2_0_balanced'] = rel_err(W, tern_tq2_blocks(A2), tern_tq2_blocks(B2), fro)
        # ternary A only / B only (balanced) to see which factor hurts
        res['err_tern_absmean_A_only'] = rel_err(W, tern_absmean_rows(A2), B2, fro)
        res['err_tern_absmean_B_only'] = rel_err(W, A2, tern_absmean_rows(B2), fro)
        # bytes
        dense = n_out * n_in * 2.0625 / 8
        res['bytes_dense_TQ2_0'] = dense
        res['bytes_factors_TQ2_0'] = (n_out + n_in) * rk * 2.0625 / 8
        res['bytes_factors_F16'] = (n_out + n_in) * rk * 16 / 8
        res['bytes_ratio_TQ2_0'] = res['bytes_factors_TQ2_0'] / dense
        res['bytes_ratio_F16'] = res['bytes_factors_F16'] / dense
        results['ranks'][rk] = res
        print(f'rank {rk}: ' + ' '.join(f'{k}={v:.4f}' for k, v in res.items()), f'rss={rss_mb():.0f}MB', flush=True)
        del Ur, A2, B2
    json.dump(results, open(a.out, 'w'), indent=1)

if __name__ == '__main__':
    main()
