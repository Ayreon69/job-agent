## Résumé du matching
Cette candidature présente un profil technique aligné sur plusieurs exigences clés du poste d’**Ingénieur LLM Senior - IA Générative**, avec des réalisations concrètes en **modèles de langage (LLM)** et **architectures agentiques** :

- **Expertise LLM et IA générative** :
  - Prototypage d’un **assistant interne basé sur l’API Mistral** avec interface Gradio, incluant une gestion de contexte complet (22 000 tokens) et une compréhension des compromis architecturaux (ex : choix de ne pas utiliser RAG) *(source : prototypage assistant interne)*.
  - Utilisation quotidienne de **Claude Code** pour du développement assisté par agent, avec structuration de projets via des fichiers `CLAUDE.md` pour un contexte persistant *(source : utilisation Claude Code)*.
  - Maîtrise des APIs **Mistral et Claude**, avec une approche pratique des LLM en production *(source : APIs Mistral/Claude)*.

- **Architectures d’agents IA** :
  - Expérience avancée avec les **workflows multi-agents**, via l’utilisation de serveurs MCP (GitHub, Playwright, Firecrawl, Context7, Vercel) et des outils comme Claude Code pour des projets de développement assisté *(source : utilisation Claude Code et serveurs MCP)*.
  - Structuration de projets avec des **fichiers de contexte persistant** (`CLAUDE.md`), démontrant une approche systématique des agents IA *(source : structuration projets)*.

- **Prompt Engineering et intégration IA/SDLC** :
  - **Prompt Engineering avancé** : gestion de contextes longs (22 000 tokens) et optimisation des interactions avec les LLM *(source : prototypage assistant interne)*.
  - Intégration de l’IA dans le **cycle de développement logiciel (SDLC)** : expérience en pipelines ETL (architecture proche Medallion sur Snowflake), développement de modèles ML en production (ex : churn), et prototypage d’outils IA *(source : pipelines ETL, modèles churn)*.
  - Collaboration avec les équipes produit pour des solutions alignées sur les KPIs métier, via la création d’outils métiers (tarification santé, tableaux de bord Power BI) et un assistant interne pour les règles de commission *(source : outils métiers, assistant interne)*.

- **Compétences techniques complémentaires** :
  - Maîtrise de **Python, SQL**, et outils de data engineering (Snowflake, pandas).
  - Expérience en **automatisation** (Playwright) et en structuration de données (architecture Medallion).

---

## Gaps et incertitudes
### Gaps confirmés (compétences absentes) :
1. **Développement de pipelines RAG** :
   - Aucune expérience pratique en **RAG** (chunking, embeddings, évaluation de retrieval, recherche hybride). Le prototypage actuel repose sur un **contexte complet sans retrieval**, par choix architectural délibéré *(source : absence de RAG dans les réalisations)*.
   - **Impact** : Limite la capacité à concevoir des solutions nécessitant une **recherche contextuelle avancée** (ex : bases de connaissances dynamiques).

2. **Frameworks d’évaluation pour LLM** :
   - Aucune expérience en conception de **harnais d’évaluation** ou de frameworks pour LLM. Expérience limitée à l’évaluation de modèles ML classiques (ex : recall/précision pour le churn) *(source : absence de frameworks d’évaluation LLM)*.
   - **Impact** : Difficulté à industrialiser des solutions LLM avec des **métriques robustes** (ex : évaluation de la cohérence, de la pertinence).

3. **Développement en TypeScript** :
   - Aucune expérience en **TypeScript** pour le développement de SDK IA internes ou d’outils front-end. Compétences limitées à **Python et SQL** *(source : absence de TypeScript dans les réalisations)*.
   - **Impact** : Frein potentiel pour des projets nécessitant une **intégration full-stack** (ex : interfaces utilisateur pour agents IA).

4. **Montée en compétence des équipes** :
   - Aucune expérience formelle en **formation ou accompagnement** d’équipes sur les technologies LLM/IA. Expérience limitée à la création d’outils métiers **autonomes** (ex : tarification santé) *(source : absence de formation/accompagnement)*.

### Flags incertains (absence de match fiable) :
- **Développement de pipelines RAG** :
  - Aucun élément dans le profil ne permet de confirmer ou d’infirmer une expérience en RAG. L’absence de mention ne signifie pas nécessairement une incompétence, mais **aucune preuve de maîtrise** n’a été identifiée *(source : flag incertain)*.

---

## Questions d’entretien probables
1. **Architectures LLM et compromis techniques** :
   - *"Vous avez choisi de ne pas utiliser RAG pour votre assistant interne. Pouvez-vous expliquer ce choix, ses limites, et dans quels cas vous recommanderiez une architecture RAG ?"* *(source : prototypage assistant interne sans RAG)*.
   - *"Comment gérez-vous les limites de contexte des LLM (ex : 22 000 tokens) dans des applications nécessitant une mémoire longue ?"* *(source : gestion de contexte complet)*.

2. **Agents IA et workflows multi-agents** :
   - *"Comment structurez-vous un projet utilisant des agents IA (ex : Claude Code) pour garantir un contexte persistant et une collaboration efficace entre agents ?"* *(source : fichiers `CLAUDE.md`)*.
   - *"Quels outils (ex : MCP, Firecrawl) utilisez-vous pour orchestrer des workflows multi-agents, et quels sont leurs avantages/inconvénients ?"* *(source : serveurs MCP)*.

3. **Prompt Engineering et évaluation** :
   - *"Quelles techniques de prompt engineering utilisez-vous pour optimiser la qualité des réponses d’un LLM dans un contexte métier (ex : règles de commission) ?"* *(source : assistant interne pour règles de commission)*.
   - *"Comment évalueriez-vous la performance d’un agent IA dans un pipeline de développement logiciel ? Quelles métriques utiliseriez-vous ?"* *(source : absence de frameworks d’évaluation LLM)*.

4. **Intégration IA/SDLC et collaboration produit** :
   - *"Comment alignez-vous une solution IA (ex : assistant interne) avec les KPIs d’une équipe produit ? Pouvez-vous partager un exemple concret ?"* *(source : outils métiers alignés sur KPIs)*.
   - *"Quels défis avez-vous rencontrés en intégrant des outils IA dans un cycle de développement logiciel (SDLC), et comment les avez-vous résolus ?"* *(source : pipelines ETL, modèles churn)*.

5. **Gaps techniques (RAG, TypeScript, évaluation)** :
   - *"Comment aborderiez-vous la conception d’un pipeline RAG pour une base de connaissances métier, en partant de zéro ?"* *(source : gap RAG)*.
   - *"Quelles stratégies mettriez-vous en place pour évaluer la qualité d’un modèle LLM dans un contexte de production ?"* *(source : gap frameworks d’évaluation)*.
   - *"Comment envisagez-vous de monter en compétence sur TypeScript pour contribuer à un SDK IA interne ?"* *(source : gap TypeScript)*.

---

## Angle de candidature
**Positionnement** :
Candidature axée sur une **expertise opérationnelle en LLM et agents IA**, avec une approche pragmatique de l’intégration de l’IA dans des **processus métiers et techniques**. Le profil met en avant :
- Une **maîtrise des outils modernes** (Mistral, Claude, MCP, Gradio) et des **compromis architecturaux** (ex : choix de ne pas utiliser RAG).
- Une **expérience terrain** en collaboration avec des équipes produit pour des solutions alignées sur les besoins métiers (ex : tarification santé, règles de commission).
- Une **approche structurée** des agents IA (fichiers `CLAUDE.md`, contexte persistant) et du développement assisté par IA.

**Points à souligner** :
1. **Valeur ajoutée immédiate** :
   - **Prototypage rapide** : Expérience en création d’outils IA opérationnels (ex : assistant interne en 2 semaines avec Gradio/Mistral), idéale pour des **POC ou MVP**.
   - **Intégration IA/SDLC** : Capacité à concevoir des pipelines ETL (Snowflake) et des modèles ML en production, avec une vision **end-to-end** du cycle de développement.
   - **Collaboration produit** : Création d’outils métiers adoptés par des équipes non-techniques (ex : tableaux de bord Power BI), démontrant une **compréhension des enjeux business**.

2. **Adaptation aux gaps** :
   - **RAG** : Mettre en avant la **compréhension des limites** du contexte complet et une **volonté de monter en compétence** sur les architectures RAG (ex : formation sur les embeddings, chunking).
   - **Évaluation LLM** : Proposer une approche progressive, en s’appuyant sur l’expérience en évaluation de modèles ML classiques (ex : recall/précision) pour étendre aux métriques LLM (ex : cohérence, pertinence).
   - **TypeScript** : Insister sur la **maîtrise de Python** (langage dominant en IA) et une **ouverture à l’apprentissage** de TypeScript pour des besoins front-end.

3. **Alignement avec l’offre** :
   - **Seniorité** : Mettre en avant l’expérience en **leadership technique** (ex : structuration de projets agents IA) et en **collaboration transverse** (équipes produit, data).
   - **Innovation** : Souligner l’utilisation d’outils **cutting-edge** (Claude Code, MCP) et une approche **expérimentale** (ex : choix architecturaux délibérés).
   - **Impact métier** : Insister sur la **création de valeur concrète** (ex : outils adoptés par les équipes, alignement sur les KPIs).

**Message clé** :
*"Ingénieur LLM avec une expertise opérationnelle en prototypage d’agents IA et en intégration de l’IA dans des processus métiers. Mon approche combine une maîtrise des outils modernes (Mistral, Claude, MCP) avec une compréhension des compromis techniques (ex : contexte vs. RAG) et une collaboration étroite avec les équipes produit pour des solutions alignées sur les KPIs. Je cherche à rejoindre une équipe où je pourrai contribuer à des projets d’IA générative à fort impact, tout en consolidant mes compétences sur les architectures RAG et les frameworks d’évaluation."*