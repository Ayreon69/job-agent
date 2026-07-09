"""Entry point: scrape Hellowork job offers and store them in SQLite.

Usage:
    python -m scraper.run
    python -m scraper.run --query "data engineer" --pages 2
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper.hellowork import scrape
from storage.db import DEFAULT_DB_PATH, Job, connect, init_db, upsert_job

DEFAULT_QUERIES = [
    "data scientist",
    "data analyst",
    "data engineer",
    "IA générative agent LLM",
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def run(queries: list[str], max_pages: int, headless: bool) -> None:
    init_db()
    total_new = 0
    total_seen = 0

    with connect() as conn:
        for query in queries:
            logger.info("=== Scraping query: %r ===", query)
            jobs = scrape(query, max_pages=max_pages, headless=headless)
            total_seen += len(jobs)

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

    logger.info(
        "Done. %d offers scraped, %d new rows inserted into %s",
        total_seen,
        total_new,
        DEFAULT_DB_PATH,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Hellowork job offers into SQLite")
    parser.add_argument(
        "--query",
        action="append",
        dest="queries",
        help="Search query to scrape (repeatable). Defaults to a preset data/AI query set.",
    )
    parser.add_argument("--pages", type=int, default=1, help="Number of search result pages per query")
    parser.add_argument("--headed", action="store_true", help="Run the browser with a visible window")
    args = parser.parse_args()

    queries = args.queries or DEFAULT_QUERIES
    run(queries, max_pages=args.pages, headless=not args.headed)


if __name__ == "__main__":
    main()
