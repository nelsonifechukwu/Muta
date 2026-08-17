#!/usr/bin/env python3
"""Verify a vocab-pruned GGUF against its source: identical tokenization (as piece strings) on
English/math text, identical special ids by string, and byte-identical kept rows of the
embedding/output tensors. Usage: verify_prune.py src.gguf pruned.gguf [textfile ...]"""
import sys
sys.path.insert(0, "/Users/timii/Developer/Muta/muta-iq/opt/llama.cpp/gguf-py")
import numpy as np
from gguf import GGUFReader
from llama_cpp import Llama

src, dst = sys.argv[1], sys.argv[2]
texts = []
for p in sys.argv[3:]:
    texts.append(open(p, encoding="utf-8", errors="replace").read()[:60000])
texts += [
    "A trader buys 24 identical crates for 18000 naira and sells them at a 25% profit. What is the selling price of one crate? Show your working.",
    "Solve for x: 3x^2 - 12x + 9 = 0. Then compute the derivative of f(x) = x^3 e^x and ∫ x^2 e^x dx.",
    "Newton's second law F = ma; g ≈ 9.81 m/s². Photosynthesis: 6CO₂ + 6H₂O → C₆H₁₂O₆ + 6O₂. Écoute, señor — naïve café résumé; Ọmọ Yorùbá, Hausa, Kiswahili.",
    "def f(n):\n    return 1 if n < 2 else n * f(n-1)  # factorial\nprint(f(10))  <|im_start|>user\nhi<|im_end|>\n",
]

ra, rb = GGUFReader(src), GGUFReader(dst)
def toks(r):
    f = r.fields["tokenizer.ggml.tokens"]; return [bytes(f.parts[i]) for i in f.data]
ta, tb = toks(ra), toks(rb)
print(f"vocab {len(ta)} -> {len(tb)}")
# kept-row byte identity
b_to_a = {t: i for i, t in enumerate(ta)}
map_b = np.array([b_to_a[t] for t in tb])
assert len(set(map_b.tolist())) == len(tb), "duplicate token strings — cannot verify by string"
for name in ("token_embd.weight", "output.weight"):
    A = next(t for t in ra.tensors if t.name == name).data
    B = next(t for t in rb.tensors if t.name == name).data
    assert B.shape[0] == len(tb) and A.shape[1] == B.shape[1], (A.shape, B.shape)
    # spot-check every 97th row plus first/last 100 rows for speed, then a full check
    idx = np.r_[np.arange(0, len(tb), 97), np.arange(100), np.arange(len(tb)-100, len(tb))]
    assert all(np.array_equal(A[map_b[i]], B[i]) for i in idx), name
    assert np.array_equal(A[map_b], B), name + " full"
    print(f"  {name}: kept rows byte-identical ({B.shape[0]} rows x {B.shape[1]} B)")
# special ids by string
for k in ("bos_token_id", "eos_token_id", "unknown_token_id", "padding_token_id"):
    key = "tokenizer.ggml." + k
    if key in ra.fields:
        ia = int(ra.fields[key].parts[ra.fields[key].data[0]][0]); ib = int(rb.fields[key].parts[rb.fields[key].data[0]][0])
        assert ta[ia] == tb[ib], (k, ta[ia], tb[ib]); print(f"  {k}: {ia}->{ib} {ta[ia]!r} ok")
# tokenization identity
la = Llama(model_path=src, vocab_only=True, verbose=False)
lb = Llama(model_path=dst, vocab_only=True, verbose=False)
n_tok = 0; n_cjk = 0
for text in texts:
    ida = la.tokenize(text.encode("utf-8"), add_bos=True, special=True)
    idb = lb.tokenize(text.encode("utf-8"), add_bos=True, special=True)
    pa = [ta[i] for i in ida]; pb = [tb[i] for i in idb]
    n_tok += len(ida)
    if pa != pb:
        # find first divergence
        k = next(i for i in range(min(len(pa), len(pb))) if pa[i] != pb[i]) if any(x != y for x, y in zip(pa, pb)) else min(len(pa), len(pb))
        print("  MISMATCH at", k, pa[max(0,k-3):k+3], pb[max(0,k-3):k+3]); sys.exit(1)
    # sanity: does the original tokenization use any dropped piece?
    kept = set(tb)
    n_cjk += sum(1 for p in pa if p not in kept)
print(f"  tokenization identical on {n_tok} tokens across {len(texts)} texts; dropped-piece uses in source tokenization: {n_cjk}")
# round trip detokenize on pruned
s = "The derivative of x^2 is 2x. ∫ x dx = x²/2 + C. Ọmọ."
print("  roundtrip:", lb.detokenize(lb.tokenize(s.encode())).decode("utf-8", "replace") == s)
print("VERIFY OK")
