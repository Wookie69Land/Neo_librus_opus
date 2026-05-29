"""LLM client factory for the AI recommendation pipeline.

Creates the correct LangChain chat model for each pipeline node based on
Django settings. Supports Google Gemini and Groq (OpenAI-compatible API).

Also configures a global LangChain LLM response cache backed by MongoDB
(``MongoDBCache``). The cache intercepts every ``llm.ainvoke()`` call and
returns a stored response when the exact ``(prompt, model, params)`` hash
was seen before — eliminating redundant API round-trips and provider
rate-limit errors without any changes in the node code.

Usage::

    from app.ai.client import get_llm, LLMRole

    llm = get_llm(LLMRole.QUERY)       # lightweight model  – query understanding
    llm = get_llm(LLMRole.STATS)       # reasoning model    – statistical analysis
    llm = get_llm(LLMRole.RESPONSE)    # quality model      – response composition
"""
from __future__ import annotations

import logging
from enum import StrEnum
from urllib.parse import quote_plus

from django.conf import settings
from langchain_core.language_models.chat_models import BaseChatModel

logger = logging.getLogger(__name__)

_llm_cache_initialized: bool = False


def _setup_llm_cache() -> None:
    """Configure the global LangChain LLM response cache using MongoDB.

    ``MongoDBCache`` hashes ``(prompt, model, params)`` and serves the stored
    response on a cache hit — every ``llm.ainvoke()`` call in any pipeline
    node benefits automatically.

    Silently skipped when:
    * ``langchain-mongodb`` is not installed.
    * ``MONGODB_HOST`` is empty or unset.
    * The MongoDB connection cannot be established.
    """
    global _llm_cache_initialized
    if _llm_cache_initialized:
        return
    _llm_cache_initialized = True  # set early so a failure doesn't retry on every call

    host: str = getattr(settings, "MONGODB_HOST", "")
    if not host:
        return

    try:
        from langchain_core.globals import set_llm_cache  # noqa: PLC0415
        from langchain_mongodb.cache import MongoDBCache  # noqa: PLC0415

        user = quote_plus(settings.MONGODB_USER) if settings.MONGODB_USER else ""
        password = quote_plus(settings.MONGODB_PASSWORD) if settings.MONGODB_PASSWORD else ""
        port = settings.MONGODB_PORT
        db = settings.MONGODB_DATABASE

        if user and password:
            uri = f"mongodb://{user}:{password}@{host}:{port}/?authSource={db}"
        else:
            uri = f"mongodb://{host}:{port}/"

        set_llm_cache(
            MongoDBCache(
                connection_string=uri,
                database_name=db,
                collection_name="llm_cache",
            )
        )
        logger.info("LangChain LLM response cache enabled (MongoDB)")
    except Exception as exc:
        logger.warning("MongoDB LLM cache setup failed (non-fatal): %s", exc)


class LLMRole(StrEnum):
    """Names for the three pipeline nodes that each need a dedicated LLM."""

    QUERY = "query"       # Node 1: parse / normalise the user's intent
    STATS = "stats"       # Node 2: statistical analysis of DB findings
    RESPONSE = "response" # Node 3: compose the final user-facing recommendation


def structured_output_kwargs() -> dict:
    """Return extra kwargs to pass to ``with_structured_output()`` for the active provider.

    **Groq:** use ``json_mode`` (``response_format: {"type": "json_object"}``).
    ``function_calling`` was the previous default but Groq's server-side validator
    rejects generation output that contains trailing commas — a known model quirk
    — with a hard 400 error before we can inspect or repair the text.  With
    ``json_mode`` the model returns raw JSON text; LangChain/Pydantic parses it
    on our side, where malformed output produces a recoverable ``ValidationError``
    instead of an unrecoverable HTTP 400.

    **Gemini:** uses its own structured-output path internally; no override needed.
    """
    if settings.AI_PROVIDER.lower() == "groq":
        return {"method": "json_mode"}
    return {}


def _model_for_role(role: LLMRole) -> str:
    """Return the configured model name for the given role.

    Args:
        role: One of the three pipeline node roles.

    Returns:
        The model identifier string (e.g. ``"gemini-2.0-flash"``).
    """
    mapping: dict[LLMRole, str] = {
        LLMRole.QUERY: settings.AI_MODEL_QUERY,
        LLMRole.STATS: settings.AI_MODEL_STATS,
        LLMRole.RESPONSE: settings.AI_MODEL_RESPONSE,
    }
    return mapping[role]


def get_llm(role: LLMRole) -> BaseChatModel:
    """Return an async-capable LangChain chat model for the given node role.

    The provider is chosen by ``settings.AI_PROVIDER`` (default: ``"gemini"``).
    Model names per role come from the ``AI_MODEL_*`` settings so they can be
    overridden per environment without code changes.

    The global LangChain LLM cache is configured on first call (idempotent).

    Args:
        role: Which pipeline node the model will serve.

    Returns:
        A LangChain ``BaseChatModel`` configured for the role.

    Raises:
        ValueError: If ``settings.AI_PROVIDER`` is not a supported value.
        ValueError: If ``GEMINI_API_KEY`` is empty when using the gemini provider.
    """
    _setup_llm_cache()

    provider: str = settings.AI_PROVIDER.lower()
    model_name: str = _model_for_role(role)

    if provider == "gemini":
        return _build_gemini(model_name)

    if provider == "groq":
        return _build_groq(model_name)

    raise ValueError(
        f"Unsupported AI_PROVIDER: '{provider}'. "
        "Supported values: 'gemini', 'groq'."
    )


def _build_gemini(model_name: str) -> BaseChatModel:
    """Construct a ChatGoogleGenerativeAI instance.

    Args:
        model_name: The Gemini model identifier (e.g. ``"gemini-2.0-flash"``).

    Returns:
        A configured ``ChatGoogleGenerativeAI`` instance.

    Raises:
        ValueError: When ``GEMINI_API_KEY`` is not set.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: PLC0415

    api_key: str = settings.GEMINI_API_KEY
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is not set. "
            "Obtain a free key at https://aistudio.google.com/ "
            "and add it to your .env file."
        )

    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        max_output_tokens=settings.AI_MAX_TOKENS,
        timeout=settings.AI_TIMEOUT_SECONDS,
        # Disable automatic retries here; retry policy lives in the graph nodes.
        max_retries=0,
    )


def _build_groq(model_name: str) -> BaseChatModel:
    """Construct a ChatOpenAI instance pointed at Groq's OpenAI-compatible API.

    Groq offers a generous free tier with fast inference for open-source models
    such as Llama 3.3 70B. No extra package is needed — langchain-openai (already
    installed) works against any OpenAI-compatible endpoint.

    Args:
        model_name: The Groq model identifier (e.g. ``"llama-3.3-70b-versatile"``).

    Returns:
        A configured ``ChatOpenAI`` instance targeting ``api.groq.com``.

    Raises:
        ValueError: When ``GROQ_API_KEY`` is not set.
    """
    from langchain_openai import ChatOpenAI  # noqa: PLC0415

    api_key: str = settings.GROQ_API_KEY
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY is not set. "
            "Obtain a free key at https://console.groq.com/ "
            "and add it to your .env file."
        )

    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
        max_tokens=settings.AI_MAX_TOKENS,
        timeout=settings.AI_TIMEOUT_SECONDS,
        max_retries=0,
    )
