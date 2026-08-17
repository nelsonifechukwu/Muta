# adtc-audit-bench — measure what the Gate-2 audit binary will actually do

The profiler image builds llama.cpp **b10175 with AVX/AVX2/FMA/F16C off** (SSE4.2 only) on
debian bookworm and runs `llama-bench -m <gguf> -p 512 -n 128 -ngl 0`. On that binary only Q4_0
has a hand-written SIMD kernel; TQ2_0 and every k-/i-quant run generic C (see
`../research/r4_x86_kernels.md`). Nothing on an M1 can measure that; a free x86 GitHub runner can.

This workflow rebuilds that exact binary in a `debian:bookworm-slim` container and benches a
list of GGUFs in parallel jobs (default threads = physical cores, plus a `-t 4` run), printing
tg tok/s and max RSS per model.

## Run it (≈10 min setup, ≈20 min results; free)
```
cd muta-iq/opt/audit-bench
git init && git add -A && git commit -m "audit bench"
gh repo create <your-user>/adtc-audit-bench --public --source=. --push
gh secret set HF_TOKEN --body "$(cat ~/.cache/huggingface/token)"   # only needed for private HF files
gh workflow run bench.yml -f models='[
 {"name":"bitcpm4-8b-tq2_0","url":"https://huggingface.co/openbmb/BitCPM-CANN-8B-gguf/resolve/main/bitcpm4-8b-tq2_0.gguf"},
 {"name":"bitcpm4-3b-tq2_0","url":"https://huggingface.co/openbmb/BitCPM-CANN-3B-gguf/resolve/main/bitcpm4-3b-tq2_0.gguf"},
 {"name":"bitcpm4-1b-tq2_0","url":"https://huggingface.co/openbmb/BitCPM-CANN-1B-gguf/resolve/main/bitcpm4-1b-tq2_0.gguf"},
 {"name":"qwen3-1.7b-q4_0","url":"https://huggingface.co/bartowski/Qwen_Qwen3-1.7B-GGUF/resolve/main/Qwen_Qwen3-1.7B-Q4_0.gguf"},
 {"name":"qwen3-1.7b-q4_k_m","url":"https://huggingface.co/bartowski/Qwen_Qwen3-1.7B-GGUF/resolve/main/Qwen_Qwen3-1.7B-Q4_K_M.gguf"},
 {"name":"gemma-3-1b-q4_0","url":"https://huggingface.co/bartowski/google_gemma-3-1b-it-GGUF/resolve/main/google_gemma-3-1b-it-Q4_0.gguf"}
]'
gh run watch
```
Add your own pruned/requantized GGUFs by uploading them to a (private) HF repo
(`hf upload <user>/muta-adtc-candidates file.gguf`) and appending `{name,url}` entries.
The `Q4_0` vs `Q4_K_M` pair for the same model directly tests the kernel-ranking prediction.
