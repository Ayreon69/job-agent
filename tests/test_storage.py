"""Tests for the Postgres store (storage/db.py), the stale-offer query
(storage/cleanup.py) and the one-off SQLite import
(storage/migrate_from_sqlite.py), each on a throwaway schema (db_fixture.py).

Not pytest: standalone script like the other tests, run directly.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg

from db_fixture import temp_database
from storage.cleanup import find_stale_offers
from storage.db import (
    Job, connect, mark_seen, save_analysis, set_job_status, set_scoring_summary, set_user_verdict, upsert_job,
)
from storage.migrate_from_sqlite import import_offers, read_sqlite

OLD = "2026-01-01 08:00:00+00"


def check(label: str, got, expected) -> int:
    ok = got == expected
    print(f"[{'OK' if ok else 'FAIL'}] {label}: {got!r}" + ("" if ok else f"  (attendu {expected!r})"))
    return 0 if ok else 1


def _job(**overrides) -> Job:
    fields = {"source": "jobup", "source_id": "uuid-1", "url": "https://example.test/1", "title": "Data Scientist",
              "company": "Acme", "location": "Genève", "description": "Texte v1", "published_at": "20 octobre 2026"}
    return Job(**{**fields, **overrides})


def _analysis(conn, job_id: int, markdown: str) -> None:
    save_analysis(
        conn, job_id, matches=[{"skill": "SQL", "matched_chunk_summary": "ECA"}], gaps=[{"skill": "Spark", "note": "absent"}],
        uncertain_flags=["Airflow"], analysis_markdown=markdown, orchestrator_trace={"decisions": ["ok"]},
        scoring_trace={"rag_queries": []}, generation_trace=None,
    )


def upsert_cases() -> int:
    failures = 0
    with temp_database() as dsn, connect(dsn) as conn:
        failures += check("upsert : nouvelle offre insérée", upsert_job(conn, _job()), True)
        job_id = conn.execute("SELECT id FROM jobs").fetchone()[0]
        set_job_status(conn, job_id, "analyse")
        set_user_verdict(conn, job_id, "interessante")
        set_scoring_summary(conn, job_id, score=81, geography_zone="suisse_romande", sector="Assurance", gaps_count=1, uncertain_count=1)
        conn.execute("UPDATE jobs SET last_seen_at = %s, scraped_at = %s", (OLD, OLD))

        failures += check("upsert : offre connue rafraîchie, pas réinsérée", upsert_job(conn, _job(description="Texte v2")), False)
        row = conn.execute(
            "SELECT description, status, user_verdict, score, scraped_at = %s, last_seen_at > %s FROM jobs", (OLD, OLD)
        ).fetchone()
        failures += check("rafraîchissement : description à jour, statut/verdict/score/1re vue intacts, vue maintenant",
                          row, ("Texte v2", "analyse", "interessante", 81, True, True))

        upsert_job(conn, _job(source_id="uuid-2"))
        conn.execute("UPDATE jobs SET last_seen_at = %s", (OLD,))
        mark_seen(conn, [job_id])
        seen = conn.execute("SELECT source_id, last_seen_at > %s FROM jobs ORDER BY id", (OLD,)).fetchall()
        failures += check("mark_seen : seulement les offres listées", seen, [("uuid-1", True), ("uuid-2", False)])

        try:
            with conn.transaction():
                conn.execute("UPDATE jobs SET status = 'bof'")
            failures += check("statut hors liste refusé par la base", "accepté", "CheckViolation")
        except psycopg.errors.CheckViolation:
            failures += check("statut hors liste refusé par la base", "CheckViolation", "CheckViolation")
    return failures


def analysis_cases() -> int:
    failures = 0
    with temp_database() as dsn, connect(dsn) as conn:
        upsert_job(conn, _job())
        job_id = conn.execute("SELECT id FROM jobs").fetchone()[0]
        _analysis(conn, job_id, "v1")
        _analysis(conn, job_id, "v2")
        row = conn.execute("SELECT count(*), max(analysis_markdown), max(gaps::text) FROM analyses").fetchone()
        failures += check("analyse : la dernière remplace la précédente", row, (1, "v2", '[{"note": "absent", "skill": "Spark"}]'))
        loaded = conn.execute("SELECT matches, generation_trace FROM analyses").fetchone()
        failures += check("analyse : jsonb relu en objets Python, NULL conservé",
                          loaded, ([{"skill": "SQL", "matched_chunk_summary": "ECA"}], None))
        conn.execute("DELETE FROM jobs WHERE id = %s", (job_id,))
        failures += check("analyse supprimée avec son offre (cascade)", conn.execute("SELECT count(*) FROM analyses").fetchone()[0], 0)
    return failures


def cleanup_cases() -> int:
    with temp_database() as dsn, connect(dsn) as conn:
        for source_id, last_seen in (("vieille", "2026-08-01 10:00:00+00"), ("recente", "2026-10-20 10:00:00+00"), ("inconnue", None)):
            upsert_job(conn, _job(source_id=source_id, title=source_id))
            conn.execute("UPDATE jobs SET last_seen_at = %s WHERE source_id = %s", (last_seen, source_id))
        stale = find_stale_offers(conn, datetime(2026, 9, 21, tzinfo=timezone.utc))
    return check("nettoyage : seule la vieille offre, jamais celle sans last_seen_at",
                 [(o["title"], o["last_seen_at"]) for o in stale], [("vieille", "2026-08-01")])


def migration_cases() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        sqlite_path = Path(tmp) / "jobs.db"
        lite = sqlite3.connect(sqlite_path)
        # The SQLite schema as it stood at the end of session 19.
        lite.executescript("""
            CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, source_id TEXT NOT NULL,
                url TEXT NOT NULL, title TEXT NOT NULL, company TEXT, location TEXT, contract_type TEXT, salary TEXT,
                experience TEXT, description TEXT, published_at TEXT, scraped_at TEXT NOT NULL DEFAULT (datetime('now')),
                status TEXT NOT NULL DEFAULT 'nouveau', user_verdict TEXT, last_seen_at TEXT, score INTEGER,
                geography_zone TEXT, sector TEXT, gaps_count INTEGER, uncertain_count INTEGER, UNIQUE(source, source_id));
            INSERT INTO jobs (id, source, source_id, url, title, scraped_at, status, user_verdict, last_seen_at, score)
                VALUES (7, 'hellowork', 'a', 'https://x/a', 'Analyste', '2026-07-10 08:30:00', 'analyse', 'peut_etre', '2026-10-21 11:58:36', 64);
            INSERT INTO jobs (id, source, source_id, url, title, scraped_at, status, last_seen_at)
                VALUES (5390, 'linkedin', 'b', 'https://x/b', 'AI Engineer', '2026-10-21 11:58:36', 'echec', NULL);
        """)
        lite.commit()
        lite.close()
        offers = read_sqlite(sqlite_path)

        with temp_database() as dsn:
            with connect(dsn) as conn:
                import_offers(conn, offers, replace=False)
                rows = conn.execute("SELECT id, user_verdict, score, scraped_at, last_seen_at FROM jobs ORDER BY id").fetchall()
                failures += check("migration : ids, verdict, score et horodatages UTC conservés", rows, [
                    (7, "peut_etre", 64, datetime(2026, 7, 10, 8, 30, tzinfo=timezone.utc), datetime(2026, 10, 21, 11, 58, 36, tzinfo=timezone.utc)),
                    (5390, None, None, datetime(2026, 10, 21, 11, 58, 36, tzinfo=timezone.utc), None),
                ])
                upsert_job(conn, _job())
                failures += check("migration : la prochaine offre prend l'id suivant le plus grand",
                                  conn.execute("SELECT max(id) FROM jobs").fetchone()[0], 5391)
            with connect(dsn) as conn:
                try:
                    import_offers(conn, offers, replace=False)
                    refused = False
                except RuntimeError:
                    refused = True
                failures += check("migration : refusée sur une base non vide sans --replace", refused, True)
            with connect(dsn) as conn:
                import_offers(conn, offers, replace=True)
                failures += check("migration --replace : base remplacée", conn.execute("SELECT count(*) FROM jobs").fetchone()[0], 2)
    return failures


def main() -> None:
    failures = upsert_cases() + analysis_cases() + cleanup_cases() + migration_cases()
    total = 4 + 3 + 1 + 4
    print(f"\n{total - failures}/{total} cas passés")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
