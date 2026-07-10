# Réalisations — chunks indépendants pour indexation

Chaque section ci-dessous est un chunk autonome : une réalisation, son contexte, et
ce qu'elle démontre. Ne pas fusionner les sections lors du découpage en embeddings.

---

## chunk: churn_model

Développement d'un modèle de machine learning pour prédire la résiliation des
clients (churn) chez ECA Assurances, en production. Recall de 85 pourcent,
priorisé volontairement sur la précision : dans le contexte assurance, manquer un
client qui va résilier coûte plus cher qu'une fausse alerte. Le modèle alimente des
stratégies de fidélisation ciblées. Démontre : machine learning appliqué en
production, capacité à justifier un choix statistique par une logique métier,
autonomie sur un projet de recherche appliquée (mémoire de fin d'études mis en
production).

Tags: machine learning, ML, prédiction, churn, recall, production, décision métier

---

## chunk: commission_automation

Refonte de la méthodologie de calcul des commissions chez ECA Assurances et
automatisation du suivi. Temps de traitement réduit de plus de 10 heures à environ
35 minutes. Élimination de coûts de licence logicielle associés à l'ancien
processus. Taux d'erreur quasi nul après automatisation. Démontre : capacité
d'automatisation de processus métier critique, impact chiffré et mesurable,
optimisation financière au-delà du seul gain de temps.

Tags: automatisation, ETL, reporting, finance, gain de temps, réduction de coûts

---

## chunk: power_bi_dashboards

Conception de tableaux de bord Power BI sur des indicateurs sensibles (commissions,
sinistralité, coût moyen), devenus des outils décisionnels adoptés par l'ensemble
des départements de l'entreprise, pas seulement l'équipe data. Alignement direct
avec les KPIs métier définis par la direction. Démontre : maîtrise de Power BI
(DAX avancé), capacité à produire des outils utilisables par des audiences
non-techniques, adoption large à l'échelle de l'entreprise.

Tags: Power BI, DAX, dashboard, KPI, reporting, adoption utilisateur, vulgarisation

---

## chunk: snowflake_etl

Structuration des pipelines ETL sur Snowflake selon une organisation en couches
(staging vers core vers reporting), proche d'une architecture Medallion sans être
une implémentation certifiée ou nommée comme telle formellement. Objectif :
fiabiliser la production de rapports à grande échelle. Démontre : architecture de
données, fiabilisation et gouvernance technique des données, maîtrise de
Snowflake.

Note d'honnêteté : à formuler comme "proche d'une architecture Medallion" ou
"inspirée de", jamais comme une implémentation Medallion certifiée.

Tags: Snowflake, ETL, architecture de données, Medallion, staging, data quality

---

## chunk: pricing_tool

Création d'un outil de tarification pour les produits santé individuelle,
permettant des ajustements tarifaires en autonomie par les équipes métier
elles-mêmes, sans dépendre de l'équipe technique pour chaque changement. Démontre :
compréhension des besoins métier, capacité à construire un outil qui transfère de
l'autonomie aux utilisateurs finaux, logique de modélisation de scénarios et
hypothèses tarifaires.

Tags: tarification, scénarios, autonomie métier, outil, santé, assurance

---

## chunk: mistral_chatbot

Prototypage d'un assistant interne basé sur l'API Mistral pour répondre aux
questions sur les règles de commission. Architecture volontairement simple : appel
API direct avec un contexte complet d'environ 22000 tokens, interface web via
Gradio. Choix architectural délibéré de ne pas utiliser de RAG à ce stade (pas un
oubli, une décision consciente compte tenu du volume de contexte gérable
directement). Démontre : prototypage LLM en conditions réelles d'entreprise,
compréhension des compromis entre contexte complet et retrieval, première
expérience concrète avec les APIs de LLM en production interne.

Tags: LLM, Mistral, chatbot, Gradio, prototypage IA, API, full-context

---

## chunk: sql_adhoc_analysis

Requêtes SQL avancées pour répondre aux demandes analytiques ad hoc des équipes
opérationnelles et de la direction. Exercice constant de vulgarisation des
résultats techniques pour des audiences non-techniques. Démontre : maîtrise SQL
avancée, capacité de communication et de traduction technique vers métier.

Tags: SQL, analyse ad hoc, communication, vulgarisation, direction

---

## chunk: agentic_coding

Utilisation quotidienne de Claude Code et de serveurs MCP (GitHub, Playwright,
Firecrawl, Context7, Vercel) pour des projets de développement assisté par agent.
Structuration de projets via des fichiers CLAUDE.md pour donner du contexte
persistant aux sessions d'agent. Démontre : familiarité avancée et pratique
quotidienne de l'écosystème agentique moderne, au-delà d'un simple usage
occasionnel d'un chatbot IA.

Tags: agentic coding, Claude Code, MCP, agents, outillage IA, développement assisté

---

## chunk: whisper_nlp_pipeline

Pipeline d'extraction audio depuis YouTube suivi d'une transcription via Whisper,
pour alimenter une base de contenu recherchable (projet personnel,
lislam-simplement.com). Démontre : maîtrise de pipelines NLP audio, capacité à
construire un projet personnel de bout en bout depuis l'ingestion de données brutes
jusqu'à un produit utilisable.

Tags: NLP, Whisper, audio, transcription, pipeline, projet personnel

---

## chunk: playwright_scraping_insurance

Bot d'automatisation basé sur Playwright pour scraper Hyperassur et remplir
automatiquement des formulaires de devis santé et animaux, avec simulation de
comportement humain pour éviter la détection. Démontre : maîtrise de Playwright en
conditions réelles avancées (pas juste du scraping simple mais de l'interaction
formulaire complexe), sensibilité aux contraintes anti-bot.

Tags: Playwright, scraping, automatisation, veille tarifaire, comportement humain

---

## chunk: b2b_outreach_automation

Stack complet de prospection B2B automatisée pour Second Serve (marque de
vêtements, ciblage clubs tennis et padel en Rhône-Alpes) : scraping de contacts,
outreach email automatisé via pandas, smtplib et Brevo. Démontre : capacité à
construire un système complet de bout en bout (données brutes vers action
commerciale), compréhension d'un besoin business externe à l'assurance.

Tags: B2B, outreach, automatisation, scraping, email, pandas, smtplib, Brevo
