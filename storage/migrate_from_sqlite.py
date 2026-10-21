"""One-off import of the former SQLite store into Postgres (session 20).

Copies every row of the SQLite `jobs` table, ids included, so links to
#/offres?offre=<id> and the ids quoted in ROADMAP.md stay valid. SQLite's
timestamps ('YYYY-MM-DD HH:MM:SS', UTC without a zone marker) become
timestamptz. Analyses aren't migrated: the ones the CI produced were never
kept anywhere (orchestrator/runs/ stayed on the runner).

Refuses to write into a non-empty `jobs` table unless --replace is given,
which empties it first (analyses included) — the way to re-run the import
right before the cutover, to pick up the CI bot's last SQLite commit.
Never run it with --replace once the pipeline writes to Postgres: that
would throw away everything collected since.

Usage:
    git show origin/master:storage/jobs.db > jobs-latest.db
    python -m storage.migrate_from_sqlite jobs-latest.db --dry-run
    python -m storage.migrate_from_sqlite jobs-latest.db [--replace]
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from storage.db import connect, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

COLUMNS = (
    "id", "source", "source_id", "url", "title", "company", "location", "contract_type", "salary",
    "experience", "description", "published_at", "scraped_at", "last_seen_at", "status", "user_verdict",
    "score", "geography_zone", "sector", "gaps_count", "uncertain_count",
)
TIMESTAMP_COLUMNS = ("scraped_at", "last_seen_at")


def _utc(raw: str | None) -> datetime | None:
    if raw is None:
        return None
    return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)


def read_sqlite(path: Path) -> list[dict]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = conn.execute(f"SELECT {', '.join(COLUMNS)} FROM jobs ORDER BY id").fetchall()
    finally:
        conn.close()
    offers = [dict(zip(COLUMNS, row)) for row in rows]
    for offer in offers:
        for column in TIMESTAMP_COLUMNS:
            offer[column] = _utc(offer[column])
    return offers


def import_offers(conn: psycopg.Connection, offers: list[dict], *, replace: bool) -> None:
    existing = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    if existing and not replace:
        raise RuntimeError(
            f"La table jobs contient déjà {existing} offre(s) : rien écrit. "
            "--replace pour la vider d'abord (uniquement avant la bascule, voir le docstring)."
        )
    if existing:
        logger.info("--replace : suppression des %d offre(s) existantes et de leurs analyses.", existing)
        conn.execute("TRUNCATE jobs, analyses")

    # COPY streams every row in one statement: the bulk-load path of
    # Postgres, much faster than one INSERT per row over the network.
    with conn.cursor().copy(f"COPY jobs ({', '.join(COLUMNS)}) FROM STDIN") as copy:
        for offer in offers:
            copy.write_row([offer[column] for column in COLUMNS])

    # Explicit ids bypass the identity sequence: move it past the largest
    # one, or the next scraped offer would collide with an imported id.
    conn.execute("SELECT setval(pg_get_serial_sequence('jobs', 'id'), (SELECT max(id) FROM jobs))")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import the former SQLite jobs.db into Postgres (DATABASE_URL)")
    parser.add_argument("sqlite_path", type=Path)
    parser.add_argument("--replace", action="store_true", help="Empty the Postgres tables first (jobs and analyses)")
    parser.add_argument("--dry-run", action="store_true", help="Read and report, write nothing")
    args = parser.parse_args()

    offers = read_sqlite(args.sqlite_path)
    logger.info(
        "SQLite : %d offre(s) ; statuts %s ; verdicts %s ; sans last_seen_at : %d",
        len(offers),
        dict(Counter(o["status"] for o in offers)),
        dict(Counter(o["user_verdict"] for o in offers if o["user_verdict"])),
        sum(o["last_seen_at"] is None for o in offers),
    )
    if args.dry_run:
        logger.info("--dry-run : rien écrit.")
        return

    init_db()
    with connect() as conn:
        try:
            import_offers(conn, offers, replace=args.replace)
        except RuntimeError as exc:
            raise SystemExit(str(exc))
        imported = conn.execute("SELECT COUNT(*), max(id), max(last_seen_at) FROM jobs").fetchone()

    logger.info("Postgres : %d offre(s) importée(s), id max %s, dernière collecte %s.", *imported)


if __name__ == "__main__":
    main()
