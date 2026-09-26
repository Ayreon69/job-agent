"""Same offer published on two sources (LinkedIn and jobup.ch, mostly).

Measured on the first LinkedIn search run (2026-09-27, ROADMAP.md session
19): 199 LinkedIn offers, 14 of them already stored from jobup — FIA,
Nexthink, Talan, Vaudoise, Swissquote, Flyability... Stored twice, each
would be scored twice by Mistral and shown twice in the dashboard.

jobup's own republication check (scraper/jobup.py's is_same_offer) can't be
reused as is, because across sources:
  - places are written differently ("Paudex" vs "Paudex, Vaud,
    Switzerland", "Genève" vs "Geneva, Geneva, Switzerland");
  - jobup machine-translates English offers into French and prepends an AI
    summary: the same Nexthink/FIA offer then scores ~0.1 in word
    similarity against its LinkedIn original, while same-language twins
    score 0.86-0.96 (Talan, Vaudoise, Swissquote, Michael Page);
  - company names vary ("FIA – Fédération Internationale de l'Automobile"
    vs "FEDERATION INTERNATIONALE DE L'AUTOMOBILE").

Hence two ways to be the same offer, both requiring the same normalized
title and the same place:
  1. companies known on both sides and compatible (equal, or one contained
     in the other) — language-independent, decidable on a search card
     before any detail page is fetched;
  2. a company unknown on one side (legacy jobup rows still carrying the
     "Offre pertinente ?" artifact): descriptions must then be >= 0.85
     similar. "Senior AI Engineer" at Chaberton (LinkedIn) vs Nexthink's
     (jobup, company unknown), same title, same canton: 0.02 — kept apart.
Accepted risk of rule 1: one company posting two distinct openings with the
exact same title in the same place, one per source — the second one is
then not stored, while its identical-looking twin stays visible.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping

from scoring.geography import check_geography_rules
from scraper.jobup import DESCRIPTION_SIMILARITY_THRESHOLD, description_similarity, normalize_title

Row = Mapping[str, str | None]

# Zones that say where an offer is; "autre_france"/"inconnu" are defaults
# that say nothing about two offers being in the same place.
_PLACE_ZONES = {"suisse_romande", "rhone_alpes", "uae_gcc", "suisse_autre"}
_AREA_SUFFIX_RE = re.compile(r"\b(metropolitan area|area)\b|^greater\b")
# jobup card chrome once stored as the company (fixed in 9e5a3e6, legacy rows
# heal on their next scrape) — means "unknown", not a company called that.
_COMPANY_ARTIFACTS = {"offre pertinente"}


def _fold(text: str | None) -> str:
    ascii_text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()


def _city(location: str | None) -> str:
    """First part of a location, folded: "Paudex, Vaud, Switzerland" ->
    "paudex", "Geneva Metropolitan Area" -> "geneva", "Lyon - 69" -> "lyon"."""
    first = re.split(r",| - |\(", location or "")[0]
    return _AREA_SUFFIX_RE.sub(" ", _fold(first)).strip()


def same_place(a: str | None, b: str | None) -> bool:
    city_a, city_b = _city(a), _city(b)
    if city_a and city_a == city_b:
        return True
    zone_a, zone_b = check_geography_rules(a or "").zone, check_geography_rules(b or "").zone
    return zone_a == zone_b and zone_a in _PLACE_ZONES


def company_key(company: str | None) -> str | None:
    folded = _fold(company)
    if not folded or folded in _COMPANY_ARTIFACTS:
        return None
    return folded


def companies_match(a: str | None, b: str | None) -> bool | None:
    """True/False when both companies are known, None when one isn't."""
    key_a, key_b = company_key(a), company_key(b)
    if not key_a or not key_b:
        return None
    return key_a == key_b or f" {key_a} " in f" {key_b} " or f" {key_b} " in f" {key_a} "


def is_cross_source_twin(candidate: Row, stored: Row, *, need_description: bool = True) -> bool:
    """Rules 1 and 2 of the module docstring. With need_description=False
    (search card, no description yet) only rule 1 can answer True."""
    if normalize_title(candidate["title"]) != normalize_title(stored["title"]):
        return False
    if not same_place(candidate["location"], stored["location"]):
        return False
    companies = companies_match(candidate["company"], stored["company"])
    if companies is not None:
        return companies
    if not need_description:
        return False
    desc_a, desc_b = candidate.get("description"), stored.get("description")
    if not desc_a or not desc_b:
        return False
    return description_similarity(_fold(desc_a), _fold(desc_b)) >= DESCRIPTION_SIMILARITY_THRESHOLD


def find_twin(candidate: Row, stored_rows: Iterable[Row], *, need_description: bool = True) -> Row | None:
    """First stored row of another source that is the same offer as
    candidate, or None."""
    for row in stored_rows:
        if row["source"] != candidate["source"] and is_cross_source_twin(candidate, row, need_description=need_description):
            return row
    return None
