"""Estado tipado do grafo LangGraph."""

from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    route: Literal["rag", "ops", "misto"]
    rag_query: str
    rag_docs: str
    rag_payload: list[dict]
    rag_sufficient: bool
    rag_attempts: int
    inventory_snapshot: str
    active_skill: str
    loaded_skills: list[str]
    called_tools: list[str]
    blocked: bool
    guardrail_reason: str
    final_answer: str
