# ROADMAP — job-agent

Suivi de session à session. Voir CLAUDE.md pour le contexte projet complet.

## Étapes

1. **Scraper + stockage SQLite (Hellowork)** — ✅ terminé (2026-07-10)
2. Indexation profil utilisateur dans ChromaDB — à faire
3. Scoring d'une offre via agent (score + justification) — à faire
4. Génération d'analyse de candidature (markdown structuré) — à faire
5. Wrapper FastAPI (endpoint `/analyze`) — à faire
6. Dockerisation — à faire
7. GitHub Actions (scraping programmé) — à faire

## Session 1 (2026-07-10) — Scraper Hellowork + SQLite

**Livré :**
- `storage/db.py` — schéma SQLite (table `jobs`, contrainte unique `(source, source_id)`
  pour éviter les doublons au re-scraping), helpers `init_db` / `upsert_job` / `connect`.
- `scraper/hellowork.py` — scraping Playwright en deux passes :
  1. page de résultats de recherche (`[data-cy="serpCard"]`) → titre, entreprise,
     lieu, type de contrat, URL
  2. page de détail de chaque offre → description complète, salaire, expérience,
     date de publication
- `scraper/run.py` — point d'entrée CLI : `python -m scraper.run [--query ... --pages N --headed]`.
  Sans argument, tourne sur un set de requêtes par défaut alignées avec le profil
  data/IA du CLAUDE.md.
- `requirements.txt` (playwright).

**Test réel effectué :** `python -m scraper.run --query "data scientist" --pages 1`
→ 30 offres réelles scrapées et insérées, 0 description manquante après correction
du sélecteur (voir note technique ci-dessous).

**Note technique — fragilité des sélecteurs Hellowork :**
Le heading introduisant la description varie selon les offres : "Détail du poste",
"Les missions du poste", "Description du poste", "Le poste". Le scraper essaie ces
variantes dans l'ordre et prend la première trouvée. Si Hellowork change son DOM,
c'est le premier endroit à vérifier (`fetch_job_detail` dans `scraper/hellowork.py`).

**Limites connues à traiter en session suivante ou plus tard :**
- Pas de gestion de pagination au-delà d'une page par requête par défaut (`--pages`
  disponible mais pas testé à grande échelle).
- Pas de retry/backoff sur échec réseau individuel (une offre en échec est juste
  loggée et sautée, cf. `scraper/run.py`).
- Pas encore de filtrage géographique appliqué au scraping lui-même (les règles de
  ciblage géo du CLAUDE.md s'appliqueront à l'étape scoring, pas ici).
