"""Entry point: scrape job offers (Hellowork and/or jobup.ch) into SQLite.

Usage:
    python -m scraper.run
        (both sources, each with its own default query set/region)
    python -m scraper.run --source hellowork
    python -m scraper.run --source jobup
    python -m scraper.run --source jobup --query "data engineer" --pages 2
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import hellowork, jobup
from storage.db import DEFAULT_DB_PATH, Job, connect, init_db, upsert_job

# Hellowork ne référence que des offres France (pas de Suisse/UAE/Moyen-Orient utile
# ici). Ciblage géo limité au repli du CLAUDE.md, élargi de Lyon à toute la région
# pour couvrir aussi Grenoble, Saint-Étienne, Annecy, etc. jobup.ch (ajouté session
# 11) couvre la vraie priorité 1 du CLAUDE.md (Suisse romande), jamais scrapée
# jusqu'ici. UAE/Moyen-Orient restent à couvrir par une source future.
HELLOWORK_DEFAULT_LOCATION = "Rhône-Alpes"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _store_jobs(conn, jobs: list[dict]) -> int:
    total_new = 0
    for job_dict in jobs:
        job = Job(
            source=job_dict["source"],
            source_id=job_dict["source_id"],
            url=job_dict["url"],
            title=job_dict["title"],
            company=job_dict["company"],
            location=job_dict["location"],
            contract_type=job_dict["contract_type"],
            salary=job_dict["salary"],
            experience=job_dict["experience"],
            description=job_dict["description"],
            published_at=job_dict["published_at"],
        )
        if upsert_job(conn, job):
            total_new += 1
    return total_new


def run_hellowork(conn, queries: list[str], location: str, max_pages: int, headless: bool) -> tuple[int, int]:
    total_seen = 0
    total_new = 0
    for query in queries:
        logger.info("=== [hellowork] Scraping query: %r (location: %r) ===", query, location)
        jobs = hellowork.scrape(query, location=location, max_pages=max_pages, headless=headless)
        total_seen += len(jobs)
        total_new += _store_jobs(conn, jobs)
    return total_seen, total_new


def run_jobup(conn, queries: list[str], locations: list[str], max_pages: int, headless: bool) -> tuple[int, int]:
    total_seen = 0
    total_new = 0
    for query in queries:
        logger.info("=== [jobup] Scraping query: %r (locations: %r) ===", query, locations)
        jobs = jobup.scrape(query, locations=locations, max_pages=max_pages, headless=headless)
        total_seen += len(jobs)
        total_new += _store_jobs(conn, jobs)
    return total_seen, total_new


def run(
    sources: list[str],
    hellowork_queries: list[str],
    hellowork_location: str,
    jobup_queries: list[str],
    jobup_locations: list[str],
    max_pages: int,
    headless: bool,
) -> None:
    init_db()

    with connect() as conn:
        if "hellowork" in sources:
            seen, new = run_hellowork(conn, hellowork_queries, hellowork_location, max_pages, headless)
            logger.info("[hellowork] Done. %d offers scraped, %d new rows inserted.", seen, new)
        if "jobup" in sources:
            seen, new = run_jobup(conn, jobup_queries, jobup_locations, max_pages, headless)
            logger.info("[jobup] Done. %d offers scraped, %d new rows inserted.", seen, new)

    logger.info("All sources done. Database: %s", DEFAULT_DB_PATH)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape job offers (Hellowork and/or jobup.ch) into SQLite")
    parser.add_argument(
        "--source",
        choices=["hellowork", "jobup", "both"],
        default="both",
        help="Which source(s) to scrape (default: both)",
    )
    parser.add_argument(
        "--query",
        action="append",
        dest="queries",
        help="Search query to scrape (repeatable). Applied to whichever source(s) are selected via --source; "
             "defaults to each source's own preset query set if omitted.",
    )
    parser.add_argument(
        "--location",
        default=HELLOWORK_DEFAULT_LOCATION,
        help=f"Hellowork location filter (default: {HELLOWORK_DEFAULT_LOCATION!r}). Pass an empty string for no filter. "
             "Ignored for jobup (use --jobup-location instead — jobup requires real location slugs, not free text).",
    )
    parser.add_argument(
        "--jobup-location",
        action="append",
        dest="jobup_locations",
        help="jobup.ch location slug to scrape (repeatable, e.g. --jobup-location genève --jobup-location vaud). "
             f"Defaults to Suisse romande: {jobup.DEFAULT_LOCATIONS!r}.",
    )
    parser.add_argument("--pages", type=int, default=1, help="Number of search result pages per query")
    parser.add_argument("--headed", action="store_true", help="Run the browser with a visible window")
    args = parser.parse_args()

    sources = ["hellowork", "jobup"] if args.source == "both" else [args.source]
    hellowork_queries = (args.queries or hellowork.DEFAULT_JOB_QUERIES) if "hellowork" in sources else []
    jobup_queries = (args.queries or jobup.DEFAULT_QUERIES) if "jobup" in sources else []
    jobup_locations = args.jobup_locations or jobup.DEFAULT_LOCATIONS

    run(
        sources=sources,
        hellowork_queries=hellowork_queries,
        hellowork_location=args.location,
        jobup_queries=jobup_queries,
        jobup_locations=jobup_locations,
        max_pages=args.pages,
        headless=not args.headed,
    )


if __name__ == "__main__":
    main()
