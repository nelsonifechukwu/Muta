# Benchmarking on a target-box-shaped container

**Why this exists.** RESULTS.md admits three hardware contexts, and only `x86 target` —
the competition-class box — will ever be report-grade. Nobody doing daily development has
that box. This tooling builds the closest stand-in an arbitrary dev host can produce, and
— for everything a container *cannot* imitate — measures the gap and staples it to the
numbers, so a reader can map a run onto the real machine instead of being silently misled.

Numbers from this harness are labeled **`x86 container-proxy (<host CPU>)`**. They are
never report-grade; they are the best pre-target signal we can manufacture.

## The target, row by row

The deploy box: **i5 10th–12th gen / Ryzen 5 3000–5000 (6C/12T), 8 GB DDR4, integrated
graphics only, 256 GB SSD, Ubuntu 22.04 — no GPU.**

| Target property | What the container does about it | Fidelity |
|---|---|---|
| Ubuntu 22.04 | The backend image *is* Ubuntu 22.04 userland (glibc 2.35, libgomp) for both the engine build and the run | exact |
| ISA: AVX2+FMA+F16C, **no AVX-512** | Enforced at image build (`GGML_AVX2=ON GGML_AVX512=OFF GGML_NATIVE=OFF` + the objdump assertion) — the binary is target-ISA even on an AVX-512 host | exact |
| No GPU / iGPU only | CPU-only engine build; no `/dev` passthrough; `--n-gpu-layers 0` throughout | exact |
| 6 cores / 12 threads | cpuset of 6 physical cores + their SMT siblings, all on **one socket** and numerically first (on hybrid Intel that means P-cores; offline/nosmt CPUs are skipped); falls back to a cfs **quota** of the same logical count where the runtime can't pin (quota throttles instead of pinning — the report records which one it got, and the granted CPU list is in the artifact) | good / fair |
| 8 GB DDR4 (capacity) | cgroup: 8 GiB hard, **swap denied**. Deliberately harsher than the real box (which would swap to SSD): an over-budget config must fail loudly here, not limp | good |
| DDR4 (bandwidth) | **Not emulable.** Decode on CPU is bandwidth-bound, and a cloud/dev host bus can be 2–4× a dual-channel DDR4 desktop. The harness measures memcpy GiB/s in-container and prints the decode ceiling it implies (see below) | measured, not imitated |
| CPU clocks (~2.9–4.4 GHz boost) | Not emulable; `/proc/cpuinfo` model + the bandwidth probe are recorded so the delta is visible | measured, not imitated |
| 256 GB SSD | Irrelevant to steady-state decode; model load time depends on the host disk and is not scored | n/a |

## Running it

```
make bench-target                                   # build image, fingerprint + bandwidth + llama-bench
scripts/bench_target_box.sh --skip-build            # reuse the existing image
scripts/bench_target_box.sh -- --sweep WINNER       # add the server-level probe (metric of record)
scripts/bench_target_box.sh --cores 6 --mem 8g -- --reps 5
```

Everything after `--` goes to `python -m bench.target_box` inside the container
(`--threads`, `--reps`, `--pp/--tg`, `--hash`, `--sweep`, `--no-bench`). Results land in
`bench/.artifacts/target-box/*.json`; the model must already be provisioned
(`run.sh` does it, or `scripts/fetch_models.py --only core`). A missing model degrades
the run to fingerprint + bandwidth instead of erroring — those are still worth recording.

The stages, and what each is for:

- **fingerprint** — CPU model/ISA/affinity, the cgroup caps actually granted (cpuset vs
  quota, memory+swap), OS, engine version, model presence/provenance. This block is what
  makes a JSON artifact interpretable a month later.
- **bandwidth** — numpy memcpy over a 512 MiB buffer. Every decoded token streams the
  full Q4_K_M weight file (~2.55 GiB) through the bus once, so
  `ceiling ≈ 2×memcpy ÷ weights` is a first-order **upper bound** on decode tok/s
  (memcpy counts a byte of read + a byte of write per byte copied; a weight stream is
  reads). KV/activation traffic and sampling overhead only subtract. Use it to normalize
  across hosts: a dual-channel DDR4-3200 desktop peaks at 51.2 GB/s on paper and
  typically measures 12–18 GiB/s memcpy.
- **llama-bench** — pp512/tg128 at physical-core and all-thread counts, 3 reps, tree-RSS
  sampled with `bench.sampler` (the scored methodology). Engine-only, standard shape —
  the number to compare against llama.cpp results elsewhere.
- **sweep** (optional) — named `bench.native_sweep` configs driven over
  `/v1/chat/completions` inside the container: engine-*reported* warm decode, prefill,
  reuse — the RESULTS.md metric of record, minus gateway/db (for the full product path
  use `bench/profile.py` against a running stack).

## Reading the numbers honestly

- A container-proxy run on a fast host **overstates** the target box in proportion to
  the bandwidth ratio (decode) and clock ratio (prefill). Divide by the measured
  bandwidth ratio for a decode estimate before anyone gets excited.
- On the **quota fallback** the engine sees every host CPU and gets throttled to a
  budget: barrier-synchronized decode can stall harder than on real cores. Treat decode
  from quota runs as a lower bound; cpuset runs are the trustworthy shape.
- Peak tree-RSS under the 8 GiB cap *is* transferable — allocation behaviour doesn't
  depend on bus speed. This is the number the cap exists for: if a config OOMs here, it
  does not ship.
- Speculation verdicts ("draft on/off") measured on a proxy carry over only
  directionally; the 07-31/08-01 rule stands — the call is parked until the real
  `x86 target` box speaks.
