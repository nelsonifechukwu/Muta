# Local model selection

Muta's native Linux UI exposes a fixed local model registry in the sidebar. It is an
experiment/control surface, not a claim that the biggest model is the best competition entry.

## Included choices

| id | role | exact artifact | benchmark evidence |
|---|---|---|---|
| `muta-tutor-qwen3-1.7b-q4_0` | default / recommended | 974,198,528 bytes; SHA-256 `a98ce36e9ff97e5271d90cbc429c952f99a5a966bb0195ae74661b4c054fd63e` | ARC-Easy 0.70; composite winner because pure Q4_0 retains the audit kernel's fast path |
| `bitcpm4-8b-tq2_0-envocab` | accuracy experiment | 2,208,746,208 bytes; SHA-256 `069621f168502215839fb82db3afe35beb8e5350fb6cbf8523aa1eea6bee237d` | ARC-Easy 0.84; generic/audit proxy 3.92 tok/s, so its overall score loses despite the accuracy lead |
| `cloud` | future backend seam | no local artifact | visibly disabled while offline |

The values come from `RESULTS.md` and `muta-iq/opt/results/bakeoff.tsv`. These are selection
evidence, not report-grade target-box measurements.

## Provisioning the two local models

Run once while online for the recommended default:

```bash
./muta-iq/download_model.sh
```

The script downloads the pinned bartowski Qwen3-1.7B Q4_0 source, verifies it, rebuilds the
recorded pure-Q4_0 tied-head artifact, bakes the tutor metadata, and accepts only the catalog
hash. It does not depend on the removed historical derived-model repository.

For the optional BitCPM model, run:

```bash
./muta-iq/fetch_bitcpm.sh
```

The script downloads the official OpenBMB GGUF at revision
`78a2fa992bd0326b081abf3dc8ba97c33e6250f1`, verifies source SHA-256
`b72d23bf549e90bdfb161a4ed217ba26b9eb3efd19363716e9bfcd265370ac91`,
applies the recorded 73,448 → 44,416 English-vocabulary pruning, and refuses to install the
result unless the final hash matches the catalog. Both pipelines fetch and verify the exact
llama.cpp b10360 tooling revision they need when no local checkout exists. Subsequent model
selection is fully offline.

## Runtime behaviour

`GET /v1/models` lists the fixed registry. `POST /v1/models/select` accepts only a catalog
`model_id`; it never accepts a path. Before activation the manager checks byte size and SHA-256.
It then stops the current engine and starts the selected model on the same loopback port. The
gateway and SQLite process stay alive, so conversations persist. Only one `llama-server` is
resident at a time. A loader failure restores the previous model before returning an error.

Selection is enabled only by the native Linux launcher and only for requests whose socket peer
is loopback. The laptop operator can use the local browser (or an SSH-forwarded browser), while
LAN classroom clients may chat but cannot globally restart the shared engine.

A model change interrupts an in-flight generation. The UI therefore disables the selector
during a reply and disables new generation controls while the replacement is loading.

## GCP cloud-proxy smoke (2026-08-18)

On `muta-vm` (`n2-custom-4-8192`, 2 physical cores / 4 SMT threads), the exact BitCPM artifact
loaded in 0.97 s under the pinned b10035/602f828 AVX2 engine. A fixed gateway prompt completed
correctly at 12.24 prompt tok/s and 6.64 decode tok/s (45 decoded tokens). Switching there and
back preserved gateway PID 86561 and SQLite inode 1806427; one `llama-server` PID remained after
each transition. This is a functional cloud-proxy smoke, not a competition target result.
