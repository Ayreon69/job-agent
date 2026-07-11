# Règles de ciblage géographique — chunks indépendants pour indexation

IMPORTANT — changement d'architecture (2026-07-11) : la décision de savoir à
quelle zone appartient une offre (Suisse romande vs alémanique, Rhône-Alpes vs
autre France, etc.) n'est PLUS gérée par ce fichier ni par le RAG. Elle est gérée
par la fonction `check_geography_rules` (matching par département/ville, en dur),
suite à un problème documenté de confusion Zurich/Genève par le RAG en session 2
(voir ROADMAP.md). Voir check_geography_rules_spec.md pour l'ordre de priorité
complet des zones (Suisse romande = 1, Rhône-Alpes = 2, UAE/GCC = 3, Suisse
alémanique/italienne = 4).

Ce fichier ne contient désormais que les règles de **ton et de comportement** à
appliquer une fois la zone déjà déterminée par `check_geography_rules`. L'agent de
génération (étape 4) doit recevoir le verdict de zone en entrée et interroger ce
fichier pour savoir comment adapter le discours en conséquence — pas pour
redéterminer la zone elle-même.

---

## chunk: rule_lyon_no_mobility

Règle stricte pour toute offre dont `check_geography_rules` a déterminé la zone
"rhone_alpes" ou "autre_france" : zéro signal de mobilité internationale ne doit
apparaître dans l'analyse ou la candidature générée. Ne jamais mentionner le
projet de relocalisation, l'ouverture à l'international, ou le conjoint dans ce
contexte, même si Rhône-Alpes est une priorité géographique élevée. Ces
candidatures doivent se présenter comme un choix professionnel local à part
entière, pas comme un plan de secours visible.

Tags: Lyon, Rhône-Alpes, France, mobilité, règle stricte, exclusion, zéro signal

---

## chunk: rule_switzerland_mobility

Règle pour toute offre dont `check_geography_rules` a déterminé la zone
"suisse_romande" : le projet de relocalisation personnel, incluant le conjoint
(épouse coach sportive et nutrition), est mentionnable et peut être intégré à la
candidature. Le ton doit rester factuel et non excessif.

Tags: Suisse romande, mobilité, conjoint, mentionnable, ton factuel

---

## chunk: rule_uae_middle_east

Règle pour toute offre dont `check_geography_rules` a déterminé la zone
"uae_gcc" : l'ouverture à la relocalisation doit être explicite et assumée dans la
candidature. Ne pas utiliser de framing orienté avantages spécifiquement français
(par exemple ne pas insister sur des éléments qui n'ont de sens que dans un
contexte d'expatriation depuis la France). Prendre en compte que la nationalité
française implique un besoin de visa de travail (voir chunk nationality_visa dans
constraints.md).

Tags: UAE, Moyen-Orient, GCC, Golfe, mobilité, explicite, visa, relocalisation assumée

---

## chunk: rule_switzerland_other_mobility

Règle pour toute offre dont `check_geography_rules` a déterminé la zone
"suisse_autre" (Suisse alémanique ou italienne, ex: Zurich, Bâle, Berne, Tessin) :
la mobilité reste mentionnable comme pour la Suisse romande (c'est toujours une
relocalisation vers la Suisse), mais cette zone est en dernière priorité
géographique. Le ton peut rester ouvert à la mobilité, sans le même niveau
d'enthousiasme prioritaire que pour une offre en Suisse romande ou même UAE/GCC —
à traiter comme une option de repli plutôt qu'un objectif de premier choix.

Tags: Suisse alémanique, Suisse italienne, Zurich, mobilité, priorité basse, repli

---

## chunk: rule_role_priority_current

Priorité actuelle de type de poste, indépendante de la géographie : rôles orientés
IA appliquée (agents, LLM, RAG) préférés aux rôles data classiques de type
reporting pur. Les rôles data classiques restent considérés comme plan de
sécurité pragmatique, pas comme objectif de carrière prioritaire. Un score de
pertinence doit refléter un bonus pour les offres à composante IA/agents/LLM,
sans exclure totalement les offres data classiques bien positionnées
géographiquement.

Tags: priorité poste, IA, agents, LLM, RAG, reporting, data classique, bonus scoring