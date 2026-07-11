# Spécification — check_geography_rules (session 3)

## Principe

Cette fonction NE PASSE PAS par le RAG / ChromaDB. C'est une fonction déterministe,
en dur, basée sur un matching de texte simple (liste de villes/mots-clés), car le
retrieval sémantique s'est montré incapable de distinguer fiablement Suisse
romande vs Suisse alémanique/italienne (voir ROADMAP.md, session 2, retest du
2026-07-11).

Le RAG reste utilisé pour tout le reste du scoring (compétences, réalisations,
ton de candidature) — uniquement la décision géographique est sortie du RAG.

## Signature proposée

```python
def check_geography_rules(offer_location: str) -> GeographyVerdict:
    ...
```

`offer_location` : le texte brut de localisation tel que scrapé (ex: "Genève",
"Zurich (ZH)", "Lyon 3e", "Dubai, UAE", "Full remote France").

Retourne un objet structuré (dataclass ou dict), pas juste une string, pour que
l'agent de scoring puisse l'exploiter facilement :

```python
GeographyVerdict = {
    "zone": "suisse_romande" | "rhone_alpes" | "uae_gcc" | "suisse_autre" | "autre_france" | "inconnu",
    "priority_rank": 1 | 2 | 3 | 4 | None,   # None si zone = "autre_france" ou "inconnu"
    "mobility_signal_allowed": bool,          # False pour rhone_alpes/autre_france, True sinon
    "matched_keyword": str | None,            # le mot-clé ou département qui a permis le matching, pour audit/debug
    "match_method": "departement" | "ville_connue" | "aucun",  # traçabilité du type de matching utilisé
}
```

## Listes de mots-clés (à coder en dur, insensible à la casse et aux accents)

**Suisse romande (priority_rank = 1, mobility_signal_allowed = True) :**
Genève, Geneva, Lausanne, Neuchâtel, Neuchatel, Yverdon, Yverdon-les-Bains, Nyon,
Vevey, Montreux, Fribourg (ambigu bilingue, voir note), Sion, Vaud, Valais
(partie francophone).

**Rhône-Alpes (priority_rank = 2, mobility_signal_allowed = False) :**

Détection en deux temps, pas une simple liste de noms de ville fermée — pour
couvrir les petites villes non explicitement listées (ex: Bourgoin-Jallieu,
Villefranche-sur-Saône) sans avoir à énumérer toutes les communes.

1. **Détection par département**, en priorité — repérer un code postal (5
   chiffres) ou une mention explicite de département dans le texte de
   localisation, et vérifier si les deux premiers chiffres du code postal (ou le
   numéro de département cité) correspondent à la région Rhône-Alpes /
   Auvergne-Rhône-Alpes :
   `01` (Ain), `07` (Ardèche), `26` (Drôme), `38` (Isère), `42` (Loire),
   `69` (Rhône), `73` (Savoie), `74` (Haute-Savoie).
   Exemple : "Bourgoin-Jallieu (38300)" → département 38 → rhone_alpes.

2. **Repli sur liste de grandes villes connues** si aucun code postal/département
   n'est identifiable dans le texte, pour les cas où l'offre ne mentionne qu'un
   nom de ville sans code postal :
   Lyon, Villeurbanne, Grenoble, Annecy, Saint-Étienne, Saint-Etienne, Chambéry,
   Chambery, Valence, Bourg-en-Bresse, Vienne, Civrieux, Rhône-Alpes, Rhone-Alpes,
   Auvergne-Rhône-Alpes.

3. Si ni département ni ville connue ne matchent, mais que le texte mentionne
   quand même "France" sans autre précision → zone "autre_france" (voir plus bas),
   pas "rhone_alpes" par défaut. Le doute doit profiter à la prudence, pas à
   l'inclusion automatique dans le périmètre Rhône-Alpes.

**UAE / GCC (priority_rank = 3, mobility_signal_allowed = True) :**
Dubai, Dubaï, Abu Dhabi, Abou Dabi, UAE, Émirats, Emirats, Sharjah, Doha, Qatar,
Riyadh, Riyad, Arabie Saoudite, Saudi Arabia, Koweït, Kuwait, Bahrain, Bahreïn,
Oman, Muscat.

**Suisse hors romande (priority_rank = 4, mobility_signal_allowed = True) :**
Zurich, Zürich, Bâle, Basel, Berne, Bern, Lucerne, Lucerna, Winterthur, Lugano,
Tessin, Ticino, Suisse alémanique, Deutschschweiz.

**Autre France (priority_rank = None, mobility_signal_allowed = False) :**
Toute ville française non listée ci-dessus (Paris, Marseille, Toulouse, etc.) ou
mention générique "France" sans ville identifiée dans les listes précédentes.

**Inconnu (priority_rank = None, mobility_signal_allowed = False par défaut,
posture prudente) :**
Aucun mot-clé ne matche (ex: "Remote", "Télétravail" sans précision, ville non
reconnue). Dans ce cas, `flag_uncertain` devrait être déclenché par l'agent de
scoring plutôt que de deviner.

## Cas particuliers à gérer explicitement dans le code

- **Fribourg / Freiburg** : ville bilingue suisse, ambiguë. Par défaut la classer
  en Suisse romande (le canton de Fribourg est majoritairement francophone), mais
  documenter ce choix comme approximation dans un commentaire de code.
- **"Suisse" seul, sans ville précisée** : ne pas classer par défaut en Suisse
  romande. Retourner zone "inconnu" et laisser `flag_uncertain` s'appliquer, car le
  risque d'erreur (classer une offre alémanique comme romande) est justement ce
  qu'on cherche à éviter depuis le début.
- **Remote / télétravail** : si la mention précise un pays (ex: "Remote Suisse"),
  retomber sur les mêmes règles que ci-dessus. Si totalement générique ("Full
  remote"), zone "inconnu".
- **Ordre de priorité dans le matching** : si plusieurs mots-clés de zones
  différentes apparaissent dans le même texte (rare mais possible sur une offre
  mal structurée), prioriser le matching le plus spécifique (nom de ville exact)
  sur le plus générique (nom de région/pays).

## Tests à effectuer avant de valider cette fonction

Sur des chaînes réalistes, pas seulement des noms de ville isolés :
- "Genève, Suisse" → suisse_romande, rank 1, mobility True
- "Zurich (ZH)" → suisse_autre, rank 4, mobility True
- "Lyon 3e arrondissement" → rhone_alpes, rank 2, mobility False
- "Civrieux (01)" → rhone_alpes, rank 2, mobility False
- "Bourgoin-Jallieu (38300)" → rhone_alpes (via département 38), rank 2, mobility False
- "Villefranche-sur-Saône, 69400" → rhone_alpes (via département 69), rank 2, mobility False
- "Dubai, UAE" → uae_gcc, rank 3, mobility True
- "Paris 8e" → autre_france, rank None, mobility False
- "Suisse" (seul, sans ville) → inconnu, rank None, mobility False
- "Full remote" → inconnu, rank None, mobility False
- "Fribourg" → suisse_romande (approximation documentée), rank 1, mobility True

## Intégration avec l'agent de scoring

Cette fonction doit être appelée en tout premier dans la boucle de décision de
l'agent de scoring (avant même d'interroger le RAG sur les compétences), car le
verdict géographique conditionne ensuite le ton de toute la suite de l'analyse
(voir rule_lyon_no_mobility, rule_switzerland_mobility, rule_uae_middle_east dans
geography_rules.md). Si `zone = "inconnu"`, l'agent doit déclencher
`flag_uncertain("géographie")` et le signaler clairement dans sa sortie plutôt que
de choisir arbitrairement un ton de candidature.
