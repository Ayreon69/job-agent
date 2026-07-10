# Règles de ciblage géographique — chunks indépendants pour indexation

Ces chunks sont les plus critiques du profil : ils gouvernent à la fois le scoring
d'une offre (priorité) et le ton de toute analyse générée ensuite (règle de
séparation stricte, voir CLAUDE.md). À indexer et interroger en priorité par
l'agent de scoring pour chaque offre traitée.

---

## chunk: priority_order

Ordre de priorité de relocalisation, du plus désiré au moins désiré : premièrement
Émirats Arabes Unis, deuxièmement autres pays du Moyen-Orient, troisièmement Suisse
francophone (zone Genève, Neuchâtel, Yverdon), quatrièmement Lyon en repli
pragmatique. Un score de pertinence géographique doit refléter cet ordre : une
offre UAE bien positionnée sur le plan technique devrait généralement primer sur
une offre Lyon équivalente en technique.

Tags: priorité, géographie, UAE, Moyen-Orient, Suisse, Lyon, ordre

---

## chunk: rule_lyon_no_mobility

Règle stricte pour toute offre basée à Lyon ou en France (hors Suisse) : zéro
signal de mobilité internationale ne doit apparaître dans l'analyse ou la
candidature générée. Ne jamais mentionner le projet de relocalisation, l'ouverture
à l'international, ou le conjoint dans ce contexte. Ces candidatures doivent se
présenter comme un choix professionnel local à part entière, pas comme un plan de
secours visible.

Tags: Lyon, France, mobilité, règle stricte, exclusion, zéro signal

---

## chunk: rule_switzerland_mobility

Règle pour toute offre en Suisse francophone : le projet de relocalisation
personnel, incluant le conjoint (épouse coach sportive et nutrition), est
mentionnable et peut être intégré à la candidature. Le ton doit rester factuel et
non excessif.

Tags: Suisse, mobilité, conjoint, mentionnable, romande

---

## chunk: rule_uae_middle_east

Règle pour toute offre aux Émirats Arabes Unis ou ailleurs au Moyen-Orient :
l'ouverture à la relocalisation doit être explicite et assumée dans la candidature.
Ne pas utiliser de framing orienté avantages spécifiquement français (par exemple
ne pas insister sur des éléments qui n'ont de sens que dans un contexte
d'expatriation depuis la France). Prendre en compte que la nationalité française
implique un besoin de visa de travail (voir chunk nationality_visa dans
constraints.md).

Tags: UAE, Moyen-Orient, mobilité, explicite, visa, relocalisation assumée

---

## chunk: rule_role_priority_current

Priorité actuelle de type de poste : rôles orientés IA appliquée (agents, LLM,
RAG) préférés aux rôles data classiques de type reporting pur. Les rôles data
classiques restent considérés comme plan de sécurité pragmatique, pas comme
objectif de carrière prioritaire. Un score de pertinence doit refléter un bonus
pour les offres à composante IA/agents/LLM, sans exclure totalement les offres
data classiques bien positionnées géographiquement (notamment UAE/Suisse).

Tags: priorité poste, IA, agents, LLM, RAG, reporting, data classique, bonus scoring
