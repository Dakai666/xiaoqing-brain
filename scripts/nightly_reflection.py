#!/usr/bin/env python3
"""小晴夜間沉澱 (Nightly Reflection) — 給 23:30 cron 排程使用。

在一天結束前，主動完成三件事：
1. 檢查今日是否有尚未寫入記憶庫的對話重點（統計今日記憶筆數）
2. 檢查向量庫與 SQLite 是否同步（embedding 失敗會讓檢索降級）
3. 把今天的重點濃縮成一段日記摘要，寫入 `nightly_report.txt` 供小晴固化到記憶庫

⚠️ stdout 只輸出 ASCII（供排程器比對變化），完整中文報告寫入 UTF-8 報告檔。

用法：
    C:/Users/User/xiaoqing/brain/scripts/nightly_reflection.cmd
"""

import io
import os
import shutil
import sqlite3
import sys
import urllib.request
from datetime import datetime

BRAIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BRAIN_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "memories.db")
REPORT_PATH = "C:/Users/User/opencode/data/nightly_report.txt"

REPORT = []
FLAGS = []


def add(line: str) -> None:
    REPORT.append(line)


def today_stats() -> None:
    """今日記憶筆數與重點。"""
    if not os.path.isfile(DB_PATH):
        add("記憶庫尚未建立，無法統計今日內容。")
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        today = datetime.now().strftime("%Y-%m-%d")
        total = conn.execute(
            "SELECT COUNT(*) FROM memories WHERE date = ? AND is_superseded = 0", (today,)
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT topic, substr(lossless_text, 1, 120) FROM memories "
            "WHERE date = ? AND is_superseded = 0 ORDER BY created_at DESC LIMIT 8",
            (today,),
        ).fetchall()
        conn.close()

        add(f"今日有效記憶：{total} 筆")
        if rows:
            add("今日重點：")
            for topic, text in rows:
                add(f"  - ({topic}) {text}")
        if total == 0:
            FLAGS.append("NO-MEMORY-TODAY")
    except Exception as e:
        add(f"統計今日記憶時發生錯誤：{e}")


def check_vector_drift() -> None:
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
            add(
                f"向量庫與 SQLite 不同步：少了 {missing} 筆向量"
                "（embedding 當時失敗，檢索降級為純 BM25）。"
                "修復：python scripts/resync_lancedb.py"
            )
            FLAGS.append("VECTOR-DRIFT")
    except Exception:
        pass


def check_ollama() -> None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=4) as resp:
            resp.read(1)
        add("Ollama embedding 後端：正常運作")
    except Exception:
        add("Ollama embedding 後端：未啟動（檢索降級為純 BM25）")
        FLAGS.append("OLLAMA-OFFLINE")


def check_disk() -> None:
    try:
        usage = shutil.disk_usage("C:\\")
        free_gb = usage.free / (1024**3)
        add(f"C 磁碟剩餘空間：{free_gb:.1f} GB")
        if free_gb < 20:
            FLAGS.append("LOW-DISK")
    except Exception:
        pass


def main() -> int:
    today_stats()
    check_vector_drift()
    check_ollama()
    check_disk()

    try:
        os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
        with io.open(REPORT_PATH, "w", encoding="utf-8") as fh:
            fh.write("\n".join(REPORT))
    except Exception:
        pass

    print("NIGHTLY: " + (",".join(sorted(set(FLAGS))) if FLAGS else "CLEAN"))
    print("REPORT: " + REPORT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
