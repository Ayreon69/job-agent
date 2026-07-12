"""Tests for generation/analysis.py — structural validation of the generated
markdown, plus a dedicated web_search path exercise (session 4 follow-up).

Not pytest: standalone script in the same style as test_geography.py, run
directly. Hits the real Mistral API and the real ChromaDB index (same as
generation/run.py) — no mocking, consistent with this project's preference
for testing against real offers/real profile data rather than fixtures.
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from generation.analysis import _should_search_web, generate_analysis, structured_analysis_to_json, trace_to_json
from scoring.agent import ScoringResult, score_offer
from storage.db import connect

PROFILE_DIR = Path(__file__).resolve().parent.parent / "scoring" / "profile"

EXPECTED_SECTIONS = [
    "## Résumé du matching",
    "## Gaps et incertitudes",
    "## Questions d'entretien probables",
    "## Angle de candidature",
]

MOBILITY_WORDS_RE = re.compile(
    r"\bmobilit[eé]\b|\brelocalisation\b|\bexpatriation\b|\binternational\w*\b|\bconjoint\w*\b|\bd[ée]m[ée]nagement\b",
    re.IGNORECASE,
)

# Stopwords/generic connector words that would trivially "match" any profile
# text and defeat the anti-fabrication check if not excluded.
# Gap/uncertain counts previously validated by hand this session (session 9
# follow-up structured-output correctif) — see ROADMAP.md. Re-running
# score_offer calls the LLM again, which isn't deterministic, so a drift here
# is a WARNING, not a hard failure: what actually matters is that
# structured.gaps/uncertain_flags always equal ScoringResult's own fields for
# THIS run (see check_structured_matches_scoring), not that scoring produces
# byte-identical output across runs.
EXPECTED_GAPS_UNCERTAIN = {
    7: (4, 1),
    24: (4, 1),
}

SKILL_STOPWORDS = {
    "et", "de", "des", "du", "la", "le", "les", "un", "une", "en", "pour", "dans",
    "avec", "sur", "au", "aux", "ou", "a", "d", "l", "qualité", "gestion", "outils",
    "systèmes", "système", "données", "donnée", "expertise", "support", "analyse",
}


def load_offer(offer_id: int) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, title, location, description, company FROM jobs WHERE id = ?", (offer_id,)
        ).fetchone()
    if row is None:
        raise ValueError(f"No offer with id={offer_id}")
    return {"id": row[0], "title": row[1], "location": row[2], "description": row[3], "company": row[4]}


def load_profile_text() -> str:
    text = ""
    for name in ("achievements.md", "skills.md", "constraints.md", "geography_rules.md"):
        path = PROFILE_DIR / name
        if path.exists():
            text += path.read_text(encoding="utf-8").lower() + "\n"
    return text


def _normalize_apostrophes(text: str) -> str:
    """The LLM sometimes uses a typographic apostrophe (') instead of the
    straight one ('), despite the prompt asking for the latter — normalize
    before matching rather than trusting the instruction to always be followed.
    """
    return text.replace("’", "'")


def check_sections(markdown: str) -> list[str]:
    """Returns a list of missing sections (empty if all 4 are present, in order)."""
    markdown = _normalize_apostrophes(markdown)
    missing = []
    last_pos = -1
    for section in EXPECTED_SECTIONS:
        pos = markdown.find(section)
        if pos == -1:
            missing.append(f"section manquante: {section!r}")
        elif pos < last_pos:
            missing.append(f"section hors ordre: {section!r}")
        else:
            last_pos = pos
    return missing


def check_no_mobility(markdown: str, zone: str) -> list[str]:
    """Zones rhone_alpes/autre_france must never mention mobility, in any form."""
    if zone not in ("rhone_alpes", "autre_france"):
        return []
    hits = MOBILITY_WORDS_RE.findall(markdown)
    return [f"mention de mobilité trouvée alors que zone={zone!r} l'interdit: {hits}"] if hits else []


def check_no_fabricated_skills(markdown: str, matches: list[dict], profile_text: str) -> list[str]:
    """Basic anti-fabrication guard: for each match, at least one significant
    word from its GROUNDING (matched_chunk_summary — the actual claim about
    the candidate's experience) must appear somewhere in the profile source
    files. Checking the "skill" label itself would false-positive constantly:
    that label is the LLM's paraphrase of the OFFER's wording (e.g.
    "Prétraitement et exploration des données"), not a profile term — the
    grounding is what must trace back to the profile, not the requirement
    label it was matched against. Not a semantic check — just a sanity net
    against a match with zero textual grounding anywhere in the profile.
    """
    problems = []
    for m in matches:
        skill = m.get("skill", "")
        summary = m.get("matched_chunk_summary", "")
        words = [w for w in re.findall(r"[a-zàâäéèêëïîôöùûüç0-9]+", summary.lower()) if len(w) > 2]
        words = [w for w in words if w not in SKILL_STOPWORDS]
        if not words:
            continue
        if not any(w in profile_text for w in words):
            problems.append(f"match {skill!r} — sa justification {summary!r} ne partage aucun mot-clé avec le profil source: {words}")
    return problems


def check_structured_matches_scoring(structured, result: ScoringResult) -> list[str]:
    """structured_analysis (session 9 follow-up) must be a faithful mirror of
    ScoringResult's own matches/gaps/uncertain_flags — not a re-interpretation.
    Since it's built in Python (not a second LLM call), this should hold
    exactly, every time.
    """
    problems = []
    if structured.matches != result.matches:
        problems.append(f"structured.matches diverge de ScoringResult.matches: {structured.matches!r} != {result.matches!r}")
    if structured.gaps != result.gaps:
        problems.append(f"structured.gaps diverge de ScoringResult.gaps: {structured.gaps!r} != {result.gaps!r}")
    if structured.uncertain_flags != result.uncertain_flags:
        problems.append(f"structured.uncertain_flags diverge de ScoringResult.uncertain_flags: {structured.uncertain_flags!r} != {result.uncertain_flags!r}")
    return problems


def run_case(label: str, result: ScoringResult, offer_title: str, offer_description: str,
             company_name: str | None, profile_text: str) -> bool:
    markdown, structured, trace = generate_analysis(result, offer_title, offer_description, company_name)

    problems = []
    problems += check_sections(markdown)
    problems += check_no_mobility(markdown, result.geography_zone)
    problems += check_no_fabricated_skills(markdown, result.matches, profile_text)
    problems += check_structured_matches_scoring(structured, result)

    ok = not problems
    status = "OK" if ok else "FAIL"
    print(f"\n[{status}] {label} (zone={result.geography_zone}, {len(markdown)} caractères, "
          f"structured: {len(structured.matches)} matches / {len(structured.gaps)} gaps / "
          f"{len(structured.uncertain_flags)} uncertain)")
    for p in problems:
        print(f"       - {p}")
    return ok, markdown, structured, trace


def main() -> None:
    profile_text = load_profile_text()
    failures = 0
    total = 0

    # Cases already validated manually this session: offers 7, 15, 24.
    for offer_id in (7, 15, 24):
        offer = load_offer(offer_id)
        result = score_offer(
            offer_id=offer["id"], title=offer["title"], location=offer["location"],
            description=offer["description"],
        )
        ok, _md, structured, _trace = run_case(f"offre {offer_id}", result, offer["title"], offer["description"], offer["company"], profile_text)
        expected = EXPECTED_GAPS_UNCERTAIN.get(offer_id)
        if expected is not None:
            exp_gaps, exp_uncertain = expected
            if len(structured.gaps) != exp_gaps or len(structured.uncertain_flags) != exp_uncertain:
                print(f"       - [WARN] offre {offer_id}: {len(structured.gaps)} gaps / "
                      f"{len(structured.uncertain_flags)} uncertain, valeur historiquement observée "
                      f"{exp_gaps} gaps / {exp_uncertain} uncertain (le scoring LLM n'est pas déterministe, "
                      f"un écart n'est pas forcément une régression — voir ROADMAP.md)")
        total += 1
        failures += 0 if ok else 1

    # New case: short/generic offer, to exercise the web_search path.
    short_title = "Data Analyst"
    short_description = (
        "Data Analyst recherché. Poste basé à Lyon. Expérience SQL et Power BI "
        "souhaitée. CDI."
    )
    assert _should_search_web(short_title, short_description), (
        "_should_search_web devrait se déclencher sur une description courte/générique"
    )
    result = ScoringResult(
        offer_id=9999,
        score=60,
        geography_zone="rhone_alpes",
        geography_priority_rank=2,
        matches=[
            {"skill": "SQL", "matched_chunk_summary": "SQL (requêtes avancées, agrégations, optimisation)."},
            {"skill": "Power BI", "matched_chunk_summary": "Power BI (DAX avancé, Power Query)."},
        ],
        gaps=[],
        uncertain_flags=[],
        reasoning_summary="Offre générique mais compétences de base alignées.",
        trace=None,
    )
    ok, md, structured, trace = run_case(
        "offre courte/générique (test web_search)", result, short_title, short_description,
        "Entreprise Test SARL", profile_text,
    )
    total += 1
    failures += 0 if ok else 1

    assert trace.web_search_used is True, "web_search aurait dû être déclenché sur cette offre courte"
    assert trace.web_search_result is None, "web_search doit retourner None (stub désactivé)"
    print(f"       web_search_used={trace.web_search_used}, web_search_result={trace.web_search_result!r}")

    Path("tests/generation_web_search_case.md").write_text(md, encoding="utf-8")
    Path("tests/generation_web_search_case_trace.json").write_text(trace_to_json(trace), encoding="utf-8")
    Path("tests/generation_web_search_case_structured.json").write_text(
        structured_analysis_to_json(structured), encoding="utf-8"
    )

    print(f"\n{total - failures}/{total} cas passés")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
