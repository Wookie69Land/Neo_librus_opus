"""Async MongoDB client for the AI recommendation pipeline.

Responsibilities
----------------
* **Pipeline run logging** — every invocation of the LangGraph pipeline is
  persisted to the ``pipeline_runs`` collection with timing, token usage, and
  error details.  This provides a durable audit trail beyond the Redis 1-hour
  result TTL.

* **Recommendation result cache** — results are cached by a SHA-256 fingerprint
  of the normalised query parameters.  A MongoDB TTL index expires documents
  automatically after 24 hours so stale recommendations are never served.

Collections
-----------
``pipeline_runs``
    Append-only audit log.  Indexed on ``request_id`` and ``created_at``.

``recommendation_cache``
    Query-keyed cache with 24 h TTL index on ``created_at`` and a unique index
    on ``fingerprint`` for fast upserts.

Usage::

    from app.ai.mongo import get_cached_result, cache_result, log_pipeline_run

    # Inside an async ARQ task:
    cached = await get_cached_result(raw_query, language, include_unavailable, max_results)
    if cached:
        return cached

    result = await run_pipeline(...)
    await cache_result(raw_query, language, include_unavailable, max_results, result)
    await log_pipeline_run(request_id, raw_query, payload, result, timings, tokens, errors, total_s)
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

# Module-level Motor client — created lazily on first use and reused.
_client: Any = None  # motor.motor_asyncio.AsyncIOMotorClient
_indexes_created: bool = False


# ── Client helpers ─────────────────────────────────────────────────────────────

def _get_client() -> Any:
    """Return (or create) the singleton Motor async client.

    Credentials are read from Django settings so they never appear in source.
    The client is NOT thread-safe for synchronous code, but Motor is designed
    for use in asyncio event loops and is safe to share across coroutines.
    """
    global _client
    if _client is None:
        try:
            import motor.motor_asyncio  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "motor is required for MongoDB support. "
                "Add 'motor>=3.3,<4' to your dependencies."
            ) from exc

        _client = motor.motor_asyncio.AsyncIOMotorClient(
            host=settings.MONGODB_HOST,
            port=settings.MONGODB_PORT,
            username=settings.MONGODB_USER or None,
            password=settings.MONGODB_PASSWORD or None,
            authSource=settings.MONGODB_DATABASE,
            serverSelectionTimeoutMS=5_000,
        )
        logger.debug("MongoDB Motor client created (host=%s)", settings.MONGODB_HOST)
    return _client


def _get_db() -> Any:
    """Return the configured MongoDB database handle."""
    return _get_client()[settings.MONGODB_DATABASE]


# ── Index management ───────────────────────────────────────────────────────────

async def ensure_indexes() -> None:
    """Create required indexes on first call; no-op on subsequent calls.

    Call this once at worker startup or before the first MongoDB operation.
    The flag ``_indexes_created`` prevents repeated round-trips.
    """
    global _indexes_created
    if _indexes_created:
        return
    try:
        db = _get_db()
        # recommendation_cache: TTL + unique fingerprint
        await db.recommendation_cache.create_index(
            "created_at",
            expireAfterSeconds=86_400,  # 24 hours
            background=True,
            name="ttl_created_at",
        )
        await db.recommendation_cache.create_index(
            "fingerprint",
            unique=True,
            background=True,
            name="uq_fingerprint",
        )
        # pipeline_runs: lookup by request_id and time-range queries
        await db.pipeline_runs.create_index("request_id", background=True)
        await db.pipeline_runs.create_index("created_at", background=True)
        _indexes_created = True
        logger.info("MongoDB indexes ensured")
    except Exception as exc:
        logger.warning("MongoDB index creation failed (non-fatal): %s", exc)


# ── Query fingerprinting ───────────────────────────────────────────────────────

def _query_fingerprint(
    raw_query: str,
    language: str | None,
    include_unavailable: bool,
    max_results: int,
) -> str:
    """Return a deterministic SHA-256 hex fingerprint for a set of query parameters.

    The fingerprint is used as the cache key in ``recommendation_cache``.
    Queries that differ only in whitespace or casing are treated as identical.
    """
    key = json.dumps(
        {
            "q": raw_query.strip().lower(),
            "lang": language,
            "incl": include_unavailable,
            "max": max_results,
        },
        sort_keys=True,
    )
    return hashlib.sha256(key.encode()).hexdigest()


# ── Cache operations ───────────────────────────────────────────────────────────

async def get_cached_result(
    raw_query: str,
    language: str | None,
    include_unavailable: bool,
    max_results: int,
) -> dict | None:
    """Return a cached pipeline result dict, or ``None`` if no cache hit.

    Silently swallows MongoDB errors so that a connectivity issue never
    blocks a recommendation request.
    """
    fingerprint = _query_fingerprint(raw_query, language, include_unavailable, max_results)
    try:
        db = _get_db()
        doc = await db.recommendation_cache.find_one({"fingerprint": fingerprint})
        if doc:
            logger.info(
                "MongoDB cache hit for fingerprint=%s query=%r",
                fingerprint[:8],
                raw_query[:60],
            )
            return doc.get("result")
    except Exception as exc:
        logger.warning("MongoDB cache lookup failed (non-fatal): %s", exc)
    return None


async def cache_result(
    raw_query: str,
    language: str | None,
    include_unavailable: bool,
    max_results: int,
    result: dict,
) -> None:
    """Upsert a pipeline result into the recommendation cache.

    Uses ``replace_one(..., upsert=True)`` so repeated calls for the same
    query simply refresh the document and reset the 24 h TTL window.

    Silently swallows errors — caching is best-effort.
    """
    fingerprint = _query_fingerprint(raw_query, language, include_unavailable, max_results)
    try:
        db = _get_db()
        await db.recommendation_cache.replace_one(
            {"fingerprint": fingerprint},
            {
                "fingerprint": fingerprint,
                "raw_query": raw_query,
                "result": result,
                "created_at": datetime.now(tz=timezone.utc),
            },
            upsert=True,
        )
        logger.debug(
            "MongoDB cached result for fingerprint=%s query=%r",
            fingerprint[:8],
            raw_query[:60],
        )
    except Exception as exc:
        logger.warning("MongoDB cache write failed (non-fatal): %s", exc)


# ── Pipeline run logging ───────────────────────────────────────────────────────

async def log_pipeline_run(
    request_id: str,
    raw_query: str,
    payload: dict,
    result: dict,
    node_timings: dict[str, float],
    token_usage: dict[str, dict],
    node_errors: list[str],
    total_latency_s: float,
) -> None:
    """Append a pipeline run record to the ``pipeline_runs`` collection.

    This is the persistent audit trail.  The document is never auto-expired
    so it can be used for debugging, analytics, and future model evaluation.

    Silently swallows errors — logging is best-effort and must not break the
    task result.
    """
    try:
        db = _get_db()
        await db.pipeline_runs.insert_one(
            {
                "request_id": request_id,
                "raw_query": raw_query,
                "language": payload.get("language"),
                "include_unavailable": payload.get("include_unavailable", True),
                "max_results": payload.get("max_results", 10),
                "status": result.get("status", "unknown"),
                "recommendation_count": len(result.get("recommendations") or []),
                "node_timings_s": node_timings,
                "token_usage": token_usage,
                "node_errors": node_errors,
                "total_latency_s": total_latency_s,
                "created_at": datetime.now(tz=timezone.utc),
            }
        )
        logger.debug(
            "MongoDB logged pipeline run request_id=%s total=%.2fs",
            request_id,
            total_latency_s,
        )
    except Exception as exc:
        logger.warning("MongoDB pipeline run logging failed (non-fatal): %s", exc)


# ── Lifecycle ──────────────────────────────────────────────────────────────────

async def close_client() -> None:
    """Close the Motor client and reset the singleton.

    Call this during application or worker shutdown to release connections.
    """
    global _client
    if _client is not None:
        _client.close()
        _client = None
        logger.debug("MongoDB Motor client closed")
