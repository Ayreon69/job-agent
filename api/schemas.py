"""Pydantic request/response models for the API — pure serialization shapes,
no business logic. See orchestrator/agent.py and storage/db.py for the
actual data these mirror.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str


class OfferSummary(BaseModel):
    id: int
    title: str
    location: str | None
    company: str | None
    status: str
    score: int | None = Field(default=None, description="Score 0-100, null if not yet analyzed")
    geography_zone: str | None = Field(default=None, description="Zone from check_geography_rules, null if not yet analyzed")


class OfferDetailResponse(BaseModel):
    id: int
    title: str
    location: str | None
    company: str | None
    url: str
    status: str
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
