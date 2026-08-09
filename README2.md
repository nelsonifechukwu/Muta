

# Benchmark
- Do a thorough benchmark review that accompanies your selection of a model (showing a graph of the optimal point for acc, perf, and ram) 

# Hack
- Add a small 50m sub-model to hack tps.

# Optimise Time to First Token (TTFT)
- This would improve the reading experience
- **Done (2026-08-08): TinyStories-1M as the TTFT model.** Runs in-process as NumPy
  GPT-Neo (`runtime/ttft.py`) — llama.cpp cannot load it (GPT-Neo ≠ GPT-NeoX, no GGUF
  exists, vocab 50257 vs 248320 so it can't be a draft either). 1.65 ms to first chunk,
  662 tok/s, 15 MB. Streamed as a labelled `preamble` event that is never persisted and
  never counted in `ttft_s`. Off by default — the weights have **no declared licence**,
  and the text is toddler-story English, so it is a placeholder, not an answer.
  → `docs/ttft-preamble.md`, RESULTS.md 2026-08-08 §-1.
- Still open, and these are the reductions rather than the mask: prewarm each mode's
  system-prompt prefix into the engine cache at boot (first turn becomes a cache hit);
  A/B `n_ubatch` 128 → higher on x86.

# Report style
- I love the quote style before every chapter in [this](https://www.mlmi.eng.cam.ac.uk/files/2021-2022_dissertations/attention-based-sheaf-neural-networks.pdf)
- Quote [this](https://www.arjunvirk.com/inference-engineering.html#:~:text=Optimization%20is%20not%20%22make%20the%20number%20go%20up.%22%20It%27s%20picking%20the%20least%2Dbad%20tradeoff%20among%20things%20that%20fight%20each%20other)
    
