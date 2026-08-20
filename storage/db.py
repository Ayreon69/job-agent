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
    status TEXT NOT NULL DEFAULT 'nouveau',
    user_verdict TEXT,
    UNIQUE(source, source_id)
);
"""

# Statuts possibles de jobs.status, gérés par l'orchestrateur (session 5) :
#   nouveau                 - pas encore traité
#   analyse                 - scoring + génération réussis
#   a_valider_geographie    - traité avec succès mais zone géographique
#                              "inconnu" (session 3) : ne pas faire confiance
#                              silencieusement au ton généré, valider à la main
#   echec                   - une étape a levé une exception ; voir la trace
#                              orchestrateur pour le détail
JOB_STATUSES = ("nouveau", "analyse", "a_valider_geographie", "echec")

# Verdict manuel de l'utilisateur (dashboard, tri façon swipe) — indépendant
# du score/statut calculés par le pipeline : c'est un jugement humain, jamais
# recalculé ni influencé par l'agent. NULL = pas encore trié.
USER_VERDICTS = ("interessante", "peut_etre", "pas_interessante")


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
        _migrate_add_status_column(conn)
        _migrate_add_user_verdict_column(conn)


def _migrate_add_status_column(conn: sqlite3.Connection) -> None:
    """CREATE TABLE IF NOT EXISTS in SCHEMA doesn't touch a table that already
    exists without the new column (databases created before session 5) — add
    it explicitly if missing, defaulting existing rows to 'nouveau'.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "status" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN status TEXT NOT NULL DEFAULT 'nouveau'")


def _migrate_add_user_verdict_column(conn: sqlite3.Connection) -> None:
    """Same pattern as _migrate_add_status_column, for databases created
    before the dashboard's swipe-triage feature existed.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "user_verdict" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN user_verdict TEXT")


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


def set_job_status(conn: sqlite3.Connection, job_id: int, status: str) -> None:
    if status not in JOB_STATUSES:
        raise ValueError(f"Unknown job status {status!r}, expected one of {JOB_STATUSES}")
    conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))


def set_user_verdict(conn: sqlite3.Connection, job_id: int, verdict: str | None) -> None:
    """Set (or clear, with verdict=None) the user's own manual triage
    decision for an offer — never touched by the scoring/generation
    pipeline, purely a human judgment recorded from the dashboard.
    """
    if verdict is not None and verdict not in USER_VERDICTS:
        raise ValueError(f"Unknown user verdict {verdict!r}, expected one of {USER_VERDICTS} or None")
    conn.execute("UPDATE jobs SET user_verdict = ? WHERE id = ?", (verdict, job_id))
