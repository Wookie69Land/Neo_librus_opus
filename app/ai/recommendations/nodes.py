"""LangGraph node functions for the book recommendation pipeline.

Each node is a pure ``async`` function that accepts the current
``RecommendationState`` and returns a *partial* dict of updated fields.

Node execution order:
    START → understand_query → fetch_candidates → analyze_statistics
          → compose_response → END

The three LLM-backed nodes use different Gemini model variants configured
via Django settings (``AI_MODEL_QUERY``, ``AI_MODEL_STATS``, ``AI_MODEL_RESPONSE``).
"""
from __future__ import annotations

import json
import logging
import time

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.outputs import LLMResult

from app.ai.client import LLMRole, get_llm, structured_output_kwargs
from app.ai.recommendations.prompts import (
    QUERY_UNDERSTANDING_HUMAN,
    QUERY_UNDERSTANDING_SYSTEM,
    RESPONSE_COMPOSITION_HUMAN,
    RESPONSE_COMPOSITION_SYSTEM,
    STATISTICAL_ANALYSIS_HUMAN,
    STATISTICAL_ANALYSIS_SYSTEM,
)
from app.ai.recommendations.schemas import (
    FinalResponse,
    QueryUnderstanding,
    StatisticalAnalysis,
)
from app.ai.recommendations.state import RecommendationState

logger = logging.getLogger(__name__)


# ── Token-usage callback ───────────────────────────────────────────────────────

class _TokenUsageCallback(BaseCallbackHandler):
    """Lightweight LangChain callback that captures token counts from any provider.

    Compatible with both Gemini (``usage_metadata`` key) and Groq/OpenAI-compat
    (``token_usage`` key) response formats.
    """

    def __init__(self) -> None:
        super().__init__()
        self.input_tokens: int = 0
        self.output_tokens: int = 0

    def on_llm_end(self, response: LLMResult, **kwargs: object) -> None:  # noqa: ARG002
        lo: dict = response.llm_output or {}
        # Gemini: usage_metadata.{prompt_token_count, candidates_token_count}
        # Groq / OpenAI-compat: token_usage.{prompt_tokens, completion_tokens}
        usage: dict = (
            lo.get("usage_metadata")
            or lo.get("token_usage")
            or lo.get("usage")
            or {}
        )
        self.input_tokens += (
            usage.get("prompt_token_count") or usage.get("prompt_tokens") or 0
        )
        self.output_tokens += (
            usage.get("candidates_token_count") or usage.get("completion_tokens") or 0
        )


# ── Node 1: Query Understanding ────────────────────────────────────────────────

async def understand_query(state: RecommendationState) -> dict:
    """Parse and normalise the user's free-text query.

    Uses ``AI_MODEL_QUERY`` (gemini-2.0-flash) with structured output to
    extract keywords, language hints, and audience signals.

    Fallback: if the LLM call fails, the raw query is tokenised naively and
    the pipeline continues with degraded quality.

    Args:
        state: Current graph state containing ``raw_query``.

    Returns:
        Partial state update with query understanding fields.
    """
    raw_query: str = state["raw_query"]
    errors: list[str] = list(state.get("node_errors") or [])

    try:
        llm = get_llm(LLMRole.QUERY).with_structured_output(QueryUnderstanding, **structured_output_kwargs())
        messages = [
            SystemMessage(content=QUERY_UNDERSTANDING_SYSTEM),
            HumanMessage(content=QUERY_UNDERSTANDING_HUMAN.format(raw_query=raw_query)),
        ]
        token_cb = _TokenUsageCallback()
        t0 = time.monotonic()
        result: QueryUnderstanding = await llm.ainvoke(messages, config={"callbacks": [token_cb]})
        latency = time.monotonic() - t0

        timings = dict(state.get("node_timings") or {})
        timings["understand_query"] = round(latency, 3)
        usage = dict(state.get("token_usage") or {})
        usage["understand_query"] = {"input": token_cb.input_tokens, "output": token_cb.output_tokens}

        logger.info(
            "understand_query succeeded: keywords=%s language_hint=%r audience=%r period=%s-%s latency=%.2fs tokens_in=%d tokens_out=%d",
            result.keywords,
            result.language_hint,
            result.audience,
            result.period_from,
            result.period_to,
            latency,
            token_cb.input_tokens,
            token_cb.output_tokens,
            extra={"request_id": state.get("request_id")},
        )
        return {
            "normalized_intent": result.normalized_intent,
            "extracted_keywords": result.keywords,
            "language_hint": result.language_hint,
            "audience": result.audience,
            "period_from": result.period_from,
            "period_to": result.period_to,
            "node_errors": errors,
            "node_timings": timings,
            "token_usage": usage,
        }

    except Exception as exc:
        logger.warning(
            "understand_query fallback triggered: %s",
            exc,
            extra={"request_id": state.get("request_id")},
        )
        errors.append(f"understand_query: {exc}")
        # Naive fallback: split raw query into keywords
        keywords = [w.strip() for w in raw_query.split() if len(w.strip()) >= 3][:7]
        return {
            "normalized_intent": raw_query,
            "extracted_keywords": keywords or [raw_query],
            "language_hint": state.get("language"),
            "audience": None,
            "period_from": None,
            "period_to": None,
            "node_errors": errors,
        }


# ── DB Fetch: Candidate Retrieval (no LLM) ────────────────────────────────────

async def fetch_candidates(state: RecommendationState) -> dict:
    """Retrieve candidate books from the database using extracted keywords.

    This node performs the deterministic DB query — it does not call any LLM.
    It is a necessary step between the understanding node and the analysis node.

    Args:
        state: Must contain ``extracted_keywords``, ``language_hint``,
               ``include_unavailable``, and optionally ``period_from``/``period_to``.

    Returns:
        Partial state update with ``candidate_books``, ``total_candidates``,
        ``categories_found``, ``languages_found``.
    """
    from app.domain.repositories import RecommendationRepository  # local import avoids circular

    keywords: list[str] = state.get("extracted_keywords") or [state["raw_query"]]
    # Only apply language filter when the user explicitly requested one.
    # The LLM-inferred language_hint reflects the query language, not a filter preference,
    # so it must not narrow the DB results.
    language: str | None = state.get("language")
    include_unavailable: bool = state.get("include_unavailable", True)
    period_from: int | None = state.get("period_from")
    period_to: int | None = state.get("period_to")
    errors: list[str] = list(state.get("node_errors") or [])

    logger.info(
        "fetch_candidates: keywords=%s language=%r include_unavailable=%s period=%s-%s",
        keywords,
        language,
        include_unavailable,
        period_from,
        period_to,
        extra={"request_id": state.get("request_id")},
    )

    repo = RecommendationRepository()
    candidates = await repo.fetch_candidates(
        keywords=keywords,
        language=language,
        include_unavailable=include_unavailable,
        period_from=period_from,
        period_to=period_to,
        limit=25,
    )

    # Fallback: if language filter + keywords produced nothing, retry without language.
    if not candidates and language:
        logger.info(
            "fetch_candidates: 0 results with language=%r — retrying without language filter",
            language,
            extra={"request_id": state.get("request_id")},
        )
        candidates = await repo.fetch_candidates(
            keywords=keywords,
            language=None,
            include_unavailable=include_unavailable,
            period_from=period_from,
            period_to=period_to,
            limit=25,
        )

    categories: list[str] = list({
        c.strip()
        for book in candidates
        if book.get("category")
        for c in book["category"].split(",")
        if c.strip()
    })
    languages: list[str] = list({
        book["language"]
        for book in candidates
        if book.get("language")
    })

    logger.info(
        "fetch_candidates: %d books retrieved",
        len(candidates),
        extra={"request_id": state.get("request_id")},
    )
    return {
        "candidate_books": candidates,
        "total_candidates": len(candidates),
        "categories_found": categories,
        "languages_found": languages,
        "node_errors": errors,
    }


# ── Node 2: Statistical Analysis ──────────────────────────────────────────────

async def analyze_statistics(state: RecommendationState) -> dict:
    """Analyse candidate books and score them for relevance.

    Uses ``AI_MODEL_STATS`` (gemini-2.0-flash) with structured output.
    Receives the full candidate list and the normalised intent, then produces
    a relevance score and short rationale for each candidate.

    Fallback: if the LLM call fails, all candidates receive an equal score of 0.5.

    Args:
        state: Must contain ``candidate_books``, ``normalized_intent``, ``total_candidates``.

    Returns:
        Partial state update with ``statistical_analysis`` and ``scored_candidates``.
    """
    candidates: list[dict] = state.get("candidate_books") or []
    errors: list[str] = list(state.get("node_errors") or [])

    if not candidates:
        logger.warning(
            "analyze_statistics: no candidates — fetch_candidates returned 0 books",
            extra={"request_id": state.get("request_id")},
        )
        return {
            "statistical_analysis": "No candidate books were found in the catalogue.",
            "scored_candidates": [],
            "node_errors": errors,
        }

    # Summarise each candidate for the prompt (avoid giant payloads)
    slim_candidates = [
        {
            "book_id": b["book_id"],
            "title": b["title"],
            "authors": b["authors"],
            "category": b.get("category", ""),
            "language": b.get("language", ""),
            "published_year": b.get("published_year"),
            "available_copies": b.get("available_copies", 0),
            "description_snippet": (b.get("description") or "")[:200],
        }
        for b in candidates
    ]

    try:
        llm = get_llm(LLMRole.STATS).with_structured_output(StatisticalAnalysis, **structured_output_kwargs())
        messages = [
            SystemMessage(content=STATISTICAL_ANALYSIS_SYSTEM),
            HumanMessage(
                content=STATISTICAL_ANALYSIS_HUMAN.format(
                    normalized_intent=state.get("normalized_intent", state["raw_query"]),
                    total_candidates=len(candidates),
                    candidates_json=json.dumps(slim_candidates, ensure_ascii=False, indent=2),
                )
            ),
        ]
        token_cb = _TokenUsageCallback()
        t0 = time.monotonic()
        result: StatisticalAnalysis = await llm.ainvoke(messages, config={"callbacks": [token_cb]})
        latency = time.monotonic() - t0

        timings = dict(state.get("node_timings") or {})
        timings["analyze_statistics"] = round(latency, 3)
        usage = dict(state.get("token_usage") or {})
        usage["analyze_statistics"] = {"input": token_cb.input_tokens, "output": token_cb.output_tokens}

        scored = [
            {
                "book_id": sc.book_id,
                "relevance_score": sc.relevance_score,
                "reasoning": sc.reasoning,
            }
            for sc in result.scored_candidates
        ]

        logger.info(
            "analyze_statistics succeeded: %d scored latency=%.2fs tokens_in=%d tokens_out=%d",
            len(scored),
            latency,
            token_cb.input_tokens,
            token_cb.output_tokens,
            extra={"request_id": state.get("request_id")},
        )
        return {
            "statistical_analysis": result.analysis_summary,
            "scored_candidates": scored,
            "categories_found": result.dominant_categories or state.get("categories_found", []),
            "languages_found": result.dominant_languages or state.get("languages_found", []),
            "node_errors": errors,
            "node_timings": timings,
            "token_usage": usage,
        }

    except Exception as exc:
        logger.warning(
            "analyze_statistics fallback triggered: %s",
            exc,
            extra={"request_id": state.get("request_id")},
        )
        errors.append(f"analyze_statistics: {exc}")
        # Fallback: equal scores, ordered by available copies descending
        scored = sorted(
            [{"book_id": b["book_id"], "relevance_score": 0.5, "reasoning": "Matched search keywords."} for b in candidates],
            key=lambda x: next((c.get("available_copies", 0) for c in candidates if c["book_id"] == x["book_id"]), 0),
            reverse=True,
        )
        return {
            "statistical_analysis": f"Found {len(candidates)} matching books in the catalogue.",
            "scored_candidates": scored,
            "node_errors": errors,
        }


# ── Node 3: Response Composition ──────────────────────────────────────────────

async def compose_response(state: RecommendationState) -> dict:
    """Compose the final user-facing recommendation text.

    Uses ``AI_MODEL_RESPONSE`` (gemini-2.5-pro) with structured output.
    Selects the top-N candidates from the scored list and writes personalised,
    book-specific recommendation text for each.

    Fallback: if the LLM call fails, returns generic text derived from the
    scored candidates without an LLM-written explanation.

    Args:
        state: Must contain ``scored_candidates``, ``candidate_books``,
               ``statistical_analysis``, ``raw_query``, ``max_results``.

    Returns:
        Partial state update with ``query_interpretation``, ``final_recommendations``,
        and ``stats_narrative``.
    """
    scored: list[dict] = state.get("scored_candidates") or []
    candidate_books: list[dict] = state.get("candidate_books") or []
    max_results: int = state.get("max_results", 10)
    errors: list[str] = list(state.get("node_errors") or [])

    if not scored:
        logger.warning(
            "compose_response: no scored candidates to compose from",
            extra={"request_id": state.get("request_id")},
        )
        return {
            "query_interpretation": state.get("normalized_intent", state["raw_query"]),
            "final_recommendations": [],
            "stats_narrative": "No books were found matching your request.",
            "node_errors": errors,
        }

    # Sort by score and take exactly max_results candidates for the LLM prompt.
    # Sending more than needed wastes tokens and risks hitting provider TPM limits.
    book_meta = {b["book_id"]: b for b in candidate_books}
    top_scored = sorted(scored, key=lambda x: x["relevance_score"], reverse=True)[:max_results]

    ranked_for_prompt = [
        {
            "book_id": sc["book_id"],
            "score": sc["relevance_score"],
            "title": book_meta.get(sc["book_id"], {}).get("title", ""),
            "authors": book_meta.get(sc["book_id"], {}).get("authors", []),
            "category": book_meta.get(sc["book_id"], {}).get("category", ""),
            "reasoning": sc["reasoning"],
        }
        for sc in top_scored
        if sc["book_id"] in book_meta
    ]

    try:
        llm = get_llm(LLMRole.RESPONSE).with_structured_output(FinalResponse, **structured_output_kwargs())
        messages = [
            SystemMessage(content=RESPONSE_COMPOSITION_SYSTEM),
            HumanMessage(
                content=RESPONSE_COMPOSITION_HUMAN.format(
                    raw_query=state["raw_query"],
                    normalized_intent=state.get("normalized_intent", state["raw_query"]),
                    statistical_analysis=state.get("statistical_analysis", ""),
                    max_results=max_results,
                    ranked_candidates_json=json.dumps(ranked_for_prompt, ensure_ascii=False, indent=2),
                )
            ),
        ]
        token_cb = _TokenUsageCallback()
        t0 = time.monotonic()
        result: FinalResponse = await llm.ainvoke(messages, config={"callbacks": [token_cb]})
        latency = time.monotonic() - t0

        timings = dict(state.get("node_timings") or {})
        timings["compose_response"] = round(latency, 3)
        usage = dict(state.get("token_usage") or {})
        usage["compose_response"] = {"input": token_cb.input_tokens, "output": token_cb.output_tokens}

        final_recs = [
            {"book_id": r.book_id, "why_recommended": r.why_recommended}
            for r in result.recommendations[:max_results]
        ]

        logger.info(
            "compose_response succeeded: %d recommendations latency=%.2fs tokens_in=%d tokens_out=%d",
            len(final_recs),
            latency,
            token_cb.input_tokens,
            token_cb.output_tokens,
            extra={"request_id": state.get("request_id")},
        )
        return {
            "query_interpretation": result.query_interpretation,
            "final_recommendations": final_recs,
            "stats_narrative": result.stats_narrative,
            "node_errors": errors,
            "node_timings": timings,
            "token_usage": usage,
        }

    except Exception as exc:
        logger.warning(
            "compose_response fallback triggered: %s",
            exc,
            extra={"request_id": state.get("request_id")},
        )
        errors.append(f"compose_response: {exc}")
        final_recs = [
            {"book_id": sc["book_id"], "why_recommended": sc.get("reasoning", "Matched your search.")}
            for sc in top_scored[:max_results]
        ]
        return {
            "query_interpretation": state.get("normalized_intent", state["raw_query"]),
            "final_recommendations": final_recs,
            "stats_narrative": state.get("statistical_analysis", ""),
            "node_errors": errors,
        }
