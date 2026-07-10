# Règles de ciblage géographique — chunks indépendants pour indexation

Ces chunks sont les plus critiques du profil : ils gouvernent à la fois le scoring
d'une offre (priorité) et le ton de toute analyse générée ensuite (règle de
séparation stricte, voir CLAUDE.md). À indexer et interroger en priorité par
l'agent de scoring pour chaque offre traitée.

---

## chunk: priority_order

Ordre de priorité de relocalisation, du plus désiré au moins désiré : premièrement
Suisse romande (Genève, Lausanne, Neuchâtel), deuxièmement Rhône-Alpes (Lyon et
alentours, par exemple Grenoble, Annecy, Saint-Étienne), troisièmement Émirats
Arabes Unis et autres pays du Golfe (GCC), quatrièmement Suisse hors Romandie
(Suisse alémanique ou italienne, par exemple Zurich, Bâle, Berne). Un score de
pertinence géographique doit refléter cet ordre : une offre Suisse romande bien
positionnée sur le plan technique devrait généralement primer sur une offre
Rhône-Alpes équivalente en technique, elle-même généralement au-dessus d'une offre
UAE/GCC équivalente, elle-même au-dessus d'une offre Suisse alémanique équivalente.

Tags: priorité, géographie, Suisse romande, Rhône-Alpes, Lyon, UAE, GCC, Suisse alémanique, ordre

---

## chunk: rule_lyon_no_mobility

Règle stricte pour toute offre basée à Lyon, en Rhône-Alpes, ou en France (hors
Suisse) : zéro signal de mobilité internationale ne doit apparaître dans l'analyse
ou la candidature générée. Ne jamais mentionner le projet de relocalisation,
l'ouverture à l'international, ou le conjoint dans ce contexte, même si Rhône-Alpes
est une priorité géographique élevée. Ces candidatures doivent se présenter comme
un choix professionnel local à part entière, pas comme un plan de secours visible.

Tags: Lyon, Rhône-Alpes, France, mobilité, règle stricte, exclusion, zéro signal

---

## chunk: rule_switzerland_mobility

Règle pour toute offre en Suisse romande (Genève, Lausanne, Neuchâtel) : le projet
de relocalisation personnel, incluant le conjoint (épouse coach sportive et
nutrition), est mentionnable et peut être intégré à la candidature. Le ton doit
rester factuel et non excessif. La Suisse romande est la priorité géographique
numéro un.

Tags: Suisse, mobilité, conjoint, mentionnable, romande, priorité 1

---

## chunk: rule_switzerland_german_italian

Distinction géographique critique à ne pas confondre : la Suisse alémanique
(Zurich, Bâle, Berne) et la Suisse italienne (Tessin, Lugano) ne sont PAS la
Suisse romande. Ces régions sont en dernière priorité géographique (quatrième et
dernière position), en dessous même des Émirats et du Golfe. Une offre à Zurich ne
doit jamais être traitée avec les mêmes règles de mobilité que Genève ou Lausanne :
la proximité géographique en Suisse ne signifie pas une priorité équivalente. Ne
pas confondre "Suisse" au sens large avec "Suisse romande" lors du scoring d'une
offre.

Tags: Suisse alémanique, Zurich, Bâle, Berne, Tessin, dernière priorité, distinction critique, romande

---

## chunk: rule_uae_middle_east

Règle pour toute offre aux Émirats Arabes Unis ou dans un autre pays du Golfe
(GCC) : l'ouverture à la relocalisation doit être explicite et assumée dans la
candidature. Ne pas utiliser de framing orienté avantages spécifiquement français
(par exemple ne pas insister sur des éléments qui n'ont de sens que dans un
contexte d'expatriation depuis la France). Prendre en compte que la nationalité
française implique un besoin de visa de travail (voir chunk nationality_visa dans
constraints.md). Cette zone est en troisième position de priorité géographique,
après la Suisse romande et Rhône-Alpes.

Tags: UAE, Moyen-Orient, GCC, Golfe, mobilité, explicite, visa, relocalisation assumée, priorité 3

---

## chunk: rule_role_priority_current

Priorité actuelle de type de poste : rôles orientés IA appliquée (agents, LLM,
RAG) préférés aux rôles data classiques de type reporting pur. Les rôles data
classiques restent considérés comme plan de sécurité pragmatique, pas comme
objectif de carrière prioritaire. Un score de pertinence doit refléter un bonus
pour les offres à composante IA/agents/LLM, sans exclure totalement les offres
data classiques bien positionnées géographiquement (notamment UAE/Suisse).

Tags: priorité poste, IA, agents, LLM, RAG, reporting, data classique, bonus scoring