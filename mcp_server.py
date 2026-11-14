#!/usr/bin/env python3
import sys
import os

BRAIN_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BRAIN_DIR)
BRAIN_DATA_DIR = os.environ.get(
    "XIAOQING_DATA_DIR",
    os.path.join(BRAIN_DIR, "data"),
)
os.environ["XIAOQING_DATA_DIR"] = BRAIN_DATA_DIR
os.chdir(BRAIN_DIR)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

ENV_FILE = os.environ.get("XIAOQING_ENV_FILE", os.path.join(PROJECT_ROOT, ".env"))


def _load_env() -> None:
    """載入 .env（不覆蓋既有環境變數）。

    必須在讀取 XIAOQING_LLM_MODEL 等變數「之前」呼叫，否則 .env 的設定會
    被預設值蓋掉，造成模型名跟實際 backend 不一致。
    """
    if not os.path.isfile(ENV_FILE):
        return
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_env()

LLM_MODEL = os.environ.get("XIAOQING_LLM_MODEL", "") or ""
EMBED_MODEL = os.environ.get("XIAOQING_EMBED_MODEL", "")
HEALTH_FILE = os.path.join(BRAIN_DATA_DIR, "brain_mcp_status.json")

os.makedirs(BRAIN_DATA_DIR, exist_ok=True)

import asyncio
from datetime import datetime, timezone
from mcp.server import Server
from mcp.types import Tool, TextContent, Prompt
from mcp.server.stdio import stdio_server

from brain.models.memory_unit import MemoryUnit
from brain.stages.compression import CompressionStage
from brain.storage.sqlite import SQLiteStorage
from brain.storage.lancedb import LanceDBStorage
from brain.retrieval.hybrid import HybridRetriever
from brain.retrieval.intent import IntentRetriever
from brain.utils.llm_backend import MiniMaxBackend, OllamaBackend, set_llm_backend
from brain.accounting import AccountingService
from brain.hooks.base import HookRegistry
from brain.hooks.opencode_adapter import OpenCodeHook
from brain.hooks.ingest import IngestError, dispatch_events


server = Server("xiaoqing-memory")
_accounting_service = None
_hook_registry: HookRegistry = None


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
            name="memory_refresh",
            description="翻新（Supersede）一筆舊記憶：當主人的偏好、專案狀態、模型設定或決策發生改變時，將舊記憶標記為已過時（is_superseded=1），並寫入最新版本的記憶，確保檢索不會讀到過期資訊。",
            inputSchema={
                "type": "object",
                "properties": {
                    "old_memory_id": {"type": "string", "description": "要被取代的舊記憶 ID（完整 ID 或前 8 碼皆可）"},
                    "new_content": {"type": "string", "description": "翻新後的完整最新記憶內容"},
                    "topic": {"type": "string", "description": "主題分類（如 preference, decision, technical, project, personal, routine）", "default": "preference"},
                    "keywords": {"type": "array", "items": {"type": "string"}, "description": "關鍵詞列表"}
                },
                "required": ["old_memory_id", "new_content"]
            }
        ),
        Tool(
            name="memory_delete",
            description="刪除一筆錯誤或不再需要的記憶（完整 ID 或前 8 碼皆可）",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string", "description": "要刪除的記憶 ID"}
                },
                "required": ["memory_id"]
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
        Tool(
            name="lifecycle_event",
            description="觸發記憶生命週期事件（被動記憶捕捉）。當 session 狀態改變時呼叫此 tool 來記錄。",
            inputSchema={
                "type": "object",
                "properties": {
                    "event_type": {
                        "type": "string",
                        "description": "事件類型",
                        "enum": ["session_start", "user_message", "tool_use", "stop", "session_end"]
                    },
                    "session_id": {"type": "string", "description": "Session ID"},
                    "agent_name": {"type": "string", "description": "Agent 名稱（session_start 時使用）"},
                    "message": {"type": "string", "description": "用戶訊息內容（user_message 時使用）"},
                    "tool_name": {"type": "string", "description": "Tool 名稱（tool_use 時使用）"},
                    "tool_args": {"type": "object", "description": "Tool 參數（tool_use 時使用）"},
                    "tool_result": {"type": "string", "description": "Tool 結果（tool_use 時使用）"},
                    "reason": {"type": "string", "description": "結束原因（stop 時使用）"},
                    "summary": {"type": "string", "description": "Session 摘要（session_end 時使用）"},
                },
                "required": ["event_type", "session_id"]
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
    elif name == "memory_refresh":
        return await _memory_refresh(
            arguments["old_memory_id"],
            arguments["new_content"],
            arguments.get("topic", "preference"),
            arguments.get("keywords", []),
        )
    elif name == "memory_delete":
        return await _memory_delete(arguments["memory_id"])
    elif name == "accounting_add":
        return await _accounting_add(arguments["text"], arguments["session_id"])
    elif name == "accounting_summary":
        return await _accounting_summary(arguments.get("days", 30))
    elif name == "accounting_today":
        return await _accounting_today()
    elif name == "accounting_all":
        return await _accounting_all()
    elif name == "lifecycle_event":
        return await _lifecycle_event(arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")


async def _memory_health() -> list[TextContent]:
    try:
        sqlite = SQLiteStorage()
        lancedb = LanceDBStorage()

        # 只比對「有效記憶」（未被取代）；被 superseded 的舊記憶留在兩邊是設計如此。
        sqlite_active = len(sqlite.get_active_memories(limit=100000))
        lancedb_rows = (
            lancedb.db["memories"].search(None).limit(100000).to_list()
        )
        lancedb_active = len([r for r in lancedb_rows if not r.get("is_superseded", False)])
        lancedb_superseded = len(lancedb_rows) - lancedb_active
        sqlite_superseded = len(sqlite.search('', 10000)) - sqlite_active
        today_memories = sqlite.get_today_memories()

        if sqlite_active == lancedb_active:
            sync_status = "✅ 已同步"
        else:
            diff = lancedb_active - sqlite_active
            sync_status = (
                f"⚠️ 向量庫差 {abs(diff)} 筆（缺 {max(diff, 0)} / 多 {max(-diff, 0)}），"
                "可執行 scripts/resync_lancedb.py 修復"
            )

        status_parts = [
            "✅ 記憶系統正常運作",
            f"SQLite 有效記憶: {sqlite_active} 筆（另有 {sqlite_superseded} 筆已被取代）",
            f"LanceDB 有效記憶: {lancedb_active} 筆（另有 {lancedb_superseded} 筆已被取代）({sync_status})",
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
    compression = CompressionStage(model=LLM_MODEL)
    retriever = HybridRetriever()
    
    clean_content, is_private, private_hash = MemoryUnit.parse_private_tags(content)
    
    existing_text = "無"
    try:
        active = retriever.sqlite.get_active_memories(limit=300)
        if active:
            retriever.bm25.index(active)
            related = retriever.bm25_search(clean_content, top_k=5)
            if related:
                existing_text = "\n".join(
                    f"- [ID:{m.id[:8]}] [{m.topic}] {m.lossless_text}" for m in related
                )
    except Exception:
        pass

    memories = await compression.process(clean_content, existing_memories_text=existing_text)
    
    superseded_ids = []
    for m in memories:
        m.session_id = session_id
        if is_private:
            m.is_private = True
            m.private_hash = private_hash
        await retriever.add_memory(m)
        if m.provenance and m.provenance.startswith("supersedes:"):
            old_id = m.provenance.split("supersedes:", 1)[1].strip()
            if old_id:
                retriever.sqlite.supersede(old_id, m.id)
                retriever.lancedb.supersede(old_id, m.id)
                superseded_ids.append(old_id)
    
    private_note = "（含私人資料已脫敏）" if is_private else ""
    sup_note = f"（已自動翻新舊記憶: {', '.join(superseded_ids)}）" if superseded_ids else ""
    return [TextContent(type="text", text=f"已儲存 {len(memories)} 個記憶單元 {private_note}{sup_note}")]


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

        lines.append(f"\n{i}. [ID:{m.id[:8]}] [{m.topic}] {m.lossless_text}")
        lines.append(f"   💡 這是{time_distance}的事，信心度 {confidence_pct}%")
        if m.keywords:
            lines.append(f"   關鍵詞: {', '.join(m.keywords[:3])}")

    output.append(TextContent(type="text", text="\n".join(lines)))
    return output


async def _memory_refresh(old_memory_id: str, new_content: str, topic: str = "preference", keywords: list = None) -> list[TextContent]:
    """翻新舊記憶：標記舊記憶為 superseded，並寫入新記憶"""
    try:
        from brain.models.memory_unit import IntentType, DecayRate
        retriever = HybridRetriever()
        clean_content, is_private, private_hash = MemoryUnit.parse_private_tags(new_content)
        
        intent_map = {
            "preference": IntentType.PREFERENCE,
            "routine": IntentType.HABIT,
        }
        decay_map = {
            "preference": DecayRate.SLOW,
            "decision": DecayRate.SLOW,
            "personal": DecayRate.NONE,
            "technical": DecayRate.SLOW,
        }
        unit = MemoryUnit(
            lossless_text=clean_content,
            keywords=keywords if isinstance(keywords, list) and keywords else [topic, "記憶翻新"],
            topic=topic or "preference",
            intent_type=intent_map.get(topic, IntentType.FACT),
            decay_rate=decay_map.get(topic, DecayRate.NORMAL),
            session_id="memory_refresh",
            provenance=f"supersedes:{old_memory_id}",
            is_private=is_private,
            private_hash=private_hash,
        )
        await retriever.add_memory(unit)
        sql_ok = retriever.sqlite.supersede(old_memory_id, unit.id)
        retriever.lancedb.supersede(old_memory_id, unit.id)
        return [TextContent(
            type="text",
            text=f"✨ 記憶已翻新！\n- 舊記憶 `{old_memory_id}` 已標記為過時 (SQLite={sql_ok})\n- 新記憶 `{unit.id[:8]}` 已寫入：[{unit.topic}] {unit.lossless_text}"
        )]
    except Exception as e:
        return [TextContent(type="text", text=f"❌ 記憶翻新失敗: {e}")]


async def _memory_delete(memory_id: str) -> list[TextContent]:
    """刪除指定記憶"""
    try:
        retriever = HybridRetriever()
        sql_ok = retriever.sqlite.delete(memory_id)
        retriever.lancedb.delete(memory_id)
        return [TextContent(type="text", text=f"🗑️ 記憶 `{memory_id}` 已刪除 (SQLite={sql_ok})")]
    except Exception as e:
        return [TextContent(type="text", text=f"❌ 記憶刪除失敗: {e}")]


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


async def _lifecycle_event(arguments: dict) -> list[TextContent]:
    """處理 lifecycle event，分發到已註冊的 hooks"""
    global _hook_registry

    if not _hook_registry:
        return [TextContent(type="text", text="⚠️ Hook registry 尚未初始化")]

    event_type = arguments.get("event_type", "")

    try:
        errors = await dispatch_events(
            _hook_registry,
            [
                {
                    "event_type": event_type,
                    "session_id": arguments.get("session_id", ""),
                    "arguments": arguments,
                }
            ],
        )
    except IngestError as e:
        return [TextContent(type="text", text=f"❌ {e}")]

    if errors:
        error_msgs = "\n".join(
            f"  - [{e.hook_name}] {e.error}" for e in errors
        )
        return [TextContent(
            type="text",
            text=f"⚠️ {event_type} 事件已分發，但 {len(errors)} 個 hook 失敗:\n{error_msgs}"
        )]
    return [TextContent(type="text", text=f"✅ {event_type} 事件已分發")]


def _write_health_status(status: str, error: str = None):
    import json
    from datetime import datetime
    data = {
        "status": status,
        "error": error,
        "last_check": datetime.now().isoformat()
    }
    try:
        with open(HEALTH_FILE, 'w') as f:
            json.dump(data, f)
    except Exception:
        pass


async def main():
    global _hook_registry, LLM_MODEL

    try:
        # .env 已在 module 層載入（見 _load_env），這裡只需挑 backend 並校正模型名。
        from brain.utils.llm_backend import configure_llm_backend

        _backend, LLM_MODEL = configure_llm_backend(os.environ.get("XIAOQING_LLM_MODEL"))

        _hook_registry = HookRegistry()
        _hook_registry.register(OpenCodeHook())
        print(f"[Hook] Registered hooks: {len(_hook_registry._hooks)}", flush=True, file=sys.stderr)

        # 背景整併排程（ConsolidationScheduler）已於 2026-11-09 完整移除。
        # 記憶改由「主動記憶」機制處理：session 結束時由 OpenCodeHook 產生摘要，
        # 開新 session 時以 memory_get_context 注入相關記憶。
        # （2026-11-09 查證：該排程自 2026-09-10 起從未成功產出過任何輸出。）

        _write_health_status("running")
        print(f"MCP Server started successfully (model={LLM_MODEL})", flush=True, file=sys.stderr)

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
