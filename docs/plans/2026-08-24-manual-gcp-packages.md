# Manual and GCP-triggered desktop package plan

**Status:** implementation in progress, 2026-08-24

## Outcome

Provide one command, run from the development Mac after a pushed commit, that produces the four
verified offline archives below `desktop/build/final-packages/`:

- macOS arm64;
- macOS x86-64;
- Ubuntu 22.04 x86-64;
- Windows x86-64.

The command must not depend on GitHub Actions. It coordinates the two native/cross-native macOS
builds on the development Mac and the Linux/Windows builds through GCP. GCP remains build
infrastructure only; none of it becomes an installed-app runtime dependency.

## Platform boundary

GCP Compute Engine has no supported macOS guest. Linux cannot produce a genuine PyInstaller Mach-O
closure or Apple Tauri bundle. Therefore:

- `muta-vm` is the always-on commit watcher and GCP coordinator;
- Linux builds on the Ubuntu coordinator;
- Windows builds on a stopped-when-idle persistent Windows Server builder;
- macOS arm64 and Intel build on the development Mac, with Intel Python/Rust/native sidecars run
  under Rosetta/x86-64;
- automatic GCP detection can finish Linux/Windows without the Mac; an optional macOS LaunchAgent
  polls for pending commits and completes both Mac targets whenever the Mac is awake.

No run is described as a four-platform final package until all four archives and checksums exist.

## Exact source and cache model

Every build is identified by a pushed Git commit SHA and SemVer. A detached Git worktree or exported
archive supplies tracked source, so uncommitted developer files cannot enter a package. Verified
model inputs are hard-linked/copied into that isolated tree from the persistent model cache.

The manual worker mirrors the GitHub cache boundaries:

1. UI output key = offline UI builder + UI source/vendor bytes.
2. Model layer = catalog/pins plus full size/SHA-256 verification; weights are never rebuilt for a
   code-only change.
3. Native key = platform + native pins/build/verifier bytes.
4. Frozen gateway key = platform/Python/dependency identity + backend/freezer source bytes.
5. Final Tauri assembly, package inspection, archive creation and SHA-256 are never cached.

Cache hits are copied into the isolated worktree and reverified. Missing/invalid layers rebuild and
are published atomically into the persistent cache. Linux, Windows and Mac keep separate
architecture-specific caches; only model identities are shared through GCS.

## GCP lifecycle

- A dedicated least-privilege package-builder service account lets `muta-vm` write only the package
  bucket and start/stop the named Windows builder.
- The persistent Windows boot disk retains toolchains and caches, while the billable VM is stopped
  after every build, including failures.
- A systemd timer on `muta-vm` fetches `origin/main` periodically under `flock`. A new commit creates
  an automatic version from the commit count, builds Linux/Windows and records status/output in GCS.
- The local one-command run may request an explicit version and reuses any matching GCP layers even
  when an automatic build used a different final version.
- A macOS LaunchAgent is opt-in and invokes the same coordinator only while the Mac is awake.

## Safety and verification

- refuse a local commit that is not reachable from `origin/main`;
- refuse an existing version/SHA mapping rather than overwrite it silently;
- use per-commit work directories and validated explicit cache/output roots;
- preserve `muta-vm` benchmark files and the developer worktree;
- stop the Windows VM in a `finally` path;
- verify model, UI, native, frozen gateway and final package checksums;
- unit-test keys, commit/version selection, safe paths and command planning;
- provide `--dry-run`, GCP-only and Mac-only modes for diagnosis;
- install and exercise the watcher without forcing an unrequested four-gigabyte publication during
  its provisioning step.
