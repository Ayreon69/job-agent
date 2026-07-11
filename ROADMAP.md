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
- Pas de gestion de cache/coût sur les appels LLM (extraction + arbitrage
  final = 2 appels Mistral par offre, sans compter les futurs appels de
  génération de candidature en session 4).
- Le score et les matches/gaps dépendent entièrement du jugement du LLM sur
  la pertinence sémantique des chunks retrouvés — pas de garde-fou
  supplémentaire si le LLM se trompe d'appréciation malgré un contexte RAG
  correct (contrairement au cas géographique, sorti du RAG justement pour
  cette raison).

## Correctif post-session 3 (2026-07-11) : granularité atomique du matching RAG

**Problème :** le seuil de bruit RAG (0.75) était appliqué à la phrase
composite entière d'une exigence (ex: "gouvernance et gestion des données QMS
(ISO 13485, FDA 21 CFR Part 820, EU MDR)"). Une phrase longue peut matcher un
chunk générique avec une distance sous le seuil même si aucune des normes
citées individuellement n'a de vrai équivalent dans le profil — le bruit d'un
élément peut être masqué par la longueur de la phrase composite. Le
regroupement du bug 1 (session 3, `MAX_SKILLS`), pensé pour réduire le bruit
d'affichage, avait comme effet de bord de diluer aussi le signal de matching.

**Correctif :** séparation de la granularité de recherche et de la
granularité d'affichage dans `scoring/agent.py` :
- `_extract_requirements` demande au LLM, pour chaque exigence (toujours
  plafonnée à `MAX_SKILLS`), un libellé composite (`label`, affichage) ET la
  liste des éléments atomiques qui le composent (`atoms`, matching), ex.
  `label="gouvernance et gestion des données QMS (ISO 13485, FDA 21 CFR Part
  820, EU MDR)"` → `atoms=["ISO 13485", "FDA 21 CFR Part 820", "EU MDR",
  "gouvernance des données QMS", ...]`.
- `_search_requirement` fait une recherche `search_profile` séparée
  (n_results=3) sur CHAQUE atome, avec le seuil `NOISE_THRESHOLD=0.75` évalué
  individuellement par atome — jamais sur la phrase composite globale.
- Principe "maillon faible" : si au moins un atome dépasse le seuil de bruit,
  `flag_uncertain(label)` est déclenché pour toute l'exigence composite, même
  si d'autres atomes de la même exigence ont bien matché. Un bon match sur un
  élément ne doit jamais masquer l'absence de match sur un autre.
- Le contexte envoyé au LLM d'arbitrage final distingue maintenant
  explicitement les exigences "incertaines malgré un match partiel" des
  exigences "sans aucun match", pour que le LLM ne traite pas les chunks
  partiels comme une confirmation de compétence acquise.

**Cas concret observé (offre 24, avant/après) :**
Avant le correctif (`trace_24.json`, recherche sur composite) : la requête
`"gouvernance et gestion des données QMS (ISO 13485, FDA 21 CFR Part 820, EU
MDR)"` obtenait `best_distance=0.5357` (chunk `geography_rules::
rule_role_priority_current`) → **"match retenu"**, aucun `flag_uncertain`
déclenché pour cette exigence.

Après le correctif (`trace_24_atomic.json`, recherche par atome) : sur les 7
atomes de la même exigence, 6 matchent sous le seuil (0.49–0.65), mais
**"ISO 13485" isolé obtient `best_distance=0.7625`** (meilleur chunk retrouvé :
`achievements::power_bi_dashboards`, sans rapport réel) — au-dessus du seuil
de bruit. Confirmé indépendamment : une recherche brute sur "ISO 13485" seul
retourne 0.7625/0.7722/0.7790, et sur "FDA 21 CFR Part 820" seul 0.6508
(passe de justesse). Résultat : `flag_uncertain("gouvernance et gestion des
données QMS...")` est maintenant bien déclenché, alors que l'ancien
comportement composite ne l'aurait pas fait. Dans ce cas précis le score final
et les gaps affichés au LLM d'arbitrage restaient corrects (le LLM avait
identifié le gap QMS de lui-même dans son jugement final, comme noté en
session 3), mais le signal structuré `uncertain_flags` — utilisé par le
pipeline en amont du jugement LLM — était jusqu'ici silencieusement faux sur
ce cas. Score final inchangé à 65-68 selon les runs (variabilité normale du
LLM d'arbitrage), gaps toujours honnêtement listés.

**Test :** rerun complet sur l'offre 24
(`scoring/traces_test/trace_24_atomic.json`), 5 gaps identifiés dont la
gouvernance QMS désormais marquée incertaine avec la bonne cause atomique
tracée dans le JSON (`requirement_atom` step, un log par atome).

**Limite restante :** le nombre d'appels `search_profile` par offre augmente
significativement (un appel par atome au lieu d'un par exigence groupée) —
pas un problème de coût (recherche locale, pas d'appel LLM), mais à surveiller
si le nombre d'exigences/atomes extraits croît sur des offres plus verbeuses.

## Session 4 (2026-07-11) : agent de génération d'analyse de candidature

**Objectif :** transformer la sortie de l'agent de scoring (session 3) en une
analyse de candidature structurée en markdown, dans l'esprit des analyses
produites habituellement en conversation — sans recalculer la géographie
(consommée telle quelle depuis `ScoringResult`), en respectant strictement le
ton dicté par la zone, et sans jamais lisser les gaps/incertitudes.

**Implémentation (`generation/analysis.py`, `generation/run.py`) :**
- `generate_analysis(result, offer_title, offer_description, company_name)` :
  boucle de décision en 5 étapes, tracée dans un `GenerationTrace` (même
  principe d'auditabilité que le `DecisionTrace` de session 3) :
  1. Consomme `result.geography_zone` déjà calculé par `check_geography_rules`
     — aucun nouveau calcul géographique.
  2. `search_profile` sur la requête de ton associée à cette zone
     (`ZONE_TO_QUERY`, réutilisé tel quel depuis `scoring/agent.py` pour que
     scoring et génération récupèrent le même chunk de ton pour une même
     zone), avec `n_results=1` — un seul chunk de règle par zone dans
     `geography_rules.md`.
  3. `web_search(company_name)` — **stub désactivé** : décision prise en
     amont (AskUserQuestion) de ne pas intégrer de vraie API de recherche web
     cette session, pour rester cohérent avec la règle d'honnêteté du
     CLAUDE.md (ne jamais fabriquer de contexte non vérifié). La fonction est
     appelée quand l'offre est jugée trop courte/générique
     (`_should_search_web`, heuristique sur la longueur du texte), logue
     l'appel, et retourne toujours `None`. Prête à être branchée sur une
     vraie API plus tard sans changer l'appelant.
  4. Génère le markdown via un unique appel LLM (`call_llm`, pas
     `call_llm_json` — la sortie est du markdown, pas du JSON structuré),
     avec un prompt système qui liste les matches/gaps/uncertain_flags du
     scoring et impose le format à 4 sections : Résumé du matching, Gaps et
     incertitudes, Questions d'entretien probables, Angle de candidature.
  5. Distinction explicite dans le prompt entre "gap confirmé" (compétence
     constatée absente) et "flag_uncertain" (aucun match RAG fiable, ce qui
     n'est pas la même chose qu'une absence confirmée) — l'analyse générée
     doit refléter cette nuance, pas la diluer.
- `generation/run.py` : CLI chaînant scoring (session 3) puis génération pour
  une offre de la base SQLite (`python -m generation.run --offer-id N
  [--output analyse.md] [--trace-file trace.json]`).

**Bug trouvé et corrigé en testant (règle de silence géographique) :**
Le premier prompt système interdisait de *mentionner* la mobilité mais pas de
*nier* sa nécessité. Résultat observé sur l'offre 24 (zone `rhone_alpes`,
`rule_lyon_no_mobility` — silence total attendu) : le LLM a généré la phrase
*"La localisation en Rhône-Alpes correspond parfaitement à la zone
géographique prioritaire de l'offre, **sans nécessité de mobilité**."* — une
violation subtile : nommer l'absence de mobilité revient à en parler, ce que
la règle interdit tout autant que l'affirmer. Corrigé en renforçant
explicitement le prompt système : interdiction du mot "mobilité" et de ses
synonymes (relocalisation, expatriation, international, conjoint,
déménagement) sous toute forme, y compris négative, avec l'explication
"nommer l'absence de mobilité revient à en parler". Reformulation regénérée,
plus aucune occurrence trouvée par recherche automatique
(`grep -iE "mobilit|relocalisation|conjoint|expatriation|international"`) sur
les 3 analyses de test.

**Tests réels sur les 3 offres de la session 3 :**
| Offre | Zone | Règle de ton appliquée | Gap honnête cité | Flag incertain distingué | Mention mobilité |
|---|---|---|---|---|---|
| 7 | rhone_alpes | rule_lyon_no_mobility | dbt, intégration ERP/MES (SAP) | aucun (tous les gaps sont confirmés) | aucune |
| 15 | rhone_alpes | rule_lyon_no_mobility | animation d'ateliers, gouvernance formelle | aucun (tous les gaps sont confirmés) | aucune |
| 24 | rhone_alpes | rule_lyon_no_mobility | gouvernance QMS, secteur régulé, outils médicaux | **gouvernance QMS (ISO 13485/FDA/EU MDR) marquée "flag incertain" séparément du gap confirmé**, avec la nuance explicite "absence de preuve fiable, pas une absence confirmée" | aucune |

Sur l'offre 24, la distinction gap/incertain fonctionne comme prévu grâce au
correctif de granularité atomique de ce même jour : le `flag_uncertain`
déclenché sur "ISO 13485" isolé (voir plus haut) remonte bien jusqu'à la
section "Flags incertains" de l'analyse générée, séparée de la section "Gaps
confirmés" — la nuance entre "on n'a pas trouvé de preuve" et "on a constaté
une absence" est préservée de bout en bout du pipeline scoring → génération.

**Exemple de sortie complète (offre 24, après correctif) :**
Voir `generation/analyses_test/analysis_24.md` (versionné) — extrait de la
section la plus significative :

```
## Gaps et incertitudes
### Gaps confirmés (compétences absentes)
1. **Gouvernance QMS et conformité réglementaire** :
   - Aucune expérience en gouvernance formelle des données QMS
     (ISO 13485, FDA 21 CFR Part 820, EU MDR) ou dans un secteur régulé...

### Flags incertains (absence de preuve fiable, pas une absence confirmée)
- **Gouvernance et gestion des données QMS** (ISO 13485, FDA 21 CFR Part 820,
  EU MDR) : Aucun élément dans le profil ne permet de confirmer ou d'infirmer
  une expérience dans ce domaine spécifique. À clarifier en entretien.
```

**Traces de génération versionnées :** `generation/analyses_test/` contient
les 3 analyses markdown (`analysis_7.md`, `analysis_15.md`, `analysis_24.md`)
et leurs traces JSON (`trace_gen_*.json`, chunk de ton utilisé, distance RAG,
décision web_search, étapes loguées).

**Limites connues à traiter plus tard :**
- `web_search` reste un stub désactivé — aucune offre testée n'a eu besoin de
  contexte entreprise supplémentaire (les 3 descriptions dépassaient le seuil
  de 300 caractères de `_should_search_web`), donc le chemin "offre courte,
  recherche web déclenchée" n'a pas encore été testé avec une vraie offre
  générique. À revisiter si une offre courte apparaît dans un futur scraping.
- Un seul appel LLM (`call_llm`, pas JSON) génère tout le markdown d'un coup
  — pas de validation structurelle automatique du format de sortie (sections
  attendues, absence de fabrication) au-delà du prompt et de la vérification
  manuelle par grep sur la mobilité. Une régression future sur le respect du
  format ne serait pas détectée automatiquement sans un test dédié.
- Le prompt de génération fait implicitement confiance aux matches/gaps déjà
  validés par `_validate_items` en session 3 — aucune revalidation côté
  génération si jamais `ScoringResult` est construit autrement (ex: appel
  direct sans passer par `score_offer`).

## Correctif post-session 4 (2026-07-11) : test du chemin web_search + test de structure automatique

**1. Test du chemin web_search non exercé.** Les 3 offres testées en session 4
avaient toutes une description dépassant le seuil de 300 caractères de
`_should_search_web`, donc le chemin "offre courte → web_search déclenché"
n'avait jamais été exercé. Test dédié dans `tests/test_generation.py` :
construction directe d'un `ScoringResult` (sans passer par `score_offer`,
volontairement) pour une offre fictive très courte ("Data Analyst recherché.
Poste basé à Lyon. Expérience SQL et Power BI souhaitée. CDI." — 89
caractères), appel direct à `generate_analysis`. Résultat :
- `_should_search_web` retourne bien `True` sur ce cas (`assert` dans le
  test).
- `web_search("Entreprise Test SARL")` est appelée, loguée dans
  `GenerationTrace.steps`, retourne bien `None` sans lever d'erreur (stub
  désactivé, comportement attendu).
- L'analyse générée reste complète (4 sections présentes, 4416 caractères) et
  cohérente malgré l'absence de contexte entreprise : le LLM ne fabrique pas
  d'information sur "Entreprise Test SARL", et ajoute même une section "À
  éviter" avertissant explicitement de ne pas promettre des compétences non
  documentées — comportement prudent, pas un crash ni une section vide.

Trace complète du cas (`tests/generation_web_search_case_trace.json`, versionnée) :
```json
{
  "offer_id": 9999,
  "tone_chunk_used": "geography_rules::rule_lyon_no_mobility",
  "tone_rag_query": "règle de ton pour une offre en Rhône-Alpes ou en France, mobilité",
  "tone_rag_distance": 0.3036,
  "web_search_used": true,
  "web_search_result": null,
  "steps": [
    "règle de ton récupérée: geography_rules::rule_lyon_no_mobility (distance=0.3036) pour zone='rhone_alpes'",
    "offre jugée trop courte/générique, tentative de web_search('Entreprise Test SARL')",
    "web_search indisponible (aucun fournisseur configuré) — analyse basée uniquement sur l'offre",
    "analyse générée"
  ]
}
```
Analyse markdown complète versionnée dans `tests/generation_web_search_case.md`.

**2. Test de structure automatique (`tests/test_generation.py`).** Trois
vérifications mécaniques sur chaque analyse générée :
- présence et ordre des 4 sections attendues (`##` headers) ;
- garde-fou anti-fabrication : pour chaque match, au moins un mot-clé de sa
  **justification** (`matched_chunk_summary`) doit apparaître dans
  `scoring/profile/*.md` ;
- absence totale de vocabulaire lié à la mobilité (mobilité, relocalisation,
  expatriation, international, conjoint, déménagement — y compris formes
  négatives) pour toute offre en zone `rhone_alpes` ou `autre_france`.

Lancé sur les 3 offres déjà validées manuellement (7, 15, 24) plus le nouveau
cas web_search — **2 bugs trouvés dans le test lui-même au premier run (2/4
cas passés), corrigés avant de faire confiance au test :**

1. **Faux négatif sur l'apostrophe typographique** : l'offre 15 a généré le
   titre `## Questions d'entretien probables` avec une apostrophe
   typographique (’) au lieu de l'apostrophe droite (') utilisée dans
   `EXPECTED_SECTIONS`, faisant échouer la détection de section alors que la
   section était bien présente et au bon endroit. Corrigé des deux côtés :
   (a) le prompt système de génération précise maintenant explicitement
   d'utiliser l'apostrophe droite dans les titres de section, et (b) le test
   normalise quand même les apostrophes avant comparaison
   (`_normalize_apostrophes`), plutôt que de faire confiance à cette
   consigne pour être toujours respectée.
2. **Garde-fou anti-fabrication testait le mauvais champ** : le test
   vérifiait initialement que le libellé `skill` (ex: "Prétraitement et
   nettoyage des données", "Décloisonnement des silos métiers") partageait
   un mot avec le profil — mais ce libellé est la reformulation par le LLM du
   **besoin de l'offre**, pas un terme du profil candidat. C'est
   `matched_chunk_summary` (ex: "Expérience en traitement de données
   structurées via pandas, numpy, scikit-learn...") qui porte la
   justification réellement censée provenir du profil. Corrigé en vérifiant
   `matched_chunk_summary` au lieu de `skill` — sur ce point précis, aucune
   vraie fabrication n'a été détectée, seulement un test mal ciblé au départ.

Après ces deux corrections, rerun complet : **4/4 cas passés** (offres 7, 15,
24, + cas web_search), confirmant qu'aucune vraie régression de format ou de
fabrication n'existait dans le pipeline de génération lui-même — les échecs
initiaux étaient entièrement imputables au test, pas au code de génération.

**Limite restante :** le garde-fou anti-fabrication reste un contrôle de
cohérence lexicale basique (chevauchement de mots-clés), pas une vérification
sémantique — il ne détecterait pas une justification qui réutilise des mots du
profil dans un sens détourné ou exagéré. Suffisant comme filet de sécurité
mécanique, pas comme garantie d'honnêteté complète (qui reste portée par le
prompt et la relecture humaine ponctuelle).
