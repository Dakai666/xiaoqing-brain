#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, '/home/user/.kimaki/projects/xiaoqing')

import asyncio
from mcp.server import Server
from mcp.types import Tool, TextContent, Prompt
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
from brain.accounting import AccountingService


server = Server("xiaoqing-memory")
_accounting_service = None


def get_accounting_service():
    global _accounting_service
    if _accounting_service is None:
        _accounting_service = AccountingService()
    return _accounting_service


@server.list_prompts()
async def list_prompts() -> list[Prompt]:
    return []


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
        Tool(
            name="memory_get_context",
            description="取得上下文相關的記憶，方便小晴在回覆時引用（主動記憶注入）",
            inputSchema={
                "type": "object",
                "properties": {
                    "context": {"type": "string", "description": "當前對話情境或話題"},
                    "top_k": {"type": "integer", "description": "回傳結果數量", "default": 3}
                },
                "required": ["context"]
            }
        ),
        Tool(
            name="accounting_add",
            description="新增一筆帳目記錄（支援自然語言或結構化輸入）",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "帳目描述，例如「今天中午吃飯花了120元」或「expense:120:food:午餐」"},
                    "session_id": {"type": "string", "description": "對話 session ID"}
                },
                "required": ["text", "session_id"]
            }
        ),
        Tool(
            name="accounting_summary",
            description="取得本月記帳摘要（收入/支出/分類統計）",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "查詢天數範圍", "default": 30}
                }
            }
        ),
        Tool(
            name="accounting_today",
            description="取得今天的所有記帳記錄",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="accounting_all",
            description="取得所有記帳記錄（最近50筆）",
            inputSchema={
                "type": "object",
                "properties": {}
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
    elif name == "memory_get_context":
        return await _memory_get_context(arguments["context"], arguments.get("top_k", 3))
    elif name == "accounting_add":
        return await _accounting_add(arguments["text"], arguments["session_id"])
    elif name == "accounting_summary":
        return await _accounting_summary(arguments.get("days", 30))
    elif name == "accounting_today":
        return await _accounting_today()
    elif name == "accounting_all":
        return await _accounting_all()
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


async def _memory_get_context(context: str, top_k: int = 3) -> list[TextContent]:
    retriever = HybridRetriever()
    intent_retriever = IntentRetriever(retriever)
    results = await intent_retriever.search(context, top_k)

    output = []
    memories = results.get("results", [])

    if not memories:
        return [TextContent(type="text", text="找不到相關的記憶")]

    lines = [f"找到 {len(memories)} 筆相關記憶："]

    for i, m in enumerate(memories, 1):
        time_distance = m.get_time_distance()
        confidence_pct = int(m.confidence * 100)

        lines.append(f"\n{i}. {m.lossless_text}")
        lines.append(f"   💡 這是{time_distance}的事，信心度 {confidence_pct}%")
        if m.keywords:
            lines.append(f"   關鍵詞: {', '.join(m.keywords[:3])}")

    output.append(TextContent(type="text", text="\n".join(lines)))
    return output


async def _accounting_add(text: str, session_id: str) -> list[TextContent]:
    svc = get_accounting_service()
    ok, msg, tx = svc.add_transaction(text, session_id)
    if ok:
        return [TextContent(type="text", text=f"✅ {msg}")]
    else:
        return [TextContent(type="text", text=f"❌ {msg}")]


async def _accounting_summary(days: int) -> list[TextContent]:
    svc = get_accounting_service()
    summary = svc.get_summary(days)
    return [TextContent(type="text", text=summary)]


async def _accounting_today() -> list[TextContent]:
    svc = get_accounting_service()
    result = svc.get_today()
    return [TextContent(type="text", text=result)]


async def _accounting_all() -> list[TextContent]:
    svc = get_accounting_service()
    result = svc.get_all()
    return [TextContent(type="text", text=result)]


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
