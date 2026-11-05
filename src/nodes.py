"""Nós do grafo FridgeChef Ampliado."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from src.mcp_client import get_all_tools_sync
from src.prompts import build_system_prompt
from src.rag import retrieve
from src.skills_loader import load_skill
from src.state import AgentState

INJECTION_PATTERNS = [
    r"ignore\s+(todas\s+)?(as\s+)?instru",
    r"ignore\s+(all\s+)?(previous|above)\s+instructions",
    r"disregard\s+(your|the)\s+system",
    r"revela\s+(o\s+)?(system\s*)?prompt",
    r"jailbreak",
    r"DAN\s+mode",
]

OUT_OF_SCOPE_PATTERNS = [
    r"\b(bitcoin|cryptocurrency|código\s+malicioso|exploit|hackear)\b",
    r"\b(trabalho\s+de\s+casa\s+de\s+cálculo|equações\s+diferenciais)\b",
    r"\b(eleições|partido\s+político)\b",
]

MEDICAL_LEAK_PATTERNS = [
    r"\bcure\s+(diabetes|câncer|cancer)\b",
    r"\bcura\s+(diabetes|câncer|cancer)\b",
    r"\btome\s+\d+\s*mg\b",
    r"\bdiagnóstico\s+médico\b",
]

SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9]{10,}",
    r"OPENAI_API_KEY\s*=\s*\S+",
    r"api[_-]?key\s*[:=]\s*\S+",
]


def get_llm(temperature: float = 0.0) -> ChatOpenAI:
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    return ChatOpenAI(model=model, temperature=temperature)


def _last_user_text(state: AgentState) -> str:
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            content = msg.content
            return content if isinstance(content, str) else str(content)
        if getattr(msg, "type", None) == "human":
            return str(msg.content)
    return ""


def _reset_turn_fields() -> dict[str, Any]:
    """Limpa metadados do turno atual (evita carregar lixo da thread)."""
    return {
        "called_tools": [],
        "loaded_skills": [],
        "active_skill": "",
        "rag_docs": "",
        "rag_payload": [],
        "rag_attempts": 0,
        "rag_sufficient": False,
        "inventory_snapshot": "",
        "final_answer": "",
        "blocked": False,
        "guardrail_reason": "",
    }


def _extend_tools(state: AgentState, *names: str) -> list[str]:
    current = list(state.get("called_tools") or [])
    current.extend(names)
    return current


def _extend_skills(state: AgentState, *names: str) -> list[str]:
    current = list(state.get("loaded_skills") or [])
    for name in names:
        if name and name not in current:
            current.append(name)
    return current


def input_guardrail(state: AgentState) -> dict[str, Any]:
    text = _last_user_text(state).lower()
    base = _reset_turn_fields()
    for pat in INJECTION_PATTERNS:
        if re.search(pat, text, flags=re.IGNORECASE):
            base.update(
                {
                    "blocked": True,
                    "guardrail_reason": "prompt_injection",
                    "final_answer": (
                        "Não posso atender a esse pedido: parece uma tentativa de "
                        "ignorar as instruções do assistente."
                    ),
                }
            )
            return base
    for pat in OUT_OF_SCOPE_PATTERNS:
        if re.search(pat, text, flags=re.IGNORECASE):
            base.update(
                {
                    "blocked": True,
                    "guardrail_reason": "fora_de_escopo",
                    "final_answer": (
                        "Esse pedido está fora do escopo do FridgeChef "
                        "(estoque, receitas, higiene e técnica culinária)."
                    ),
                }
            )
            return base
    return base


def refuse(state: AgentState) -> dict[str, Any]:
    answer = state.get("final_answer") or "Pedido bloqueado pelo guardrail de entrada."
    return {"messages": [AIMessage(content=answer)], "final_answer": answer}


class RouteDecision(BaseModel):
    route: Literal["rag", "ops", "misto"] = Field(
        description="rag=documentos; ops=estoque/receitas; misto=ambos"
    )
    rag_query: str = Field(
        default="",
        description="Consulta para busca documental quando route é rag ou misto",
    )
    skill_hint: str = Field(
        default="",
        description="planejar-refeicoes | substituir-e-comprar | vazio",
    )


def router(state: AgentState) -> dict[str, Any]:
    user = _last_user_text(state)
    llm = get_llm().with_structured_output(RouteDecision)
    decision: RouteDecision = llm.invoke(
        [
            SystemMessage(
                content=(
                    "Classifique a intenção do usuário do FridgeChef.\n"
                    "- rag: dúvidas sobre higiene, conservação, técnica culinária, guias.\n"
                    "- ops: estoque, receitas, substituições cadastradas, compras, plano de refeições.\n"
                    "- misto: precisa de documentos E operações de estoque/receitas.\n"
                    "Se mencionar planejar várias refeições, skill_hint=planejar-refeicoes.\n"
                    "Se mencionar falta/substituição/lista de compras, skill_hint=substituir-e-comprar."
                )
            ),
            HumanMessage(content=user),
        ]
    )
    rag_query = decision.rag_query or user
    updates: dict[str, Any] = {
        "route": decision.route,
        "rag_query": rag_query,
        "rag_attempts": 0,
        "rag_sufficient": False,
        "rag_docs": "",
        "rag_payload": [],
    }
    if decision.skill_hint in {"planejar-refeicoes", "substituir-e-comprar"}:
        updates["active_skill"] = load_skill(decision.skill_hint)
        updates["loaded_skills"] = _extend_skills(state, decision.skill_hint)
    return updates


def retrieve_node(state: AgentState) -> dict[str, Any]:
    query = state.get("rag_query") or _last_user_text(state)
    formatted, payload = retrieve(query, k=4)
    return {
        "rag_docs": formatted,
        "rag_payload": payload,
        "called_tools": _extend_tools(state, "retrieve_docs"),
    }


class GradeResult(BaseModel):
    sufficient: bool = Field(description="Se os trechos bastam para responder a pergunta")
    reason: str = Field(description="Justificativa curta")


def grade_docs(state: AgentState) -> dict[str, Any]:
    user = _last_user_text(state)
    docs = state.get("rag_docs") or ""
    if not docs or docs.startswith("(nenhum"):
        return {"rag_sufficient": False}
    llm = get_llm().with_structured_output(GradeResult)
    result: GradeResult = llm.invoke(
        [
            SystemMessage(
                content=(
                    "Avalie se os trechos recuperados são suficientes para responder "
                    "a pergunta sobre cozinha/higiene/técnica. Se os trechos não "
                    "falarem do tema, sufficient=false."
                )
            ),
            HumanMessage(content=f"Pergunta: {user}\n\nTrechos:\n{docs}"),
        ]
    )
    return {"rag_sufficient": bool(result.sufficient)}


def rewrite_query(state: AgentState) -> dict[str, Any]:
    user = _last_user_text(state)
    prev = state.get("rag_query") or user
    llm = get_llm()
    msg = llm.invoke(
        [
            SystemMessage(
                content=(
                    "Reformule a consulta de busca vetorial para documentos de "
                    "culinária/higiene. Devolva apenas a nova consulta, sem aspas."
                )
            ),
            HumanMessage(
                content=f"Pergunta original: {user}\nConsulta anterior: {prev}"
            ),
        ]
    )
    new_q = str(msg.content).strip()
    return {
        "rag_query": new_q,
        "rag_attempts": int(state.get("rag_attempts") or 0) + 1,
        "called_tools": _extend_tools(state, "rewrite_query"),
    }


def prefetch_inventory(state: AgentState) -> dict[str, Any]:
    """Tenta ler estoque via tool MCP get_inventory."""
    tools = {t.name: t for t in get_all_tools_sync()}
    # nomes prefixados: fridgechef_get_inventory
    candidates = [n for n in tools if n.endswith("get_inventory") or n == "get_inventory"]
    if not candidates:
        return {"inventory_snapshot": "(estoque indisponível: tool não encontrada)"}
    tool = tools[candidates[0]]
    try:
        result = tool.invoke({})
    except Exception as exc:  # noqa: BLE001
        return {"inventory_snapshot": f"(falha ao ler estoque: {exc})"}
    text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
    return {
        "inventory_snapshot": text,
        "called_tools": _extend_tools(state, candidates[0]),
    }


def maybe_load_skill(state: AgentState) -> dict[str, Any]:
    if state.get("active_skill"):
        return {}
    user = _last_user_text(state).lower()
    if any(
        k in user
        for k in ("planejar", "cardápio", "cardapio", "sequência", "sequencia", "várias refeições", "varias refeicoes")
    ):
        return {
            "active_skill": load_skill("planejar-refeicoes"),
            "loaded_skills": _extend_skills(state, "planejar-refeicoes"),
        }
    if any(
        k in user
        for k in ("substit", "lista de compra", "o que falta", "shopping")
    ):
        return {
            "active_skill": load_skill("substituir-e-comprar"),
            "loaded_skills": _extend_skills(state, "substituir-e-comprar"),
        }
    return {}


def apos_rag(state: AgentState) -> dict[str, Any]:
    """Ponte após RAG: se route misto, pré-carrega estoque; senão só segue."""
    if state.get("route") == "misto":
        return prefetch_inventory(state)
    return {}


def agent_node(state: AgentState) -> dict[str, Any]:
    tools = list(get_all_tools_sync())
    llm = get_llm().bind_tools(tools)
    extra_parts = []
    if state.get("inventory_snapshot"):
        extra_parts.append(f"Estoque atual:\n{state['inventory_snapshot']}")
    if state.get("rag_docs"):
        extra_parts.append(f"Trechos documentais:\n{state['rag_docs']}")
    system = build_system_prompt(
        active_skill=state.get("active_skill"),
        extra_context="\n\n".join(extra_parts),
    )
    messages = [SystemMessage(content=system), *state.get("messages", [])]
    response = llm.invoke(messages)
    called: list[str] = []
    if isinstance(response, AIMessage) and response.tool_calls:
        called = [tc["name"] for tc in response.tool_calls]
        # se load_skill for chamado, registrar skill
        loaded = []
        for tc in response.tool_calls:
            if tc["name"] == "load_skill":
                name = (tc.get("args") or {}).get("name")
                if name:
                    loaded.append(name)
        updates: dict[str, Any] = {
            "messages": [response],
            "called_tools": _extend_tools(state, *called),
        }
        if loaded:
            updates["active_skill"] = load_skill(loaded[0])
            updates["loaded_skills"] = _extend_skills(state, *loaded)
        return updates
    return {"messages": [response], "called_tools": _extend_tools(state, *called)}


def build_tool_node() -> ToolNode:
    return ToolNode(list(get_all_tools_sync()))


def tools_with_tracking(state: AgentState) -> dict[str, Any]:
    node = build_tool_node()
    result = node.invoke(state)
    # ToolNode returns messages; extract tool names from last AI tool_calls
    names: list[str] = []
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            names = [tc["name"] for tc in msg.tool_calls]
            break
    out = dict(result)
    if names:
        out["called_tools"] = _extend_tools(state, *names)
    return out


def finalize(state: AgentState) -> dict[str, Any]:
    # última mensagem AI sem tool calls
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, AIMessage) and not msg.tool_calls:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            return {"final_answer": content}
    # se só houve RAG puro e o agent não rodou bem, gera resposta com docs
    if state.get("rag_docs") and state.get("route") == "rag":
        llm = get_llm()
        user = _last_user_text(state)
        msg = llm.invoke(
            [
                SystemMessage(
                    content=(
                        "Responda em português com base apenas nos trechos. "
                        "Cite a fonte (nome do arquivo). Se insuficiente, diga que não encontrou."
                    )
                ),
                HumanMessage(
                    content=f"Pergunta: {user}\n\nTrechos:\n{state['rag_docs']}"
                ),
            ]
        )
        answer = str(msg.content)
        return {"messages": [AIMessage(content=answer)], "final_answer": answer}
    return {"final_answer": state.get("final_answer") or "Não foi possível gerar resposta."}


def output_guardrail(state: AgentState) -> dict[str, Any]:
    answer = state.get("final_answer") or ""
    for pat in SECRET_PATTERNS:
        if re.search(pat, answer, flags=re.IGNORECASE):
            safe = (
                "Removi conteúdo sensível da resposta (possível vazamento de credenciais). "
                "Reformule sua pergunta sobre cozinha/estoque."
            )
            return {
                "final_answer": safe,
                "messages": [AIMessage(content=safe)],
                "guardrail_reason": "vazamento",
            }
    for pat in MEDICAL_LEAK_PATTERNS:
        if re.search(pat, answer, flags=re.IGNORECASE):
            safe = (
                "Não forneço orientações médicas ou de tratamento. "
                "Posso ajudar com receitas, estoque e higiene alimentar geral."
            )
            return {
                "final_answer": safe,
                "messages": [AIMessage(content=safe)],
                "guardrail_reason": "risco_medico",
            }
    return {"final_answer": answer}
