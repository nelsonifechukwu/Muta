# Linux-native runtime and benchmark plan

**Date:** 2026-08-18
**Status:** Complete
**Scope:** Make the GCP Ubuntu x86-64 VM a Docker-free experiment runner after a one-time,
auditable extraction from the existing backend image. The current Compose stack remains the
control.

## Why this work exists

`./run.sh --native` currently means “Apple-silicon development”: it downloads a macOS arm64
engine, then keeps PostgreSQL and nginx in Docker. On the Ubuntu VM the verified AVX2/no-AVX512
engine exists only inside `muta-backend:latest`, so there is no repeatable native Linux launch
or artifact identity. That makes native engine measurements unnecessarily awkward and makes a
purported Docker-free full-stack run depend on two containers.

The target architecture in `ROADMAP.md` A.1/A.2 is two product processes on Linux:
`llama-server` plus the mounted FastAPI gateway. Persistence must travel with the portable
directory. PostgreSQL is retained for the Compose control, but the native path will use the
roadmap's SQLite topology so a database daemon is not hidden outside the measured process tree.

## Decisions and invariants

1. Docker is a **build/extraction boundary**, not an experiment runtime. The extraction command
   may use the existing backend image once; engine and gateway experiments after that do not.
2. Export both `llama-server` and `llama-bench` from the backend image, plus the complete offline
   browser bundle from the frontend image. Refuse anything that is
   not Linux x86-64 ELF, does not identify as pinned llama.cpp b10035/602f828, or contains the
   forbidden AVX-512 instruction signatures used by the Docker build assertion.
3. Write an adjacent JSON manifest containing image identity, Muta git SHA, engine version,
   binary SHA-256 values, ELF descriptions, extraction time, and verification results. Native
   experiment artifacts can therefore identify the exact engine they used.
4. Do not copy model weights. They remain host files under `models/` and are hash-verified by the
   existing model tooling.
5. Compose continues to use PostgreSQL unchanged. `ConversationStore` selects SQLite only for a
   `sqlite:` URL; its public method contract remains identical and is exercised by the same
   behavioral test suite.
6. Native Linux defaults to `sqlite:///data/muta.sqlite3`, loopback-only HTTP, no model download,
   CPU-only engine flags from `RuntimeConfig`, speculation off, and no explicit thread pin so
   llama.cpp chooses physical cores.
7. The GCP VM is labelled `x86 cloud proxy (GCP n2-custom-4-8192, 2C/4T)`. Its AVX-512-capable
   Xeon, unknown memory bandwidth, and unmeasured thermals make results exploratory, never
   report-grade.
8. The native benchmark command records a hardware/runtime fingerprint and uses the extracted
   `llama-bench`; it must not silently fall back to a binary on `PATH`.

## Implementation sequence

1. Add a full SQLite implementation of the current persistence API, plus store selection from
   the configured URL and SQLite-aware readiness checks. Keep existing Postgres behavior and
   tests intact.
2. Add a one-time Linux engine exporter that extracts from `muta-backend:latest`, verifies the
   pin/ELF/ISA, installs atomically into `runtime/build/bin`, and writes a provenance manifest.
3. Add Linux-native launch commands for engine-only and full two-process product mode. The full
   mode is one gateway parent supervising one `llama-server` child and uses SQLite; FastAPI also
   serves the checked-in offline UI without nginx.
4. Add a native GCP benchmark wrapper around `bench.target_box` that enforces the extracted
   binaries, writes into a separate `gcp-cloud-proxy` artifact directory, fingerprints the host,
   and applies the required non-report-grade label.
5. Update `run.sh`, Make targets, and operator documentation with the exact control/extract/run/
   benchmark workflow. Preserve Apple-native behavior.
6. Test SQLite parity, shell behavior, command construction, readiness, and the existing suite;
   lint changed Python and shell-check scripts where available.
7. Deploy the change to the VM without disturbing the Compose control, export the already-built
   engine, prove Docker-free engine and gateway smokes, and capture a pre-experiment artifact.
8. Run an adversarial review in a fresh context and fix any acceptance failures before declaring
   the VM ready for experiments.

## Acceptance checks

- Compose control remains healthy and still uses PostgreSQL.
- `runtime/build/bin/{llama-server,llama-bench}` are verified x86-64 ELF binaries at b10035 /
  602f828, with SHA-256 values in the manifest and no forbidden AVX-512 signatures.
- After stopping Compose, a native engine smoke succeeds while no Muta container is running.
- Native full-stack `/v1/ready` reports gateway, inference, and SQLite all ready; a fixed chat
  request persists and can be read back after restart.
- The native UI is reachable from the gateway process without nginx.
- The benchmark artifact includes exact git SHA, engine identity, model identity, CPU topology,
  host swap state, and the cloud-proxy/non-report-grade label.
- Native launch does not depend on Docker, PostgreSQL, or network access once artifacts and Python
  dependencies are present.

## Completion evidence

Acceptance was run on `muta-vm` as an **x86 cloud proxy (GCP n2-custom-4-8192,
2C/4T)**, not as a report-grade target:

- source identity matched locally and remotely at
  `7f4ab4a22f9e+tree.5e2e3acbf84d`;
- manifest schema 2 records backend image `sha256:ede746…`, frontend image
  `sha256:d608af…`, 90 hashed UI files, resolved dynamic-library dependencies, and
  the two binary hashes;
- `llama-server` SHA-256 is `43ed5a…0124a` and `llama-bench` is
  `f0ef958…08a53`; both identify as 602f828/b10035 and pass the AVX-512 signature
  rejection check;
- native `/v1/ready` reported gateway, inference, and SQLite ready with
  `online:false`; `/v1/health` returned the exact source identity; every browser
  asset referenced by `ui/dist/index.html` returned HTTP 200;
- the final bounded engine smoke produced 5.78 tok/s decode and 8.63 tok/s prompt
  evaluation, then SIGTERM removed the engine without an orphan;
- Compose/native mutual exclusion and occupied-port rejection were exercised;
  the historical M2 `WINNER` sweep was rejected because its six-thread pin exceeds
  the VM's four allowed CPUs;
- the final pre-experiment fingerprint is
  `bench/.artifacts/gcp-cloud-proxy/gcp-n2-cloud-proxy-20260818T174901Z.json`;
- the full local suite and focused VM suite passed, and the PostgreSQL-backed Docker
  control was restored with all three services healthy.

The fresh adversarial review found eight acceptance gaps (native UI packaging,
host-specific sweep pins, process contamination, benchmark exit status, build identity,
dynamic dependencies, SQLite migrations, and absolute model paths). Each is covered by
the final implementation and regression checks above.
