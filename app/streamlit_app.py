"""Interface Streamlit do FridgeChef Ampliado."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from src.graph import get_app  # noqa: E402


UI_CSS = """
<style>
  .stApp { background: #fbf9f4; }
  [data-testid="stHeader"] { background: transparent; }
  [data-testid="stMainBlockContainer"] {
    max-width: 900px;
    padding-top: 2.5rem;
    padding-bottom: 8rem;
  }
  h1 { letter-spacing: -0.035em; font-weight: 750; }
  h2, h3 { letter-spacing: -0.02em; }
  .fc-subtitle { color: #52665a; font-size: 1.05rem; margin: -.35rem 0 1.5rem; }
  .fc-intro { padding: 2.5rem 0 1.25rem; }
  .fc-intro h2 { color: #24352b; font-size: 1.55rem; margin-bottom: .4rem; }
  .fc-intro p { color: #52665a; margin: 0; }
  [data-testid="stChatMessage"] {
    background: #ffffff;
    border: 1px solid #e4e8df;
    border-radius: 16px;
    margin-bottom: .85rem;
  }
  [data-testid="stChatMessageAvatarUser"],
  [data-testid="stChatMessageAvatarAssistant"] {
    background: #e8f2eb;
    color: #216b52;
  }
  [data-testid="stButton"] button {
    border-radius: 10px;
    font-weight: 600;
  }
  [data-testid="stChatInput"] { border-radius: 14px; }
  [data-testid="stGraphVizChart"] {
    background: #fff;
    border: 1px solid #e4e8df;
    border-radius: 14px;
    padding: .75rem;
  }
  ::selection { background: #c8e7d7; color: #173a2d; }
  @media (max-width: 640px) {
    [data-testid="stMainBlockContainer"] { padding-top: 1.5rem; }
    .fc-intro { padding-top: 1.5rem; }
  }
</style>
"""


def graph_dot() -> str:
    """Desenha a estrutura compilada, com rótulos legíveis nas decisões."""
    graph = get_app().get_graph()
    colors = {
        "input_guardrail": "#FDE8E7",
        "refuse": "#FDE8E7",
        "output_guardrail": "#FDE8E7",
        "router": "#E4EDFF",
        "retrieve": "#EFE7FF",
        "grade_docs": "#EFE7FF",
        "rewrite_query": "#EFE7FF",
        "apos_rag": "#EFE7FF",
        "prefetch_inventory": "#DEF5EC",
        "maybe_load_skill": "#FFF0D6",
        "agent": "#FFF0D6",
        "tools": "#FFF0D6",
        "finalize": "#E8EEF3",
    }
    labels = {
        ("input_guardrail", "refuse"): "bloqueado",
        ("input_guardrail", "router"): "aceito",
        ("router", "retrieve"): "RAG / misto",
        ("router", "prefetch_inventory"): "operações",
        ("grade_docs", "rewrite_query"): "insuficiente; até 2 vezes",
        ("grade_docs", "apos_rag"): "suficiente / limite",
        ("agent", "tools"): "chama ferramenta",
        ("agent", "finalize"): "resposta pronta",
        ("tools", "agent"): "resultado",
    }
    lines = [
        "digraph FridgeChef {",
        '  graph [rankdir=TB, bgcolor="#FFFFFF", pad="0.3", nodesep="0.35", ranksep="0.55"];',
        '  node [shape=box, style="rounded,filled", color="#C8D2DC", fontcolor="#18212F", fontname="Helvetica", fontsize=12, margin="0.17,0.10"];',
        '  edge [color="#66788A", fontcolor="#344054", fontname="Helvetica", fontsize=10, arrowsize=0.7];',
    ]
    for node in graph.nodes.values():
        node_id = node.id
        if node_id in {"__start__", "__end__"}:
            title = "Início" if node_id == "__start__" else "Fim"
            lines.append(
                f'  "{node_id}" [label="{title}", shape=oval, fillcolor="#E8EEF3"];'
            )
        else:
            lines.append(
                f'  "{node_id}" [fillcolor="{colors.get(node_id, "#FFFFFF")}"];'
            )
    for edge in graph.edges:
        label = labels.get((edge.source, edge.target))
        suffix = f' [label="{label}"]' if label else ""
        lines.append(f'  "{edge.source}" -> "{edge.target}"{suffix};')
    lines.append("}")
    return "\n".join(lines)


def _new_thread_id() -> str:
    return str(uuid.uuid4())


def init_session() -> None:
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = _new_thread_id()
    if "chat" not in st.session_state:
        st.session_state.chat = []
    if "last_meta" not in st.session_state:
        st.session_state.last_meta = {"tools": [], "skills": [], "route": ""}


def render_meta(meta: dict, *, expanded: bool, key: str) -> None:
    panel = (
        st.expander("Ferramentas e skills desta resposta", expanded=True, key=key)
        if expanded
        else st.popover("Ferramentas e skills desta resposta", key=key)
    )
    with panel:
        tools = meta.get("tools") or []
        skills = meta.get("skills") or []
        route = meta.get("route") or "—"
        st.markdown(f"**Rota do grafo:** `{route}`")
        st.markdown("**Ferramentas chamadas:**")
        if tools:
            st.markdown("\n".join(f"- `{name}`" for name in dict.fromkeys(tools)))
        else:
            st.write("Nenhuma ferramenta chamada nesta resposta.")
        st.markdown("**Skills carregadas:**")
        if skills:
            st.markdown("\n".join(f"- `{name}`" for name in dict.fromkeys(skills)))
        else:
            st.write("Nenhuma skill carregada nesta resposta.")


def main() -> None:
    st.set_page_config(page_title="FridgeChef", page_icon="🥗", layout="centered")
    st.markdown(UI_CSS, unsafe_allow_html=True)
    st.title("FridgeChef")
    st.markdown(
        '<p class="fc-subtitle">Cozinhe melhor com o que você já tem.</p>',
        unsafe_allow_html=True,
    )
    view = st.segmented_control(
        "Navegação",
        ["Conversa", "Fluxo do agente"],
        default="Conversa",
        key="view",
        label_visibility="collapsed",
        width="stretch",
    )
    if view == "Fluxo do agente":
        st.subheader("Como o assistente decide")
        st.caption(
            "O roteador escolhe documentos, operações ou os dois. "
            "A busca pode ser refeita até duas vezes e o agente volta após cada ferramenta."
        )
        st.graphviz_chart(
            graph_dot(),
            width="stretch",
            alt="Fluxo do agente: guardrail de entrada, roteamento, RAG ou estoque, "
            "skill, agente e ferramentas em ciclo, finalização e guardrail de saída.",
        )
        return

    init_session()
    st.divider()
    title_col, action_col = st.columns([3, 1], vertical_alignment="center")
    with title_col:
        st.subheader("Conversa")
    with action_col:
        if st.button("Nova conversa", use_container_width=True):
            st.session_state.thread_id = _new_thread_id()
            st.session_state.chat = []
            st.session_state.last_meta = {"tools": [], "skills": [], "route": ""}
            st.rerun()

    selected_prompt = None
    if not st.session_state.chat:
        intro = st.empty()
        with intro.container():
            st.markdown(
                '<div class="fc-intro"><h2>O que vamos cozinhar hoje?</h2>'
                '<p>Pergunte sobre seu estoque, planeje refeições ou consulte os guias culinários.</p></div>',
                unsafe_allow_html=True,
            )
            examples = [
                ("Ver meu estoque", "Liste meu estoque atual."),
                ("Planejar refeições", "Planeje duas refeições com meu estoque, sem alterá-lo."),
                ("Higienizar alimentos", "Como higienizar frutas e verduras para consumo cru?"),
            ]
            for column, (label, question) in zip(st.columns(3), examples):
                with column:
                    if st.button(label, key=f"example-{label}", use_container_width=True):
                        selected_prompt = question
        if selected_prompt:
            intro.empty()

    last_assistant_index = next(
        (
            index
            for index in range(len(st.session_state.chat) - 1, -1, -1)
            if st.session_state.chat[index]["role"] == "assistant"
        ),
        None,
    )
    for index, turn in enumerate(st.session_state.chat):
        avatar = ":material/person:" if turn["role"] == "user" else ":material/restaurant:"
        with st.chat_message(turn["role"], avatar=avatar):
            st.markdown(turn["content"])
            if turn["role"] == "assistant" and turn.get("meta"):
                latest = index == last_assistant_index
                render_meta(
                    turn["meta"],
                    expanded=latest,
                    key=f"meta-{st.session_state.thread_id}-{index}-{'latest' if latest else 'older'}",
                )

    typed_prompt = st.chat_input(
        "Pergunte sobre estoque, receitas, higiene ou planejamento…"
    )
    prompt = selected_prompt or typed_prompt
    if not prompt:
        return

    st.session_state.chat.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(prompt)

    app = get_app()
    config = {"configurable": {"thread_id": st.session_state.thread_id}}
    with st.chat_message("assistant", avatar=":material/restaurant:"):
        with st.spinner("Pensando…"):
            try:
                result = app.invoke(
                    {"messages": [HumanMessage(content=prompt)]},
                    config=config,
                )
            except Exception as exc:  # noqa: BLE001
                err = (
                    f"Erro ao executar o grafo: `{exc}`.\n\n"
                    "Verifique se o MCP próprio está no ar (porta 8000), "
                    "se o servidor público de clima está acessível e se "
                    "`OPENAI_API_KEY` está no `.env`."
                )
                st.error(err)
                st.session_state.chat.append({"role": "assistant", "content": err, "meta": {}})
                return

        answer = result.get("final_answer")
        if not answer:
            for msg in reversed(result.get("messages", [])):
                if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
                    answer = msg.content
                    break
        answer = answer or "(sem resposta)"
        meta = {
            "tools": result.get("called_tools") or [],
            "skills": result.get("loaded_skills") or [],
            "route": result.get("route") or "",
        }
        st.markdown(answer)
        render_meta(
            meta,
            expanded=True,
            key=f"meta-{st.session_state.thread_id}-{len(st.session_state.chat)}-latest",
        )
        st.session_state.chat.append(
            {"role": "assistant", "content": answer, "meta": meta}
        )
        st.session_state.last_meta = meta


if __name__ == "__main__":
    main()
