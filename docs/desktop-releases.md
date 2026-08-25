# Desktop builds and releases

Muta now has one native desktop architecture for all supported systems:

```
Tauri window
  -> frozen muta-gateway (the existing FastAPI app and existing web UI)
       -> platform-native llama-server
```

There is no Electron rewrite and no separate macOS frontend. Tauri supplies the native window,
single-instance lock and process lifecycle; the application navigates to the same loopback
`/chat/` UI after `/v1/ready` returns `{"ready": true}`. Release builds also contain the signed
updater configuration and verification key used by the published update artifacts.

## Supported release targets

| Release target | GitHub runner | First-install artifact |
|---|---|---|
| Ubuntu 22.04 x86-64 | `ubuntu-22.04` | AppImage + model pack tarball |
| Windows x86-64 | `windows-2022` | offline NSIS/WebView2 installer + model pack zip |
| macOS Apple Silicon | `macos-15` | notarized app/DMG + model pack tarball |
| macOS Intel | `macos-15-intel` | notarized app/DMG + model pack tarball |

The explicit macOS labels are intentional: GitHub's current standard `macos-15` runner is
arm64 while `macos-15-intel` is Intel. See the [GitHub-hosted runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

Each platform's **offline kit** pairs the native application with the selected Muta Tutor 0.8B
GGUF, its image projector, the English ASR/VAD/TTS models, the retrieval embedding model, local
licences and hashes. Code-only installers and updater artifacts intentionally omit the model pack,
so routine application releases do not re-download almost 1 GB of unchanged weights. Development
directories such as `muta-iq`, top-level `bench`, model bake-off candidates and training code do
not ship.

## Offline and model-update contract

The application never downloads a model at runtime. It binds the API and model engine to random
loopback ports, uses local SQLite, and sets model auto-download off. GCP is not involved in
startup, tutoring, storage or inference.

The optional heartbeat is the only configured network path. It is absent unless both release
settings are supplied, inert until the operator grants consent, contains no prompts or learner
content, and treats an unreachable collector as a normal offline condition.

Models do not live inside the signed app. On first launch Muta verifies the detached signature,
every file size and every SHA-256, copies the pack into a versioned per-user directory, verifies
the copy, then atomically replaces `active.json`. This is required because changing a GGUF inside
a macOS app invalidates its code signature, AppImages are compressed/read-only, and Windows
cannot overwrite a GGUF while llama.cpp has it mmap-open.

Normal app releases keep the same model-pack ID and update code only. A future model release uses
a new pack ID; the old version remains available until the new pack is fully verified and
activated.

## Local unsigned build

Prerequisites are Python 3.11, Node 22, stable Rust, CMake/Ninja, a C/C++ toolchain and the native
Tauri system libraries. Then:

```bash
python -m pip install -e ".[desktop,dev]"
make desktop-models
make desktop-native
make desktop-test
make desktop-build ARGS="--include-optional-models"
```

Outputs land below `desktop/build/` and `desktop/src-tauri/target/release/bundle/`. Native
binaries are always compiled on their destination OS/architecture. The native build is pinned to
llama.cpp `b10035` at `602f828b4d93a2fefdd546145d9e761825f3bd11` and FFmpeg `n7.1.1` at
`db69d06eeeab4f46da15030a80d539efb4503ca8`.

Unsigned local builds are for development only. They intentionally do not contain updater/model
signing keys and are not suitable for distribution.

## Immediate four-platform test packages

Pushing the `muta-packages` branch runs `.github/workflows/desktop-packages.yml` on four native
GitHub runners and uploads one complete offline archive for each supported target. These archives
include the application and model pack and are suitable for copying to test laptops immediately.
Every archive exposes `HOW TO INSTALL.txt` at its top level. They are intentionally unsigned:
the macOS test kit includes `Muta.command`, which clears download quarantine only from its sibling
`Muta.app` before opening it. Because Finder can quarantine the helper too, the guide has the
tester invoke it explicitly by typing `/bin/zsh ` in Terminal, dragging `Muta.command` into that
window and pressing Return. Windows displays an **Unknown Publisher** warning, and Linux includes
`Muta.sh` to restore the AppImage executable bit. These helpers are private-test conveniences, not
substitutes for platform trust. Use the protected release workflow below for public, warning-free
distribution; its notarized macOS kit opens `Muta.app` directly and does not include the quarantine
helper.

The package workflow restores three content-addressed layers when their inputs have not changed:
the verified platform-independent models/UI, each target's pinned native sidecars, and each
target's complete frozen Python gateway. It always stages, bundles, smoke-tests and inspects a new
final package. A cache miss is not an error; the runner regenerates and verifies that layer before
continuing.

`.github/workflows/desktop-cache.yml` populates trusted default-branch caches after relevant pushes
to `main`, making those entries visible to the package branch and release tags. Run it manually
once after GitHub Actions is enabled if its initial push run was missed. UI changes invalidate only
the UI layer; Python/dependency changes invalidate only the frozen gateway; native pin/build changes
invalidate only native sidecars; model pin/provisioning changes invalidate only the model layer.
GitHub may evict caches, so no release depends on them for correctness.

## Manual four-platform builds through GCP

GitHub Actions is not required. After committing and pushing an update to `main`, run this on the
development Mac:

```bash
make final-package
```

That command resolves the exact pushed commit, derives a SemVer such as `0.1.394`, builds Ubuntu
and Windows through GCP, builds both macOS architectures locally, verifies all four checksums, and
writes the result below `desktop/build/final-packages/`. Use `ARGS="--version 0.2.0"` to choose an
explicit version. The command refuses unpushed commits so every package remains reproducible.

The manual workers reuse content-addressed model, UI, native-sidecar, frozen-gateway and Cargo
caches. Final assembly and checksums always run. `muta-vm` also has a five-minute systemd timer:
when `origin/main` changes, it automatically warms/builds the Linux and Windows outputs. GCP cannot
host macOS, so the two Mac outputs are completed by `make final-package` while the Mac is awake;
the command reuses the GCP outputs instead of rebuilding them.

For diagnosis, `make final-package ARGS="--dry-run --skip-upload"` prints the complete execution
plan. GCP watcher logs are available with
`journalctl -u muta-package-watch.service --no-pager`.

## One-time GitHub release setup

Create a protected GitHub Actions environment named `desktop-release`. Require approval and
restrict it to protected `v*` tags. Add these values to that environment:

| Name | Kind | Required for |
|---|---|---|
| `MUTA_UPDATER_PUBLIC_KEY` | variable | every release; also verifies model packs |
| `TAURI_SIGNING_PRIVATE_KEY` | secret | updater and model-pack signatures |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | secret | private-key password |
| `APPLE_SIGNING_IDENTITY` | secret | Developer ID identity string |
| `APPLE_CERTIFICATE_BASE64` | secret | base64 PKCS#12 Developer ID certificate |
| `APPLE_CERTIFICATE_PASSWORD` | secret | PKCS#12/keychain password |
| `APPLE_ID`, `APPLE_PASSWORD`, `APPLE_TEAM_ID` | secrets | notarization |
| `WINDOWS_CERTIFICATE_BASE64` | secret | base64 Windows code-signing PFX |
| `WINDOWS_CERTIFICATE_PASSWORD` | secret | PFX password |

Generate the Tauri/minisign updater key exactly once and back it up offline:

```bash
cd desktop
npm ci
npm run tauri -- signer generate --write-keys ~/.config/muta/updater.key
```

Use a strong password when prompted. Store the private file contents as the private-key secret,
the password as its password secret, and the exact one-line `.pub` file contents as the public
variable. Tauri base64-wraps the underlying two-line minisign public-key document; do not decode
or reformat it. The workflow validates that wrapper and refuses to invent replacement keys.
Rotating this key is a separate trust migration, not an ordinary app release.

Optional heartbeat values are `MUTA_DESKTOP_HEARTBEAT_URL` (environment variable) and
`MUTA_DESKTOP_HEARTBEAT_INGEST_KEY` (secret). Set both or neither. `MUTA_MODEL_URL` is an optional
secret URL for a trusted mirror of the already-derived final tutor GGUF; its pinned SHA-256 is
still mandatory.

## Publish an update from Git

A source change does not alter already-built executables. Commit and test the change, then push a
new SemVer tag:

```bash
git push origin main
git tag -s v0.2.0 -m "Muta 0.2.0"
git push origin v0.2.0
```

The tag runs `.github/workflows/desktop-release.yml`. It restores or provisions and verifies models
once, then performs four native assemblies in parallel. Each build restores or freezes the Python
onedir and native sidecars, signs nested code, signs the model manifest, builds the Tauri
installer/updater, signs or notarizes the outer artifact, inspects architecture/dependencies, and
creates a complete offline first-install kit.
The publish job refuses to overwrite an existing release, creates `latest.json`, and uploads all
installers, offline kits, updater signatures and checksums to the immutable GitHub Release.

This pipeline republishes the applications from the tagged Git revision. The current desktop
shell does not silently check for or install updates while tutoring: users install a newer signed
release deliberately. The generated signed updater artifacts and `latest.json` leave a safe path
for adding an explicit in-app update prompt later without changing the release format.

Pull requests and normal branch pushes run tests but cannot access release secrets. An approved
manual run is available for recovery, but normal production releases should come from a signed,
protected SemVer tag.
