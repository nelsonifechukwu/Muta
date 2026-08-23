# Local model selection

Muta's native Linux UI exposes a fixed local model registry in the sidebar. It is an
experiment/control surface, not a claim that the biggest model is the best competition entry.

## Included choices

| id | role | image input | exact artifact | benchmark evidence |
|---|---|---|---|---|
| `qwen3.5-4b-iq4_xs` | shipped Compose/full tutor | yes, with its verified 4B projector | 2,477,053,088 bytes; SHA-256 `658a9e7e406deb06d0179755e3c14f6a82915a4be4962a2f92a64d948d2e572f` | resident full tutor; target performance measurement remains separate |
| `muta-tutor-qwen3.5-0.8b-q4_0` | default / risk-adjusted recommendation | yes, with its verified 0.8B projector | 507,148,832 bytes; SHA-256 `c96df4ef6d9416bea6a35866751cb6cf02e20ec6ce28b20980d66c90604d5d7b` | direct Scalar: ARC-Easy-50 0.64 and 12.63 tok/s; the matched 500-item check leads the two finalists at 0.588 |
| `qwen3.5-0.8b-q4_k_m` | competition-safe fallback | yes, with the same verified 0.8B-family projector | 532,517,120 bytes; SHA-256 `bd258782e35f7f458f8aced1adc053e6e92e89bc735ba3be89d38a06121dc517` | capacity fallback; target score measurement remains separate |
| `qwen2.5-1.5b-instruct-q4_k_m` | vector-path candidate | no | 1,117,320,736 bytes; SHA-256 `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e` | ARC-Easy-500 0.718; 5.69 Scalar and 17.23 vector decode tok/s on the GCP proxy |
| `qwen3-0.6b-math-expert-q4_k_m` | raw-score alternative | no | 396,706,176 bytes; SHA-256 `7f64c2e3bbd5c6fa570f49631cad5527ebd4acd7fcaf014963152027b2dae9a1` | direct Scalar: ARC-Easy-50 0.68 and 12.72 tok/s; highest current fixed-15 Scalar and AVX2 total |
| `muta-tutor-qwen3-1.7b-q4_0` | previous recommendation | no | 974,198,528 bytes; SHA-256 `a98ce36e9ff97e5271d90cbc429c952f99a5a966bb0195ae74661b4c054fd63e` | retained for comparison with the earlier campaign |
| `bitcpm4-8b-tq2_0-envocab` | accuracy experiment | no | 2,208,746,208 bytes; SHA-256 `069621f168502215839fb82db3afe35beb8e5350fb6cbf8523aa1eea6bee237d` | ARC-Easy 0.84; generic/audit proxy 3.92 tok/s, so its overall score loses despite the accuracy lead |
| `cloud` | future backend seam | unavailable offline | no local artifact | visibly disabled while offline |

The current finalist values come from the direct participant-profiler campaign and the matched
portable AVX2 comparison in `RESULTS.md`. They remain GCP proxy evidence rather than measurements
from the physical competition laptop.

## Provisioning the local models

Run once while online for the recommended default:

```bash
./muta-iq/download_model.sh
```

This downloads the pinned Qwen3.5 0.8B Q4_0 source and its paired F16 image projector, verifies
both, bakes the tutor metadata, and accepts only the catalog hashes. The projector is
204,987,232 bytes with SHA-256
`56e4c6cfe73b0c82e3e82bc518d7591997e61d81f723fc41a586f4fa69ea2453`.

For the Qwen2.5 1.5B vector-path candidate:

```bash
./muta-iq/fetch_qwen25.sh
```

The script downloads the exact official Qwen Q4_K_M artifact from a pinned source revision and
accepts it only when both its byte size and SHA-256 match the runtime catalog. This is the base
instruction model used in the benchmark; Muta supplies its tutor prompt at runtime.

For the Math-Expert alternative:

```bash
./muta-iq/fetch_math_expert.sh
```

The script downloads the exact pinned Q4_K_M artifact and accepts it only when both its byte size
and SHA-256 match the runtime catalog.

For the optional BitCPM model, run:

```bash
./muta-iq/fetch_bitcpm.sh
```

The script downloads the official OpenBMB GGUF at revision
`78a2fa992bd0326b081abf3dc8ba97c33e6250f1`, verifies source SHA-256
`b72d23bf549e90bdfb161a4ed217ba26b9eb3efd19363716e9bfcd265370ac91`,
applies the recorded 73,448 → 44,416 English-vocabulary pruning, and refuses to install the
result unless the final hash matches the catalog. The derived-model pipelines fetch and verify
the exact llama.cpp b10360 tooling revision they need when no local checkout exists. Subsequent
model selection is fully offline.

## Runtime behaviour

`GET /v1/models` lists the fixed registry. `POST /v1/models/select` accepts only a catalog
`model_id`; it never accepts a path. Before activation the manager checks byte size and SHA-256.
It then stops the current engine and starts the selected model on the same loopback port. The
gateway and SQLite process stay alive, so conversations persist. Only one `llama-server` is
resident at a time. A loader failure restores the previous model before returning an error.

Selection is enabled only by the native Linux launcher and only for requests whose socket peer
is loopback. The laptop operator can use the local browser (or an SSH-forwarded browser), while
LAN classroom clients may chat but cannot globally restart the shared engine.

Native Linux mode also gives loopback browser sessions one persistent random operator identity.
The identity is stored in `data/operator-student-id`, not browser storage, so changing an SSH
tunnel's local port does not create a separate conversation list. Non-loopback clients keep their
per-browser identities. This is an interim local-operator policy; the planned account layer will
replace it when individual users are introduced.

A model change never interrupts an in-flight generation. The UI disables the selector during a
reply and while replacement is loading. Merely uploading or previewing an image is not a
generation and does not block switching. Image history is capability-checked again after the
generation/model-replacement barrier: switching a conversation to a text-only model produces a
specific recovery message instead of sending stale visual content to that model.

## GCP cloud-proxy smoke (2026-08-18)

On `muta-vm` (`n2-custom-4-8192`, 2 physical cores / 4 SMT threads), the exact BitCPM artifact
loaded in 0.97 s under the pinned b10035/602f828 AVX2 engine. A fixed gateway prompt completed
correctly at 12.24 prompt tok/s and 6.64 decode tok/s (45 decoded tokens). Switching there and
back preserved gateway PID 86561 and SQLite inode 1806427; one `llama-server` PID remained after
each transition. This is a functional cloud-proxy smoke, not a competition target result.
