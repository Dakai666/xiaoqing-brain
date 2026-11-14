"""End-to-end smoke test with real Ollama calls."""
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
            safe_print(">>> initialize OK")

            safe_print("\n>>> memory_health")
            r = await session.call_tool("memory_health", {})
            safe_print(r.content[0].text)

            safe_print("\n>>> memory_add (real Ollama call)")
            r = await session.call_tool("memory_add", {
                "session_id": "smoketest-001",
                "content": "主人是 Dakai666，住在台灣，講繁體中文，喜歡簡潔直接的回覆"
            })
            safe_print(r.content[0].text)

            safe_print("\n>>> memory_search")
            r = await session.call_tool("memory_search", {
                "query": "主人喜歡什麼樣的回覆風格",
                "top_k": 3
            })
            for item in r.content:
                safe_print(item.text)
                safe_print("---")

            safe_print("\n>>> memory_health (after add)")
            r = await session.call_tool("memory_health", {})
            safe_print(r.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())
