"""Battery-aware, reversible policy for Muta-owned work.

Sensing and policy stay separate: tests inject snapshots, while production reads the host
battery through ``runtime.power``.  The governor never changes a machine-wide CPU governor or
requests system sleep. It only shapes optional Muta work, and preserves explicit extended
reasoning and schema-constrained assessment responses.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from enum import Enum
from typing import Any

from runtime.power import PowerProvider, PowerSnapshot, SystemPowerProvider


class PowerMode(str, Enum):
    NORMAL = "normal"
    ECO = "eco"
    CRITICAL = "critical"


class PowerGovernor:
    def __init__(
        self,
        provider: PowerProvider | None = None,
        *,
        globally_enabled: bool = True,
        poll_interval_s: float = 15.0,
        sensor_grace_s: float = 120.0,
        critical_percentage: float = 12.0,
        critical_time_s: int = 30 * 60,
        hysteresis_percentage: float = 3.0,
        hysteresis_time_s: int = 15 * 60,
        eco_reasoning_budget: int = 256,
        eco_max_tokens: int = 800,
        critical_max_tokens: int = 512,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.provider = provider or SystemPowerProvider()
        self.globally_enabled = globally_enabled
        self.poll_interval_s = max(1.0, poll_interval_s)
        self.sensor_grace_s = max(self.poll_interval_s, sensor_grace_s)
        self.critical_percentage = critical_percentage
        self.critical_time_s = critical_time_s
        self.hysteresis_percentage = hysteresis_percentage
        self.hysteresis_time_s = hysteresis_time_s
        self.eco_reasoning_budget = eco_reasoning_budget
        self.eco_max_tokens = eco_max_tokens
        self.critical_max_tokens = critical_max_tokens
        self.clock = clock
        self._lock = threading.RLock()
        self._snapshot = PowerSnapshot()
        self._last_poll = -1e30
        self._last_available_at = -1e30
        self._host_mode = PowerMode.NORMAL
        self._critical_signals: set[str] = set()

    def snapshot(self, *, force: bool = False) -> PowerSnapshot:
        now = self.clock()
        with self._lock:
            if not force and now - self._last_poll < self.poll_interval_s:
                return self._snapshot
            try:
                value = self.provider.snapshot()
            except Exception:  # noqa: BLE001 - power telemetry is optional, tutoring is not
                value = PowerSnapshot()
            self._snapshot = value
            self._last_poll = now
            if value.available:
                self._last_available_at = now
            return value

    def host_mode(self) -> PowerMode:
        """Classify the host with hysteresis; independent of one learner's preference."""
        snapshot = self.snapshot()
        with self._lock:
            if not self.globally_enabled or snapshot.on_battery is False:
                self._host_mode = PowerMode.NORMAL
                self._critical_signals.clear()
                return self._host_mode
            if snapshot.on_battery is None:
                # A desktop/no-battery host is simply Normal. If a known battery briefly
                # loses its source signal during Critical reserve, keep the safe state until
                # firmware positively reports AC or discharging again.
                if self._host_mode is PowerMode.CRITICAL and (
                    snapshot.available
                    or self.clock() - self._last_available_at <= self.sensor_grace_s
                ):
                    return self._host_mode
                self._host_mode = PowerMode.NORMAL
                self._critical_signals.clear()
                return self._host_mode

            percentage = snapshot.percentage
            remaining = snapshot.time_to_empty_s
            critical_signals: set[str] = set()
            if percentage is not None and percentage <= self.critical_percentage:
                critical_signals.add("percentage")
            if remaining is not None and remaining <= self.critical_time_s:
                critical_signals.add("time")

            if critical_signals:
                self._critical_signals.update(critical_signals)
                self._host_mode = PowerMode.CRITICAL
                return self._host_mode

            if self._host_mode is PowerMode.CRITICAL:
                # A trigger must itself recover. Treating a missing trigger as safe would let
                # flaky firmware clear the reserve exactly when its estimate becomes least
                # reliable.
                if "percentage" in self._critical_signals and (
                    percentage is None
                    or percentage <= self.critical_percentage + self.hysteresis_percentage
                ):
                    return self._host_mode
                if "time" in self._critical_signals and (
                    remaining is None or remaining <= self.critical_time_s + self.hysteresis_time_s
                ):
                    return self._host_mode

            self._critical_signals.clear()
            self._host_mode = PowerMode.ECO
            return self._host_mode

    def mode(self, *, enabled: bool = True) -> PowerMode:
        return self.host_mode() if enabled and self.globally_enabled else PowerMode.NORMAL

    def adjust_sampling(
        self,
        params: dict[str, Any],
        *,
        enabled: bool = True,
        requested_thinking: str | None = None,
    ) -> dict[str, Any]:
        """Return request params with energy concessions applied when safe.

        Explicit Extended reasoning is a learner choice, and structured marking can become
        invalid if clipped. Both bypass the concessions. Memory and thermal safety controls
        remain in force elsewhere regardless of this preference.
        """
        adjusted = dict(params)
        mode = self.mode(enabled=enabled)
        if (
            mode is PowerMode.NORMAL
            or requested_thinking == "extended"
            or "response_format" in adjusted
        ):
            return adjusted

        if mode is PowerMode.ECO:
            adjusted["max_tokens"] = min(
                int(adjusted.get("max_tokens") or self.eco_max_tokens),
                self.eco_max_tokens,
            )
            if requested_thinking != "off":
                if requested_thinking == "auto":
                    adjusted["enable_thinking"] = True
                current = adjusted.get("reasoning_budget_tokens")
                adjusted["reasoning_budget_tokens"] = min(
                    int(current) if current is not None else self.eco_reasoning_budget,
                    self.eco_reasoning_budget,
                )
            return adjusted

        adjusted["max_tokens"] = min(
            int(adjusted.get("max_tokens") or self.critical_max_tokens),
            self.critical_max_tokens,
        )
        adjusted["enable_thinking"] = False
        adjusted.pop("reasoning_budget_tokens", None)
        return adjusted

    def vision_allowed(self) -> bool:
        """Critical reserve protects text tutoring; a running vision request is not killed."""
        return self.host_mode() is not PowerMode.CRITICAL

    def tts_allowed(self) -> bool:
        # Like memory/thermal guards, critical reserve is host-wide. A learner may opt out of
        # shorter replies, but cannot spend the shared laptop's last reserve on speech playback.
        return self.host_mode() is not PowerMode.CRITICAL

    def status(self, *, enabled: bool = True) -> dict[str, Any]:
        snapshot = self.snapshot()
        host_mode = self.host_mode()
        mode = self.mode(enabled=enabled)
        actions: list[str] = []
        if mode is PowerMode.ECO:
            actions = ["limit_auto_reasoning", "limit_response_length"]
        elif mode is PowerMode.CRITICAL:
            actions = ["direct_responses", "limit_response_length"]
        if host_mode is PowerMode.CRITICAL:
            actions.extend(["pause_vision", "pause_tts"])
        return {
            "optimization_enabled": bool(enabled and self.globally_enabled),
            "available": snapshot.available,
            "mode": mode.value,
            "host_mode": host_mode.value,
            "on_battery": snapshot.on_battery,
            "external_power_connected": snapshot.external_power_connected,
            "charging": snapshot.charging,
            "percentage": snapshot.percentage,
            "energy_wh": snapshot.energy_wh,
            "energy_full_wh": snapshot.energy_full_wh,
            "energy_rate_w": snapshot.energy_rate_w,
            "time_to_empty_s": snapshot.time_to_empty_s,
            "source": snapshot.source,
            "actions": actions,
        }
