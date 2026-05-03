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
        "edit", "write", "bash", "glob", "grep", "read",
        "task", "skill", "webfetch",
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
        print(f"[OpenCodeHook] Session started: {event.session_id}", flush=True)

    async def on_user_message(self, event: UserMessageEvent) -> None:
        msg = event.message.strip()
        if not msg:
            return

        try:
            compression = self._get_compression()
            retriever = self._get_retriever()

            memories = await compression.process(msg)
            for m in memories:
                m.session_id = event.session_id
                await retriever.add_memory(m)

            print(f"[OpenCodeHook] Extracted {len(memories)} memories from user message", flush=True)
        except Exception as e:
            print(f"[OpenCodeHook] Error processing user message: {e}", flush=True)

    async def on_tool_use(self, event: ToolUseEvent) -> None:
        if not event.tool_name:
            return

        tool_lower = event.tool_name.lower()

        if not any(tool_lower.startswith(t) for t in self._MEANINGFUL_TOOLS):
            return

        try:
            compression = self._get_compression()
            retriever = self._get_retriever()

            result_str = str(event.result)[:500] if event.result else "(no result)"
            content = (
                f"Agent 使用工具 [{event.tool_name}]，"
                f"參數: {self._summarize_args(event.args)}，"
                f"結果: {result_str}"
            )

            memories = await compression.process(content)
            for m in memories:
                m.session_id = event.session_id
                await retriever.add_memory(m)

            print(f"[OpenCodeHook] Recorded tool use: {event.tool_name}", flush=True)
        except Exception as e:
            print(f"[OpenCodeHook] Error recording tool use: {e}", flush=True)

    async def on_stop(self, event: StopEvent) -> None:
        # TODO: 生成 session 摘要並儲存
        pass

    async def on_session_end(self, event: SessionEndEvent) -> None:
        print(f"[OpenCodeHook] Session ended: {self._session_id}", flush=True)
        self._session_id = None

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
