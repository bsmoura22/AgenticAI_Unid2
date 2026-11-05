import asyncio

from fastmcp import Client


async def main():
    async with Client("http://127.0.0.1:8000/mcp") as c:
        tools = await c.list_tools()
        print("OWN tools:", [t.name for t in tools])
        r = await c.call_tool("get_inventory", {})
        print("inventory sample:", str(r)[:300])
    async with Client("http://127.0.0.1:8001/mcp") as c:
        tools = await c.list_tools()
        print("COMM tools:", [t.name for t in tools])
        r = await c.call_tool("get_weather", {"city": "Curitiba"})
        print("weather:", r)


if __name__ == "__main__":
    asyncio.run(main())
