"""One-off repair: merge jobup offers stored several times under different
source_ids before store_jobup_jobs existed (ROADMAP.md session 18).

Groups stored jobup rows with the same rule the scraper now applies at
storage time (scraper/jobup.py's is_same_offer), keeps one row per group
and deletes the others — rows and orchestrator/runs/ files, exactly like
storage/cleanup.py. The row kept is, in order of preference:
  1. the one carrying a user_verdict (a human judgment is never dropped;
     a group where SEVERAL rows carry one is left untouched and reported);
  2. the one whose jobup page is still online (HTTP 200 — republished
     offers answer 404/410 under their old source_id);
  3. the most recently seen (last_seen_at, or scraped_at when NULL).

Usage:
    python -m scraper.merge_jobup_duplicates --dry-run
    python -m scraper.merge_jobup_duplicates
    python -m scraper.merge_jobup_duplicates --no-check-live   (offline: skips rule 2)
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper.jobup import BASE_URL, _fold, is_same_offer, normalize_title
from storage.cleanup import delete_offer_files
from storage.db import connect, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def find_duplicate_groups(conn: sqlite3.Connection) -> list[list[dict]]:
    """Groups of 2+ stored jobup rows that is_same_offer links together
    (transitively: A~B and B~C put A, B, C in one group)."""
    rows = [
        {"id": r[0], "source_id": r[1], "title": r[2], "company": r[3], "location": r[4], "description": r[5],
         "status": r[6], "score": r[7], "user_verdict": r[8], "last_seen": r[9]}
        for r in conn.execute(
            "SELECT id, source_id, title, company, location, description, status, score, user_verdict, "
            "COALESCE(last_seen_at, scraped_at) FROM jobs WHERE source = 'jobup' ORDER BY id"
        ).fetchall()
    ]
    parent = {row["id"]: row["id"] for row in rows}

    def root(job_id: int) -> int:
        while parent[job_id] != job_id:
            job_id = parent[job_id]
        return job_id

    buckets: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        buckets.setdefault((normalize_title(row["title"]), _fold(row["location"])), []).append(row)
    for bucket in buckets.values():
        for i, a in enumerate(bucket):
            for b in bucket[i + 1:]:
                if is_same_offer(a, b):
                    parent[root(b["id"])] = root(a["id"])

    groups: dict[int, list[dict]] = {}
    for row in rows:
        groups.setdefault(root(row["id"]), []).append(row)
    return [group for group in groups.values() if len(group) > 1]


def mark_live(groups: list[list[dict]]) -> None:
    """Requests go through a real Chromium page's context: a bare
    Playwright request context gets HTTP 200 with jobup's "page not found"
    body for expired offers (checked 2026-09-26), a browser page gets the
    real 404/410.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        for group in groups:
            for row in group:
                response = page.request.get(f"{BASE_URL}/fr/emplois/detail/{row['source_id']}/", max_redirects=0)
                row["live"] = response.status == 200
        browser.close()


def pick_keeper(group: list[dict]) -> dict | None:
    """The row to keep, or None when several rows carry a user verdict
    (no automatic choice between two human judgments)."""
    if sum(row["user_verdict"] is not None for row in group) > 1:
        return None
    return max(group, key=lambda row: (row["user_verdict"] is not None, row.get("live", False), row["last_seen"] or ""))


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge jobup offers stored under several source_ids")
    parser.add_argument("--dry-run", action="store_true", help="List what would be deleted without deleting anything")
    parser.add_argument("--no-check-live", action="store_true", help="Don't query jobup.ch for which source_ids are still online")
    args = parser.parse_args()

    init_db()
    with connect() as conn:
        groups = find_duplicate_groups(conn)
        if not groups:
            logger.info("Aucun doublon jobup en base.")
            return
        if not args.no_check_live:
            mark_live(groups)

        to_delete: list[int] = []
        for group in groups:
            keeper = pick_keeper(group)
            if keeper is None:
                logger.warning("Groupe laissé intact (plusieurs verdicts) : %s", [(r["id"], r["user_verdict"]) for r in group])
                continue
            logger.info("%r — garde #%d", keeper["title"], keeper["id"])
            for row in group:
                live = {True: "en ligne", False: "hors ligne"}.get(row.get("live"), "?")
                action = "GARDE    " if row is keeper else "SUPPRIME "
                logger.info(
                    "    %s #%d %s  %s  score=%s  vue=%s  verdict=%s",
                    action, row["id"], row["source_id"][:8], live, row["score"], row["last_seen"], row["user_verdict"],
                )
                if row is not keeper:
                    to_delete.append(row["id"])

        logger.info("%d groupe(s), %d ligne(s) à supprimer.", len(groups), len(to_delete))
        if args.dry_run:
            logger.info("--dry-run : aucune suppression effectuée.")
            return

        total_files = 0
        for job_id in to_delete:
            total_files += delete_offer_files(job_id)
            conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    logger.info("Supprimé : %d offre(s), %d fichier(s) associé(s) dans orchestrator/runs/.", len(to_delete), total_files)


if __name__ == "__main__":
    main()
