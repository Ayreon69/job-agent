## Résumé du matching

Cette candidature présente un profil technique aligné sur plusieurs exigences clés de l’offre **Ingénieur LLM Senior - IA Générative - RAG - Agents IA**, avec des réalisations concrètes en développement d’agents IA, utilisation de LLM en production, et industrialisation de solutions. Voici les points forts identifiés :

- **Architecture et développement d’agents IA** :
  - Utilisation quotidienne de **Claude Code** et de serveurs **MCP** (GitHub, Playwright, Firecrawl, Context7, Vercel) pour des projets de développement assisté par agent (*source : structuration de projets via CLAUDE.md*).
  - Prototypage d’un **assistant interne basé sur l’API Mistral** avec interface Gradio, démontrant une maîtrise des compromis architecturaux et des APIs de LLM en conditions réelles (*source : prototype Mistral/Gradio*).

- **Expérience avec les LLM** :
  - Maîtrise des APIs **Mistral** et **Claude** en usage direct, avec une compréhension pratique des enjeux de production (*source : utilisation quotidienne de Claude Code et prototype Mistral*).
  - Intégration des LLM dans des workflows techniques, notamment via des outils comme **Gradio** (*source : prototype d’assistant interne*).

- **Collaboration avec les équipes produit et développement** :
  - Création d’outils décisionnels (**Power BI**) adoptés par des départements non-techniques, et développement d’un **outil de tarification** aligné sur les KPIs métier (*source : outils pour équipes métier*).
  - Prototypage d’un assistant interne pour répondre aux besoins opérationnels (*source : prototype Mistral*).

- **Industrialisation de solutions IA** :
  - Déploiement en production d’un **modèle de churn** (machine learning) chez ECA Assurances, avec un **recall de 85%** (*source : modèle de prédiction de résiliation*).
  - Expérience en **pipelines ETL** (Snowflake) et déploiement de modèles en conditions réelles (*source : industrialisation chez ECA Assurances*).

- **Prompt Engineering avancé** :
  - Réflexion sur les compromis entre **contexte complet** et **retrieval** dans le cadre du prototype Mistral, illustrant une approche pragmatique du prompt engineering (*source : prototype d’assistant interne*).

- **Intégration de l’IA dans le SDLC** :
  - Utilisation de **Claude Code** et de serveurs MCP pour du développement assisté par agent, structuration de pipelines techniques, et déploiement de modèles (*source : projets GitHub/Playwright et modèle de churn*).

---

## Gaps et incertitudes

### Gaps confirmés (compétences absentes)
1. **Développement de pipelines RAG** :
   - Aucune expérience identifiée en **RAG** (chunking, embeddings, évaluation de retrieval, recherche hybride, optimisation de la couche vectorielle). Le profil mentionne une décision de ne pas utiliser de RAG dans un prototype, mais sans implémentation concrète (*source : absence de réalisation RAG*).

2. **Conception de frameworks d’évaluation pour LLM** :
   - Aucune expérience dans la création de **harnais d’évaluation** ou de frameworks pour mesurer la qualité/robustesse des modèles LLM (*source : chunks liés à des outils métier ou modèles prédictifs classiques*).

3. **Développement en TypeScript** :
   - Compétences limitées à **Python** et **SQL**, sans expérience en TypeScript pour des SDK IA internes (*source : absence de mention de TypeScript*).

4. **Montée en compétence des équipes sur les LLM** :
   - Aucune expérience formelle de **formation** ou de transfert de connaissances sur les technologies LLM (*source : chunks liés à des outils métier, pas à l’IA avancée*).

### Flags incertains (absence de match fiable)
- **Développement de pipelines RAG** :
  - Le système n’a pas identifié de preuve explicite d’expérience en RAG, mais cela ne confirme pas une absence totale de compétences (*à clarifier en entretien*).

---

## Questions d’entretien probables

1. **Architecture et agents IA** :
   - *"Pouvez-vous détailler les compromis architecturaux que vous avez identifiés lors du prototypage de votre assistant interne basé sur Mistral ? Comment avez-vous géré les limites de contexte ?"* (*source : prototype Mistral/Gradio*).
   - *"Quels outils ou frameworks utilisez-vous pour orchestrer des agents IA (ex : MCP, Firecrawl) ? Comment gérez-vous la persistance du contexte entre les sessions ?"* (*source : CLAUDE.md et serveurs MCP*).

2. **LLM et prompt engineering** :
   - *"Comment évaluez-vous la qualité des réponses d’un LLM en production ? Avez-vous mis en place des métriques ou des tests automatisés ?"* (*source : prototype Mistral, absence de frameworks d’évaluation*).
   - *"Quels défis avez-vous rencontrés lors de l’intégration de l’API Mistral dans votre prototype ? Comment avez-vous optimisé les coûts ou la latence ?"* (*source : prototype d’assistant interne*).

3. **RAG et industrialisation** :
   - *"Pourquoi avez-vous choisi de ne pas utiliser de RAG dans votre prototype ? Quels critères utiliseriez-vous pour décider d’implémenter une architecture RAG dans un projet futur ?"* (*source : absence de RAG dans le prototype*).
   - *"Comment aborderiez-vous la conception d’un pipeline RAG pour un cas d’usage similaire à votre assistant interne ? Quels outils ou bibliothèques utiliseriez-vous ?"* (*source : gap RAG*).

4. **Collaboration et industrialisation** :
   - *"Comment avez-vous aligné votre prototype d’assistant interne avec les besoins des équipes métier ? Quels KPIs avez-vous définis pour mesurer son succès ?"* (*source : outil de tarification et KPIs métier*).
   - *"Quelles leçons avez-vous tirées du déploiement de votre modèle de churn chez ECA Assurances ? Comment gérez-vous la maintenance des modèles en production ?"* (*source : modèle de prédiction de résiliation*).

5. **TypeScript et SDK** :
   - *"Avez-vous déjà travaillé sur des SDK ou des bibliothèques internes pour des outils IA ? Si non, comment aborderiez-vous ce type de projet en TypeScript ?"* (*source : gap TypeScript*).

---

## Angle de candidature

Cette candidature doit mettre en avant une **expertise opérationnelle en LLM et agents IA**, tout en reconnaissant les gaps techniques (RAG, évaluation, TypeScript) comme des opportunités de montée en compétence ciblée. Voici l’angle à privilégier :

1. **Expérience terrain en LLM et agents** :
   - Insister sur la **maîtrise des APIs LLM** (Mistral, Claude) et des outils d’orchestration (MCP, Firecrawl), avec des exemples concrets de prototypes et de déploiements (*prototype Mistral/Gradio, utilisation quotidienne de Claude Code*).
   - Souligner la **compréhension des enjeux de production** : gestion du contexte, latence, coûts, et intégration dans des workflows techniques (*modèle de churn, pipelines ETL*).

2. **Industrialisation et collaboration** :
   - Mettre en avant la **capacité à livrer des solutions IA en production**, avec des résultats mesurables (*recall de 85% pour le modèle de churn, adoption d’outils Power BI par les équipes métier*).
   - Montrer une **approche pragmatique** : choix architecturaux réfléchis (ex : non-utilisation de RAG dans le prototype) et alignement avec les besoins métier (*outil de tarification, KPIs*).

3. **Adaptabilité et apprentissage** :
   - Reconnaître les **gaps techniques** (RAG, évaluation, TypeScript) comme des axes de progression, en citant des ressources ou des projets personnels pour les combler (ex : formations, contributions open source).
   - Proposer une **vision proactive** : *"Je souhaite approfondir les architectures RAG pour compléter mon expérience en LLM, notamment via des projets concrets comme [exemple pertinent]."*

4. **Alignement avec les valeurs locales** :
   - Si l’entreprise cible est basée en Rhône-Alpes, souligner l’ancrage géographique comme un **choix professionnel assumé**, avec une connaissance des écosystèmes tech locaux (ex : meetups, collaborations avec des acteurs régionaux).
   - Mettre en avant des **réalisations en contexte français** (ex : modèle de churn chez ECA Assurances) pour renforcer la pertinence locale.

**Exemple de phrase d’accroche** :
*"Mon expérience en prototypage d’agents IA (Mistral, Claude) et en industrialisation de modèles (churn, ETL) me permet de rejoindre votre équipe avec une approche terrain des LLM. Bien que je n’aie pas encore implémenté de pipeline RAG, je maîtrise les enjeux de production et suis motivé pour monter en compétence sur ces architectures, comme en témoigne mon prototype d’assistant interne déployé en conditions réelles."*