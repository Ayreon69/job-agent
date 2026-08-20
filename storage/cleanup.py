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

Deletion removes the SQLite row AND its orchestrator/runs/ files
(analysis_<id>.md, structured_analysis_<id>.json, the 3 trace JSON files)
— leaving those behind would accumulate as orphaned, git-tracked files
referencing a row that no longer exists.

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
from datetime import date, datetime, timedelta
from pathlib import Path

from storage.db import connect, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

RUNS_DIR = Path(__file__).parent.parent / "orchestrator" / "runs"
DEFAULT_MAX_AGE_DAYS = 30

# One template per artifact orchestrator/run.py's write_outputs() can
# produce for an offer — deleted alongside the SQLite row so nothing
# orphaned (referencing a row that no longer exists) survives a cleanup.
RUN_FILE_TEMPLATES = [
    "analysis_{id}.md",
    "structured_analysis_{id}.json",
    "trace_orchestrator_{id}.json",
    "trace_scoring_{id}.json",
    "trace_generation_{id}.json",
]


def _parse_last_seen_date(last_seen_at: str | None) -> date | None:
    """last_seen_at is a SQLite datetime('now') string (UTC, 'YYYY-MM-DD
    HH:MM:SS') — always well-formed since the column is NOT NULL with a
    DEFAULT and every write goes through datetime('now'); None only guards
    against a row that somehow predates even the migration's backfill.
    """
    if not last_seen_at:
        return None
    try:
        return datetime.fromisoformat(last_seen_at.split(" ")[0]).date()
    except ValueError:
        return None


def find_stale_offers(conn, cutoff: date) -> list[dict]:
    rows = conn.execute("SELECT id, title, last_seen_at FROM jobs").fetchall()
    stale = []
    for offer_id, title, last_seen_at in rows:
        last_seen = _parse_last_seen_date(last_seen_at)
        if last_seen and last_seen < cutoff:
            stale.append({"id": offer_id, "title": title, "last_seen_at": last_seen.isoformat()})
    return stale


def delete_offer_files(offer_id: int) -> int:
    removed = 0
    for template in RUN_FILE_TEMPLATES:
        path = RUNS_DIR / template.format(id=offer_id)
        if path.exists():
            path.unlink()
            removed += 1
    return removed


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
    cutoff = date.today() - timedelta(days=args.days)

    with connect() as conn:
        stale = find_stale_offers(conn, cutoff)
        if not stale:
            logger.info(
                "Aucune offre non revue depuis %s (seuil: %d jours) — rien à supprimer.",
                cutoff.isoformat(), args.days,
            )
            return

        logger.info(
            "%d offre(s) non revue(s) depuis %s (seuil: %d jours) :",
            len(stale), cutoff.isoformat(), args.days,
        )
        for offer in stale:
            logger.info("  - #%s %r (dernière fois vue: %s)", offer["id"], offer["title"], offer["last_seen_at"])

        if args.dry_run:
            logger.info("--dry-run : aucune suppression effectuée.")
            return

        total_files = 0
        for offer in stale:
            total_files += delete_offer_files(offer["id"])
            conn.execute("DELETE FROM jobs WHERE id = ?", (offer["id"],))

    logger.info(
        "Supprimé : %d offre(s), %d fichier(s) associé(s) dans orchestrator/runs/.",
        len(stale), total_files,
    )


if __name__ == "__main__":
    main()
