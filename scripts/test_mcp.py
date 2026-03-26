import asyncio
import os
from brain.mcp.server import call_tool, _memory_search, _memory_add


async def test_mcp():
    os.makedirs("./data", exist_ok=True)
    
    with open('.env', 'r') as f:
        for line in f:
            if line.startswith('MINIMAX_API_KEY='):
                os.environ['MINIMAX_API_KEY'] = line.strip().split('=', 1)[1]
                break

    from brain.utils.llm_backend import MiniMaxBackend, set_llm_backend
    set_llm_backend(MiniMaxBackend())
    
    print("=== MCP Server 測試 ===\n")
    
    # Test memory_add
    print("1. 測試 memory_add...")
    result = await call_tool("memory_add", {
        "session_id": "test-session-1",
        "content": "使用者說他最喜歡 Python，平時用 VSCode 開發"
    })
    print(f"   結果: {result[0].text}")
    
    # Test memory_search
    print("\n2. 測試 memory_search...")
    result = await call_tool("memory_search", {
        "query": "程式語言",
        "top_k": 3
    })
    print(f"   找到 {len(result)} 個結果:")
    for r in result:
        print(f"   - {r.text[:80]}...")
    
    print("\n=== MCP 測試完成 ===")


if __name__ == "__main__":
    asyncio.run(test_mcp())
