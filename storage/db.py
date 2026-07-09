"""Schema and access helpers for the SQLite job store."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

DEFAULT_DB_PATH = Path(__file__).parent / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT,
    location TEXT,
    contract_type TEXT,
    salary TEXT,
    experience TEXT,
    description TEXT,
    published_at TEXT,
    scraped_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source, source_id)
);
"""


@dataclass
class Job:
    source: str
    source_id: str
    url: str
    title: str
    company: str | None = None
    location: str | None = None
    contract_type: str | None = None
    salary: str | None = None
    experience: str | None = None
    description: str | None = None
    published_at: str | None = None


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


@contextmanager
def connect(db_path: Path = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_job(conn: sqlite3.Connection, job: Job) -> bool:
    """Insert a job, ignoring it if (source, source_id) already exists.

    Returns True if a new row was inserted, False if it already existed.
    """
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO jobs
            (source, source_id, url, title, company, location,
             contract_type, salary, experience, description, published_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job.source,
            job.source_id,
            job.url,
            job.title,
            job.company,
            job.location,
            job.contract_type,
            job.salary,
            job.experience,
            job.description,
            job.published_at,
        ),
    )
    return cursor.rowcount > 0


def count_jobs(db_path: Path = DEFAULT_DB_PATH) -> int:
    with connect(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
