# ROADMAP — job-agent

Suivi de session à session. Voir CLAUDE.md pour le contexte projet complet.

## Étapes

1. **Scraper + stockage SQLite (Hellowork)** — ✅ terminé (2026-07-10)
2. **Indexation profil utilisateur dans ChromaDB** — ✅ terminé (2026-07-10)
3. **Scoring d'une offre via agent (score + justification)** — ✅ terminé (2026-07-11)
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

**Retest (2026-07-11) après mise à jour de geography_rules.md :** un nouveau chunk
dédié `rule_switzerland_german_italian` a été ajouté, énonçant explicitement que
Zurich/Bâle/Berne/Tessin ne sont PAS la Suisse romande et sont en dernière priorité
géographique. Réindexation (31 chunks) et re-test sur la même requête piège Zurich :

```
0.3590  rule_switzerland_mobility        (romande — toujours 1er, à tort)
0.3899  rule_switzerland_german_italian  (désambiguïsation — 2e, dans le top 3)
0.3954  priority_order
0.4281  rule_lyon_no_mobility
```

Amélioration réelle mais partielle : `rule_switzerland_mobility` reste en tête
(distance légèrement meilleure), mais le chunk de désambiguïsation apparaît
désormais dans la fenêtre par défaut de `search_profile` (`n_results=3`), donc
l'agent de scoring reçoit les deux chunks contradictoires ensemble et peut arbitrer
correctement — à condition de lire l'intégralité des chunks retournés, pas
seulement le premier. Le risque resterait entier si un futur appelant limitait la
recherche à `n_results=1` ou traitait le premier résultat comme la règle unique à
appliquer. À garder en tête pour l'implémentation de l'agent de scoring en session 3 :
toujours passer `n_results >= 3` sur les requêtes géographiques, et faire arbitrer
le LLM sur l'ensemble des chunks plutôt que sur le seul meilleur score.

## Session 3 (2026-07-11) — Agent de scoring

**Partie A — `check_geography_rules` (déterministe, hors RAG) :**
- `scoring/geography.py` — matching en dur par ville connue (priorité 1) puis
  département/code postal (priorité 2, Rhône-Alpes uniquement), avec repli
  prudent sur `autre_france`/`inconnu` selon `check_geography_rules_spec.md`.
- `tests/test_geography.py` — 11/11 cas de la spec passés.
- **2 bugs trouvés et corrigés en testant sur des localisations réelles de la
  base (pas seulement les cas de la spec) :**
  1. Le format Hellowork `"Ville - NN"` (ex: `"Saint-Priest - 69"`, vu dès la
     session 1) n'était pas reconnu par le regex de département, qui ne
     couvrait que `(NN)` et `département NN`. Corrigé en ajoutant le pattern
     `- NN` en fin de chaîne.
  2. `"Belgique - Antwerpen"` (offre réellement scrapée en session 1) était
     classé à tort `autre_france` par un fallback trop généreux ("texte non
     vide sans ville connue → France"). Corrigé en ajoutant une liste de pays
     étrangers hors périmètre (Belgique, Luxembourg, Allemagne...) qui
     retombent sur `inconnu` plutôt que sur une règle France non pertinente.
- Cas limite non résolu et documenté plutôt que sur-conçu : `"Lyon ou Genève"`
  (deux villes valides dans le même texte) matche Genève par ordre de tri
  interne, comportement arbitraire non couvert par la spec.

**Partie B — Agent de scoring :**
- `scoring/llm.py` — client Mistral minimal (`call_llm_json`), clé
  `MISTRAL_API_KEY` chargée depuis `.env` (`.env.example` fourni, versionné).
- `scoring/agent.py` — boucle de décision : géographie déterministe en premier
  → `flag_uncertain("géographie")` si zone inconnue sans bloquer le scoring →
  recherche RAG du chunk de ton via le nom de zone (pas le texte brut de
  localisation) → extraction LLM des exigences de l'offre (plafonnée à 10,
  voir limite ci-dessous) → recherche RAG séparée par exigence
  (`n_results=3`) avec `flag_uncertain` si la meilleure distance dépasse
  `NOISE_THRESHOLD=0.75` (seuil identifié en session 2) → arbitrage final LLM
  produisant score, matches, gaps, résumé.
- `scoring/run.py` — point d'entrée CLI : `python -m scoring.run --offer-id N
  [--trace-file chemin.json]`.

**Partie C — Traçabilité :**
- `DecisionTrace` dans `scoring/agent.py` logue chaque requête RAG (étape,
  query, chunks retournés avec distance, conclusion) et chaque
  `flag_uncertain`, en JSON exportable via `--trace-file`. Exemples réels dans
  `scoring/traces_test/`.

**Environnement — venv dédié créé (`job-agent/.venv`) :**
`chromadb` et `mistralai` ont des exigences `opentelemetry` mutuellement
incompatibles (chromadb veut `opentelemetry-api==1.43.0` +
`opentelemetry-semantic-conventions==0.64b0`, mistralai plafonne cette
dernière à `<0.61`). Installer les deux dans l'environnement Python global
(qui sert aussi d'autres projets comme instagrapi/mitmproxy) cassait l'import
de l'un ou l'autre selon l'ordre d'installation. Un venv isolé résout la
résolution de dépendances proprement. **À partir de maintenant, toutes les
commandes du projet doivent utiliser `job-agent/.venv/Scripts/python.exe`**,
pas le Python global.

**Bug externe contourné — `mistralai==2.6.0` (et `2.5.2`) mal empaqueté :**
Le wheel PyPI de `mistralai` n'expose pas `Mistral` depuis `mistralai/`
directement (`mistralai/__init__.py` absent, seuls les sous-modules
`azure/client/extra/gcp` existent) — `from mistralai import Mistral` échoue à
l'import alors que le SDK est bien installé. La classe existe réellement dans
`mistralai.client.sdk.Mistral`. `scoring/llm.py` essaie d'abord l'import
normal puis retombe sur ce chemin interne, avec un commentaire expliquant
pourquoi. À surveiller : si une future version de `mistralai` corrige son
empaquetage, le fallback deviendra inutile mais restera inoffensif.

**Test réel effectué sur 3 offres en base :**
| Offre | Titre | Zone | Score | Gaps honnêtes | Incertains |
|---|---|---|---|---|---|
| 7 | Data Analyst Senior - Lyon | rhone_alpes | 85 | dbt, SAP/MES, gouvernance formelle | 0 |
| 15 | Business Analyst Data Gouvernance | rhone_alpes | 70 | gouvernance formelle, contexte grand compte, outils marché (Collibra/Alation), désalignement IA vs data classique | 0 |
| 24 | Quality System Data Analyst (QMS) | rhone_alpes | 68 | gouvernance QMS (ISO 13485/FDA/EU MDR), audits réglementaires, secteur régulé | 0 |

Les 3 zones géographiques sont correctement déterminées (Lyon → ville connue,
Le Pont-de-Claix → département 38). Les gaps sont honnêtement signalés dans
les 3 cas, cohérents avec la règle d'honnêteté du CLAUDE.md — notamment la
gouvernance formelle des données, systématiquement décrite comme "notions
seulement" ou "expérience technique mais pas formelle", jamais présentée
comme acquise.

**2 bugs trouvés et corrigés pendant les tests réels (offre 24, avant fix) :**
1. **Bruit dans l'extraction d'exigences** : le LLM extrayait jusqu'à 23
   variantes quasi-redondantes d'une même compétence (`data cleansing`,
   `data validation`, `data quality checks`...), diluant le signal et gonflant
   artificiellement le nombre de matches. Corrigé en plafonnant l'extraction à
   10 exigences (`MAX_SKILLS` dans `scoring/agent.py`) et en demandant
   explicitement au LLM de regrouper les variantes proches en une seule
   entrée composite plutôt que de les lister séparément.
2. **Item de gap malformé** : le LLM a une fois produit un objet hors schéma
   (`{"phrase libre...": ""}` au lieu de `{"skill": ..., "note": ...}`),
   silencieusement laissé tel quel dans la sortie. Corrigé par une validation
   défensive (`_validate_items`) qui filtre tout objet ne respectant pas
   exactement le schéma attendu, plutôt que de faire confiance aveuglément au
   JSON retourné malgré le `response_format=json_object`. Ajout aussi d'une
   règle explicite : une compétence ne peut jamais apparaître à la fois dans
   `matches` et `gaps` (observé sur "dbt" dans l'offre 7) — en cas de
   contradiction du LLM avec lui-même, le gap l'emporte par prudence.

**Limites connues à traiter plus tard :**
- Le seuil de bruit RAG (0.75) est appliqué par exigence individuelle, mais
  une exigence formulée en phrase longue et composite (comme
  "gouvernance et gestion des données QMS (ISO 13485, FDA 21 CFR Part 820, EU
  MDR)" après le fix du bug 1) peut matcher un chunk générique avec une
  distance sous le seuil, masquant ainsi un gap réel que `flag_uncertain`
  aurait dû signaler si chaque norme avait été cherchée séparément. Ce n'est
  pas un problème dans les tests actuels (le LLM a quand même identifié le
  gap dans son propre jugement final), mais reste un compromis entre
  "moins de bruit" (fix de cette session) et "détection fine des gaps"
  (potentiellement perdue) à surveiller sur d'autres offres.
- Pas de gestion de cache/coût sur les appels LLM (extraction + arbitrage
  final = 2 appels Mistral par offre, sans compter les futurs appels de
  génération de candidature en session 4).
- Le score et les matches/gaps dépendent entièrement du jugement du LLM sur
  la pertinence sémantique des chunks retrouvés — pas de garde-fou
  supplémentaire si le LLM se trompe d'appréciation malgré un contexte RAG
  correct (contrairement au cas géographique, sorti du RAG justement pour
  cette raison).
