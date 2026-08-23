# Image reader recovery

**Date:** 2026-08-23
**Status:** implementation complete and pending user review; do not commit, push, or deploy

## Failure

An uploaded image reaches `/v1/tutor/vision`, but the ephemeral CORE-VISION process does not
become usable. The browser consequently receives `accepted: false` and collapses every backend
reason into the generic “The image couldn’t be read.” message shown in the attachment chip and
toast.

The deployed native topology exposes two concrete launch defects:

1. `runtime.vision._wrap_with_scope()` invokes the system service manager from an unprivileged
   user-owned gateway. The GCP/native service is a systemd **user** unit, so the transient vision
   scope must use the same user manager.
2. The scope still carries the original 1,100 MiB marginal-memory limit. That limit assumed the
   resident text and ephemeral vision servers mapped the same 4B weights. Native GCP now serves
   the 0.8B Muta Tutor while CORE-VISION correctly retains its paired Qwen3.5-4B model and
   projector. The original 3,500 MiB planner estimate is also below the repository's own
   analytical working set (~3,791 MiB before allocator/engine overhead), so the process needs
   a 4,352 MiB ceiling and the planner must reserve the same conservative amount when text and
   vision weights differ.
3. The vision server can be launched with the bundle's `data/api.key`, but `VisionClient` did not
   send that key. A secured portable bundle therefore rejected every transcription request even
   after a successful spawn. The current GCP checkout has no key file, so this is not the observed
   GCP trigger, but it is part of the same universally broken multimodal path.
4. A fixed-name transient scope without `--collect` remains failed after an OOM on systemd 249;
   the next upload then fails because `tutor-core-vision.scope` still exists.

The model and projector are present on GCP, the gateway and resident text engine are healthy,
and more than 6 GiB was available during diagnosis. The upload picker and multipart request are
not the failing boundary.

## Invariants

1. The vision process remains CPU-only, loopback-only, single-slot, TTL-reaped, and memory-bounded.
2. A user systemd manager owns the transient scope when available; non-systemd development keeps
   the existing direct-process fallback.
3. The configured vision ceiling must cover the separately staged 4B vision model and projector,
   and Host-capacity admission must reserve the same amount.
4. A refusal remains a successful HTTP response with `accepted: false`; the UI shows the server's
   safe, actionable reason instead of inventing a generic diagnosis.
5. The current request is local-only. No commit, push, GCP file change, service restart, or
   deployment occurs before explicit user approval.

## Work

1. Add regression tests proving the transient scope targets the user manager and carries the full
   separately-weighted vision ceiling.
2. Centralize the vision full-RSS default so runtime enforcement and Host-capacity planning cannot
   silently diverge again; retain an environment override for measured target-box tuning.
3. Preserve the backend `detail` in the attachment entry and surface it in the visible toast and
   accessible chip metadata. Treat non-JSON/non-2xx responses as upload errors with a recovery
   instruction.
4. Authenticate the image-content completion request whenever the spawned vision server uses the
   staged API key.
5. Add a UI regression that exercises accepted, refused, and transport-error image uploads.
6. Run focused tests, full relevant suites, lint/syntax checks, and a fresh adversarial review.
7. Present the uncommitted diff and evidence to the user for review.

## Acceptance

- The scope command contains `systemd-run --user --scope` and a memory limit consistent with the
  full vision reserve.
- Capacity planning and runtime enforcement read the same default/override.
- A backend refusal such as memory pressure or a failed reader is displayed verbatim as the toast
  and retained on the chip; it is never replaced by “The image couldn’t be read.”
- Existing guard, timeout, cancellation, queueing, persistence, and transcription tests remain
  green.
- Git history and GCP remain unchanged until the user explicitly approves commit/deployment/push.
