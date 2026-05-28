"""LangGraph state definition for the recommendation pipeline.

The state is a plain ``TypedDict`` so LangGraph can manage it natively.
Every node receives the full state and returns a *partial* dict with only
the keys it mutates — LangGraph merges the updates automatically.
"""
from __future__ import annotations

from typing import TypedDict


class RecommendationState(TypedDict, total=False):
    """Shared state that flows through every node of the recommendation graph.

    Fields are populated progressively as the graph executes:

    * After ``understand_query`` node: ``normalized_intent``, ``extracted_keywords``,
      ``language_hint``, ``audience``, ``period_from``, ``period_to``.
    * After ``fetch_candidates`` node: ``candidate_books``, ``total_candidates``,
      ``categories_found``, ``languages_found``.
    * After ``analyze_statistics`` node: ``statistical_analysis``, ``scored_candidates``.
    * After ``compose_response`` node: ``query_interpretation``, ``final_recommendations``,
      ``stats_narrative``.
    """

    # ── Input (always present) ─────────────────────────────────────────────────
    request_id: str
    raw_query: str
    max_results: int
    language: str | None
    include_unavailable: bool

    # ── Node 1 output: query understanding ────────────────────────────────────
    normalized_intent: str
    extracted_keywords: list[str]
    language_hint: str | None
    audience: str | None
    period_from: int | None
    period_to: int | None

    # ── Intermediate: DB candidate fetch ──────────────────────────────────────
    candidate_books: list[dict]   # Each dict: book metadata + availability list
    total_candidates: int
    categories_found: list[str]
    languages_found: list[str]

    # ── Node 2 output: statistical analysis ───────────────────────────────────
    statistical_analysis: str     # Narrative summary produced by the model
    scored_candidates: list[dict] # [{book_id, relevance_score, reasoning}, ...]

    # ── Node 3 output: response composition ───────────────────────────────────
    query_interpretation: str
    final_recommendations: list[dict]  # [{book_id, why_recommended}, ...]
    stats_narrative: str

    # ── Error tracking (non-fatal; nodes may set this and continue) ───────────
    node_errors: list[str]

    # ── Observability: per-node wall-clock latency and token usage ────────────
    node_timings: dict[str, float]   # {node_name: latency_in_seconds}
    token_usage: dict[str, dict]     # {node_name: {input_tokens: int, output_tokens: int}}
