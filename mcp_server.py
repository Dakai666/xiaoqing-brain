#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, '/home/user/.kimaki/projects/xiaoqing')

import asyncio
from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.stdio import stdio_server

from brain.models.memory_unit import MemoryUnit
from brain.stages.compression import CompressionStage
from brain.stages.consolidation import ConsolidationScheduler
from brain.stages.synthesis import SynthesisStage
from brain.storage.sqlite import SQLiteStorage
from brain.storage.markdown import MarkdownBackup
from brain.retrieval.hybrid import HybridRetriever
from brain.retrieval.intent import IntentRetriever
from brain.utils.llm_backend import MiniMaxBackend, set_llm_backend


server = Server("xiaoqing-memory")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="memory_health",
            description="檢查小晴記憶系統健康狀態",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="memory_search",
            description="搜尋小晴的記憶",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜尋查詢"},
                    "top_k": {"type": "integer", "description": "回傳結果數量", "default": 5}
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
                    "session_id": {"type": "string", "description": "對話 session ID"},
                    "content": {"type": "string", "description": "要儲存的對話內容"}
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
                    "topic": {"type": "string", "description": "主題分類"}
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
                    "person": {"type": "string", "description": "人名"}
                },
                "required": ["person"]
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "memory_health":
        return await _memory_health()
    elif name == "memory_search":
        return await _memory_search(arguments["query"], arguments.get("top_k", 5))
    elif name == "memory_add":
        return await _memory_add(arguments["session_id"], arguments["content"])
    elif name == "memory_get_by_topic":
        return await _memory_get_by_topic(arguments["topic"])
    elif name == "memory_get_by_person":
        return await _memory_get_by_person(arguments["person"])
    else:
        raise ValueError(f"Unknown tool: {name}")


async def _memory_health() -> list[TextContent]:
    try:
        sqlite = SQLiteStorage()
        total = len(sqlite.search('', 1000))
        today_memories = sqlite.get_today_memories()
        
        status_parts = [
            f"✅ 記憶系統正常運作",
            f"總記憶: {total} 筆",
            f"今日新增: {len(today_memories)} 筆",
        ]
        
        return [TextContent(type="text", text="\n".join(status_parts))]
    except Exception as e:
        return [TextContent(type="text", text=f"❌ 記憶系統錯誤: {str(e)}")]


async def _memory_search(query: str, top_k: int) -> list[TextContent]:
    retriever = HybridRetriever()
    intent_retriever = IntentRetriever(retriever)
    results = await intent_retriever.search(query, top_k)
    
    output = []
    for m in results.get("results", []):
        time_distance = m.get_time_distance()
        output.append(TextContent(
            type="text",
            text=f"[{m.topic}] {m.lossless_text}\n關鍵詞: {', '.join(m.keywords)}\n時間: {time_distance} ({m.timestamp})"
        ))
    
    return output if output else [TextContent(type="text", text="找不到相關記憶")]


async def _memory_add(session_id: str, content: str) -> list[TextContent]:
    compression = CompressionStage(model="MiniMax-M2.7")
    retriever = HybridRetriever()
    
    memories = await compression.process(content)
    
    for m in memories:
        m.session_id = session_id
        await retriever.add_memory(m)
    
    return [TextContent(type="text", text=f"已儲存 {len(memories)} 個記憶單元")]


async def _memory_get_by_topic(topic: str) -> list[TextContent]:
    retriever = HybridRetriever()
    results = await retriever.lancedb.get_by_topic(topic)
    
    output = []
    for m in results:
        time_distance = m.get_time_distance()
        output.append(TextContent(
            type="text",
            text=f"[{m.topic}] {m.lossless_text}\n關鍵詞: {', '.join(m.keywords)}\n時間: {time_distance} ({m.timestamp})"
        ))
    
    return output if output else [TextContent(type="text", text=f"找不到主題為 {topic} 的記憶")]


async def _memory_get_by_person(person: str) -> list[TextContent]:
    retriever = HybridRetriever()
    results = await retriever.lancedb.get_by_person(person)
    
    output = []
    for m in results:
        time_distance = m.get_time_distance()
        output.append(TextContent(
            type="text",
            text=f"[{m.topic}] {m.lossless_text}\n關鍵詞: {', '.join(m.keywords)}\n時間: {time_distance} ({m.timestamp})"
        ))
    
    return output if output else [TextContent(type="text", text=f"找不到與 {person} 相關的記憶")]


def _write_health_status(status: str, error: str = None):
    status_file = '/home/user/.kimaki/projects/xiaoqing/data/brain_mcp_status.json'
    import json
    from datetime import datetime
    data = {
        "status": status,
        "error": error,
        "last_check": datetime.now().isoformat()
    }
    try:
        with open(status_file, 'w') as f:
            json.dump(data, f)
    except Exception:
        pass


async def main():
    try:
        with open('/home/user/.kimaki/projects/xiaoqing/.env', 'r') as f:
            for line in f:
                if line.startswith('MINIMAX_API_KEY='):
                    os.environ['MINIMAX_API_KEY'] = line.strip().split('=', 1)[1]
                    break
        
        set_llm_backend(MiniMaxBackend())
        
        sqlite = SQLiteStorage()
        synthesis = SynthesisStage(model="MiniMax-M2.7")
        markdown_backup = MarkdownBackup()
        scheduler = ConsolidationScheduler(sqlite, synthesis, markdown_backup, interval_hours=24)
        scheduler.start()
        
        _write_health_status("running")
        print("MCP Server started successfully", flush=True, file=sys.stderr)
        
    except Exception as e:
        _write_health_status("error", str(e))
        print(f"MCP Server startup failed: {e}", flush=True, file=sys.stderr)
        raise
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
