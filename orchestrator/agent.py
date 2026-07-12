"""Top-level orchestrator: chains scoring (session 3) into generation
(session 4) for a job offer, but makes real decisions about the pipeline
instead of following a fixed sequence unconditionally.

What makes this an orchestrator rather than a plain sequential script — three
decision points, checked in priority order before/during the default path:

  1. Insufficient offer description: if the offer text in SQLite is too thin
     to score meaningfully (same heuristic as generation's
     _should_search_web, reused here — a short offer is a short offer
     regardless of which downstream step cares), attempt a targeted
     re-scrape of the offer's URL (scraper/hellowork.py, reusing
     fetch_job_detail rather than a fresh full search) BEFORE scoring. If
     the re-scrape fails or doesn't add anything, continue anyway but log
     that this was a deliberate, logged choice — not a silent gap.
  2. Unknown geography zone: if check_geography_rules (session 3) returns
     zone="inconnu", the orchestrator does NOT stop the pipeline — scoring
     and generation still run — but the final status is
     "a_valider_geographie" rather than "analyse", so a human knows not to
     trust the generated tone silently.
  3. Any technical failure (malformed offer row, LLM call exception,
     uncaught exception anywhere in scoring/generation): caught, logged with
     full context for later debugging, offer marked "echec" in SQLite, and
     the orchestrator moves on to the next offer rather than crashing the
     whole batch run.

Every decision the orchestrator itself makes (not just the RAG queries made
by scoring/generation, which have their own traces) is recorded in an
OrchestratorTrace for audit.

Hard rule (CLAUDE.md): the orchestrator NEVER submits a candidacy
automatically. It stops after producing the analysis; human validation is a
mandatory checkpoint before any external action (sending, applying, etc.).
This module has no code path that sends anything anywhere.
"""

from __future__ import annotations

import json
import logging
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from generation.analysis import generate_analysis
from generation.analysis import structured_analysis_to_json
from generation.analysis import trace_to_json as generation_trace_to_json
from scoring.agent import score_offer
from scoring.agent import trace_to_json as scoring_trace_to_json
from scraper.hellowork import JobListing, fetch_job_detail
from storage.db import connect, set_job_status

logger = logging.getLogger(__name__)

# Same threshold as generation.analysis._should_search_web: below this many
# characters (title + description combined), an offer is too thin to trust
# for scoring, not just for grounding a candidacy angle.
MIN_OFFER_TEXT_LENGTH = 300


@dataclass
class OrchestratorTrace:
    offer_id: int
    decisions: list[str] = field(default_factory=list)
    final_status: str | None = None
    error: str | None = None

    def log(self, message: str) -> None:
        self.decisions.append(message)
        logger.info("[offer %s] %s", self.offer_id, message)


@dataclass
class OrchestrationResult:
    offer_id: int
    status: str
    analysis_markdown: str | None
    trace: OrchestratorTrace
    scoring_trace_json: str | None = None
    generation_trace_json: str | None = None
    structured_analysis_json: str | None = None


def _offer_text_is_thin(title: str, description: str | None) -> bool:
    return len(f"{title or ''} {description or ''}".strip()) < MIN_OFFER_TEXT_LENGTH


def _attempt_rescrape(trace: OrchestratorTrace, offer: dict) -> str | None:
    """Try to re-fetch a fuller description from the offer's own URL.

    Returns the new description if the re-scrape produced something usable,
    None otherwise (any failure is caught here — a re-scrape is a best-effort
    enrichment, never something that should crash the pipeline).
    """
    listing = JobListing(
        source_id=str(offer["id"]),
        url=offer["url"],
        title=offer["title"] or "",
        company=offer.get("company"),
        location=offer.get("location"),
        contract_type=None,
    )
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                detail = fetch_job_detail(page, listing)
            finally:
                browser.close()
    except Exception as exc:
        trace.log(f"re-scraping échoué ({exc!r}) — poursuite avec la description existante en connaissance de cause")
        return None

    new_description = detail.get("description")
    if not new_description or len(new_description) <= len(offer.get("description") or ""):
        trace.log("re-scraping n'a rien apporté de plus (description vide ou pas plus longue) — poursuite avec la description existante en connaissance de cause")
        return None

    trace.log(f"re-scraping réussi: description enrichie de {len(offer.get('description') or '')} à {len(new_description)} caractères")
    return new_description


def process_offer(offer: dict) -> OrchestrationResult:
    """Run the full scoring -> generation pipeline for one offer, with the
    three orchestrator-level decisions described in the module docstring.

    `offer` is a dict with at least: id, url, title, location, description,
    company.
    """
    offer_id = offer["id"]
    trace = OrchestratorTrace(offer_id=offer_id)

    try:
        # Decision 1: offer too thin to score reliably -> targeted re-scrape.
        description = offer.get("description")
        combined_length = len(f"{offer.get('title', '')} {description or ''}".strip())
        if _offer_text_is_thin(offer.get("title", ""), description):
            trace.log(
                f"description jugée trop courte/tronquée ({combined_length} caractères < "
                f"{MIN_OFFER_TEXT_LENGTH}) — tentative de re-scraping ciblé avant scoring"
            )
            new_description = _attempt_rescrape(trace, offer)
            if new_description:
                description = new_description

        # Default path: scoring, always run (geography included).
        scoring_result = score_offer(
            offer_id=offer_id,
            title=offer["title"],
            location=offer.get("location"),
            description=description,
        )
        trace.log(
            f"scoring terminé: score={scoring_result.score}, zone={scoring_result.geography_zone}, "
            f"gaps={len(scoring_result.gaps)}, uncertain_flags={len(scoring_result.uncertain_flags)}"
        )

        # Decision 2: unknown geography zone -> pipeline continues, but the
        # final status flags the result as needing manual geography review.
        geography_uncertain = scoring_result.geography_zone == "inconnu"
        if geography_uncertain:
            trace.log(
                "zone géographique 'inconnu' détectée — pipeline poursuivi (scoring + génération), "
                "mais le résultat sera marqué 'a_valider_geographie' plutôt que d'appliquer "
                "silencieusement une règle de ton par défaut"
            )

        markdown, structured_analysis, generation_trace = generate_analysis(
            scoring_result,
            offer_title=offer["title"],
            offer_description=description or "",
            company_name=offer.get("company"),
        )
        trace.log("génération de l'analyse terminée")

        final_status = "a_valider_geographie" if geography_uncertain else "analyse"
        trace.final_status = final_status

        with connect() as conn:
            set_job_status(conn, offer_id, final_status)

        return OrchestrationResult(
            offer_id=offer_id,
            status=final_status,
            analysis_markdown=markdown,
            trace=trace,
            scoring_trace_json=scoring_trace_to_json(scoring_result.trace),
            generation_trace_json=generation_trace_to_json(generation_trace),
            structured_analysis_json=structured_analysis_to_json(structured_analysis),
        )

    except Exception as exc:
        # Decision 3: any technical failure -> capture, log with context,
        # mark as "echec" in SQLite, and let the caller continue the batch.
        error_context = (
            f"{type(exc).__name__}: {exc}\n"
            f"offer_id={offer_id}, title={offer.get('title')!r}, url={offer.get('url')!r}\n"
            f"{traceback.format_exc()}"
        )
        trace.error = error_context
        trace.final_status = "echec"
        trace.log(f"échec technique capturé — offre marquée 'echec': {type(exc).__name__}: {exc}")
        logger.error("[offer %s] échec technique:\n%s", offer_id, error_context)

        with connect() as conn:
            set_job_status(conn, offer_id, "echec")

        return OrchestrationResult(
            offer_id=offer_id,
            status="echec",
            analysis_markdown=None,
            trace=trace,
        )


def orchestrator_trace_to_json(trace: OrchestratorTrace) -> str:
    return json.dumps(
        {
            "offer_id": trace.offer_id,
            "decisions": trace.decisions,
            "final_status": trace.final_status,
            "error": trace.error,
        },
        ensure_ascii=False,
        indent=2,
    )
