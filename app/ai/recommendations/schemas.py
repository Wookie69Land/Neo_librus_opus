"""Pydantic schemas for the AI recommendation pipeline.

Two groups of schemas live here:

1. **API schemas** – used at the Django Ninja boundary (request/response).
2. **LLM structured-output schemas** – used with LangChain's
   ``with_structured_output`` to enforce typed JSON from each model node.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


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

    model_config = ConfigDict(populate_by_name=True)

    # Old cache hits may omit this field entirely — default to "" and let
    # the model_validator below reconstruct it from keywords.
    normalized_intent: str = Field(
        default="", description="A clean, concise English restatement of what the user is looking for."
    )

    @model_validator(mode="after")
    def _fill_normalized_intent(self) -> QueryUnderstanding:
        if not self.normalized_intent and self.keywords:
            self.normalized_intent = " ".join(self.keywords)
        return self
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

    model_config = ConfigDict(populate_by_name=True)

    book_id: int
    # Old cache: field was named "score"
    relevance_score: float = Field(
        ..., ge=0.0, le=1.0,
        validation_alias=AliasChoices("relevance_score", "score"),
    )
    # Old cache: field was named "explanation"
    reasoning: str = Field(
        ...,
        validation_alias=AliasChoices("reasoning", "explanation"),
        description="One sentence explaining why this book fits the query.",
    )


class StatisticalAnalysis(BaseModel):
    """Output schema for Node 2 (statistical analysis model).

    Produced by gemini-2.0-flash via ``with_structured_output``.
    """

    model_config = ConfigDict(populate_by_name=True)

    # Old cache: field was named "analysis"
    analysis_summary: str = Field(
        ...,
        validation_alias=AliasChoices("analysis_summary", "analysis"),
        description="2–4 sentence narrative of what the database returned and what patterns stand out.",
    )
    # Old cache: field was named "scores"
    scored_candidates: list[ScoredCandidate] = Field(
        ...,
        validation_alias=AliasChoices("scored_candidates", "scores"),
        description="All candidates re-ranked by relevance to the user's query.",
    )
    # Old cache: could be null or absent
    dominant_categories: list[str] = Field(
        default_factory=list,
        description="Top category labels found among candidates.",
    )
    # Old cache: could be a bare string (e.g. "pol") or null
    dominant_languages: list[str] = Field(
        default_factory=list,
        description="Top language codes found among candidates.",
    )

    @field_validator("dominant_categories", "dominant_languages", mode="before")
    @classmethod
    def _coerce_to_list(cls, v: object) -> list:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v  # type: ignore[return-value]


class FinalRecommendation(BaseModel):
    """A final book recommendation with a user-facing explanation."""

    model_config = ConfigDict(populate_by_name=True)

    book_id: int
    # Old cache: field was named "explanation"
    why_recommended: str = Field(
        ...,
        validation_alias=AliasChoices("why_recommended", "explanation"),
        description="2–3 sentence, user-friendly explanation of why this book was selected.",
    )


class FinalResponse(BaseModel):
    """Output schema for Node 3 (response composition model).

    Produced by gemini-2.5-pro via ``with_structured_output``.
    """

    model_config = ConfigDict(populate_by_name=True)

    # Old cache: field was named "user_intent"
    query_interpretation: str = Field(
        ...,
        validation_alias=AliasChoices("query_interpretation", "user_intent"),
        description="One sentence summarising what the system understood the user to be looking for.",
    )
    # Old cache: field was named "recommended_books"
    recommendations: list[FinalRecommendation] = Field(
        ...,
        validation_alias=AliasChoices("recommendations", "recommended_books"),
        description="Ordered list of book recommendations (highest relevance first).",
    )
    # Old cache: field was named "library_catalogue"
    stats_narrative: str = Field(
        ...,
        validation_alias=AliasChoices("stats_narrative", "library_catalogue"),
        description="A short, friendly paragraph summarising what was found in the library catalogue.",
    )
