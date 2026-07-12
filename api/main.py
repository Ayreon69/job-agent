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


def _parse_gaps_and_uncertain(markdown: str) -> tuple[list[str], list[str]]:
    """Extract short gap/uncertain-flag labels from the analysis markdown for
    the dashboard's flag counts (session 9).

    No structured field carries this in the traces (scoring's own trace JSON
    only has `uncertain_flags`, and even that one doesn't record `gaps` —
    both live only as prose inside the LLM-generated markdown, see
    ScoringResult vs trace_scoring_<id>.json). Since the generation prompt
    fixes the top-level heading ("## Gaps et incertitudes", enforced and
    tested in tests/test_generation.py) but not the subheading wording or
    bullet style beneath it — real examples vary between "### Gaps confirmés
    (compétences absentes)", "### **Gaps confirmés**", "**Gaps confirmés
    (...) :**", etc. — this parses by position (everything between the
    top-level heading and the next one) and by list-item syntax ("- " or
    "N. "), not by matching a fixed subheading string. A "confirmés"/
    "incertains" keyword split tracks which half of the section each bullet
    belongs to. Bold **Label** prefixes are extracted as the short label;
    lines with no bold prefix are skipped (e.g. explanatory continuation
    lines under a numbered item) to avoid double-counting one gap as two
    bullets.
    """
    lines = markdown.splitlines()
    section_start = next((i for i, l in enumerate(lines) if l.strip() == "## Gaps et incertitudes"), None)
    if section_start is None:
        return [], []

    section_end = next(
        (i for i in range(section_start + 1, len(lines)) if lines[i].strip().startswith("## ")),
        len(lines),
    )
    section_lines = lines[section_start + 1 : section_end]

    gaps: list[str] = []
    uncertain: list[str] = []
    current_bucket = gaps  # gaps come first in the fixed section order

    import re

    label_re = re.compile(r"^[-*]\s+\*\*(.+?)\*\*|^\d+\.\s+\*\*(.+?)\*\*")

    for line in section_lines:
        stripped = line.strip()
        lower = stripped.lower()
        if "incertain" in lower and ("flag" in lower or "###" in stripped or stripped.startswith("**")):
            current_bucket = uncertain
            continue
        if lower.startswith(("*aucun", "aucun flag", "aucun gap")):
            continue
        match = label_re.match(stripped)
        if match:
            label = (match.group(1) or match.group(2)).strip()
            current_bucket.append(label)

    return gaps, uncertain


def _parse_matching_summary(markdown: str) -> str | None:
    """First bullet under "## Résumé du matching" as a short matching summary
    (session 9 dashboard detail panel) — deliberately not the full section,
    which can run to 6+ bullets of prose. Same positional approach as
    _parse_gaps_and_uncertain: the top-level heading is fixed by the
    generation prompt, but the subheading immediately below it varies
    ("**Points forts alignés sur l'offre :**", "### Points forts majeurs",
    "**Points forts clés** :", ...) so this skips straight to the first
    real list item rather than matching a fixed subheading string.
    """
    lines = markdown.splitlines()
    section_start = next((i for i, l in enumerate(lines) if l.strip() == "## Résumé du matching"), None)
    if section_start is None:
        return None

    import re

    item_re = re.compile(r"^[-*]\s+(.+)")
    for line in lines[section_start + 1 :]:
        stripped = line.strip()
        if stripped.startswith("## "):
            break
        match = item_re.match(stripped)
        if match:
            return match.group(1).strip()
    return None


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
        markdown = _read_markdown(offer_id)
        gaps_count = uncertain_count = None
        if markdown:
            gaps, uncertain = _parse_gaps_and_uncertain(markdown)
            gaps_count, uncertain_count = len(gaps), len(uncertain)
        summaries.append(
            OfferSummary(
                id=offer_id, title=r[1], location=r[2], company=r[3],
                status=r[4], score=score, geography_zone=zone,
                gaps_count=gaps_count, uncertain_count=uncertain_count,
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
    markdown = _read_markdown(offer_id)
    gaps, uncertain = _parse_gaps_and_uncertain(markdown) if markdown else ([], [])
    return OfferDetailResponse(
        id=offer["id"],
        title=offer["title"],
        location=offer["location"],
        company=offer["company"],
        url=offer["url"],
        status=offer["status"],
        score=score,
        geography_zone=zone,
        matching_summary=_parse_matching_summary(markdown) if markdown else None,
        gaps=gaps,
        uncertain_flags=uncertain,
        analysis_markdown=markdown,
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
