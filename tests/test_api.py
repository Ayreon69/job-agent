"""Tests for the API's two views of the data (api/main.py): the public one
(offers, scores, counts) and the owner's (verdicts, analyses), on a
throwaway schema (db_fixture.py) with FastAPI's in-process TestClient.

API_MODE=readonly: the embedding model is never loaded, as on the deployed
dashboard. Not pytest: standalone script like the other tests.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db_fixture import temp_database
from storage.db import Job, connect, save_analysis, upsert_job

TOKEN = "jeton-de-test"
OWNER = {"Authorization": f"Bearer {TOKEN}"}


def check(label: str, got, expected) -> int:
    ok = got == expected
    print(f"[{'OK' if ok else 'FAIL'}] {label}: {got!r}" + ("" if ok else f"  (attendu {expected!r})"))
    return 0 if ok else 1


def _seed(dsn: str) -> int:
    with connect(dsn) as conn:
        upsert_job(conn, Job(source="jobup", source_id="uuid-1", url="https://example.test/1", title="Data Scientist",
                             location="Genève", description="Texte de l'offre"))
        job_id = conn.execute("SELECT id FROM jobs").fetchone()[0]
        conn.execute("UPDATE jobs SET status = 'analyse', score = 77, gaps_count = 1 WHERE id = %s", (job_id,))
        save_analysis(conn, job_id, matches=[{"skill": "SQL", "matched_chunk_summary": "ECA"}],
                      gaps=[{"skill": "Spark", "note": "absent du profil"}], uncertain_flags=[],
                      analysis_markdown="## Résumé du matching", orchestrator_trace={"decisions": []},
                      scoring_trace=None, generation_trace=None)
    return job_id


def main() -> None:
    failures = 0
    with temp_database() as dsn:
        os.environ.update(DATABASE_URL=dsn, OWNER_TOKEN=TOKEN, API_MODE="readonly")
        from fastapi.testclient import TestClient

        from api.main import app

        job_id = _seed(dsn)
        with TestClient(app) as client:
            listing = client.get("/offers").json()
            failures += check("liste : score et date ISO UTC", (listing[0]["score"], listing[0]["first_seen_at"][-1]), (77, "Z"))

            public = client.get(f"/offers/{job_id}").json()
            failures += check("détail public : compteurs oui, analyse non",
                              (public["gaps_count"], public["gaps"], public["analysis_markdown"], public["description"]),
                              (1, [], None, "Texte de l'offre"))
            wrong = client.get(f"/offers/{job_id}", headers={"Authorization": "Bearer mauvais"}).json()
            failures += check("détail avec un mauvais jeton : vue publique", wrong["gaps"], [])

            owned = client.get(f"/offers/{job_id}", headers=OWNER)
            failures += check("détail propriétaire : écarts et analyse rédigée",
                              (owned.json()["gaps"][0]["skill"], owned.json()["analysis_markdown"]), ("Spark", "## Résumé du matching"))
            failures += check("détail propriétaire : jamais en cache partagé", owned.headers.get("cache-control"), "private, no-store")

            failures += check("GET /owner sans jeton", client.get("/owner").json(), {"owner": False})
            failures += check("GET /owner avec le jeton", client.get("/owner", headers=OWNER).json(), {"owner": True})

            verdict = {"verdict": "interessante"}
            failures += check("verdict sans jeton : 401", client.post(f"/offers/{job_id}/verdict", json=verdict).status_code, 401)
            failures += check("verdict avec le jeton : 200", client.post(f"/offers/{job_id}/verdict", json=verdict, headers=OWNER).status_code, 200)
            with connect(dsn) as conn:
                stored = conn.execute("SELECT user_verdict FROM jobs WHERE id = %s", (job_id,)).fetchone()[0]
            failures += check("verdict enregistré en base", stored, "interessante")
            failures += check("verdict invalide : 422",
                              client.post(f"/offers/{job_id}/verdict", json={"verdict": "bof"}, headers=OWNER).status_code, 422)
            failures += check("verdict sur une offre inconnue : 404",
                              client.post("/offers/999999/verdict", json=verdict, headers=OWNER).status_code, 404)

            failures += check("/analyze sans jeton : 401", client.post("/analyze", json={"offer_id": job_id}).status_code, 401)
            failures += check("/analyze en lecture seule, même propriétaire : 503",
                              client.post("/analyze", json={"offer_id": job_id}, headers=OWNER).status_code, 503)

            failures += check("santé : base accessible", client.get("/health").json()["checks"]["database_accessible"], True)

            os.environ["OWNER_TOKEN"] = ""
            failures += check("aucun OWNER_TOKEN configuré : personne n'est propriétaire",
                              client.post(f"/offers/{job_id}/verdict", json=verdict, headers={"Authorization": "Bearer "}).status_code, 401)

    total = 16
    print(f"\n{total - failures}/{total} cas passés")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
