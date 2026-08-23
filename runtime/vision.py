"""CORE-VISION lifecycle — spawn on demand, kill on idle (TDD §6.3, §7.1, D7, S2).

Why a second server rather than one instance with `--mmproj` always loaded: on current
mainline, loading an mmproj sets the multimodal capability flag on *every* slot, which
disables slot save/restore, context shift and prompt-cache reuse — the three mechanisms the
classroom server is built on (upstream #21133). So text serving and vision serving are
separate processes over the *same weight file*; the OS page cache shares the read-only
weight pages, making the marginal cost mmproj + this instance's KV, not a second copy of the
weights.

D7 resolved it as a gateway-managed subprocess under `systemd-run --scope -p MemoryMax=…`,
with llama-swap and llama-server router mode documented as alternatives. The escape hatch is
explicit in the TDD: if this manager exceeds 200 LoC or three bugs, switch. That budget is
why there is no queueing, no restart backoff and no warm pool here — spawn, health-check,
reap.
"""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import httpx

from runtime.profiles import (
    BundlePaths,
    Invocation,
    ServingProfile,
    core_vision_command,
    get_profile,
    vision_full_rss_reserve_mib,
)

log = logging.getLogger("muta.runtime.vision")

#: TDD §6.3: TTL-kill after 120 s idle; cold spawn budget ≤ 6 s from page-cache-warm weights.
IDLE_TTL_SECONDS = 120.0
SPAWN_BUDGET_SECONDS = 6.0
STARTUP_TIMEOUT_SECONDS = 60.0


def _startup_timeout_from_env() -> float:
    """60 s covers a warm spawn on the target box; a cold load under emulation can exceed it,
    turning every image into "did not become ready". MUTA_RT_VISION_STARTUP_S widens the
    window per box — the vision-side sibling of MUTA_RT_STARTUP_TIMEOUT_S."""
    try:
        return float(os.environ.get("MUTA_RT_VISION_STARTUP_S", STARTUP_TIMEOUT_SECONDS))
    except ValueError:
        return STARTUP_TIMEOUT_SECONDS


CPU_WEIGHT = "500"


class VisionDenied(RuntimeError):
    """Spawn refused — by the degradation ladder, or because nothing is staged to spawn."""


@dataclass
class VisionManager:
    paths: BundlePaths = field(default_factory=BundlePaths.from_env)
    profile: ServingProfile = field(default_factory=get_profile)
    ttl_seconds: float = IDLE_TTL_SECONDS
    startup_timeout_s: float = field(default_factory=_startup_timeout_from_env)
    #: Returns True when a vision spawn is allowed. Wired to the degradation ladder (§5.3):
    #: at L1 and above new spawns are denied and vision requests queue.
    admit: Callable[[], bool] = lambda: True
    clock: Callable[[], float] = time.monotonic

    process: subprocess.Popen | None = field(default=None, init=False)
    # None = never used. Not 0.0: a monotonic clock legitimately reads 0, and treating that
    # as "never touched" made an idle instance immortal.
    last_used: float | None = field(default=None, init=False)
    spawns: int = field(default=0, init=False)
    #: True from Popen until the health check passes. An instance that is still loading has
    #: not been idle for a single second yet, so the reaper has nothing to measure and must
    #: leave it alone.
    starting: bool = field(default=False, init=False)
    #: Requests currently inside `in_use()`. A transcription at the Qwen-VL token floor
    #: legitimately runs past the 120 s TTL on a slow box, and `last_used` is only stamped at
    #: `ensure()` — without this count the reaper killed a busy server mid-read (latent until
    #: the client timeout grew past the TTL).
    _active: int = field(default=0, init=False, repr=False)
    #: Guards `_active` alone. Deliberately NOT `_lock`: that one is held for the whole
    #: spawn (up to minutes), and a finishing request must never wait on someone else's
    #: model load just to decrement a counter.
    _active_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    # CORE-VISION is a single-slot auxiliary engine. Serialisation prevents overlapping image
    # contexts from escaping the Host-mode memory plan when several learners upload at once.
    _use_slot: threading.Semaphore = field(
        default_factory=lambda: threading.Semaphore(1), init=False, repr=False
    )
    #: Serialises spawn decisions. Two uploads in flight at once would otherwise both see
    #: `running == False` and race two servers onto port 8082; the loser exits with EADDRINUSE
    #: and both students are told the reader is broken. The second caller waits and then
    #: reuses the instance the first one started — which is the queueing §5.3 already promises.
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    # --- state ------------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    @property
    def base_url(self) -> str:
        from runtime.profiles import port

        return f"http://127.0.0.1:{port('VISION', 8082)}"

    def idle_seconds(self) -> float:
        return self.clock() - self.last_used if self.last_used is not None else 0.0

    # --- lifecycle --------------------------------------------------------------------
    def ensure(self) -> str:
        """Return a ready base URL, spawning the instance if needed.

        Raises `VisionDenied` when the ladder says no — the caller turns that into S2's
        honest fallback ("type the problem for now"), never into an error page.
        """
        with self._lock:
            if self.running:
                self.touch()
                return self.base_url
            if not self.admit():
                raise VisionDenied(
                    "vision is unavailable right now (memory pressure) — "
                    "type the problem and I'll work through it with you"
                )
            self._spawn()
            self.touch()
            return self.base_url

    def _spawn(self) -> None:
        try:
            invocation = core_vision_command(self.paths, self.profile)
        except (FileNotFoundError, RuntimeError) as e:
            log.warning("CORE-VISION model staging failed: %s", e)
            raise VisionDenied(
                "the image reader isn't installed correctly — "
                "type the problem and I'll work through it with you"
            ) from e

        argv = _wrap_with_scope(invocation)
        log.info("spawning CORE-VISION: %s", " ".join(_redact_cli_secrets(argv)))
        started = self.clock()
        # Start the idle clock at spawn, not after the load finishes. `_wait_until_ready`
        # blocks for tens of seconds, and for all of it `running` is already True; leaving
        # `last_used` on the *previous* use (always older than the TTL once an instance has
        # been reaped) let the reaper kill the very server this call is waiting for.
        self.starting = True
        self.touch()
        try:
            # Inside the try: a Popen that raises must still clear `starting`, or the reaper
            # is disabled for the rest of the process's life.
            self.process = subprocess.Popen(
                argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            self.spawns += 1
            self._wait_until_ready(started)
        finally:
            self.starting = False

    def _wait_until_ready(self, started: float) -> None:
        deadline = started + self.startup_timeout_s
        # Hold the process locally: `stop()` nulls the attribute, so reading it through `self`
        # meant a server that died mid-load looked merely slow and burned the whole timeout
        # before reporting the wrong reason.
        process = self.process
        while self.clock() < deadline:
            if process is not None and process.poll() is not None:
                code = process.returncode
                if self.process is process:
                    self.process = None
                raise VisionDenied(f"vision server exited during startup (code {code})")
            if self._healthy():
                elapsed = self.clock() - started
                if elapsed > SPAWN_BUDGET_SECONDS:
                    # Not fatal, but the student is staring at "reading your work…" for that
                    # long — worth seeing in the logs when the demo feels slow.
                    log.warning(
                        "vision spawn took %.1fs (budget %.0fs)", elapsed, SPAWN_BUDGET_SECONDS
                    )
                log.info("CORE-VISION ready in %.1fs", elapsed)
                return
            time.sleep(0.25)
        self.stop()
        raise VisionDenied("vision server did not become ready in time")

    def _healthy(self) -> bool:
        try:
            return httpx.get(f"{self.base_url}/health", timeout=1.0).status_code == 200
        except httpx.HTTPError:
            return False

    def touch(self) -> None:
        self.last_used = self.clock()

    @contextlib.contextmanager
    def in_use(self) -> Iterator[None]:
        """Marks a request in flight so the TTL reaper leaves the server alone. The idle
        clock restarts when the request finishes — TTL measures idleness, not wall time."""
        with self._use_slot:
            with self._active_lock:
                self._active += 1
            try:
                yield
            finally:
                with self._active_lock:
                    self._active -= 1
                    self.touch()

    def stop_for_reconfigure(self) -> bool:
        """Stop an idle auxiliary engine before the text profile is replaced.

        Both locks are non-blocking: a host capacity change must report that an image is
        still being read instead of killing it mid-request or waiting invisibly for minutes.
        `in_use()` owns `_use_slot` across spawn and transcription, while `_lock` excludes a
        concurrent spawn decision.
        """
        if not self._use_slot.acquire(blocking=False):
            return False
        if not self._lock.acquire(blocking=False):
            self._use_slot.release()
            return False
        try:
            if self._active > 0 or self.starting:
                return False
            self.stop()
            return True
        finally:
            self._lock.release()
            self._use_slot.release()

    def reap_if_idle(self) -> bool:
        """TTL reaper tick. Returns True when it killed the instance.

        Called on a timer by the gateway: the auxiliary RSS this frees is headroom the
        degradation ladder spends (§5.3), so holding an idle vision server is not free even
        when nothing is asking for memory yet.
        """
        # Non-blocking: this runs on the gateway's event loop, so waiting on a 60 s spawn here
        # would stall every other request. A spawn in flight also means nothing is idle.
        if not self._lock.acquire(blocking=False):
            return False
        try:
            if self.starting:
                # Mid-load: a student is waiting on this exact instance, and it has accrued no
                # idle time to judge. Killing it here is how the second upload of a session
                # used to fail permanently.
                return False
            if self._active > 0:
                # Mid-request: a student is waiting on this exact answer.
                return False
            if not self.running:
                return False
            if self.idle_seconds() < self.ttl_seconds:
                return False
            log.info("reaping idle CORE-VISION after %.0fs", self.idle_seconds())
            self.stop()
            return True
        finally:
            self._lock.release()

    def stop(self) -> None:
        process, self.process = self.process, None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()

    def status(self) -> dict:
        return {
            "running": self.running,
            "url": self.base_url if self.running else None,
            "idle_seconds": round(self.idle_seconds(), 1) if self.running else None,
            "ttl_seconds": self.ttl_seconds,
            "spawns": self.spawns,
        }


def _wrap_with_scope(invocation: Invocation) -> list[str]:
    """`systemd-run --scope` where it exists (the target), plain exec where it does not (dev).

    The cap is the point: without it, a vision instance that mis-sizes its KV takes the core
    server down with it, and an OOM kill is a disqualification rather than a slow answer.
    """
    if shutil.which("systemd-run") is None:
        log.info("systemd-run absent — spawning vision without a cgroup cap (dev only)")
        return invocation.argv
    memory_max_mib = vision_full_rss_reserve_mib()
    return [
        "systemd-run",
        # Native Muta is itself a systemd user unit. Calling the system manager here asks an
        # unprivileged process to create a root-owned scope and exits before llama-server ever
        # starts; use the same per-user manager that owns the gateway.
        "--user",
        "--scope",
        # CollectMode=inactive-or-failed: an OOM/crash must not leave the fixed unit name in
        # the failed state and make every later image retry fail with "unit already exists".
        "--collect",
        "--quiet",
        "--unit",
        "tutor-core-vision",
        "-p",
        f"MemoryMax={memory_max_mib}M",
        "-p",
        f"MemoryHigh={int(memory_max_mib * 0.9)}M",
        "-p",
        f"CPUWeight={CPU_WEIGHT}",
        "-p",
        "Slice=tutor.slice",
        *invocation.argv,
    ]


def _redact_cli_secrets(argv: list[str]) -> list[str]:
    """Return a log-safe command without exposing llama-server credentials."""
    redacted = list(argv)
    for index, argument in enumerate(redacted[:-1]):
        if argument == "--api-key":
            redacted[index + 1] = "<redacted>"
    return redacted


def ffmpeg_frames_command(
    source: str, out_pattern: str, *, fps: int = 1, frames: int = 8
) -> list[str]:
    """Video → at most 8 frames at 1 fps, longest side ≤ 1280 (TDD §6.3, S4).

    The cap is a context budget, not a quality choice: image tokens scale with resolution and
    frame count, and one careless clip would eat a whole slot's context.
    """
    return [
        "ffmpeg",
        "-i",
        source,
        "-vf",
        f"fps={fps},scale='min(1280,iw)':-2",
        "-frames:v",
        str(frames),
        "-y",
        out_pattern,
    ]
