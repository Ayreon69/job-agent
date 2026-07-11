## Résumé du matching
**Adéquation globale : 75/100**
Le profil présente une **forte adéquation technique et sectorielle** avec l’offre de Business Analyst Data & Reporting, notamment grâce à :
- **Une expertise en architecture et gouvernance des données** :
  - Structuration de pipelines ETL sur Snowflake selon une logique proche de l’architecture Medallion (*source : reprise de données et migration*), avec une maîtrise des couches *staging → core → reporting*.
  - Fiabilisation des flux de données et optimisation des requêtes SQL avancées (*source : manipulation de gros volumes sur Snowflake*).
- **Une capacité prouvée à qualifier et restituer des données** :
  - Conception de tableaux de bord Power BI alignés sur les KPIs métier, adoptés par plusieurs départements (*source : coordination multi-acteurs*).
  - Certifications DataCamp (SQL avancé, Python) et expérience en recette de données (*source : qualification des données*).
- **Une connaissance opérationnelle du secteur santé/prévoyance** :
  - Développement d’un modèle de churn pour ECA Assurances et création d’un outil de tarification pour des produits santé individuelle (*source : domaine Collectif Santé/Prévoyance*).
  - Formation en Data Analytics et Risk Management (ISFA), renforçant la crédibilité sur les enjeux métiers.
- **Des compétences transverses clés** :
  - Rédaction de spécifications fonctionnelles via des outils comme Claude Code (*source : fichiers CLAUDE.md pour structurer des projets*).
  - Automatisation de processus critiques (ex : calcul des commissions) avec un impact mesurable (*source : réduction du temps de traitement et élimination des erreurs*).
  - Utilisation de l’IA en contexte projet (prototypage d’un assistant interne via l’API Mistral) (*source : utilisation de Claude Code et serveurs MCP*).

---

## Gaps et incertitudes
**Gaps confirmés (compétences absentes)** :
1. **Méthodologie formelle de migration de données** :
   - Expérience en architecture ETL proche Medallion, mais **absence de mention explicite** de méthodologies structurées de migration (ex : reprise par objet métier, mapping source-cible détaillé, phases de recette).
2. **Connaissance approfondie des métiers de l’assureur** :
   - Expertise limitée au **domaine santé individuelle et prévoyance** (churn, tarification). **Pas de référence** à des branches comme l’assurance collective ou l’IARD.
3. **Préparation et animation de plans de bascule** :
   - **Aucune expérience identifiée** en gestion de bascule de projets data (ex : identification d’adhérences entre composants, coordination des tests de non-régression).

**Flags incertains** :
*Aucun* – Tous les écarts identifiés sont des **gaps confirmés** (absence de compétences constatée), sans zone d’incertitude sur le profil.

---

## Questions d’entretien probables
**1. Approfondissement des compétences techniques** :
- *"Pouvez-vous détailler la structuration de vos pipelines ETL sur Snowflake ? Comment avez-vous géré les dépendances entre les couches staging/core/reporting ?"* (*source : reprise de données et migration*)
- *"Quels critères utilisez-vous pour valider la conformité des données dans vos tableaux de bord Power BI ? Avez-vous des exemples de KPIs métier que vous avez alignés avec des indicateurs techniques ?"* (*source : qualification des données*)

**2. Méthodologie et gestion de projet** :
- *"Comment abordez-vous la reprise de données pour un nouveau projet ? Avez-vous déjà utilisé une méthodologie spécifique (ex : mapping source-cible) ?"* (*gap : méthodologie formelle de migration*)
- *"Comment gérez-vous les adhérences entre composants lors d’un déploiement ? Avez-vous déjà participé à un plan de bascule ?"* (*gap : préparation de bascule*)

**3. Connaissance du secteur assurance** :
- *"Quels sont les enjeux spécifiques de la data dans le domaine de la santé/prévoyance que vous avez identifiés ?"* (*source : domaine Collectif Santé/Prévoyance*)
- *"Comment adapteriez-vous vos compétences en tarification santé individuelle à un contexte d’assurance collective ?"* (*gap : connaissance des métiers de l’assureur*)

**4. Soft skills et coordination** :
- *"Comment avez-vous convaincu des équipes non techniques d’adopter vos tableaux de bord Power BI ?"* (*source : coordination multi-acteurs*)
- *"Pouvez-vous partager un exemple où vous avez dû arbitrer entre des besoins métiers et des contraintes techniques ?"* (*source : spécifications fonctionnelles*)

**5. Utilisation de l’IA** :
- *"Comment l’IA (ex : Claude Code, Mistral) a-t-elle amélioré votre productivité sur des projets data ? Avez-vous des cas d’usage concrets ?"* (*source : utilisation de l’IA en contexte projet*)

---

## Angle de candidature
**Positionnement clé** :
*"Business Analyst Data avec une double expertise technique et sectorielle, capable de **traduire des enjeux métiers en solutions data fiables** pour le domaine santé/prévoyance. Mon profil combine :*
- **Une maîtrise opérationnelle des outils** (Snowflake, Power BI, SQL avancé) pour concevoir des pipelines et des tableaux de bord alignés sur les KPIs.
- **Une approche structurée de la data** (architecture proche Medallion, gouvernance technique) pour garantir la qualité et la traçabilité des données.
- **Une connaissance terrain du secteur assurance** (tarification, churn, automatisation des commissions) pour dialoguer avec les métiers et les équipes IT.
- **Un leadership technique** démontré par l’adoption de mes livrables (ex : tableaux de bord Power BI) et l’automatisation de processus critiques (ex : réduction des erreurs de calcul)."*

**Points différenciants à mettre en avant** :
1. **L’IA comme levier de productivité** :
   - *"Mon utilisation quotidienne de Claude Code et de l’API Mistral (ex : prototypage d’un assistant interne pour les règles de commission) me permet d’accélérer la documentation, le débogage et la structuration des projets. Cette approche moderne complète ma rigueur technique sur les outils traditionnels (SQL, ETL)."*
   *(Source : utilisation de l’IA en contexte projet)*

2. **L’impact concret sur les processus métiers** :
   - *"Chez ECA Assurances, j’ai développé un modèle de churn qui a permis d’identifier des leviers de rétention ciblés. Cette expérience renforce ma capacité à **lier la data aux décisions business**, un atout pour des projets comme la migration de données ou l’optimisation des reportings."*
   *(Source : domaine Collectif Santé/Prévoyance + automatisation des commissions)*

3. **La méthodologie "data as a product"** :
   - *"Mes pipelines ETL sur Snowflake s’inspirent de l’architecture Medallion : une couche *staging* pour l’ingestion brute, une couche *core* pour la transformation, et une couche *reporting* pour la restitution. Cette approche **scalable et gouvernée** est directement applicable à des projets de migration ou de fiabilisation des données."*
   *(Source : reprise de données et migration)*

**Stratégie pour combler les gaps** :
- **Sur la méthodologie de migration** :
  - *"Bien que je n’aie pas utilisé de framework formel comme le mapping source-cible, mon expérience en structuration de pipelines ETL (ex : dépendances entre couches) et en recette de données (Power BI) me permet d’aborder ces enjeux avec une **logique de traçabilité et de validation progressive**."*
  - Proposer un exemple concret : *"Pour un projet de reprise de données, je commencerais par identifier les objets métiers prioritaires, puis je documenterais les transformations via des fichiers CLAUDE.md (comme pour mes outils de tarification)."*

- **Sur la connaissance des métiers de l’assureur** :
  - *"Mon expertise en santé individuelle et prévoyance (tarification, churn) est un socle solide pour monter en compétence sur l’assurance collective. Ma formation en Risk Management (ISFA) et mon expérience en automatisation des commissions me donnent les clés pour **comprendre rapidement les spécificités techniques et réglementaires** du secteur."*

**Message de clôture** :
*"Cette offre représente une opportunité idéale pour **mettre mon expertise data au service d’un acteur du secteur santé/prévoyance**, tout en consolidant mes compétences en migration et en gestion de projets complexes. Mon profil hybride – à la fois technique et orienté métier – me permet d’être opérationnel rapidement sur des enjeux comme la fiabilisation des reportings ou la coordination entre équipes IT et métiers."*