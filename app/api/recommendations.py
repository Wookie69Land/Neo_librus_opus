"""Django Ninja router for AI book recommendation endpoints.

Endpoints
---------
POST /api/ai/recommendations
    Enqueue a new recommendation job. Returns 202 with a ``request_id``.

GET  /api/ai/recommendations/{request_id}
    Poll for the result of a previously enqueued job.
    Returns 200 with the full result when complete, or 202 while pending.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from arq.jobs import Job, JobStatus
from django.conf import settings
from ninja import Router, Schema
from ninja.errors import HttpError

from app.ai.recommendations.schemas import (
    BookAvailabilitySummary,
    RecommendationRequest,
    RecommendationResponse,
    RecommendationStats,
    RecommendedBook,
)
from app.api.permissions import get_authenticated_session

logger = logging.getLogger(__name__)
router = Router(tags=["AI Recommendations"])

# ── Redis pool helpers ───────────────────────────────────────────────────────

def _arq_redis_settings() -> RedisSettings:
    return RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        database=settings.REDIS_DATABASE,
    )


async def _get_redis_pool() -> ArqRedis:
    """Create a fresh ARQ Redis pool bound to the current event loop.

    A new pool is created per call instead of being cached at module level.
    This avoids ``RuntimeError: Event loop is closed`` when Django's dev
    server (or asgiref's AsyncToSync) runs each request in a separate thread
    with its own event loop.

    Callers are responsible for calling ``await pool.aclose()`` after use.

    Returns:
        A connected ``ArqRedis`` instance.
    """
    return await create_pool(_arq_redis_settings())


# ── Response helpers ──────────────────────────────────────────────────────────

def _build_response(result: dict) -> RecommendationResponse:
    """Convert the raw ARQ task result dict into the API response schema.

    Args:
        result: Dict returned by ``run_ai_recommendation_pipeline``.

    Returns:
        Populated ``RecommendationResponse``.
    """
    from datetime import datetime

    recommendations = [
        RecommendedBook(
            book_id=r["book_id"],
            title=r["title"],
            isbn=r["isbn"],
            authors=r["authors"],
            language=r.get("language"),
            score=r["score"],
            why_recommended=r["why_recommended"],
            availability=[
                BookAvailabilitySummary(
                    library_id=a["library_id"],
                    library_name=a["library_name"],
                    is_available=a["is_available"],
                )
                for a in r.get("availability", [])
            ],
        )
        for r in result.get("recommendations", [])
    ]

    stats_raw = result.get("stats_summary")
    stats = (
        RecommendationStats(
            total_candidates=stats_raw["total_candidates"],
            categories_found=stats_raw["categories_found"],
            languages_found=stats_raw["languages_found"],
            narrative=stats_raw.get("narrative", ""),
        )
        if stats_raw
        else None
    )

    generated_at_raw = result.get("generated_at")
    generated_at = datetime.fromisoformat(generated_at_raw) if generated_at_raw else None

    return RecommendationResponse(
        request_id=result["request_id"],
        status=result.get("status", "completed"),
        query_interpretation=result.get("query_interpretation"),
        recommendations=recommendations,
        stats_summary=stats,
        generated_at=generated_at,
        error=result.get("error"),
        node_errors=result.get("node_errors") or [],
    )


# ── POST /api/ai/recommendations ─────────────────────────────────────────────

class EnqueuedResponse(Schema):
    """Immediate 202 response returned when the job is accepted."""

    request_id: str
    status: str = "pending"
    message: str = "Recommendation job enqueued. Poll GET /api/ai/recommendations/{request_id} for results."


@router.post(
    "/recommendations",
    response={202: EnqueuedResponse, 422: dict, 429: dict},
    summary="Request AI book recommendations",
    description=(
        "Submit a free-text topic query. The request is processed asynchronously "
        "by the AI pipeline (LangGraph + Gemini). Poll the GET endpoint for results.\n\n"
        "**Authentication:** Bearer token required."
    ),
)
async def create_recommendation(request: Any, body: RecommendationRequest) -> tuple[int, EnqueuedResponse]:
    """Enqueue an AI recommendation pipeline job.

    Args:
        request: Django request (auth is checked via session).
        body: Validated request payload.

    Returns:
        202 with ``request_id`` for polling.

    Raises:
        HttpError 401: If the user is not authenticated.
    """
    get_authenticated_session(request)  # raises 401 if not authenticated

    request_id = str(uuid.uuid4())
    payload = {
        "request_id": request_id,
        "query": body.query,
        "max_results": body.max_results,
        "language": body.language,
        "include_unavailable": body.include_unavailable,
    }

    pool = await _get_redis_pool()
    try:
        await pool.enqueue_job(
            "run_ai_recommendation_pipeline",
            payload,
            _job_id=request_id,
        )
    except Exception as exc:
        logger.exception("Failed to enqueue AI recommendation job: %s", exc)
        raise HttpError(503, "Recommendation service temporarily unavailable.") from exc
    finally:
        await pool.aclose()

    logger.info("AI recommendation job enqueued", extra={"request_id": request_id})
    return 202, EnqueuedResponse(request_id=request_id)


# ── GET /api/ai/recommendations/{request_id} ─────────────────────────────────

@router.get(
    "/recommendations/{request_id}",
    response={200: RecommendationResponse, 202: EnqueuedResponse, 404: dict},
    summary="Poll for recommendation results",
    description=(
        "Check the status of a previously submitted recommendation request.\n\n"
        "* **202** — the pipeline is still running; retry after a few seconds.\n"
        "* **200** — results are ready.\n"
        "* **404** — ``request_id`` not found or expired (results are kept for 1 hour).\n\n"
        "**Authentication:** Bearer token required."
    ),
)
async def get_recommendation(request: Any, request_id: str) -> tuple[int, Any]:
    """Retrieve the result of an AI recommendation job.

    Args:
        request: Django request (auth checked).
        request_id: UUID returned by the POST endpoint.

    Returns:
        202 if still pending, 200 with full results when done, 404 if not found.

    Raises:
        HttpError 401: If the user is not authenticated.
        HttpError 404: If the job is not found or has expired.
    """
    get_authenticated_session(request)

    pool = await _get_redis_pool()
    try:
        job = Job(request_id, pool)
        try:
            status = await job.status()
        except Exception as exc:
            logger.exception("Error checking job status: %s", exc)
            raise HttpError(503, "Recommendation service temporarily unavailable.") from exc

        if status == JobStatus.not_found:
            raise HttpError(404, f"Recommendation request '{request_id}' not found or expired.")

        if status in (JobStatus.deferred, JobStatus.queued, JobStatus.in_progress):
            return 202, EnqueuedResponse(
                request_id=request_id,
                message="Pipeline is still running. Please retry in a few seconds.",
            )

        # status == JobStatus.complete
        try:
            result: dict = await asyncio.wait_for(job.result(), timeout=5.0)
        except (asyncio.TimeoutError, Exception) as exc:
            logger.exception("Error retrieving job result for %s: %s", request_id, exc)
            raise HttpError(503, "Could not retrieve recommendation result.") from exc
    finally:
        await pool.aclose()

    return 200, _build_response(result)
