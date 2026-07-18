# Build flags — why AVX2, and never AVX-512

**ROADMAP deliverable: Tue 14 Jul, `[Lane A]`.** The decision and, more importantly, the
reasoning — so nobody "optimizes" it back later.

## The decision

```
-DGGML_NATIVE=OFF -DGGML_AVX2=ON -DGGML_AVX512=OFF -DGGML_F16C=ON -DGGML_FMA=ON
```

Implemented in [`docker/dev.Dockerfile`](../docker/dev.Dockerfile) stage 1. Pinned llama.cpp
version in [`runtime/VERSIONS.md`](../runtime/VERSIONS.md).

## Why never AVX-512

**An illegal-instruction fault is a hard failure — disqualification, not a deduction.** That
asymmetry is the whole argument. AVX-512 might buy some throughput on machines that have it;
on machines that don't, the binary doesn't run at all. We are optimizing a score, and a score
of zero cannot be recovered by any amount of tok/s.

Much of the target field simply lacks it:

| Target-class CPU | AVX-512 |
|---|---|
| AMD Ryzen 5000 (Zen 3) | **Absent** |
| Intel 12th-gen consumer (Alder Lake) | **Fused off** — present on die, disabled |
| Intel 11th-gen (Rocket Lake) | Present |
| AMD Ryzen 7000+ (Zen 4) | Present |

The competition targets "the hardware Africa actually has" — mid- and low-end commodity
laptops. Zen 3 and Alder Lake are squarely that. Building for AVX-512 would fault on a large
share of the plausible field.

AVX2 is universal on anything remotely modern (Intel since Haswell 2013, AMD since Excavator
2015), so it costs us nothing to assume.

## Why `GGML_NATIVE=OFF`

`GGML_NATIVE=ON` (the default) compiles for **the machine doing the build**. That is a trap
here: the build host is a CI runner or a laptop, not the target. It would silently bake in
whatever ISA the builder happened to have — including AVX-512 on a Zen 4 build box — and the
failure would only appear on the target, at the worst possible moment.

`OFF` makes the ISA an explicit decision rather than an accident of hardware.

## Why `LLAMA_CURL=OFF`

Not an ISA decision, but it belongs with them: it drops llama.cpp's `-hf` model puller and the
libcurl dependency. **The deploy target is offline**, so a network model-fetch path is dead
weight and a dependency we'd have to carry. `runtime/models.py` provisions weights itself and
always resolves to a local path.

## The assertion (why this is enforced, not documented)

A comment saying "never AVX-512" prevents nothing. `docker/dev.Dockerfile` stage 1 **fails the
build** if the rule is broken:

```dockerfile
file build/bin/llama-server | grep -q 'ELF 64-bit LSB.*x86-64'
objdump -d build/bin/llama-server | grep -qE '\s(vpxord|vpternlogd|kmovw|vpbroadcastmw2d)\s' && exit 1
```

Those four mnemonics are EVEX/AVX-512-only; GCC cannot emit them when targeting AVX2. Checking
on the target box (9–11 Aug) would be too late — the whole point of building `linux/amd64` from
day one is that the binary is *already* the shipping artifact. Verified in-image:
`GNU 11.4.0 for Linux x86_64`.

## What this does NOT decide

Runtime **thread count** is a separate decision and a scoring one, not a performance one — more
threads stop helping once memory bandwidth saturates but keep producing heat, and >85 °C is a
flat −10. See `MUTA_RT_N_THREADS` in [`runtime/config.py`](../runtime/config.py).

Caveat worth knowing: [`docs/rules-digest.md`](rules-digest.md) establishes that the audit may
run on a cloud VM with **no thermal sensor**, in which case the penalty may be unreachable and
the thread cap could be costing throughput for nothing. Unresolved; do not act on it yet.

## Rejected alternatives

- **`-march=native`** — same trap as `GGML_NATIVE=ON`, more explicit about it.
- **AVX-512 with runtime dispatch** — llama.cpp can select kernels at runtime, but the build
  must still *contain* AVX-512 code, and a mis-detected dispatch is an illegal instruction. The
  upside is throughput on a minority of the field; the downside is a zero. Declined on
  asymmetry, not on performance.
- **Multiple binaries per ISA** — plausible (ship AVX2 + AVX-512, pick at launch), but it
  doubles the build matrix and the flash-drive payload to chase points on hardware the
  competition explicitly says it isn't targeting.
