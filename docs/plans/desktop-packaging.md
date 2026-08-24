# Desktop packaging and release implementation plan

**Status:** implemented, 2026-08-24
**Scope:** offline Muta product for Ubuntu 22.04 x86-64, Windows x86-64, macOS arm64,
and macOS x86-64. GCP remains a hardware proxy and optional heartbeat collector; it is not a
runtime dependency.

## Product boundary

The desktop product is the existing `/v1` application in a native shell. Tauri owns the window
and lifecycle but does not replace the browser UI or the FastAPI contract. A frozen Python
sidecar serves the existing UI and API on loopback and supervises the platform-native pinned
`llama-server` process.

Every first-install artifact contains the complete offline model pack. Installed model files
remain ordinary files so llama.cpp can mmap them. Application updates and model-pack updates
are versioned independently so a code-only update does not repeatedly transfer several GiB of
unchanged weights.

### Runtime process tree

```
Muta (Tauri shell)
  -> muta-gateway (frozen Python sidecar, loopback HTTP)
       -> llama-server (native sidecar)
       -> deterministic tool workers (same frozen executable, --tool-worker)
```

The shell waits for `/v1/ready` before replacing its local splash page with `/chat/`. Closing
the last window terminates the gateway process tree. Host mode remains an explicit opt-in and
is the only path that binds beyond loopback.

## Files that ship

The staging script uses an allow-list, never a repository-wide copy:

- the frozen `contracts`, `orchestrator`, `runtime`, and desktop entrypoint modules in the
  complete PyInstaller `onedir` closure, excluding tests/caches;
- `ui/dist`, `landing`, runtime prompts/configuration/question bank and visualization licences;
- the verified `models` runtime files and their licence/provenance manifests;
- a built retrieval index when present;
- platform-native `llama-server` plus its dependency closure;
- desktop notices, updater public key, product manifest and build identity.

It excludes top-level `bench`, `muta-iq`, `papers`, `pilot-v2`, development corpus tooling,
Docker inputs, repository metadata, tests, local databases/logs, and build caches. The
`orchestrator.bench_metrics` runtime module remains because the product telemetry strip imports
it; excluding top-level `bench/` must not remove that module.

## Immutable resources versus mutable state

Desktop releases define three explicit roots:

- `MUTA_RESOURCE_ROOT`: signed/read-only application resources (UI, index and binaries);
- `MUTA_MODEL_ROOT`: a separately signed and versioned ordinary-file model pack;
- `MUTA_DATA_ROOT`: conversations, account state, learning twins, attachments, certificates,
  logs, KV snapshots and heartbeat consent state;
- `MUTA_CACHE_ROOT`: replaceable temporary/generated data.

Legacy native/Compose launches keep working: when the new variables are absent,
`TUTOR_ROOT` retains its current meaning and mutable data stays below `TUTOR_ROOT/data`.
Desktop launchers always pass absolute roots and an absolute SQLite DSN.

Platform data locations:

| Platform | Data root |
|---|---|
| Windows | `%LOCALAPPDATA%\\Muta` |
| macOS | `~/Library/Application Support/Muta` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/muta` |

## Portability work

1. Add one path authority and migrate every product write away from the resource root.
2. Add `desktop/backend_entry.py` with `--serve`, `--healthcheck`, and `--tool-worker` modes.
3. Make the deterministic-tool launcher platform-specific:
   - POSIX retains rlimits, process groups and optional Linux network namespaces;
   - Windows uses a new process group, a reader thread for pipe timeouts, hidden console flags,
     and tree termination through `taskkill`; the native shell additionally owns the whole
     backend tree through a kill-on-close Job Object.
4. Replace the Host-mode shell certificate generator with a Python implementation using the
   bundled `cryptography` package; retain the checked-in shell script as a dev fallback.
5. Resolve UI/assets and the llama binary from the frozen resource root, not source-tree
   `__file__` assumptions.
6. Force offline desktop defaults (`MUTA_OFFLINE=1`, no model auto-download, SQLite, loopback).

## Build outputs

PyInstaller `onedir` freezes the gateway. A one-file build is forbidden: it would extract the
interpreter/native dependencies on every launch and is incompatible with stable worker paths.
GGUF files are never collected by PyInstaller.

Tauri bundles the frozen gateway as an external binary, launches it with absolute resource and
data paths, and produces:

- Ubuntu x86-64 portable tarball and AppImage/update artifact;
- Windows x86-64 NSIS installer and portable zip;
- macOS arm64 `.app`/DMG and updater archive;
- macOS x86-64 `.app`/DMG and updater archive.

macOS nested binaries/libraries are signed before the outer app, then the DMG is notarized and
stapled. Windows PE files and the final installer are signed. Unsigned development artifacts are
allowed only on branch/manual CI and are labelled as such.

## Release and update pipeline

Existing `ci.yml` remains the full fast push/PR gate. `desktop-ci.yml` adds focused desktop
Python/Rust/dependency gates. `desktop-release.yml` runs only for a protected SemVer tag
(`vX.Y.Z`) or an approved manual release:

1. test/lint/contract gate;
2. verify tag version and clean source identity;
3. prepare and hash the product/model manifest;
4. build each native matrix target on its own OS/architecture;
5. run package allow-list, architecture, dependency and manifest inspection;
6. sign/notarize protected release artifacts;
7. generate Tauri signed update artifacts and `latest.json`;
8. assemble a signed offline update directory for flash-drive delivery;
9. publish immutable artifacts to the GitHub Release.

`desktop-cache.yml` is a trusted, path-filtered default-branch cache warmer. Its exact keys split
platform-independent model/UI inputs, target-native pinned sidecars, and target-specific frozen
Python gateways. Package branches and release tags can restore default-branch entries, but every
restored layer is verified and every workflow can regenerate it. Tauri assembly, signing, package
inspection and final artifact creation are deliberately never skipped.

Signing secrets exist only in the protected `desktop-release` environment. Pull requests,
including forked PRs, never receive them. CI must refuse to generate a replacement signing key.

Application and model versions are independent. A normal release reuses the installed model
pack when its signed manifest ID is unchanged. A model release includes the new pack and applies
it atomically only after signature and hash verification.

## Verification gates

- unit tests for path selection on all platforms;
- static Windows import test for the sandbox module;
- frozen-entrypoint and product-manifest tests;
- package allow-list test proving forbidden repo roots are absent;
- binary architecture/dependency/hash inspection;
- model manifest/hash/licence verification;
- first-start and second-start persistence smoke;
- text turn plus PDF, diagram, voice and vision degradation/availability probes;
- no-network run proving readiness and tutoring never require DNS/GCP;
- heartbeat tests proving unconfigured/declined/offline states make no product failure;
- versioned model installation and repeated-start checks that preserve user state;
- signed native artifacts intended for final clean-machine install checks on their target OS.

No release is complete until a separate-context reviewer attempts to break the artifact and its
update path, and every blocking finding is fixed or explicitly recorded.
