# GCP campaign completion and service restoration

Read-only host checks were made on `muta-vm` (`muta-adtc`, `us-west1-b`) at approximately 20:29–20:30 UTC on 14 September 2026. No service, configuration, model, or inference job was changed during these checks.

## Benchmark completion

The journal for `muta-judges-scalar-20260914.service` records the last response at 20:16:20 UTC, `judge-prompt phase ended` at 20:16:21, and service termination accounting at 20:16:22. The transient unit is now absent (`LoadState=not-found`, inactive/dead).

The [raw responses](raw/judges-responses.jsonl) contain 125 captured responses: twelve selected models have all ten prompts, and Falcon has five responses followed by the [recorded parsing failure](failures/falcon-gcp-scalar.md). Full capture does not imply that every response finished within the token limit or passed grading. Spark was excluded from the thirteen-model run and remains untested here.

The local and GCP files have matching complete-file hashes:

| Evidence | Records | Bytes | SHA-256 |
|---|---:|---:|---|
| `raw/judges-responses.jsonl` | 125 | 585,190 | `acf72e89dc9de772ac8fa38493a5a103d44c7c579d1b2ba8f687d2eabb77b544` |
| `raw/judges-events.jsonl` | 27 | 14,651 | `0f3f2ca3a972099e0fa52f2da76552975c6a349278a31d38122958d5d16b4557` |

No `llama-server`, `llama-bench`, judges runner, or STEM runner process was found during the process check. Ports 8000, 8080, and 18081 had no listening socket.

## Restoration state

The [campaign wrapper](run_judges_suite.sh) attempts to restore both services on exit. Its journal records the Ops Agent start command at 20:16:21; `google-cloud-ops-agent.service` is active.

**The gateway is not healthy.** `muta-gateway.service` is configured to run `run.sh --native-linux` and restart every three seconds. At 20:29:04 it was `activating/auto-restart`, with exit status 1 and no main process. Its journal repeatedly reports:

```text
native UI index references missing assets: brand/muta-stacked-on-dark.svg, brand/muta-stacked-on-light.svg, brand/muta-wordmark-on-dark.svg, brand/muta-wordmark-on-light.svg, muta-icon.svg
```

All five source files exist in the checkout. `ui/dist/brand` and `ui/dist/muta-icon.svg` are absent. The [native exporter](../../../scripts/export_native_linux.py) discovers only top-level `.css`, `.html`, and `.js` files, then overlays that inventory before validating the updated HTML. Consequently, the HTML is copied but its SVG dependencies are omitted. Startup exits at this validation step before launching the engine.

The branding change is from commit `524fe61f` (12 September); the exporter is unchanged since `333aaef6` (22 August), and the native manifest predates the branding change. This establishes a pre-existing source/export incompatibility. Bounded gateway journal queries before campaign completion returned no entries, so this audit cannot establish whether the gateway was healthy immediately before the benchmark stopped it. Restoration attempted a start; it did not restore a working UI.

## Repair boundary

A focused repair would extend native UI synchronization to include the required SVG and brand assets, preserve path and hash validation, update the UI manifest, and verify startup. Rebuilding inference binaries is not indicated by the logged error. No repair or restart was attempted under this read-only audit; the gateway remains unavailable.

Host source hashes used for the diagnosis: `scripts/export_native_linux.py` → `6e4bc5e1626412c06931f49c137a7bdc58dc26e7224e9de5574e801521782bf4`; `ui/index.html` → `64fb484357c78fd438316f217f338f33b81d80e7f87336e7fb1eea029a7e9300`.
