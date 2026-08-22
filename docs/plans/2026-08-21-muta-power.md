# Muta power optimization

## Outcome

Make energy conservation a default-on, visible product capability without letting an
ordinary learner silently control the shared host. The first slice must work on the Ubuntu
target, degrade honestly on machines without battery sensors, and preserve tutoring quality
for explicit high-effort or assessed work.

## Existing seams

- `runtime/config.py` already bounds inference threads, context, cache and reasoning.
- `runtime/vision.py` already spawns the vision process on demand and reaps it after an idle TTL.
- `orchestrator/gateway/sessions.py` can persist and release llama.cpp slots.
- `orchestrator/gateway/ladder.py` removes optional features under memory pressure.
- `orchestrator/telemetry.py` owns the bounded, process-wide sampling thread.
- `/v1/settings` persists learner preferences and the browser already renders a settings modal.
- `ModelManager` and `GenerationManager.run_when_idle()` serialize engine lifecycle changes.

## Design

### 1. Observe, never invent

Add `runtime/power.py` with a small provider interface and a `PowerSnapshot` value object.
The Linux provider reads `/sys/class/power_supply` and supports multiple batteries. A psutil
fallback supplies charge and remaining time on other supported desktops. Missing fields are
`None`; an absent battery means `available=false`, not “fully charged.” Sampling is bounded
and cached so request handlers never spawn a command or repeatedly walk sysfs. Connected AC
and active battery discharge are separate signals because an undersized adapter can remain
connected while the battery reserve continues to fall.

### 2. Policy is separate from sensing

Add a process-wide `PowerGovernor` under the gateway. It maps a snapshot to:

- `normal`: AC power, unknown power source, or learner optimization disabled;
- `eco`: discharging with usable reserve;
- `critical`: discharging below the configurable percentage/runtime floor.

Hysteresis prevents percentage or time-to-empty noise from flapping the mode. Critical host
safety actions (for example blocking a new optional vision process) remain host-wide. A
learner's default-on setting controls request-level concessions such as bounded auto-reasoning
and output length; it cannot raise engine concurrency or bypass memory/thermal safeguards.
A short, configurable stale-sensor grace keeps an existing Critical reserve fail-safe through
one or more provider errors; it never invents a new Critical state from unknown data.

### 3. Apply savings on real work

- In Eco mode, cap ordinary automatic reasoning and output, while preserving explicit
  `thinking=extended` and schema-constrained marking.
- In Critical mode, use direct answers for ordinary chat and a tighter output cap.
- Do not start CORE-VISION in Critical mode. Existing running/busy vision work is never killed.
- Do not synthesize TTS in Critical mode; text remains available.
- Reduce idle power/thermal telemetry polling frequency while keeping active-generation
  telemetry at 1 Hz.

### 4. Product surface

Extend `UserSettings` with `power_optimization_enabled=true`. Add authenticated
`GET /v1/power/status`, returning sensor availability, source, percentage, rate, remaining
time, effective mode and concrete active actions. The settings modal gets:

- a default-on “Muta power optimization” switch;
- a live status card;
- an unobtrusive header badge only while Eco/Critical is active.

Phone clients therefore see the serving laptop's condition rather than their own battery.
Unknown hardware produces a clear “power information unavailable” state and no fake numbers.

Power-specific copy is marked as English in this slice rather than falsely declaring existing
machine-assisted locale packs complete with untranslated strings. It must go through the
catalog translation/acceptance pipeline before those packs claim coverage for the new feature.

### 5. Engine parking boundary

Do not overload session suspension: freeing a KV slot does not unload model weights. Add a
park-aware `ModelManager` lifecycle only if the supervisor can distinguish a deliberate park
from a crash, wait without busy-looping, and wake on a request without losing persisted chat.
The inactivity threshold must be configurable and default-disabled until target measurements
establish the restart-energy break-even. This avoids shipping an arbitrary timer that may
consume more energy than it saves.

Whole-system suspend is explicitly outside this slice. It needs a separately installed,
allowlisted privilege helper, multi-user/session checks, a visible countdown and an operator
opt-in “dedicated appliance” setting.

## Verification

- Unit-test Linux sysfs parsing, aggregation, absent/partial sensors and psutil fallback.
- Unit-test mode thresholds, hysteresis, disabled preference and sampling concessions.
- Contract-test default-on private settings and `/v1/power/status` authentication/shape.
- UI asset tests cover the switch, live status card and active-mode badge.
- Regenerate `contracts/openapi.yaml`; run focused tests, full pytest and lint.
- Run an adversarial review in a fresh context and apply findings before handoff.
