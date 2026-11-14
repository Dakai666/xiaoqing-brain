#!/usr/bin/env python3
"""小晴晨間簡報資料收集器 — 給 08:00 cron 排程使用。

輸出昨晚到今天的重點記憶、今日日記摘錄與系統狀態，
讓小晴在晨間簡報排程中轉成 3-6 句親切的問候。

用法：
    python C:/Users/User/xiaoqing/brain/scripts/morning_brief.py
"""

import io
import os
import shutil
import sqlite3
import sys
import urllib.request
from datetime import datetime, timedelta

BRAIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BRAIN_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "memories.db")
DIARY_ROOT = "C:/Users/User/opencode/diary"

LINES = []


def add(line: str) -> None:
    LINES.append(line)


def recent_memories() -> None:
    """最近 3 天內的記憶，依時間倒序，取前 12 筆。"""
    if not os.path.isfile(DB_PATH):
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        cutoff = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        rows = conn.execute(
            "SELECT date, topic, substr(lossless_text, 1, 120) FROM memories "
            "WHERE is_superseded = 0 AND date >= ? ORDER BY created_at DESC LIMIT 12",
            (cutoff,),
        ).fetchall()
        conn.close()
        if rows:
            add("--- RECENT MEMORY (newest first) ---")
            for date, topic, text in rows:
                add(f"[{date}] ({topic}) {text}")
    except Exception:
        pass


def today_diary() -> None:
    """今日日記檔（若存在）。"""
    now = datetime.now()
    path = os.path.join(DIARY_ROOT, now.strftime("%Y-%m"), now.strftime("%Y-%m-%d") + ".md")
    if not os.path.isfile(path):
        return
    try:
        with io.open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        add("")
        add("--- TODAY DIARY (first 1200 chars) ---")
        add(text[:1200])
    except Exception:
        pass


def system_status() -> None:
    add("")
    add("--- SYSTEM ---")
    try:
        usage = shutil.disk_usage("C:\\")
        add(f"Disk C free: {usage.free / (1024**3):.1f} GB")
    except Exception:
        pass
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=4) as resp:
            resp.read(1)
        add("Ollama embedding backend: running")
    except Exception:
        add("Ollama embedding backend: OFFLINE (search degraded to BM25 only)")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    recent_memories()
    today_diary()
    system_status()

    print("\n".join(LINES) if LINES else "NO-DATA")
    return 0


if __name__ == "__main__":
    sys.exit(main())
