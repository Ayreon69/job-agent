"""Schema and access helpers for the SQLite job store."""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
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
    last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
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
        _migrate_add_last_seen_at_column(conn)


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


def _migrate_add_last_seen_at_column(conn: sqlite3.Connection) -> None:
    """Same pattern as _migrate_add_status_column, for databases created
    before storage/cleanup.py's staleness tracking existed. Backfilled from
    scraped_at (the best available approximation — "last confirmed seen" is
    unknown for historical rows, so "first seen" is the closest honest
    substitute) rather than left NULL, so existing offers aren't
    immediately treated as having an unknown/undefined last-seen date.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "last_seen_at" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN last_seen_at TEXT")
        conn.execute("UPDATE jobs SET last_seen_at = scraped_at WHERE last_seen_at IS NULL")


@contextmanager
def connect(db_path: Path = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_job(conn: sqlite3.Connection, job: Job) -> bool:
    """Insert a job, or — if (source, source_id) already exists — refresh
    the existing row with this run's freshly-scraped values (url, title,
    company, location, contract_type, salary, experience, description,
    published_at) plus last_seen_at. The scraper already re-fetches an
    offer's detail page on every run regardless of whether it's already
    known (see scraper/hellowork.py/jobup.py's scrape()) — this used to
    discard that fresh data for already-known offers, which is exactly why
    published_at could silently go stale (a source can bump/republish an
    active listing's displayed date — confirmed live on a real Hellowork
    offer, see ROADMAP.md session 14 — but our copy never caught up).
    status and user_verdict are deliberately NEVER touched here: they're
    this app's own pipeline/human judgment, not scraped data, and a
    re-scrape must never silently reset them. scraped_at (first-seen) is
    also left untouched — it's a historical fact, not a "current" field.

    last_seen_at is what storage/cleanup.py judges an offer's staleness by:
    a real "still shows up in a scraping run" signal, unlike published_at
    or scraped_at (both can go stale for an offer that keeps reappearing —
    see this function's git history / ROADMAP.md session 14 for why both
    were tried and rejected as the staleness signal specifically).

    Returns True if a new row was inserted, False if it already existed
    (and had its scraped fields + last_seen_at refreshed).
    """
    existing = conn.execute(
        "SELECT id FROM jobs WHERE source = ? AND source_id = ?",
        (job.source, job.source_id),
    ).fetchone()

    if existing is not None:
        conn.execute(
            """
            UPDATE jobs SET
                url = ?, title = ?, company = ?, location = ?,
                contract_type = ?, salary = ?, experience = ?,
                description = ?, published_at = ?, last_seen_at = datetime('now')
            WHERE id = ?
            """,
            (
                job.url,
                job.title,
                job.company,
                job.location,
                job.contract_type,
                job.salary,
                job.experience,
                job.description,
                job.published_at,
                existing[0],
            ),
        )
        return False

    conn.execute(
        """
        INSERT INTO jobs
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
    return True


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


# jobs.published_at is stored verbatim, in whichever format the source site
# used at scrape time (see scraper/hellowork.py and scraper/jobup.py) — NOT
# normalized at scrape time. Two formats exist in practice: Hellowork's
# "DD/MM/YYYY" and jobup.ch's French "DD mois AAAA" (session 11). Originally
# lived in api/main.py (dashboard sort-by-date, session "date de publication"
# follow-up) — moved here so storage/cleanup.py can reuse the exact same
# parsing to decide an offer's real age, rather than duplicating the regexes.
_MOIS_FR = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}
_PUBLISHED_AT_SLASH_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_PUBLISHED_AT_FR_RE = re.compile(r"^(\d{1,2})\s+([a-zéû]+)\s+(\d{4})$", re.IGNORECASE)


def parse_published_at(raw: str | None) -> date | None:
    """Parse jobs.published_at's raw, source-specific text into a real date,
    or None if it's missing or in an unrecognized format.
    """
    if not raw:
        return None
    raw = raw.strip()

    slash_match = _PUBLISHED_AT_SLASH_RE.match(raw)
    if slash_match:
        day, month, year = (int(g) for g in slash_match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None

    fr_match = _PUBLISHED_AT_FR_RE.match(raw)
    if fr_match:
        day_str, month_name, year_str = fr_match.groups()
        month = _MOIS_FR.get(month_name.lower())
        if month is None:
            return None
        try:
            return date(int(year_str), month, int(day_str))
        except ValueError:
            return None

    return None
