"""Delete stale job offers — one that hasn't shown up in any scraping run
for a while has very likely expired, been filled, or been taken down, and
isn't worth keeping in the database or cluttering the dashboard.

Staleness is judged by jobs.last_seen_at (storage/db.py's upsert_job:
refreshed to "now" every time an offer is encountered again in a scraping
run, left untouched otherwise) — NOT by published_at or the original
scraped_at. Both were tried first and rejected for a real, confirmed
reason: published_at is the source site's own listing date, which some
sites bump/republish on a still-active listing (confirmed live: a
Hellowork offer scraped 2026-07-13 with published_at="13/07/2026" showed
"Publiée le 12/08/2026" on the live site a month later — the field is not
frozen at true publication time, so it doesn't reliably signal whether an
offer is still live). scraped_at has the opposite problem: it's frozen at
first-seen time forever, so an offer that keeps reappearing in every
subsequent scrape (i.e. is obviously still live) would look just as "old"
as one that vanished the day after being scraped. last_seen_at solves both:
it only ages for an offer that has genuinely stopped showing up.

Deleting an offer also deletes its analysis (analyses.job_id is
ON DELETE CASCADE, see storage/db.py).

By explicit user decision (2026-08-20): this does NOT special-case
user_verdict. An offer marked "interessante" is deleted exactly like any
other once it crosses the staleness threshold — no protection for triaged
offers. If that turns out to be the wrong default in practice, it's a
one-line change (skip rows where user_verdict is not null) rather than a
structural one.

Known limitation: an offer only gets its last_seen_at refreshed if it's
still returned by the scraper's default queries/page count on a given run
— one that's still live but has simply fallen off page 1 of results (or
whose query terms drifted) will look stale here even though it hasn't
actually expired. Not solved by this script; would need the scraper itself
to widen its recall (more pages/queries) to reduce false staleness.

Usage:
    python -m storage.cleanup [--days 30] [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, time, timedelta, timezone

from storage.db import connect, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_MAX_AGE_DAYS = 30


def find_stale_offers(conn, cutoff: datetime) -> list[dict]:
    """Offers last seen before cutoff. A NULL last_seen_at (rows inherited
    from SQLite, see storage/db.py) never compares as older: those rows are
    kept, as they were before the migration."""
    rows = conn.execute(
        "SELECT id, title, last_seen_at FROM jobs WHERE last_seen_at < %s ORDER BY id", (cutoff,)
    ).fetchall()
    return [{"id": r[0], "title": r[1], "last_seen_at": r[2].date().isoformat()} for r in rows]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delete job offers not seen in any scraping run for a threshold number of days"
    )
    parser.add_argument(
        "--days", type=int, default=DEFAULT_MAX_AGE_DAYS,
        help=f"Days since last_seen_at before an offer is deleted (default: {DEFAULT_MAX_AGE_DAYS})",
    )
    parser.add_argument("--dry-run", action="store_true", help="List what would be deleted without deleting anything")
    args = parser.parse_args()

    init_db()
    # Midnight UTC, args.days days ago: an offer seen at any time on the
    # cutoff day itself is kept.
    today = datetime.now(timezone.utc).date()
    cutoff = datetime.combine(today - timedelta(days=args.days), time.min, tzinfo=timezone.utc)

    with connect() as conn:
        stale = find_stale_offers(conn, cutoff)
        if not stale:
            logger.info(
                "Aucune offre non revue depuis %s (seuil: %d jours) — rien à supprimer.",
                cutoff.date().isoformat(), args.days,
            )
            return

        logger.info(
            "%d offre(s) non revue(s) depuis %s (seuil: %d jours) :",
            len(stale), cutoff.date().isoformat(), args.days,
        )
        for offer in stale:
            logger.info("  - #%s %r (dernière fois vue: %s)", offer["id"], offer["title"], offer["last_seen_at"])

        if args.dry_run:
            logger.info("--dry-run : aucune suppression effectuée.")
            return

        # Their analyses go with them (analyses.job_id is ON DELETE CASCADE).
        conn.execute("DELETE FROM jobs WHERE id = ANY(%s)", ([offer["id"] for offer in stale],))

    logger.info("Supprimé : %d offre(s) et leurs analyses.", len(stale))


if __name__ == "__main__":
    main()
