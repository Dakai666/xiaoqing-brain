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
from brain.storage.lancedb import LanceDBStorage
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
            name="memory_index",
            description="取得記憶索引（Progressive Disclosure Layer 1）- 只回傳 ID、標題、時間、token 估計，不回傳完整內容。用於快速掃描決定是否需要深入。",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "回傳數量上限", "default": 50},
                    "date": {"type": "string", "description": "過濾特定日期 (YYYY-MM-DD)", "default": ""}
                }
            }
        ),
        Tool(
            name="memory_timeline",
            description="取得記憶時間上下文（Progressive Disclosure Layer 2）- 以某筆記憶為中心，回傳前後發生了什麼。幫助理解脈絡敘事。",
            inputSchema={
                "type": "object",
                "properties": {
                    "anchor_id": {"type": "string", "description": "中心記憶的 ID（從 memory_index 取得）"},
                    "depth_before": {"type": "integer", "description": "往前取幾筆", "default": 3},
                    "depth_after": {"type": "integer", "description": "往後取幾筆", "default": 3}
                },
                "required": ["anchor_id"]
            }
        ),
        Tool(
            name="memory_search",
            description="搜尋小晴的記憶。可用 `ids` 參數指定特定 ID 直接取得完整內容（Layer 3），或使用 `query` 進行語意搜尋。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜尋查詢"},
                    "ids": {"type": "array", "items": {"type": "string"}, "description": "直接指定記憶 ID 取得完整內容（Layer 3）"},
                    "start_date": {"type": "string", "description": "開始日期 (YYYY-MM-DD)", "default": ""},
                    "end_date": {"type": "string", "description": "結束日期 (YYYY-MM-DD)", "default": ""},
                    "top_k": {"type": "integer", "description": "回傳結果數量", "default": 5}
                }
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
    elif name == "memory_index":
        return await _memory_index(arguments.get("limit", 50), arguments.get("date", ""))
    elif name == "memory_timeline":
        return await _memory_timeline(
            arguments.get("anchor_id", ""),
            arguments.get("depth_before", 3),
            arguments.get("depth_after", 3)
        )
    elif name == "memory_search":
        return await _memory_search(
            arguments.get("query", ""),
            arguments.get("ids"),
            arguments.get("top_k", 5),
            arguments.get("start_date", ""),
            arguments.get("end_date", "")
        )
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
        lancedb = LanceDBStorage()
        
        sqlite_total = len(sqlite.search('', 1000))
        lancedb_total = len(lancedb.db["memories"].search(None).limit(10000).to_list())
        today_memories = sqlite.get_today_memories()
        
        sync_status = "✅" if sqlite_total == lancedb_total else f"⚠️ 差{lancedb_total - sqlite_total}筆"
        
        status_parts = [
            f"✅ 記憶系統正常運作",
            f"SQLite: {sqlite_total} 筆",
            f"LanceDB: {lancedb_total} 筆 ({sync_status})",
            f"今日新增: {len(today_memories)} 筆",
        ]
        
        return [TextContent(type="text", text="\n".join(status_parts))]
    except Exception as e:
        return [TextContent(type="text", text=f"❌ 記憶系統錯誤: {str(e)}")]


async def _memory_index(limit: int, date: str) -> list[TextContent]:
    """Progressive Disclosure Layer 1: 取得記憶索引"""
    try:
        retriever = HybridRetriever()
        
        index_entries = await retriever.lancedb.get_index(limit=limit, date=date if date else None)
        
        if not index_entries:
            return [TextContent(type="text", text="沒有找到任何記憶")]
        
        lines = [
            "## 小晴記憶索引（Progressive Disclosure Layer 1）",
            "",
            "**使用方式**：查看標題和 token 估計，決定是否需要深入 fetch 完整內容。",
            "",
            "| ID | 時間 | Icon | 標題 | ~Tokens |",
            "|----|------|------|------|--------|",
        ]
        
        for entry in index_entries:
            intent_type = entry.get("intent_type", "fact")
            icon = _get_icon_for_type(intent_type)
            entry_id = entry["id"][:8]
            time_str = entry.get("timestamp", "")[11:16] if entry.get("timestamp") else ""
            date_str = entry.get("date", "")[5:] if entry.get("date") else ""
            title = entry.get("title", "")[:50]
            tokens = entry.get("token_estimate", 0)
            
            lines.append(f"| {entry_id} | {date_str} {time_str} | {icon} | {title} | ~{tokens} |")
        
        lines.append("")
        lines.append("*使用 `memory_search` 並指定 IDs 參數來取得感興趣的完整內容*")
        
        return [TextContent(type="text", text="\n".join(lines))]
    except Exception as e:
        return [TextContent(type="text", text=f"❌ 取得索引失敗: {str(e)}")]


async def _memory_timeline(anchor_id: str, depth_before: int, depth_after: int) -> list[TextContent]:
    """Progressive Disclosure Layer 2: 取得時間上下文"""
    try:
        retriever = HybridRetriever()
        timeline = await retriever.lancedb.get_timeline(anchor_id, depth_before, depth_after)
        
        if "error" in timeline:
            return [TextContent(type="text", text=f"❌ {timeline['error']}")]
        
        anchor = timeline["anchor"]
        before = timeline["before"]
        after = timeline["after"]
        
        def _format_ts(ts: str) -> str:
            """安全格式化 timestamp 為 MM/DD HH:MM"""
            if len(ts) >= 16:
                return f"{ts[5:7]}/{ts[8:10]} {ts[11:16]}"
            return ts
        
        lines = [
            "## 小晴記憶時間線（Progressive Disclosure Layer 2）",
            "",
            f"**中心**：{anchor['id'][:8]} | {_format_ts(anchor['timestamp'])} | {_get_icon_for_type(anchor.get('intent_type', 'fact'))} {anchor['title'][:50]}",
            ""
        ]
        
        if before:
            lines.append("**之前**：")
            for entry in reversed(before):
                lines.append(f"  {_format_ts(entry['timestamp'])} | {_get_icon_for_type(entry.get('intent_type', 'fact'))} {entry['title'][:50]}")
            lines.append("")
        
        if after:
            lines.append("**之後**：")
            for entry in after:
                lines.append(f"  {_format_ts(entry['timestamp'])} | {_get_icon_for_type(entry.get('intent_type', 'fact'))} {entry['title'][:50]}")
            lines.append("")
        
        lines.append("*使用 `memory_search` 並指定 `ids` 參數取得感興趣的完整內容*")
        
        return [TextContent(type="text", text="\n".join(lines))]
    except Exception as e:
        return [TextContent(type="text", text=f"❌ 取得時間線失敗: {str(e)}")]


def _estimate_tokens(text: str) -> int:
    """Token 估計：中/日/韓 1.5，其他 1.0"""
    cjk_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3040' <= c <= '\u30ff' or '\uac00' <= c <= '\ud7af')
    other_chars = len(text) - cjk_chars
    return int(cjk_chars * 1.5 + other_chars * 1.0)


def _get_icon_for_type(intent_type: str) -> str:
    """對應 Icon 類型"""
    try:
        from brain.models.memory_unit import IntentType
        return IntentType(intent_type).icon
    except (ValueError, ImportError):
        return "🔵"


async def _memory_search(query: str, ids: list, top_k: int, start_date: str = "", end_date: str = "") -> list[TextContent]:
    """Layer 3: 根據指定 IDs 回傳完整內容，或執行語意搜尋"""
    retriever = HybridRetriever()
    
    if ids:
        memories = await retriever.lancedb.get_by_ids(ids)
        output = []
        for m in memories:
            time_distance = m.get_time_distance()
            icon = _get_icon_for_type(m.intent_type.value if hasattr(m.intent_type, 'value') else m.intent_type)
            tokens = _estimate_tokens(m.lossless_text)
            output.append(TextContent(
                type="text",
                text=f"{icon} **[{m.topic}]**\n{m.lossless_text}\n\n💡 時間: {time_distance} | ~{tokens} tokens\n關鍵詞: {', '.join(m.keywords)}"
            ))
        return output if output else [TextContent(type="text", text="找不到指定的記憶")]
    
    results = []
    
    if start_date or end_date:
        date_results = await retriever.lancedb.get_by_date_range(start_date or end_date, end_date)
        if query and query.strip():
            intent_retriever = IntentRetriever(retriever)
            semantic_results = await intent_retriever.search(query, top_k * 2)
            semantic_ids = {m.id for m in semantic_results.get("results", [])}
            date_ids = {m.id for m in date_results}
            intersection = semantic_ids & date_ids
            results = [m for m in semantic_results.get("results", []) if m.id in intersection][:top_k]
            if not results:
                results = [m for m in date_results if m.id in semantic_ids][:top_k]
        else:
            results = date_results[:top_k]
    else:
        intent_retriever = IntentRetriever(retriever)
        results = (await intent_retriever.search(query, top_k)).get("results", [])
    
    output = []
    for m in results:
        time_distance = m.get_time_distance()
        icon = _get_icon_for_type(m.intent_type.value if hasattr(m.intent_type, 'value') else m.intent_type)
        tokens = _estimate_tokens(m.lossless_text)
        output.append(TextContent(
            type="text",
            text=f"{icon} **[{m.topic}]**\n{m.lossless_text}\n\n💡 時間: {time_distance} | ~{tokens} tokens\n關鍵詞: {', '.join(m.keywords)}"
        ))
    
    return output if output else [TextContent(type="text", text="找不到相關記憶")]


async def _memory_add(session_id: str, content: str) -> list[TextContent]:
    compression = CompressionStage(model="MiniMax-M2.7")
    retriever = HybridRetriever()
    
    clean_content, is_private, private_hash = MemoryUnit.parse_private_tags(content)
    
    memories = await compression.process(clean_content)
    
    for m in memories:
        m.session_id = session_id
        if is_private:
            m.is_private = True
            m.private_hash = private_hash
        await retriever.add_memory(m)
    
    private_note = "（含私人資料已脫敏）" if is_private else ""
    return [TextContent(type="text", text=f"已儲存 {len(memories)} 個記憶單元 {private_note}")]


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
