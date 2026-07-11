"""Scoring agent: evaluate a scraped job offer against the user profile.

Decision loop:
  1. check_geography_rules(offer.location) — deterministic, no RAG (see
     scoring/geography.py). Runs before anything else because the geography
     verdict conditions the tone rules to fetch next.
  2. If zone == "inconnu", flag_uncertain("géographie") but keep scoring —
     a missing geography match must not block the rest of the pipeline.
  3. search_profile on the *zone name*, not the offer's raw location text, to
     fetch the matching tone rule chunk(s) from geography_rules.md.
  4. Extract the offer's key requirements (skills, seniority) via the LLM.
     Each requirement has a composite display label (grouped, capped to
     MAX_SKILLS) AND a list of atomic elements it bundles together (e.g. the
     individual standards inside "gouvernance QMS (ISO 13485, FDA 21 CFR Part
     820, EU MDR)"). Grouping is for display only.
  5. search_profile runs on each ATOM separately (n_results >= 3), never on
     the composite label — a composite sentence can find a passable-looking
     match as a whole even when none of its individual parts are actually
     covered by the profile. If any single atom's best distance exceeds
     NOISE_THRESHOLD, flag_uncertain(requirement_label): one weak link is
     enough, even if other atoms of the same requirement matched well.
  6. Ask the LLM to produce the final structured verdict from all the
     gathered context (geography verdict, tone chunks, matched achievements,
     honest gaps, uncertain flags).

Every RAG query this loop makes is recorded in a DecisionTrace so the
reasoning can be audited after the fact, not just the final score.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from scoring.embeddings.index import search_profile_with_scores
from scoring.geography import GeographyVerdict, check_geography_rules
from scoring.llm import call_llm_json

logger = logging.getLogger(__name__)

# Distance de bruit identifiée en session 2 (ROADMAP.md) : au-delà de ce seuil,
# le meilleur chunk retrouvé n'est plus considéré comme un vrai match.
NOISE_THRESHOLD = 0.75

ZONE_TO_QUERY = {
    "rhone_alpes": "règle de ton pour une offre en Rhône-Alpes ou en France, mobilité",
    "autre_france": "règle de ton pour une offre en France hors Rhône-Alpes, mobilité",
    "suisse_romande": "règle de ton pour une offre en Suisse romande, mobilité conjoint",
    "uae_gcc": "règle de ton pour une offre aux Émirats Arabes Unis ou dans le Golfe, mobilité",
    "suisse_autre": "règle de ton pour une offre en Suisse alémanique ou italienne, mobilité",
}


@dataclass
class RagQueryLog:
    step: str
    query: str
    n_results: int
    results: list[dict] = field(default_factory=list)  # [{"id", "distance", "source_file"}]
    conclusion: str = ""


@dataclass
class DecisionTrace:
    offer_id: int
    geography_verdict: GeographyVerdict | None = None
    rag_queries: list[RagQueryLog] = field(default_factory=list)
    uncertain_flags: list[str] = field(default_factory=list)

    def log_rag(self, step: str, query: str, n_results: int, results, conclusion: str) -> None:
        entry = RagQueryLog(
            step=step,
            query=query,
            n_results=n_results,
            results=[
                {"id": chunk.id, "distance": round(dist, 4), "source_file": chunk.source_file}
                for chunk, dist in results
            ],
            conclusion=conclusion,
        )
        self.rag_queries.append(entry)
        logger.info(
            "[offer %s] RAG step=%s query=%r n_results=%d -> %s | conclusion=%s",
            self.offer_id,
            step,
            query,
            n_results,
            entry.results,
            conclusion,
        )

    def flag_uncertain(self, label: str) -> None:
        self.uncertain_flags.append(label)
        logger.info("[offer %s] flag_uncertain(%r)", self.offer_id, label)


@dataclass
class ScoringResult:
    offer_id: int
    score: int
    geography_zone: str
    geography_priority_rank: int | None
    matches: list[dict]
    gaps: list[dict]
    uncertain_flags: list[str]
    reasoning_summary: str
    trace: DecisionTrace


def _validate_items(items: list, required_keys: set[str]) -> list[dict]:
    """Keep only well-formed {key: str, ...} dicts, dropping anything the LLM
    produced outside the requested schema (e.g. a bare {"some sentence": ""}).
    """
    valid = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if not required_keys.issubset(item.keys()):
            continue
        if any(not isinstance(item[k], str) or not item[k].strip() for k in required_keys):
            continue
        valid.append(item)
    return valid


def _fetch_geography_tone_chunks(trace: DecisionTrace, zone: str) -> list[str]:
    query = ZONE_TO_QUERY.get(zone)
    if query is None:
        # zone == "inconnu": no tone rule applies, nothing to fetch.
        return []

    results = search_profile_with_scores(query, n_results=3)
    best_distance = min((dist for _c, dist in results), default=1.0)
    conclusion = (
        f"best_distance={best_distance:.4f}, "
        f"{'ok' if best_distance <= NOISE_THRESHOLD else 'au-dessus du seuil de bruit'}"
    )
    trace.log_rag("geography_tone", query, 3, results, conclusion)

    if best_distance > NOISE_THRESHOLD:
        trace.flag_uncertain("ton_geographique")
        return []

    return [chunk.text for chunk, _dist in results]


MAX_SKILLS = 10


def _extract_requirements(offer_title: str, offer_description: str) -> dict:
    """Ask the LLM to pull out key requirements from the raw offer text.

    Each requirement is a composite label (for display / grouping, capped to
    MAX_SKILLS) plus its "atoms": the individual technical items it bundles
    together (e.g. distinct standards/tools mentioned in the same sentence).
    Matching runs on the atoms, not the composite label — see _search_requirement.
    """
    system_prompt = (
        "Tu extrais les exigences clés d'une offre d'emploi data/IA. Réponds en JSON "
        f"strict avec les clés: skills (liste d'AU PLUS {MAX_SKILLS} objets), "
        "seniority (chaîne libre décrivant le niveau d'expérience demandé, ou null si "
        "non précisé), role_focus (\"ia_agents_llm\" si le poste est orienté "
        "agents/LLM/RAG, \"data_classique\" sinon). "
        "Chaque objet de skills doit avoir EXACTEMENT les clés: "
        "\"label\" (le libellé composite lisible regroupant les variantes proches d'une "
        "même compétence, ex: 'gouvernance et gestion des données QMS (ISO 13485, FDA 21 "
        "CFR Part 820, EU MDR)') et \"atoms\" (liste des éléments techniques atomiques qui "
        "composent ce libellé, chacun recherchable indépendamment, ex: [\"ISO 13485\", "
        "\"FDA 21 CFR Part 820\", \"EU MDR\", \"gouvernance des données QMS\"] — si le "
        "libellé ne regroupe qu'un seul élément, atoms contient cet unique élément)."
    )
    user_prompt = f"Titre: {offer_title}\n\nDescription:\n{offer_description[:3000]}"
    result = call_llm_json(system_prompt, user_prompt)
    raw_skills = (result.get("skills") or [])[:MAX_SKILLS]

    skills = []
    for item in raw_skills:
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        atoms = item.get("atoms") or []
        if not isinstance(label, str) or not label.strip():
            continue
        atoms = [a for a in atoms if isinstance(a, str) and a.strip()]
        if not atoms:
            atoms = [label]
        skills.append({"label": label, "atoms": atoms})
    result["skills"] = skills
    return result


def _search_requirement(trace: DecisionTrace, label: str, atoms: list[str]) -> tuple[list[str], bool]:
    """search_profile on each atomic element of a (possibly composite) requirement.

    Matching granularity is deliberately finer than display granularity: a
    composite label like "gouvernance QMS (ISO 13485, FDA 21 CFR Part 820, EU
    MDR)" can find a mediocre-but-passable match as a whole sentence even when
    none of its individual standards are actually covered by the profile. One
    weak atom is enough to flag the whole requirement uncertain — a good match
    on one atom must not hide the absence of a match on another.
    """
    matched_chunks: list[str] = []
    worst_distance = 0.0
    any_uncertain = False

    for atom in atoms:
        results = search_profile_with_scores(atom, n_results=3)
        best_distance = min((dist for _c, dist in results), default=1.0)
        worst_distance = max(worst_distance, best_distance)

        if best_distance > NOISE_THRESHOLD or not results:
            trace.log_rag(
                "requirement_atom", f"[{label}] {atom}", 3, results,
                "aucun match fiable -> flag_uncertain",
            )
            any_uncertain = True
            continue

        trace.log_rag(
            "requirement_atom", f"[{label}] {atom}", 3, results,
            f"best_distance={best_distance:.4f}, match retenu",
        )
        matched_chunks.extend(chunk.text for chunk, _dist in results)

    if any_uncertain:
        trace.flag_uncertain(label)
        return matched_chunks, True

    return matched_chunks, False


def score_offer(offer_id: int, title: str, location: str, description: str) -> ScoringResult:
    trace = DecisionTrace(offer_id=offer_id)

    # 1. Géographie en premier, avant tout appel RAG.
    geo_verdict = check_geography_rules(location)
    trace.geography_verdict = geo_verdict
    logger.info("[offer %s] geography verdict: %s", offer_id, geo_verdict)

    # 2. Zone inconnue : on flag mais on continue le scoring.
    if geo_verdict.zone == "inconnu":
        trace.flag_uncertain("géographie")

    # 3. Chunks de ton géographique, via le nom de zone, pas le texte brut de l'offre.
    tone_chunks = _fetch_geography_tone_chunks(trace, geo_verdict.zone)

    # 4. Extraction des exigences clés de l'offre.
    requirements = _extract_requirements(title, description or "")
    skills = requirements.get("skills", []) or []
    seniority = requirements.get("seniority")
    role_focus = requirements.get("role_focus")
    logger.info("[offer %s] extracted requirements: %s", offer_id, requirements)

    # 5. Une recherche RAG séparée par élément atomique de chaque exigence
    #    (le libellé composite ne sert qu'à l'affichage, voir _search_requirement).
    requirement_context: dict[str, list[str]] = {}
    requirement_uncertain: dict[str, bool] = {}
    for skill in skills:
        label = skill["label"]
        chunks, uncertain = _search_requirement(trace, label, skill["atoms"])
        requirement_context[label] = chunks
        requirement_uncertain[label] = uncertain

    # 6. Arbitrage final par le LLM à partir de tout le contexte rassemblé.
    system_prompt = (
        "Tu es l'agent de scoring d'un outil de recherche d'emploi. Évalue la pertinence "
        "d'une offre pour le candidat à partir UNIQUEMENT du contexte fourni (réalisations, "
        "règles de ton, compétences). Ne jamais inventer une compétence ou une expérience "
        "non présente dans le contexte. Si une compétence de l'offre n'a aucun match dans "
        "le profil, elle doit apparaître UNIQUEMENT comme un gap honnête, jamais aussi comme "
        "un match — une compétence ne peut pas être listée à la fois dans matches et dans gaps. "
        "Réponds en JSON strict avec les clés: score (entier 0-100), matches (liste "
        "d'objets avec EXACTEMENT les clés \"skill\" et \"matched_chunk_summary\", chaînes de "
        "caractères non vides), gaps (liste d'objets avec EXACTEMENT les clés \"skill\" et "
        "\"note\", chaînes de caractères non vides — jamais d'autre forme d'objet), "
        "reasoning_summary (2-3 phrases expliquant le score)."
    )

    context_parts = [
        f"OFFRE: {title}\nLocalisation brute: {location}\n",
        f"Verdict géographique: zone={geo_verdict.zone}, priority_rank={geo_verdict.priority_rank}, "
        f"mobility_signal_allowed={geo_verdict.mobility_signal_allowed}\n",
    ]
    if tone_chunks:
        context_parts.append("Règles de ton applicables:\n" + "\n---\n".join(tone_chunks))
    if seniority:
        context_parts.append(f"Séniorité demandée: {seniority}")
    if role_focus:
        context_parts.append(f"Orientation du poste: {role_focus}")

    for skill, chunks in requirement_context.items():
        if requirement_uncertain[skill]:
            if chunks:
                context_parts.append(
                    f"Compétence '{skill}' — AU MOINS UN élément constitutif n'a AUCUN match "
                    "fiable dans le profil, malgré un match partiel sur d'autres éléments "
                    "(gap potentiel, un maillon faible suffit — ne pas considérer comme acquis) :\n"
                    + "\n---\n".join(chunks)
                )
            else:
                context_parts.append(f"Compétence '{skill}' — AUCUN match fiable dans le profil (gap potentiel).")
        else:
            context_parts.append(f"Compétence '{skill}' — chunks profil trouvés:\n" + "\n---\n".join(chunks))

    context_parts.append(f"Description complète de l'offre:\n{(description or '')[:3000]}")

    user_prompt = "\n\n".join(context_parts)
    verdict = call_llm_json(system_prompt, user_prompt)

    matches = _validate_items(verdict.get("matches", []), {"skill", "matched_chunk_summary"})
    gaps = _validate_items(verdict.get("gaps", []), {"skill", "note"})

    # Une compétence ne doit jamais apparaître à la fois en match et en gap :
    # en cas de désaccord du LLM avec lui-même, le gap l'emporte (posture prudente,
    # cohérente avec la règle d'honnêteté du CLAUDE.md — ne jamais présenter comme
    # acquis ce qui est signalé ailleurs comme manquant).
    gap_skills = {g["skill"] for g in gaps}
    matches = [m for m in matches if m["skill"] not in gap_skills]

    result = ScoringResult(
        offer_id=offer_id,
        score=verdict.get("score", 0),
        geography_zone=geo_verdict.zone,
        geography_priority_rank=geo_verdict.priority_rank,
        matches=matches,
        gaps=gaps,
        uncertain_flags=list(trace.uncertain_flags),
        reasoning_summary=verdict.get("reasoning_summary", ""),
        trace=trace,
    )
    logger.info("[offer %s] final score=%d gaps=%d uncertain=%d", offer_id, result.score, len(result.gaps), len(result.uncertain_flags))
    return result


def trace_to_json(trace: DecisionTrace) -> str:
    """Serialize a DecisionTrace to a readable JSON string, for audit."""
    return json.dumps(
        {
            "offer_id": trace.offer_id,
            "geography_verdict": (
                {
                    "zone": trace.geography_verdict.zone,
                    "priority_rank": trace.geography_verdict.priority_rank,
                    "mobility_signal_allowed": trace.geography_verdict.mobility_signal_allowed,
                    "matched_keyword": trace.geography_verdict.matched_keyword,
                    "match_method": trace.geography_verdict.match_method,
                }
                if trace.geography_verdict
                else None
            ),
            "rag_queries": [
                {
                    "step": q.step,
                    "query": q.query,
                    "n_results": q.n_results,
                    "results": q.results,
                    "conclusion": q.conclusion,
                }
                for q in trace.rag_queries
            ],
            "uncertain_flags": trace.uncertain_flags,
        },
        ensure_ascii=False,
        indent=2,
    )
