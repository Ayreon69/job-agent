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

## Session 5 (2026-07-11) : orchestrateur

**Objectif :** un agent de plus haut niveau qui enchaîne scoring (session 3)
puis génération (session 4) sur une offre, mais qui prend de vraies décisions
sur le déroulement du pipeline selon le contexte, plutôt que d'appeler les
deux étapes dans l'ordre à chaque fois sans condition.

**Schéma (`storage/db.py`) :** ajout de la colonne `jobs.status`
(`nouveau` / `analyse` / `a_valider_geographie` / `echec`), avec une
migration explicite (`_migrate_add_status_column`) car les bases déjà
existantes (créées en session 1, avant l'ajout de la colonne) ne sont pas
mises à jour par un simple `CREATE TABLE IF NOT EXISTS`.

**Implémentation (`orchestrator/agent.py`, `orchestrator/run.py`) — les 3
décisions attendues, dans l'ordre :**

1. **Offre insuffisamment détaillée → re-scraping ciblé avant scoring.**
   Réutilise le seuil de `generation.analysis._should_search_web`
   (300 caractères titre+description) comme heuristique côté orchestrateur :
   une offre trop courte pour fonder un angle de candidature l'est aussi pour
   scorer correctement. Si détectée, tentative de re-scraping via
   `scraper/hellowork.fetch_job_detail` sur l'URL déjà stockée en base (pas
   une nouvelle recherche complète, un ciblage direct sur l'offre concernée).
   Si le re-scraping échoue (exception Playwright) ou n'apporte rien de plus
   (description vide ou pas plus longue), le pipeline continue quand même
   avec la description existante — mais ce choix est explicitement logué,
   jamais silencieux.
2. **Zone géographique "inconnu" → pipeline non bloqué, mais statut dédié.**
   Le scoring et la génération s'exécutent normalement (comme prévu depuis la
   session 3 : `flag_uncertain("géographie")` sans bloquer). L'orchestrateur
   ajoute une décision supplémentaire à son propre niveau : le statut final
   en base est `a_valider_geographie` plutôt que `analyse`, pour qu'un humain
   sache ne pas faire confiance silencieusement au ton généré par défaut sur
   cette offre.
3. **Échec technique → capture, log détaillé, statut `echec`, poursuite du
   batch.** Un `try/except` unique autour de tout le pipeline (re-scraping,
   scoring, génération) capture toute exception, logue le type d'erreur, le
   contexte de l'offre (id/titre/URL) et la stack trace complète, marque
   l'offre `echec` en base, et retourne un résultat plutôt que de laisser
   l'exception remonter — la boucle batch dans `orchestrator/run.py` traite
   donc toujours les offres suivantes.

**Ce que l'orchestrateur ne fait jamais (rappel CLAUDE.md) :** aucune
fonction de ce module n'envoie ni ne soumet quoi que ce soit à un système
externe — il s'arrête après avoir produit l'analyse markdown et le statut en
base. La validation humaine reste le seul chemin vers une action externe.

**Interface :** `orchestrator/run.py`, mode offre unique
(`--offer-id N`) ou mode batch (sans argument, traite tout `status='nouveau'`
en base). Chaque offre traitée produit 4 fichiers dans `orchestrator/runs/` :
`analysis_<id>.md` (si succès), `trace_orchestrator_<id>.json` (les
décisions propres à l'orchestrateur), `trace_scoring_<id>.json` et
`trace_generation_<id>.json` (les traces déjà produites par les sessions 3 et
4, remontées telles quelles).

**Tests réels — 3 scénarios distincts, sur les 30 offres de la session 1 plus
2 offres synthétiques ajoutées pour forcer les cas non standard absents des
30 offres réelles (toutes en Rhône-Alpes/France avec description
substantielle, donc aucun déclencheur naturel des décisions 1 et 2) :**

- **Offre synthétique 31** (`Belgique - Antwerpen`, description tronquée à
  35 caractères, URL factice) : déclenche la décision 1 (re-scraping tenté)
  ET la décision 2 (zone `inconnu`, via `FOREIGN_NON_TARGET_COUNTRIES` de la
  session 3). Le re-scraping a échoué proprement (à ce moment, Chromium
  n'était pas encore installé dans le venv — voir plus bas), logué et
  poursuivi ; la zone `inconnu` a été détectée et le statut final est bien
  `a_valider_geographie`, pas `analyse`. Trace complète :
  ```json
  {
    "offer_id": 31,
    "decisions": [
      "description jugée trop courte/tronquée (48 caractères < 300) — tentative de re-scraping ciblé avant scoring",
      "re-scraping échoué (...) — poursuite avec la description existante en connaissance de cause",
      "scoring terminé: score=95, zone=inconnu, gaps=0, uncertain_flags=1",
      "zone géographique 'inconnu' détectée — pipeline poursuivi (scoring + génération), mais le résultat sera marqué 'a_valider_geographie' plutôt que d'appliquer silencieusement une règle de ton par défaut",
      "génération de l'analyse terminée"
    ],
    "final_status": "a_valider_geographie",
    "error": null
  }
  ```
- **Offre synthétique 32** (URL réelle de l'offre 7, description tronquée à
  37 caractères) : déclenche la décision 1 avec un **re-scraping réussi**
  (après installation de Chromium dans le venv, voir plus bas) — description
  enrichie de 37 à 950 caractères directement depuis la vraie page Hellowork,
  scoring exécuté sur la description complète, statut final `analyse`.
  Démontre le chemin de succès de la décision 1, complémentaire à l'échec
  observé sur l'offre 31.
- **Rate limiting Mistral en conditions réelles (décision 3, cas non
  anticipé mais découvert en testant) :** le premier run batch sur les 30
  offres réelles enchaînées sans délai a produit **13 échecs consécutifs**
  (offres 2 à 14) avec `SDKError: Status 429 Rate limit exceeded`, avant que
  l'API ne se rétablisse d'elle-même pour les offres 15 à 30. Le batch a
  continué jusqu'au bout sans planter — exactement le comportement attendu
  de la décision 3 — et chaque offre en échec a une trace complète avec
  stack trace exploitable, ex. (`trace_orchestrator_2.json`) :
  ```json
  {
    "offer_id": 2,
    "decisions": ["échec technique capturé — offre marquée 'echec': SDKError: API error occurred: Status 429. Body: {...\"rate_limited\"...}"],
    "final_status": "echec",
    "error": "SDKError: ...\noffer_id=2, title='Data Analyst H/F', url='https://www.hellowork.com/fr-fr/emplois/80532972.html'\nTraceback (most recent call last):\n  File \".../orchestrator/agent.py\", line 148, in process_offer\n    scoring_result = score_offer(...)\n  ...\n"
  }
  ```
  Correctif appliqué : ajout d'un délai configurable entre offres en mode
  batch (`--delay-seconds`, défaut 2s) dans `orchestrator/run.py`. Les 13
  offres en échec ont été repassées à `nouveau` et retraitées avec ce délai :
  **0 échec sur le rerun**, confirmant que le délai suffit à éviter le
  rate limit dans ces conditions d'usage.

**Bilan final sur les 30 offres réelles de la session 1, après le correctif
de délai :**
| Statut | Nombre | Détail |
|---|---|---|
| `analyse` | 30 | Toutes les offres réelles, aucune zone `inconnu` naturelle (toutes en Rhône-Alpes ou France identifiable) |
| `a_valider_geographie` | 0 (sur les offres réelles) | 1 sur l'offre synthétique 31 (Belgique) |
| `echec` | 0 (après retraitement) | 13 échecs transitoires (rate limit Mistral) sur le premier run sans délai, tous résolus au rerun avec `--delay-seconds` |

**124 fichiers versionnés** dans `orchestrator/runs/` (31 offres traitées ×
4 fichiers, moins les fichiers scoring/génération de l'offre 31 qui a échoué
son re-scraping mais a quand même produit une analyse — donc bien 4 fichiers
partout sauf remarque : seule une offre marquée `echec` définitivement
n'aurait pas de `analysis_<id>.md` ni de traces scoring/génération, ce qui
ne s'est produit sur aucune offre après le rerun).

**Limites connues à traiter plus tard :**
- ~~Le délai fixe (`--delay-seconds`) est un correctif pragmatique, pas un
  vrai retry avec backoff exponentiel sur 429~~ — traité en correctif
  post-session 5, voir plus bas.
- La décision 1 (re-scraping) réutilise `fetch_job_detail` mais reconstruit
  un `JobListing` minimal à partir des colonnes déjà en base plutôt que de
  passer par `search_jobs` — cohérent avec l'objectif de cibler l'offre
  précise sans relancer une recherche complète, mais suppose que l'URL en
  base reste valide (offre non expirée/supprimée côté Hellowork). Aucun test
  sur une URL expirée réelle cette session.
- Aucune offre réelle des 30 de la session 1 n'a naturellement déclenché les
  décisions 1 et 2 (descriptions substantielles, zones identifiables) — leur
  validation repose sur les 2 offres synthétiques ajoutées spécifiquement
  pour ce test, comme suggéré par la spec de session. À surveiller sur de
  futurs scraping élargis (autres régions, autres sources) où ces cas
  pourraient apparaître naturellement.

## Correctif post-session 5 (2026-07-11) : retry avec backoff exponentiel sur 429

**Objectif :** le délai fixe entre offres (`--delay-seconds`, session 5)
réduit la fréquence des rate limits Mistral mais ne fait rien si un 429
survient quand même — l'offre était marquée `echec` immédiatement, sans
seconde chance. Ajout d'un retry ciblé sur les 429 spécifiquement, en
complément du délai fixe (pas à sa place).

**Implémentation (`scoring/llm.py`) :** `_call_with_retry(make_request,
max_retries=3, backoff_base_seconds=2.0)` enveloppe l'appel API dans
`call_llm` et `call_llm_json`. Détection ciblée via `exc.status_code == 429`
(attribut fiable exposé par `SDKError`/`MistralError` du SDK Mistral, plutôt
que du pattern-matching sur le message d'erreur) — toute autre exception
(401, JSON malformé, etc.) remonte immédiatement dès la première tentative,
sans retry inutile. Backoff exponentiel 2s / 4s / 8s (3 tentatives par
défaut), chaque tentative loguée (`logger.warning`, numéro de tentative et
délai appliqué — pas un retry silencieux). Si toutes les tentatives
échouent, la dernière `SDKError` remonte normalement : l'orchestrateur gère
ça exactement comme avant (statut `echec`, trace complète, poursuite du
batch) — le retry est un filet supplémentaire avant l'échec définitif, pas
un remplacement de la gestion d'échec de session 5.

**Test 1 — mécanique du retry, en mock (`tests/test_llm_retry.py`) :**
4 cas déterministes sans appel API réel : succès après deux 429 simulés,
épuisement des tentatives puis levée de l'exception, un 401 non retenté
(passe dès la première tentative), et vérification du timing exact du
backoff (1.0s / 2.0s / 4.0s avec `time.sleep` mocké). **4/4 cas passés** —
prouve que la mécanique elle-même est correcte, indépendamment de tout vrai
rate limit.

**Test 2 — reproduction réaliste des conditions de session 5, en deux
temps :**

D'abord, rejeu direct du scénario original : les 30 offres relancées avec
`orchestrator.run --delay-seconds 0` (mêmes conditions qu'en session 5).
Résultat : **0 rate limit rencontré, 30/30 analysées**. Constat honnête :
contrairement à l'hypothèse de départ, ce rejeu ne suffit pas à prouver que
le retry fonctionne contre un vrai 429 — chaque offre fait un travail RAG
local significatif (recherches par atome, `sentence-transformers`) entre les
deux appels Mistral réels (extraction + arbitrage), ce qui espace
naturellement les requêtes API bien plus que `--delay-seconds 0` seul ne le
laisse penser. Le run de session 5 avait dû tomber sur une fenêtre de rate
limit plus stricte (chargée côté compte Mistral à ce moment précis), pas
uniquement sur l'absence de délai.

Pour obtenir une preuve non biaisée, `tests/test_llm_retry_live.py` retire
cet espacement naturel : 20 appels `call_llm` réels tirés en boucle serrée,
sans aucun travail RAG entre eux, pour recréer des conditions de rafale
comparables à celles qui avaient causé les 13 échecs originaux. Résultat
réel (aucune donnée retouchée) :
```
[4] ECHEC DEFINITIF après épuisement des tentatives: ...429...
[5] ECHEC DEFINITIF après épuisement des tentatives: ...429...
[6] OK (retries observés: 3) -> 'ok'
...
[10] ECHEC DEFINITIF ... [11] ECHEC DEFINITIF ... [12] ECHEC DEFINITIF ...
[13] OK (retries observés: 2) -> 'ok'
...
[17] ECHEC DEFINITIF ... [18] ECHEC DEFINITIF ... [19] ECHEC DEFINITIF ...

Résumé: 12/20 succès, 8/20 échecs définitifs
Dont 2 succès obtenus APRES au moins un retry sur 429 (preuve que le backoff a absorbé un vrai rate limit)
```
Deux appels (indices 6 et 13) ont réellement échoué une première fois avec un
vrai 429, puis réussi après respectivement 3 et 2 tentatives — preuve directe
que le backoff absorbe un vrai rate limit, pas seulement le cas mocké. Les
8 échecs restants ont épuisé leurs 3 tentatives (jusqu'à 2+4+8=14s d'attente
cumulée chacun) sans jamais obtenir de réponse 200 : dans une rafale aussi
dense (20 requêtes sans aucun espacement), le rate limit Mistral est plus
persistant que ce que 3 tentatives à backoff court peuvent absorber — le
retry réduit le taux d'échec, il ne l'élimine pas dans un scénario de rafale
extrême et volontairement pire que l'usage réel de l'orchestrateur.

**Interprétation honnête pour l'usage réel :** l'orchestrateur (`orchestrator/
run.py`) n'envoie jamais 20 requêtes Mistral sans espacement — chaque offre
insère un travail RAG local entre les deux appels réels, et `--delay-seconds`
(2s par défaut) ajoute un espacement supplémentaire entre offres. Le test 2
en rafale serrée est un stress-test volontairement plus dur que les
conditions réelles, pas une reproduction fidèle de l'usage courant — mais
c'est la seule façon de garantir qu'un vrai 429 était bien présent pour
tester le retry contre lui, plutôt que de se contenter d'un rejeu qui n'en a
rencontré aucun.

**Conclusion :** le retry est un filet réel et vérifié (2/8 429 rencontrés
dans le test en rafale ont été absorbés sans intervention), complémentaire
au délai fixe de session 5, pas un remplacement total du risque de rate
limit sous charge extrême. Combiné au délai fixe existant entre offres, la
probabilité qu'une offre traitée par l'orchestrateur échoue définitivement à
cause d'un 429 est maintenant plus faible qu'avant ce correctif, mais pas
nulle en cas de rafale anormalement dense.

## Session 6 (2026-07-11) : wrapper FastAPI

**Objectif :** exposer l'orchestrateur existant (sessions 3-5) via une API
HTTP, sans y ajouter de nouvelle logique de décision — l'API appelle
`orchestrator.agent.process_offer`, `storage.db`, et lit les fichiers déjà
produits dans `orchestrator/runs/` ; elle ne réimplémente rien.

**Implémentation :**
- `api/schemas.py` : modèles Pydantic purement descriptifs (`HealthResponse`,
  `OfferSummary`, `OfferDetailResponse`, `AnalyzeRequest`, `AnalyzeResponse`).
- `api/main.py` : les 4 endpoints demandés, `FastAPI` + `uvicorn` ajoutés à
  `requirements.txt`. `MISTRAL_API_KEY` est chargé par le simple fait
  d'importer `scoring.llm` (qui appelle déjà `load_dotenv()` en haut de
  fichier) — aucune logique de chargement `.env` dupliquée.
- Comme `score`/`geography_zone` ne sont pas stockés dans `jobs` (calculés
  à la volée et écrits uniquement dans `orchestrator/runs/*.json`),
  `GET /offers` les reconstruit en relisant la ligne de décision
  `"scoring terminé: score=X, zone=Y, ..."` déjà présente dans
  `trace_orchestrator_<id>.json` plutôt que d'ajouter une nouvelle colonne
  SQLite — cohérent avec le principe de session : pas de nouvelle logique,
  juste de la lecture de ce qui existe déjà.

**Les 4 endpoints :**

- **`GET /health`** — vérification simple, aucune logique métier.
  ```
  $ curl http://127.0.0.1:8000/health
  {"status":"ok"}
  ```

- **`GET /offers`** — liste légère (statut, score, zone, titre), pour un
  usage dashboard. Score/zone valent `null` tant que l'offre n'a pas été
  traitée.
  ```
  $ curl http://127.0.0.1:8000/offers
  [
    {"id": 7, "title": "Data Analyst Senior - Lyon H/F", "location": "Lyon - 69",
     "company": "Ippon Technologies", "status": "analyse", "score": 82,
     "geography_zone": "rhone_alpes"},
    ...  (30 offres au total)
  ]
  ```

- **`GET /offers/{offer_id}`** — détail complet : markdown de l'analyse (si
  disponible) + les 3 traces JSON complètes (orchestrateur, scoring,
  génération), pour audit fin. Une offre existante mais pas encore traitée
  renverrait 200 avec `analysis_markdown: null` et les traces à `null`
  (`status: "nouveau"`) plutôt qu'une erreur — seul un `offer_id` absent de
  la base déclenche un 404.
  ```
  $ curl http://127.0.0.1:8000/offers/7
  {"id": 7, "title": "Data Analyst Senior - Lyon H/F", ..., "status": "analyse",
   "analysis_markdown": "## Résumé du matching\n...", 
   "orchestrator_trace": {...}, "scoring_trace": {...}, "generation_trace": {...}}
  ```

- **`POST /analyze`** — déclenche `process_offer` sur un `offer_id` déjà en
  base (choix délibéré, voir "Limites" ci-dessous), écrit les fichiers via
  la même fonction `write_outputs` que `orchestrator/run.py`, renvoie le
  statut final, le markdown, et un `trace_summary` (liste de phrases
  lisibles — les décisions de l'orchestrateur, pas les 3 traces JSON brutes
  qui seraient illisibles en réponse directe ; celles-ci restent accessibles
  via `GET /offers/{id}` après coup).
  ```
  $ curl -X POST http://127.0.0.1:8000/analyze \
      -H "Content-Type: application/json" -d '{"offer_id": 7}'
  {"offer_id": 7, "status": "analyse", "analysis_markdown": "## Résumé...",
   "trace_summary": [
     "scoring terminé: score=82, zone=rhone_alpes, gaps=2, uncertain_flags=0",
     "génération de l'analyse terminée"
   ],
   "error": null}
  ```
  Appel réel chronométré à ~85 secondes (rechargement du modèle
  `sentence-transformers` à chaque process + 2 appels LLM réels) — la
  docstring de l'endpoint recommande explicitement un timeout client d'au
  moins 60s, voire plus en pratique sur un poste sans le modèle déjà en
  cache local.

**Tests réels effectués (serveur lancé en local via
`uvicorn api.main:app --port 8000`) :**
- `GET /health` → `200 {"status":"ok"}`.
- `GET /offers` → 200, liste des 30 offres avec score/zone correctement
  reconstruits depuis les traces.
- `GET /offers/7` → 200, markdown + 3 traces complètes présents.
- **`GET /offers/99999` → 404 `{"detail":"Offre 99999 introuvable"}`**, pas
  de 500 ni de traceback exposé — cas d'erreur explicitement testé comme
  demandé.
- **`POST /analyze` avec `offer_id: 99999` → 404** (même comportement que
  `GET`, la vérification d'existence est partagée via `_load_offer_row`).
- `POST /analyze` avec `offer_id: 7` (offre déjà analysée en session 5) →
  200, ré-exécute tout le pipeline avec succès, statut `analyse`,
  `trace_summary` lisible.
- `GET /docs` et `/openapi.json` (générés automatiquement par FastAPI) → 200,
  utile pour la documentation interactive sans travail supplémentaire.

**Limites connues à traiter plus tard :**
- `POST /analyze` n'accepte qu'un `offer_id` déjà en base, pas une URL à
  scraper à la volée — la spec de session l'anticipait explicitement comme
  une itération future possible plutôt qu'un prérequis de cette session.
- Endpoint synchrone, pas de file de tâches en arrière-plan : un appel
  `POST /analyze` bloque la requête HTTP pendant toute la durée du pipeline
  (~85s observé). Acceptable pour un usage personnel/local à ce stade
  (décision explicite de la spec de session pour éviter la complexité d'une
  queue), mais deviendrait un problème avec plusieurs utilisateurs
  concurrents ou un traitement par lot déclenché via l'API.
- ~~Le modèle `sentence-transformers` est rechargé à chaque appel
  `/analyze`~~ — traité en correctif post-session 6, voir plus bas.
- Aucune authentification/autorisation sur l'API — cohérent avec un usage
  local pour l'instant, à revisiter avant toute exposition réseau plus
  large (session Docker/déploiement).

## Correctif post-session 6 (2026-07-11) : singleton pour le modèle d'embeddings

**Diagnostic avant correctif :** contrairement à l'hypothèse initiale ("le
modèle est rechargé à chaque appel"), les poids `sentence-transformers` sont
en réalité déjà mis en cache process-wide par ChromaDB lui-même
(`SentenceTransformerEmbeddingFunction` maintient un dict de classe `models`
keyé par nom de modèle). Le vrai coût récurrent identifié par mesure directe
(`get_embedding_function()` appelé deux fois de suite) : la **première**
construction de `SentenceTransformerEmbeddingFunction()` dans un processus
déclenche ~12s de requêtes HTTP HEAD vers le Hub HuggingFace (vérification
que le cache local du modèle est à jour), même si les poids eux-mêmes sont
déjà sur disque — la deuxième construction dans le même processus est
quasi-instantanée (0.00s mesuré). Comme `scoring/embeddings/index.py`
reconstruisait `get_embedding_function()`/`get_client()` à chaque appel de
`search_profile_with_scores` (des dizaines de fois par offre), le **premier**
appel de chaque processus payait ces 12s — invisible en mode batch (un seul
processus pour tout le batch, donc payé une fois de toute façon), mais payé
à nouveau sur le tout premier `/analyze` de chaque redémarrage de l'API.

**Correctif (`scoring/embeddings/index.py`) :** `get_embedding_function()` et
`get_client()` transformés en singletons module-level avec double-checked
locking (`threading.Lock`) — construits une seule fois par processus, de
façon thread-safe explicite plutôt que de compter implicitement sur le fait
qu'un seul thread appelle jamais ces fonctions.

**Chargement explicite au démarrage (`api/main.py`) :** remplacement de
`@app.on_event("startup")` (API dépréciée) par un `lifespan` context manager
moderne, qui appelle `get_embedding_function()` et `get_client()` avant que
le serveur commence à accepter des requêtes — pour que même le tout premier
`/analyze` après un redémarrage n'ait plus à payer les 12s.

**Mesures réelles avant/après (même offre id=7, mêmes conditions) :**
| Scénario | Temps mesuré |
|---|---|
| Avant correctif — 1er `/analyze` après démarrage API (session 6) | ~85s (dont ~12s de chargement paresseux du modèle) |
| Après correctif — démarrage de l'API (chargement explicite du modèle) | 12.12s (loggé : `"Modèle d'embeddings chargé au démarrage en 12.12s"`) |
| Après correctif — 1er `/analyze` après démarrage | 56.0s |
| Après correctif — 2e `/analyze` (offre différente) | 66.8s (variation normale de latence Mistral, pas de rechargement modèle) |

Le gain net sur le premier appel (~85s → ~56s, soit ~29s ou ~34% de moins)
correspond bien aux 12s de HEAD requests éliminées, plus une variation de
latence réseau/LLM incompressible (confirmée par le fait que le 2e appel à
66.8s n'est pas plus rapide que le 1er — la variance vient de Mistral, pas du
modèle d'embeddings). Aucune requête HTTP vers HuggingFace Hub observée dans
les logs pendant les deux appels `/analyze` post-correctif (vérifié par
grep sur `huggingface.co` dans les logs serveur) — confirmation directe que
le modèle n'est plus jamais rechargé après le démarrage.

**Non-régression du mode batch vérifiée :** `orchestrator/agent.process_offer`
rejoué directement (sans passer par l'API) sur 3 offres dans le même
processus Python : 62.80s / 60.31s / 55.51s — durées homogènes d'une offre à
l'autre, aucun pic sur la première confirmant que le comportement "un seul
chargement pour tout le batch" n'a pas régressé vers un rechargement par
offre.

**Concurrence testée réellement (pas supposée) :** deux requêtes
`POST /analyze` (offres 2 et 3) lancées en parallèle via deux processus
`curl` simultanés contre le même serveur uvicorn. Les logs confirment un
véritable entrelacement (lignes `[offer 2]` et `[offer 3]` alternées pendant
l'exécution, les deux appelant `search_profile_with_scores` — donc le
singleton — en concurrence réelle sur des threads différents, FastAPI
exécutant les handlers synchrones dans un threadpool). Résultat : les deux
requêtes ont abouti en 200 OK (57.4s et 68.2s) avec chacune son analyse
correcte et propre à son offre, aucune corruption croisée, aucune exception.
Cohérent avec la garantie de thread-safety standard de PyTorch/
sentence-transformers pour de l'inférence pure en mode eval (pas de mutation
d'état partagé pendant `encode()`) — vérifié empiriquement plutôt que
seulement invoqué comme argument théorique.

## Session 7 (2026-07-12) : dockerisation de l'API

**Objectif :** empaqueter ce qui existe déjà (sessions 3-6 : scoring,
génération, orchestrateur, RAG, API FastAPI) dans un conteneur Docker
fonctionnel — aucune nouvelle logique métier.

**Blocage matériel rencontré avant tout test :** Docker Desktop refusait de
démarrer ("Virtualization support not detected"). Diagnostic confirmé via
PowerShell (`Get-CimInstance Win32_Processor | Select
VirtualizationFirmwareEnabled` → `False`) : la virtualisation (VT-x) était
désactivée au niveau du BIOS/firmware, pas un problème logiciel contournable.
Résolu par l'utilisateur en activant VT-x dans le BIOS et en redémarrant la
machine — aucune action possible depuis l'agent tant que ce n'était pas fait,
tests bloqués jusque-là plutôt que simulés.

**Fichiers produits :**
- `docker/Dockerfile` — image basée sur `python:3.11-slim` (aligné sur la
  version locale du venv, 3.11.9).
- `docker/requirements-lock.txt` — `pip freeze` complet du `job-agent/.venv`
  local fonctionnel, installé à la place de `requirements.txt` (non pinné,
  `>=`) pour que le conteneur reproduise exactement l'environnement qui a
  résolu le conflit opentelemetry de la session 3
  (`opentelemetry-semantic-conventions==0.60b1` dans l'environnement réel,
  et non 0.64b0 comme supposé à l'époque — corrigé ici par la mesure directe
  plutôt que par la mémoire de la session 3).
- `docker/entrypoint.sh` — construit l'index ChromaDB au premier démarrage
  si `scoring/embeddings/chroma/` est vide (cas d'un volume neuf), sinon ne
  fait rien. Sans ça, un volume fraîchement créé aurait fait échouer
  systématiquement `search_profile()` (`NotFoundError` sur la collection
  manquante) et donc chaque offre en `echec` dès le premier `/analyze`.
- `docker-compose.yml` — un service, 3 volumes nommés (`storage`, `chroma`,
  `orchestrator/runs`), variables d'env via `.env`.
- `.dockerignore` — exclut `.venv/` (1.5GB), `.git/`, les DB/index locaux.
- `.env.example` — recréé (existait en théorie depuis la session 3 mais
  n'avait en fait jamais été committé — trouvé manquant en préparant cette
  session).

**Le fallback `mistralai` (session 3) et l'installation Playwright ont été
testés explicitement, pas supposés fonctionner :**
- Fallback d'import `mistralai` (`scoring/llm.py`, try/except vers
  `mistralai.client.sdk.Mistral`) : identique en conteneur, aucune
  adaptation nécessaire — le bug est dans le wheel PyPI lui-même, pas lié à
  l'environnement.
- `RUN python -m playwright install --with-deps chromium` : a nécessité une
  longue liste de libs système Debian (`libnss3`, `libatk-bridge2.0-0`,
  `libgbm1`, etc., voir Dockerfile) installées en amont via `apt-get` —
  sans elles, `playwright install --with-deps` échoue. Testé avec succès :
  voir le test de re-scraping réel plus bas, qui confirme que Chromium
  fonctionne réellement en conteneur, pas seulement que l'installation
  s'est terminée sans erreur.

**Build réel — deux tentatives, la première ayant révélé un vrai problème :**

| Tentative | Temps | Taille image | Résultat |
|---|---|---|---|
| 1 (torch non contraint) | 13m42s | **13.2GB** | Build réussi, mais anormalement lourd |
| 2 (torch CPU-only forcé) | 5m36s | **6.62GB** | Build réussi, taille attendue |

Diagnostic de l'écart : `docker/requirements-lock.txt` contenait
`torch==2.13.0` sans préciser la variante — le `.venv` local avait résolu la
variante `+cpu` (confirmé : `torch.__version__` → `2.13.0+cpu` en local),
mais un `pip install` de ce même pin dans l'image Debian slim a résolu par
défaut la variante CUDA (`2.13.0+cu130`, ~9GB de bibliothèques NVIDIA
embarquées) — vérifié directement (`docker run --rm job-agent python -c
"import torch; print(torch.version.cuda)"` → `13.0` sur le premier build).
Ce projet n'utilise jamais le GPU (l'inférence `sentence-transformers` tourne
sur CPU, comme documenté depuis la session 2). Corrigé en retirant `torch`
de `requirements-lock.txt` et en l'installant séparément depuis l'index
officiel CPU-only de PyTorch
(`--index-url https://download.pytorch.org/whl/cpu`) avant le reste des
dépendances — confirmé par le nom du wheel téléchargé au 2e build
(`torch-2.13.0+cpu-...`, 191.8MB au lieu de la roue CUDA nettement plus
grosse).

**Tests réels effectués (`docker compose up -d`, conteneur `job-agent-api-1`) :**
1. `GET /health` → `200 {"status":"ok"}`.
2. `GET /offers` sur un volume neuf → `[]` (base vide, comme attendu).
3. Offre de test insérée directement via `docker exec` (URL Hellowork réelle
   de la session 3/7, description tronquée à 37 caractères) pour forcer
   spécifiquement le chemin de re-scraping de la décision 1 (session 5).
4. **`POST /analyze` réel, chaîne complète testée depuis le conteneur** :
   logs confirmant `"re-scraping réussi: description enrichie de 37 à 950
   caractères"` — **Playwright/Chromium fonctionne réellement en
   conteneur**, pas seulement installé — puis scoring (RAG via ChromaDB +
   appel Mistral réel), génération (2e appel Mistral réel), statut final
   `analyse`. Réponse `200 OK` en 56.0s (comparable aux temps mesurés en
   local sessions 5-6).
5. `GET /offers/{id}` → détail complet (markdown + 3 traces JSON) présent.
6. `GET /offers/99999` → **404** `{"detail":"Offre 99999 introuvable"}`, pas
   de 500 — cas d'erreur explicitement re-testé depuis le conteneur.
7. **Persistance testée par un vrai redémarrage** (`docker restart
   job-agent-api-1`, pas juste supposée) : les logs de redémarrage confirment
   `"[entrypoint] Index ChromaDB déjà présent (volume persisté), pas de
   reconstruction."` (pas de reconstruction inutile de l'index), et
   `GET /offers` après redémarrage renvoie toujours l'offre analysée avant
   l'arrêt (`status: "analyse"`, `score: 78`), avec son markdown et ses
   traces toujours accessibles via `GET /offers/1`.

**Limites connues à traiter plus tard :**
- L'image reste à 6.62GB malgré la correction torch — `sentence-transformers`
  (poids du modèle pré-téléchargés, ~1.1GB), Chromium (~300MB), et les
  dépendances Python restantes (chromadb, mistralai, torch CPU) representent
  un poids incompressible pour ce stack, pas un problème d'optimisation
  Docker à ce stade (pas de multi-stage build tenté cette session).
- `docker/requirements-lock.txt` fige des versions exactes issues d'un
  `pip freeze` ponctuel — à régénérer manuellement si `requirements.txt`
  évolue dans une future session, pas de mécanisme automatique de
  synchronisation entre les deux fichiers.
- ~~Le `HEALTHCHECK` du Dockerfile n'a pas été testé en conditions d'échec~~
  — traité en correctif post-session 7, voir plus bas.

## Correctif post-session 7 (2026-07-12) : /health distingue "process up" de "pipeline configuré"

**Problème :** `GET /health` renvoyait `200 {"status": "ok"}` dès que le
process FastAPI tournait, sans vérifier que le pipeline derrière était
réellement utilisable. Un `docker-compose up` avec un `.env` mal rempli
(`MISTRAL_API_KEY` vide ou absente) aurait donné un conteneur "sain" en
apparence, avec chaque `/analyze` échouant silencieusement au premier appel
LLM — le pire moment pour découvrir un problème de configuration.

**Implémentation :**
- `scoring/embeddings/index.py` : nouvelle fonction `is_initialized()` qui
  lit l'état des singletons `_embedding_function`/`_client` (session 6) SANS
  les construire — contrairement à `get_embedding_function()`/`get_client()`,
  un appel à `is_initialized()` ne déclenche jamais de chargement paresseux.
  Nécessaire pour que `/health` ne paie jamais le coût d'un chargement modèle
  juste pour répondre à un ping de monitoring.
- `api/main.py` : `GET /health` fait 3 vérifications, aucune ne fait
  d'appel réseau :
  1. `mistral_key_present` — présence/non-vacuité de `MISTRAL_API_KEY` dans
     l'environnement (`os.environ`), pas sa validité (vérifier la validité
     nécessiterait un vrai appel Mistral, explicitement exclu).
  2. `embeddings_loaded` — `is_initialized()`, donc reflète un échec réel du
     chargement au démarrage (`lifespan`, session 6) plutôt que de répondre
     "ok" par défaut si ce chargement avait échoué silencieusement.
  3. `database_accessible` — ouverture de connexion SQLite + `SELECT 1`,
     capturée dans un `try/except` (pas de présomption que la DB répond).
- Réponse structurée : `{"status": "ok"|"degraded", "checks": {...}}`
  (`api/schemas.py`, `HealthChecks`) plutôt qu'un `"ok"` binaire opaque.
- **Décision sur le code HTTP** : 200 si tout passe, **503** si un seul check
  échoue. Raisonnement : un `HEALTHCHECK` Docker ou un futur load balancer
  n'inspecte généralement que le code HTTP, pas le corps JSON — un `200` avec
  `"degraded"` caché dans la réponse serait silencieusement ignoré par ce
  genre d'outil, ce qui annulerait l'intérêt de détecter le problème au
  niveau du conteneur plutôt qu'au premier `/analyze` en échec. Le
  `HEALTHCHECK` existant du Dockerfile (`curl -f`) échoue déjà nativement sur
  tout code ≥400, donc aucune modification du Dockerfile n'a été nécessaire
  pour que ce changement soit pris en compte par Docker.

**Tests réels — les deux cas demandés, via de vrais conteneurs (pas de mock) :**

1. **Chemin nominal**, conteneur relancé via `docker compose up -d` avec le
   vrai `.env` monté :
   ```
   $ curl -s -w "\nHTTP_STATUS:%{http_code}\n" http://localhost:8000/health
   {"status":"ok","checks":{"mistral_key_present":true,"embeddings_loaded":true,"database_accessible":true}}
   HTTP_STATUS:200
   ```

2. **Cas d'échec explicitement provoqué** : conteneur relancé avec
   `docker run -e MISTRAL_API_KEY=` (vide, sans passer par `.env`) sur les
   mêmes volumes persistés :
   ```
   $ curl -s -w "\nHTTP_STATUS:%{http_code}\n" http://localhost:8003/health
   {"status":"degraded","checks":{"mistral_key_present":false,"embeddings_loaded":true,"database_accessible":true}}
   HTTP_STATUS:503
   ```
   Résultat exactement conforme à l'objectif : `mistral_key_present: false`
   isolé des deux autres checks restés `true` (le modèle d'embeddings et la
   base restent fonctionnels même sans clé Mistral — seul l'appel LLM
   échouerait, ce que `/health` signale maintenant AVANT le premier
   `/analyze` raté, sans avoir eu besoin de faire cet appel réel pour le
   détecter).

**Avant/après sur ce cas précis :**
| | Avant correctif | Après correctif |
|---|---|---|
| Réponse `/health` avec clé vide | `200 {"status":"ok"}` (faux positif) | `503 {"status":"degraded","checks":{"mistral_key_present":false,...}}` |
| Détectable par un `HEALTHCHECK` Docker/monitoring | Non — ressemble à un conteneur sain | Oui — code 503 explicite |
| Moment de découverte du problème | Au premier `/analyze` (échec `echec`, après un appel Mistral raté) | Au démarrage du conteneur, sans appel réseau |

**Incident de test rencontré (documenté par transparence) :** le premier
test du cas nominal après rebuild a montré un `/health` toujours sans le
champ `checks` — le conteneur `docker compose up` réutilisait une image
`job-agent-api:latest` obsolète (construite par un `docker compose build`
antérieur, distincte du tag `job-agent:latest` que je reconstruisais
manuellement). Diagnostiqué via `docker exec ... grep` (le code source dans
le conteneur ne contenait pas les nouvelles fonctions), corrigé en retaguant
l'image à jour (`docker tag job-agent:latest job-agent-api:latest`) plutôt
qu'en relançant un rebuild complet inutile. Point de vigilance à garder pour
les prochaines sessions Docker : `docker build -t X` et `docker compose
build` gèrent des tags d'image séparés par défaut, ils ne se synchronisent
pas automatiquement.

## Session 8 (2026-07-12) : GitHub Actions pour le scraping/scoring quotidien

**Objectif :** automatiser l'exécution de ce qui existe déjà (scraper session
1, orchestrateur session 5) via un workflow GitHub Actions programmé, sans
nouvelle logique métier. Jamais de soumission automatique de candidature
(CLAUDE.md).

**Décision — exécution Python directe plutôt que Docker en CI :** le
Dockerfile de la session 7 reste l'artefact de déploiement pour l'API, mais
ce workflow n'exécute pas l'API — il lance deux scripts batch
(`scraper.run`, `orchestrator.run`). Un runner GitHub hébergé donne déjà un
environnement Python 3.11 propre par job ; construire ou puller l'image
(~6.6GB) n'aurait rien apporté de spécifique à Docker ici (pas de
préoccupation d'isolation host sur un runner jetable) et aurait seulement
ajouté du temps de build/transfert. Même jeu de dépendances verrouillées que
Docker (`docker/requirements-lock.txt` + torch CPU via l'index PyTorch dédié)
pour éviter de re-découvrir en CI le conflit opentelemetry résolu en session
3.

**Persistance entre les runs — décision et pourquoi :** un run GitHub Actions
repart d'un checkout propre à chaque fois (pas de volume comme en Docker
local). Comparé à trois options :
- **Commit automatique dans le repo (choisi)** : le workflow commit
  `storage/jobs.db` + `orchestrator/runs/` (bot `job-agent-bot`, message
  `[skip ci]`) à la fin de chaque run réussi. Simple, versionné, inspectable
  via `git log`/`git diff` comme n'importe quel autre changement, aucun
  risque d'éviction. Volumes actuels (DB 144K, runs 1.4M, croissance lente)
  restent négligeables pour un repo git.
- **`actions/cache`** : écarté — pas conçu pour être une source de vérité
  (éviction LRU sous pression, limite 10GB/repo, pas versionné), détournerait
  un outil d'accélération de build de son usage normal.
- **Artifact entre runs** : écarté — pas de restauration automatique (il
  faudrait interroger l'API GitHub pour retrouver le dernier artifact),
  rétention 90 jours par défaut, plomberie ajoutée pour un gain nul face à
  l'option commit.

`scoring/embeddings/chroma/` (l'index vectoriel) n'est PAS persisté de cette
façon : il est reconstruit à chaque run depuis les fichiers source déjà
versionnés `scoring/profile/*.md` (quelques secondes, évite de committer un
binaire régénérable à l'identique). `.gitignore` explicitement mis à jour
(`!storage/jobs.db`) pour cette exception délibérée — les autres `*.db`
locaux restent ignorés.

**Secret :** `MISTRAL_API_KEY` chargé via `secrets.MISTRAL_API_KEY` (GitHub
Secrets, configuré via `gh secret set`), jamais en clair dans le workflow.

**Sécurité — limite explicite respectée :** aucune étape du workflow
n'envoie, ne publie, ni ne soumet quoi que ce soit à l'extérieur — uniquement
scraper, scorer, générer, committer les résultats pour consultation
ultérieure via l'API ou les fichiers générés. `permissions: contents: write`
est le seul droit élevé accordé, strictement nécessaire pour le commit de
persistance.

**Déclenchement :** `schedule` (cron quotidien `0 6 * * *`, ~08:00
Europe/Paris — volume actuel de quelques dizaines d'offres/jour au plus)
+ `workflow_dispatch` pour déclenchement manuel/test. `concurrency` avec
`cancel-in-progress: false` pour éviter que deux runs concurrents écrivent
`jobs.db` en même temps (mise en file plutôt qu'annulation).

**Tests réels effectués (deux runs `workflow_dispatch` consécutifs, pas de
simulation) :**

1. **Premier run** (`29186309321`, 48m52s) : scraping réel (Hellowork,
   requêtes/région par défaut), 36 offres au statut `nouveau` trouvées
   (30 nouvelles scrapées + 6 déjà en base non traitées), orchestrateur batch
   exécuté avec succès sur les 36 — **`analyse: 36, a_valider_geographie: 0,
   echec: 0`**. Commit bot réel poussé (`aebe25c..5c6fa41`) avec les 4
   fichiers de sortie (analyse + 3 traces) pour chacune des 36 offres plus la
   DB mise à jour.
2. **Deuxième run** (`29200908630`, 10m17s), déclenché après le premier sans
   modification manuelle entre les deux : le scraper a retrouvé
   majoritairement des doublons (ignorés par `UNIQUE(source, source_id)` /
   `upsert_job`), et **une seule offre neuve** (offer 148) est apparue au
   statut `nouveau` — les 66 offres déjà `analyse` n'ont **pas** été
   retraitées (`Traitement de 1 offre(s)...` dans les logs, `Total: 1`).
   Commit bot réel (`5c6fa41..0a4a14d`) ne contenant que les 4 fichiers de la
   nouvelle offre 148.
3. **Vérification a posteriori** : `git show origin/master:orchestrator/runs/analysis_37.md`
   confirme que l'analyse produite lors du premier run reste lisible et
   intacte après le second commit — aucune perte, aucune régénération
   inutile.

**Problèmes spécifiques à l'environnement CI rencontrés :** aucun bloquant.
Seule note : `Node.js 20 is deprecated` (annotation GitHub sur
`actions/checkout@v4`/`actions/setup-python@v5`, forcés sur Node 24 par le
runner) — avertissement d'infrastructure GitHub, sans action requise côté
projet. Le premier run a pris ~49 minutes (36 offres × ~2s de délai +
plusieurs appels Mistral par offre pour l'extraction RAG atomique), à garder
en tête si le volume quotidien augmente significativement par rapport au
timeout de 60 minutes fixé dans le workflow.

**Fichiers :** `.github/workflows/scrape-and-score.yml`, `.gitignore` (ajout
de l'exception `storage/jobs.db`).

## Session 9 (2026-07-12) : dashboard web pour consulter les offres scorées

**Objectif :** interface de consultation en lecture seule au-dessus de l'API
existante (session 6) — aucune nouvelle logique métier, uniquement un
affichage de ce que l'API retourne déjà.

**Stack — HTML/JS simple plutôt que React :** pas de valeur ajoutée réelle
d'un framework ici — une table triable/filtrable et un panneau de détail sur
clic sont un besoin trop simple pour justifier un build toolchain (webpack/
vite), une dépendance npm, ou l'overhead conceptuel d'un framework de
composants pour un usage personnel mono-page. Servi par `StaticFiles` de
FastAPI (`api/static/`, monté sur `/static`, `index.html` servi à `/`) plutôt
qu'un serveur frontend séparé — un seul process à faire tourner.

**Extension API nécessaire (pas de nouvelle décision métier, juste de
l'exposition) :** aucun champ structuré `gaps`/`matches` n'est persisté nulle
part — `ScoringResult.gaps` ne survit que dans le markdown généré par le LLM
(`trace_scoring_<id>.json` ne contient que `uncertain_flags`, pas `gaps`, voir
`scoring/agent.py` `ScoringResult`). `api/main.py` ajoute donc un parsing
positionnel du markdown (`_parse_gaps_and_uncertain`, `_parse_matching_summary`) :
- Le titre de section top-level `## Gaps et incertitudes` est fixé par le
  prompt de génération (testé dans `tests/test_generation.py`) — utilisé comme
  ancre fiable.
- Le sous-titre juste en-dessous ("Gaps confirmés", niveau `###` ou `**gras**`)
  varie librement selon la sortie LLM (constaté sur les 30+ analyses réelles :
  `### Gaps confirmés (compétences absentes)`, `### **Gaps confirmés**`,
  `**Gaps confirmés (...) :**`...) — le parsing ne matche donc PAS un texte de
  sous-titre fixe, il repère les items de liste (`- **Label**` ou `N. **Label**`)
  et bascule vers le bucket "incertain" au premier repère contenant "incertain".
- Testé sur les **~40 fichiers markdown réels** déjà générés (sessions 3-8) :
  100% parsés sans exception, comptes de gaps cohérents avec une relecture
  manuelle (offre 24 : 4 gaps + 1 incertain — ISO 13485, cohérent avec le
  correctif post-session 3 ; offre 7 : 4 gaps + 1 incertain avec un style de
  liste numérotée `1.`/`2.`, correctement géré).
- Nouveaux champs exposés : `OfferSummary.gaps_count`/`uncertain_count` (liste
  `/offers`), `OfferDetailResponse.score`/`geography_zone`/`matching_summary`/
  `gaps`/`uncertain_flags` (détail `/offers/{id}`) — tous `None`/liste vide si
  l'offre n'a pas encore d'analyse, jamais d'exception.

**Interface livrée :**
- Table triable (clic sur un en-tête, bascule asc/desc), triée par score
  décroissant par défaut (les offres sans score triées en dernier, quelle que
  soit la direction — un score manquant n'est pas "pire", juste pas encore
  comparable).
- Filtres zone géographique (6 valeurs réelles de `check_geography_rules` :
  `suisse_romande`, `rhone_alpes`, `uae_gcc`, `suisse_autre`, `autre_france`,
  `inconnu`) et statut, peuplés dynamiquement depuis les valeurs réellement
  présentes dans `/offers` (pas de liste figée qui pourrait diverger du
  backend). Badge vert pour toute zone classifiée avec confiance, ambre
  uniquement pour `inconnu` (le seul cas marqué `a_valider_geographie` par
  l'orchestrateur, donc le seul nécessitant réellement une vérification
  humaine — pas une question de "priorité" au sens CLAUDE.md).
- Panneau de détail sous la table au clic : score, résumé court du matching
  (première puce de la section, pas les 6+ puces complètes), gaps confirmés et
  flags incertains sous forme de listes courtes avec compteurs, lien vers
  `GET /offers/{id}` (JSON brut incluant le markdown complet) — pas de rendu
  markdown élaboré dans cette première version comme demandé, seul le `**gras**`
  est converti en `<strong>` côté client (bug visuel constaté et corrigé lors
  des tests, voir plus bas).
- Rendu null-safe : score/zone absents affichés `—`, jamais d'exception JS.

**Tests réels effectués (Playwright headless contre le serveur FastAPI local,
pas de mock, 14 vérifications automatisées + captures d'écran) :**

1. Chargement de `/` avec les 67 offres réelles de la base (30 scrapées
   session 1 + 36 traitées + 1 nouvelle du run CI de la session 8) : la table
   affiche bien les lignes réelles, tri par score décroissant confirmé
   (première ligne avec un score numérique non vide), **aucune erreur console
   JS**.
2. Filtre zone testé avec une vraie valeur (`autre_france`) : réduit
   effectivement le nombre de lignes visibles (67 → 3, vérifié).
3. Filtre statut testé avec une offre de test insérée au statut `nouveau`
   (créée proprement via `storage.db.upsert_job`, pas via le CLI `sqlite3`
   qui a d'abord introduit un bug d'encodage UTF-8 corrompant le titre —
   détecté par un crash `sqlite3.OperationalError: Could not decode to UTF-8`
   sur `GET /offers`, corrigé en réinsérant via Python) : le filtre isole
   correctement cette unique offre.
4. **Clic sur l'offre `nouveau` (non scorée)** : le panneau de détail
   s'affiche sans erreur JS, avec le message "cette offre n'a pas encore été
   traitée" plutôt qu'un score/zone vides mal gérés — exactement le
   comportement demandé.
5. Clic sur une offre `analyse` réelle : panneau affiche score, résumé du
   matching, gaps/incertitudes avec compteurs, lien vers l'analyse complète —
   confirmé par capture d'écran.
6. Bascule du tri (clic sur l'en-tête Score) : la classe CSS de direction de
   tri change bien (`sorted-desc` → `sorted-asc`).
7. `GET /offers/99999` (déjà couvert par la session 6, revérifié ici) : 404
   propre, pas de 500.

**Bug trouvé et corrigé pendant les tests :** le résumé du matching (première
puce de "Résumé du matching") est affiché tel quel côté client — le markdown
`**gras**` généré par le LLM apparaissait donc littéralement avec ses
astérisques dans l'interface (visible sur la première capture d'écran). Corrigé
avec `escapeAndBold()` côté JS (conversion `**texte**` → `<strong>`, pas un
rendu markdown complet, juste ce cas précis) — reconfirmé par une seconde
capture d'écran après correction, tous les 14 tests automatisés toujours au
vert après le changement.

**Offre de test nettoyée** de la base après les tests (comme pour les
sessions précédentes).

**Fichiers :** `api/static/index.html`, `api/static/dashboard.css`,
`api/static/dashboard.js`, `api/main.py` (mount `StaticFiles` + route `/` +
`_parse_gaps_and_uncertain`/`_parse_matching_summary`), `api/schemas.py`
(champs `gaps_count`/`uncertain_count`/`score`/`geography_zone`/
`matching_summary`/`gaps`/`uncertain_flags` ajoutés).

**Limites connues à traiter plus tard :**
- ~~Le parsing du markdown pour les compteurs de gaps est un pis-aller...~~ —
  traité en correctif post-session 9, voir plus bas.
- Pas de rendu markdown complet pour le lien "analyse complète" (ouvre le
  JSON brut de `GET /offers/{id}`, qui inclut le markdown en texte) — accepté
  explicitement comme suffisant pour cette première version.

## Correctif post-session 9 (2026-07-12) : sortie structurée pour matches/gaps/uncertain_flags

**Problème :** `api/main.py` re-parsait le markdown généré par
`generation/analysis.py` (`_parse_gaps_and_uncertain`, `_parse_matching_summary`)
pour en extraire les compteurs affichés par le dashboard — un pis-aller qui
fonctionnait à 100% sur les analyses réelles mais dépendait d'un format de
sortie LLM non contractuel (seul le titre de section top-level `## Gaps et
incertitudes` est garanti par le prompt, pas le style de sous-titre ni de
puce en dessous).

**Décision — zéro appel LLM supplémentaire, formatage déterministe en
Python :** la consigne demandait de choisir entre un appel JSON combiné et
deux appels séparés, en testant les deux en cas de doute. Analyse du besoin
réel avant de choisir : `ScoringResult.matches`/`.gaps`/`.uncertain_flags`
(session 3) contiennent DÉJÀ tout ce qui était demandé — un libellé
(`skill`) et une justification courte (`matched_chunk_summary`/`note`) par
item. Le problème n'était donc pas un manque d'information à faire produire
par un LLM, mais un manque de *persistance* de cette information déjà
existante sous forme structurée. Conclusion : aucun appel LLM, ni combiné ni
séparé, n'est nécessaire — `generation/analysis.py` construit
`StructuredAnalysis` directement en Python à partir de `ScoringResult` (voir
`_build_structured_analysis`), en parallèle de l'appel `call_llm` existant
pour le markdown (totalement inchangé). Cette option n'était pas dans la
liste proposée par la consigne mais respecte strictement son objectif
("mise en forme fidèle de ce que ScoringResult contient déjà — pas une
nouvelle interprétation") mieux qu'un second appel LLM ne pourrait le faire :
un second appel LLM demandant de "réextraire" la structure depuis soit
`ScoringResult` soit le markdown généré réintroduirait exactement le risque
de divergence que ce correctif doit éliminer — un LLM qui paraphrase un
paraphrase. Zéro coût, zéro latence additionnelle, zéro nouveau point de
défaillance JSON malformé, divergence structurellement impossible (pas une
propriété testée à chaque run, une propriété garantie par construction).

**Validation défensive :** `_validate_items` (déjà utilisée par
`scoring/agent.py` sur sa propre sortie LLM) est réappliquée sur
`ScoringResult.matches`/`.gaps` au moment de construire `StructuredAnalysis`
— pas parce que `call_llm_json` n'aurait pas déjà validé une fois côté
scoring, mais pour protéger contre un `ScoringResult` construit à la main
(exactement le cas du test `web_search` dans `tests/test_generation.py`, qui
construit un `ScoringResult` synthétique sans passer par `score_offer`).

**Fichiers modifiés :**
- `generation/analysis.py` : `StructuredAnalysis` (dataclass), `_build_structured_analysis`,
  `structured_analysis_to_json` ; `generate_analysis` retourne désormais
  `(markdown, structured_analysis, trace)` — signature élargie, pas remplacée.
- `orchestrator/agent.py` : `OrchestrationResult.structured_analysis_json` ajouté.
- `orchestrator/run.py` : `write_outputs` persiste `structured_analysis_<id>.json`
  en plus des 3 fichiers existants.
- `generation/run.py`, `tests/test_generation.py` : adaptés au nouveau tuple
  de retour à 3 éléments.
- `api/schemas.py` : `MatchItem`/`GapItem` (nouveaux), `OfferDetailResponse.matches`
  (nouveau), `.gaps`/`.uncertain_flags` passent de `list[str]` à des objets
  structurés ; `matching_summary` (l'ancien hack "première puce") **supprimé**,
  remplacé par `matches` qui est strictement plus informatif.
- `api/main.py` : `_parse_gaps_and_uncertain`/`_parse_matching_summary`
  **supprimées sans fallback** (comme demandé) ; nouvelle
  `_read_structured_analysis` qui lit directement `structured_analysis_<id>.json`.
- `api/static/dashboard.js` : `renderDetail` adapté au nouveau schéma —
  affiche désormais une vraie section "Points forts" avec justification par
  match (amélioration par rapport à l'ancienne puce unique de résumé),
  gaps/uncertain rendus depuis des objets `{skill, note}` au lieu de chaînes.

**Tests réels effectués (pas de simulation) :**

1. `tests/test_generation.py` relancé sur offres 7/15/24 + le cas synthétique
   web_search : **4/4 cas passés**, nouvelle vérification
   `check_structured_matches_scoring` (compare `structured.matches/gaps/
   uncertain_flags` à `ScoringResult` du même run) **passée sur les 4 cas,
   aucune divergence** — la garantie de fidélité tient en pratique, pas
   seulement en théorie.
2. **Échantillon de 12 offres réelles régénérées** via l'orchestrateur complet
   (offres 1, 7, 15, 18, 19, 24, 38, 50, 57, 94, 96, 148 — couvrant
   `rhone_alpes`, `autre_france`, `suisse_romande`) : **0 échec**.
   - Qualité du markdown préservée : **4/4 sections présentes sur les 12**,
     **zéro mention de mobilité sur les 12** (y compris toutes les offres
     `rhone_alpes`/`autre_france` de l'échantillon, où c'est interdit).
   - Fidélité vérifiée offre par offre : le compte `gaps=N, uncertain_flags=N`
     déjà loggé par l'orchestrateur (`scoring_result.gaps`/`.uncertain_flags`,
     donnée de `ScoringResult`) correspond **exactement** au compte dans
     `structured_analysis_<id>.json` sur les **12/12 offres** — preuve directe
     que la sortie structurée reflète bien ce que le scoring a décidé, pas une
     réinterprétation.
   - Offre 24 (cas de référence ISO 13485 du correctif post-session 3) :
     `structured_analysis_24.json` contient bien le gap "ISO 13485"/QMS et le
     flag incertain correspondant — le comportement honnête du correctif
     post-session 3 traverse intact la nouvelle couche structurée.
   - Note sur les comptes historiques : la consigne demandait de vérifier
     "offre 24 : 4 gaps + 1 incertain" et "offre 7 : 4 gaps + 1 incertain"
     (valeurs de la session 4). En pratique cette régénération donne offre 24
     = 5 gaps + 1 incertain, offre 7 = 2 gaps + 1 incertain : le scoring
     rappelle réellement le LLM (`score_offer`), qui n'est pas déterministe
     d'un run à l'autre — chaque régénération est un nouveau jugement, pas un
     rejeu figé. Documenté honnêtement plutôt que forcé pour coller aux
     chiffres historiques ; ce qui compte et qui a été vérifié à chaque run,
     c'est que `structured` == `ScoringResult` **du même run**, propriété
     confirmée 12/12.
3. **Dashboard retesté avec Playwright headless contre le nouveau schéma**
   (16 vérifications automatisées) : offre 24 affiche "Points forts (✓ 10)",
   "Gaps confirmés (✕ 5)", "Flags incertains (? 1)" directement depuis l'API
   structurée, mention ISO 13485/QMS visible ; offre `nouveau` (non scorée)
   toujours rendue sans erreur JS ; une offre pas encore régénérée (parmi les
   55 restantes au moment du test) affiche bien "—" pour ses compteurs plutôt
   qu'une exception — confirmé par capture d'écran.
4. **Backfill complet des offres historiques restantes** : les 55 offres au
   statut `analyse` sans `structured_analysis_<id>.json` ont été régénérées
   via l'orchestrateur pour une couverture complète du jeu de données —
   **55/55 réussies, 0 échec**. Base finale : **67/67 offres avec
   `structured_analysis_<id>.json`** (12 de l'échantillon initial + 55 du
   backfill).
   - **Vérification systématique sur les 67 offres** (pas un sous-ensemble) :
     fidélité structurée/scoring **0 divergence sur 67/67**, et **4/4
     sections markdown présentes sur 67/67**.
   - **Vérification anti-mobilité sur les 67 offres, 4 alertes trouvées et
     analysées individuellement** (offres 8, 12, 16, 75, zones `rhone_alpes`) :
     après lecture du contexte réel, ce sont des **faux positifs du grep de
     détection**, pas des violations de la règle CLAUDE.md — le grep (déjà
     volontairement large dans `tests/test_generation.py`, sans limite de
     mot) matche du vocabulaire métier légitime sans rapport avec la mobilité
     personnelle du candidat : offre 12 est une offre du secteur transport
     (le gap listé est littéralement "écosystèmes de transport et mobilité",
     le domaine métier de l'offre, pas la mobilité du candidat) ; offres 8/75
     mentionnent "environnement international"/"contexte international"
     comme gap de compétence (travail en contexte international), pas comme
     projet de relocalisation. Aucune des 4 alertes ne correspond à une
     mention du projet personnel de mobilité du candidat — limite
     préexistante du grep de détection (non liée à ce correctif, la même
     regex existait déjà dans `tests/test_generation.py` avant cette
     session), documentée ici par transparence plutôt que passée sous
     silence.

**Avant/après :**
| | Avant correctif | Après correctif |
|---|---|---|
| Source des compteurs gaps/matches/uncertain | Reparsing du markdown (regex sur puces, sensible au style de sortie LLM) | `structured_analysis_<id>.json`, construit en Python depuis `ScoringResult` |
| Divergence scoring/dashboard possible | Oui en théorie (jamais observée en pratique, mais non garantie) | Non — garantie par construction, pas par test |
| Coût LLM additionnel | 0 | 0 (aucun appel supplémentaire) |
| Information affichée pour un match | Résumé de la première puce de prose uniquement | Libellé + justification pour CHAQUE match (`matches` complet) |
| Fallback silencieux sur l'ancien parsing | N/A | Aucun — fonctions supprimées, pas conservées "au cas où" |

## Correctif post-session 9 (2026-07-12) : baseline de bruit RAG calculée dynamiquement

**Problème :** `NOISE_THRESHOLD = 0.75` était une constante en dur dans
`scoring/agent.py`, calibrée une fois en session 2 sur un profil de 31
chunks et le modèle `paraphrase-multilingual-mpnet-base-v2`. Rien ne
garantissait sa validité si le profil grossissait ou si le modèle
d'embedding changeait à nouveau (ça avait déjà été le cas une fois, voir
session 2 : passage de `all-MiniLM-L6-v2` à ce modèle).

**Implémentation :**
- `scoring/embeddings/index.py` — `NOISE_PROBE_QUERIES` : 5 requêtes
  hors-sujet et variées (cuisine "recette de tarte aux pommes" — le probe
  original de session 2, gardé pour la continuité historique —, météo,
  sport, actualités, jardinage), délibérément dans des domaines différents
  plutôt qu'une seule requête : une requête isolée risque de tomber par
  hasard proche du vocabulaire du profil (constaté empiriquement, voir plus
  bas — "météo à Paris" est tombée à 0.59 de distance, bien en dessous des
  autres probes, par pure coïncidence lexicale).
- `_compute_noise_baseline(collection)` : interroge la collection fraîchement
  construite avec ces 5 probes, calcule la **médiane** (pas la moyenne) des
  meilleures distances. Médiane choisie car robuste à UN probe aberrant sur
  cinq échantillons (le cas du probe météo ci-dessus) — une moyenne aurait
  été tirée vers le bas par cet unique outlier, sous-estimant le vrai
  plancher de bruit.
- Persistance dans `scoring/embeddings/chroma/noise_baseline.json` (fichier
  JSON simple à côté de l'index, pas une collection ChromaDB dédiée — c'est
  un unique scalaire, pas des données vectorisables, un fichier est plus
  simple). Recalculée à CHAQUE appel de `build_index()`, donc à chaque
  rebuild d'index (local, Docker, GitHub Actions — les trois chemins
  appellent déjà `scoring.embeddings.build`, aucun câblage CI supplémentaire
  nécessaire). Le fichier vit dans `chroma/`, déjà gitignoré : c'est un
  artefact de build régénérable à l'identique depuis les fichiers source du
  profil, pas une donnée à versionner.
- `get_noise_threshold()` lit ce fichier au runtime et retourne
  `median_distance × NOISE_THRESHOLD_SAFETY_MARGIN` (0.85). **Raisonnement
  du facteur 0.85** : la baseline mesurée est le PLANCHER de bruit (distance
  où atterrissent des requêtes non liées), pas la frontière entre signal et
  bruit — l'utiliser telle quelle flaguerait comme "peut-être un match" tout
  probe de bruit qui tombe un peu mieux que la moyenne. L'écart empirique
  déjà observé en session 2 entre vrais matches (~0.33-0.65) et bruit
  (~0.85) donne un ratio 0.75/0.85 ≈ 0.88, proche de 0.85 — ce facteur
  reproduit donc approximativement l'ancien seuil fixe sur le profil/modèle
  actuels, tout en restant une fraction relative valable si le profil ou le
  modèle change à nouveau, plutôt qu'un nombre recalibré à la main à chaque
  fois.
- **Repli sur l'ancien seuil fixe (0.75)** si aucune baseline n'est
  disponible : fichier absent (ancien index jamais reconstruit avec cette
  fonctionnalité), JSON corrompu, ou clé manquante — capturé explicitement
  (`FileNotFoundError`, `json.JSONDecodeError`, `KeyError`, `ValueError`),
  jamais d'exception non gérée qui ferait planter le scoring pour une
  raison aussi accessoire qu'un fichier de métadonnées manquant.
- `scoring/agent.py` : `get_noise_threshold()` appelé UNE FOIS par
  `score_offer()` (pas au niveau module, pas par requête RAG individuelle)
  — reflète un rebuild d'index survenu en cours de vie du process sans
  nécessiter de redémarrage, sans payer le coût d'une lecture disque par
  atome recherché (jusqu'à 50+ appels RAG par offre).

**Tests réels effectués (pas de simulation) :**

1. **Baseline calculée sur le profil réel actuel (30 chunks)** :
   médiane = **0.7881** (probes individuels : tarte aux pommes 0.8324,
   météo 0.5927, football 0.7881, actualités 0.6575, jardinage 0.8256).
   Seuil dynamique résultant : **0.6699** (0.7881 × 0.85).
2. **Comparaison avec le seuil fixe de session 2 (0.75)** : le nouveau seuil
   dynamique (0.6699) est **notablement plus strict**, pas juste une
   variation d'arrondi. Explication : la baseline de session 2 avait été
   estimée à l'œil sur un seul probe ("tarte aux pommes" ≈ 0.85) sur un
   profil légèrement différent (31 chunks vs 30 aujourd'hui, contenu
   modifié depuis) ; la médiane sur 5 probes variés révèle une distribution
   de bruit plus large et surtout un cas (météo, 0.59) où le "bruit" tombe
   dangereusement proche de la zone des vrais matches — un seul probe ne
   pouvait pas capturer cette variance. Le nouveau seuil est donc plus
   conservateur par construction, pas par accident.
3. **Revalidation sur offre 24 (cas de référence ISO 13485, correctif
   post-session 3)** : régénérée avec le nouveau seuil dynamique. Le gap
   ISO 13485 (atome individuel à distance 0.7625) est **toujours
   correctement flagué incertain** — au-dessus du nouveau seuil (0.6699)
   comme de l'ancien (0.75). Un second flag incertain est apparu
   ("tableaux de bord", atome à distance 0.7165) : analyse détaillée de la
   trace RAG a confirmé que ce n'est **pas un faux positif** mais une
   détection plus fine — cet atome isolé retrouve en meilleur match
   `skills_notions_seulement` (le chunk du profil explicitement dédié aux
   compétences à l'état de notions, pas maîtrisées), un match objectivement
   faible que l'ancien seuil 0.75 était trop permissif pour capter. Sur les
   55 requêtes RAG de l'offre 24, seules ces 2 atomes dépassent le nouveau
   seuil — tout le reste (machine learning à 0.19, modélisation prédictive à
   0.38, etc.) reste confortablement en dessous.
4. **Vérification anti-faux-positif sur les compétences bien établies**
   (`search_profile_with_scores` direct, hors pipeline complet) : "churn
   model" (0.60), "Power BI" (0.34), "SQL avancé" (0.26), "Snowflake ETL"
   (0.37), "recall 85%" (0.51) — toutes largement sous le nouveau seuil
   0.6699, aucune ne bascule en incertain.
5. **Régénération offres 7 et 15** (mêmes offres que les tests
   post-session-3/4) pour vérifier l'absence de nouveaux faux positifs à
   plus large échelle : offre 15 → 0 flag incertain (matchs propres) ;
   offre 7 → 2 flags incertains (intégration ERP/MES, détection de dérives
   / modèles de scoring), vérifiés individuellement via
   `search_profile_with_scores` — ERP/MES n'apparaît nulle part dans le
   profil (distance 0.64-0.71 sur les meilleurs chunks trouvés, aucun
   rapport réel), donc un flag honnête, pas un faux positif.
6. **Test de robustesse — profil élargi, recalcul automatique sans
   intervention manuelle** : ajout temporaire d'un fichier
   `_test_expansion.md` avec 5 chunks synthétiques (DevOps, NLP, finance
   quantitative, mobile, big data — domaines choisis pour être distincts du
   profil réel), rebuild de l'index. Résultat : `profile_chunk_count` passe
   correctement de 30 à 35, médiane recalculée automatiquement de 0.7881 à
   **0.7730**, seuil résultant de 0.6699 à **0.6571** — sans modifier une
   seule ligne de code, uniquement en relançant `scoring.embeddings.build`.
   Fichier de test supprimé et index reconstruit sur le profil réel (30
   chunks) après validation.
7. **Test du repli sur seuil fixe**, 3 scénarios de panne simulés
   individuellement puis restaurés : fichier de baseline absent
   (`FileNotFoundError`), JSON corrompu (`JSONDecodeError`), clé
   `median_distance` manquante (`KeyError`) — **les 3 cas retournent
   proprement 0.75** avec un warning loggé, jamais d'exception qui
   remonterait jusqu'au scoring.

**Avant/après :**
| | Avant correctif | Après correctif |
|---|---|---|
| Source du seuil de bruit | `NOISE_THRESHOLD = 0.75`, constante en dur | `get_noise_threshold()`, lu depuis `noise_baseline.json`, recalculé à chaque build d'index |
| Sensibilité à la taille du profil | Aucune — même seuil quel que soit le nombre de chunks | Recalculée automatiquement (vérifié : 30→35 chunks, seuil ajusté sans intervention) |
| Sensibilité à un changement de modèle d'embedding | Aucune — seuil resterait figé à 0.75 même avec un modèle différent | Recalculée automatiquement au prochain build (le modèle fait partie de la baseline persistée) |
| Comportement si baseline indisponible | N/A | Repli sur 0.75, jamais de crash (3 scénarios de panne testés) |
| Seuil actuel (profil réel, 30 chunks) | 0.75 (fixe) | 0.6699 (dynamique) — plus strict, détection plus fine confirmée sur offre 24 |
| Offres déjà scorées (67 en base) | Scorées avec 0.75 | Inchangées (décision : pas de backfill systématique cette fois, seules 7/15/24 régénérées pour la validation demandée) — le nouveau seuil s'applique automatiquement à toute nouvelle offre via le prochain run GitHub Actions ou `/analyze` |

## Correctif post-session 9 (2026-07-13) : ergonomie du dashboard — accordéon + lien offre originale

**Problème signalé après usage réel avec les 67 offres en base :**
1. Le clic sur une ligne affichait le détail dans un panneau fixe SOUS le
   tableau entier — avec 67 lignes, cliquer sur une offre en haut de liste
   obligeait à scroller jusqu'en bas pour voir son détail.
2. L'URL Hellowork de l'offre (`jobs.url`, en base depuis la session 1)
   n'apparaissait nulle part dans le dashboard.

**1. Accordéon — implémentation :**
- `api/static/index.html` : suppression de la section `<section
  id="detail-panel">` fixe en bas de page.
- `api/static/dashboard.js` — `renderTable()` insère désormais une
  `<tr class="detail-row">` (une seule cellule `colspan="6"`) **directement
  après** la ligne de l'offre développée (`expandedOfferId`), pas ailleurs
  dans le DOM. `selectOffer(offerId)` implémente le bascule : même offre
  reclique → `expandedOfferId = null` (ferme) ; offre différente →
  remplace `expandedOfferId` (ferme l'ancienne, ouvre la nouvelle à sa
  position). Un seul `renderTable()` complet à chaque clic reconstruit tout
  le tableau avec la ligne de détail à la bonne position — plus simple et
  plus robuste que d'essayer de déplacer un élément DOM existant, au prix
  de reconstruire les lignes déjà affichées (négligeable avec 67 lignes).
- `api/static/dashboard.css` : le panneau de détail vit maintenant dans une
  `<td>` de la table (`tr.detail-row > td { padding: 0; }`, le vrai padding
  déplacé sur `.detail-panel` à l'intérieur) plutôt que dans une `<section>`
  de page — mêmes règles de style pour le contenu (`h2`, `dl`, `ul`,
  `.full-link`), seul le conteneur change.

**2. Lien vers l'offre originale :**
- **Déjà exposé côté API** : `OfferDetailResponse.url` (session 6) était
  déjà rempli depuis `jobs.url` par `_load_offer_row` dans `api/main.py` —
  aucune modification nécessaire côté `api/schemas.py`/`api/main.py`, c'est
  bien de l'exposition, la donnée existait déjà bout en bout. Le manque
  était uniquement côté frontend : `dashboard.js` ne lisait/affichait
  jamais ce champ.
- `originalOfferLinkHtml(detail)` (dashboard.js) : lien `<a
  target="_blank" rel="noopener">Voir l'offre originale ↗</a>`, positionné
  juste sous le titre de l'offre dans le panneau (première ligne visible du
  détail, avant même les métadonnées zone/statut) — visible sans avoir à
  chercher.

**Tests réels effectués (Playwright headless, 18 vérifications automatisées,
contre les 67 offres réelles de la base — pas de mock) :**

1. **Position HAUT de liste** (1ère ligne) : détail apparaît, et
   vérification structurelle forte — le `nextElementSibling` de la ligne
   cliquée dans le DOM est bien la ligne de détail (`data-detail-for`
   correspondant), pas juste "quelque part dans la page". Reclic sur la
   même ligne → ligne de détail disparaît du DOM.
2. **Position MILIEU de liste** (ligne ~34/67) : détail apparaît ; vérifié
   par mesure de `bounding_box()` que le panneau de détail est positionné
   pixel-perfect juste sous la ligne cliquée (delta < 5px), pas ailleurs sur
   la page — capture d'écran à l'appui.
3. **Changement de sélection** : clic sur une offre différente pendant
   qu'une autre est ouverte → l'ancienne ligne de détail disparaît du DOM
   AVANT que la nouvelle n'apparaisse (vérifié : jamais plus d'une
   `tr.detail-row` présente simultanément, y compris pendant la transition).
4. **Position BAS de liste** (dernière ligne) : détail apparaît
   correctement, ferme bien la précédente ouverture.
5. **Lien offre originale** : présent dans le panneau, URL réelle
   `https://www.hellowork.com/fr-fr/emplois/80521087.html` (pas un
   placeholder), `target="_blank"`. **Test de clic réel** (pas juste
   inspection des attributs) : `page.expect_popup()` + clic effectif sur le
   lien → un nouvel onglet s'ouvre réellement, chargé sur la vraie URL
   Hellowork.
6. **Aucune régression** : 0 erreur console JS sur l'ensemble du parcours de
   test (chargement initial + 5 ouvertures/fermetures d'accordéon + 1 clic
   de lien externe).

**Captures d'écran** (comportement réel, pas de maquette) : accordéon ouvert
sur la 3e ligne de la liste (lien "Voir l'offre originale" visible juste
sous le titre) et sur une ligne au milieu de la liste (les lignes suivantes
poussées vers le bas, pas de scroll nécessaire pour voir le détail juste
après avoir cliqué).

**Avant/après :**
| | Avant correctif | Après correctif |
|---|---|---|
| Position du panneau de détail | Fixe, en bas de page (après les 67 lignes) | Inséré juste sous la ligne cliquée, à sa position exacte dans le tableau |
| Scroll nécessaire pour voir le détail (offre en haut de liste) | Oui, jusqu'en bas de la page | Non, visible immédiatement |
| Comportement au clic sur une 2e offre | Contenu du panneau remplacé, toujours en bas | Ancienne ligne de détail fermée, nouvelle ouverte à sa propre position |
| Lien vers l'offre originale | Absent du dashboard | Visible en première ligne du panneau, cliquable, nouvel onglet — testé avec navigation réelle |

## Session 10 (2026-07-13) : préparation du déploiement Render + correctif API_MODE=readonly

**Objectif initial :** déployer l'API/dashboard sur Render avec redéploiement
automatique déclenché par les commits du bot GitHub Actions (session 8).

**Deux bugs réels trouvés en préparant le déploiement (pas des suppositions
— vérifiés par un vrai `docker build` avec un Dockerfile de diagnostic) :**

1. `.dockerignore` excluait `storage/jobs.db` (règle `*.db`/`storage/*.db`
   héritée de la session 7, jamais mise à jour après la session 8 qui a
   pourtant ajouté l'exception correspondante dans `.gitignore`). Un
   `docker build` réel confirmait `JOBS_DB_MISSING` dans l'image — un
   déploiement Render serait parti d'une base vide malgré les 67 offres
   déjà versionnées dans le repo.
2. `.dockerignore` excluait aussi `orchestrator/runs/` (339 fichiers
   analyses + traces, versionnés depuis la session 8) — même symptôme :
   dashboard avec scores/statuts corrects mais tous les panneaux de détail
   vides sur un déploiement frais.

**Corrigé** dans `.dockerignore` : exception `!storage/jobs.db` (miroir
exact de `.gitignore`), suppression de la ligne excluant
`orchestrator/runs/`. Revérifié par un second `docker build` de diagnostic :
`JOBS_DB_PRESENT`, 339 fichiers dans `orchestrator/runs/` présents.

**Adaptations du Dockerfile pour Render :**
- Render fixe `$PORT` à l'exécution (10000 par défaut) et exige que le
  conteneur écoute EXACTEMENT ce port sur `0.0.0.0` — le `CMD` figé sur
  `--port 8000` aurait fait échouer la détection de port par Render. Changé
  en `ENV PORT=8000` (valeur par défaut pour `docker run`/`docker-compose`
  sans variable positionnée, comportement local inchangé) + `CMD exec
  uvicorn ... --port "${PORT}"` (forme shell, pas la forme exec-array —
  nécessaire pour que `${PORT}` soit interpolé au démarrage). Le `exec`
  explicite fait remplacer le shell par le process uvicorn lui-même plutôt
  que de le garder comme enfant : sans ça, un `SIGTERM` de Render (à chaque
  redéploiement) n'atteindrait jamais uvicorn, qui ne s'arrêterait proprement
  qu'après le timeout de force-kill. Vérifié directement via `docker top` :
  uvicorn tourne bien comme PID direct de l'entrypoint, pas sous un
  `/bin/sh -c` intermédiaire.
- `HEALTHCHECK` du Dockerfile mis à jour pour utiliser `${PORT}` aussi (reste
  utile pour `docker-compose` local ; Render ignore l'instruction Docker
  `HEALTHCHECK` et fait son propre polling HTTP contre `healthCheckPath`,
  voir `render.yaml`).
- Render ne lit pas `docker-compose.yml` ni le `HEALTHCHECK` du Dockerfile —
  la configuration Render se fait via `render.yaml` (Blueprint) ou
  directement dans le dashboard Render.

**Problème découvert en testant le déploiement Render (bloquant, signalé
avant de continuer) :** mesure réelle via `docker stats` sur le conteneur
"full" (comportement identique à avant cette session) : **~749MB-921MB RAM
au repos** (sentence-transformers + torch chargés par le singleton de
session 6). Les tiers Free ET Starter (7$/mo) de Render plafonnent tous les
deux à 512MB — insuffisant sur les deux. Seul le tier Standard (25$/mo,
2GB) tiendrait "full" tel quel. Décision (validée avec l'utilisateur) :
ne pas payer plus cher, mais séparer les deux usages réels de l'API selon
l'environnement — Render n'a jamais besoin de faire tourner le RAG, ce
travail est déjà fait par GitHub Actions (session 8).

**Correctif — API_MODE=readonly|full :**
- `api/main.py` : `API_MODE = os.environ.get("API_MODE", "full")`, avec
  repli sur `"full"` si la valeur est inconnue (jamais de crash pour une
  variable mal orthographiée — comportement local/Docker-compose/CI
  inchangé, ces environnements ne positionnent jamais cette variable).
- **La vraie source d'économie mémoire n'est pas le blocage de l'endpoint en
  façade, mais l'endroit où l'import a lieu.** `orchestrator.agent` importe
  `scoring.agent` au niveau module, qui importe
  `scoring.embeddings.index` (chromadb + sentence-transformers + torch) —
  donc un simple `from orchestrator.agent import process_offer` en haut de
  `api/main.py`, même jamais appelé, charge torch en mémoire dès l'import du
  module. Les imports de `orchestrator.agent`/`orchestrator.run` sont donc
  déplacés à l'intérieur du handler `/analyze` lui-même (import différé),
  exécutés seulement si `API_MODE != "readonly"`. Même chose pour
  `get_embedding_function`/`get_client` (déplacés dans `lifespan`, appelés
  seulement hors readonly) et `is_initialized` (déplacé dans le handler
  `/health`, appelé seulement hors readonly).
- **Vérifié directement via `sys.modules`** (pas une simple lecture de
  code) : `import api.main` avec `API_MODE=readonly` positionné →
  `'torch' in sys.modules`, `'chromadb' in sys.modules`,
  `'sentence_transformers' in sys.modules` tous `False`. En mode `full`
  (défaut), toujours `False` à l'import du module (le chargement reste
  différé dans `lifespan`, comportement de la session 6 inchangé) puis
  `True` une fois le serveur démarré.
- `GET /health` : `embeddings_loaded` devient `bool | None` — `null` en mode
  readonly plutôt qu'un faux `False` qui ferait passer le check en
  `"degraded"` (503) alors que le modèle n'est jamais censé être chargé dans
  ce mode. Le calcul de `all_ok` exclut explicitement ce check quand il vaut
  `None` (pas applicable, pas un échec). `is_initialized()` n'est même pas
  importé en mode readonly, pour ne pas tirer chromadb/torch en mémoire rien
  que pour répondre à un ping de santé.
- `POST /analyze` : renvoie **503 Service Unavailable** en mode readonly,
  avec un message explicite ("Scoring désactivé sur ce déploiement... géré
  par GitHub Actions... consultez GET /offers..."). **503 choisi plutôt que
  409** : ce n'est pas un conflit d'état sur la ressource (l'`offer_id`, le
  corps de requête) comme le suggérerait 409 — c'est une caractéristique
  permanente de CE déploiement (le scoring est le travail de GitHub Actions,
  pas de ce déploiement en lecture seule), ce que 503 communique
  correctement pour un endpoint légitimement indisponible ici.
- `docker/entrypoint.sh` : en `API_MODE=readonly`, l'étape de construction
  de l'index ChromaDB est sautée entièrement (jamais interrogée dans ce
  mode, la construire consommerait CPU/temps/RAM pour rien).

**Tests réels effectués (pas de simulation) :**

1. **Import direct, mode readonly** : `torch`/`chromadb`/
   `sentence_transformers` absents de `sys.modules` après `import api.main`
   avec `API_MODE=readonly` — preuve directe que l'économie mémoire vient
   bien de l'endroit où l'import a lieu, pas juste d'un blocage de façade.
2. **Serveur local readonly, 4 endpoints testés** : `GET /health` → `200
   {"embeddings_loaded": null, ...}` ; `GET /offers` → 67 offres réelles ;
   `GET /offers/24` → détail réel (score, matches, gaps) ; `GET
   /offers/99999` → 404 ; `POST /analyze` → **503** avec le message attendu.
   Logs serveur vérifiés sans traceback.
3. **Serveur local mode full (non-régression)** : `GET /health` →
   `embeddings_loaded: true` ; `POST /analyze` sur une offre réelle (148) →
   pipeline complet exécuté (vrai appel Mistral, vrai RAG), `200` avec
   analyse complète — comportement identique à avant cette session.
4. **Conteneur Docker réel, mode readonly** : temps de démarrage mesuré
   (container start → `/health` répond) : **~1.7s** (contre ~29.8s en mode
   full, mesuré dans la même session avant ce correctif — voir plus bas).
   Mémoire au repos mesurée via `docker stats` : **~58MB** (contre
   ~749-921MB en mode full). Logs de l'entrypoint confirmant le skip de
   construction d'index. `GET /offers` → 67 offres, `POST /analyze` → 503 —
   comportement identique au test local, cette fois dans les conditions
   réelles du déploiement (image buildée, pas de volume persistant).
5. **Conteneur Docker réel, mode full (non-régression post-changement
   d'imports différés)** : `embeddings_loaded: true`, index reconstruit
   normalement au démarrage — aucune régression introduite par le
   déplacement des imports.

**Mesures de démarrage/latence (toutes réelles, container Docker, pas de
volume persistant — simule l'environnement Render où le filesystem repart de
zéro à chaque déploiement) :**

| | Mode `full` | Mode `readonly` |
|---|---|---|
| Temps de démarrage (container start → `/health` répond) | ~29.8s | **~1.7s** |
| Détail du temps de démarrage | ~15.4s construction index + ~14s chargement modèle (lifespan) — les deux étapes rechargent indépendamment le modèle car ce sont deux process séparés (`python -m scoring.embeddings.build` en sous-process de l'entrypoint, puis le process uvicorn lui-même), le singleton de session 6 ne peut pas partager d'état entre les deux | Aucune des deux étapes ne s'exécute |
| RAM au repos | ~749-921MB (mesuré à deux moments différents, cohérent avec le même ordre de grandeur) | **~58MB** |
| Tient dans le tier Free Render (512MB) ? | Non | **Oui, large marge** |
| Tient dans le tier Starter Render (512MB, 7$/mo) ? | Non | **Oui, large marge** |

**Limite non résolue, notée pour référence :** en mode `full`, la
construction de l'index (`scoring.embeddings.build`, sous-process de
l'entrypoint) et le chargement du singleton d'embeddings par `lifespan`
(process uvicorn) chargent chacun leur propre instance du modèle
sentence-transformers, doublant le coût des ~12-14s de vérification de
cache HuggingFace Hub. Une optimisation possible serait de partager l'état
entre les deux (ex: construire l'index directement dans le process uvicorn
au lieu d'un sous-process séparé) — non traité cette session, hors périmètre
du correctif readonly qui ne modifie pas le chemin `full`.

## Procédure de déploiement Render

**1. Créer le compte / connecter le repo**
- Créer un compte sur render.com (ou se connecter avec le compte GitHub).
- "New +" → "Blueprint" → sélectionner le repo `Ayreon69/job-agent` (le
  dépôt privé créé en session 8) → Render détecte automatiquement
  `render.yaml` à la racine.

**2. Variables d'environnement**
- `API_MODE=readonly` est déjà fixé dans `render.yaml` (`envVars`), pas
  besoin de le ressaisir.
- `MISTRAL_API_KEY` : marqué `sync: false` dans `render.yaml` — Render
  demande sa valeur dans le dashboard au moment de la création du service
  (onglet "Environment"), jamais committée dans le repo. Techniquement non
  utilisée par aucun endpoint en mode readonly (POST /analyze est
  désactivé), mais la renseigner évite que `GET /health` rapporte
  `mistral_key_present: false` de façon trompeuse sur un déploiement qui n'en
  a simplement jamais besoin.

**3. Activer le déploiement automatique**
- Déjà configuré dans `render.yaml` via `autoDeployTrigger: commit` — se
  déclenche sur chaque push vers la branche connectée, y compris les commits
  du bot `job-agent-bot` (workflow GitHub Actions de la session 8) qui
  pousse `storage/jobs.db` + `orchestrator/runs/` après chaque scrape. Une
  nouvelle offre scrapée un matin apparaît donc sur le dashboard en ligne
  sans étape manuelle.
- Vérifiable/modifiable après coup dans le dashboard Render : Service →
  Settings → Build & Deploy → "Auto-Deploy".

**4. Health check**
- `healthCheckPath: /health` déjà configuré dans `render.yaml` — Render
  interroge cet endpoint avant de router le trafic vers un nouveau déploiement
  (déploiement sans interruption). `/health` répond déjà `200`/`503` de
  façon cohérente en mode readonly (voir plus haut), aucun changement
  nécessaire côté endpoint pour ce point.

**5. Limite connue à surveiller après le premier déploiement réel**
- Le tier `free` de Render **met le service en veille après 15 minutes
  d'inactivité** et le redémarre à la prochaine requête (cold start Render,
  généralement 30-50s selon la documentation Render — non mesuré ici, propre
  à l'infrastructure Render et pas reproductible en local). Combiné au
  démarrage applicatif mesuré ci-dessus (~1.7s en mode readonly), le premier
  chargement du dashboard après une période d'inactivité prend donc
  approximativement **30-50s (cold start Render) + ~2s (démarrage
  applicatif) ≈ 30-52s** au total — à vérifier avec une mesure réelle une
  fois le service effectivement déployé sur Render (cette session prépare et
  teste tout le code/la configuration nécessaires, mais la création du
  service Render lui-même et la mesure du cold start réel restent une étape
  manuelle, hors de portée d'un agent sans accès au compte Render de
  l'utilisateur).

**Fichiers :** `render.yaml` (nouveau), `.dockerignore` (correctif
`storage/jobs.db` + `orchestrator/runs/`), `docker/Dockerfile` ($PORT
dynamique, exec signal handling), `docker/entrypoint.sh` (skip index en
readonly), `api/main.py` (API_MODE, imports différés), `api/schemas.py`
(`embeddings_loaded: bool | None`).

## Session 11 (2026-07-13) : jobup.ch — Suisse romande, priorité géographique 1

**Objectif :** ajouter jobup.ch comme deuxième source de scraping, ciblée sur
la Suisse romande (Genève, Vaud, Neuchâtel) — la vraie priorité 1 de
CLAUDE.md, jamais testée de bout en bout jusqu'ici (tout le système n'avait
tourné que sur Rhône-Alpes via Hellowork depuis la session 1).

### Reconnaissance (avant tout code de production)

Un `web_fetch` exploratoire préalable avait montré que les paramètres
`term=`/`region=` devinés sur la page d'accueil ne filtraient PAS réellement
(41528 offres génériques retournées pour "data analyst" + Genève). Plutôt
que de deviner davantage, la vraie syntaxe a été découverte en pilotant
Playwright comme un utilisateur réel : remplissage du champ "Profession ou
mots-clés" (`#synonym-typeahead-text-field`) et du champ "Villes ou régions"
(`#location-typeahead-text-field`), sélection d'une vraie suggestion du
typeahead, clic sur "Recherche", puis lecture de l'URL résultante.

**Syntaxe réelle confirmée** (contraste net avec le résultat non filtré
initial — 22-24 offres réelles vs 41528) :
```
https://www.jobup.ch/fr/emplois/?location=<slug>&term=<query>&employment-type=<code>&page=<n>
```
- `location` : un slug de ville/canton que jobup résout lui-même via son
  typeahead (`genève`, `vaud`, `neuchâtel` — accentué, minuscule) — pas du
  texte libre ; une valeur non reconnue retombe silencieusement sur le
  listing national non filtré, exactement comme le devinage initial cassé.
  Confirmé directement navigable sans repasser par l'interaction JS à chaque
  fois (testé : navigation directe vers l'URL produit le même résultat
  filtré).
- `employment-type` : un code entier par type de contrat, non documenté
  nulle part et sans ordre logique évident — découvert en ouvrant le vrai
  panneau de filtre "Type de contrat" et en lisant l'URL produite par chaque
  case cochée : `Temporaire=1`, `Indépendant=2`, `Stage=3`, `Revenu
  complémentaire=4`, `Durée indéterminée=5`, `Apprentissage=6`. Plusieurs
  codes se combinent en répétant le paramètre (`&employment-type=1&employment-type=2&employment-type=5`),
  vérifié : 210 résultats = exactement 173+36+1 (comptes individuels des 3
  codes combinés).
- `page` : pagination 1-indexée, confirmée via les vrais liens de
  pagination sur une page de résultats large (367 offres).

**Structure de la page de résultats** (stable sur ~20 échantillons de
reconnaissance) :
- `[data-cy="serp-item"]` : une carte par offre.
- `[data-cy="job-link"]` : lien titre (le titre complet est dans l'attribut
  `title`, pas seulement le texte visible parfois tronqué).
- Champs en paires de lignes texte brut : `"Lieu de travail:"` / valeur,
  `"Taux d'activité:"` / valeur, `"Type de contrat:"` / valeur — **pas
  systématiquement présents** : les gros employeurs (CERN, UNICEF,
  SonarSource) omettent parfois complètement `"Type de contrat:"` et/ou
  `"Taux d'activité:"`, contrairement à Hellowork où chaque carte a toujours
  les mêmes champs. Le parsing tolère l'absence d'un label plutôt que de
  supposer une position fixe.
- `[data-cy="vacancy-description"]` sur la page de détail : sélecteur fiable
  pour la description complète.
- Date de publication : premier motif "DD mois AAAA" absolu dans le texte de
  la page de détail (ex: "25 juin 2026"), apparaît juste après le titre —
  plus fiable que le texte relatif de la carte ("Il y a 3 semaines").

### Adaptation du vocabulaire de recherche

Les requêtes par défaut de Hellowork ont été testées telles quelles sur
jobup avant d'être copiées aveuglément : `"data scientist"` (14 résultats) et
`"data analyst"` (24 résultats) fonctionnent identiquement, mais
**`"IA générative agent LLM"` retourne ZÉRO résultat** sur jobup (phrase
française trop spécifique pour son moteur de recherche, contrairement à
Hellowork). Remplacée par `"intelligence artificielle"` (12 résultats
confirmés), le vocabulaire le plus proche que jobup résout réellement — testé
et confirmé non vide avant adoption, pas supposé équivalent.

### Scraper (scraper/jobup.py)

Même structure que `scraper/hellowork.py` (dataclass `JobListing`,
`search_jobs`/`fetch_job_detail`/`scrape`). `source='jobup'` dans le schéma
`storage/db.py` existant (`UNIQUE(source, source_id)` déjà conçu pour
plusieurs sources). Cible Genève/Vaud/Neuchâtel uniquement — jamais
Zurich/Berne/Bâle, cohérent avec `check_geography_rules` (`suisse_autre`,
priority_rank 4, la zone la plus basse des quatre zones classées).

`scrape()` déduplique par `source_id` à travers les régions AVANT de
récupérer les détails (une offre à Genève peut apparaître aussi dans une
recherche Vaud si les index de jobup se chevauchent géographiquement) — évite
de fetcher/stocker la même offre deux fois dans un seul appel.

**Filtre de contrat en deux couches**, pas une seule :
1. `employment-type` au niveau URL (couche principale, comme Hellowork) :
   inclut Temporaire/Indépendant/Durée indéterminée, exclut Stage/
   Apprentissage/Revenu complémentaire.
2. **Filet de sécurité sur le titre** (`_looks_like_internship`), ajouté
   après un test réel : 3 offres sur 34 scrapées avaient un titre
   explicitement "Stagiaire"/"Internship" mais un `employment-type` mal
   classé par jobup lui-même comme "Temporaire" ou "Durée indéterminée" (pas
   "Stage") — un vrai défaut de qualité des données côté jobup, pas un bug
   du filtre URL. Regex `\b(stagiaire|stage|internship|intern)\b` avec
   limites de mot, vérifiée sans faux positif sur les 34 offres réelles
   (ex: "International Business Analyst" ne matche pas).

### Bug réel découvert et corrigé : couverture géographique Suisse romande incomplète

**Le test de bout en bout demandé a révélé un vrai bug préexistant**, jamais
détecté avant parce que jobup.ch (la vraie source de la priorité 1) n'avait
jamais été scrapée : `SUISSE_ROMANDE_VILLES` dans `scoring/geography.py` ne
contenait qu'une liste fermée de grandes villes (Genève, Lausanne,
Neuchâtel, Yverdon, Nyon, Vevey, Montreux, Fribourg, Sion) — sans mécanisme
de repli comme le code département pour Rhône-Alpes. Sur les 34 offres
réelles scrapées, **4 (Gland, Renens VD, Palézieux, Marin-Epagnier NE)
étaient mal classées `autre_france`** au lieu de `suisse_romande` —
appliquant à tort la règle "zéro mobilité" pensée pour la France à des
offres suisses, et leur retirant la priority_rank 1.

**Corrigé** dans `scoring/geography.py` :
- Ajout des villes réelles manquantes à `SUISSE_ROMANDE_VILLES` (Gland,
  Renens, Palézieux, Marin-Epagnier, + Morges/Rolle/Aigle/Bulle/Delémont/La
  Chaux-de-Fonds/Le Locle en prévision — mêmes cantons, pas encore vues dans
  une offre réelle mais du même type de gap).
- **Nouveau mécanisme de repli générique** : `SUISSE_ROMANDE_CANTON_ABBR_RE`
  détecte l'abréviation cantonale suisse telle qu'utilisée par jobup (ex:
  "Renens VD", "Marin-Epagnier (NE)") — VD/NE/GE/FR/VS — même principe que
  le repli département pour Rhône-Alpes, pour ne pas devoir énumérer toutes
  les communes vaudoises/neuchâteloises/genevoises/fribourgeoises/
  valaisannes existantes. Matché sur le texte BRUT (pas la version
  normalisée en minuscules, où "ne" en minuscule serait un simple fragment
  de mot français) — vérifié qu'une ville alémanique connue (ex: "Winterthur
  ZH") reste classée `suisse_autre` via la liste de villes AVANT que le
  repli cantonal romand ne soit même consulté (ordre de priorité préservé).

**Revalidation complète** : les 34/34 offres jobup réelles reclassées
`suisse_romande` après correctif (0 restant en `autre_france`). Les 11 cas
originaux de `check_geography_rules_spec.md` toujours corrects (aucune
régression) + 6 nouveaux cas ajoutés à `tests/test_geography.py`
(17/17 passés).

### Intégration

- `scraper/run.py` réécrit pour supporter `--source hellowork|jobup|both`
  (défaut `both`) — une seule invocation lance les deux sources séquentiellement.
  `hellowork.py` exporte désormais aussi `DEFAULT_JOB_QUERIES` (auparavant
  seulement dans l'ancien `run.py`), symétrique à `jobup.DEFAULT_QUERIES`.
- `.github/workflows/scrape-and-score.yml` : aucun changement de commande
  nécessaire (`python -m scraper.run` sans `--source` scrape déjà les deux
  par défaut) — seulement le commentaire mis à jour et le timeout bumpé de
  60 à 90 minutes (une exécution Hellowork seule avait déjà pris ~49 minutes
  en session 8 ; ajouter jobup double approximativement le volume du
  premier run avant que la dédup par upsert ne réduise les runs suivants au
  delta).

### Tests réels effectués (pas de simulation)

1. **Scraping réel** (`scraper.run --source jobup --pages 1`, requêtes par
   défaut, Genève+Vaud+Neuchâtel) : **38 offres scrapées, 34 nouvelles
   lignes insérées**, `source='jobup'` dans SQLite.
2. **Vérification géographique** : `check_geography_rules` appliqué aux 34
   locations réelles stockées — 34/34 `suisse_romande` après correctif (0
   avant, avec 4 mal classées). Aucune offre alémanique n'a fuité dans
   l'échantillon.
3. **Orchestrateur complet sur 5 offres jobup.ch réelles** (168, 170-173,
   hors les 3 stages détectés a posteriori) : **5/5 réussies, 0 échec** —
   premier test de bout en bout de la priorité géographique 1 depuis le
   début du projet. `geography_verdict.zone='suisse_romande'`,
   `priority_rank=1` confirmé sur les 5 traces scoring réelles. Trace de
   génération confirmée utilisant le bon chunk de ton
   (`rule_switzerland_other_mobility`), pas une règle par défaut.
4. **Anti-doublons croisés** : test contrôlé avec deux offres synthétiques
   de MÊME titre ET MÊME `source_id` mais `source` différent
   (`hellowork`/`jobup`) — les deux insérées comme lignes séparées (la
   contrainte `UNIQUE(source, source_id)` est bien scopée par source).
   Réinsertion du même `(source, source_id)` correctement ignorée (retour
   `False`). Données de test nettoyées après vérification.
5. **Qualité des données jobup** (limite documentée, pas un bug du
   scraper) : 3/34 offres réelles avaient un `employment-type` jobup
   incohérent avec leur propre titre ("Stagiaire..." classé "Temporaire"
   par jobup) — corrigé avec un filet de sécurité sur le titre (voir
   ci-dessus), pas silencieusement ignoré.

**Fichiers :** `scraper/jobup.py` (nouveau), `scraper/hellowork.py`
(export `DEFAULT_JOB_QUERIES`), `scraper/run.py` (réécrit, flag `--source`),
`.github/workflows/scrape-and-score.yml` (commentaire + timeout),
`scoring/geography.py` (villes manquantes + repli cantonal),
`tests/test_geography.py` (6 nouveaux cas).
