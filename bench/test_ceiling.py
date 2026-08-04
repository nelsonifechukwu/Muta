"""Ceiling math is pure arithmetic — test it exactly; smoke the bandwidth probe."""

from bench.ceiling import ceiling_tps, measure_copy_bandwidth_bytes_s


def test_ceiling_tps_exact():
    # 60 GB/s over a 355 MB model -> the cactus blog's ~169 tok/s iPhone ceiling.
    assert round(ceiling_tps(60e9, 355e6), 0) == 169


def test_ceiling_tps_zero_guard():
    assert ceiling_tps(60e9, 0) == float("inf")


def test_bandwidth_probe_returns_plausible_number():
    # 64 MiB keeps the test fast; any machine that can run the stack moves >1 GiB/s.
    bw = measure_copy_bandwidth_bytes_s(size_mib=64, passes=2)
    assert bw > 2**30
