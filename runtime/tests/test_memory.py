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


def test_first_user_message_reads_only_the_opening_user_turn(store: ConversationStore):
    cid = store.create_conversation("s1")
    store.add_message(cid, "assistant", "preamble")
    store.add_message(cid, "user", "opening question")
    store.add_message(cid, "assistant", "answer")
    store.add_message(cid, "user", "follow-up")

    first = store.get_first_user_message(cid)

    assert first is not None
    assert first["role"] == "user"
    assert first["content"] == "opening question"
    assert store.get_first_user_message("missing") is None


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


def test_settings_patch_preserves_independent_controls(store: ConversationStore):
    assert store.patch_settings("s1", {"allow_parallel_chats": False}) == {
        "allow_parallel_chats": False
    }
    assert store.patch_settings("s1", {"power_optimization_enabled": False}) == {
        "allow_parallel_chats": False,
        "power_optimization_enabled": False,
    }


# --- ownership & erasure (production-hardening) -----------------------------------------


def test_get_attachment_owner_scoping(store: ConversationStore):
    # Uploaded by alice, unlinked: only alice (or no-owner-check) may read it.
    aid = store.add_attachment("image", "image/png", b"\x89PNG", owner_id="alice")
    assert store.get_attachment(aid, owner_id="alice") is not None
    assert store.get_attachment(aid, owner_id="bob") is None
    assert store.get_attachment(aid) is not None  # no owner filter = unchecked (internal)


def test_get_attachment_owner_via_linked_conversation(store: ConversationStore):
    # An attachment with no owner_id is still reachable by the owner of its conversation.
    cid = store.create_conversation("alice")
    mid = store.add_message(cid, "user", "see this")
    aid = store.add_attachment(
        "image", "image/png", b"\x89PNG", conversation_id=cid, message_id=mid
    )
    assert store.get_attachment(aid, owner_id="alice") is not None
    assert store.get_attachment(aid, owner_id="mallory") is None


def test_link_attachment_cannot_claim_another_students_upload(store: ConversationStore):
    alice_conversation = store.create_conversation("alice")
    alice_message = store.add_message(alice_conversation, "user", "look")
    bob_attachment = store.add_attachment("image", "image/png", b"bob-private", owner_id="bob")

    store.link_attachment(
        bob_attachment,
        alice_conversation,
        alice_message,
        owner_id="alice",
    )

    row = store.get_attachment(bob_attachment, owner_id="bob")
    assert row is not None and row["conversation_id"] is None
    assert store.get_attachment(bob_attachment, owner_id="alice") is None


def test_student_deletion_removes_historical_cross_linked_uploads(store: ConversationStore):
    victim_conversation = store.create_conversation("victim")
    attachment = store.add_attachment(
        "audio",
        "audio/webm",
        b"attacker-owned",
        conversation_id=victim_conversation,
        owner_id="attacker",
    )

    counts = store.delete_student("attacker")

    assert counts["orphan_attachments"] == 1
    assert store.get_attachment(attachment) is None
    assert store.get_conversation(victim_conversation) is not None


def test_delete_conversation_owner_scoped(store: ConversationStore):
    cid = store.create_conversation("alice")
    # A non-owner's delete removes nothing and reports it.
    assert store.delete_conversation(cid, owner_id="mallory") is False
    assert store.get_conversation(cid) is not None
    # The owner's delete succeeds and reports it.
    assert store.delete_conversation(cid, owner_id="alice") is True
    assert store.get_conversation(cid) is None
    # Deleting again (now nonexistent) reports False, not a false success.
    assert store.delete_conversation(cid, owner_id="alice") is False


def test_delete_student_erases_all_owned_data(store: ConversationStore):
    cid = store.create_conversation("alice")
    store.add_message(cid, "user", "hi")
    linked = store.add_attachment(
        "image", "image/png", b"\x89PNG", conversation_id=cid, owner_id="alice"
    )
    orphan = store.add_attachment("audio", "audio/webm", b"\x1a\x45", owner_id="alice")
    store.put_settings("alice", {"theme": "dark"})
    # bob's data is untouched.
    bob_cid = store.create_conversation("bob")

    counts = store.delete_student("alice")
    assert counts["conversations"] == 1
    # Frozen field name; deletion now counts every directly-owned attachment so even a
    # historical cross-link into someone else's conversation cannot survive account removal.
    assert counts["orphan_attachments"] == 2
    assert counts["settings"] == 1
    assert store.get_conversation(cid) is None
    assert store.get_attachment(linked) is None
    assert store.get_attachment(orphan) is None
    assert store.get_settings("alice") == {}
    assert store.get_conversation(bob_cid) is not None


def test_reap_orphan_attachments_only_unlinked(store: ConversationStore):
    cid = store.create_conversation("alice")
    linked = store.add_attachment("image", "image/png", b"\x89PNG", conversation_id=cid)
    orphan = store.add_attachment("image", "image/png", b"\x89PNG", owner_id="alice")
    # Nothing is old enough to reap yet.
    assert store.reap_orphan_attachments(older_than_seconds=3600) == 0
    assert store.get_attachment(orphan) is not None
    # Everything already created is "older than -1s"; the linked one is exempt.
    assert store.reap_orphan_attachments(older_than_seconds=-1) == 1
    assert store.get_attachment(orphan) is None
    assert store.get_attachment(linked) is not None
