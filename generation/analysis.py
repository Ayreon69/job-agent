"""Candidacy analysis generator: turns a ScoringResult (session 3) into a
readable, structured markdown analysis — in the spirit of the analyses
usually produced by hand in conversation.

Decision loop:
  1. Consume the geography zone already computed by check_geography_rules
     (via ScoringResult.geography_zone) — never recompute it.
  2. search_profile on the zone's tone-rule query (same ZONE_TO_QUERY mapping
     as the scoring agent) to fetch the exact tone chunk to write under
     (rule_lyon_no_mobility, rule_switzerland_mobility, rule_uae_middle_east,
     or rule_switzerland_other_mobility).
  3. If the offer text is too short/generic to write a grounded "angle de
     candidature", optionally call web_search(company_name) for context.
     web_search is currently a disabled stub (see below) — no third-party API
     wired in yet, so it always reports itself unavailable rather than
     fabricating company context.
  4. Generate the markdown analysis, instructed to follow the fetched tone
     chunk strictly — in particular, staying completely silent about mobility
     when the zone requires it, without ever narrating the rule itself.
  5. Never invent a skill or achievement absent from the scoring result's
     matches — gaps and uncertain_flags from scoring must appear explicitly,
     never smoothed over or dropped.

Every step is recorded in a GenerationTrace, same auditability principle as
the scoring agent's DecisionTrace.

Structured output (session 9 follow-up): generate_analysis also returns a
StructuredAnalysis (matches/gaps/uncertain_flags) alongside the markdown, so
callers (the API, the dashboard) don't have to re-parse the free-text
markdown to answer "how many gaps does this offer have". This is built
directly from ScoringResult.matches/gaps/uncertain_flags in Python — NOT a
second LLM call re-deriving these from the generated text. Two reasons:
  1. Fidelity: the point of this structured output is to reflect exactly what
     scoring (session 3) already decided. An LLM asked to "extract structure
     from this markdown" would be re-interpreting a paraphrase of scoring's
     own data, reintroducing exactly the divergence risk this change exists
     to eliminate.
  2. Cost/risk: a second LLM call would double latency and API cost for
     information already sitting in memory as a typed dataclass, and adds a
     second point of possible malformed-JSON failure for no benefit.
_validate_items (already used by scoring/agent.py) is reused here as the
schema guard on ScoringResult's own fields — scoring's LLM call already
produced this data through call_llm_json, so it was already validated once
at that point; re-validating on the way into StructuredAnalysis costs
nothing and protects against a future caller constructing a ScoringResult by
hand (as tests/test_generation.py's synthetic web_search case already does)
without going through score_offer's validation path.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from scoring.agent import ZONE_TO_QUERY, ScoringResult, _validate_items
from scoring.embeddings.index import search_profile_with_scores
from scoring.llm import call_llm

logger = logging.getLogger(__name__)


def web_search(company_name: str) -> str | None:
    """Optional company-context lookup. Currently a disabled stub: no
    third-party search API is wired in, so it always reports unavailable
    rather than fabricating context — consistent with the project's honesty
    rule (CLAUDE.md: never invent factual content not present in the source
    profile, and by extension, not present in a verified external source).
    """
    logger.info("web_search(%r) called but no provider is configured — skipped", company_name)
    return None


@dataclass
class GenerationTrace:
    offer_id: int
    tone_chunk_used: str | None = None
    tone_rag_query: str | None = None
    tone_rag_distance: float | None = None
    web_search_used: bool = False
    web_search_result: str | None = None
    steps: list[str] = field(default_factory=list)

    def log(self, message: str) -> None:
        self.steps.append(message)
        logger.info("[offer %s] %s", self.offer_id, message)


@dataclass
class StructuredAnalysis:
    """Machine-readable mirror of the matching/gaps/uncertain sections of the
    generated markdown — built directly from ScoringResult, not re-derived
    from the markdown text (see module docstring). Every item has at least a
    label and a short justification, matching the shapes ScoringResult
    already carries:
      - matches: [{"skill": ..., "matched_chunk_summary": ...}]
      - gaps:    [{"skill": ..., "note": ...}]
      - uncertain_flags: [str]  (no per-item justification in ScoringResult —
        these are requirement labels the scoring agent couldn't find a
        reliable RAG match for, see DecisionTrace.flag_uncertain)
      - sector: str | None  (the offer/company's business sector, extracted
        by the same LLM call as the requirements — see
        scoring/agent.py::_extract_requirements; null if the offer text
        didn't give the LLM enough to determine one)
    """
    matches: list[dict]
    gaps: list[dict]
    uncertain_flags: list[str]
    sector: str | None = None


def _build_structured_analysis(result: ScoringResult) -> StructuredAnalysis:
    """Deterministic formatting of ScoringResult's own fields — see module
    docstring for why this isn't a second LLM call. _validate_items is the
    same schema guard scoring/agent.py already runs its own LLM output
    through; reused here so a hand-built ScoringResult (e.g. a test fixture)
    can't smuggle a malformed item into the API response either.
    """
    matches = _validate_items(result.matches, {"skill", "matched_chunk_summary"})
    gaps = _validate_items(result.gaps, {"skill", "note"})
    uncertain_flags = [f for f in result.uncertain_flags if isinstance(f, str) and f.strip()]
    sector = result.sector if isinstance(result.sector, str) and result.sector.strip() else None
    return StructuredAnalysis(matches=matches, gaps=gaps, uncertain_flags=uncertain_flags, sector=sector)


def _fetch_tone_chunk(trace: GenerationTrace, zone: str) -> str | None:
    """search_profile on the zone's tone query — same mapping the scoring
    agent already used in session 3, so the same tone chunk is retrieved
    consistently between scoring and generation for a given zone.
    """
    query = ZONE_TO_QUERY.get(zone)
    if query is None:
        trace.log(f"zone={zone!r} n'a pas de règle de ton associée (zone inconnue) — aucun chunk récupéré")
        return None

    results = search_profile_with_scores(query, n_results=1)
    if not results:
        trace.log(f"aucune règle de ton trouvée pour zone={zone!r}")
        return None

    chunk, distance = results[0]
    trace.tone_rag_query = query
    trace.tone_rag_distance = round(distance, 4)
    trace.tone_chunk_used = chunk.id
    trace.log(f"règle de ton récupérée: {chunk.id} (distance={distance:.4f}) pour zone={zone!r}")
    return chunk.text


def _should_search_web(title: str, description: str) -> bool:
    """Heuristic: an offer is "too short/generic" to ground a candidacy angle
    when its description is thin. Kept simple and inspectable rather than an
    extra LLM call just to decide whether to search.
    """
    return len(f"{title} {description}".strip()) < 300


def _format_matches(matches: list[dict]) -> str:
    if not matches:
        return "(aucun match identifié)"
    return "\n".join(f"- {m['skill']}: {m['matched_chunk_summary']}" for m in matches)


def _format_gaps(gaps: list[dict]) -> str:
    if not gaps:
        return "(aucun gap identifié)"
    return "\n".join(f"- {g['skill']}: {g['note']}" for g in gaps)


def _format_uncertain(uncertain_flags: list[str]) -> str:
    if not uncertain_flags:
        return "(aucun)"
    return "\n".join(f"- {flag}" for flag in uncertain_flags)


GENERATION_SYSTEM_PROMPT = """Tu rédiges une analyse de candidature structurée en markdown, dans le \
style des analyses de candidature produites habituellement en conversation par un assistant \
spécialisé en recherche d'emploi.

Règles strictes, non négociables :
1. Respecte EXACTEMENT la règle de ton géographique fournie ci-dessous. Si elle impose un \
silence total sur la mobilité, le mot "mobilité" (et ses synonymes : relocalisation, \
expatriation, international, conjoint, déménagement) NE DOIT APPARAÎTRE NULLE PART dans le \
texte généré — même dans une formulation négative du type "sans nécessité de mobilité" ou \
"pas de mobilité requise". Nommer l'absence de mobilité revient à en parler : c'est interdit au \
même titre que l'affirmer. Ne fais non plus JAMAIS référence à cette règle elle-même dans le \
texte généré (pas de phrase du type "candidature Lyon donc pas de mention mobilité"). Le ton \
doit refléter la règle par un silence total et naturel sur le sujet, comme une évidence qui \
n'a pas besoin d'être énoncée — pas comme une consigne appliquée ou niée explicitement.
2. Ne fabrique JAMAIS une compétence ou une réalisation qui n'est pas dans la liste de matches \
fournie. Cite la réalisation source pour chaque point fort mis en avant.
3. Les gaps et les incertitudes (uncertain_flags) fournis DOIVENT apparaître explicitement dans \
la section dédiée, de façon honnête — jamais dilués, jamais omis, jamais reformulés pour \
paraître moins graves qu'ils ne sont. Distingue clairement un "gap connu" (compétence absente, \
constatée) d'un "flag_uncertain" (le système n'a pas trouvé de match fiable dans le profil, ce \
qui n'est pas la même chose qu'une absence confirmée — formule-le avec cette nuance).
4. N'invente aucune information sur l'entreprise si aucun contexte web n'a été trouvé — dans ce \
cas, base l'angle de candidature uniquement sur le contenu de l'offre.

Format de sortie attendu, en markdown, avec ces sections EXACTEMENT dans cet ordre et EXACTEMENT \
ce texte de titre (utilise bien l'apostrophe droite ' et pas l'apostrophe typographique ’) :
## Résumé du matching
## Gaps et incertitudes
## Questions d'entretien probables
## Angle de candidature

Réponds uniquement avec le markdown brut, sans préambule, sans commentaire hors de ces sections, \
et SANS l'envelopper dans un bloc de code (pas de \`\`\`markdown au début ni de \`\`\` à la fin)."""


def generate_analysis(result: ScoringResult, offer_title: str, offer_description: str,
                       company_name: str | None = None) -> tuple[str, StructuredAnalysis, GenerationTrace]:
    """Generate the structured markdown candidacy analysis from a ScoringResult.

    Returns (markdown_text, structured_analysis, trace). structured_analysis
    is a faithful, non-LLM reformatting of ScoringResult's own matches/gaps/
    uncertain_flags (see module docstring) — kept alongside the markdown so
    callers don't have to re-parse free text to answer "how many gaps".
    """
    trace = GenerationTrace(offer_id=result.offer_id)

    # 1-2. Consume the zone already computed by scoring; fetch its tone chunk.
    tone_text = _fetch_tone_chunk(trace, result.geography_zone)

    # 3. Optional web search for company context, only if the offer is thin.
    company_context = None
    if company_name and _should_search_web(offer_title, offer_description):
        trace.web_search_used = True
        trace.log(f"offre jugée trop courte/générique, tentative de web_search({company_name!r})")
        company_context = web_search(company_name)
        trace.web_search_result = company_context
        if company_context is None:
            trace.log("web_search indisponible (aucun fournisseur configuré) — analyse basée uniquement sur l'offre")
    else:
        trace.log("contexte de l'offre jugé suffisant — pas de web_search")

    # 4-5. Generate the analysis, LLM instructed to follow the tone strictly
    #      and to never smooth over gaps/uncertain_flags.
    user_prompt_parts = [
        f"OFFRE: {offer_title}",
        f"Score de matching: {result.score}/100",
        f"Zone géographique: {result.geography_zone} (priority_rank={result.geography_priority_rank})",
        "",
        "Règle de ton géographique à respecter strictement:",
        tone_text or "(aucune règle de ton spécifique trouvée — reste neutre et factuel, sans mention de mobilité)",
        "",
        "Matches (points forts, avec réalisation source):",
        _format_matches(result.matches),
        "",
        "Gaps honnêtes (compétences constatées absentes):",
        _format_gaps(result.gaps),
        "",
        "Flags incertains (aucun match RAG fiable trouvé, pas une absence confirmée):",
        _format_uncertain(result.uncertain_flags),
        "",
        f"Résumé du scoring: {result.reasoning_summary}",
    ]
    if company_context:
        user_prompt_parts += ["", f"Contexte entreprise (web_search): {company_context}"]

    user_prompt = "\n".join(user_prompt_parts)
    markdown = call_llm(GENERATION_SYSTEM_PROMPT, user_prompt)
    markdown = _strip_code_fence(markdown)
    trace.log("analyse générée")

    structured = _build_structured_analysis(result)
    trace.log(
        f"analyse structurée construite depuis ScoringResult (pas de second appel LLM): "
        f"{len(structured.matches)} matches, {len(structured.gaps)} gaps, "
        f"{len(structured.uncertain_flags)} uncertain_flags"
    )

    return markdown, structured, trace


def _strip_code_fence(text: str) -> str:
    """The LLM occasionally wraps its markdown output in a ```markdown fence
    despite being asked for raw markdown — strip it if present.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        return "\n".join(lines).strip()
    return stripped


def structured_analysis_to_json(structured: StructuredAnalysis) -> str:
    return json.dumps(
        {
            "matches": structured.matches,
            "gaps": structured.gaps,
            "uncertain_flags": structured.uncertain_flags,
            "sector": structured.sector,
        },
        ensure_ascii=False,
        indent=2,
    )


def trace_to_json(trace: GenerationTrace) -> str:
    return json.dumps(
        {
            "offer_id": trace.offer_id,
            "tone_chunk_used": trace.tone_chunk_used,
            "tone_rag_query": trace.tone_rag_query,
            "tone_rag_distance": trace.tone_rag_distance,
            "web_search_used": trace.web_search_used,
            "web_search_result": trace.web_search_result,
            "steps": trace.steps,
        },
        ensure_ascii=False,
        indent=2,
    )
