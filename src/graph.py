"""Compilação do grafo LangGraph do FridgeChef Ampliado."""

from __future__ import annotations

from typing import Any, Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import tools_condition

from src.nodes import (
    agent_node,
    apos_rag,
    finalize,
    grade_docs,
    input_guardrail,
    maybe_load_skill,
    output_guardrail,
    prefetch_inventory,
    refuse,
    retrieve_node,
    rewrite_query,
    router,
    tools_with_tracking,
)
from src.state import AgentState


def _after_input(state: AgentState) -> Literal["refuse", "router"]:
    return "refuse" if state.get("blocked") else "router"


def _after_router(state: AgentState) -> Literal["retrieve", "prefetch_inventory"]:
    route = state.get("route") or "ops"
    if route in {"rag", "misto"}:
        return "retrieve"
    return "prefetch_inventory"


def _after_grade(state: AgentState) -> Literal["rewrite_query", "apos_rag"]:
    sufficient = bool(state.get("rag_sufficient"))
    attempts = int(state.get("rag_attempts") or 0)
    if not sufficient and attempts < 2:
        return "rewrite_query"
    return "apos_rag"


def build_graph(checkpointer: Any | None = None):
    graph = StateGraph(AgentState)

    graph.add_node("input_guardrail", input_guardrail)
    graph.add_node("refuse", refuse)
    graph.add_node("router", router)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("grade_docs", grade_docs)
    graph.add_node("rewrite_query", rewrite_query)
    graph.add_node("apos_rag", apos_rag)
    graph.add_node("prefetch_inventory", prefetch_inventory)
    graph.add_node("maybe_load_skill", maybe_load_skill)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_with_tracking)
    graph.add_node("finalize", finalize)
    graph.add_node("output_guardrail", output_guardrail)

    graph.add_edge(START, "input_guardrail")
    graph.add_conditional_edges(
        "input_guardrail",
        _after_input,
        {"refuse": "refuse", "router": "router"},
    )
    graph.add_edge("refuse", END)

    graph.add_conditional_edges(
        "router",
        _after_router,
        {"retrieve": "retrieve", "prefetch_inventory": "prefetch_inventory"},
    )

    graph.add_edge("retrieve", "grade_docs")
    graph.add_conditional_edges(
        "grade_docs",
        _after_grade,
        {"rewrite_query": "rewrite_query", "apos_rag": "apos_rag"},
    )
    graph.add_edge("rewrite_query", "retrieve")

    graph.add_edge("apos_rag", "maybe_load_skill")
    graph.add_edge("prefetch_inventory", "maybe_load_skill")
    graph.add_edge("maybe_load_skill", "agent")

    graph.add_conditional_edges(
        "agent",
        tools_condition,
        {"tools": "tools", "__end__": "finalize"},
    )
    graph.add_edge("tools", "agent")
    graph.add_edge("finalize", "output_guardrail")
    graph.add_edge("output_guardrail", END)

    memory = checkpointer if checkpointer is not None else MemorySaver()
    return graph.compile(checkpointer=memory)


_APP = None


def get_app():
    global _APP
    if _APP is None:
        _APP = build_graph()
    return _APP
