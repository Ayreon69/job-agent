"""Tests for scraper/linkedin.py's pure parsing, on real HTML returned by
LinkedIn's guest endpoints (2026-09-27 reconnaissance, <script>/<style>
stripped to keep the fixtures small) — no network access."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper.linkedin import job_id_from_url, parse_job_detail, parse_search_cards, skip_reason

FIXTURES = Path(__file__).parent / "fixtures" / "linkedin"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def check(label: str, got, expected) -> int:
    ok = got == expected
    print(f"[{'OK' if ok else 'FAIL'}] {label}: {got!r}" + ("" if ok else f"  (attendu {expected!r})"))
    return 0 if ok else 1


def main() -> None:
    failures = 0

    cards = parse_search_cards(_read("search_geneve_data_scientist.html"))
    failures += check("cartes d'une page de recherche", len(cards), 10)
    first, last = cards[0], cards[-1]
    failures += check("id", first.source_id, "4428513958")
    # Canonical URL, not the card's tracking link (changes on every search).
    failures += check("url canonique", first.url, "https://www.linkedin.com/jobs/view/4428513958/")
    failures += check("titre", first.title, "Senior Data Scientist")
    failures += check("entreprise (lien imbriqué)", first.company, "Vorsee")
    failures += check("lieu", first.location, "Geneva Metropolitan Area")
    failures += check("date ISO -> JJ/MM/AAAA", first.published_at, "20/06/2026")
    # Entities decoded (&#39;, en dash) in the company name.
    failures += check("entités HTML", last.company, "FIA – Fédération Internationale de l'Automobile")
    failures += check("accents", cards[4].location, "Étoy, Vaud, Switzerland")
    failures += check("page vide -> aucune carte", parse_search_cards("<!DOCTYPE html>"), [])

    sonar = parse_job_detail(_read("detail_4464367532_sonar.html"))
    failures += check("contrat traduit", sonar["contract_type"], "Temps plein")
    failures += check("niveau traduit", sonar["experience"], "Confirmé / senior")
    failures += check("pas de salaire affiché", sonar["salary"], None)
    failures += check("pas un stage", sonar["is_internship"], False)
    desc = sonar["description"] or ""
    failures += check("description : début", desc.split("\n")[0], "Who is Sonar?")
    failures += check("description : listes en '- '", "\n- SonarQube: The world’s leading AI code review" in desc, True)
    failures += check("description : pas de ligne vide dans une liste", "\n\n- Obsessed with quality." in desc, False)
    failures += check("description : pas de balise", "<" in desc, False)

    sanofi = parse_job_detail(_read("detail_4460341047_sanofi_salaire.html"))
    failures += check("salaire affiché", sanofi["salary"], "€54,400.00/yr - €72,533.33/yr")
    failures += check("niveau absent -> None", sanofi["experience"], None)

    failures += check("stage (titre)", skip_reason("Data Science Intern"), "stage/alternance")
    failures += check("alternance (titre)", skip_reason("Data Analyst en alternance"), "stage/alternance")
    failures += check("réservé ressortissants", skip_reason("Business Analyst – Data & Reporting (UAE Nationals Only) - DUBAI"),
                      "réservé aux ressortissants")
    failures += check("réservé ressortissants (Emirati Talent)", skip_reason("Emirati Talent - Senior Associate, Data Analyst"),
                      "réservé aux ressortissants")
    # "International" must not trip the "intern" check, nor "Internal".
    failures += check("pas un faux stage", skip_reason("Internal Audit Data Analyst - International"), None)

    failures += check("id depuis l'URL canonique", job_id_from_url("https://www.linkedin.com/jobs/view/4428513958/"), "4428513958")
    failures += check("id depuis une URL avec slug",
                      job_id_from_url("https://ch.linkedin.com/jobs/view/senior-data-scientist-at-vorsee-4428513958?position=1"),
                      "4428513958")

    total = 27
    print(f"\n{total - failures}/{total} cas passés")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
