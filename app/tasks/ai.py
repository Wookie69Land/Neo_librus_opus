"""ARQ task for the AI book recommendation pipeline.

This module defines ``run_ai_recommendation_pipeline``, an async ARQ task
that executes the full LangGraph recommendation workflow and returns the
serialisable result for the polling endpoint to retrieve.

Registration: add this function to ``WorkerSettings.functions`` in
``app/tasks/worker.py``.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from django.db import close_old_connections

from app.ai.mongo import cache_result, ensure_indexes, get_cached_result, log_pipeline_run
from app.ai.recommendations.graph import recommendation_graph
from app.ai.recommendations.state import RecommendationState

logger = logging.getLogger(__name__)


async def run_ai_recommendation_pipeline(ctx: dict, payload: dict) -> dict:
    """Execute the LangGraph recommendation pipeline as an ARQ background task.

    The function builds the initial ``RecommendationState`` from ``payload``,
    invokes the compiled graph, and returns a serialisable dict that the polling
    endpoint can read directly from the ARQ result store.

    Args:
        ctx: ARQ worker context (not used directly, but required by ARQ).
        payload: Dict with keys matching ``RecommendationRequest`` fields:
            - ``request_id`` (str)
            - ``query`` (str)
            - ``max_results`` (int)
            - ``language`` (str | None)
            - ``include_unavailable`` (bool)

    Returns:
        Dict with ``status``, ``query_interpretation``, ``recommendations``,
        ``stats_summary``, ``generated_at``, and ``node_errors``.
    """
    # Ensure fresh DB connections inside the worker process.
    close_old_connections()

    request_id: str = payload["request_id"]
    raw_query: str = payload["query"]
    language: str | None = payload.get("language")
    include_unavailable: bool = payload.get("include_unavailable", True)
    max_results: int = payload.get("max_results", 10)

    logger.info("AI recommendation pipeline started", extra={"request_id": request_id})

    # ── MongoDB: ensure indexes (idempotent, fast after first call) ────────────
    await ensure_indexes()

    # ── MongoDB: check recommendation cache ───────────────────────────────────
    cached = await get_cached_result(raw_query, language, include_unavailable, max_results)
    if cached:
        logger.info(
            "AI recommendation pipeline served from cache",
            extra={"request_id": request_id},
        )
        # Replace request_id so the polling endpoint sees this request's ID.
        cached["request_id"] = request_id
        return cached

    pipeline_start = time.monotonic()

    initial_state: RecommendationState = {
        "request_id": request_id,
        "raw_query": raw_query,
        "max_results": max_results,
        "language": language,
        "include_unavailable": include_unavailable,
        "node_errors": [],
    }

    try:
        final_state: RecommendationState = await recommendation_graph.ainvoke(initial_state)
    except Exception as exc:
        logger.exception(
            "AI recommendation pipeline failed with unhandled error",
            extra={"request_id": request_id},
        )
        failed_result = {
            "status": "failed",
            "request_id": request_id,
            "error": f"Pipeline error: {exc}",
            "recommendations": [],
            "stats_summary": None,
            "query_interpretation": None,
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "node_errors": [],
        }
        await log_pipeline_run(
            request_id=request_id,
            raw_query=raw_query,
            payload=payload,
            result=failed_result,
            node_timings={},
            token_usage={},
            node_errors=[f"unhandled: {exc}"],
            total_latency_s=round(time.monotonic() - pipeline_start, 3),
        )
        return failed_result

    # Build availability lookup from candidate_books
    book_meta: dict[int, dict] = {
        b["book_id"]: b for b in (final_state.get("candidate_books") or [])
    }

    recommendations: list[dict] = []
    for rec in final_state.get("final_recommendations") or []:
        book = book_meta.get(rec["book_id"], {})
        scored = next(
            (s for s in (final_state.get("scored_candidates") or []) if s["book_id"] == rec["book_id"]),
            {"relevance_score": 0.5},
        )
        recommendations.append(
            {
                "book_id": rec["book_id"],
                "title": book.get("title", ""),
                "isbn": book.get("isbn", ""),
                "authors": book.get("authors", []),
                "language": book.get("language"),
                "score": scored["relevance_score"],
                "why_recommended": rec["why_recommended"],
                "availability": book.get("availability", []),
            }
        )

    stats_summary = {
        "total_candidates": final_state.get("total_candidates", 0),
        "categories_found": final_state.get("categories_found", []),
        "languages_found": final_state.get("languages_found", []),
        "narrative": final_state.get("stats_narrative", ""),
    }

    node_errors: list[str] = final_state.get("node_errors") or []
    if node_errors:
        logger.warning(
            "Pipeline completed with %d node errors: %s",
            len(node_errors),
            node_errors,
            extra={"request_id": request_id},
        )

    logger.info(
        "AI recommendation pipeline completed: %d recommendations",
        len(recommendations),
        extra={"request_id": request_id},
    )

    result = {
        "status": "completed",
        "request_id": request_id,
        "query_interpretation": final_state.get("query_interpretation"),
        "recommendations": recommendations,
        "stats_summary": stats_summary,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "node_errors": node_errors,
        "error": None,
    }

    total_latency = round(time.monotonic() - pipeline_start, 3)
    node_timings: dict[str, float] = final_state.get("node_timings") or {}
    token_usage: dict[str, dict] = final_state.get("token_usage") or {}

    logger.info(
        "Pipeline timings: total=%.2fs nodes=%s",
        total_latency,
        {k: f"{v:.2f}s" for k, v in node_timings.items()},
        extra={"request_id": request_id},
    )

    # ── MongoDB: cache successful result + append audit log ────────────────────
    await cache_result(raw_query, language, include_unavailable, max_results, result)
    await log_pipeline_run(
        request_id=request_id,
        raw_query=raw_query,
        payload=payload,
        result=result,
        node_timings=node_timings,
        token_usage=token_usage,
        node_errors=node_errors,
        total_latency_s=total_latency,
    )

    return result
