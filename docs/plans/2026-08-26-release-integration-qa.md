# August 26 release integration and QA

## Scope

Integrate the independently reviewed UI, Host mode, power/parallel policy,
mathematical visualization, and localization workstreams for the August 26
release fixes. Gate the fleet live-feed alongside Muta as an independent
deliverable. Packaging and publication remain out of scope.

## Merge protocol

1. Pin every handoff by local commit SHA and import it into a named local ref.
2. Merge the localization inventory/test foundation first, followed by Power,
   visualization, UI, and Host mode. Resolve overlap against the user’s exact
   copy, screenshots, API ownership, and lifecycle requirements.
3. Send the fully integrated English-key base to the localization task. Merge
   its final catalog commit last.
4. Keep authored UI assets and generated `ui/dist` output consistent, and
   regenerate the OpenAPI contract only from application models.
5. Do not merge or subtree-import the unrelated private fleet repository. Pin
   and test its reviewed commit independently, then record that it must be
   pushed and deployed separately after the shared release gate.

## Pinned provenance

- Localization foundation: `05bc6df551a4864ec12bc19061aa1e9873502b01`
- Power/parallel policy: `504485b820580fa25ff993e4d2c391d40d9ea06f`
- Deterministic visualization: `b28f24ee9bccb771639789451969157ece70015f`
- UI polish: `534939cdb637937d6e365c9887ac422c5efd3eb4`
- Independent fleet deliverable:
  `084d4c48a6fa035eb9548c3d3193ba9850ba0f59`

## Release gate

- Run the complete Python and Node suites, focused Host/SSE/cancel/mobile,
  visualization, localization, fleet, desktop staging/inspection, and Rust
  launcher suites.
- Browser-test desktop, 375 px, large phone, and landscape in light/dark and
  reduced-motion modes. Cover cold/warm/failure startup, delete/pin, Host
  removal, disconnect/recovery, Stop recovery, code highlighting, mobile
  autoscroll pause/resume, visualization static/animation, and fleet updates.
- Exercise the local Host relay and GCP relay path where credentials and the
  existing signed-in environment permit it.
- Record commands, outcomes, screenshots, and any explicit environment
  boundary in a release evidence document.
- Perform a fresh adversarial review after all fixes and localization land.

Only after the gate is green may this branch be committed/pushed and reported
to the parent task. Packaging may rebuild only after the parent confirms the
release gate; this task never publishes or replaces release assets itself.
