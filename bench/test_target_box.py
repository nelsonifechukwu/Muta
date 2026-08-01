"""Unit coverage for the pure parts of bench/target_box.py — no docker, no engine.

The container-shaped stages (llama-bench, sweeps) are exercised by
scripts/bench_target_box.sh itself; what belongs here is the plumbing whose silent
failure would mislabel a benchmark: cgroup-limit parsing and the pins fallback that
keeps the bandwidth ceiling meaningful when the model file is absent.
"""

from __future__ import annotations

from bench import target_box


def test_cgroup_bytes_v2_max_means_unlimited(tmp_path):
    p = tmp_path / "memory.max"
    p.write_text("max\n")
    assert target_box._cgroup_bytes(str(p)) is None


def test_cgroup_bytes_v1_sentinel_means_unlimited(tmp_path):
    p = tmp_path / "memory.limit_in_bytes"
    p.write_text(str(2**63 - 4096))  # v1 reports "no limit" as PAGE_COUNTER_MAX
    assert target_box._cgroup_bytes(str(p)) is None


def test_cgroup_bytes_first_readable_real_limit_wins(tmp_path):
    absent = tmp_path / "absent"
    real = tmp_path / "real"
    real.write_text(str(8 * 2**30))
    assert target_box._cgroup_bytes(str(absent), str(real)) == 8 * 2**30


def test_pinned_core_bytes_reads_the_lockfile():
    size = target_box._pinned_core_bytes()
    # The committed pins.lock.json must yield the 4B core's size even with no GGUF on
    # disk — that is what keeps est_decode_ceiling_tps available on a modelless host.
    assert isinstance(size, int) and size > 2**30


def test_default_threads_are_deduplicated_and_positive():
    threads = target_box._default_threads()
    assert threads == sorted(set(threads))
    assert all(t >= 1 for t in threads)
