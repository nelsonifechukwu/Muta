"""CloudFallbackClient — cloud when online, silent local fallback before the first token.

Policy under test (design P3, 2026-08-08): offline or unknown connectivity → local, no
cloud attempt; cloud failure before ANY streamed chunk → local passthrough, silently;
mid-stream failure → propagate (the dropped-stream partial-persist path owns it);
non-streaming → any cloud exception falls back to local.
"""

from __future__ import annotations

import pytest

from runtime.cloud import CloudFallbackClient


class FakeStreamClient:
    def __init__(self, events=None, fail_after: int | None = None, exc=None):
        self.events = events or []
        self.fail_after = fail_after  # raise after yielding this many events
        self.exc = exc or ConnectionError("cloud down")
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


CLOUD_EVENTS = [("content", "from "), ("content", "cloud")]
LOCAL_EVENTS = [("reasoning", "hmm "), ("content", "from local")]


def _client(cloud, local, online=True):
    return CloudFallbackClient(cloud=cloud, local=local, online=lambda: online)


def test_cloud_serves_when_online():
    cloud, local = FakeStreamClient(CLOUD_EVENTS), FakeStreamClient(LOCAL_EVENTS)
    c = _client(cloud, local)
    assert list(c.stream_events([], )) == CLOUD_EVENTS
    assert c.last_source == "cloud"
    assert local.calls == 0


@pytest.mark.parametrize("verdict", [False, None])
def test_offline_or_unknown_goes_local_without_a_cloud_attempt(verdict):
    cloud, local = FakeStreamClient(CLOUD_EVENTS), FakeStreamClient(LOCAL_EVENTS)
    c = _client(cloud, local, online=verdict)
    assert list(c.stream_events([])) == LOCAL_EVENTS
    assert c.last_source == "local"
    assert cloud.calls == 0


def test_cloud_failure_before_first_chunk_falls_back_silently():
    cloud = FakeStreamClient(CLOUD_EVENTS, fail_after=0)
    local = FakeStreamClient(LOCAL_EVENTS)
    c = _client(cloud, local)
    assert list(c.stream_events([])) == LOCAL_EVENTS
    assert c.last_source == "local"


def test_mid_stream_cloud_failure_propagates_after_the_prefix():
    cloud = FakeStreamClient(CLOUD_EVENTS, fail_after=1)
    local = FakeStreamClient(LOCAL_EVENTS)
    c = _client(cloud, local)
    got = []
    with pytest.raises(ConnectionError):
        for ev in c.stream_events([]):
            got.append(ev)
    assert got == [CLOUD_EVENTS[0]]
    assert local.calls == 0, "a half-streamed reply must not silently restart elsewhere"


def test_stream_yields_only_content():
    c = _client(FakeStreamClient(CLOUD_EVENTS), FakeStreamClient(LOCAL_EVENTS))
    assert list(c.stream([])) == ["from ", "cloud"]


def test_chat_with_timings_falls_back_on_cloud_exception():
    cloud = FakeStreamClient(fail_after=0)
    local = FakeStreamClient()
    c = _client(cloud, local)
    assert c.chat_with_timings([]) == "generation"
    assert c.last_source == "local"
