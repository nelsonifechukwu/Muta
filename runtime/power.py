"""Host power sensing for Muta's battery-aware policy.

The product cares about the battery powering the *server laptop*, not the browser battery on
each connected phone.  Linux exposes that through ``/sys/class/power_supply`` without a
daemon or network dependency.  ``psutil.sensors_battery`` is a deliberately smaller fallback
for desktops where the kernel interface is absent or lives behind another OS API.

Every field is optional.  A driver may expose charge percentage but no power meter, and a
desktop may have no battery at all.  Unknown is represented as ``None``/``available=False``;
inventing a time-to-empty value would make the governor less safe than having no value.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class PowerSnapshot:
    available: bool = False
    on_battery: bool | None = None
    external_power_connected: bool | None = None
    charging: bool | None = None
    percentage: float | None = None
    energy_wh: float | None = None
    energy_full_wh: float | None = None
    energy_rate_w: float | None = None
    time_to_empty_s: int | None = None
    source: str = "unavailable"
    sampled_at: float = 0.0


class PowerProvider(Protocol):
    def snapshot(self) -> PowerSnapshot: ...


def _text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None


def _number(path: Path) -> float | None:
    raw = _text(path)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _micro_value(device: Path, name: str) -> float | None:
    value = _number(device / name)
    return None if value is None or value < 0 else value / 1_000_000.0


def _battery_rate_w(device: Path) -> float | None:
    direct = _micro_value(device, "power_now")
    if direct is not None:
        return abs(direct)
    current_ua = _number(device / "current_now")
    voltage_uv = _number(device / "voltage_now")
    if current_ua is None or voltage_uv is None:
        return None
    # µA × µV = 10⁻¹² W.
    return abs(current_ua * voltage_uv / 1_000_000_000_000.0)


@dataclass(frozen=True)
class _Battery:
    status: str | None
    percentage: float | None
    energy_wh: float | None
    energy_full_wh: float | None
    rate_w: float | None
    time_to_empty_s: int | None


def _read_battery(device: Path) -> _Battery:
    status = _text(device / "status")
    percentage = _number(device / "capacity")
    energy = _micro_value(device, "energy_now")
    energy_full = _micro_value(device, "energy_full")
    if energy is None:
        # Charge is useful only with voltage. Convert µAh × µV to Wh.
        charge_uah = _number(device / "charge_now")
        voltage_uv = _number(device / "voltage_now")
        if (
            charge_uah is not None
            and charge_uah >= 0
            and voltage_uv is not None
            and voltage_uv >= 0
        ):
            energy = charge_uah * voltage_uv / 1_000_000_000_000.0
    if energy_full is None:
        charge_full_uah = _number(device / "charge_full")
        voltage_uv = _number(device / "voltage_now")
        if (
            charge_full_uah is not None
            and charge_full_uah >= 0
            and voltage_uv is not None
            and voltage_uv >= 0
        ):
            energy_full = charge_full_uah * voltage_uv / 1_000_000_000_000.0
    time_value = _number(device / "time_to_empty_now")
    return _Battery(
        status=status,
        percentage=percentage,
        energy_wh=energy,
        energy_full_wh=energy_full,
        rate_w=_battery_rate_w(device),
        time_to_empty_s=int(time_value) if time_value is not None and time_value >= 0 else None,
    )


class LinuxPowerSupplyProvider:
    """Read the standard kernel power-supply class, aggregating multiple batteries."""

    def __init__(
        self,
        root: Path | str = "/sys/class/power_supply",
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.root = Path(root)
        self.clock = clock

    def snapshot(self) -> PowerSnapshot:
        try:
            devices = sorted(path for path in self.root.iterdir() if path.is_dir())
        except OSError:
            return PowerSnapshot(sampled_at=self.clock())

        batteries = [
            _read_battery(device)
            for device in devices
            if (_text(device / "type") or "").casefold() == "battery"
            and _text(device / "present") != "0"
        ]
        if not batteries:
            return PowerSnapshot(sampled_at=self.clock())

        ac_online = any(
            (_text(device / "type") or "").casefold()
            in {"mains", "usb", "usb_c", "usb_pd", "wireless"}
            and (_number(device / "online") or 0) > 0
            for device in devices
        )
        statuses = {(battery.status or "").casefold() for battery in batteries}
        charging = "charging" in statuses
        if "discharging" in statuses:
            # A weak adapter can be connected yet fail to meet system load. The battery is
            # still the reserve being consumed, so discharge wins for governor policy.
            on_battery = True
        elif statuses & {"charging", "full", "not charging"}:
            on_battery = False
        elif ac_online:
            on_battery = False
        else:
            on_battery = None

        # A partial aggregate is worse than unknown: one unmetered battery would make the
        # displayed energy and runtime look artificially low. Only sum a metric when every
        # present battery exposes it.
        energy = (
            sum(row.energy_wh for row in batteries if row.energy_wh is not None)
            if all(row.energy_wh is not None for row in batteries)
            else None
        )
        energy_full = (
            sum(row.energy_full_wh for row in batteries if row.energy_full_wh is not None)
            if all(row.energy_full_wh is not None for row in batteries)
            else None
        )
        rate = (
            sum(row.rate_w for row in batteries if row.rate_w is not None)
            if all(row.rate_w is not None for row in batteries)
            else None
        )

        if energy is not None and energy_full and energy_full > 0:
            percentage = max(0.0, min(100.0, 100.0 * energy / energy_full))
        else:
            percentages = [value for row in batteries if (value := row.percentage) is not None]
            percentage = sum(percentages) / len(percentages) if percentages else None
        if percentage is not None:
            percentage = max(0.0, min(100.0, percentage))

        explicit_times = [value for row in batteries if (value := row.time_to_empty_s) is not None]
        if explicit_times:
            # Simultaneous batteries drain together; summing their individual clocks would
            # double the estimate. The conservative minimum is more useful for policy.
            time_to_empty = min(explicit_times)
        elif on_battery is True and energy is not None and rate and rate > 0:
            time_to_empty = int(energy / rate * 3600)
        else:
            time_to_empty = None

        return PowerSnapshot(
            available=True,
            on_battery=on_battery,
            external_power_connected=ac_online,
            charging=charging,
            percentage=round(percentage, 2) if percentage is not None else None,
            energy_wh=round(energy, 3) if energy is not None else None,
            energy_full_wh=round(energy_full, 3) if energy_full is not None else None,
            energy_rate_w=round(rate, 3) if rate is not None else None,
            time_to_empty_s=time_to_empty,
            source="linux-sysfs",
            sampled_at=self.clock(),
        )


class PsutilPowerProvider:
    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self.clock = clock

    def snapshot(self) -> PowerSnapshot:
        try:
            import psutil

            battery = psutil.sensors_battery()
        except Exception:  # noqa: BLE001 - optional OS support must never break the tutor
            battery = None
        if battery is None:
            return PowerSnapshot(sampled_at=self.clock())
        seconds = battery.secsleft
        unknown = {
            getattr(psutil, "POWER_TIME_UNKNOWN", -2),
            getattr(psutil, "POWER_TIME_UNLIMITED", -1),
        }
        return PowerSnapshot(
            available=True,
            on_battery=not bool(battery.power_plugged),
            external_power_connected=bool(battery.power_plugged),
            # psutil exposes plugged/unplugged, not the charge controller's current state.
            charging=None,
            percentage=max(0.0, min(100.0, float(battery.percent))),
            time_to_empty_s=None if seconds in unknown or seconds < 0 else int(seconds),
            source="psutil",
            sampled_at=self.clock(),
        )


class SystemPowerProvider:
    """Prefer the richer Linux data, then fall back to psutil's portable subset."""

    def __init__(
        self,
        *,
        linux: PowerProvider | None = None,
        fallback: PowerProvider | None = None,
    ) -> None:
        self.linux = linux or LinuxPowerSupplyProvider()
        self.fallback = fallback or PsutilPowerProvider()

    def snapshot(self) -> PowerSnapshot:
        linux = self.linux.snapshot()
        return linux if linux.available else self.fallback.snapshot()
