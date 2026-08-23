# CORE-VISION lifecycle — the two races, and the invariants that close them

> **Historical subsystem record — superseded 23 Aug 2026.** The browser no longer starts this
> auxiliary server or asks it to transcribe a selected image. It uploads guarded bytes, then the
> selected catalog model receives those bytes with the learner's exact text when Send is pressed.
> `runtime/vision.py` remains only for legacy/non-browser callers. Current behavior and rationale:
> [`multimodal-decision.md`](multimodal-decision.md).

`runtime/vision.py` spawns an ephemeral llama-server on demand and TTL-kills it at 120 s idle
(TDD §6.3, D7). Two concurrency bugs lived in that ~150-line manager and made image upload
fail *permanently* after the first use. Both are fixed; this is the record of why the
invariants exist, so nobody re-optimises them away.

Status: **27 Jul 2026**. Found by debugging a "the tutor says it can't see my image" report.

---

## Race 1 — the idle reaper killed servers that were still starting

`ensure()` stamped `last_used` only *after* `_spawn()` returned. But `_spawn()` blocks for the
whole model load — 12–15 s here, and `STARTUP_TIMEOUT_SECONDS` allows 60. For that entire
window:

- `running` is already `True` (Popen returned), so the reaper considers the instance fair game;
- `last_used` still holds the **previous** use, which after a reap is by definition older than
  the 120 s TTL.

So `_vision_reaper`'s 30 s tick (`orchestrator/main.py`) saw a fully idle instance and killed
the server a student was waiting on. Measured: the process died ~21 s into its load.

It is not an intermittent race. After the first successful upload and its reap, `last_used` is
*always* stale, so **every subsequent upload for the life of the process was killed mid-load**.

### Why it reported the wrong reason

`stop()` does `process, self.process = self.process, None`. `_wait_until_ready` read the
process through `self`, so once the reaper nulled it the exit check
(`self.process is not None and self.process.poll() is not None`) could never fire again. The
loop spun out its full 60 s and raised `"vision server did not become ready in time"` — a slow
load — for a server that had been dead for 39 s. That misdirection is why this took a
process-level timeline to find rather than a log read; the log just stopped mid-load.

### Invariants

1. **The idle clock starts at spawn, not at ready.** `_spawn()` calls `touch()` before Popen.
2. **`starting` is set for the whole load**, and `reap_if_idle()` returns early on it. A server
   that has not finished loading has accrued no idle time to judge.
3. **`_wait_until_ready` holds its process in a local**, so a concurrent `stop()` cannot blind
   the exit check. A death is reported as a death, promptly, with its exit code.

Invariant 1 alone would be enough only while `STARTUP_TIMEOUT_SECONDS (60) < IDLE_TTL (120)`.
That coupling is invisible at both definition sites, so 2 states it explicitly.

## Race 2 — concurrent uploads raced two servers onto one port

`ensure()` took no lock. Two uploads in flight — one impatient student clicking twice, or two
of the six phones a classroom is sized for — both saw `running == False` and both spawned.
The loser exits with `EADDRINUSE`; because both callers are polling the *same* port, the winner's
student is told the reader is broken too.

`ensure()` now serialises on `_lock`; the second caller waits and then reuses the instance the
first one started, which is the queueing §5.3 already promises at L1.

**`reap_if_idle()` must use a non-blocking acquire.** It runs directly on the gateway's event
loop (`_vision_reaper` awaits, then calls it inline), so blocking it on a 60 s spawn would stall
every other request in the classroom. Failing to get the lock also *means* a spawn is in
flight, i.e. nothing is idle — so returning `False` is correct, not merely convenient.

## The client side: a transcription the tutor never received

Worth recording because it produced the same user-visible symptom from the other end.

The tutor is a **text** model. `attachment_ids` on `/v1/chat/stream` binds attachment rows to
the persisted turn (`_link_attachments`) — it is history metadata and **never reaches the
model**. The only thing that tells the tutor an image exists is the transcription text the UI
inlines into `message` (`composeOutgoingMessage` in `ui/app.js`).

So when vision was refused, `ui/app.js` kept the chip (with `transcription: ""`) and rendered
the thumbnail into the transcript, while sending the tutor a bare question. The student saw
their photo on screen and read "I cannot see the image" underneath it. The backend had degraded
honestly (`accepted:false` + a reason); the UI dropped that on the floor.

The UI now declares an unreadable image in the message text, so the tutor asks the student to
type the problem instead of denying the photo exists — and the chip carries a durable
`reading…` / `couldn't read it` state instead of a 4-second toast, because reading a photo here
takes 12–95 s and silence is what made students upload the same image repeatedly.

## What a regression looks like

`runtime/tests/test_vision.py`:

- `test_the_idle_reaper_does_not_kill_an_instance_that_is_still_starting`
- `test_concurrent_requests_spawn_exactly_one_instance`

Both fail against the old code with exactly the production symptoms
(`VisionDenied: vision server did not become ready in time`, and `raced 2 vision servers`).

End-to-end, on the compose stack: upload an image, wait past the 120 s TTL for the reap, upload
again. The second upload is the one that used to fail forever. Warm reuse answers in ~3 s; a
cold spawn costs ~12 s plus ~80 s of image processing under amd64 emulation on this box.
