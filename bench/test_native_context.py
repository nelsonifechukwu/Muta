from __future__ import annotations

from bench import target_box


def test_physical_core_count_uses_package_and_core(monkeypatch):
    values = {
        "/sys/devices/system/cpu/cpu0/topology/physical_package_id": "0",
        "/sys/devices/system/cpu/cpu0/topology/core_id": "0",
        "/sys/devices/system/cpu/cpu1/topology/physical_package_id": "0",
        "/sys/devices/system/cpu/cpu1/topology/core_id": "0",
        "/sys/devices/system/cpu/cpu2/topology/physical_package_id": "0",
        "/sys/devices/system/cpu/cpu2/topology/core_id": "1",
        "/sys/devices/system/cpu/cpu3/topology/physical_package_id": "0",
        "/sys/devices/system/cpu/cpu3/topology/core_id": "1",
    }
    monkeypatch.setattr(target_box, "_read", values.get)
    assert target_box._physical_cores([0, 1, 2, 3]) == 2


def test_host_swap_parser(monkeypatch):
    monkeypatch.setattr(
        target_box, "_read", lambda _path: "MemTotal: 100 kB\nSwapTotal: 0 kB\n"
    )
    assert target_box._host_swap_total_bytes() == 0
    assert target_box._host_memory_total_bytes() == 100 * 1024


def test_report_failure_propagates_to_process_status():
    assert target_box._report_failed({"llama_bench": {"rc": 1}}) is True
    assert target_box._report_failed({"sweeps": {"x": {"ok": False}}}) is True
    assert target_box._report_failed({"sweeps": {"x": {"error": "bad config"}}}) is True
    assert target_box._report_failed({"llama_bench": {"rc": 0}}) is False
