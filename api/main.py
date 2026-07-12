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
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response

import scoring.llm  # noqa: F401  (side effect: load_dotenv() for MISTRAL_API_KEY)
from api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    HealthChecks,
    HealthResponse,
    OfferDetailResponse,
    OfferSummary,
)
from orchestrator.agent import process_offer
from orchestrator.run import write_outputs, DEFAULT_OUTPUT_DIR
from scoring.embeddings.index import get_client, get_embedding_function, is_initialized
from storage.db import connect, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Load the embedding model + ChromaDB client eagerly at startup rather
    # than lazily on the first /analyze request (session 6 follow-up): the
    # first construction of SentenceTransformerEmbeddingFunction pays ~12s of
    # HuggingFace Hub HEAD requests (verifying the local model cache is
    # current), even though chromadb caches the actual model weights
    # process-wide afterwards. Paying that cost here means the FIRST real
    # request is as fast as every subsequent one, not ~12s slower.
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

RUNS_DIR = DEFAULT_OUTPUT_DIR


def _load_offer_row(offer_id: int) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, title, location, description, company, url, status "
            "FROM jobs WHERE id = ?",
            (offer_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Offre {offer_id} introuvable")
    return {
        "id": row[0], "title": row[1], "location": row[2], "description": row[3],
        "company": row[4], "url": row[5], "status": row[6],
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
        lazily loading the model just to make the check pass.
      - database_accessible: SQLite connection opens and answers a trivial
        query — not a full read/write test, just reachability.

    HTTP status: 200 when every check passes, 503 (Service Unavailable) if
    any fails. Decision: a monitoring/orchestration layer (e.g. Docker's own
    HEALTHCHECK, or a future load balancer) needs the STATUS CODE to act
    automatically — a 200 with "degraded" buried in the JSON body would be
    silently ignored by anything that only checks for a 2xx response, which
    defeats the point of catching this at the container level rather than
    at the first failed /analyze.
    """
    mistral_key_present = bool(os.environ.get("MISTRAL_API_KEY", "").strip())
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
    all_ok = mistral_key_present and embeddings_loaded and database_accessible
    response.status_code = 200 if all_ok else 503

    return HealthResponse(status="ok" if all_ok else "degraded", checks=checks)


@app.get("/offers", response_model=list[OfferSummary])
def list_offers() -> list[OfferSummary]:
    """Lightweight listing for a dashboard-style view: status, score, zone,
    title — not the full analysis or trace (see GET /offers/{id} for that).
    """
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, title, location, company, status FROM jobs ORDER BY id"
        ).fetchall()

    summaries = []
    for r in rows:
        offer_id = r[0]
        score, zone = _score_and_zone_from_trace(offer_id)
        summaries.append(
            OfferSummary(
                id=offer_id, title=r[1], location=r[2], company=r[3],
                status=r[4], score=score, geography_zone=zone,
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
    return OfferDetailResponse(
        id=offer["id"],
        title=offer["title"],
        location=offer["location"],
        company=offer["company"],
        url=offer["url"],
        status=offer["status"],
        analysis_markdown=_read_markdown(offer_id),
        orchestrator_trace=_read_json_trace(offer_id, "trace_orchestrator"),
        scoring_trace=_read_json_trace(offer_id, "trace_scoring"),
        generation_trace=_read_json_trace(offer_id, "trace_generation"),
    )


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
    """
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
