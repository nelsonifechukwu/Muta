from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from pydantic import ValidationError

from runtime.config import RuntimeConfig
from runtime.power import LinuxPowerSupplyProvider, PowerSnapshot, SystemPowerProvider


def _supply(root: Path, name: str, **values: object) -> Path:
    device = root / name
    device.mkdir()
    for key, value in values.items():
        (device / key).write_text(f"{value}\n", encoding="utf-8")
    return device


def test_linux_provider_reads_whole_host_battery_state(tmp_path):
    _supply(
        tmp_path,
        "BAT0",
        type="Battery",
        present=1,
        status="Discharging",
        energy_now=30_000_000,
        energy_full=60_000_000,
        power_now=10_000_000,
    )
    _supply(tmp_path, "AC", type="Mains", online=0)

    value = LinuxPowerSupplyProvider(tmp_path, clock=lambda: 123.0).snapshot()

    assert value.available is True and value.on_battery is True
    assert value.percentage == 50.0
    assert value.energy_wh == 30.0 and value.energy_rate_w == 10.0
    assert value.time_to_empty_s == 10_800
    assert value.source == "linux-sysfs" and value.sampled_at == 123.0


def test_linux_provider_uses_capacity_when_driver_has_no_energy_meter(tmp_path):
    _supply(
        tmp_path,
        "BAT0",
        type="Battery",
        status="Unknown",
        capacity=71,
    )

    value = LinuxPowerSupplyProvider(tmp_path).snapshot()

    assert value.available is True
    assert value.percentage == 71.0
    assert value.on_battery is None
    assert value.energy_rate_w is None and value.time_to_empty_s is None


def test_weak_adapter_does_not_hide_an_actively_discharging_battery(tmp_path):
    _supply(
        tmp_path,
        "BAT0",
        type="Battery",
        status="Discharging",
        capacity=80,
    )
    _supply(tmp_path, "ACAD", type="Mains", online=1)

    value = LinuxPowerSupplyProvider(tmp_path).snapshot()

    assert value.external_power_connected is True
    assert value.on_battery is True


def test_full_battery_is_plugged_but_not_actively_charging(tmp_path):
    _supply(tmp_path, "BAT0", type="Battery", status="Full", capacity=100)
    _supply(tmp_path, "AC", type="Mains", online=1)

    value = LinuxPowerSupplyProvider(tmp_path).snapshot()

    assert value.on_battery is False
    assert value.external_power_connected is True
    assert value.charging is False


def test_multiple_batteries_are_energy_weighted(tmp_path):
    _supply(
        tmp_path,
        "BAT0",
        type="Battery",
        status="Discharging",
        energy_now=10_000_000,
        energy_full=20_000_000,
        power_now=4_000_000,
    )
    _supply(
        tmp_path,
        "BAT1",
        type="Battery",
        status="Discharging",
        energy_now=30_000_000,
        energy_full=60_000_000,
        power_now=6_000_000,
    )

    value = LinuxPowerSupplyProvider(tmp_path).snapshot()

    assert value.energy_wh == 40.0 and value.energy_full_wh == 80.0
    assert value.percentage == 50.0 and value.energy_rate_w == 10.0
    assert value.time_to_empty_s == 14_400


def test_partial_multi_battery_meter_does_not_publish_a_false_runtime(tmp_path):
    _supply(
        tmp_path,
        "BAT0",
        type="Battery",
        status="Discharging",
        capacity=50,
        energy_now=10_000_000,
        energy_full=20_000_000,
        power_now=5_000_000,
    )
    _supply(tmp_path, "BAT1", type="Battery", status="Discharging", capacity=70)

    value = LinuxPowerSupplyProvider(tmp_path).snapshot()

    assert value.percentage == 60.0
    assert value.energy_wh is None and value.energy_rate_w is None
    assert value.time_to_empty_s is None


def test_no_battery_is_unavailable_not_full(tmp_path):
    _supply(tmp_path, "AC", type="Mains", online=1)

    value = LinuxPowerSupplyProvider(tmp_path).snapshot()

    assert value.available is False
    assert value.percentage is None and value.on_battery is None


@dataclass
class _Provider:
    value: PowerSnapshot

    def snapshot(self) -> PowerSnapshot:
        return self.value


def test_system_provider_falls_back_only_when_linux_has_no_battery():
    fallback = PowerSnapshot(available=True, percentage=44, source="fallback")
    system = SystemPowerProvider(linux=_Provider(PowerSnapshot()), fallback=_Provider(fallback))
    assert system.snapshot() is fallback

    linux = PowerSnapshot(available=True, percentage=55, source="linux")
    system = SystemPowerProvider(linux=_Provider(linux), fallback=_Provider(fallback))
    assert system.snapshot() is linux


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("MUTA_RT_POWER_CRITICAL_PERCENTAGE", "101"),
        ("MUTA_RT_POWER_CRITICAL_TIME_S", "-1"),
        ("MUTA_RT_POWER_CRITICAL_MAX_TOKENS", "-1"),
    ],
)
def test_invalid_power_environment_values_fail_closed(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        RuntimeConfig(_env_file=None)


def test_power_hysteresis_must_have_a_reachable_recovery_threshold(monkeypatch):
    monkeypatch.setenv("MUTA_RT_POWER_CRITICAL_PERCENTAGE", "99")
    monkeypatch.setenv("MUTA_RT_POWER_HYSTERESIS_PERCENTAGE", "1")
    with pytest.raises(ValidationError):
        RuntimeConfig(_env_file=None)
