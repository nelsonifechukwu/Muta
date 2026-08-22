from __future__ import annotations

from dataclasses import dataclass

from orchestrator.gateway.power import PowerGovernor, PowerMode
from runtime.power import PowerSnapshot


@dataclass
class _Provider:
    value: PowerSnapshot
    calls: int = 0

    def snapshot(self) -> PowerSnapshot:
        self.calls += 1
        return self.value


def _governor(value: PowerSnapshot, **kw) -> tuple[PowerGovernor, _Provider]:
    provider = _Provider(value)
    governor = PowerGovernor(provider, poll_interval_s=1, **kw)
    return governor, provider


def test_ac_and_unknown_power_do_not_change_sampling():
    for snapshot in (
        PowerSnapshot(),
        PowerSnapshot(available=True, on_battery=False, percentage=20),
    ):
        governor, _ = _governor(snapshot)
        params = {"max_tokens": 1200, "enable_thinking": True}
        assert governor.mode() is PowerMode.NORMAL
        assert governor.adjust_sampling(params) == params


def test_eco_bounds_automatic_reasoning_and_response_length():
    governor, _ = _governor(PowerSnapshot(available=True, on_battery=True, percentage=60))

    adjusted = governor.adjust_sampling({"max_tokens": 1200}, requested_thinking="auto")

    assert governor.mode() is PowerMode.ECO
    assert adjusted["max_tokens"] == 800
    assert adjusted["enable_thinking"] is True
    assert adjusted["reasoning_budget_tokens"] == 256


def test_eco_preserves_an_unset_server_thinking_default():
    governor, _ = _governor(PowerSnapshot(available=True, on_battery=True, percentage=60))

    adjusted = governor.adjust_sampling({"max_tokens": 1200}, requested_thinking=None)

    assert adjusted["max_tokens"] == 800
    assert adjusted["reasoning_budget_tokens"] == 256
    assert "enable_thinking" not in adjusted


def test_critical_preserves_text_but_pauses_optional_expensive_features():
    governor, _ = _governor(
        PowerSnapshot(available=True, on_battery=True, percentage=9, time_to_empty_s=1200)
    )

    adjusted = governor.adjust_sampling(
        {"max_tokens": 1200, "reasoning_budget_tokens": 600},
        requested_thinking="auto",
    )
    status = governor.status()

    assert adjusted == {"max_tokens": 512, "enable_thinking": False}
    assert governor.vision_allowed() is False and governor.tts_allowed() is False
    assert status["mode"] == "critical"
    assert {"pause_vision", "pause_tts", "direct_responses"} <= set(status["actions"])


def test_explicit_extended_and_schema_constrained_work_keep_their_budget():
    governor, _ = _governor(PowerSnapshot(available=True, on_battery=True, percentage=5))
    extended = {"max_tokens": 3000, "reasoning_budget_tokens": 2048}
    marking = {"max_tokens": 1200, "response_format": {"type": "json_schema"}}

    assert governor.adjust_sampling(extended, requested_thinking="extended") == extended
    assert governor.adjust_sampling(marking) == marking


def test_learner_can_disable_request_concessions_but_not_host_safety():
    governor, _ = _governor(PowerSnapshot(available=True, on_battery=True, percentage=5))
    params = {"max_tokens": 1200}

    assert governor.mode(enabled=False) is PowerMode.NORMAL
    assert governor.adjust_sampling(params, enabled=False) == params
    status = governor.status(enabled=False)
    assert status["optimization_enabled"] is False
    assert status["mode"] == "normal" and status["host_mode"] == "critical"
    assert {"pause_vision", "pause_tts"} <= set(status["actions"])
    assert governor.vision_allowed() is False
    assert governor.tts_allowed() is False


def test_critical_mode_uses_hysteresis_before_recovery():
    now = [0.0]
    provider = _Provider(
        PowerSnapshot(available=True, on_battery=True, percentage=10, time_to_empty_s=1200)
    )
    governor = PowerGovernor(provider, poll_interval_s=1, clock=lambda: now[0])
    assert governor.mode() is PowerMode.CRITICAL

    provider.value = PowerSnapshot(
        available=True, on_battery=True, percentage=13, time_to_empty_s=2000
    )
    now[0] = 2.0
    assert governor.mode() is PowerMode.CRITICAL

    provider.value = PowerSnapshot(
        available=True, on_battery=True, percentage=16, time_to_empty_s=2800
    )
    now[0] = 4.0
    assert governor.mode() is PowerMode.ECO


def test_critical_mode_does_not_clear_on_transient_sensor_dropout():
    now = [0.0]
    provider = _Provider(PowerSnapshot(available=True, on_battery=True, percentage=10))
    governor = PowerGovernor(provider, poll_interval_s=1, clock=lambda: now[0])
    assert governor.mode() is PowerMode.CRITICAL

    provider.value = PowerSnapshot(available=True, on_battery=True)
    now[0] = 2.0
    assert governor.mode() is PowerMode.CRITICAL

    provider.value = PowerSnapshot(available=True, on_battery=None)
    now[0] = 4.0
    assert governor.mode() is PowerMode.CRITICAL


def test_critical_mode_uses_a_bounded_grace_for_total_provider_failure():
    now = [0.0]
    provider = _Provider(PowerSnapshot(available=True, on_battery=True, percentage=10))
    governor = PowerGovernor(
        provider,
        poll_interval_s=1,
        sensor_grace_s=120,
        clock=lambda: now[0],
    )
    assert governor.mode() is PowerMode.CRITICAL

    provider.value = PowerSnapshot()
    now[0] = 2.0
    assert governor.mode() is PowerMode.CRITICAL

    now[0] = 122.0
    assert governor.mode() is PowerMode.NORMAL


def test_critical_time_trigger_must_itself_recover_before_eco():
    now = [0.0]
    provider = _Provider(
        PowerSnapshot(available=True, on_battery=True, percentage=80, time_to_empty_s=1200)
    )
    governor = PowerGovernor(provider, poll_interval_s=1, clock=lambda: now[0])
    assert governor.mode() is PowerMode.CRITICAL

    provider.value = PowerSnapshot(
        available=True, on_battery=True, percentage=80, time_to_empty_s=None
    )
    now[0] = 2.0
    assert governor.mode() is PowerMode.CRITICAL

    provider.value = PowerSnapshot(
        available=True, on_battery=True, percentage=80, time_to_empty_s=2800
    )
    now[0] = 4.0
    assert governor.mode() is PowerMode.ECO


def test_snapshot_polling_is_bounded():
    now = [0.0]
    provider = _Provider(PowerSnapshot(available=True, on_battery=False))
    governor = PowerGovernor(provider, poll_interval_s=15, clock=lambda: now[0])

    governor.snapshot()
    governor.snapshot()
    assert provider.calls == 1
    now[0] = 16.0
    governor.snapshot()
    assert provider.calls == 2
