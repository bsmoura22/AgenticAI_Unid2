import asyncio
import os

from fastmcp import Client


async def main():
    async with Client("http://127.0.0.1:8000/mcp") as c:
        tools = await c.list_tools()
        print("OWN tools:", [t.name for t in tools])
        r = await c.call_tool("get_inventory", {})
        print("inventory sample:", str(r)[:300])
    async with Client(os.getenv("MCP_COMMUNITY_URL", "https://open-meteo.caseyjhand.com/mcp")) as c:
        tools = await c.list_tools()
        print("COMM tools:", [t.name for t in tools])
        r = await c.call_tool("openmeteo_search_locations", {"name": "Curitiba", "country": "BR", "count": 1})
        print("Curitiba search:", str(r)[:500])


if __name__ == "__main__":
    asyncio.run(main())
