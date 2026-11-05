"""Cliente MCP: servidor próprio FridgeChef + servidor da comunidade."""

from __future__ import annotations

import asyncio
import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain_core.tools import BaseTool, StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from src.skills_loader import load_skill as _load_skill_text

load_dotenv()


def _servers_config() -> dict:
    own = os.getenv("MCP_OWN_URL", "http://127.0.0.1:8000/mcp")
    community = os.getenv("MCP_COMMUNITY_URL", "http://127.0.0.1:8001/mcp")
    return {
        "fridgechef": {
            "url": own,
            "transport": "streamable_http",
        },
        "comunidade": {
            "url": community,
            "transport": "streamable_http",
        },
    }


def make_load_skill_tool() -> BaseTool:
    def _load(name: str) -> str:
        """Carrega as instruções completas de uma skill pelo nome."""
        return _load_skill_text(name)

    return StructuredTool.from_function(
        func=_load,
        name="load_skill",
        description=(
            "Carrega as instruções completas de uma skill pelo nome "
            "(planejar-refeicoes ou substituir-e-comprar)."
        ),
    )


async def _fetch_mcp_tools() -> list[BaseTool]:
    client = MultiServerMCPClient(_servers_config())
    return await client.get_tools()


def _run_async(coro):
    """Executa coroutine mesmo se já houver event loop (ex.: Streamlit)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


@lru_cache(maxsize=1)
def get_all_tools_sync() -> tuple[BaseTool, ...]:
    """Carrega tools MCP + load_skill (cacheia na sessão do processo)."""
    mcp_tools = _run_async(_fetch_mcp_tools())
    return tuple(list(mcp_tools) + [make_load_skill_tool()])


def refresh_tools() -> tuple[BaseTool, ...]:
    get_all_tools_sync.cache_clear()
    return get_all_tools_sync()
