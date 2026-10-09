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


def test_deleting_middle_cited_resource_never_repoints_markers(store):
    resources = [
        store.create_resource("alice", f"chapter-{index}.txt", "text/plain", b"text")
        for index in range(3)
    ]
    conversation = store.create_conversation("alice")
    store.add_message(conversation, "user", "Explain the three chapters")
    answer = store.add_message(
        conversation,
        "assistant",
        "First [R1]. Second [R2]. Third [R3].",
        completion_state="failed",
    )
    store.add_message_sources(
        answer,
        [
            {
                "resource_id": resource,
                "title": f"chapter-{index}.txt",
                "page": 1,
                "chunk_index": 0,
                "excerpt": "text",
            }
            for index, resource in enumerate(resources)
        ],
    )
    assert not store.delete_resource(resources[1], owner_id="mallory")
    assert "[R2]" in store.list_messages(conversation)[-1]["content"]

    assert store.delete_resource(resources[1], owner_id="alice")
    row = store.list_messages(conversation)[-1]
    assert row["content"] == "First. Second. Third."
    assert row["resource_citations"] == []
    assert store.get_resource(resources[0], owner_id="alice") is not None
    assert store.get_resource(resources[2], owner_id="alice") is not None


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


def test_migration_six_rebuilds_resources_without_losing_chunks_or_citations(tmp_path):
    """Widening the mime CHECK rebuilds `learning_resources`; with foreign keys left on, the
    DROP would cascade-delete every chunk and citation. The rows must survive, and the
    cascades must still work afterwards."""
    path = tmp_path / "v5.sqlite3"
    store = ConversationStore(f"sqlite:///{path}")
    store.close()
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        PRAGMA foreign_keys=OFF;
        DROP TABLE message_sources;
        DROP TABLE resource_chunks;
        DROP TABLE learning_resources;
        CREATE TABLE learning_resources (
            id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, name TEXT NOT NULL,
            mime TEXT NOT NULL CHECK (mime = 'application/pdf'), data BLOB NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('processing', 'ready', 'failed')),
            page_count INTEGER, embedder_identity TEXT, error TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE resource_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resource_id TEXT NOT NULL REFERENCES learning_resources(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL, page_number INTEGER NOT NULL, text TEXT NOT NULL,
            embedding TEXT NOT NULL, UNIQUE(resource_id, chunk_index)
        );
        CREATE TABLE message_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            resource_id TEXT NOT NULL REFERENCES learning_resources(id) ON DELETE CASCADE,
            title TEXT NOT NULL, page_number INTEGER NOT NULL, chunk_index INTEGER NOT NULL,
            excerpt TEXT NOT NULL, UNIQUE(message_id, resource_id, page_number, chunk_index)
        );
        DELETE FROM schema_migrations WHERE version = 6;
        INSERT INTO conversations VALUES ('c', 'a', NULL, NULL, NULL, NULL, NULL, 't', 't', 0);
        INSERT INTO messages (conversation_id, role, content, created_at)
            VALUES ('c', 'assistant', 'answer [R1]', 't');
        INSERT INTO learning_resources VALUES
            ('r', 'a', 'book.pdf', 'application/pdf', x'25504446', 'ready', 3, 'hashing:384',
             NULL, 't', 't');
        INSERT INTO resource_chunks (resource_id, chunk_index, page_number, text, embedding)
            VALUES ('r', 0, 2, 'Kinetic energy', '[0.5]');
        INSERT INTO message_sources
            (message_id, resource_id, title, page_number, chunk_index, excerpt)
            VALUES (1, 'r', 'book.pdf', 2, 0, 'Kinetic energy');
        """
    )
    connection.commit()
    connection.close()

    store = ConversationStore(f"sqlite:///{path}")
    try:
        assert store.get_resource_chunks(["r"], owner_id="a")[0]["section"] is None
        assert store.get_message_sources(1)[0]["page"] == 2
        assert store.create_resource("a", "notes.md", "text/markdown", b"# Notes")
        assert store._conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert store.delete_resource("r", owner_id="a")
        assert store.get_resource_chunks(["r"], owner_id="a") == []
        assert store.get_message_sources(1) == []
    finally:
        store.close()
