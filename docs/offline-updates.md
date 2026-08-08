# Offline signed updates for the classroom fleet

**Status:** 2026-08-08. Operator guide. Companion scripts: `scripts/sign_release.sh`,
`scripts/verify_release.sh`.

## Why the current `run.sh update` is wrong for a fleet

`./run.sh update` today does an **online `git pull` + on-device `docker compose build`**.
On a deployed classroom laptop that is three separate problems:

1. **It needs the network.** The boxes are offline (`update_stack` even `die`s if it can't
   reach the internet). The README promises *offline signed-patch* updates, not this.
2. **It recompiles llama.cpp on the device.** The backend image build compiles the pinned
   engine (`b10035`, `GGML_AVX2=ON`) from source — tens of minutes of 100% CPU on a
   low-end classroom laptop, per box, times the whole fleet. The build even *asserts* the
   x86-64/AVX2 discipline; that belongs on a build machine, not in a classroom.
3. **It is unverified and non-atomic.** A `git pull` pulls whatever the remote has; a
   half-finished build leaves a box in an unknown state with no rollback.

The right model for a fleet with no network is the one this repo already uses for **models**
(`models/pins.lock.json`: pin exact bytes, sha256-verify **twice**): build once on a trusted
machine, sign, carry the bytes on a flash drive, and **verify before applying** on each box.
Compile zero times in the classroom.

## The release: prebuilt images + a manifest, never source

A release is a directory of **prebuilt image tarballs** (`docker save`) plus the models
provenance manifest — everything a box needs to move to a new version without building
anything. Images are `linux/amd64` and already carry the AVX2-only engine, so they load and
run as-is on the Ubuntu 22.04 x86 target.

```
muta-release-2026-08-08/
  muta-backend.tar          # docker save of the backend image (engine + gateway)
  muta-frontend.tar         # docker save of the nginx frontend image
  models-manifest.json      # models/pins.lock.json for this release (provenance)
  VERSION.txt               # human tag, e.g. 2026-08-08 / git sha
  SHA256SUMS                # written by sign_release.sh
  SHA256SUMS.sig            # written by sign_release.sh (or .minisig)
```

Models weights are big and rarely change; ship them in the release only when a pin actually
moved. Most patches are just the two image tarballs.

## Build + sign (once, on a trusted machine — offline is fine)

```bash
# 1. Build the pinned images (this is the slow, compile-once step — do it HERE, not on a laptop)
docker compose build

# 2. Save the images to tarballs. Names come from `docker compose images` / `docker images`.
mkdir -p muta-release-2026-08-08
docker save muta-backend:latest  -o muta-release-2026-08-08/muta-backend.tar
docker save muta-frontend:latest -o muta-release-2026-08-08/muta-frontend.tar
cp models/pins.lock.json         muta-release-2026-08-08/models-manifest.json
date -u +%Y-%m-%dT%H:%M:%SZ    > muta-release-2026-08-08/VERSION.txt

# 3. Hash every file and sign the manifest
./scripts/sign_release.sh muta-release-2026-08-08
```

`sign_release.sh` writes `SHA256SUMS` (a hash per file) and a **detached signature over that
manifest**. It uses `minisign` if present, else `openssl` with an Ed25519 key it generates
into `keys/` on first use. Signing the manifest, and the manifest committing to every file's
bytes, is the "verify twice" model: one signature authenticates the list, the list
authenticates the payload.

**The keys:**
- The **private** key (`keys/muta_release_ed25519.key`) stays on this trusted machine. It
  never rides the flash drive and never touches a target. Anyone with it can forge a release
  every box will trust. The script writes it `0600` and gitignores it.
- The **public** key (`keys/muta_release_ed25519.pub`) is the fleet's trust anchor. Install
  it **once** on each target, out of band — the same way you install `rootCA.pem` for TLS.
  It is safe to commit and safe to publish. `verify_release.sh` takes it as an explicit
  argument; it must be the pre-shared key, **not** a copy pulled from the release (a release
  can carry its own signature but never its own trust anchor).

Copy the release directory to the flash drive. Do **not** copy the private key.

## Verify + apply (on each target laptop)

Always verify first. **Never apply an update that does not verify.**

```bash
# 1. Verify signature AND every file hash against the PRE-SHARED public key
./scripts/verify_release.sh --pubkey /path/to/muta_release_ed25519.pub /media/usb/muta-release-2026-08-08
#   exit 0 → "✓ RELEASE VERIFIED … Safe to apply."
#   exit 1 → bad signature   · exit 2 → hash/manifest mismatch or extra/missing files
#   On any non-zero exit: STOP. Do not load anything.
```

`verify_release.sh` checks two independent things and fails closed on either: (1) the
signature over `SHA256SUMS` is valid for your public key, and (2) every sha256 matches on
disk, with no unexpected or missing files. A single altered byte, a swapped manifest, an
injected file, or a wrong key all abort with a clear message and a non-zero exit.

Only after a clean verify:

```bash
REL=/media/usb/muta-release-2026-08-08

# 2. Tag the CURRENT images as a rollback point BEFORE overwriting them
docker tag muta-backend:latest  muta-backend:previous
docker tag muta-frontend:latest muta-frontend:previous

# 3. Load the new images from the verified tarballs
docker load -i "$REL/muta-backend.tar"
docker load -i "$REL/muta-frontend.tar"

# 4. If the release moved a model pin, refresh weights from its manifest; otherwise skip.
#    (Weights are volume-mounted, never baked — swapping images does not touch ./models.)

# 5. Restart onto the new images (conversations survive in the muta-pgdata volume)
docker compose up -d --wait
```

The `db` container (`postgres:16-alpine`, pinned by digest) is unaffected; only the two
built images move. Student data lives in the `muta-pgdata` volume and is never in a release.

## Rollback

If the new version misbehaves, go back to the images you tagged in step 2:

```bash
docker tag muta-backend:previous  muta-backend:latest
docker tag muta-frontend:previous muta-frontend:latest
docker compose up -d --wait
```

Keep the previous release's tarballs on the flash drive too, so a box can be rebuilt from
known-good bytes even if its local `:previous` tags were pruned.

## Why this satisfies "degradation, not errors"

A failed or tampered update never leaves a half-built, unbootable tutor in front of a
student: verification fails **before** any image is loaded, and the box keeps running the
version it already had. The only state changes happen after a clean verify and are a single
atomic `compose up`, with the previous images one `docker tag` away.
