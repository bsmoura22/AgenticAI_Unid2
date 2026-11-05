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


def _new_thread_id() -> str:
    return str(uuid.uuid4())


def init_session() -> None:
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = _new_thread_id()
    if "chat" not in st.session_state:
        st.session_state.chat = []
    if "last_meta" not in st.session_state:
        st.session_state.last_meta = {"tools": [], "skills": [], "route": ""}


def render_meta(meta: dict) -> None:
    with st.expander("Ferramentas e skills desta resposta", expanded=True):
        tools = meta.get("tools") or []
        skills = meta.get("skills") or []
        route = meta.get("route") or "—"
        st.markdown(f"**Rota do grafo:** `{route}`")
        st.markdown("**Ferramentas chamadas:**")
        if tools:
            st.code(", ".join(dict.fromkeys(tools)))
        else:
            st.write("Nenhuma tool nesta resposta.")
        st.markdown("**Skills carregadas:**")
        if skills:
            st.code(", ".join(dict.fromkeys(skills)))
        else:
            st.write("Nenhuma skill carregada nesta resposta.")


def main() -> None:
    st.set_page_config(page_title="FridgeChef Ampliado", page_icon="🥗", layout="centered")
    st.title("FridgeChef Ampliado")
    st.caption(
        "Assistente de estoque, receitas e guias culinários — LangGraph + MCP + RAG agêntico"
    )
    init_session()

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Nova conversa", use_container_width=True):
            st.session_state.thread_id = _new_thread_id()
            st.session_state.chat = []
            st.session_state.last_meta = {"tools": [], "skills": [], "route": ""}
            st.rerun()
    with col2:
        st.caption(f"thread: `{st.session_state.thread_id[:8]}…`")

    for turn in st.session_state.chat:
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])
            if turn["role"] == "assistant" and turn.get("meta"):
                render_meta(turn["meta"])

    prompt = st.chat_input("Pergunte sobre estoque, receitas, higiene ou planejamento…")
    if not prompt:
        return

    st.session_state.chat.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    app = get_app()
    config = {"configurable": {"thread_id": st.session_state.thread_id}}
    with st.chat_message("assistant"):
        with st.spinner("Pensando…"):
            try:
                result = app.invoke(
                    {"messages": [HumanMessage(content=prompt)]},
                    config=config,
                )
            except Exception as exc:  # noqa: BLE001
                err = (
                    f"Erro ao executar o grafo: `{exc}`.\n\n"
                    "Verifique se os servidores MCP estão no ar "
                    "(portas 8000 e 8001) e se `OPENAI_API_KEY` está no `.env`."
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
        render_meta(meta)
        st.session_state.chat.append(
            {"role": "assistant", "content": answer, "meta": meta}
        )
        st.session_state.last_meta = meta


if __name__ == "__main__":
    main()
