"""Tests for brain hook system (Phase 4.2)"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from brain.hooks.base import HookRegistry, MemoryHook, _camel_to_snake
from brain.hooks.events import (
    SessionStartEvent, UserMessageEvent, ToolUseEvent,
    StopEvent, SessionEndEvent,
)


class TestCamelToSnake:
    def test_session_start(self):
        assert _camel_to_snake("SessionStartEvent") == "on_session_start"

    def test_user_message(self):
        assert _camel_to_snake("UserMessageEvent") == "on_user_message"

    def test_tool_use(self):
        assert _camel_to_snake("ToolUseEvent") == "on_tool_use"

    def test_stop(self):
        assert _camel_to_snake("StopEvent") == "on_stop"

    def test_session_end(self):
        assert _camel_to_snake("SessionEndEvent") == "on_session_end"

    def test_simple_word(self):
        assert _camel_to_snake("Foo") == "on_foo"


class TestHookDispatch:

    @pytest.mark.asyncio
    async def test_dispatch_session_start(self):
        registry = HookRegistry()

        hook = AsyncMock()
        hook.name = "MockHook"
        hook.on_session_start = AsyncMock()

        registry._hooks = [hook]

        event = SessionStartEvent(
            event_type="session_start",
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id="test-session-1",
            agent_name="build",
        )

        await registry.dispatch(event)

        hook.on_session_start.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_dispatch_user_message(self):
        registry = HookRegistry()

        hook = AsyncMock()
        hook.name = "MockHook"
        hook.on_user_message = AsyncMock()

        registry._hooks = [hook]

        event = UserMessageEvent(
            event_type="user_message",
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id="test-session-2",
            message="幫我寫一個測試",
        )

        await registry.dispatch(event)

        hook.on_user_message.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_dispatch_tool_use(self):
        registry = HookRegistry()

        hook = AsyncMock()
        hook.name = "MockHook"
        hook.on_tool_use = AsyncMock()

        registry._hooks = [hook]

        event = ToolUseEvent(
            event_type="tool_use",
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id="test-session-3",
            tool_name="bash",
            args={"command": "ls", "hasSideEffect": False},
            result="file1.py\nfile2.py",
        )

        await registry.dispatch(event)

        hook.on_tool_use.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_dispatch_multiple_hooks(self):
        registry = HookRegistry()

        hook1 = AsyncMock()
        hook1.name = "Hook1"
        hook1.on_session_start = AsyncMock()

        hook2 = AsyncMock()
        hook2.name = "Hook2"
        hook2.on_session_start = AsyncMock()

        registry._hooks = [hook1, hook2]

        event = SessionStartEvent(
            event_type="session_start",
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id="test-multi",
        )

        await registry.dispatch(event)

        hook1.on_session_start.assert_called_once_with(event)
        hook2.on_session_start.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_dispatch_skips_unknown_handler(self):
        registry = HookRegistry()

        hook = AsyncMock()
        hook.name = "MockHook"
        hook.on_session_start = AsyncMock()
        # No on_user_message on this hook

        registry._hooks = [hook]

        event = UserMessageEvent(
            event_type="user_message",
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id="test-skip",
            message="hello",
        )

        await registry.dispatch(event)

        hook.on_session_start.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_error_does_not_crash(self):
        registry = HookRegistry()

        hook = AsyncMock()
        hook.name = "FailingHook"
        hook.on_session_start = AsyncMock(
            side_effect=RuntimeError("simulated error")
        )

        registry._hooks = [hook]

        event = SessionStartEvent(
            event_type="session_start",
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id="test-error",
        )

        await registry.dispatch(event)


class TestLifecycleEventTool:

    @patch("brain.mcp_server._hook_registry")
    def test_valid_session_start_event(self, mock_registry):
        from brain.mcp_server import _lifecycle_event

        mock_registry.dispatch = AsyncMock()

        args = {
            "event_type": "session_start",
            "session_id": "ses_abc123",
            "agent_name": "build",
        }

        result = asyncio.run(_lifecycle_event(args))
        text = result[0].text

        assert "session_start" in text
        mock_registry.dispatch.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
