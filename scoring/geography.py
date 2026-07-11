"""Deterministic geography classification for job offers.

Not RAG-based on purpose: semantic retrieval proved unable to reliably tell
Suisse romande apart from Suisse alémanique/italienne (see ROADMAP.md,
session 2 retest, 2026-07-11). This module does plain keyword/department
matching instead. See check_geography_rules_spec.md for the full spec this
implements.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

Zone = Literal["suisse_romande", "rhone_alpes", "uae_gcc", "suisse_autre", "autre_france", "inconnu"]
MatchMethod = Literal["departement", "ville_connue", "aucun"]


@dataclass
class GeographyVerdict:
    zone: Zone
    priority_rank: int | None
    mobility_signal_allowed: bool
    matched_keyword: str | None
    match_method: MatchMethod


# Départements de la région Auvergne-Rhône-Alpes (deux premiers chiffres du code postal).
RHONE_ALPES_DEPARTEMENTS = {"01", "07", "26", "38", "42", "69", "73", "74"}

# Rhône-Alpes : grandes villes connues, utilisées en repli si aucun département
# n'est identifiable dans le texte (cf. spec, point 2).
RHONE_ALPES_VILLES = [
    "lyon", "villeurbanne", "grenoble", "annecy", "saint-etienne", "saint etienne",
    "chambery", "valence", "bourg-en-bresse", "bourg en bresse", "vienne", "civrieux",
    "rhone-alpes", "rhone alpes", "auvergne-rhone-alpes", "auvergne rhone alpes",
]

# Suisse romande : Fribourg est traité comme romand par approximation documentée
# (canton majoritairement francophone), voir spec "Cas particuliers".
SUISSE_ROMANDE_VILLES = [
    "geneve", "geneva", "lausanne", "neuchatel", "yverdon-les-bains", "yverdon",
    "nyon", "vevey", "montreux", "fribourg", "freiburg", "sion", "vaud", "valais",
]

UAE_GCC_VILLES = [
    "dubai", "dubai", "abu dhabi", "abou dabi", "uae", "emirats", "sharjah",
    "doha", "qatar", "riyadh", "riyad", "arabie saoudite", "saudi arabia",
    "koweit", "kuwait", "bahrain", "bahreïn", "bahrein", "oman", "muscat",
]

# Suisse hors Romandie : "suisse alemanique" et "deutschschweiz" servent à détecter
# une mention explicite de la zone sans nom de ville précis (cf. cas particuliers).
SUISSE_AUTRE_VILLES = [
    "zurich", "zuerich", "bale", "basel", "berne", "bern", "lucerne", "lucerna",
    "winterthur", "lugano", "tessin", "ticino", "suisse alemanique", "deutschschweiz",
]

# Pays étrangers hors des zones ci-dessus, vus dans les offres scrapées (ex:
# Hellowork remonte occasionnellement des offres Belgique/Luxembourg). Sert
# uniquement à éviter de classer ces offres en "autre_france" par défaut — elles
# doivent rester "inconnu" plutôt que de forcer la règle Lyon/France à tort.
FOREIGN_NON_TARGET_COUNTRIES = [
    "belgique", "belgium", "luxembourg", "allemagne", "germany", "espagne", "spain",
    "italie", "italy", "royaume-uni", "royaume uni", "united kingdom", "pays-bas",
    "pays bas", "netherlands", "canada", "etats-unis", "etats unis", "usa",
]

ZONE_CONFIG: dict[Zone, dict] = {
    "suisse_romande": {"priority_rank": 1, "mobility_signal_allowed": True},
    "rhone_alpes": {"priority_rank": 2, "mobility_signal_allowed": False},
    "uae_gcc": {"priority_rank": 3, "mobility_signal_allowed": True},
    "suisse_autre": {"priority_rank": 4, "mobility_signal_allowed": True},
    "autre_france": {"priority_rank": None, "mobility_signal_allowed": False},
    "inconnu": {"priority_rank": None, "mobility_signal_allowed": False},
}

POSTAL_CODE_RE = re.compile(r"\b(\d{5})\b")
# "(38)" / "dept 38" / "département 38" / "- 69" (format Hellowork "Ville - NN") —
# un numéro de département à deux chiffres isolé, entre parenthèses, précédé du
# mot "département"/"dept", ou précédé d'un tiret en fin de texte.
DEPARTEMENT_MENTION_RE = re.compile(
    r"(?:d[eé]partement|dept\.?)\s*(\d{2})\b|\((\d{2})\)|-\s*(\d{2})\s*$"
)


def _normalize(text: str) -> str:
    """Lowercase and strip accents for accent/case-insensitive matching."""
    decomposed = unicodedata.normalize("NFD", text)
    without_accents = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return without_accents.lower()


def _find_departement_code(text: str) -> str | None:
    """Extract a 2-digit département code from a postal code or explicit mention."""
    postal_match = POSTAL_CODE_RE.search(text)
    if postal_match:
        return postal_match.group(1)[:2]

    dept_match = DEPARTEMENT_MENTION_RE.search(text)
    if dept_match:
        return dept_match.group(1) or dept_match.group(2) or dept_match.group(3)

    return None


def _find_first_keyword(normalized_text: str, keywords: list[str]) -> str | None:
    """Return the first keyword (longest first, to prefer specific matches) found."""
    for keyword in sorted(keywords, key=len, reverse=True):
        if keyword in normalized_text:
            return keyword
    return None


def _make_verdict(zone: Zone, matched_keyword: str | None, match_method: MatchMethod) -> GeographyVerdict:
    config = ZONE_CONFIG[zone]
    return GeographyVerdict(
        zone=zone,
        priority_rank=config["priority_rank"],
        mobility_signal_allowed=config["mobility_signal_allowed"],
        matched_keyword=matched_keyword,
        match_method=match_method,
    )


def check_geography_rules(offer_location: str) -> GeographyVerdict:
    """Classify a raw job-offer location string into a geography zone.

    Matching order (most specific first, per spec "Ordre de priorité dans le
    matching"): city-name keywords first (ville_connue), then département /
    postal code, so an explicit city name always wins over a broader region
    code that might also appear in the same string.
    """
    text = offer_location or ""
    normalized = _normalize(text)

    # 1. Ville connue la plus spécifique, toutes zones confondues, en priorité.
    for zone, villes in (
        ("suisse_romande", SUISSE_ROMANDE_VILLES),
        ("suisse_autre", SUISSE_AUTRE_VILLES),
        ("uae_gcc", UAE_GCC_VILLES),
        ("rhone_alpes", RHONE_ALPES_VILLES),
    ):
        keyword = _find_first_keyword(normalized, villes)
        if keyword:
            return _make_verdict(zone, keyword, "ville_connue")

    # 2. Pas de ville connue : tenter un matching par département (Rhône-Alpes
    #    uniquement, cf. spec — les autres zones n'ont pas de logique département).
    dept_code = _find_departement_code(text)
    if dept_code and dept_code in RHONE_ALPES_DEPARTEMENTS:
        return _make_verdict("rhone_alpes", dept_code, "departement")

    # 3. "Suisse" seul, sans ville précisée : ne jamais présumer romande.
    if re.search(r"\bsuisse\b|\bswitzerland\b", normalized) and dept_code is None:
        return _make_verdict("inconnu", None, "aucun")

    # 4. Mention générique de la France, sans ville/département identifiable.
    if re.search(r"\bfrance\b", normalized):
        return _make_verdict("autre_france", None, "aucun")

    # 5. Pays étranger connu mais hors des zones ciblées (ex: Belgique, Luxembourg) :
    #    ne jamais classer en "autre_france" par défaut, ce qui appliquerait à tort
    #    la règle "zéro signal de mobilité" pensée pour la France.
    foreign_keyword = _find_first_keyword(normalized, FOREIGN_NON_TARGET_COUNTRIES)
    if foreign_keyword:
        return _make_verdict("inconnu", foreign_keyword, "aucun")

    # 6. Mot-clé générique "remote"/"télétravail" sans pays précisé.
    if re.search(r"\bremote\b|\bt[ée]l[ée]travail\b", normalized):
        return _make_verdict("inconnu", None, "aucun")

    # 7. Reste : par défaut prudent, seul un texte non vide sans aucun signal
    #    d'un pays étranger est traité comme "autre_france" (cf. spec: "Paris 8e"
    #    doit donner autre_france sans mention explicite de "France").
    if text.strip():
        return _make_verdict("autre_france", None, "aucun")

    return _make_verdict("inconnu", None, "aucun")
