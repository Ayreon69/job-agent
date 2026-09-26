"""Tests for the "same jobup offer under several source_ids" handling:
scraper/jobup.py's is_same_offer (identity rule) and scraper/run.py's
store_jobup_jobs (what gets written), on descriptions copied from real
jobs.db rows (2026-09-26 reconnaissance — see ROADMAP.md session 18)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper.jobup import description_similarity, is_same_offer, normalize_title
from scraper.run import store_jobup_jobs
from storage.db import connect, init_db

_WIDGET = """Vous correspondez très bien à ce poste

Votre expérience avec cela ...
Le diplôme en économie ...
Améliorez cette compétence pour obtenir un ...

Ce poste est-il fait pour vous ?

Voir mon match
À propos de cette offre

CDI - Taux 100%
"""

# jobs.db #4594 and #4596: the same OK Job SA offer, published twice (14 and
# 16 septembre), the second time with a reworded layout and "Automation/
# développement" written without spaces. Word similarity 0.891 — the lowest
# of all real duplicates measured.
BECKHOFF_A = _WIDGET + """
Ingénieur Automation / développement Beckhoff

Profil souhaité

Diplôme d'ingénieur en automation, mécatronique ou formation jugée équivalente
Bonnes connaissances des automates Beckhoff ou Fanuc
Expérience dans le développement software machine / automation industrielle
Connaissances en vision industrielle et/ou asservissement = un atout
Personne rigoureuse, structurée, autonome et orientée solutions
Capacité à travailler en petite équipe et en lien direct avec les clients

Nous offrons

Un cadre de travail stimulant.
Bonnes conditions sociales.
Responsabilités principales

Etudier, développer et optimiser des systèmes automatisés pour le pilotage de machines
Programmer les éléments d'automation sur environnements Beckhoff (ou Fanuc)
Participer aux phases de tests, validation, mise en service et mise au point
Assurer le support technique aux clients dans le cadre de développements spécifiques
Collaborer avec une petite équipe sur des projets techniques sur mesure
"""

BECKHOFF_B = _WIDGET + """Mandatés par un de nos clients, nous recherchons un/e :

Ingénieur Automation/développement Beckhoff

Diplôme d'ingénieur en automation, mécatronique ou formation jugée équivalente
Bonnes connaissances des automates Beckhoff ou Fanuc
Expérience dans le développement software machine / automation industrielle
Connaissances en vision industrielle et/ou asservissement = un atout
Personne rigoureuse, structurée, autonome et orientée solutions
Capacité à travailler en petite équipe et en lien direct avec les clients
Etudier, développer et optimiser des systèmes automatisés pour le pilotage de machines
Programmer les éléments d'automation sur environnements Beckhoff (ou Fanuc)
Participer aux phases de tests, validation, mise en service et mise au point
Assurer le support technique aux clients dans le cadre de développements spécifiques
Collaborer avec une petite équipe sur des projets techniques sur mesure
Les avantages:

Un cadre de travail stimulant
Bonnes conditions sociales
"""

# jobs.db #4592: another offer from the same agency, same town, same
# template — a genuinely different job.
DEV_LOGICIEL = _WIDGET + """
Ingénieur Développeur logiciel

Titulaire d'un diplôme d'ingénieur dans le domaine du développement logiciel.
Excellentes compétences en programmation C#.
La connaissance de la commande numérique Fanuc constitue un atout.
Personne autonome, rigoureuse et dotée d'un bon esprit d'analyse.
Capacité à travailler en équipe pluridisciplinaire.
Nous offrons

Un cadre de travail stimulant.
Bonnes conditions sociales.
Concevoir, développer et tester des applications logicielles pour le pilotage de machines et de systèmes automatisés.
Assurer l'adéquation aux cahiers des charges et garantir la qualité, la performance et la sécurité des solutions développées.
Maintenir les applications existantes, optimiser les performances et participer aux évolutions techniques.
"""


def offer(title: str, description: str | None = BECKHOFF_A, company: str | None = "OK Job SA",
          location: str | None = "La Chaux-de-Fonds") -> dict:
    return {"title": title, "company": company, "location": location, "description": description}


BECKHOFF = "Ingénieur Automation / développement Beckhoff"

SAME_OFFER_CASES = [
    ("republication reformulée (réel #4594/#4596)",
     offer(BECKHOFF), offer("Ingénieur Automation/développement Beckhoff", BECKHOFF_B), True),
    ("marqueur (H/F) ajouté à la republication",
     offer("Technicien Qualité"), offer("Technicien Qualité (H/F)"), True),
    ("entreprise illisible sur l'ancienne ligne (avant 9e5a3e6)",
     offer(BECKHOFF, company="Offre pertinente ?"), offer(BECKHOFF), True),
    ("entreprise absente d'un côté",
     offer(BECKHOFF, company=None), offer(BECKHOFF), True),
    # Real pair (Bellevue): two positions, 0.967 similar descriptions.
    ("Senior vs Principal : deux postes, même texte",
     offer("Senior Data and Applied Scientist"), offer("Principal Data and Applied Scientist"), False),
    ("titre précisé = autre poste (réel « Ingénieur qualité (TQ2) »)",
     offer("Ingénieur qualité"), offer("Ingénieur qualité (TQ2)"), False),
    ("même intitulé, autre lieu",
     offer(BECKHOFF), offer(BECKHOFF, location="Fleurier"), False),
    ("même intitulé, deux entreprises connues",
     offer(BECKHOFF), offer(BECKHOFF, company="Proman"), False),
    ("même intitulé, description d'un autre poste de l'agence",
     offer(BECKHOFF), offer(BECKHOFF, DEV_LOGICIEL), False),
    ("description manquante : pas de preuve, pas de fusion",
     offer(BECKHOFF, description=None), offer(BECKHOFF), False),
]

TITLE_CASES = [
    ("Business Analyst Atlassian (h/f/x) 80-100%", "business analyst atlassian 80 100"),
    ("Contrôleur qualité (H/F)", "controleur qualite"),
    ("Data Engineer (m/w/d)", "data engineer"),
    ("Business Analyst – Enterprise Data Management (EDM)", "business analyst enterprise data management edm"),
    ("ML/Data Infrastructure Engineer", "ml data infrastructure engineer"),
]


def _job(source_id: str, title: str = BECKHOFF, description: str = BECKHOFF_A) -> dict:
    return {
        "source": "jobup", "source_id": source_id, "url": f"https://www.jobup.ch/fr/emplois/detail/{source_id}/",
        "title": title, "company": "OK Job SA", "location": "La Chaux-de-Fonds", "contract_type": "Durée indéterminée",
        "salary": None, "experience": None, "description": description, "published_at": "25 septembre 2026",
    }


def _seed(conn, source_id: str, *, verdict: str | None = None, last_seen: str = "2026-09-20 11:00:00",
          company: str = "Offre pertinente ?", description: str = BECKHOFF_B) -> int:
    conn.execute(
        "INSERT INTO jobs (source, source_id, url, title, company, location, description, status, score, "
        "user_verdict, last_seen_at) VALUES ('jobup', ?, ?, ?, ?, 'La Chaux-de-Fonds', ?, 'analyse', 45, ?, ?)",
        (source_id, f"https://www.jobup.ch/fr/emplois/detail/{source_id}/", BECKHOFF, company, description,
         verdict, last_seen),
    )
    return conn.execute("SELECT id FROM jobs WHERE source_id = ?", (source_id,)).fetchone()[0]


def _rows(conn) -> list[tuple]:
    return conn.execute("SELECT id, source_id, status, score, user_verdict FROM jobs ORDER BY id").fetchall()


def scenario_republication(conn) -> list[str]:
    """Old UUID gone, new UUID found: the stored row follows the new UUID,
    no new 'nouveau' row, analysis and verdict kept."""
    row_id = _seed(conn, "old-uuid", verdict="interessante")
    counts = store_jobup_jobs(conn, [_job("new-uuid")])
    errors = []
    if counts != (0, 1, 0):
        errors.append(f"compteurs {counts}, attendu (0, 1, 0)")
    if _rows(conn) != [(row_id, "new-uuid", "analyse", 45, "interessante")]:
        errors.append(f"lignes {_rows(conn)}")
    company = conn.execute("SELECT company FROM jobs").fetchone()[0]
    if company != "OK Job SA":
        errors.append(f"champs scrapés non rafraîchis (company={company!r})")
    return errors


def scenario_live_alias(conn) -> list[str]:
    """Both UUIDs live in the same run, the new one listed first: the row
    keeps the UUID it already had, nothing inserted."""
    row_id = _seed(conn, "old-uuid")
    counts = store_jobup_jobs(conn, [_job("new-uuid"), _job("old-uuid", description=BECKHOFF_B)])
    errors = []
    if counts != (0, 0, 1):
        errors.append(f"compteurs {counts}, attendu (0, 0, 1)")
    if _rows(conn) != [(row_id, "old-uuid", "analyse", 45, None)]:
        errors.append(f"lignes {_rows(conn)}")
    return errors


def scenario_new_offer_twice(conn) -> list[str]:
    """A never-seen offer shows up under two UUIDs in one run: one row."""
    counts = store_jobup_jobs(conn, [_job("uuid-1"), _job("uuid-2", description=BECKHOFF_B)])
    errors = []
    if counts != (1, 0, 1):
        errors.append(f"compteurs {counts}, attendu (1, 0, 1)")
    if [r[1:3] for r in _rows(conn)] != [("uuid-1", "nouveau")]:
        errors.append(f"lignes {_rows(conn)}")
    return errors


def scenario_distinct_openings(conn) -> list[str]:
    """Different jobs from the same agency and town are all stored."""
    _seed(conn, "old-uuid")
    counts = store_jobup_jobs(conn, [
        _job("uuid-dev", title="Ingénieur Développeur logiciel", description=DEV_LOGICIEL),
        _job("uuid-principal", title="Principal " + BECKHOFF),
    ])
    errors = []
    if counts != (2, 0, 0):
        errors.append(f"compteurs {counts}, attendu (2, 0, 0)")
    if len(_rows(conn)) != 3:
        errors.append(f"lignes {_rows(conn)}")
    return errors


def scenario_existing_duplicates(conn) -> list[str]:
    """Several stored duplicates (from before the fix): the row the user
    triaged is the one kept alive, even if another was seen more recently."""
    _seed(conn, "dup-recent", last_seen="2026-09-25 11:00:00")
    triaged = _seed(conn, "dup-triaged", verdict="peut_etre", last_seen="2026-09-19 11:00:00")
    counts = store_jobup_jobs(conn, [_job("new-uuid")])
    errors = []
    if counts != (0, 1, 0):
        errors.append(f"compteurs {counts}, attendu (0, 1, 0)")
    new_owner = conn.execute("SELECT id FROM jobs WHERE source_id = 'new-uuid'").fetchone()
    if new_owner != (triaged,):
        errors.append(f"re-pointée sur {new_owner}, attendu ({triaged},)")
    return errors


SCENARIOS = [scenario_republication, scenario_live_alias, scenario_new_offer_twice,
             scenario_distinct_openings, scenario_existing_duplicates]


def main() -> None:
    failures = 0
    total = 0

    for raw, expected in TITLE_CASES:
        got = normalize_title(raw)
        ok = got == expected
        total += 1
        failures += not ok
        print(f"[{'OK' if ok else 'FAIL'}] titre {raw!r:55} -> {got!r}" + ("" if ok else f"  (attendu {expected!r})"))

    for label, a, b, expected in SAME_OFFER_CASES:
        got = is_same_offer(a, b)
        ok = got == expected and is_same_offer(b, a) == expected
        total += 1
        failures += not ok
        sim = description_similarity(a["description"], b["description"]) if a["description"] and b["description"] else None
        sim_text = f"{sim:.3f}" if sim is not None else "  - "
        print(f"[{'OK' if ok else 'FAIL'}] {label:58} sim={sim_text} -> {got}" + ("" if ok else f"  (attendu {expected})"))

    for scenario in SCENARIOS:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "jobs.db"
            init_db(db_path)
            with connect(db_path) as conn:
                errors = scenario(conn)
        total += 1
        failures += bool(errors)
        print(f"[{'OK' if not errors else 'FAIL'}] {scenario.__name__}" + "".join(f"\n       {e}" for e in errors))

    print(f"\n{total - failures}/{total} cas passés")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
