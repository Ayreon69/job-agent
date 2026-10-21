"""FastAPI wrapper: the dashboard, read access to the offers, and the
orchestrator (session 5) over HTTP.

Pure exposition, no new decision logic: every endpoint calls into
orchestrator/ or storage/db.py as-is. If a decision needs to change, it
belongs in orchestrator/agent.py, not here.

Run locally:
    uvicorn api.main:app --reload
    (from the job-agent/ directory, with .venv activated; DATABASE_URL and
    MISTRAL_API_KEY come from .env, loaded by storage.db)

API_MODE: "full" (default — local dev, docker-compose) or "readonly" (the
deployed dashboard). Render's free tier caps at 512MB RAM; the "full"
container measured ~749MB at rest (sentence-transformers + torch, loaded for
POST /analyze). "readonly" trades /analyze away — scoring is GitHub
Actions' job — and never imports that stack: torch's C extension is loaded
the moment its module is imported, before anything is instantiated, so the
orchestrator import is deferred to inside /analyze rather than done at the
top of this file.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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
from storage.db import USER_VERDICTS, connect, parse_published_at, set_user_verdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

VALID_API_MODES = ("full", "readonly")
API_MODE = os.environ.get("API_MODE", "full").strip().lower()
if API_MODE not in VALID_API_MODES:
    logger.warning("API_MODE=%r inconnu, repli sur 'full' (valeurs valides: %s)", API_MODE, VALID_API_MODES)
    API_MODE = "full"


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    version="0.2.0",
    lifespan=lifespan,
)

STATIC_DIR = Path(__file__).parent / "static"

# Dashboard (session 9): a static HTML/JS page consuming the endpoints below
# client-side — no server-side templating, no JS build step. Mounted at
# /static (not /) so it doesn't shadow the API routes.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# StaticFiles sends ETag/Last-Modified but no Cache-Control, which lets
# browsers apply heuristic caching: after a deploy, a visitor could keep
# running the previous dashboard's JS modules/CSS for hours (seen during the
# session-16 redesign). "no-cache" still caches — it just revalidates
# against the ETag on every load, which is a cheap 304 when nothing changed.
@app.middleware("http")
async def revalidate_static(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


# ---------------------------------------------------------------------
# Offers
# ---------------------------------------------------------------------

def _iso_utc(value: datetime | None) -> str | None:
    """timestamptz -> "2026-10-21T11:58:36Z", whatever the session's time zone."""
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# Sorting jobs.published_at's raw strings lexicographically mixes Hellowork's
# "DD/MM/YYYY" and jobup.ch's French "DD mois AAAA" (e.g. "12 juillet" sorts
# before "13 juin"). parse_published_at (storage/db.py, shared with
# storage/cleanup.py) turns it into a real date; published_at itself keeps
# being shown as-is (its exact source wording is still useful to see).
def _published_at_sortable(raw: str | None) -> str | None:
    parsed = parse_published_at(raw)
    return parsed.isoformat() if parsed else None


OFFER_COLUMNS = (
    "id, title, location, company, url, status, published_at, scraped_at, last_seen_at, user_verdict, "
    "score, geography_zone, sector, gaps_count, uncertain_count, source, contract_type, salary, experience"
)


def _summary_fields(row: dict) -> dict:
    return {
        "id": row["id"], "title": row["title"], "location": row["location"], "company": row["company"],
        "url": row["url"], "status": row["status"], "score": row["score"],
        "geography_zone": row["geography_zone"], "sector": row["sector"],
        "gaps_count": row["gaps_count"], "uncertain_count": row["uncertain_count"],
        "published_at": row["published_at"], "published_at_sortable": _published_at_sortable(row["published_at"]),
        "first_seen_at": _iso_utc(row["scraped_at"]), "last_seen_at": _iso_utc(row["last_seen_at"]),
        "user_verdict": row["user_verdict"], "source": row["source"],
        "contract_type": row["contract_type"], "salary": row["salary"], "experience": row["experience"],
    }


def _fetch_dicts(conn, sql: str, params: tuple = ()) -> list[dict]:
    cursor = conn.execute(sql, params)
    names = [column.name for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


@app.get("/health", response_model=HealthResponse)
def health(response: Response) -> HealthResponse:
    """Distinguishes "the process is up" from "the pipeline is actually
    configured correctly" (session 7 follow-up): a container with a missing
    MISTRAL_API_KEY used to look healthy while every /analyze failed.

    None of the checks makes an LLM call — this endpoint must stay cheap to
    poll:
      - mistral_key_present: presence only, not validity.
      - embeddings_loaded: the session-6 singleton's state, read WITHOUT
        constructing it; None in API_MODE=readonly, where the model is never
        loaded by design (importing scoring.embeddings.index would pull
        torch into a process that's specifically avoiding it).
      - database_accessible: a connection opens and answers SELECT 1.

    200 when every applicable check passes, 503 otherwise: monitoring
    (Docker's HEALTHCHECK, Render's poller) acts on the status code, and a
    200 with "degraded" in the body would be ignored by anything checking
    for a 2xx.
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
        logger.exception("Base de données injoignable")
        database_accessible = False

    checks = HealthChecks(
        mistral_key_present=mistral_key_present,
        embeddings_loaded=embeddings_loaded,
        database_accessible=database_accessible,
    )
    # embeddings_loaded=None (readonly mode) is "not applicable", not "failed".
    required_checks = [mistral_key_present, database_accessible]
    if embeddings_loaded is not None:
        required_checks.append(embeddings_loaded)
    all_ok = all(required_checks)
    response.status_code = 200 if all_ok else 503

    return HealthResponse(status="ok" if all_ok else "degraded", checks=checks)


@app.get("/offers", response_model=list[OfferSummary])
def list_offers() -> list[OfferSummary]:
    """Every offer, without description or analysis (see GET /offers/{id})."""
    with connect() as conn:
        rows = _fetch_dicts(conn, f"SELECT {OFFER_COLUMNS} FROM jobs ORDER BY id")
    return [OfferSummary(**_summary_fields(row)) for row in rows]


@app.get("/offers/{offer_id}", response_model=OfferDetailResponse)
def get_offer(offer_id: int) -> OfferDetailResponse:
    """One offer with its description. 404 if offer_id doesn't exist."""
    with connect() as conn:
        rows = _fetch_dicts(conn, f"SELECT {OFFER_COLUMNS}, description FROM jobs WHERE id = %s", (offer_id,))
    if not rows:
        raise HTTPException(status_code=404, detail=f"Offre {offer_id} introuvable")
    return OfferDetailResponse(**_summary_fields(rows[0]), description=rows[0]["description"])


@app.post("/offers/{offer_id}/verdict", response_model=VerdictResponse)
def set_offer_verdict(offer_id: int, request: VerdictRequest) -> VerdictResponse:
    """Record (or clear) the user's own triage decision for an offer — the
    dashboard's swipe UI. Pure human judgment: never read, computed, or
    influenced by the scoring/generation pipeline. Available in both
    API_MODE values (a plain database write, no model or LLM involved).

    404 if offer_id doesn't exist, 422 if verdict isn't one of
    storage.db.USER_VERDICTS or null.
    """
    if request.verdict is not None and request.verdict not in USER_VERDICTS:
        raise HTTPException(
            status_code=422,
            detail=f"verdict invalide {request.verdict!r}, attendu un de {USER_VERDICTS} ou null",
        )

    with connect() as conn:
        exists = conn.execute("SELECT 1 FROM jobs WHERE id = %s", (offer_id,)).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail=f"Offre {offer_id} introuvable")
        set_user_verdict(conn, offer_id, request.verdict)

    return VerdictResponse(id=offer_id, user_verdict=request.verdict)


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """Run the orchestrator (scoring -> generation) on one offer already in
    the database; the analysis is stored like in a batch run. Synchronous:
    at least three real LLM calls plus local RAG lookups, several seconds to
    ~30s — set an HTTP client timeout of at least 60s. No job queue on
    purpose (ROADMAP.md session 6).

    Disabled in API_MODE=readonly: 503 rather than crashing on an unloaded
    embedding model / OOM under Render's 512MB. 503, not 409: it isn't a
    conflict with the resource's state, it's a permanent characteristic of
    this deployment (scoring is GitHub Actions' job).
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

    with connect() as conn:
        rows = _fetch_dicts(
            conn, "SELECT id, title, location, description, company, url FROM jobs WHERE id = %s", (request.offer_id,)
        )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Offre {request.offer_id} introuvable")

    from orchestrator.agent import process_offer

    result = process_offer(rows[0])
    return AnalyzeResponse(
        offer_id=result.offer_id,
        status=result.status,
        analysis_markdown=result.analysis_markdown,
        trace_summary=list(result.trace.decisions),
        error=result.trace.error,
    )
