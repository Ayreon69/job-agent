"""Entry point: scrape job offers (Hellowork, jobup.ch, LinkedIn) into SQLite.

Usage:
    python -m scraper.run
        (all sources, each with its own default query set/region)
    python -m scraper.run --source hellowork
    python -m scraper.run --source jobup
    python -m scraper.run --source linkedin --linkedin-location Lyon
    python -m scraper.run --source jobup --query "data engineer" --pages 2
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import cross_source, hellowork, jobup, linkedin
from storage.db import DEFAULT_DB_PATH, Job, connect, init_db, mark_seen, refresh_job, upsert_job

# Hellowork ne référence que des offres France (pas de Suisse/UAE/Moyen-Orient utile
# ici). Ciblage géo limité au repli du CLAUDE.md, élargi de Lyon à toute la région
# pour couvrir aussi Grenoble, Saint-Étienne, Annecy, etc. jobup.ch (ajouté session
# 11) couvre la vraie priorité 1 du CLAUDE.md (Suisse romande), jamais scrapée
# jusqu'ici. LinkedIn (session 19) couvre enfin UAE/Golfe (priorité 3) et
# complète la Suisse romande.
HELLOWORK_DEFAULT_LOCATION = "Rhône-Alpes"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _to_job(job_dict: dict) -> Job:
    return Job(
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


SOURCES = ["hellowork", "jobup", "linkedin"]


def _other_source_rows(conn, source: str) -> list[dict]:
    """Stored offers of every other source, for scraper/cross_source.py."""
    return [
        {"id": r[0], "source": r[1], "title": r[2], "company": r[3], "location": r[4], "description": r[5]}
        for r in conn.execute(
            "SELECT id, source, title, company, location, description FROM jobs WHERE source != ?", (source,)
        ).fetchall()
    ]


def _cross_source_twin(job_dict: dict, other_rows: list[dict]) -> dict | None:
    """Stored offer of another source that job_dict (a new offer) duplicates,
    logged — the caller then doesn't store job_dict at all."""
    twin = cross_source.find_twin(job_dict, other_rows)
    if twin is not None:
        logger.info(
            "[%s] %s already stored from %s as offer #%d: not stored again — %r",
            job_dict["source"], job_dict["source_id"], twin["source"], twin["id"], job_dict["title"],
        )
    return twin


def _store_jobs(conn, jobs: list[dict]) -> int:
    total_new = 0
    other_rows: list[dict] | None = None
    for job_dict in jobs:
        is_known = conn.execute(
            "SELECT 1 FROM jobs WHERE source = ? AND source_id = ?", (job_dict["source"], job_dict["source_id"])
        ).fetchone()
        if not is_known:
            if other_rows is None:
                other_rows = _other_source_rows(conn, job_dict["source"])
            if _cross_source_twin(job_dict, other_rows):
                continue
        if upsert_job(conn, _to_job(job_dict)):
            total_new += 1
    return total_new


def store_jobup_jobs(conn, jobs: list[dict]) -> tuple[int, int, int]:
    """Store one jobup run's offers, recognizing an offer jobup republished
    under a new source_id (see scraper/jobup.py's is_same_offer) instead of
    inserting it as a new 'nouveau' row that the orchestrator would score
    again. Returns (inserted, repointed, aliases).

    Two passes, so the outcome doesn't depend on result order:
      1. offers whose source_id is already stored: plain refresh; their
         rows are marked "seen this run";
      2. unknown source_ids, compared to every stored jobup row:
         - no match                 -> inserted (and matchable by the next ones),
                                        unless another source already has
                                        it (scraper/cross_source.py);
         - match seen this run      -> alias: the same offer is live under
                                        another UUID we just refreshed,
                                        nothing written;
         - match not seen this run  -> republication: the row is re-pointed
                                        to the new source_id/url, keeping
                                        its status, score and user_verdict.
    When several stored rows match (duplicates stored before this fix), the
    one carrying a user_verdict wins, then the most recently seen.
    """
    known = dict(conn.execute("SELECT source_id, id FROM jobs WHERE source = 'jobup'").fetchall())
    other_rows = _other_source_rows(conn, "jobup")
    seen_this_run: set[int] = set()
    unknown: list[dict] = []
    for job_dict in jobs:
        job_id = known.get(job_dict["source_id"])
        if job_id is None:
            unknown.append(job_dict)
        else:
            refresh_job(conn, job_id, _to_job(job_dict))
            seen_this_run.add(job_id)

    # last_seen_at is NULL on rows inserted after its migration and never
    # seen again (the migrated column has no default): scraped_at is then
    # the last time the offer was seen.
    stored = [
        {"id": r[0], "title": r[1], "company": r[2], "location": r[3], "description": r[4],
         "user_verdict": r[5], "last_seen_at": r[6]}
        for r in conn.execute(
            "SELECT id, title, company, location, description, user_verdict, COALESCE(last_seen_at, scraped_at) "
            "FROM jobs WHERE source = 'jobup'"
        ).fetchall()
    ]

    inserted = repointed = aliases = 0
    for job_dict in unknown:
        matches = [row for row in stored if jobup.is_same_offer(job_dict, row)]
        live = [row for row in matches if row["id"] in seen_this_run]
        if live:
            logger.info(
                "[jobup] %s is an alias of offer #%d (live under another source_id this run): not stored — %r",
                job_dict["source_id"], live[0]["id"], job_dict["title"],
            )
            aliases += 1
            continue

        if matches:
            target = max(matches, key=lambda row: (row["user_verdict"] is not None, row["last_seen_at"] or ""))
            refresh_job(conn, target["id"], _to_job(job_dict))
            target.update({k: job_dict[k] for k in ("title", "company", "location", "description")})
            seen_this_run.add(target["id"])
            logger.info(
                "[jobup] %s is a republication of offer #%d: row re-pointed to the new source_id (status/score/verdict kept)%s — %r",
                job_dict["source_id"], target["id"],
                f", {len(matches) - 1} other stored duplicate(s) left untouched" if len(matches) > 1 else "",
                job_dict["title"],
            )
            repointed += 1
            continue

        if _cross_source_twin(job_dict, other_rows):
            continue

        upsert_job(conn, _to_job(job_dict))
        new_id = conn.execute(
            "SELECT id FROM jobs WHERE source = 'jobup' AND source_id = ?", (job_dict["source_id"],)
        ).fetchone()[0]
        stored.append({"id": new_id, "user_verdict": None, "last_seen_at": None,
                       **{k: job_dict[k] for k in ("title", "company", "location", "description")}})
        seen_this_run.add(new_id)
        inserted += 1

    return inserted, repointed, aliases


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
    # All queries are collected before storing: store_jobup_jobs needs the
    # whole run to know which stored offers are still live under their own
    # source_id (an offer can come back under its old UUID in one query and
    # a new one in another). Nothing is lost by waiting: connect() only
    # commits once the whole run is done anyway.
    total_seen = 0
    jobs_by_source_id: dict[str, dict] = {}
    for query in queries:
        logger.info("=== [jobup] Scraping query: %r (locations: %r) ===", query, locations)
        jobs = jobup.scrape(query, locations=locations, max_pages=max_pages, headless=headless)
        total_seen += len(jobs)
        for job in jobs:
            jobs_by_source_id.setdefault(job["source_id"], job)

    inserted, repointed, aliases = store_jobup_jobs(conn, list(jobs_by_source_id.values()))
    logger.info(
        "[jobup] Same offer under a new source_id: %d republication(s) re-pointed, %d live alias(es) skipped.",
        repointed, aliases,
    )
    return total_seen, inserted


def run_linkedin(conn, queries: list[str], locations: list[str], max_pages: int) -> tuple[int, int]:
    """Only offers never seen before cost a detail request: already-stored
    ones are just marked as seen, and a card whose twin is already stored
    from another source (same title, place and company) is dropped before
    its detail page is fetched. Twins that need the description to be told
    apart (company unknown on the other side) are checked once fetched."""
    known = dict(conn.execute("SELECT source_id, id FROM jobs WHERE source = 'linkedin'").fetchall())
    other_rows = _other_source_rows(conn, "linkedin")

    listings = linkedin.collect_listings(queries, locations, max_pages=max_pages)
    to_fetch: list[linkedin.JobListing] = []
    seen_again = twins_on_card = 0
    for listing in listings:
        if listing.source_id in known:
            mark_seen(conn, known[listing.source_id])
            seen_again += 1
            continue
        card = {"source": "linkedin", "title": listing.title, "company": listing.company, "location": listing.location}
        twin = cross_source.find_twin(card, other_rows, need_description=False)
        if twin is not None:
            logger.info(
                "[linkedin] %s already stored from %s as offer #%d: skipped before fetching — %r",
                listing.source_id, twin["source"], twin["id"], listing.title,
            )
            twins_on_card += 1
            continue
        to_fetch.append(listing)
    logger.info(
        "[linkedin] %d unique listings: %d already stored (marked seen), %d stored from another source, %d to fetch",
        len(listings), seen_again, twins_on_card, len(to_fetch),
    )

    offers = linkedin.fetch_offers(to_fetch)
    return len(listings), _store_jobs(conn, offers)


def run(
    sources: list[str],
    hellowork_queries: list[str],
    hellowork_location: str,
    jobup_queries: list[str],
    jobup_locations: list[str],
    linkedin_queries: list[str],
    linkedin_locations: list[str],
    max_pages: int,
    linkedin_pages: int,
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
        if "linkedin" in sources:
            # Last, and isolated: LinkedIn may refuse the runner's IP (hosted
            # CI ranges often are), which must not cost the other sources'
            # results. Its own refusals (429/999) are already handled inside
            # scraper/linkedin.py; this catches anything unexpected.
            try:
                seen, new = run_linkedin(conn, linkedin_queries, linkedin_locations, linkedin_pages)
                logger.info("[linkedin] Done. %d offers found, %d new rows inserted.", seen, new)
            except Exception:
                logger.exception("[linkedin] Failed — other sources' results are kept")

    logger.info("All sources done. Database: %s", DEFAULT_DB_PATH)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape job offers (Hellowork, jobup.ch, LinkedIn) into SQLite")
    parser.add_argument(
        "--source",
        choices=[*SOURCES, "both", "all"],
        default="all",
        help="Which source(s) to scrape (default: all). 'both' = Hellowork + jobup, as before LinkedIn existed.",
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
    parser.add_argument(
        "--linkedin-location",
        action="append",
        dest="linkedin_locations",
        help="LinkedIn location, free text resolved by LinkedIn (repeatable, e.g. --linkedin-location Lyon). "
             f"Defaults to {linkedin.DEFAULT_LOCATIONS!r}.",
    )
    parser.add_argument("--pages", type=int, default=1, help="Number of search result pages per query (Hellowork, jobup)")
    parser.add_argument(
        "--linkedin-pages",
        type=int,
        default=linkedin.DEFAULT_PAGES,
        help=f"LinkedIn search pages of {linkedin.PAGE_SIZE} offers per query and location (default: {linkedin.DEFAULT_PAGES})",
    )
    parser.add_argument("--headed", action="store_true", help="Run the browser with a visible window")
    args = parser.parse_args()

    sources = {"all": SOURCES, "both": ["hellowork", "jobup"]}.get(args.source, [args.source])
    hellowork_queries = (args.queries or hellowork.DEFAULT_JOB_QUERIES) if "hellowork" in sources else []
    jobup_queries = (args.queries or jobup.DEFAULT_QUERIES) if "jobup" in sources else []
    jobup_locations = args.jobup_locations or jobup.DEFAULT_LOCATIONS
    linkedin_queries = (args.queries or linkedin.DEFAULT_QUERIES) if "linkedin" in sources else []
    linkedin_locations = args.linkedin_locations or linkedin.DEFAULT_LOCATIONS

    run(
        sources=sources,
        hellowork_queries=hellowork_queries,
        hellowork_location=args.location,
        jobup_queries=jobup_queries,
        jobup_locations=jobup_locations,
        linkedin_queries=linkedin_queries,
        linkedin_locations=linkedin_locations,
        max_pages=args.pages,
        linkedin_pages=args.linkedin_pages,
        headless=not args.headed,
    )


if __name__ == "__main__":
    main()
