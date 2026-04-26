"""LLM client factory for the AI recommendation pipeline.

Creates the correct LangChain chat model for each pipeline node based on
Django settings. Supports Google Gemini and Groq (OpenAI-compatible API).

Usage::

    from app.ai.client import get_llm, LLMRole

    llm = get_llm(LLMRole.QUERY)       # lightweight model  – query understanding
    llm = get_llm(LLMRole.STATS)       # reasoning model    – statistical analysis
    llm = get_llm(LLMRole.RESPONSE)    # quality model      – response composition
"""
from __future__ import annotations

from enum import StrEnum

from django.conf import settings
from langchain_core.language_models.chat_models import BaseChatModel


class LLMRole(StrEnum):
    """Names for the three pipeline nodes that each need a dedicated LLM."""

    QUERY = "query"       # Node 1: parse / normalise the user's intent
    STATS = "stats"       # Node 2: statistical analysis of DB findings
    RESPONSE = "response" # Node 3: compose the final user-facing recommendation


def structured_output_kwargs() -> dict:
    """Return extra kwargs to pass to ``with_structured_output()`` for the active provider.

    Groq's API does not reliably support ``json_schema`` response format, so we
    fall back to ``function_calling`` (tool use), which every Groq model with
    tool-use support handles correctly.  Gemini via LangChain uses its own
    structured-output path and does not need an explicit method override.
    """
    if settings.AI_PROVIDER.lower() == "groq":
        return {"method": "function_calling"}
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

    Args:
        role: Which pipeline node the model will serve.

    Returns:
        A LangChain ``BaseChatModel`` configured for the role.

    Raises:
        ValueError: If ``settings.AI_PROVIDER`` is not a supported value.
        ValueError: If ``GEMINI_API_KEY`` is empty when using the gemini provider.
    """
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
