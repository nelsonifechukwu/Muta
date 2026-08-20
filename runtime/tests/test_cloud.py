"""CloudFallbackClient — cloud when online, silent local fallback before the first token.

Policy under test (design P3, 2026-08-08): offline or unknown connectivity → local, no
cloud attempt; transient cloud failure before ANY streamed chunk → local passthrough;
permanent cloud request/auth 4xx → propagate without hiding it behind a local answer;
mid-stream failure → propagate (ChatEngine's same-row recovery path owns it);
non-streaming → any cloud exception falls back to local.
"""

from __future__ import annotations

import httpx
import pytest

from runtime.cloud import CloudFallbackClient


class FakeStreamClient:
    def __init__(self, events=None, fail_after: int | None = None, exc=None, token_count=17):
        self.events = events or []
        self.fail_after = fail_after  # raise after yielding this many events
        self.exc = exc or ConnectionError("cloud down")
        self.token_count = token_count
        self.calls = 0

    def stream_events(self, messages, **params):
        self.calls += 1
        if self.fail_after == 0:
            raise self.exc
        for i, ev in enumerate(self.events, start=1):
            yield ev
            if self.fail_after is not None and i >= self.fail_after:
                raise self.exc

    def stream(self, messages, **params):
        for kind, text in self.stream_events(messages, **params):
            if kind == "content":
                yield text

    def chat_with_timings(self, messages, **params):
        self.calls += 1
        if self.fail_after == 0:
            raise self.exc
        return "generation"

    def count_prompt_tokens(self, messages, **params):
        self.calls += 1
        return self.token_count


CLOUD_EVENTS = [("content", "from "), ("content", "cloud")]
LOCAL_EVENTS = [("reasoning", "hmm "), ("content", "from local")]


def _tagged(events, source):
    return [("source", source), *events]


def _client(cloud, local, online=True):
    return CloudFallbackClient(cloud=cloud, local=local, online=lambda: online)


def test_cloud_serves_when_online():
    cloud, local = FakeStreamClient(CLOUD_EVENTS), FakeStreamClient(LOCAL_EVENTS)
    c = _client(cloud, local)
    assert list(c.stream_events([])) == _tagged(CLOUD_EVENTS, "cloud")
    assert c.last_source == "cloud"
    assert local.calls == 0


@pytest.mark.parametrize("verdict", [False, None])
def test_offline_or_unknown_goes_local_without_a_cloud_attempt(verdict):
    cloud, local = FakeStreamClient(CLOUD_EVENTS), FakeStreamClient(LOCAL_EVENTS)
    c = _client(cloud, local, online=verdict)
    assert list(c.stream_events([])) == _tagged(LOCAL_EVENTS, "local")
    assert c.last_source == "local"
    assert cloud.calls == 0


def test_cloud_failure_before_first_chunk_discloses_egress_then_falls_back():
    cloud = FakeStreamClient(CLOUD_EVENTS, fail_after=0)
    local = FakeStreamClient(LOCAL_EVENTS)
    c = _client(cloud, local)
    assert list(c.stream_events([])) == [
        ("source", "cloud"),
        *_tagged(LOCAL_EVENTS, "local"),
    ]
    assert c.last_source == "local"


def test_permanent_cloud_4xx_does_not_hide_a_bad_request_with_local_fallback():
    request = httpx.Request("POST", "https://cloud.invalid/v1/chat/completions")
    response = httpx.Response(400, request=request)
    cloud = FakeStreamClient(
        CLOUD_EVENTS,
        fail_after=0,
        exc=httpx.HTTPStatusError("bad request", request=request, response=response),
    )
    local = FakeStreamClient(LOCAL_EVENTS)
    c = _client(cloud, local)

    with pytest.raises(httpx.HTTPStatusError):
        list(c.stream_events([]))
    assert local.calls == 0


def test_mid_stream_cloud_failure_propagates_after_the_prefix():
    cloud = FakeStreamClient(CLOUD_EVENTS, fail_after=1)
    local = FakeStreamClient(LOCAL_EVENTS)
    c = _client(cloud, local)
    got = []
    with pytest.raises(ConnectionError):
        for ev in c.stream_events([]):
            got.append(ev)  # noqa: PERF402 — retain the prefix emitted before the expected error
    assert got == [("source", "cloud"), CLOUD_EVENTS[0]]
    assert local.calls == 0, "a half-streamed reply must not silently restart elsewhere"


def test_explicit_retry_after_cloud_drop_resumes_on_local():
    cloud = FakeStreamClient(CLOUD_EVENTS, fail_after=1)
    local = FakeStreamClient(LOCAL_EVENTS)
    c = _client(cloud, local)

    assert list(c.retry_stream_events([{"role": "user", "content": "continue"}])) == _tagged(
        LOCAL_EVENTS, "local"
    )
    assert c.last_source == "local"
    assert cloud.calls == 0
    assert local.calls == 1


def test_cloud_disclosure_survives_a_local_midstream_resume():
    cloud = FakeStreamClient(CLOUD_EVENTS, fail_after=1)
    local = FakeStreamClient(LOCAL_EVENTS)
    c = _client(cloud, local)

    events = c.stream_events([{"role": "user", "content": "question"}])
    assert next(events) == ("source", "cloud")
    assert next(events) == CLOUD_EVENTS[0]
    with pytest.raises(ConnectionError, match="cloud down"):
        next(events)
    resumed = list(c.retry_stream_events([{"role": "user", "content": "resume"}]))
    assert resumed == _tagged(LOCAL_EVENTS, "local")
    # Streamed provenance is carried in-band and kept sticky by the route per job.
    assert c.last_source == "local"


def test_stream_yields_only_content():
    c = _client(FakeStreamClient(CLOUD_EVENTS), FakeStreamClient(LOCAL_EVENTS))
    assert list(c.stream([])) == ["from ", "cloud"]


def test_chat_with_timings_falls_back_on_cloud_exception():
    cloud = FakeStreamClient(fail_after=0)
    local = FakeStreamClient()
    c = _client(cloud, local)
    assert c.chat_with_timings([]) == "generation"
    assert c.last_source == "local"


def test_context_fitting_always_uses_the_local_model_tokenizer():
    cloud = FakeStreamClient(token_count=999)
    local = FakeStreamClient(token_count=23)
    c = _client(cloud, local, online=True)

    assert c.count_prompt_tokens([{"role": "user", "content": "question"}]) == 23
    assert cloud.calls == 0
    assert local.calls == 1
