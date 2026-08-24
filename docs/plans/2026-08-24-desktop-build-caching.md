# Desktop build cache implementation plan

**Status:** implemented and locally verified, 2026-08-24

## Goal

Keep every final installer a clean, verified assembly of the tagged commit while avoiding work
whose inputs have not changed. GitHub-hosted runners remain disposable; reusable outputs live only
in GitHub Actions caches and are never required for a successful build.

## Cache boundaries

1. **Platform-independent inputs**
   - Cache the verified product model inputs using a key derived from the model pins, provisioning
     code, tutor bake inputs and cache schema.
   - Cache `ui/dist` using a key derived from the UI sources, checked-in vendor assets and the
     offline UI builder.
   - A single Ubuntu job verifies/builds these inputs and passes them to all four package jobs as a
     short-lived workflow artifact. Models and UI are therefore prepared once per run, not four
     times.
2. **Platform-native sidecars**
   - Cache `llama-server`, FFmpeg and their provenance file separately for Linux x86-64, Windows
     x86-64, macOS arm64 and macOS x86-64.
   - The key includes the target, pinned revisions, native build recipe and verifier. A cache hit is
     accepted only after architecture, deployment-target, dependency and AVX-512 checks pass.
3. **Frozen Python gateway**
   - Cache the complete PyInstaller `onedir` tree separately for each target.
   - The key includes Python/platform identity, installed dependency versions, the freezer recipe,
     and every backend source/data input. Any Python or dependency change therefore refreezes the
     gateway; a UI-only change reuses it.
   - Restored gateways still run the packaged `--print-config` smoke test against the newly staged
     resources and models before Tauri can bundle them.

## Trusted cache population

GitHub cache scope makes default-branch caches available to package branches and release tags. A
new path-filtered workflow on trusted pushes to `main` warms the three layers. Pull requests never
write these caches. Package and release workflows can also regenerate every layer on a cache miss,
so eviction, cancellation or an empty cache changes duration rather than correctness.

Cache keys use no broad restore prefix for native binaries, models or frozen gateways. That avoids
silently accepting a stale artifact after a recipe or dependency change. Caches contain no signing
keys, heartbeat credentials or other secrets. Signing always happens after restore inside the
protected release job.

## Work that always remains

Every requested package still stages resources, assembles the model pack, smoke-tests the frozen
gateway, runs Tauri bundling, signs where applicable, inspects architecture/dependency/manifest
closure and uploads a newly named final artifact. This preserves commit identity and release
verification even when all reusable layers hit their caches.

## Verification

- unit-test model cache verification and gateway cache-key invalidation;
- exercise UI build and verify-only modes locally;
- verify the current macOS native output with the shared native verifier;
- run desktop Python tests and lint for changed scripts;
- run `actionlint` over all workflows;
- inspect workflow diffs to prove `main` pushes do not publish installers and release secrets never
  enter a cached path.

Local verification completed with `actionlint`, ShellCheck, Ruff, 31 desktop/cache Python tests,
62 offline-asset Python tests, 95 Node UI tests, four Rust launcher tests, `npm audit`, model/UI/
native cache verifiers, and a cached PyInstaller `onedir` staging plus `--print-config` smoke. The
four GitHub-hosted cache-warming jobs cannot be timed until the repository-level Actions startup
failure is resolved; every cache miss retains the previously tested clean-build path.
