import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional

from .events import SessionStartEvent, UserMessageEvent, ToolUseEvent, StopEvent, SessionEndEvent
from .base import MemoryHook


class OpenCodeHook(MemoryHook):
    """直接使用 brain pipeline 的記憶提取 hook。

    不需要 HTTP round-trip，直接調用 CompressionStage + HybridRetriever
    進行內容提取與儲存。
    """

    _MEANINGFUL_TOOLS = {
        "edit", "write", "bash", "task", "skill",
    }

    def __init__(self, model: str = "MiniMax-M2.7"):
        self._session_id: Optional[str] = None
        self._model = model
        self._compression = None
        self._retriever = None

    @property
    def name(self) -> str:
        return "OpenCodeHook"

    def _get_compression(self):
        if self._compression is None:
            from ..stages.compression import CompressionStage
            self._compression = CompressionStage(model=self._model)
        return self._compression

    def _get_retriever(self):
        if self._retriever is None:
            from ..retrieval.hybrid import HybridRetriever
            self._retriever = HybridRetriever()
        return self._retriever

    async def on_session_start(self, event: SessionStartEvent) -> None:
        # TODO: 注入相關歷史記憶到 context
        self._session_id = event.session_id
        print(f"[OpenCodeHook] Session started: {event.session_id}", flush=True, file=sys.stderr)

    async def on_user_message(self, event: UserMessageEvent) -> None:
        msg = event.message.strip()
        if not msg:
            return

        try:
            compression = self._get_compression()
            retriever = self._get_retriever()

            # 先用 BM25 找出現有最相關的 5 筆有效記憶，供 LLM 比對是否需要翻新（supersede）
            existing_text = "無"
            try:
                active = retriever.sqlite.get_active_memories(limit=300)
                if active:
                    retriever.bm25.index(active)
                    related = retriever.bm25_search(msg, top_k=5)
                    if related:
                        existing_text = "\n".join(
                            f"- [ID:{m.id[:8]}] [{m.topic}] {m.lossless_text}" for m in related
                        )
            except Exception as ex:
                print(f"[OpenCodeHook] BM25 pre-check warning: {ex}", flush=True, file=sys.stderr)

            memories = await compression.process(msg, existing_memories_text=existing_text)
            superseded_count = 0
            for m in memories:
                m.session_id = event.session_id
                await retriever.add_memory(m)
                if m.provenance and m.provenance.startswith("supersedes:"):
                    old_id = m.provenance.split("supersedes:", 1)[1].strip()
                    if old_id:
                        retriever.sqlite.supersede(old_id, m.id)
                        retriever.lancedb.supersede(old_id, m.id)
                        superseded_count += 1

            print(
                f"[OpenCodeHook] Extracted {len(memories)} memories from user message (superseded: {superseded_count})",
                flush=True,
                file=sys.stderr,
            )
        except Exception as e:
            print(f"[OpenCodeHook] Error processing user message: {e}", flush=True, file=sys.stderr)

    async def on_tool_use(self, event: ToolUseEvent) -> None:
        """記錄工具操作。

        刻意「不」呼叫 LLM：一次對話動輒 5-10 次工具呼叫，
        每個都跑一次 compression 抽取會把額度與時間燒光。
        這裡直接寫入結構化記憶，語意整理交給 on_stop 的 synthesis。
        """
        if not event.tool_name:
            return

        tool_lower = event.tool_name.lower()

        if tool_lower not in self._MEANINGFUL_TOOLS:
            return

        try:
            from ..models.memory_unit import IntentType, MemoryUnit

            retriever = self._get_retriever()

            args = event.args if isinstance(event.args, dict) else {}
            arg_text = json.dumps(args, ensure_ascii=False)[:300]
            result_text = (event.result or "")[:300]

            unit = MemoryUnit(
                lossless_text=(
                    f"Agent 使用工具 [{event.tool_name}]，"
                    f"參數: {arg_text}，結果: {result_text}"
                ),
                keywords=[event.tool_name, "工具操作"],
                topic="event",
                intent_type=IntentType.FACT,
                session_id=event.session_id,
            )
            await retriever.add_memory(unit)

            print(f"[OpenCodeHook] Recorded tool use: {event.tool_name}", flush=True, file=sys.stderr)
        except Exception as e:
            print(f"[OpenCodeHook] Error recording tool use: {e}", flush=True, file=sys.stderr)

    async def on_stop(self, event: StopEvent) -> None:
        """生成 session 摘要日記（預設**停用**，見下方說明）。

        ⚠️ 2026-11-15 停用原因（主人反映 API 額度燒太凶）：
        這裡原本每一回合（每次 session.idle）都會把 `get_by_session(sid)` 回傳的
        **整個 session 全部記憶**丟給 LLM 做 synthesis。常駐單一窗口的 session 永遠不關，
        所以第 N 回合要送 N 筆記憶 —— 實測主人窗口累積到 77 筆時，
        每一回合就是一次約 7k token 的 LLM 呼叫，而產出是 **0 筆 diary**
        （資料庫裡 topic='diary' 一筆都沒有）。純粹是配額黑洞。

        日記改由兩個真正有效的途徑產生：
          1. 夜間沉澱 `scripts/nightly_reflection.py`（每天一次）
          2. 小晴主動 `memory_add` 寫「今日回顧」

        要恢復舊行為：設環境變數 `XIAOQING_ENABLE_STOP_SYNTHESIS=1`，
        且建議同時設 `XIAOQING_STOP_SYNTHESIS_MAX`（預設 12）限制單次筆數。
        """
        if os.environ.get("XIAOQING_ENABLE_STOP_SYNTHESIS") != "1":
            return

        sid = event.session_id
        if not sid:
            return

        try:
            from ..stages.synthesis import SynthesisStage
            from ..storage.sqlite import SQLiteStorage

            try:
                limit = int(os.environ.get("XIAOQING_STOP_SYNTHESIS_MAX", "12"))
            except ValueError:
                limit = 12

            sqlite = SQLiteStorage()
            memories = sqlite.get_by_session(sid)

            if len(memories) < 2:
                print(f"[OpenCodeHook] Session {sid[:8]} has {len(memories)} memories, skip summary", flush=True, file=sys.stderr)
                return

            # 只摘要最近的 limit 筆，避免常駐窗口無限成長把配額燒光
            memories = memories[-limit:]

            synthesis = SynthesisStage(model=self._model)
            synthesized = await synthesis.process(memories)

            retriever = self._get_retriever()
            for m in synthesized:
                m.session_id = sid
                m.topic = "diary"
                await retriever.add_memory(m)

            print(f"[OpenCodeHook] Session {sid[:8]} summary: {len(memories)} memories → {len(synthesized)} diary entries", flush=True, file=sys.stderr)
        except Exception as e:
            print(f"[OpenCodeHook] Error generating session summary: {e}", flush=True, file=sys.stderr)

    async def on_session_end(self, event: SessionEndEvent) -> None:
        # 背景整併排程已於 2026-11-09 移除，session 摘要改由 on_session_summary 主動產生
        sid = self._session_id
        self._session_id = None
        print(f"[OpenCodeHook] Session ended: {sid}", flush=True, file=sys.stderr)

    @staticmethod
    def _summarize_args(args: dict) -> str:
        """將 tool args 摘要為一行"""
        if not args:
            return "無"
        parts = []
        for k, v in args.items():
            if k == "command":
                parts.append(f"{k}='{str(v)[:80]}'")
            elif isinstance(v, str):
                parts.append(f"{k}='{v[:40]}'")
            elif isinstance(v, (int, float, bool)):
                parts.append(f"{k}={v}")
            else:
                parts.append(f"{k}=({type(v).__name__})")
        return ", ".join(parts[:5])
