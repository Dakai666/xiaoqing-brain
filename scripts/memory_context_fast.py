#!/usr/bin/env python3
"""快速記憶檢索腳本（供 OpenCode 2.x Server Plugin `context` hook 呼叫）。

設計目標：
- 極速（< 100ms）：直接查詢 SQLite 有效記憶 + Jieba BM25，不呼叫 LLM intent 分析、不阻塞模型請求。
- 同時回傳：
  1. `recalled`: 與當前使用者訊息最相關的 Top-K 記憶（含 ID 前 8 碼、主題、時間距離、內容）
  2. `core`: 最新的核心偏好/決定/專案狀態（最多 5 筆）
  3. `stats`: 記憶庫總筆數與今日新增筆數
"""

import json
import os
import sys
from datetime import datetime

BRAIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BRAIN_DIR)
os.chdir(BRAIN_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _clip(text: str, limit: int = 220) -> str:
    """注入用的截斷：常駐窗口每一輪都會重送這段，所以寧可短。

    需要完整內容時再呼叫 `memory_get_context` / `memory_search`。
    """
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def main() -> int:
    query = ""
    top_k = 3
    if len(sys.argv) > 1:
        query = sys.argv[1].strip()
    if len(sys.argv) > 2:
        try:
            top_k = int(sys.argv[2])
        except ValueError:
            top_k = 3

    try:
        from brain.storage.sqlite import SQLiteStorage
        from brain.retrieval.bm25 import BM25Retriever

        sqlite = SQLiteStorage()
        active_memories = sqlite.get_active_memories(limit=500)
        today_memories = sqlite.get_today_memories()

        recalled = []
        seen_ids = set()

        if query and active_memories:
            bm25 = BM25Retriever()
            bm25.index(active_memories)
            scored = bm25.search(query, top_k=top_k)
            for m, score in scored:
                if m.id not in seen_ids:
                    seen_ids.add(m.id)
                    recalled.append({
                        "id": m.id[:8],
                        "full_id": m.id,
                        "topic": m.topic,
                        "intent": m.intent_type.value if hasattr(m.intent_type, "value") else str(m.intent_type),
                        "text": _clip(m.lossless_text),
                        "time_ago": m.get_time_distance(),
                        "date": m.date,
                        "keywords": m.keywords[:4],
                        "score": round(float(score), 2),
                    })

        # 取最新的 preference / decision / project 作為常駐核心認知（排除已在 recalled 的）
        core_topics = {"preference", "decision", "project", "personal"}
        core = []
        for m in active_memories:
            if m.id in seen_ids:
                continue
            if m.topic in core_topics:
                core.append({
                    "id": m.id[:8],
                    "topic": m.topic,
                    "text": _clip(m.lossless_text, 180),
                    "time_ago": m.get_time_distance(),
                })
                if len(core) >= 3:
                    break

        out = {
            "ok": True,
            "stats": {
                "active_total": len(active_memories),
                "today_count": len(today_memories),
            },
            "recalled": recalled,
            "core": core,
        }
        sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
        return 0
    except Exception as e:
        err = {"ok": False, "error": f"{type(e).__name__}: {e}", "recalled": [], "core": []}
        sys.stdout.buffer.write(json.dumps(err, ensure_ascii=False).encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
