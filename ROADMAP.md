# ROADMAP — job-agent

Suivi de session à session. Voir CLAUDE.md pour le contexte projet complet.

## Étapes

1. **Scraper + stockage SQLite (Hellowork)** — ✅ terminé (2026-07-10)
2. **Indexation profil utilisateur dans ChromaDB** — ✅ terminé (2026-07-10)
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

**Correctif post-session (2026-07-10) — filtrage géographique :**
Hellowork ne référence que des offres France (pas de Suisse/UAE/Moyen-Orient) : les
priorités géo hautes du CLAUDE.md (Suisse romande, UAE) devront venir d'autres
sources à scraper plus tard. En attendant, le scraping était non filtré côté requête
(résultats dispersés dans toute la France/Belgique/Luxembourg). Corrigé en ajoutant
le paramètre de localisation Hellowork (`l=`) : `scraper/hellowork.py` accepte
maintenant un paramètre `location`, et `scraper/run.py` cible par défaut
`Rhône-Alpes` (élargi de Lyon pour couvrir aussi Grenoble, Annecy, Saint-Étienne...).
Testé : `python -m scraper.run --query "data analyst" --pages 1` → 30 offres, toutes
en 69/38/74/01 (+ Clermont-Ferrand en marge de région). Le paramètre de rayon
Hellowork (`ray=`) n'a pas d'effet observé en `d=all` ; c'est bien `l=<région>` qui
fait le filtrage.

**Correctif post-session (2026-07-10) — exclusion Alternance/Stage :**
Le scraping remontait aussi des offres Alternance et Stage, non pertinentes pour un
profil 3,5+ ans d'XP en poste. Hellowork filtre le type de contrat via des paramètres
`c=` répétés dans l'URL (ex: `c=CDI&c=CDD&c=Freelance...`) plutôt qu'une liste
séparée par virgules. `scraper/hellowork.py` envoie désormais tous les types de
contrat sauf Alternance/Stage/Stage de lycée (`CONTRACT_TYPES` dans
`scraper/hellowork.py`, personnalisable via le paramètre `contract_types`). Testé :
30 offres scrapées, aucune Alternance/Stage dans les résultats.

## Session 2 (2026-07-10) — Indexation du profil dans ChromaDB

**Livré :**
- `scoring/embeddings/parser.py` — parse les fichiers `scoring/profile/*.md` en
  chunks : découpage sur les headers `## chunk: nom`, extraction de la ligne
  `Tags: ...` en liste, le reste devient le texte du chunk. Un chunk = un id
  `nom_fichier::nom_chunk`.
- `scoring/embeddings/index.py` — construit la collection ChromaDB (`build_index`)
  et expose `search_profile(query, n_results=3)` pour la recherche par similarité.
  Client ChromaDB persistant sur disque (`scoring/embeddings/chroma/`, gitignored).
  Embeddings générés localement via la fonction par défaut de ChromaDB
  (sentence-transformers `all-MiniLM-L6-v2`, téléchargé au premier lancement,
  ~80 Mo, pas de clé API ni coût).
- `scoring/embeddings/build.py` — point d'entrée CLI : `python -m scoring.embeddings.build`.

**Test réel effectué :** 30 chunks indexés depuis les 4 fichiers profil
(achievements.md, skills.md, constraints.md, geography_rules.md). Recherche testée
sur 4 requêtes représentatives des cas d'usage scoring :
- "RAG et agents LLM" → remonte `rule_role_priority_current` et
  `skills_intermediaires_llm`
- "Poste à Dubai, relocalisation" → remonte `priority_order` et
  `rule_uae_middle_east`
- "Poste à Lyon reporting" → remonte `power_bi_dashboards` et
  `rule_lyon_no_mobility`
- "Gouvernance des données" (gap connu) → remonte `skills_notions_seulement`,
  cohérent avec la règle d'honnêteté du CLAUDE.md (pas de faux positif de
  compétence maîtrisée)

**Décision technique :** embeddings locaux plutôt que via l'API Mistral, pour rester
gratuit/offline sur cette étape d'apprentissage RAG.

**Limites connues :**
- `build_index` supprime et recrée la collection à chaque exécution (pas d'update
  incrémental) — acceptable vu la taille du profil (30 chunks), à revoir si le
  profil grossit significativement.

**Correctif post-session (2026-07-10) — retrieval réaliste et changement de modèle
d'embedding :**
Les 4 requêtes de test initiales étaient trop faciles (vocabulaire proche des chunks
eux-mêmes). Un test plus sérieux avec le modèle par défaut (`all-MiniLM-L6-v2`,
anglais) sur des extraits bruts de vraies offres scrapées a montré des résultats
médiocres, et surtout aucune séparation nette entre un vrai match et du bruit total
(ex: une requête "recette de tarte aux pommes" obtenait un score de distance
similaire aux vraies requêtes de scoring). Diagnostic : modèle faible en français,
mal adapté au texte RH bruité.

Remplacé par `paraphrase-multilingual-mpnet-base-v2` via
`SentenceTransformerEmbeddingFunction` (nécessite `sentence-transformers` + `torch`,
ajoutés à requirements.txt). Résultat sur les mêmes tests : nette séparation
d'échelle entre vraies requêtes (distance ~0.33-0.65) et bruit total (~0.85), ce qui
donne un seuil exploitable pour la session 3 (ex: flag_uncertain si la meilleure
distance dépasse ~0.7-0.75).

**Limite non résolue par le changement de modèle — ambiguïté géographique fine :**
Sur une requête piège "poste basé à Zurich, environnement suisse-allemand",
`rule_switzerland_mobility` (qui ne s'applique qu'à la Suisse **romande**) remonte
quand même en 2e position, à un score très proche de la bonne réponse
(`rule_lyon_no_mobility`). Le RAG sémantique capte "Suisse" mais pas la distinction
romande/alémanique — c'est une limite structurelle de la similarité par embedding
sur ce type de nuance géographique précise, pas un problème de modèle. À traiter
explicitement dans l'agent de scoring (session 3) : vérifier la ville/canton par une
règle simple avant d'appliquer `rule_switzerland_mobility`, ne pas se fier uniquement
au retrieval sémantique pour cette distinction.
