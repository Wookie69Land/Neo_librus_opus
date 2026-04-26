"""Compiled LangGraph for the book recommendation pipeline.

Usage::

    from app.ai.recommendations.graph import recommendation_graph

    result_state = await recommendation_graph.ainvoke(initial_state)

The graph is compiled once at module import time and reused across requests.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.ai.recommendations.nodes import (
    analyze_statistics,
    compose_response,
    fetch_candidates,
    understand_query,
)
from app.ai.recommendations.state import RecommendationState

# ── Build graph ────────────────────────────────────────────────────────────────

_builder: StateGraph = StateGraph(RecommendationState)

_builder.add_node("understand_query", understand_query)
_builder.add_node("fetch_candidates", fetch_candidates)
_builder.add_node("analyze_statistics", analyze_statistics)
_builder.add_node("compose_response", compose_response)

_builder.add_edge(START, "understand_query")
_builder.add_edge("understand_query", "fetch_candidates")
_builder.add_edge("fetch_candidates", "analyze_statistics")
_builder.add_edge("analyze_statistics", "compose_response")
_builder.add_edge("compose_response", END)

# Compile once — the compiled graph is thread/coroutine-safe for concurrent invocations.
recommendation_graph = _builder.compile()
