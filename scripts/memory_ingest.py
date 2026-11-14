#!/usr/bin/env python3
"""從 stdin 讀取事件 JSON（單一 dict 或陣列），分發到 brain 的記憶 hook。

由 OpenCode plugin `xiaoqing-memory` 自動呼叫，讓每次對話都留下記憶，
不必依賴 agent 自覺呼叫 MCP tool。

用法：
    python scripts/memory_ingest.py <事件檔.json>
    echo '[{"event_type":"user_message",...}]' | python scripts/memory_ingest.py

輸出：stdout 一行 JSON {"ok": bool, "events": int, "errors": [...]}
"""

import asyncio
import json
import os
import sys

BRAIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BRAIN_DIR)
os.chdir(BRAIN_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

ENV_FILE = os.environ.get("XIAOQING_ENV_FILE", os.path.join(PROJECT_ROOT, ".env"))


def load_env() -> None:
    """讀取 .env（不覆蓋既有環境變數），與 mcp_server.py 行為一致。"""
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


async def main() -> int:
    load_env()

    # 優先讀命令列指定的檔案；沒有才走 stdin。
    # 明確用 UTF-8 解碼：Windows 上 sys.stdin 預設是 locale 編碼（cp950），
    # 會用 surrogateescape 解出 lone surrogate，導致後續送出時編碼失敗。
    # utf-8-sig 容忍 BOM（PowerShell 的 Out-File -Encoding UTF8 會加 BOM）。
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        with open(sys.argv[1], "rb") as f:
            raw = f.read().decode("utf-8-sig", errors="replace")
    else:
        raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")

    if not raw.strip():
        print(json.dumps({"ok": False, "events": 0, "errors": ["空輸入"]}, ensure_ascii=False))
        return 1

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"ok": False, "events": 0, "errors": [f"JSON 解析失敗: {e}"]}, ensure_ascii=False))
        return 1

    events = payload if isinstance(payload, list) else [payload]

    from brain.hooks.base import HookRegistry
    from brain.hooks.ingest import IngestError, dispatch_events
    from brain.hooks.opencode_adapter import OpenCodeHook
    from brain.utils.llm_backend import configure_llm_backend

    # backend 與模型名必須一致，否則 MiniMax API 會回 400 "unknown model"。
    _backend, model = configure_llm_backend(os.environ.get("XIAOQING_LLM_MODEL"))

    registry = HookRegistry()
    registry.register(OpenCodeHook(model=model))

    try:
        errors = await dispatch_events(registry, events)
    except IngestError as e:
        print(json.dumps({"ok": False, "events": 0, "errors": [str(e)]}, ensure_ascii=False))
        return 1
    except Exception as e:
        print(json.dumps({"ok": False, "events": 0, "errors": [f"{type(e).__name__}: {e}"]}, ensure_ascii=False))
        return 1

    print(
        json.dumps(
            {
                "ok": not errors,
                "events": len(events),
                "errors": [f"{err.hook_name}: {err.error}" for err in errors],
            },
            ensure_ascii=False,
        )
    )
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
