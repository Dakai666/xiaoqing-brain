from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any


@dataclass
class HookEvent:
    """Base class for all hook events"""
    event_type: str
    timestamp: str
    session_id: str


@dataclass
class SessionStartEvent(HookEvent):
    """新 session 開始"""
    agent_name: Optional[str] = None


@dataclass
class UserMessageEvent(HookEvent):
    """用戶輸入訊息"""
    message: str
    message_type: str = "text"


@dataclass
class ToolUseEvent(HookEvent):
    """Tool 被使用"""
    tool_name: str
    args: dict
    result: str
    duration_ms: Optional[float] = None


@dataclass
class StopEvent(HookEvent):
    """Session 結束（stopped）"""
    reason: Optional[str] = None


@dataclass
class SessionEndEvent(HookEvent):
    """Session 終止"""
    summary: Optional[str] = None


@dataclass
class ErrorEvent(HookEvent):
    """Hook 執行錯誤"""
    error: str
    hook_name: str
