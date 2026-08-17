"""Timing/precision probe: np.linalg.svd(compute_uv=False) vs Gram+eigvalsh on real tensors."""
import numpy as np, time, sys, resource
from gguf import GGUFReader
from gguf.quants import dequantize
P='/Users/timii/Developer/Muta/muta-iq/model/bitcpm4-8b-tq2_0.gguf'
r = GGUFReader(P); tm={t.name:t for t in r.tensors}
def rss(): return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/2**20
for name in sys.argv[1:]:
    t=tm[name]; W=dequantize(t.data,t.tensor_type); print(name, W.shape, W.dtype, flush=True)
    t0=time.time(); s=np.linalg.svd(W, full_matrices=False, compute_uv=False); t1=time.time()
    print(f'  svd  {t1-t0:.1f}s  s[0]={s[0]:.4f} s[-1]={s[-1]:.4f} maxrss={rss():.0f}MB', flush=True)
    t0=time.time()
    if W.shape[0]>=W.shape[1]: G=(W.T@W)
    else: G=(W@W.T)
    ev=np.linalg.eigvalsh(G.astype(np.float64))[::-1]; ev=np.clip(ev,0,None); s2=np.sqrt(ev); t1=time.time()
    print(f'  gram {t1-t0:.1f}s  s[0]={s2[0]:.4f} s[-1]={s2[-1]:.4f} maxrss={rss():.0f}MB', flush=True)
    rel=np.abs(s2-s)/s; print(f'  max rel diff {rel.max():.2e}  median {np.median(rel):.2e}; energy@1024 svd {np.sum(s[:1024]**2)/np.sum(s**2):.6f} gram {np.sum(ev[:1024])/np.sum(ev):.6f}')
    del W,G,s,s2,ev
