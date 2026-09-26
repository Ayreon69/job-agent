"""LinkedIn job offers through LinkedIn's public guest endpoints — the ones its
own logged-out job search page calls. No account, no login, no cookie: this
module must never be given LinkedIn credentials (an automated logged-in
session is the surest way to get the user's own account restricted).

Reconnaissance (2026-09-27, see ROADMAP.md session 19), all confirmed live:
    search: https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
            ?keywords=<q>&location=<free text>&f_TPR=r2592000&start=<0,10,20...>
    detail: https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/<job id>
- Plain HTML fragments, served to a plain HTTP client: no browser needed,
  unlike Hellowork/jobup (Playwright). urllib from the stdlib is enough.
- 10 cards per call; `start` moves by 10, two consecutive pages never
  overlapped on the 16 searches sampled.
- `location` is free text resolved by LinkedIn itself ("Genève", "Vaud",
  "Dubai", "Abu Dhabi" all returned offers of the right place — Genève also
  returns nearby Vaud/Valais, which is fine).
- `f_TPR=r2592000` (posted in the last 30 days) is honoured. `f_JT`
  (contract type) is NOT: "f_JT=I" (internships) returned exactly the same
  cards as no filter at all. Internships are therefore dropped here, on
  the title before any detail fetch, then on the detail page's own
  "Employment type"/"Seniority level" criteria.
- Locations come in English ("Geneva, Geneva, Switzerland", "United Arab
  Emirates"): scoring/geography.py was completed for them in the same
  session.

Request volume is kept deliberately low (LinkedIn's terms forbid automated
collection; logged-out volume is tolerated but rate-limited, and hosted CI
IP ranges are often refused outright): a pause of a few seconds between
calls, and the detail page is fetched only for offers not already stored —
already-known offers are just marked as seen again (see scraper/run.py).
An HTTP 429/999 stops the whole LinkedIn run for the day instead of
hammering on; what was collected until then is kept.
"""

from __future__ import annotations

import html
import logging
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urlencode

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
VIEW_URL = "https://www.linkedin.com/jobs/view/{job_id}/"
PAGE_SIZE = 10

# Suisse romande (priority 1) and UAE (priority 3, not covered by any other
# source until now). Rhône-Alpes stays Hellowork's job; "Lyon" can be added
# with --linkedin-location, at the cost of many offers Hellowork already has.
DEFAULT_LOCATIONS = ["Genève", "Vaud", "Dubai", "Abu Dhabi"]

# "AI engineer" rather than jobup's "intelligence artificielle": LinkedIn
# search is English-first, and this query returned 20/20 relevant titles
# in Genève, Dubai and Lyon alike (GenAI/agentic/ML engineer roles).
DEFAULT_QUERIES = ["data scientist", "data analyst", "AI engineer"]
DEFAULT_PAGES = 2
POSTED_WITHIN = "r2592000"  # last 30 days

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
# English UI: the criteria labels ("Employment type"...) parsed below are
# then stable whatever the machine's locale.
ACCEPT_LANGUAGE = "en-US,en;q=0.9"
REQUEST_PAUSE_SECONDS = (2.0, 4.5)

logger = logging.getLogger(__name__)


class LinkedInRefused(RuntimeError):
    """LinkedIn answered 429 (rate limit) or 999 (its bot refusal code)."""


@dataclass
class JobListing:
    source_id: str
    url: str
    title: str
    company: str | None
    location: str | None
    published_at: str | None


# ---------------------------------------------------------------------------
# Pure parsing (tested on real HTML in tests/test_linkedin_parsing.py)
# ---------------------------------------------------------------------------

_CARD_SPLIT_RE = re.compile(r"<li[\s>]")
_JOB_ID_RE = re.compile(r"urn:li:jobPosting:(\d+)")
_CARD_TITLE_RE = re.compile(r'class="base-search-card__title"[^>]*>(.*?)</h3>', re.S)
_CARD_COMPANY_RE = re.compile(r'class="base-search-card__subtitle"[^>]*>(.*?)</h4>', re.S)
_CARD_LOCATION_RE = re.compile(r'class="job-search-card__location"[^>]*>(.*?)</span>', re.S)
_CARD_DATE_RE = re.compile(r'<time[^>]*class="job-search-card__listdate[^"]*"[^>]*datetime="(\d{4}-\d{2}-\d{2})"')


def _text(fragment: str | None) -> str | None:
    """Inner text of a small HTML fragment: tags dropped, entities decoded,
    whitespace collapsed. None if nothing is left."""
    if fragment is None:
        return None
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()
    return text or None


def _to_published_at(iso_day: str | None) -> str | None:
    """"2026-09-20" -> "20/09/2026": the DD/MM/YYYY format Hellowork already
    uses, so storage/db.parse_published_at and the dashboard read it as is."""
    if not iso_day:
        return None
    try:
        return date.fromisoformat(iso_day).strftime("%d/%m/%Y")
    except ValueError:
        return None


def parse_search_cards(page_html: str) -> list[JobListing]:
    """Cards of one search call. A card without a job id or a title is
    skipped (nothing to store or to fetch); every other field may be None."""
    listings: list[JobListing] = []
    for chunk in _CARD_SPLIT_RE.split(page_html)[1:]:
        id_match = _JOB_ID_RE.search(chunk)
        title_match = _CARD_TITLE_RE.search(chunk)
        title = _text(title_match.group(1)) if title_match else None
        if not id_match or not title:
            continue
        company_match = _CARD_COMPANY_RE.search(chunk)
        location_match = _CARD_LOCATION_RE.search(chunk)
        date_match = _CARD_DATE_RE.search(chunk)
        job_id = id_match.group(1)
        listings.append(
            JobListing(
                source_id=job_id,
                # Canonical view URL rather than the card's tracking link
                # (refId/trackingId change on every search).
                url=VIEW_URL.format(job_id=job_id),
                title=title,
                company=_text(company_match.group(1)) if company_match else None,
                location=_text(location_match.group(1)) if location_match else None,
                published_at=_to_published_at(date_match.group(1) if date_match else None),
            )
        )
    return listings


class _DescriptionText(HTMLParser):
    """Rich-text description -> plain text keeping its structure: one line
    per paragraph/<br>, "- " before list items. The dashboard's
    descriptionHtml then rebuilds headings and lists from those lines, as it
    does for the other sources."""

    _BREAKS = {"br", "p", "div", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "li":
            self.parts.append("\n- ")
        elif tag in self._BREAKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BREAKS or tag == "li":
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        lines = [re.sub(r"[ \t\xa0]+", " ", line).strip() for line in "".join(self.parts).split("\n")]
        out: list[str] = []
        for line in lines:
            if line in ("", "-"):
                if out and out[-1] != "":
                    out.append("")
                continue
            out.append(line)
        # </li> and the next <li> both break: no blank line inside a list.
        out = [
            line for i, line in enumerate(out)
            if not (line == "" and 0 < i < len(out) - 1 and out[i - 1].startswith("- ") and out[i + 1].startswith("- "))
        ]
        return "\n".join(out).strip()


_DESCRIPTION_RE = re.compile(
    r'<div class="show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>\s*(?:<button|</section>)', re.S
)
_CRITERIA_RE = re.compile(
    r'class="description__job-criteria-subheader"[^>]*>(.*?)</h3>\s*'
    r'<span class="description__job-criteria-text[^"]*"[^>]*>(.*?)</span>',
    re.S,
)
_SALARY_RE = re.compile(r'class="[^"]*\bsalary\b[^"]*"[^>]*>(.*?)</div>', re.S)

# LinkedIn's English criteria values -> the French wording the rest of the
# app uses. Unknown values are kept verbatim rather than guessed.
EMPLOYMENT_TYPES_FR = {
    "Full-time": "Temps plein",
    "Part-time": "Temps partiel",
    "Contract": "Contrat / mission",
    "Temporary": "Temporaire",
    "Internship": "Stage",
    "Volunteer": "Bénévolat",
    "Other": None,
}
SENIORITY_FR = {
    "Internship": "Stage",
    "Entry level": "Débutant",
    "Associate": "Junior / intermédiaire",
    "Mid-Senior level": "Confirmé / senior",
    "Director": "Directeur",
    "Executive": "Direction",
    "Not Applicable": None,
}


def parse_job_detail(page_html: str) -> dict:
    """description, contract_type, experience and salary of a detail page
    (None when absent), plus is_internship from LinkedIn's own criteria."""
    description = None
    desc_match = _DESCRIPTION_RE.search(page_html)
    if desc_match:
        parser = _DescriptionText()
        parser.feed(desc_match.group(1))
        description = parser.text() or None

    criteria = {_text(label): _text(value) for label, value in _CRITERIA_RE.findall(page_html)}
    employment = criteria.get("Employment type")
    seniority = criteria.get("Seniority level")

    salary_match = _SALARY_RE.search(page_html)
    return {
        "description": description,
        "contract_type": EMPLOYMENT_TYPES_FR.get(employment, employment) if employment else None,
        "experience": SENIORITY_FR.get(seniority, seniority) if seniority else None,
        "salary": _text(salary_match.group(1)) if salary_match else None,
        "is_internship": "Internship" in (employment, seniority),
    }


# Same net as jobup's title check (its f_JT equivalent isn't honoured here
# at all, see module docstring), plus offers reserved to nationals of a Gulf
# country — frequent in UAE results ("UAE Nationals Only", "Emirati Talent")
# and closed to this profile whatever the score would say.
_INTERNSHIP_TITLE_RE = re.compile(r"\b(stagiaire|stage|internship|intern|alternance|apprenti)\b", re.I)
_NATIONALS_ONLY_RE = re.compile(
    r"\b(uae|emirati|qatari|saudi|kuwaiti|omani|bahraini)\s+nationals?\b|\bemirati\s+talent\b"
    r"|\bnationals\s+only\b|\bemirati[sz]ation\b",
    re.I,
)


def skip_reason(title: str) -> str | None:
    if _INTERNSHIP_TITLE_RE.search(title):
        return "stage/alternance"
    if _NATIONALS_ONLY_RE.search(title):
        return "réservé aux ressortissants"
    return None


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _get(url: str) -> str:
    time.sleep(random.uniform(*REQUEST_PAUSE_SECONDS))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": ACCEPT_LANGUAGE})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code in (429, 999):
            raise LinkedInRefused(f"HTTP {exc.code} on {url}") from exc
        raise


def search_jobs(query: str, location: str, max_pages: int = DEFAULT_PAGES) -> list[JobListing]:
    listings: list[JobListing] = []
    for page_num in range(max_pages):
        params = {"keywords": query, "location": location, "f_TPR": POSTED_WITHIN, "start": page_num * PAGE_SIZE}
        url = SEARCH_URL + "?" + urlencode(params)
        logger.info("Fetching search page %d: %s", page_num + 1, url)
        cards = parse_search_cards(_get(url))
        if not cards:
            logger.info("No more results at page %d, stopping", page_num + 1)
            break
        listings.extend(cards)
    return listings


def fetch_job_detail(job_id: str) -> dict:
    logger.info("Fetching detail: %s", job_id)
    return parse_job_detail(_get(DETAIL_URL.format(job_id=job_id)))


def job_id_from_url(url: str) -> str | None:
    """Job id of a stored LinkedIn URL (…/jobs/view/<id>/ or …-<id>?…)."""
    match = re.search(r"(\d{6,})/?(?:\?|$)", url)
    return match.group(1) if match else None


def collect_listings(
    queries: list[str],
    locations: list[str] = DEFAULT_LOCATIONS,
    max_pages: int = DEFAULT_PAGES,
) -> list[JobListing]:
    """Search cards for every query x location, deduplicated by job id. On
    LinkedInRefused, logs it and returns what was collected until then."""
    listings: dict[str, JobListing] = {}
    try:
        for query in queries:
            for location in locations:
                logger.info("=== [linkedin] query %r @ %r ===", query, location)
                for listing in search_jobs(query, location, max_pages=max_pages):
                    listings.setdefault(listing.source_id, listing)
    except LinkedInRefused as exc:
        logger.warning("[linkedin] refused by LinkedIn (%s): search stopped, keeping %d listings", exc, len(listings))
    return list(listings.values())


def fetch_offers(listings: list[JobListing]) -> list[dict]:
    """Detail page of each listing -> job dicts in the shape scraper/run.py
    stores. Internships and nationals-only offers are dropped (title first,
    so without a request, then LinkedIn's own criteria). Stops at the first
    LinkedInRefused, keeping what was fetched."""
    results: list[dict] = []
    for listing in listings:
        reason = skip_reason(listing.title)
        if reason:
            logger.info("[linkedin] skipped (%s): %r", reason, listing.title)
            continue
        try:
            detail = fetch_job_detail(listing.source_id)
        except LinkedInRefused as exc:
            logger.warning("[linkedin] refused by LinkedIn (%s): detail fetching stopped", exc)
            break
        except Exception:
            logger.exception("Failed to fetch detail for %s", listing.url)
            continue
        if detail["is_internship"]:
            logger.info("[linkedin] skipped (stage selon LinkedIn): %r", listing.title)
            continue
        results.append(
            {
                "source": "linkedin",
                "source_id": listing.source_id,
                "url": listing.url,
                "title": listing.title,
                "company": listing.company,
                "location": listing.location,
                "contract_type": detail["contract_type"],
                "salary": detail["salary"],
                "experience": detail["experience"],
                "description": detail["description"],
                "published_at": listing.published_at,
            }
        )
    return results
