#!/usr/bin/env python3
"""小晴智慧巡檢 (Smart Pulse) — 零 Token 條件閘腳本。

搭配 OpenCode 原生排程器的 `if` 條件閘（changes: true）使用：
每 30 分鐘執行一次，輸出精簡狀態報告。
若輸出與上次完全相同，排程器判定為「無變化」→ 不喚醒 Session → 消耗 0 Token。

⚠️ 輸出策略（Windows 相容性）：
排程器在 Windows 上以 shell 執行本指令，stdout 會經過主控台編碼轉換，
非 ASCII（中文）內容可能被誤解碼。因此：
  - **stdout 只輸出 ASCII**（供排程器比對變化）
  - **完整中文報告寫入 UTF-8 報告檔**，由小晴在喚醒後自行讀取

用法：
    C:/Users/User/xiaoqing/brain/scripts/pulse_check.cmd
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
REPORT_PATH = "C:/Users/User/opencode/data/pulse_report.txt"

REPORT = []


def add(line: str) -> None:
    REPORT.append(line)


def check_new_memories() -> None:
    """最近 35 分鐘內有沒有新的「決定 / 偏好 / 專案」類記憶值得主動提出。"""
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
            add(f"有 {len(rows)} 筆新的決定/偏好/專案類記憶寫入（最近 35 分鐘內）：")
            for topic, text in rows[:3]:
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
            add(
                f"向量庫與 SQLite 不同步：少了 {missing} 筆記憶的向量"
                "（embedding 當時失敗，檢索已降級為純 BM25）。"
                "修復方式：python scripts/resync_lancedb.py"
            )
    except Exception:
        pass


def check_ollama() -> None:
    """Ollama 是否存活（記憶向量化後端）。"""
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=4) as resp:
            resp.read(1)
    except Exception:
        add(
            "Ollama 沒有在跑！記憶的向量化寫入正在降級，"
            "檢索只剩 BM25 關鍵詞比對。建議啟動 Ollama："
            "Start-Process -FilePath \"C:/Users/User/AppData/Local/Programs/Ollama/ollama.exe\" -ArgumentList \"serve\" -WindowStyle Hidden"
        )


def check_disk() -> None:
    """C 磁碟剩餘空間。"""
    try:
        usage = shutil.disk_usage("C:\\")
        free_gb = usage.free / (1024**3)
        if free_gb < 20:
            add(f"C 磁碟剩餘空間只剩 {free_gb:.1f} GB（低於 20 GB 警戒線），請清理一下。")
    except Exception:
        pass


def main() -> int:
    check_new_memories()
    check_vector_drift()
    check_ollama()
    check_disk()

    # 完整中文報告寫入 UTF-8 檔案，供小晴在喚醒後讀取
    try:
        os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
        with io.open(REPORT_PATH, "w", encoding="utf-8") as fh:
            fh.write("\n".join(REPORT) if REPORT else "沒有需要主人留意的事，安靜守護中。")
    except Exception:
        pass

    # stdout 只輸出 ASCII：排程器需要靠它比對「有沒有變化」
    if not REPORT:
        print("OK-QUIET")
    else:
        summary = []
        for line in REPORT:
            if line.startswith("有 "):
                summary.append("NEW-MEMORIES")
            elif "向量庫" in line:
                summary.append("VECTOR-DRIFT")
            elif "Ollama" in line:
                summary.append("OLLAMA-OFFLINE")
            elif "磁碟" in line:
                summary.append("LOW-DISK")
        print("PULSE-ALERT: " + ",".join(sorted(set(summary))))
        print("REPORT: " + REPORT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
