"""ConversationStore — persistence and ordering, no model required."""

from __future__ import annotations

from runtime.memory import ConversationStore


def test_messages_round_trip_in_order():
    store = ConversationStore(":memory:")
    cid = store.create_conversation("s1", mode="socratic")
    store.add_message(cid, "user", "hi")
    store.add_message(cid, "assistant", "hello")
    store.add_message(cid, "user", "bye")

    msgs = store.get_messages(cid)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert [m["content"] for m in msgs] == ["hi", "hello", "bye"]


def test_recent_limit_returns_last_n_chronologically():
    store = ConversationStore(":memory:")
    cid = store.create_conversation("s1")
    for i in range(5):
        store.add_message(cid, "user", f"m{i}")
    recent = store.get_messages(cid, limit=2)
    assert [m["content"] for m in recent] == ["m3", "m4"]


def test_conversations_scoped_to_student():
    store = ConversationStore(":memory:")
    a = store.create_conversation("alice")
    store.create_conversation("bob")
    assert [c["id"] for c in store.list_conversations("alice")] == [a]


def test_persists_across_reopen(tmp_path):
    db = tmp_path / "m.sqlite3"
    store = ConversationStore(db)
    cid = store.create_conversation("s1")
    store.add_message(cid, "user", "remember me")
    store.close()

    reopened = ConversationStore(db)
    assert reopened.get_messages(cid)[0]["content"] == "remember me"
