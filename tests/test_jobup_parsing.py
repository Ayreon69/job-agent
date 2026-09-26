"""Tests for scraper/jobup.py's card parsing (_card_company), on card texts
copied from real jobup.ch search results (2026-09-26 reconnaissance)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper.jobup import _card_company, _card_field

CASES = [
    # Plain card: company is the last line.
    (
        ["Il y a 4 jours", "·", "Consulté", "F1 Data Scientist", "Lieu de travail:", "Geneva",
         "Taux d'activité:", "100%", "Type de contrat:", "Durée indéterminée",
         "FEDERATION INTERNATIONALE DE L'AUTOMOBILE"],
        "F1 Data Scientist",
        "FEDERATION INTERNATIONALE DE L'AUTOMOBILE",
    ),
    # "Nouveau" trailer after the company.
    (
        ["Aujourd'hui", "Data Analyst", "Lieu de travail:", "Lausanne", "Type de contrat:",
         "Durée indéterminée", "Talan", "Nouveau"],
        "Data Analyst",
        "Talan",
    ),
    # Régression 2026-09 : le widget « Offre pertinente ? » ajouté sous
    # certaines cartes était pris pour l'entreprise (143/185 offres jobup).
    (
        ["La semaine dernière", "BUSINESS ANALYST", "Lieu de travail:", "Grand-Lancy",
         "Taux d'activité:", "100%", "Type de contrat:", "Durée indéterminée", "Experis",
         "Offre pertinente ?"],
        "BUSINESS ANALYST",
        "Experis",
    ),
    # Any other trailing question-widget is skipped the same way.
    (
        ["Hier", "Data Engineer", "Lieu de travail:", "Genève", "Type de contrat:", "Temporaire",
         "Randstad (Schweiz) AG", "Cette offre vous intéresse ?"],
        "Data Engineer",
        "Randstad (Schweiz) AG",
    ),
    # No company line at all -> None rather than a label or a date.
    (
        ["Il y a 2 jours", "Data Scientist", "Lieu de travail:", "Nyon", "Type de contrat:",
         "Durée indéterminée", "Candidature simplifiée"],
        "Data Scientist",
        None,
    ),
]


def main() -> None:
    failures = 0
    for lines, title, expected in CASES:
        location = _card_field(lines, "Lieu de travail:")
        contract = _card_field(lines, "Type de contrat:")
        got = _card_company(lines, title, location, contract)
        ok = got == expected
        failures += not ok
        print(f"[{'OK' if ok else 'FAIL'}] {title!r:28} -> {got!r}" + ("" if ok else f"  (attendu {expected!r})"))

    print(f"\n{len(CASES) - failures}/{len(CASES)} cas passés")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
