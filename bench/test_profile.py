"""Tests for the product-path pass — the path that can OOM.

No live server: the HTTP call is stubbed. What is tested is the aggregation and the failure
handling, which is where a wrong number would come from.
"""

from __future__ import annotations

import os

import httpx
import pytest

from bench import profile


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "boom", request=httpx.Request("POST", "http://x"), response=None
            )

    def json(self):
        return self._payload


def _ok(tps: float = 10.0):
    return _FakeResponse(
        {
            "student_id": "bench",
            "conversation_id": "c1",
            "reply": "a reply",
            "_timings": {"tokens_per_second": tps},
        }
    )


def test_aggregates_tps_across_prompts(monkeypatch):
    monkeypatch.setattr(profile.httpx, "post", lambda url, **k: _ok(11.0))
    monkeypatch.setattr(profile, "_collect_metrics", lambda base: {"avg_tps": 12.0})

    result = profile.run_product_path(
        pid=os.getpid(),
        prompts=[{"prompt_id": "a", "prompt": "x"}, {"prompt_id": "b", "prompt": "y"}],
        warmup=False,
    )
    assert result.run.source == "product"
    assert result.run.tps_actual == 12.0  # the app's rolling window wins
    assert len(result.replies) == 2
    assert result.errors == []


def test_measures_rss_of_the_given_tree(monkeypatch):
    monkeypatch.setattr(profile.httpx, "post", lambda url, **k: _ok())
    monkeypatch.setattr(profile, "_collect_metrics", lambda base: {"avg_tps": 8.0})
    result = profile.run_product_path(
        pid=os.getpid(), prompts=[{"prompt_id": "a", "prompt": "x"}], warmup=False
    )
    # This test process has a real RSS; a zero here means the sampler was never attached.
    assert result.run.peak_rss_gb > 0.0


def test_an_http_failure_is_recorded_not_swallowed(monkeypatch):
    def refuse(url, **kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(profile.httpx, "post", refuse)
    monkeypatch.setattr(profile, "_collect_metrics", lambda base: None)
    result = profile.run_product_path(
        pid=os.getpid(), prompts=[{"prompt_id": "a", "prompt": "x"}], warmup=False
    )
    assert result.errors
    assert result.run.oom_or_crash is True
    assert result.run.tps_actual == 0.0


def test_falls_back_to_response_timings_when_the_endpoint_is_absent(monkeypatch):
    monkeypatch.setattr(profile.httpx, "post", lambda url, **k: _ok(9.5))
    monkeypatch.setattr(profile, "_collect_metrics", lambda base: None)
    result = profile.run_product_path(
        pid=os.getpid(), prompts=[{"prompt_id": "a", "prompt": "x"}], warmup=False
    )
    assert result.run.tps_actual == pytest.approx(9.5)
    assert result.run.tps_from_wall_clock is True


def test_no_prompts_defaults_to_the_checked_in_two(monkeypatch):
    seen = []

    def capture(url, **kwargs):
        seen.append(kwargs["json"]["message"])
        return _ok()

    monkeypatch.setattr(profile.httpx, "post", capture)
    monkeypatch.setattr(profile, "_collect_metrics", lambda base: {"avg_tps": 5.0})
    profile.run_product_path(pid=os.getpid(), warmup=False)
    assert len(seen) == 2
