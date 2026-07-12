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
- Le parsing du markdown pour les compteurs de gaps est un pis-aller —
  fonctionne à 100% sur les analyses réelles actuelles mais reste sensible à
  un changement de structure du prompt de génération (session 4). Une
  alternative plus robuste serait de faire produire ces compteurs sous forme
  structurée par `generation/analysis.py` directement plutôt que de les
  re-dériver du texte a posteriori — non fait cette session pour rester dans
  le périmètre "pas de nouvelle logique métier".
- Pas de rendu markdown complet pour le lien "analyse complète" (ouvre le
  JSON brut de `GET /offers/{id}`, qui inclut le markdown en texte) — accepté
  explicitement comme suffisant pour cette première version.
