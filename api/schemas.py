"""Pydantic request/response models for the API — pure serialization shapes,
no business logic. See orchestrator/agent.py and storage/db.py for the
actual data these mirror.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthChecks(BaseModel):
    mistral_key_present: bool = Field(description="MISTRAL_API_KEY is set and non-empty in the environment — presence only, not validity (a real Mistral call would be needed to verify the key actually works, which /health deliberately avoids)")
    embeddings_loaded: bool | None = Field(description="The sentence-transformers model + ChromaDB client singletons (session 6) were constructed successfully at startup, or null if API_MODE=readonly (Render deployment follow-up) — the check doesn't apply since this deployment mode never loads them by design")
    database_accessible: bool = Field(description="The SQLite connection can be opened and responds to a trivial query")


class HealthResponse(BaseModel):
    status: str = Field(description="'ok' if all checks pass, 'degraded' if any check fails")
    checks: HealthChecks


class MatchItem(BaseModel):
    skill: str
    matched_chunk_summary: str = Field(description="Short justification: which profile chunk grounded this match")


class GapItem(BaseModel):
    skill: str
    note: str = Field(description="Short justification for why this is a confirmed gap")


class OfferSummary(BaseModel):
    id: int
    title: str
    location: str | None
    company: str | None
    status: str
    score: int | None = Field(default=None, description="Score 0-100, null if not yet analyzed")
    geography_zone: str | None = Field(default=None, description="Zone from check_geography_rules, null if not yet analyzed")
    gaps_count: int | None = Field(default=None, description="Number of confirmed gaps (ScoringResult.gaps via generation's StructuredAnalysis), null if not yet analyzed")
    uncertain_count: int | None = Field(default=None, description="Number of uncertain flags (ScoringResult.uncertain_flags), null if not yet analyzed")
    published_at: str | None = Field(default=None, description="Publication date as scraped from the source offer (jobs.published_at), format varies by source and is not normalized")
    analyzed_at: str | None = Field(default=None, description="When the orchestrator produced this offer's analysis, ISO 8601 UTC — derived from trace_orchestrator_<id>.json's mtime (session 5 output is never rewritten after creation), null if not yet analyzed")


class OfferDetailResponse(BaseModel):
    id: int
    title: str
    location: str | None
    company: str | None
    url: str
    status: str
    score: int | None = Field(default=None, description="Score 0-100, null if not yet analyzed")
    geography_zone: str | None = Field(default=None, description="Zone from check_geography_rules, null if not yet analyzed")
    published_at: str | None = Field(default=None, description="Publication date as scraped from the source offer (jobs.published_at), format varies by source and is not normalized")
    analyzed_at: str | None = Field(default=None, description="When the orchestrator produced this offer's analysis, ISO 8601 UTC — derived from trace_orchestrator_<id>.json's mtime, null if not yet analyzed")
    matches: list[MatchItem] = Field(default_factory=list, description="Matched skills with grounding, straight from ScoringResult.matches via generation's StructuredAnalysis (session 9 follow-up) — not re-parsed from the markdown")
    gaps: list[GapItem] = Field(default_factory=list, description="Confirmed gaps with a short note, straight from ScoringResult.gaps")
    uncertain_flags: list[str] = Field(default_factory=list, description="Requirement labels with no reliable RAG match, straight from ScoringResult.uncertain_flags")
    analysis_markdown: str | None = Field(default=None, description="Null if the offer hasn't been analyzed yet")
    orchestrator_trace: dict | None = Field(default=None, description="Orchestrator's own decision trace (session 5)")
    scoring_trace: dict | None = Field(default=None, description="Scoring agent's RAG decision trace (session 3)")
    generation_trace: dict | None = Field(default=None, description="Generation agent's decision trace (session 4)")


class AnalyzeRequest(BaseModel):
    offer_id: int = Field(description="ID of an offer already present in the database (from a prior scraper run)")


class AnalyzeResponse(BaseModel):
    offer_id: int
    status: str = Field(description="'analyse', 'a_valider_geographie', or 'echec'")
    analysis_markdown: str | None = Field(default=None, description="Null if status='echec'")
    trace_summary: list[str] = Field(description="Human-readable list of the orchestrator's own decisions — not the full nested scoring/generation traces (see GET /offers/{id} for those)")
    error: str | None = Field(default=None, description="Full exception context if status='echec', null otherwise")
