"""Tests for scraper/cross_source.py (same offer on LinkedIn and jobup/
Hellowork) and its use in scraper/run.py. Titles, companies and places are
the real pairs measured on the first LinkedIn run (2026-09-27, ROADMAP.md
session 19); descriptions are short stand-ins — no network access."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper.cross_source import companies_match, find_twin, is_cross_source_twin, same_place
from scraper.run import _store_jobs, store_jobup_jobs
from storage.db import connect, init_db

TEXT_A = " ".join(f"mission{i} competence{i}" for i in range(80))
TEXT_B = " ".join(f"autre{i} texte{i}" for i in range(80))


def offer(source: str, title: str, company: str | None, location: str, description: str | None = None, **extra) -> dict:
    return {"source": source, "title": title, "company": company, "location": location, "description": description, **extra}


PAIR_CASES = [
    # (label, candidate, stored, need_description, expected)
    ("FIA : nom d'entreprise contenu dans l'autre, dès la carte",
     offer("linkedin", "F1 Data Scientist", "FIA – Fédération Internationale de l'Automobile", "Geneva, Switzerland"),
     offer("jobup", "F1 Data Scientist", "FEDERATION INTERNATIONALE DE L'AUTOMOBILE", "Geneva"),
     False, True),
    ("Talan : Genève écrit de deux façons",
     offer("linkedin", "Lead Data Analyst", "Talan", "Genève, Geneva, Switzerland"),
     offer("jobup", "Lead Data Analyst", "Talan", "Genève"),
     False, True),
    # Traduit par jobup : descriptions ~0.1 similaires, l'entreprise suffit.
    ("même offre traduite, entreprise connue des deux côtés",
     offer("linkedin", "Senior AI Engineer", "Nexthink", "Lausanne, Vaud, Switzerland", TEXT_A),
     offer("jobup", "Senior AI Engineer", "Nexthink", "Lausanne", TEXT_B),
     True, True),
    ("Chaberton vs Nexthink (entreprise jobup inconnue), descriptions différentes",
     offer("linkedin", "Senior AI Engineer", "Chaberton Professionals", "Vaud, Switzerland", TEXT_A),
     offer("jobup", "Senior AI Engineer", "Offre pertinente ?", "Lausanne", TEXT_B),
     True, False),
    ("entreprise inconnue, descriptions identiques",
     offer("linkedin", "Data Oversight & Transformation Lead", "Swissquote", "Gland, Vaud, Switzerland", TEXT_A),
     offer("jobup", "Data Oversight & Transformation Lead", "Offre pertinente ?", "Gland", TEXT_A),
     True, True),
    ("entreprise inconnue : jamais décidé sur la carte seule",
     offer("linkedin", "Data Oversight & Transformation Lead", "Swissquote", "Gland, Vaud, Switzerland"),
     offer("jobup", "Data Oversight & Transformation Lead", "Offre pertinente ?", "Gland", TEXT_A),
     False, False),
    ("même titre, entreprises différentes",
     offer("linkedin", "Data Scientist", "Capgemini Engineering", "Lyon, Auvergne-Rhône-Alpes, France"),
     offer("hellowork", "Data Scientist H/F", "Klanik", "Lyon - 69"),
     False, False),
    ("même titre et entreprise, autre pays",
     offer("linkedin", "Senior Data Analyst", "Talan", "Dubai, United Arab Emirates"),
     offer("jobup", "Senior Data Analyst", "Talan", "Genève"),
     False, False),
    ("marqueur H/F ignoré dans le titre",
     offer("linkedin", "Data Scientist", "Sanofi", "Lyon, Auvergne-Rhône-Alpes, France"),
     offer("hellowork", "Data Scientist H/F", "Sanofi", "Lyon - 69"),
     False, True),
]

PLACE_CASES = [
    ("Paudex", "Paudex, Vaud, Switzerland", True),
    ("Geneva Metropolitan Area", "Genève", True),
    ("Lyon - 69", "Greater Lyon Area", True),
    ("Lausanne", "Dubai, United Arab Emirates", False),
    # autre_france is a default, not a place: two unrelated French cities differ.
    ("Paris", "Bordeaux, Nouvelle-Aquitaine, France", False),
]


def check(label: str, got, expected) -> int:
    ok = got == expected
    print(f"[{'OK' if ok else 'FAIL'}] {label}: {got!r}" + ("" if ok else f"  (attendu {expected!r})"))
    return 0 if ok else 1


def _insert(conn, source: str, source_id: str, title: str, company: str | None, location: str, description: str) -> None:
    conn.execute(
        "INSERT INTO jobs (source, source_id, url, title, company, location, description) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (source, source_id, f"https://example.test/{source}/{source_id}", title, company, location, description),
    )


def _job(source: str, source_id: str, title: str, company: str | None, location: str, description: str) -> dict:
    return {
        "source": source, "source_id": source_id, "url": f"https://example.test/{source}/{source_id}",
        "title": title, "company": company, "location": location, "contract_type": None,
        "salary": None, "experience": None, "description": description, "published_at": None,
    }


def store_scenarios() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "jobs.db"
        init_db(db_path)
        with connect(db_path) as conn:
            _insert(conn, "jobup", "uuid-talan", "Lead Data Analyst", "Talan", "Genève", TEXT_B)
            _insert(conn, "linkedin", "111", "Senior AI Engineer", "Nexthink", "Lausanne, Vaud, Switzerland", TEXT_A)

            # A new LinkedIn offer already stored from jobup is not stored again;
            # an unrelated one is.
            new = _store_jobs(conn, [
                _job("linkedin", "222", "Lead Data Analyst", "Talan", "Genève, Geneva, Switzerland", TEXT_A),
                _job("linkedin", "333", "Data Analyst", "EDGE", "Abu Dhabi, United Arab Emirates", TEXT_A),
            ])
            failures += check("LinkedIn : doublon jobup non stocké, l'autre oui", new, 1)
            failures += check("LinkedIn : lignes en base",
                              sorted(r[0] for r in conn.execute("SELECT source_id FROM jobs WHERE source = 'linkedin'")),
                              ["111", "333"])

            # The other direction: jobup finds, later, an offer LinkedIn already brought.
            inserted, _, _ = store_jobup_jobs(conn, [
                _job("jobup", "uuid-nexthink", "Senior AI Engineer", "Nexthink", "Lausanne", TEXT_B),
                _job("jobup", "uuid-autre", "Data Engineer", "Romande Energie", "Morges", TEXT_B),
            ])
            failures += check("jobup : doublon LinkedIn non stocké, l'autre oui", inserted, 1)

            # Already-stored offers are refreshed as before, twin or not.
            new = _store_jobs(conn, [_job("linkedin", "111", "Senior AI Engineer", "Nexthink", "Lausanne, Vaud, Switzerland", TEXT_A)])
            failures += check("offre déjà stockée : simple rafraîchissement", new, 0)
            failures += check("total en base", conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 4)
    return failures


def main() -> None:
    failures = total = 0
    for label, candidate, stored, need_description, expected in PAIR_CASES:
        failures += check(label, is_cross_source_twin(candidate, stored, need_description=need_description), expected)
        total += 1
    for a, b, expected in PLACE_CASES:
        failures += check(f"même lieu {a!r} / {b!r}", same_place(a, b), expected)
        total += 1

    failures += check("entreprise-artefact = inconnue", companies_match("Offre pertinente ?", "Nexthink"), None)
    failures += check("même source jamais comparée",
                      find_twin(offer("jobup", "Lead Data Analyst", "Talan", "Genève"),
                                [offer("jobup", "Lead Data Analyst", "Talan", "Genève", id=1)]),
                      None)
    total += 2

    failures += store_scenarios()
    total += 5

    print(f"\n{total - failures}/{total} cas passés")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
