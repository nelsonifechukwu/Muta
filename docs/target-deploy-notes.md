# Target-box OS/launch tuning — verdicts on the community low-RAM playbook

**Status:** 2026-08-05. Evaluates the tricks circulating in llama.cpp discussion #21136 /
the 0ut0flin3 low-RAM gist against this project's measurements and the ADTC scoring
path. The gist's context is a 2-core Core2Duo (pre-AVX, SSE4.1) with DDR2 under swap
pressure — instructive precisely because the ADTC audit image is ALSO an SSE-only build
(its world validates our Q4_0 kernel-map reasoning) — but its RAM regime is not ours:
the tutor's engine RSS is capped by design and the scored llama-bench run has no memory
pressure at all. Each trick gets a verdict for (a) the scored path, (b) the product demo.

| Trick (gist) | Scored path | Product (8 GB demo box) |
|---|---|---|
| `-O3 -march=native -flto` build | Self-report build must MATCH THE AUDIT (SSE-only b10175 — docs/audit-parity.md); a native build inflates numbers the audit can't reproduce → flag/fail. LTO measured ≤1–2% upstream. | Container build stays fixed-ISA AVX2 (illegal-instruction safety on the CPU field); LTO harmless, optional. |
| `vm.swappiness=10` | Irrelevant — audit runs a ~3 GB model under a 7.5 GB cap, no pressure. | **Adopt.** Cheap insurance against model-page swap while the browser/Postgres run alongside. |
| memlock unlimited + `--mlock` | **Anti-scoring.** Locking makes every weight page unreclaimably resident (RSS = max), and the profiler's fixed invocation never passes `--mlock` anyway. | **Rejected by measurement** (RESULTS.md 2026-08-01: no footprint win, unstable decode) — and on an 8 GB box locked pages can't be reclaimed under pressure, which converts graceful degradation into an OOM kill: the one failure mode that is an automatic disqualification. The gist's win comes from DDR2-era swap thrash we don't have. |
| CPU governor `performance` | **Adopted** in the self-report launch posture (audit-parity.md): ~3–10% and, more importantly, tighter rep-to-rep variance. | Adopt for the demo session. |
| `vm.vfs_cache_pressure=50`, `vm.dirty_ratio=10`, `vm.dirty_background_ratio=5` | Irrelevant (read-only workload, no pressure). | Plausible small win (biases reclaim away from the model's page cache); unmeasured, low-risk — apply with the swappiness sysctl. |
| `nice -n -10` (+ `ionice -c1`) | **Adopted** (audit-parity.md): protects the 5-rep average from ambient scheduling; ionice only matters when faulting weights from disk. | Fine for the engine process. |
| `-t` = physical cores | llama-bench's default already resolves to physical/P cores on bare-metal Linux — no flag needed (and none can be passed). | `RuntimeConfig` already leaves threads to the engine default on Linux (a documented decision, runtime/config.py). |
| `--ctx-size 2048` | llama-bench fixes its own context. | Already the deployed default. |
| Lightweight distro (Mint/MX/AntiX) | Competition pins Ubuntu 22.04. | N/A. |

## The one-liner for the demo box (safe adopts only)

```bash
sudo tee /etc/sysctl.d/99-muta.conf >/dev/null <<'EOF'
vm.swappiness=10
vm.vfs_cache_pressure=50
vm.dirty_ratio=10
vm.dirty_background_ratio=5
EOF
sudo sysctl -p /etc/sysctl.d/99-muta.conf
sudo cpupower frequency-set -g performance   # or the systemd unit from the gist
```

Do NOT raise memlock limits and do NOT add `--mlock` to any launch script — see the
table. The engine's RAM posture of record is mmap + capped state + (per-server)
`--no-repack`, which keeps weights evictable on purpose: under pressure the kernel
drops clean weight pages and the tutor slows down instead of dying.
