"""Shared fixtures: a Postgres-backed ConversationStore.

Store tests need a real Postgres — the compose `db` service (`docker compose up -d db`,
published on 127.0.0.1:15432) or anything `MUTA_TEST_DB_URL` points at. Tests run against a
dedicated `muta_test` database (created on demand) and truncate between tests, so they can
share the server with real dev data without touching it. When Postgres is unreachable the
store-backed tests skip rather than fail.
"""

from __future__ import annotations

import os

import pytest

from runtime.memory import ConversationStore

ADMIN_DSN = os.environ.get("MUTA_TEST_DB_URL", "postgresql://muta:muta@127.0.0.1:15432/muta")
TEST_DB = "muta_test"

_UNSET = object()
_dsn_cache: object = _UNSET


def _test_dsn() -> str | None:
    """DSN of the `muta_test` database (created if missing), or None when PG is down.

    Cached module-wide: with Postgres down, every store test would otherwise pay the
    connect timeout individually.
    """
    global _dsn_cache
    if _dsn_cache is not _UNSET:
        return _dsn_cache  # type: ignore[return-value]
    try:
        import psycopg
        from psycopg import conninfo

        with psycopg.connect(ADMIN_DSN, autocommit=True, connect_timeout=2) as conn:
            row = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)
            ).fetchone()
            if row is None:
                conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        _dsn_cache = conninfo.make_conninfo(ADMIN_DSN, dbname=TEST_DB)
    except Exception:  # noqa: BLE001 — any failure here means "no postgres": skip, don't error
        _dsn_cache = None
    return _dsn_cache  # type: ignore[return-value]


@pytest.fixture()
def store() -> ConversationStore:
    dsn = _test_dsn()
    if dsn is None:
        pytest.skip("postgres unavailable — start it with `docker compose up -d db`")
    s = ConversationStore(dsn)
    # Truncate BEFORE the test so leftovers from a crashed earlier run can't leak in.
    with s._pool.connection() as conn:  # noqa: SLF001 — test-only reset hook
        conn.execute(
            "TRUNCATE conversations, messages, attachments, user_settings "
            "RESTART IDENTITY CASCADE"
        )
    yield s
    s.close()
