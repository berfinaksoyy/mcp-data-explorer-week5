"""Smoke test over real MCP: start server.py over STDIO, list its tools, call each one.

This checks the server the same way an agent's MCP client talks to it.
Run: python demo_client.py
"""
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).with_name("server.py")

CALLS = [
    ("search_countries", {"query": "united", "limit": 3}),
    ("get_country_details", {"name": "Turkey"}),
    ("get_country_details", {"name": "Korea"}),
    ("get_country_details", {"name": "Atlantis"}),
    ("get_country_details", {"name": "   "}),
    ("search_countries", {"query": "a", "limit": 0}),
]


async def main() -> None:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("Tools:", ", ".join(tool.name for tool in tools.tools))
            for name, args in CALLS:
                result = await session.call_tool(name, args)
                text = "\n".join(part.text for part in result.content if hasattr(part, "text"))
                print(f"\n> {name}({json.dumps(args, ensure_ascii=False)})")
                print(text)


if __name__ == "__main__":
    asyncio.run(main())
