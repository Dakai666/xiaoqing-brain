"""Test memory_search specifically."""
import asyncio
import sys
import os

os.environ["XIAOQING_DATA_DIR"] = r"C:\Users\User\xiaoqing\brain\data"

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def safe_print(s):
    try:
        print(s)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(s.encode("utf-8", errors="replace") + b"\n")
        sys.stdout.buffer.flush()


async def main():
    params = StdioServerParameters(
        command=r"C:\Users\User\xiaoqing\brain\venv\Scripts\python.exe",
        args=[r"C:\Users\User\xiaoqing\brain\mcp_server.py"],
        cwd=r"C:\Users\User\xiaoqing\brain",
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            safe_print(">>> memory_search '繁體中文'")
            r = await session.call_tool("memory_search", {"query": "繁體中文", "top_k": 5})
            safe_print(f"got {len(r.content)} items")
            for i, item in enumerate(r.content):
                safe_print(f"--- item {i} ---")
                safe_print(item.text)

            safe_print("\n>>> memory_index")
            r = await session.call_tool("memory_index", {"limit": 10})
            safe_print(r.content[0].text if r.content else "(none)")


if __name__ == "__main__":
    asyncio.run(main())
