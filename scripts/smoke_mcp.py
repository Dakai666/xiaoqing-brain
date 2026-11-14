"""MCP server smoke test using the official mcp client (stdio transport)."""
import asyncio
import sys
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
            tools = await session.list_tools()
            safe_print(f"--- {len(tools.tools)} tools registered ---")
            for t in tools.tools:
                safe_print(f"  - {t.name}")

            safe_print("\n--- memory_health ---")
            r = await session.call_tool("memory_health", {})
            text = r.content[0].text if r.content else "(empty)"
            safe_print(text)


if __name__ == "__main__":
    asyncio.run(main())
