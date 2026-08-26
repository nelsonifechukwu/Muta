"""The portable SQLite store must match the Postgres ConversationStore contract."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from runtime.memory import ConversationStore
from runtime.sqlite_memory import _LATEST_SCHEMA_VERSION, SQLiteConversationStore, path_from_dsn
from runtime.tests import test_memory as contract


@pytest.fixture
def store(tmp_path):
    instance = ConversationStore(f"sqlite:///{tmp_path / 'muta.sqlite3'}")
    yield instance
    instance.close()


def test_factory_selects_sqlite(store):
    assert isinstance(store, SQLiteConversationStore)
    assert store.ping() is True


def test_relative_and_absolute_dsn_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert path_from_dsn("sqlite:///data/muta.sqlite3") == "data/muta.sqlite3"
    assert path_from_dsn("sqlite:////tmp/muta.sqlite3") == "/tmp/muta.sqlite3"
    relative = ConversationStore("sqlite:///data/muta.sqlite3")
    try:
        assert Path("data/muta.sqlite3").is_file()
    finally:
        relative.close()


def test_migrates_original_sqlite_database_in_place(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE conversations (
            id TEXT PRIMARY KEY, student_id TEXT NOT NULL, mode TEXT, persona TEXT,
            subject TEXT, language TEXT, title TEXT, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL
        );
        """
    )
    connection.close()

    store = ConversationStore(f"sqlite:///{path}")
    try:
        attachment = store.add_attachment("image", "image/png", b"png", owner_id="alice")
        assert store.get_attachment(attachment, owner_id="alice") is not None
        versions = store._conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        assert [row[0] for row in versions] == list(range(1, _LATEST_SCHEMA_VERSION + 1))
        assert "pinned" in {
            row[1] for row in store._conn.execute("PRAGMA table_info(conversations)").fetchall()
        }
        assert "completion_state" in {
            row[1] for row in store._conn.execute("PRAGMA table_info(messages)").fetchall()
        }
        legacy = store.create_conversation("alice", title="migrated")
        assert store.set_conversation_pinned(legacy, owner_id="alice", pinned=True)
        assert bool(store.get_conversation(legacy)["pinned"])
    finally:
        store.close()


@pytest.mark.parametrize("preview_column", ["pinned", "completion_state"])
def test_migration_five_reconciles_colliding_preview_version_four(tmp_path, preview_column):
    path = tmp_path / f"preview-{preview_column}.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE conversations (
            id TEXT PRIMARY KEY, student_id TEXT NOT NULL, mode TEXT, persona TEXT,
            subject TEXT, language TEXT, title TEXT, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
        INSERT INTO schema_migrations VALUES (1, 'preview');
        INSERT INTO schema_migrations VALUES (2, 'preview');
        INSERT INTO schema_migrations VALUES (3, 'preview');
        INSERT INTO schema_migrations VALUES (4, 'preview');
        """
    )
    if preview_column == "pinned":
        connection.execute(
            "ALTER TABLE conversations ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0"
        )
    else:
        connection.execute("ALTER TABLE messages ADD COLUMN completion_state TEXT")
    connection.commit()
    connection.close()

    store = ConversationStore(f"sqlite:///{path}")
    try:
        conversation_columns = {
            row[1] for row in store._conn.execute("PRAGMA table_info(conversations)").fetchall()
        }
        message_columns = {
            row[1] for row in store._conn.execute("PRAGMA table_info(messages)").fetchall()
        }
        assert "pinned" in conversation_columns
        assert "completion_state" in message_columns
        versions = store._conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        assert [row[0] for row in versions] == list(range(1, _LATEST_SCHEMA_VERSION + 1))
    finally:
        store.close()


def test_parallel_settings_patches_do_not_lose_sibling_controls(store):
    barrier = threading.Barrier(3)

    def patch(changes):
        barrier.wait()
        store.patch_settings("student", changes)

    first = threading.Thread(target=patch, args=({"allow_parallel_chats": False},))
    second = threading.Thread(target=patch, args=({"power_optimization_enabled": False},))
    first.start()
    second.start()
    barrier.wait()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not first.is_alive() and not second.is_alive()
    assert store.get_settings("student") == {
        "allow_parallel_chats": False,
        "power_optimization_enabled": False,
    }


# Re-run the exact behavioral tests used by Postgres against SQLite. Keeping aliases rather
# than a second hand-written suite makes future store-contract additions fail here by default.
test_messages_round_trip_in_order = contract.test_messages_round_trip_in_order
test_recent_limit_returns_last_n_chronologically = (
    contract.test_recent_limit_returns_last_n_chronologically
)
test_first_user_message_reads_only_the_opening_user_turn = (
    contract.test_first_user_message_reads_only_the_opening_user_turn
)
test_conversations_scoped_to_student = contract.test_conversations_scoped_to_student
test_pinned_conversations_persist_sort_first_and_remain_owner_scoped = (
    contract.test_pinned_conversations_persist_sort_first_and_remain_owner_scoped
)
test_persists_across_reconnect = contract.test_persists_across_reconnect
test_add_message_returns_monotonic_ids_and_bumps_updated_at = (
    contract.test_add_message_returns_monotonic_ids_and_bumps_updated_at
)
test_delete_conversation_cascades = contract.test_delete_conversation_cascades
test_attachment_round_trip_and_linking = contract.test_attachment_round_trip_and_linking
test_list_messages_includes_ids_and_attachment_refs = (
    contract.test_list_messages_includes_ids_and_attachment_refs
)
test_assistant_completion_state_is_durable_and_legacy_rows_remain_complete = (
    contract.test_assistant_completion_state_is_durable_and_legacy_rows_remain_complete
)
test_set_title_only_when_unset = contract.test_set_title_only_when_unset
test_settings_round_trip = contract.test_settings_round_trip
test_settings_patch_preserves_independent_controls = (
    contract.test_settings_patch_preserves_independent_controls
)
test_get_attachment_owner_scoping = contract.test_get_attachment_owner_scoping
test_get_attachment_owner_via_linked_conversation = (
    contract.test_get_attachment_owner_via_linked_conversation
)
test_link_attachment_cannot_claim_another_students_upload = (
    contract.test_link_attachment_cannot_claim_another_students_upload
)
test_student_deletion_removes_historical_cross_linked_uploads = (
    contract.test_student_deletion_removes_historical_cross_linked_uploads
)
test_delete_conversation_owner_scoped = contract.test_delete_conversation_owner_scoped
test_delete_student_erases_all_owned_data = contract.test_delete_student_erases_all_owned_data
test_reap_orphan_attachments_only_unlinked = contract.test_reap_orphan_attachments_only_unlinked
