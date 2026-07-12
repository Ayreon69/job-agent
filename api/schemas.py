"""Pydantic request/response models for the API — pure serialization shapes,
no business logic. See orchestrator/agent.py and storage/db.py for the
actual data these mirror.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthChecks(BaseModel):
    mistral_key_present: bool = Field(description="MISTRAL_API_KEY is set and non-empty in the environment — presence only, not validity (a real Mistral call would be needed to verify the key actually works, which /health deliberately avoids)")
    embeddings_loaded: bool = Field(description="The sentence-transformers model + ChromaDB client singletons (session 6) were constructed successfully at startup")
    database_accessible: bool = Field(description="The SQLite connection can be opened and responds to a trivial query")


class HealthResponse(BaseModel):
    status: str = Field(description="'ok' if all checks pass, 'degraded' if any check fails")
    checks: HealthChecks


class OfferSummary(BaseModel):
    id: int
    title: str
    location: str | None
    company: str | None
    status: str
    score: int | None = Field(default=None, description="Score 0-100, null if not yet analyzed")
    geography_zone: str | None = Field(default=None, description="Zone from check_geography_rules, null if not yet analyzed")
    gaps_count: int | None = Field(default=None, description="Number of confirmed gaps listed in the analysis markdown, null if not yet analyzed")
    uncertain_count: int | None = Field(default=None, description="Number of uncertain flags listed in the analysis markdown, null if not yet analyzed")


class OfferDetailResponse(BaseModel):
    id: int
    title: str
    location: str | None
    company: str | None
    url: str
    status: str
    score: int | None = Field(default=None, description="Score 0-100, null if not yet analyzed")
    geography_zone: str | None = Field(default=None, description="Zone from check_geography_rules, null if not yet analyzed")
    matching_summary: str | None = Field(default=None, description="First bullet of the analysis's matching summary, null if not yet analyzed")
    gaps: list[str] = Field(default_factory=list, description="Short labels of confirmed gaps, parsed from the analysis markdown (empty if none or not yet analyzed)")
    uncertain_flags: list[str] = Field(default_factory=list, description="Short labels of uncertain flags, parsed from the analysis markdown (empty if none or not yet analyzed)")
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
