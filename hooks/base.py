import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .events import (
        SessionStartEvent,
        UserMessageEvent,
        ToolUseEvent,
        StopEvent,
        SessionEndEvent,
    )


def _camel_to_snake(name: str) -> str:
    """Convert CamelCase to snake_case: SessionStartEvent -> on_session_start"""
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
    if s2.endswith('_event'):
        s2 = s2[:-6]
    return f"on_{s2}" if not s2.startswith("on_") else s2


class MemoryHook(ABC):
    """Abstract base class for memory hooks"""

    @property
    def name(self) -> str:
        """Hook 名稱"""
        return self.__class__.__name__

    async def on_session_start(self, event: "SessionStartEvent") -> None:
        """新 session 開始，注入相關歷史記憶"""
        pass

    async def on_user_message(self, event: "UserMessageEvent") -> None:
        """用戶輸入，儲存用戶意圖"""
        pass

    async def on_tool_use(self, event: "ToolUseEvent") -> None:
        """Tool 被使用，捕捉學習與決策"""
        pass

    async def on_stop(self, event: "StopEvent") -> None:
        """Session 結束，生成摘要"""
        pass

    async def on_session_end(self, event: "SessionEndEvent") -> None:
        """Session 終止，標記完成"""
        pass


class HookRegistry:
    """鉤子註冊表"""

    def __init__(self):
        self._hooks: list[MemoryHook] = []

    def register(self, hook: MemoryHook) -> None:
        """註冊一個 hook"""
        self._hooks.append(hook)

    def unregister(self, hook: MemoryHook) -> None:
        """取消註冊一個 hook"""
        if hook in self._hooks:
            self._hooks.remove(hook)

    async def dispatch(self, event) -> list:
        """分發事件到所有已註冊的 hooks，回傳錯誤列表"""
        from .events import ErrorEvent

        event_type = type(event).__name__
        handler_name = _camel_to_snake(event_type)
        errors: list[ErrorEvent] = []

        for hook in self._hooks:
            handler = getattr(hook, handler_name, None)
            if handler:
                try:
                    await handler(event)
                except Exception as e:
                    error_event = ErrorEvent(
                        event_type="error",
                        timestamp=event.timestamp,
                        session_id=event.session_id,
                        error=str(e),
                        hook_name=hook.name,
                    )
                    errors.append(error_event)
                    print(f"[Hook Error] {hook.name}: {e}", flush=True)

        return errors
