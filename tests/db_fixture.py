"""Throwaway Postgres schemas for the tests that need a database.

Server: TEST_DATABASE_URL if set, otherwise a local embedded Postgres
started by pgserver (`pip install pgserver`, dev only — no Docker needed).
Each temp_database() creates its own schema, points the connection's
search_path at it and drops it afterwards: even pointed at a real database,
a test never reads or writes the tables of the public schema.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
from psycopg.conninfo import make_conninfo

from storage.db import init_db

_server = None


def _server_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if url:
        return url
    global _server
    if _server is None:
        try:
            import pgserver
        except ImportError:
            raise SystemExit("Tests base de données : définir TEST_DATABASE_URL ou installer pgserver (pip install pgserver).")
        _server = pgserver.get_server(Path(tempfile.gettempdir()) / "job-agent-pgtest", cleanup_mode="stop")
    return _server.get_uri()


@contextmanager
def temp_database() -> Iterator[str]:
    """Yields a DSN whose tables (created by init_db) live in a fresh schema."""
    base = _server_url()
    schema = f"test_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(base, autocommit=True) as admin:
        admin.execute(f"CREATE SCHEMA {schema}")
    dsn = make_conninfo(base, options=f"-c search_path={schema}")
    try:
        init_db(dsn)
        yield dsn
    finally:
        with psycopg.connect(base, autocommit=True) as admin:
            admin.execute(f"DROP SCHEMA {schema} CASCADE")
