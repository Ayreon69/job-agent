# Job Agent

Pipeline multi-agents qui collecte des offres d'emploi, les score contre un profil
indexé et rédige une analyse de candidature pour chacune. **Il ne soumet jamais
de candidature** : il s'arrête à l'analyse, la décision reste humaine.

**Démo (lecture seule) :** https://job-agent-otyo.onrender.com/
— instance gratuite mise en veille, le premier chargement prend environ une minute.

Étude de cas complète : [rayan-jemai-portfolio.vercel.app/laboratoire/job-agent](https://rayan-jemai-portfolio.vercel.app/laboratoire/job-agent)

## Ce que fait le pipeline

```
scraping ──> géographie ──> scoring (RAG + LLM) ──> analyse rédigée ──> dashboard
Hellowork     zone et        profil indexé dans     markdown structuré    FastAPI
jobup.ch      priorité       ChromaDB, Mistral      gaps signalés         tri manuel
LinkedIn
```

1. **Collecte** (`scraper/`) : Playwright sur Hellowork (Rhône-Alpes) et jobup.ch
   (Suisse romande), requêtes HTTP sur la recherche publique de LinkedIn, sans
   compte (Suisse romande et Émirats). Stockage Postgres (Neon) avec
   dédoublonnage par `(source, source_id)`, republications jobup reconnues, et
   une offre publiée sur deux sites gardée une seule fois.
2. **Géographie** (`scoring/geography.py`) : chaque offre reçoit une zone et une
   priorité par règles déterministes, avant tout appel LLM. Une zone inconnue ne
   bloque rien mais marque l'offre « à valider ».
3. **Scoring** (`scoring/`) : récupération des passages pertinents du profil dans
   ChromaDB (embeddings `sentence-transformers`), puis score et justification par
   Mistral. Le seuil de bruit du retrieval est recalculé à chaque construction de
   l'index au lieu d'être fixé à la main.
4. **Analyse** (`generation/`) : analyse de candidature en markdown, avec les écarts
   de compétences signalés explicitement plutôt que masqués. Stockée en base avec
   les traces des agents, visible du seul propriétaire.
5. **Orchestration** (`orchestrator/`) : l'orchestrateur décide au lieu d'enchaîner
   aveuglément. Il relance un scraping ciblé si la description est trop maigre,
   isole les échecs offre par offre, et trace chacune de ses décisions.
6. **API et dashboard** (`api/`) : FastAPI, `GET /offers`, `GET /offers/{id}`,
   `GET /health`, et `POST /analyze` en mode complet. Un jeton propriétaire
   (`OWNER_TOKEN`) débloque le tri et les analyses détaillées ; sans lui, la vue
   est publique et en lecture seule. Le dashboard (modules ES,
   sans build) propose un brief du jour, la liste filtrable, un tri façon swipe,
   un tableau de sélection exportable et une page « coulisses » qui explique le
   pipeline avec ses vrais chiffres.

## Exécution

- **Batch quotidien** : GitHub Actions (`.github/workflows/scrape-and-score.yml`)
  scrape, score et analyse les nouvelles offres, et écrit chacune dans Postgres
  dès qu'elle est traitée.
- **Démo** : Render sert le dashboard en `API_MODE=readonly`. Le modèle d'embeddings
  n'est pas chargé, ce qui fait passer la mémoire d'environ 800 Mo à 58 Mo et tient
  dans l'offre gratuite.

## Lancer en local

```bash
cp .env.example .env        # renseigner MISTRAL_API_KEY, DATABASE_URL, OWNER_TOKEN
docker compose up --build   # API et dashboard sur http://localhost:8000
```

Sans Docker (Python 3.11) :

```bash
pip install -r requirements.txt
python -m playwright install chromium
python -m scoring.embeddings.build   # index du profil
python -m scraper.run                # collecte
python -m orchestrator.run           # scoring et analyse des nouvelles offres
```

Tests : `python tests/test_storage.py`, `python tests/test_api.py`,
`python tests/test_jobup_dedup.py`, `python tests/test_cross_source.py`,
`python tests/test_geography.py`, `python tests/test_jobup_parsing.py`,
`python tests/test_linkedin_parsing.py`, `python tests/test_llm_retry.py`.
Ceux qui ont besoin d'une base créent un schéma Postgres jetable, sur
`TEST_DATABASE_URL` ou sur un Postgres embarqué (`pip install pgserver`).
`tests/test_generation.py` appelle le vrai Mistral.

## Stack

Python 3.11 · Playwright · Postgres (Neon) · ChromaDB · sentence-transformers · API Mistral ·
FastAPI · Docker · GitHub Actions · Render
