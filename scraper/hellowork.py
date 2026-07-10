"""Playwright scraper for Hellowork job listings.

Search results are scraped for the job card summary (title, company,
location, contract type, URL), then each job's detail page is visited
to pull the full description and metadata (salary, experience, ref/date).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urlencode

from playwright.sync_api import Page, sync_playwright

BASE_URL = "https://www.hellowork.com"
SEARCH_URL = BASE_URL + "/fr-fr/emploi/recherche.html"
COOKIE_BUTTON = "button:has-text(\"Accepter\")"

# Types de contrat Hellowork, hors Alternance/Stage/Stage de lycée (exclus par défaut).
CONTRACT_TYPES = [
    "CDI",
    "CDD",
    "Freelance",
    "Intérim",
    "Indépendant",
    "Franchise",
    "Associé",
    "Fonctionnaire",
]

logger = logging.getLogger(__name__)


@dataclass
class JobListing:
    source_id: str
    url: str
    title: str
    company: str | None
    location: str | None
    contract_type: str | None


def _accept_cookies(page: Page) -> None:
    try:
        page.click(COOKIE_BUTTON, timeout=3000)
    except Exception:
        pass  # banner already dismissed or not shown


def _extract_source_id(url: str) -> str:
    match = re.search(r"/emplois/(\d+)\.html", url)
    if not match:
        raise ValueError(f"Cannot extract job id from URL: {url}")
    return match.group(1)


def search_jobs(
    page: Page,
    query: str,
    location: str = "",
    max_pages: int = 1,
    contract_types: list[str] = CONTRACT_TYPES,
) -> list[JobListing]:
    """Scrape search result pages for a query, returning job summaries."""
    listings: list[JobListing] = []

    for page_num in range(1, max_pages + 1):
        params = [("k", query), ("l", location), ("d", "all"), ("p", page_num)]
        params += [("c", c) for c in contract_types]
        url = SEARCH_URL + "?" + urlencode(params)
        logger.info("Fetching search page %d: %s", page_num, url)
        page.goto(url, timeout=30000)
        page.wait_for_timeout(2000)
        if page_num == 1:
            _accept_cookies(page)
            page.wait_for_timeout(1000)

        cards = page.query_selector_all('[data-cy="serpCard"]')
        if not cards:
            logger.info("No more results at page %d, stopping", page_num)
            break

        for card in cards:
            link = card.query_selector('[data-cy="offerTitle"]')
            if not link:
                continue
            href = link.get_attribute("href") or ""
            job_url = href if href.startswith("http") else BASE_URL + href

            title_el = card.query_selector('h3 p.typo-l, h3 p.typo-xl')
            company_el = card.query_selector("h3 p.typo-s")
            location_el = card.query_selector('[data-cy="localisationCard"]')
            contract_el = card.query_selector('[data-cy="contractCard"]')

            try:
                source_id = _extract_source_id(job_url)
            except ValueError:
                logger.warning("Skipping card with unparsable URL: %s", job_url)
                continue

            listings.append(
                JobListing(
                    source_id=source_id,
                    url=job_url,
                    title=(title_el.inner_text().strip() if title_el else ""),
                    company=(company_el.inner_text().strip() if company_el else None),
                    location=(location_el.inner_text().strip() if location_el else None),
                    contract_type=(contract_el.inner_text().strip() if contract_el else None),
                )
            )

    return listings


def fetch_job_detail(page: Page, listing: JobListing) -> dict:
    """Visit a job's detail page and extract description + metadata."""
    logger.info("Fetching detail: %s", listing.url)
    page.goto(listing.url, timeout=30000)
    page.wait_for_timeout(1500)
    _accept_cookies(page)
    page.wait_for_timeout(500)

    description = None
    for heading_text in ("Les missions du poste", "Détail du poste", "Description du poste", "Le poste"):
        heading = page.get_by_text(heading_text, exact=False).first
        if heading.count() > 0:
            description = heading.evaluate(
                'el => (el.closest("section") || el.parentElement).innerText'
            ).strip()
            break

    body_text = page.inner_text("body")

    salary_match = re.search(r"(Pas de salaire renseign\w*|[\d\s]+[€$]\s*(?:brut|net)?[^\n]*)", body_text)
    experience_match = re.search(r"Exp\.\s*[^\n]+", body_text)
    ref_match = re.search(r"Réf\s*:\s*(\S+)", body_text)
    published_match = re.search(r"Publiée le\s*([\d/]+)", body_text)

    return {
        "description": description,
        "salary": salary_match.group(0).strip() if salary_match else None,
        "experience": experience_match.group(0).strip() if experience_match else None,
        "published_at": published_match.group(1) if published_match else None,
        "ref": ref_match.group(1) if ref_match else None,
    }


def scrape(
    query: str,
    location: str = "",
    max_pages: int = 1,
    headless: bool = True,
    contract_types: list[str] = CONTRACT_TYPES,
) -> list[dict]:
    """Run the full scrape (search + detail) for a query, return job dicts."""
    results: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()

        listings = search_jobs(
            page, query, location=location, max_pages=max_pages, contract_types=contract_types
        )
        logger.info("Found %d listings for query %r in %r", len(listings), query, location or "(national)")

        for listing in listings:
            try:
                detail = fetch_job_detail(page, listing)
            except Exception:
                logger.exception("Failed to fetch detail for %s", listing.url)
                continue

            results.append(
                {
                    "source": "hellowork",
                    "source_id": listing.source_id,
                    "url": listing.url,
                    "title": listing.title,
                    "company": listing.company,
                    "location": listing.location,
                    "contract_type": listing.contract_type,
                    "salary": detail["salary"],
                    "experience": detail["experience"],
                    "description": detail["description"],
                    "published_at": detail["published_at"],
                }
            )

        browser.close()

    return results
