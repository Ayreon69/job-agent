# CLAUDE.md — Job Agent

## Contexte du projet

Agent de recherche d'emploi automatisé, construit comme projet d'apprentissage pratique
sur RAG et architecture agentique (agents LLM, embeddings, orchestration), tout en servant
un objectif réel : accélérer et fiabiliser la recherche d'emploi de l'utilisateur.

Double objectif assumé :
1. Outil fonctionnel qui scrape, score et prépare des candidatures pertinentes
2. Vecteur d'apprentissage : chaque étape doit être comprise, pas juste fonctionnelle.
   Expliquer les choix techniques (chunking, embeddings, seuils de similarité,
   orchestration d'agent) à chaque étape clé plutôt que de livrer du code opaque qui marche.

## Profil utilisateur (contexte métier, à ne jamais réinventer)

- Data Analyst / Data Scientist, 3,5+ ans chez ECA Assurances (Lyon)
- Master Économétrie & Statistiques (Data Analytics & Risk Management), ISFA Lyon 1
- Compétences clés : SQL, Python, Power BI, Snowflake, ML (churn recall 85%),
  prototypage LLM (Mistral API), agentic coding (Claude Code, MCP servers)
- Citoyenneté française uniquement — visa de travail nécessaire pour le Moyen-Orient
- Préavis : 3 mois

## Règles de scoring et de ciblage (critiques — ne jamais s'en écarter)

Priorités géographiques dans cet ordre :
1. Suisse francophone (Genève/Neuchâtel/Yverdon)
2. Émirats Arabes Unis (priorité absolue)
3. Autres pays du Moyen-Orient
4. Lyon (repli, pragmatique)

**Règle de séparation stricte par géographie :**
- Offres Lyon/France : ZÉRO signal de mobilité internationale dans l'analyse générée.
  Ne jamais mentionner le projet de relocalisation dans ce contexte.
- Offres Suisse : mobilité personnelle du couple mentionnable.
- Offres UAE/Moyen-Orient : ouverture à la relocalisation explicite, pas de framing
  avantages spécifiques français.

Ouvert à tous les rôles data science / data analyse / ingénierie IA. Priorité actuelle :
rôles orientés IA appliquée (agents, LLM, RAG) plutôt que reporting classique, mais
sans exclure les postes data "classiques" traités comme plan de sécurité.

## Honnêteté — règle non négociable

- Jamais de fabrication ou d'exagération de compétences dans les analyses générées.
- Si un gap de compétence existe (ex: gouvernance formelle des données, Monte Carlo,
  CI/CD avancé), le signaler explicitement dans l'analyse plutôt que de le masquer.
- Le scoring d'une offre doit refléter un jugement honnête, pas une optimisation
  cosmétique du score. Le but est d'aider à la décision, pas de gonfler artificiellement
  la pertinence d'une offre.

## Stack technique

| Composant | Techno | Statut |
|---|---|---|
| Scraping | Playwright | déjà maîtrisé |
| Stockage | SQLite (puis Postgres si besoin de scaler) | déjà maîtrisé (SQL) |
| Embeddings / retrieval | ChromaDB | nouveau — objectif d'apprentissage |
| LLM | API Mistral ou Claude | déjà maîtrisé |
| Orchestration agent | function calling + boucle simple, pas de framework lourd (pas de LangChain au départ) | nouveau |
| API | FastAPI | nouveau |
| Packaging | Docker | nouveau |
| CI/CD | GitHub Actions | nouveau |

Pas de RAG "full-context" façon chatbot Mistral existant : ici le RAG est délibérément
implémenté avec vraie indexation vectorielle, c'est tout l'intérêt pédagogique du projet.

## Structure du repo

```
job-agent/
├── CLAUDE.md
├── ROADMAP.md
├── scraper/
├── storage/
├── scoring/
│   ├── embeddings/
│   └── profile/         # CV + critères indexés (source de vérité du profil)
├── generation/
├── api/
├── tests/
├── docker/
└── .github/workflows/
```

## Conventions de code

- Python 3.11+, typage explicite (type hints) partout
- Un module = une responsabilité claire (scraping / scoring / génération / API séparés)
- Gestion d'erreurs explicite (pas de try/except silencieux), logs clairs à chaque étape
  du pipeline agentique pour pouvoir déboguer le raisonnement de l'agent
- Tests unitaires minimum sur : parsing scraping, scoring, génération — avant de passer
  à la session suivante
- Commits atomiques, un par fonctionnalité livrée et testée

## Méthode de travail (sessions)

Le projet avance par sessions courtes avec un livrable testable à chaque fois. Ne pas
générer plusieurs couches d'un coup sans validation intermédiaire. Ordre prévu :

1. Scraper + stockage SQLite (offres réelles Hellowork, Linkedin)
2. Indexation profil utilisateur dans ChromaDB
3. Scoring d'une offre via agent (score + justification)
4. Génération d'analyse de candidature (format markdown structuré)
5. Wrapper FastAPI (endpoint `/analyze`)
6. Dockerisation
7. GitHub Actions (scraping programmé)

Avant de passer à l'étape suivante : le livrable de l'étape en cours doit être testé et
fonctionnel. Mettre à jour ROADMAP.md à la fin de chaque session pour garder le fil
d'une session Claude Code à l'autre.

## Ce que l'agent ne doit jamais faire

- Ne jamais soumettre automatiquement une candidature sans validation humaine explicite
- Ne jamais mélanger les règles de ciblage géographique (voir section scoring ci-dessus)
- Ne jamais fabriquer de contenu factuel non présent dans le profil source