#!/usr/bin/env python3
"""小晴智慧巡檢 (Smart Pulse) — 零 Token 條件閘腳本。

搭配 OpenCode 原生排程器的 `if` 條件閘（changes: true）使用：
每 30 分鐘執行一次，輸出一份精簡狀態報告。
若輸出與上次完全相同，排程器判定為「無變化」→ 不喚醒 Session → 消耗 0 Token。

用法：
    python C:/Users/User/xiaoqing/brain/scripts/pulse_check.py
"""

import io
import os
import shutil
import sqlite3
import sys
import urllib.request

BRAIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BRAIN_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "memories.db")

REPORT = []


def add(line: str) -> None:
    REPORT.append(line)


def check_new_memories() -> None:
    """最近 35 分鐘內有沒有新的「決定 / 偏好 / 專案」類記憶值得主動提出。

    只看需要主人留意的類型（decision / preference / project / routine），
    純事實與工具操作不列入，避免每半小時就為了瑣事打擾主人。
    """
    if not os.path.isfile(DB_PATH):
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT topic, substr(lossless_text, 1, 90) FROM memories "
            "WHERE created_at >= datetime('now', '-35 minutes') "
            "AND is_superseded = 0 AND topic IN ('decision','preference','project','routine') "
            "ORDER BY created_at DESC LIMIT 5"
        ).fetchall()
        conn.close()
        if rows:
            add(f"NOTE: {len(rows)} notable new decision/preference/project memories in the last 35 minutes")
            for (topic, text) in rows[:3]:
                add(f"  - ({topic}) {text}")
    except Exception:
        pass


def check_vector_drift() -> None:
    """向量庫與 SQLite 是否不同步（embedding 失敗時會降級只寫 SQLite）。"""
    try:
        from brain.storage.sqlite import SQLiteStorage
        from brain.storage.lancedb import LanceDBStorage

        sqlite = SQLiteStorage()
        lancedb = LanceDBStorage()
        sqlite_ids = {m.id for m in sqlite.get_all_memories(limit=100000)}
        lancedb_ids = {
            r["id"]
            for r in lancedb.db["memories"]
            .search(None, vector_column_name="vector")
            .limit(100000)
            .to_list()
        }
        missing = len(sqlite_ids - lancedb_ids)
        if missing > 0:
            add(f"SYNC: vector store is missing {missing} memories (embedding degraded). Run scripts/resync_lancedb.py")
    except Exception:
        pass


def check_ollama() -> None:
    """Ollama 是否存活（記憶向量化後端）。"""
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=4) as resp:
            resp.read(1)
    except Exception:
        add("OLLAMA: NOT RUNNING. Memory embedding is degraded to BM25-only search. Recommend starting Ollama.")


def check_disk() -> None:
    """C 磁碟剩餘空間。"""
    try:
        usage = shutil.disk_usage("C:\\")
        free_gb = usage.free / (1024**3)
        if free_gb < 20:
            add(f"DISK: C drive free space is only {free_gb:.1f} GB (below the 20 GB threshold)")
    except Exception:
        pass


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    check_new_memories()
    check_vector_drift()
    check_ollama()
    check_disk()

    if not REPORT:
        print("OK-QUIET")
    else:
        print("\n".join(REPORT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
