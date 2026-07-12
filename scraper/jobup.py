"""Playwright scraper for jobup.ch job listings — Suisse romande only
(Genève, Vaud, Neuchâtel; deliberately excludes Zurich/Berne/Bâle, see
DEFAULT_LOCATIONS below and CLAUDE.md's geography priorities).

Search syntax was NOT guessed from the URL: an initial exploratory fetch on
term=/region= params returned 41528 unfiltered results (jobup.ch's homepage
default listing, not a real filter). The real search flow was reverse-
engineered by driving the actual search form with Playwright — typing into
the keyword/location typeahead fields, selecting a real suggestion, and
observing the resulting URL — which produced a genuinely filtered result set
(22-24 offers for "data analyst" @ Genève, vs 41528 unfiltered). See
ROADMAP.md for the full reconnaissance trace. Confirmed real syntax:
    https://www.jobup.ch/fr/emplois/?location=<slug>&term=<query>&employment-type=<code>&page=<n>
- location: a known city/canton slug jobup itself resolves via its own
  typeahead (lowercase, accented, e.g. "genève", "vaud", "neuchâtel") — not
  free text; passing an unrecognized string silently falls back to the
  unfiltered nationwide listing, exactly like the initial broken guess did.
- employment-type: a small integer per contract type, discovered by opening
  the real "Type de contrat" filter panel and reading back which URL each
  selection produced (see CONTRACT_TYPE_CODES below) — not documented
  anywhere in jobup's markup or an obvious guess (they don't follow contract
  name alphabetical/UI order).
- page: 1-indexed, appended by clicking the pagination links on a real
  results page.

Card structure (data-cy attributes, stable across ~20 samples during
reconnaissance): `[data-cy="serp-item"]` per card, `[data-cy="job-link"]`
for the title anchor (title in its `title` attribute, href to the detail
page). Fields inside a card are label/value line pairs in raw text
("Lieu de travail:" / "Taux d'activité:" / "Type de contrat:" each followed
by their value on the next line) — NOT every card has all three labels
(large employers like CERN/UNICEF/SonarSource sometimes omit "Type de
contrat:" and/or "Taux d'activité:" entirely), so parsing must tolerate a
missing label rather than assuming a fixed line count.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urlencode

from playwright.sync_api import Page, sync_playwright

BASE_URL = "https://www.jobup.ch"
SEARCH_URL = BASE_URL + "/fr/emplois/"
COOKIE_BUTTON = "button:has-text(\"OK\")"

# Real location slugs jobup's own typeahead resolves to a filtered result set
# (confirmed by reconnaissance — see module docstring). Suisse romande only,
# per this session's brief: Genève/Vaud/Neuchâtel are the three cantons
# check_geography_rules.SUISSE_ROMANDE_VILLES already recognizes by name.
# Deliberately excludes Zurich/Berne/Bâle/Tessin (suisse_autre in
# scoring/geography.py, priority_rank 4 — lowest of the four ranked zones).
DEFAULT_LOCATIONS = ["genève", "vaud", "neuchâtel"]

# Same default query set as Hellowork (scraper/hellowork.py's
# DEFAULT_JOB_QUERIES), except "IA générative agent LLM" — verified during
# reconnaissance to return ZERO results on jobup.ch (too specific a French
# phrase for its search engine, unlike Hellowork's). Replaced with
# "intelligence artificielle" (12 results in the same test), the closer
# vocabulary match jobup's own search actually resolves — not assumed, this
# alternative was tested and confirmed non-empty before being adopted.
DEFAULT_QUERIES = [
    "data scientist",
    "data analyst",
    "intelligence artificielle",
]

# Numeric employment-type codes, reverse-engineered by opening jobup's real
# "Type de contrat" filter UI and reading back the URL each checkbox
# produced (see module docstring) — not derivable from the UI's display
# order or any visible attribute. Mirrors Hellowork's CONTRACT_TYPES
# exclusion policy: CDI/CDD/freelance equivalents included, Apprentissage/
# Stage/Revenu complémentaire excluded (3.5+ years XP profile, not an entry
# level or side-income search — same reasoning as hellowork.py's own
# Alternance/Stage exclusion).
CONTRACT_TYPE_CODES = {
    "Temporaire": 1,       # CDD equivalent
    "Indépendant": 2,      # Freelance equivalent
    "Durée indéterminée": 5,  # CDI equivalent
}
DEFAULT_CONTRACT_TYPE_CODES = list(CONTRACT_TYPE_CODES.values())

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
    match = re.search(r"/emplois/detail/([0-9a-f-]{36})/?", url)
    if not match:
        raise ValueError(f"Cannot extract job id from URL: {url}")
    return match.group(1)


def _card_field(lines: list[str], label: str) -> str | None:
    """Cards render each field as a "Label:" line followed by its value on
    the next line — but not every card has every label (see module
    docstring: large employers sometimes omit "Type de contrat:"/"Taux
    d'activité:" entirely). Returns None rather than raising if the label
    isn't present, instead of assuming a fixed position.
    """
    try:
        idx = lines.index(label)
    except ValueError:
        return None
    return lines[idx + 1] if idx + 1 < len(lines) else None


# jobup's own "Type de contrat" classification is real but not fully
# reliable: a real scraping run found 3/34 offers whose title clearly
# describes an internship ("Stagiaire...", "...Internship...") but whose
# employment-type is "Temporaire" or "Durée indéterminée" instead of
# "Stage" — see ROADMAP.md session 11. The URL-level employment-type filter
# (CONTRACT_TYPE_CODES) is kept as the primary filter since it's accurate
# for the majority of listings and avoids fetching pages we'd discard
# anyway; this title check is a second, narrower safety net for the cases
# where jobup's own field is simply wrong, not a replacement for it.
_INTERNSHIP_TITLE_RE = re.compile(r"\b(stagiaire|stage|internship|intern)\b", re.IGNORECASE)


def _looks_like_internship(title: str) -> bool:
    return bool(_INTERNSHIP_TITLE_RE.search(title))


def search_jobs(
    page: Page,
    query: str,
    location: str,
    max_pages: int = 1,
    contract_type_codes: list[int] = DEFAULT_CONTRACT_TYPE_CODES,
) -> list[JobListing]:
    """Scrape search result pages for a query + location, returning job summaries."""
    listings: list[JobListing] = []

    for page_num in range(1, max_pages + 1):
        params = [("location", location), ("term", query)]
        params += [("employment-type", code) for code in contract_type_codes]
        params += [("page", page_num)]
        url = SEARCH_URL + "?" + urlencode(params)
        logger.info("Fetching search page %d: %s", page_num, url)
        page.goto(url, timeout=30000)
        page.wait_for_timeout(2000)
        if page_num == 1:
            _accept_cookies(page)
            page.wait_for_timeout(1000)

        cards = page.query_selector_all('[data-cy="serp-item"]')
        if not cards:
            logger.info("No more results at page %d, stopping", page_num)
            break

        for card in cards:
            link = card.query_selector('[data-cy="job-link"]')
            if not link:
                continue
            href = link.get_attribute("href") or ""
            job_url = href if href.startswith("http") else BASE_URL + href

            try:
                source_id = _extract_source_id(job_url)
            except ValueError:
                logger.warning("Skipping card with unparsable URL: %s", job_url)
                continue

            title = (link.get_attribute("title") or "").strip()
            lines = [l.strip() for l in card.inner_text().split("\n") if l.strip()]

            card_location = _card_field(lines, "Lieu de travail:")
            contract_type = _card_field(lines, "Type de contrat:")
            # Company isn't behind a label — it's whatever non-label line
            # remains after title/location/taux/contrat, generally the last
            # substantive line before "Candidature simplifiée"/"Nouveau"/
            # "Sauvegarder" trailer text. Simpler and more robust: take the
            # last line that isn't one of those known trailer strings.
            trailer_strings = {"Candidature simplifiée", "Nouveau", "Sauvegarder"}
            company = next(
                (l for l in reversed(lines) if l not in trailer_strings and l != title
                 and l not in ("Lieu de travail:", "Taux d'activité:", "Type de contrat:")
                 and l != card_location and l != contract_type
                 and not re.match(r"^\d+%$", l)
                 and not re.match(r"^(Il y a|Aujourd|Hier|Avant-hier|La semaine|Le mois)", l)),
                None,
            )

            if _looks_like_internship(title):
                logger.info("Skipping likely internship despite contract_type=%r: %r", contract_type, title)
                continue

            listings.append(
                JobListing(
                    source_id=source_id,
                    url=job_url,
                    title=title,
                    company=company,
                    location=card_location,
                    contract_type=contract_type,
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
    desc_el = page.query_selector('[data-cy="vacancy-description"]')
    if desc_el:
        description = desc_el.inner_text().strip()

    body_text = page.inner_text("body")

    # Publication date: the first absolute "DD month YYYY" date in the body
    # text, which appears right after the job title (before the activity
    # rate/contract type/location block) on every detail page sampled during
    # reconnaissance — see module docstring.
    published_match = re.search(
        r"\b(\d{1,2}\s+(?:janvier|février|mars|avril|mai|juin|juillet|août|"
        r"septembre|octobre|novembre|décembre)\s+\d{4})\b",
        body_text,
    )
    salary_match = re.search(r"CHF[^\n]{0,80}", body_text)

    return {
        "description": description,
        "salary": salary_match.group(0).strip() if salary_match else None,
        "experience": None,  # jobup doesn't expose a distinct experience field on the card/detail page
        "published_at": published_match.group(1) if published_match else None,
    }


def scrape(
    query: str,
    locations: list[str] = DEFAULT_LOCATIONS,
    max_pages: int = 1,
    headless: bool = True,
    contract_type_codes: list[int] = DEFAULT_CONTRACT_TYPE_CODES,
) -> list[dict]:
    """Run the full scrape (search + detail) for a query across all target
    Suisse romande locations, return job dicts. Deduplicates by source_id
    across locations (a job in Genève can also show up under a Vaud search
    if the region overlaps in jobup's own index) before fetching details, so
    the same offer is never fetched/stored twice within one scrape() call.
    """
    results: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()

        seen_source_ids: set[str] = set()
        listings: list[JobListing] = []
        for location in locations:
            location_listings = search_jobs(
                page, query, location=location, max_pages=max_pages,
                contract_type_codes=contract_type_codes,
            )
            for listing in location_listings:
                if listing.source_id not in seen_source_ids:
                    seen_source_ids.add(listing.source_id)
                    listings.append(listing)
        logger.info("Found %d unique listings for query %r across %r", len(listings), query, locations)

        for listing in listings:
            try:
                detail = fetch_job_detail(page, listing)
            except Exception:
                logger.exception("Failed to fetch detail for %s", listing.url)
                continue

            results.append(
                {
                    "source": "jobup",
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
