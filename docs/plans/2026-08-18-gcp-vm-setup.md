# GCP target VM setup

**Date:** 2026-08-18  
**Host:** `muta-vm` (`muta-adtc`, `us-west1-b`)  
**Purpose:** Reproducible x86-64 environment for Muta integration checks and
target-proxy experiments.

## Guardrails

- Keep Ubuntu 22.04, 4 vCPUs, 8 GB RAM, and swap disabled.
- Use the repository's pinned Ubuntu 22.04 / AVX2-only Docker build. Never use
  `-march=native` or enable AVX-512.
- Clone the repository into `~/Muta`; do not create a parallel `~/adtc` tree.
- Record the exact Git commit, Docker version, CPU topology, and memory state before
  treating any measurement as usable.
- Label this GCP Xeon as `x86 cloud proxy`, not the physical ADTC laptop. Its CPU,
  cache, and memory bandwidth differ from the competition target.
- Do not expose the raw backend port. The Compose file binds it to loopback; only the
  frontend port is published.

## Procedure

1. Install Git, Git LFS, Docker Engine with Compose v2, basic diagnostics, and build
   utilities from Ubuntu packages.
2. Enable Docker at boot and grant the login user Docker access.
3. Clone `https://github.com/iitimii/Muta.git` into `~/Muta` and verify the checkout
   matches `origin/main`.
4. Run `./run.sh plan`, validate Compose configuration, and build the pinned backend
   image. The image build is the AVX2/ELF safety check.
5. Provision the pinned, hash-verified model roster through `run.sh` and start the
   stack.
6. Verify `/v1/ready`, the frontend, container health, no swap, and engine provenance.
7. Capture a pre-experiment fingerprint. Do not run or record optimization experiments
   until this setup passes.

## Acceptance criteria

- `docker compose version` works without `sudo` in a fresh SSH session.
- `~/Muta` is on the expected `origin/main` commit with no local changes.
- The backend image contains x86-64 `llama-server` built with the repository's pinned
  reference and AVX-512 assertion.
- All required model files pass the repository's hash verification.
- `docker compose ps` reports healthy services and `/v1/ready` returns
  `"ready": true`.
- Host swap remains 0 B and there is adequate disk headroom for images, weights, and
  benchmark artifacts.

## Execution outcome

**Status:** Operational setup passed; reproducibility/package acceptance remains blocked
by the issues below.

The VM is operational at commit `7f4ab4a22f9e1b17f3c445e1aaeed26ea9cbd279`.
Docker 29.1.3, Compose 2.40.3, and Buildx 0.30.1 are installed. The AVX2-only
`llama.cpp` `b10035` build passed the ELF and forbidden-AVX-512 assertions, all three
services are healthy, `/v1/ready` reports every dependency ready, and `/v1/health`
reports the exact Git SHA. The required roster occupies 3.9 GB on disk; the host has
86 GB free and no swap. A public-API inference smoke returned "2 plus 2 equals 4."
with thinking disabled in 84.29 seconds.

The environment label is **`x86 cloud proxy (GCP n2-custom-4-8192, 2C/4T)`**.
It is not report-grade target hardware: the cloud Xeon exposes AVX-512, has only two
physical cores, exposes no temperature sensors, and does not reproduce the target
laptop's DDR4 bandwidth or thermals.

The setup fingerprint is stored on the VM at
`~/Muta/bench/.artifacts/gcp-vm/setup-20260818T165500Z.txt`.

### Open acceptance gaps found by adversarial review

- The provisioning run rewrites tracked manifest/pin metadata, so the VM checkout is
  dirty. The rewritten manifest accurately names the served IQ4_XS core, but retains
  seven bake-off candidates as `fetched` even though their optional files are absent;
  `verify_models.py` therefore reports seven false missing-file failures.
- The refreshed draft and embed license captures contain Hugging Face HTML rather than
  license text. The verifier checks only file presence and falsely accepts them.
- The resolved Ubuntu base digest differs from `runtime/VERSIONS.md`; the Dockerfile's
  floating Ubuntu/nginx tags and unchecksummed frontend assets prevent byte-for-byte
  rebuild reproducibility.
- Compose sets a 7 GiB memory limit but leaves Docker's swap allowance at another 7 GiB.
  Host swap is disabled today, but the container would be allowed to swap if that host
  posture changed.
- `GET /v1/models` returns 404 despite the run documentation advertising it.
- Port 3000 remains blocked by the GCP firewall. Keep it that way and use an SSH tunnel;
  do not create a public unauthenticated frontend rule.
