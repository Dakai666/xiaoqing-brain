"""事件攝取共用邏輯。

把原始事件 dict 轉成 HookEvent，並依序分發到 HookRegistry。
供 MCP tool `lifecycle_event` 與 `scripts/memory_ingest.py` 共用，
確保「agent 手動呼叫」與「OpenCode plugin 自動觸發」兩條路徑行為一致。
"""

from datetime import datetime, timezone
import json
from typing import Optional

from .base import HookRegistry
from .events import (
    ErrorEvent,
    HookEvent,
    SessionEndEvent,
    SessionStartEvent,
    StopEvent,
    ToolUseEvent,
    UserMessageEvent,
)

#: 各事件類型的必填欄位
REQUIRED_FIELDS: dict[str, list[str]] = {
    "session_start": [],
    "user_message": ["message"],
    "tool_use": ["tool_name"],
    "stop": [],
    "session_end": [],
}


class IngestError(ValueError):
    """事件格式錯誤（缺欄位或未知類型）"""


def validate_event(event_type: str, arguments: dict) -> None:
    """檢查事件必填欄位，缺漏時丟出 IngestError。"""
    for field in REQUIRED_FIELDS.get(event_type, []):
        if not arguments.get(field):
            raise IngestError(f"{event_type} 事件缺少必要欄位: {field}")


def _coerce_args(raw) -> dict:
    """tool_args 可能是 dict、JSON 字串或其他，一律整理成 dict。"""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}
        except json.JSONDecodeError:
            return {"value": raw}
    return {}


def build_event(
    event_type: str,
    session_id: str,
    arguments: dict,
    timestamp: Optional[str] = None,
) -> HookEvent:
    """把原始事件 dict 轉成對應的 HookEvent 實例。"""
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    common = {"event_type": event_type, "timestamp": ts, "session_id": session_id}

    if event_type == "session_start":
        return SessionStartEvent(**common, agent_name=arguments.get("agent_name"))
    if event_type == "user_message":
        return UserMessageEvent(**common, message=arguments.get("message", ""))
    if event_type == "tool_use":
        return ToolUseEvent(
            **common,
            tool_name=arguments.get("tool_name", ""),
            args=_coerce_args(arguments.get("tool_args")),
            result=arguments.get("tool_result", "") or "",
        )
    if event_type == "stop":
        return StopEvent(**common, reason=arguments.get("reason"))
    if event_type == "session_end":
        return SessionEndEvent(**common, summary=arguments.get("summary"))
    raise IngestError(f"未知事件類型: {event_type}")


async def dispatch_events(
    registry: Optional[HookRegistry],
    events: list[dict],
) -> list[ErrorEvent]:
    """依序分發事件，回傳累積的錯誤清單。

    每個事件 dict 的格式：
        {"event_type": ..., "session_id": ..., "arguments": {...}}
    """
    if registry is None:
        raise IngestError("Hook registry 尚未初始化")

    errors: list[ErrorEvent] = []
    for raw in events:
        event_type = raw.get("event_type", "")
        session_id = raw.get("session_id", "")
        arguments = raw.get("arguments") or {}
        validate_event(event_type, arguments)
        event = build_event(event_type, session_id, arguments, raw.get("timestamp"))
        errors.extend(await registry.dispatch(event))
    return errors
