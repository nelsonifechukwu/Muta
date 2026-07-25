"""ConversationStore against a real Postgres (fixture in conftest.py; skips when PG is down)."""

from __future__ import annotations

from runtime.memory import ConversationStore


def test_messages_round_trip_in_order(store: ConversationStore):
    cid = store.create_conversation("s1", mode="socratic")
    store.add_message(cid, "user", "hi")
    store.add_message(cid, "assistant", "hello")
    store.add_message(cid, "user", "bye")

    msgs = store.get_messages(cid)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert [m["content"] for m in msgs] == ["hi", "hello", "bye"]


def test_recent_limit_returns_last_n_chronologically(store: ConversationStore):
    cid = store.create_conversation("s1")
    for i in range(5):
        store.add_message(cid, "user", f"m{i}")
    recent = store.get_messages(cid, limit=2)
    assert [m["content"] for m in recent] == ["m3", "m4"]


def test_conversations_scoped_to_student(store: ConversationStore):
    a = store.create_conversation("alice")
    store.create_conversation("bob")
    assert [c["id"] for c in store.list_conversations("alice")] == [a]


def test_persists_across_reconnect(store: ConversationStore):
    cid = store.create_conversation("s1", title="t")
    store.add_message(cid, "user", "remember me")
    dsn = store.dsn
    store.close()

    reopened = ConversationStore(dsn)
    try:
        assert reopened.get_conversation(cid)["title"] == "t"
        assert reopened.get_messages(cid)[0]["content"] == "remember me"
    finally:
        reopened.close()


def test_add_message_returns_monotonic_ids_and_bumps_updated_at(store: ConversationStore):
    cid = store.create_conversation("s1")
    before = store.get_conversation(cid)["updated_at"]
    first = store.add_message(cid, "user", "a")
    second = store.add_message(cid, "assistant", "b")
    assert second > first
    assert store.get_conversation(cid)["updated_at"] >= before


def test_delete_conversation_cascades(store: ConversationStore):
    cid = store.create_conversation("s1")
    mid = store.add_message(cid, "user", "hi")
    aid = store.add_attachment(
        "image", "image/png", b"\x89PNG", conversation_id=cid, message_id=mid
    )

    store.delete_conversation(cid)
    assert store.get_conversation(cid) is None
    assert store.get_messages(cid) == []
    assert store.get_attachment(aid) is None


def test_attachment_round_trip_and_linking(store: ConversationStore):
    aid = store.add_attachment("audio", "audio/webm", b"\x1a\x45")
    got = store.get_attachment(aid)
    assert got["kind"] == "audio"
    assert got["mime"] == "audio/webm"
    assert bytes(got["data"]) == b"\x1a\x45"
    assert got["conversation_id"] is None

    cid = store.create_conversation("s1")
    mid = store.add_message(cid, "user", "listen to this")
    store.link_attachment(aid, cid, mid)
    got = store.get_attachment(aid)
    assert got["conversation_id"] == cid
    assert got["message_id"] == mid


def test_list_messages_includes_ids_and_attachment_refs(store: ConversationStore):
    cid = store.create_conversation("s1")
    m1 = store.add_message(cid, "user", "look")
    store.add_message(cid, "assistant", "I see")
    aid = store.add_attachment(
        "image", "image/jpeg", b"\xff\xd8", conversation_id=cid, message_id=m1
    )

    msgs = store.list_messages(cid)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["id"] == m1
    assert msgs[0]["attachments"] == [{"id": aid, "kind": "image", "mime": "image/jpeg"}]
    assert msgs[1]["attachments"] == []


def test_set_title_only_when_unset(store: ConversationStore):
    cid = store.create_conversation("s1")
    store.set_title(cid, "first message")
    store.set_title(cid, "should not overwrite")
    assert store.get_conversation(cid)["title"] == "first message"


def test_settings_round_trip(store: ConversationStore):
    assert store.get_settings("s1") == {}
    store.put_settings("s1", {"theme": "warm", "tts": True})
    assert store.get_settings("s1") == {"theme": "warm", "tts": True}
    store.put_settings("s1", {"theme": "dark"})
    assert store.get_settings("s1") == {"theme": "dark"}
