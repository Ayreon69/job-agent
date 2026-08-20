"""FastAPI wrapper exposing the existing orchestrator (session 5) over HTTP.

Pure exposition, no new decision logic: every endpoint calls into
orchestrator/, scoring/, generation/, or storage/db.py as-is. If a decision
needs to change, it belongs in orchestrator/agent.py, not here.

Run locally:
    uvicorn api.main:app --reload
    (from the job-agent/ directory, with .venv activated)

MISTRAL_API_KEY is loaded exactly as scoring/llm.py already does (via
python-dotenv + os.environ) — importing scoring.llm triggers that load_dotenv()
call, so this module doesn't duplicate the .env loading logic.

API_MODE (Render deployment follow-up): "full" (default, unchanged behavior —
local dev, docker-compose, GitHub Actions batch don't set this var) or
"readonly". Render's free/Starter tiers cap at 512MB RAM; a real measurement
of the "full" container at rest was ~749MB (sentence-transformers + torch
loaded via the session-6 embedding singleton) — over budget on either tier.
"readonly" trades away POST /analyze (scoring is Render's job never anyway;
GitHub Actions already owns the batch pipeline, see session 8) to stay under
that budget: GET /health, /offers, /offers/{id} only need SQLite +
already-generated structured_analysis_<id>.json/markdown files on disk, none
of which need the embedding model or ChromaDB.

The memory saving comes from WHERE the import of scoring.embeddings.index
(and therefore chromadb + sentence-transformers + torch) happens, not just
from skipping construction of the singleton: torch's own C extension gets
loaded into the process the moment its Python module is imported, before any
class is ever instantiated. orchestrator.agent (imported by /analyze)
imports scoring.agent at module top level, which imports
scoring.embeddings.index — so importing orchestrator.agent unconditionally
at the top of this file would load torch into every readonly-mode process
too, defeating the point. The import is therefore deferred to inside the
/analyze handler itself (see analyze() below), executed only if API_MODE
allows it.
"""

from __future__ import annotations

import logging
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import scoring.llm  # noqa: F401  (side effect: load_dotenv() for MISTRAL_API_KEY)
from api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    HealthChecks,
    HealthResponse,
    OfferDetailResponse,
    OfferSummary,
    VerdictRequest,
    VerdictResponse,
)
from storage.db import USER_VERDICTS, connect, init_db, set_user_verdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

VALID_API_MODES = ("full", "readonly")
API_MODE = os.environ.get("API_MODE", "full").strip().lower()
if API_MODE not in VALID_API_MODES:
    logger.warning("API_MODE=%r inconnu, repli sur 'full' (valeurs valides: %s)", API_MODE, VALID_API_MODES)
    API_MODE = "full"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    if API_MODE == "readonly":
        logger.info("API_MODE=readonly — modèle d'embeddings/ChromaDB non chargés (POST /analyze désactivé)")
        yield
        return

    # Load the embedding model + ChromaDB client eagerly at startup rather
    # than lazily on the first /analyze request (session 6 follow-up): the
    # first construction of SentenceTransformerEmbeddingFunction pays ~12s of
    # HuggingFace Hub HEAD requests (verifying the local model cache is
    # current), even though chromadb caches the actual model weights
    # process-wide afterwards. Paying that cost here means the FIRST real
    # request is as fast as every subsequent one, not ~12s slower.
    from scoring.embeddings.index import get_client, get_embedding_function

    t0 = time.monotonic()
    get_embedding_function()
    get_client()
    logger.info("Modèle d'embeddings chargé au démarrage en %.2fs", time.monotonic() - t0)
    yield


app = FastAPI(
    title="job-agent API",
    description=(
        "Wraps the existing scoring -> generation orchestrator (sessions 3-5) over HTTP. "
        "Never submits a candidacy automatically — see CLAUDE.md."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Same path orchestrator/run.py's own DEFAULT_OUTPUT_DIR resolves to
# (orchestrator/runs/, relative to that module's location) — computed here
# directly rather than imported from orchestrator.run, because that module
# imports orchestrator.agent at its own top level, which imports
# scoring.agent -> scoring.embeddings.index -> chromadb/torch. Every
# readonly-safe endpoint (health, offers, offers/{id}) needs this path, so
# it can't depend on an import chain that pulls in the very weight
# API_MODE=readonly exists to avoid.
RUNS_DIR = Path(__file__).parent.parent / "orchestrator" / "runs"
STATIC_DIR = Path(__file__).parent / "static"

# Dashboard (session 9): a static HTML/JS page consuming GET /offers and
# GET /offers/{id} client-side — no server-side templating, no new backend
# logic. Served by FastAPI's own StaticFiles rather than a separate
# frontend server: for a single-user read-only dashboard, standing up a
# second process (or a JS build toolchain) would add operational surface
# without buying anything a `fetch()` against the API already running here
# can't do plainly. Mounted at /static (not /) so it doesn't shadow the
# /offers, /health, /analyze API routes below.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


# published_at is stored verbatim, in whichever format the source site used
# at scrape time (see scraper/hellowork.py and scraper/jobup.py) — NOT
# normalized to one format at scrape time. Two formats exist in practice:
# Hellowork's "DD/MM/YYYY" and jobup.ch's French "DD mois AAAA" (session
# 11). Sorting the raw strings lexicographically mixes the two conventions
# (e.g. "12 juillet" sorts before "13 juin" — alphabetical on the month
# NAME, not the month number) — reported by the user after the first
# published_at/first_seen_at dashboard rollout. Parsed here into a real
# date, exposed as a separate ISO field the dashboard sorts on, while
# published_at itself keeps being shown as-is (its exact source wording is
# still useful to see, just not useful to sort by).
_MOIS_FR = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}
_PUBLISHED_AT_SLASH_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_PUBLISHED_AT_FR_RE = re.compile(r"^(\d{1,2})\s+([a-zéû]+)\s+(\d{4})$", re.IGNORECASE)


def _parse_published_at(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()

    slash_match = _PUBLISHED_AT_SLASH_RE.match(raw)
    if slash_match:
        day, month, year = (int(g) for g in slash_match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None

    fr_match = _PUBLISHED_AT_FR_RE.match(raw)
    if fr_match:
        day_str, month_name, year_str = fr_match.groups()
        month = _MOIS_FR.get(month_name.lower())
        if month is None:
            return None
        try:
            return date(int(year_str), month, int(day_str)).isoformat()
        except ValueError:
            return None

    return None


def _load_offer_row(offer_id: int) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, title, location, description, company, url, status, published_at, scraped_at, user_verdict "
            "FROM jobs WHERE id = ?",
            (offer_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Offre {offer_id} introuvable")
    return {
        "id": row[0], "title": row[1], "location": row[2], "description": row[3],
        "company": row[4], "url": row[5], "status": row[6], "published_at": row[7],
        "scraped_at": row[8], "user_verdict": row[9],
    }


def _read_json_trace(offer_id: int, prefix: str) -> dict | None:
    path = RUNS_DIR / f"{prefix}_{offer_id}.json"
    if not path.exists():
        return None
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _read_markdown(offer_id: int) -> str | None:
    path = RUNS_DIR / f"analysis_{offer_id}.md"
    return path.read_text(encoding="utf-8") if path.exists() else None


def _read_structured_analysis(offer_id: int) -> dict | None:
    """matches/gaps/uncertain_flags, straight from generation's
    StructuredAnalysis (session 9 follow-up) — a faithful, non-LLM
    reformatting of ScoringResult's own fields, persisted by
    orchestrator/run.py as structured_analysis_<id>.json. Replaces the
    earlier markdown-reparsing approach (_parse_gaps_and_uncertain /
    _parse_matching_summary, removed): that parsed prose whose subheading
    wording wasn't contractual, which worked in practice but depended on an
    LLM output format with no guarantee. This reads a field the generation
    agent commits to directly instead.
    """
    return _read_json_trace(offer_id, "structured_analysis")


def _score_and_zone_from_trace(offer_id: int) -> tuple[int | None, str | None]:
    """score isn't stored in scoring's own trace JSON (only geography/RAG
    steps are) — reconstructed here from the orchestrator's own decision log
    line, which records it in plain text ("scoring terminé: score=X, zone=Y, ...").
    A small text scrape rather than adding a new persisted field, since the
    orchestrator trace already carries this information.
    """
    orch_trace = _read_json_trace(offer_id, "trace_orchestrator")
    if not orch_trace:
        return None, None
    for decision in orch_trace.get("decisions", []):
        if decision.startswith("scoring terminé:"):
            import re

            score_match = re.search(r"score=(\d+)", decision)
            zone_match = re.search(r"zone=(\w+)", decision)
            return (
                int(score_match.group(1)) if score_match else None,
                zone_match.group(1) if zone_match else None,
            )
    return None, None


@app.get("/health", response_model=HealthResponse)
def health(response: Response) -> HealthResponse:
    """Distinguishes "the process is up" from "the pipeline is actually
    configured correctly" (session 7 follow-up — the previous version always
    returned 200 {"status": "ok"} as long as the process was alive, which
    would NOT have caught a docker-compose up with a missing/empty
    MISTRAL_API_KEY: the container would look healthy while every /analyze
    silently failed).

    Three checks, none of which make a network call (deliberately — this
    endpoint must stay cheap to poll and must never spend a real Mistral
    request just to answer a health check):
      - mistral_key_present: presence/non-emptiness only, not validity. A
        real Mistral call would be needed to confirm the key actually
        authenticates, which is out of scope here by design.
      - embeddings_loaded: reads the session-6 singleton state via
        is_initialized() WITHOUT constructing it — if the lifespan startup
        hook failed to load the model, this reports that failure instead of
        lazily loading the model just to make the check pass. In
        API_MODE=readonly (Render deployment follow-up), the embedding
        model is never loaded BY DESIGN (that's the whole memory saving —
        see module docstring), so this check is skipped entirely rather
        than reported as a false "degraded": is_initialized() itself isn't
        even called, since merely importing scoring.embeddings.index would
        pull chromadb/torch into a process that's specifically trying not
        to carry that weight.
      - database_accessible: SQLite connection opens and answers a trivial
        query — not a full read/write test, just reachability.

    HTTP status: 200 when every applicable check passes, 503 (Service
    Unavailable) if any fails. Decision: a monitoring/orchestration layer
    (e.g. Docker's own HEALTHCHECK, Render's health check poller, or a
    future load balancer) needs the STATUS CODE to act automatically — a
    200 with "degraded" buried in the JSON body would be silently ignored
    by anything that only checks for a 2xx response, which defeats the
    point of catching this at the container level rather than at the first
    failed /analyze.
    """
    mistral_key_present = bool(os.environ.get("MISTRAL_API_KEY", "").strip())

    if API_MODE == "readonly":
        embeddings_loaded = None
    else:
        from scoring.embeddings.index import is_initialized

        embeddings_loaded = is_initialized()

    try:
        with connect() as conn:
            conn.execute("SELECT 1")
        database_accessible = True
    except Exception:
        database_accessible = False

    checks = HealthChecks(
        mistral_key_present=mistral_key_present,
        embeddings_loaded=embeddings_loaded,
        database_accessible=database_accessible,
    )
    # embeddings_loaded=None (readonly mode) is deliberately excluded from
    # the all_ok computation — it's "not applicable", not "failed".
    required_checks = [mistral_key_present, database_accessible]
    if embeddings_loaded is not None:
        required_checks.append(embeddings_loaded)
    all_ok = all(required_checks)
    response.status_code = 200 if all_ok else 503

    return HealthResponse(status="ok" if all_ok else "degraded", checks=checks)


@app.get("/offers", response_model=list[OfferSummary])
def list_offers() -> list[OfferSummary]:
    """Lightweight listing for a dashboard-style view: status, score, zone,
    title — not the full analysis or trace (see GET /offers/{id} for that).
    """
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, title, location, company, status, published_at, scraped_at, user_verdict "
            "FROM jobs ORDER BY id"
        ).fetchall()

    summaries = []
    for r in rows:
        offer_id = r[0]
        score, zone = _score_and_zone_from_trace(offer_id)
        structured = _read_structured_analysis(offer_id)
        gaps_count = len(structured["gaps"]) if structured else None
        uncertain_count = len(structured["uncertain_flags"]) if structured else None
        summaries.append(
            OfferSummary(
                id=offer_id, title=r[1], location=r[2], company=r[3],
                status=r[4], score=score, geography_zone=zone,
                gaps_count=gaps_count, uncertain_count=uncertain_count,
                published_at=r[5], published_at_sortable=_parse_published_at(r[5]),
                first_seen_at=r[6], user_verdict=r[7],
            )
        )
    return summaries


@app.get("/offers/{offer_id}", response_model=OfferDetailResponse)
def get_offer(offer_id: int) -> OfferDetailResponse:
    """Full detail for one already-processed offer: markdown analysis (if
    any), and the three traces (orchestrator/scoring/generation) as recorded
    on disk by orchestrator/run.py. A 404 here means the offer_id itself
    doesn't exist in SQLite — an offer that exists but hasn't been analyzed
    yet returns 200 with null analysis/traces (status='nouveau').
    """
    offer = _load_offer_row(offer_id)
    score, zone = _score_and_zone_from_trace(offer_id)
    structured = _read_structured_analysis(offer_id)
    return OfferDetailResponse(
        id=offer["id"],
        title=offer["title"],
        location=offer["location"],
        company=offer["company"],
        url=offer["url"],
        status=offer["status"],
        score=score,
        geography_zone=zone,
        published_at=offer["published_at"],
        published_at_sortable=_parse_published_at(offer["published_at"]),
        first_seen_at=offer["scraped_at"],
        user_verdict=offer["user_verdict"],
        matches=structured["matches"] if structured else [],
        gaps=structured["gaps"] if structured else [],
        uncertain_flags=structured["uncertain_flags"] if structured else [],
        analysis_markdown=_read_markdown(offer_id),
        orchestrator_trace=_read_json_trace(offer_id, "trace_orchestrator"),
        scoring_trace=_read_json_trace(offer_id, "trace_scoring"),
        generation_trace=_read_json_trace(offer_id, "trace_generation"),
    )


@app.post("/offers/{offer_id}/verdict", response_model=VerdictResponse)
def set_offer_verdict(offer_id: int, request: VerdictRequest) -> VerdictResponse:
    """Record (or clear) the user's own manual triage decision for an offer
    — the dashboard's swipe UI. Pure human judgment: never read, computed,
    or influenced by the scoring/generation pipeline, and available in both
    API_MODE values (a plain SQLite write, no embedding model or LLM call
    involved) — unlike POST /analyze, this isn't gated to "full" mode.

    404 if the offer_id doesn't exist (same existence check as the other
    offer endpoints); 422 (via Pydantic/FastAPI's own validation, not a
    custom check here) if verdict isn't one of storage.db.USER_VERDICTS or
    null.
    """
    _load_offer_row(offer_id)  # raises 404 if missing, discarding the row otherwise
    if request.verdict is not None and request.verdict not in USER_VERDICTS:
        raise HTTPException(
            status_code=422,
            detail=f"verdict invalide {request.verdict!r}, attendu un de {USER_VERDICTS} ou null",
        )

    with connect() as conn:
        set_user_verdict(conn, offer_id, request.verdict)

    return VerdictResponse(id=offer_id, user_verdict=request.verdict)


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """Run the orchestrator (scoring -> generation) on one offer already in
    SQLite. Synchronous: this call blocks for the duration of at least two
    real LLM calls (extraction + arbitrage in scoring, one more in
    generation) plus local RAG lookups — in practice several seconds to
    ~30s depending on offer size and Mistral API latency. Set an HTTP client
    timeout of at least 60s when calling this endpoint; no background-task
    queue is implemented in this session (see ROADMAP.md session 6 for the
    tradeoff — kept deliberately synchronous to avoid the added complexity
    of a job queue at this stage).

    Only accepts an offer_id already present in the database (from a prior
    scraper run) — scraping an arbitrary URL on the fly is left as a future
    iteration (see ROADMAP.md).

    Disabled in API_MODE=readonly (Render deployment follow-up): 503 Service
    Unavailable rather than attempting to run and crashing on an unloaded
    embedding model / OOM under Render's 512MB tiers. 503 chosen over 409:
    this isn't a state conflict on the resource (an offer_id, a request body)
    — it's a permanent characteristic of THIS deployment (scoring/generation
    is GitHub Actions' job, see session 8; this deployment only serves
    already-computed results), which is exactly what 503 communicates for an
    endpoint that legitimately isn't available here, as opposed to 409's
    "you conflicted with existing state" semantics.
    """
    if API_MODE == "readonly":
        raise HTTPException(
            status_code=503,
            detail=(
                "Scoring désactivé sur ce déploiement (API_MODE=readonly) — le pipeline "
                "scoring/génération est géré par GitHub Actions (voir ROADMAP.md session 8), "
                "pas par ce déploiement en lecture seule. Consultez GET /offers et "
                "GET /offers/{id} pour les résultats déjà calculés."
            ),
        )

    from orchestrator.agent import process_offer
    from orchestrator.run import write_outputs

    offer = _load_offer_row(request.offer_id)
    result = process_offer(offer)
    write_outputs(RUNS_DIR, request.offer_id, result)

    trace_summary = list(result.trace.decisions)

    return AnalyzeResponse(
        offer_id=result.offer_id,
        status=result.status,
        analysis_markdown=result.analysis_markdown,
        trace_summary=trace_summary,
        error=result.trace.error,
    )
