"""Pydantic schemas for the AI recommendation pipeline.

Two groups of schemas live here:

1. **API schemas** – used at the Django Ninja boundary (request/response).
2. **LLM structured-output schemas** – used with LangChain's
   ``with_structured_output`` to enforce typed JSON from each model node.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RecommendationRequest(BaseModel):
    """Input schema for POST /api/ai/recommendations."""

    query: str = Field(..., min_length=3, max_length=500, description="Free-text topic or intent.")
    max_results: int = Field(10, ge=1, le=20, description="Number of books to return (capped at 20).")
    language: str | None = Field(None, description="ISO 639-1 language code filter (e.g. 'pl', 'en').")
    include_unavailable: bool = Field(True, description="Include books with no available copies.")


class BookAvailabilitySummary(BaseModel):
    """Per-library availability snapshot included in each recommendation."""

    library_id: int
    library_name: str
    is_available: bool


class RecommendedBook(BaseModel):
    """A single book recommendation with its ranking rationale."""

    book_id: int
    title: str
    isbn: str
    authors: list[str]
    language: str | None
    score: float = Field(..., ge=0.0, le=1.0, description="Relevance score assigned by the pipeline.")
    why_recommended: str
    availability: list[BookAvailabilitySummary]


class RecommendationStats(BaseModel):
    """High-level statistics produced by the analysis node."""

    total_candidates: int
    categories_found: list[str]
    languages_found: list[str]
    narrative: str = Field("", description="Human-readable summary of the DB findings.")


class RecommendationResponse(BaseModel):
    """Full response schema (returned on 200 when result is ready)."""

    request_id: str
    status: str  # "pending" | "completed" | "failed"
    query_interpretation: str | None = None
    recommendations: list[RecommendedBook] = []
    stats_summary: RecommendationStats | None = None
    generated_at: datetime | None = None
    error: str | None = None
    node_errors: list[str] = []  # per-node fallback messages; non-empty means partial degradation


# ── LLM structured-output schemas (internal) ──────────────────────────────────

class QueryUnderstanding(BaseModel):
    """Output schema for Node 1 (query understanding model).

    Produced by gemini-2.0-flash via ``with_structured_output``.
    """

    normalized_intent: str = Field(
        ..., description="A clean, concise English restatement of what the user is looking for."
    )
    keywords: list[str] = Field(
        ...,
        min_length=1,
        max_length=10,
        description=(
            "3–7 search terms that best capture the topic (titles, genres, themes, authors). "
            "IMPORTANT: keywords must be in the SAME LANGUAGE as the user's query so they "
            "match the library catalogue's content. For example, if the query is in Polish, "
            "return Polish keywords (e.g. 'sport', 'piłka nożna', 'historia sportu')."
        ),
    )
    language_hint: str | None = Field(
        None, description="Detected language preference as ISO 639-1 code, or null if unspecified."
    )
    audience: str | None = Field(
        None, description="Target audience inferred from the query: 'children', 'young_adult', 'adult', 'academic', or null."
    )
    period_from: int | None = Field(None, description="Earliest publication year the user seems to prefer, or null.")
    period_to: int | None = Field(None, description="Latest publication year the user seems to prefer, or null.")


class ScoredCandidate(BaseModel):
    """A single book with a relevance score from Node 2."""

    book_id: int
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    reasoning: str = Field(..., description="One sentence explaining why this book fits the query.")


class StatisticalAnalysis(BaseModel):
    """Output schema for Node 2 (statistical analysis model).

    Produced by gemini-2.0-flash via ``with_structured_output``.
    """

    analysis_summary: str = Field(
        ..., description="2–4 sentence narrative of what the database returned and what patterns stand out."
    )
    scored_candidates: list[ScoredCandidate] = Field(
        ..., description="All candidates re-ranked by relevance to the user's query."
    )
    dominant_categories: list[str] = Field(..., description="Top category labels found among candidates.")
    dominant_languages: list[str] = Field(..., description="Top language codes found among candidates.")


class FinalRecommendation(BaseModel):
    """A final book recommendation with a user-facing explanation."""

    book_id: int
    why_recommended: str = Field(
        ..., description="2–3 sentence, user-friendly explanation of why this book was selected."
    )


class FinalResponse(BaseModel):
    """Output schema for Node 3 (response composition model).

    Produced by gemini-2.5-pro via ``with_structured_output``.
    """

    query_interpretation: str = Field(
        ..., description="One sentence summarising what the system understood the user to be looking for."
    )
    recommendations: list[FinalRecommendation] = Field(
        ..., description="Ordered list of book recommendations (highest relevance first)."
    )
    stats_narrative: str = Field(
        ..., description="A short, friendly paragraph summarising what was found in the library catalogue."
    )
