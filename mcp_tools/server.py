import os
import asyncio
from typing import Optional
from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.stdio import stdio_server

from ..models.memory_unit import MemoryUnit
from ..stages.compression import CompressionStage
from ..retrieval.hybrid import HybridRetriever


server = Server("xiaoqing-memory")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="memory_search",
            description="搜尋小晴的記憶",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜尋查詢"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "回傳結果數量",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="memory_add",
            description="新增對話到小晴的記憶",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "對話 session ID"
                    },
                    "content": {
                        "type": "string",
                        "description": "要儲存的對話內容"
                    }
                },
                "required": ["session_id", "content"]
            }
        ),
        Tool(
            name="memory_get_by_topic",
            description="依主題取得小晴的記憶",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "主題分類"
                    }
                },
                "required": ["topic"]
            }
        ),
        Tool(
            name="memory_get_by_person",
            description="依人員取得小晴的記憶",
            inputSchema={
                "type": "object",
                "properties": {
                    "person": {
                        "type": "string",
                        "description": "人名"
                    }
                },
                "required": ["person"]
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "memory_search":
        return await _memory_search(arguments["query"], arguments.get("top_k", 5))
    elif name == "memory_add":
        return await _memory_add(arguments["session_id"], arguments["content"])
    elif name == "memory_get_by_topic":
        return await _memory_get_by_topic(arguments["topic"])
    elif name == "memory_get_by_person":
        return await _memory_get_by_person(arguments["person"])
    else:
        raise ValueError(f"Unknown tool: {name}")


async def _memory_search(query: str, top_k: int) -> list[TextContent]:
    compression = CompressionStage(model="MiniMax-M2.7")
    retriever = HybridRetriever()
    
    results = await retriever.search(query, top_k)
    
    output = []
    for m in results.get("vector", []) + results.get("bm25", []):
        output.append(TextContent(
            type="text",
            text=f"[{m.topic}] {m.lossless_text}\n關鍵詞: {', '.join(m.keywords)}\n時間: {m.timestamp}"
        ))
    
    return output


async def _memory_add(session_id: str, content: str) -> list[TextContent]:
    compression = CompressionStage(model="MiniMax-M2.7")
    retriever = HybridRetriever()
    
    memories = await compression.process(content)
    
    for m in memories:
        m.session_id = session_id
        await retriever.add_memory(m)
    
    return [TextContent(
        type="text",
        text=f"已儲存 {len(memories)} 個記憶單元"
    )]


async def _memory_get_by_topic(topic: str) -> list[TextContent]:
    retriever = HybridRetriever()
    
    results = await retriever.lancedb.get_by_topic(topic)
    
    output = []
    for m in results:
        output.append(TextContent(
            type="text",
            text=f"[{m.topic}] {m.lossless_text}\n關鍵詞: {', '.join(m.keywords)}\n時間: {m.timestamp}"
        ))
    
    return output


async def _memory_get_by_person(person: str) -> list[TextContent]:
    retriever = HybridRetriever()
    
    results = await retriever.lancedb.get_by_person(person)
    
    output = []
    for m in results:
        output.append(TextContent(
            type="text",
            text=f"[{m.topic}] {m.lossless_text}\n關鍵詞: {', '.join(m.keywords)}\n時間: {m.timestamp}"
        ))
    
    return output


async def main():
    from ..utils.llm_backend import MiniMaxBackend, set_llm_backend
    
    with open('.env', 'r') as f:
        for line in f:
            if line.startswith('MINIMAX_API_KEY='):
                os.environ['MINIMAX_API_KEY'] = line.strip().split('=', 1)[1]
                break
    
    set_llm_backend(MiniMaxBackend())
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
