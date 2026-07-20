"""Tests for the measurement core.

`summarize()` is a port of upstream adtc_profiler.memory.MemorySampler.report(). A port can
drift, so `test_summarize_agrees_with_upstream` feeds the SAME synthetic series through both
implementations and asserts equality. That test is what makes the port safe.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import time

import pytest

from bench import sampler
from bench.adtc import install


def test_empty_series_is_all_zero():
    r = sampler.summarize([])
    assert (r.peak_rss_mb, r.steady_state_rss_mb, r.peak_vms_mb) == (0.0, 0.0, 0.0)


def test_peak_is_the_maximum_not_the_last():
    samples = [
        sampler.Sample(t=0.0, rss_mb=100.0, vms_mb=200.0),
        sampler.Sample(t=1.0, rss_mb=900.0, vms_mb=1800.0),
        sampler.Sample(t=2.0, rss_mb=300.0, vms_mb=600.0),
    ]
    r = sampler.summarize(samples)
    assert r.peak_rss_mb == 900.0
    assert r.peak_vms_mb == 1800.0


def test_steady_state_uses_last_half_for_short_runs():
    # duration 10s < 120s, so the window is duration/2 = 5s -> cutoff at t >= 5.0
    samples = [sampler.Sample(t=float(i), rss_mb=100.0 * i, vms_mb=0.0) for i in range(11)]
    # t in {5..10} -> rss {500,600,700,800,900,1000} -> mean 750.0
    assert sampler.summarize(samples).steady_state_rss_mb == 750.0


def test_steady_state_uses_last_60s_for_long_runs():
    # duration 200s >= 120s, so the window is a fixed 60s -> cutoff at t >= 140.0
    samples = [sampler.Sample(t=float(i), rss_mb=float(i), vms_mb=0.0) for i in range(201)]
    # t in {140..200} inclusive -> mean 170.0
    assert sampler.summarize(samples).steady_state_rss_mb == 170.0


def test_gb_properties_convert_from_mb():
    r = sampler.summarize([sampler.Sample(t=0.0, rss_mb=2048.0, vms_mb=4096.0)])
    assert r.peak_rss_gb == pytest.approx(2.0)
    assert r.steady_state_rss_gb == pytest.approx(2.0)


def test_tree_sampler_includes_children():
    """The scored number is the whole process tree, so a child's RSS must be counted."""
    parent = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import subprocess,sys,time;"
            "c=subprocess.Popen([sys.executable,'-c','import time;time.sleep(5)']);"
            "time.sleep(5)",
        ]
    )
    try:
        with sampler.sample_tree(parent.pid) as s:
            time.sleep(1.5)
        report = s.report()
    finally:
        parent.kill()
        parent.wait()
    assert report.peak_rss_mb > 0.0
    assert len(s.process_names()) >= 1


def test_tree_sampler_unions_sibling_roots():
    """Regression: llama-server is a SIBLING of the gateway, not a child.

    Sampling one root reported 0.06 GB when the engine alone was 0.55 GB (2026-07-20). Two
    independent roots must sum, or the scored footprint is silently understated.
    """
    a = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    b = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        with sampler.sample_tree(a.pid) as one:
            time.sleep(0.8)
        with sampler.sample_tree([a.pid, b.pid]) as both:
            time.sleep(0.8)
    finally:
        for proc in (a, b):
            proc.kill()
            proc.wait()

    single = one.report().peak_rss_mb
    union = both.report().peak_rss_mb
    assert union > single
    # Two near-identical interpreters: the union is close to double, never merely equal.
    assert union == pytest.approx(single * 2, rel=0.5)


def test_tree_sampler_deduplicates_overlapping_roots():
    """The same PID passed twice must not be counted twice."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        with sampler.sample_tree(proc.pid) as once:
            time.sleep(0.8)
        with sampler.sample_tree([proc.pid, proc.pid]) as twice:
            time.sleep(0.8)
    finally:
        proc.kill()
        proc.wait()
    assert twice.report().peak_rss_mb == pytest.approx(once.report().peak_rss_mb, rel=0.3)


def test_tree_sampler_survives_a_dead_process():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.3)"])
    with sampler.sample_tree(proc.pid) as s:
        time.sleep(1.0)  # outlives the target
    proc.wait()
    assert s.report().peak_rss_mb >= 0.0  # must not raise


def test_thermal_report_none_temp_is_not_zero():
    t = sampler.ThermalSampler()
    t._cpu_samples = [10.0, 20.0]
    t._temp_samples = []
    r = t.report()
    assert r.core_temp_c_peak is None
    assert r.throttled is False


def test_thermal_p99_matches_upstream_indexing():
    t = sampler.ThermalSampler()
    t._cpu_samples = [float(i) for i in range(100)]
    t._temp_samples = []
    # upstream: idx = max(0, int(len*0.99) - 1) = 98 -> sorted[98] == 98.0
    assert t.report().cpu_percent_p99 == 98.0


def _upstream_report(series: list[dict]) -> dict:
    code = textwrap.dedent(f"""
        import json
        from adtc_profiler.memory import MemorySampler, _Sample
        s = MemorySampler()
        s._samples = [_Sample(**d) for d in {series!r}]
        print(json.dumps(s.report()))
    """)
    return json.loads(install.run_python(code))


@pytest.mark.skipif(
    not install.is_installed(), reason="profiler venv not bootstrapped (run make profile once)"
)
def test_summarize_agrees_with_upstream():
    """Feed one series through upstream's report() and ours; they must agree exactly."""
    series = [
        {"t": 0.0, "rss_mb": 120.5, "vms_mb": 400.0},
        {"t": 30.0, "rss_mb": 2048.25, "vms_mb": 5000.0},
        {"t": 90.0, "rss_mb": 1900.0, "vms_mb": 4800.0},
        {"t": 150.0, "rss_mb": 1875.125, "vms_mb": 4750.0},
        {"t": 200.0, "rss_mb": 1860.0, "vms_mb": 4700.0},
    ]
    upstream = _upstream_report(series)
    ours = sampler.summarize([sampler.Sample(**d) for d in series])

    assert ours.peak_rss_mb == upstream["peak_rss_mb"]
    assert ours.steady_state_rss_mb == upstream["steady_state_rss_mb"]
    assert ours.peak_vms_mb == upstream["peak_vms_mb"]


@pytest.mark.skipif(
    not install.is_installed(), reason="profiler venv not bootstrapped (run make profile once)"
)
def test_summarize_agrees_with_upstream_on_a_short_run():
    """The <120s branch takes the other side of the min(), so it needs its own check."""
    series = [{"t": float(i), "rss_mb": 100.0 * i, "vms_mb": 0.0} for i in range(11)]
    upstream = _upstream_report(series)
    ours = sampler.summarize([sampler.Sample(**d) for d in series])
    assert ours.steady_state_rss_mb == upstream["steady_state_rss_mb"]
