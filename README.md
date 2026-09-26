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
```

1. **Collecte** (`scraper/`) : Playwright sur Hellowork et jobup.ch, stockage SQLite
   avec dédoublonnage par `(source, source_id)`.
2. **Géographie** (`scoring/geography.py`) : chaque offre reçoit une zone et une
   priorité par règles déterministes, avant tout appel LLM. Une zone inconnue ne
   bloque rien mais marque l'offre « à valider ».
3. **Scoring** (`scoring/`) : récupération des passages pertinents du profil dans
   ChromaDB (embeddings `sentence-transformers`), puis score et justification par
   Mistral. Le seuil de bruit du retrieval est recalculé à chaque construction de
   l'index au lieu d'être fixé à la main.
4. **Analyse** (`generation/`) : analyse de candidature en markdown, avec les écarts
   de compétences signalés explicitement plutôt que masqués.
5. **Orchestration** (`orchestrator/`) : l'orchestrateur décide au lieu d'enchaîner
   aveuglément. Il relance un scraping ciblé si la description est trop maigre,
   isole les échecs offre par offre, et trace chacune de ses décisions.
6. **API et dashboard** (`api/`) : FastAPI, `GET /offers`, `GET /offers/{id}`,
   `GET /health`, et `POST /analyze` en mode complet. Le dashboard (modules ES,
   sans build) propose un brief du jour, la liste filtrable, un tri façon swipe,
   un tableau de sélection exportable et une page « coulisses » qui explique le
   pipeline avec ses vrais chiffres.

## Exécution

- **Batch quotidien** : GitHub Actions (`.github/workflows/scrape-and-score.yml`)
  scrape, score et analyse les nouvelles offres, puis recommite `storage/jobs.db`.
- **Démo** : Render sert le dashboard en `API_MODE=readonly`. Le modèle d'embeddings
  n'est pas chargé, ce qui fait passer la mémoire d'environ 800 Mo à 58 Mo et tient
  dans l'offre gratuite.

## Lancer en local

```bash
cp .env.example .env        # renseigner MISTRAL_API_KEY
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

Tests : `python tests/test_geography.py`, `python tests/test_generation.py`,
`python tests/test_llm_retry.py`.

## Stack

Python 3.11 · Playwright · SQLite · ChromaDB · sentence-transformers · API Mistral ·
FastAPI · Docker · GitHub Actions · Render
