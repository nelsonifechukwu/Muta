"""Marchenko-Pastur baseline: energy captured by top-r singular values of an i.i.d. random m x n matrix
(no structure at all). Numeric quadrature on the MP density; no heavy compute."""
import numpy as np, json, sys
def mp_energy(m, n, ranks):
    small, big = min(m, n), max(m, n); c = small / big
    lo, hi = (1 - np.sqrt(c))**2, (1 + np.sqrt(c))**2
    lam = np.linspace(lo, hi, 200001)[1:-1]
    f = np.sqrt((hi - lam) * (lam - lo)) / (2 * np.pi * c * lam)   # density of eigenvalues of (1/big) W^T W
    f /= np.trapezoid(f, lam)
    # cumulative from the top
    cdf_top = np.cumsum((f * np.gradient(lam))[::-1])[::-1]        # fraction of eigenvalues >= lam
    e_top = np.cumsum((f * lam * np.gradient(lam))[::-1])[::-1]; e_top /= e_top[0]
    out = {}
    for r in ranks:
        frac = min(r / small, 1.0)
        idx = np.searchsorted(-cdf_top, -frac)   # first index where cdf_top <= frac
        idx = min(idx, len(lam) - 1)
        out[r] = float(e_top[idx]) if frac < 1 else 1.0
    stable = 1.0 / hi   # ||W||_F^2/(s_max^2) normalized: mean eig / max eig * small
    return out, small / hi
ranks = [256, 512, 1024, 1536, 2048, 2560, 3072, 3584, 4096]
res = {}
for shape in [(4096, 4096), (16384, 4096), (73448, 4096)]:
    e, srank = mp_energy(*shape, ranks)
    res[f'{shape[0]}x{shape[1]}'] = {'energy': e, 'stable_rank': srank}
    print(shape, 'stable rank', round(srank), ' '.join(f'E@{r}={v:.3f}' for r, v in e.items()))
json.dump(res, open('/Users/timii/Developer/Muta/muta-iq/opt/results/svd/mp_baseline.json', 'w'), indent=1)
