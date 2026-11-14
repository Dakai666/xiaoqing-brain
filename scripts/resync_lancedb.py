#!/usr/bin/env python3
"""同步 LanceDB 向量庫與 SQLite 結構化庫。

背景：當 Ollama 未啟動或 embedding 失敗時，`HybridRetriever.add_memory()` 會降級
只寫入 SQLite / BM25 / markdown，導致向量庫筆數落後（記憶仍可被檢索到，只是
少了語意檢索那一路）。

本腳本比對兩邊的 id，把 SQLite 有、LanceDB 缺的記憶補進向量庫（重新 embed）。

用法：
    python scripts/resync_lancedb.py          # 預設只補缺失的
    python scripts/resync_lancedb.py --report # 只報告差異，不寫入
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


async def main() -> int:
    report_only = "--report" in sys.argv

    # Windows 主控台預設 cp950，無法輸出 emoji/中文標點；強制 UTF-8。
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    from brain.storage.sqlite import SQLiteStorage
    from brain.storage.lancedb import LanceDBStorage

    sqlite = SQLiteStorage()
    lancedb = LanceDBStorage()

    # 比對時包含「已被取代」的記憶：它們在兩個庫都存在，只是標記不同。
    sqlite_memories = sqlite.get_active_memories(limit=100000)
    sqlite_all = sqlite.get_all_memories(limit=100000)
    sqlite_ids = {m.id for m in sqlite_all}

    lancedb_rows = (
        lancedb.db["memories"].search(None, vector_column_name="vector").limit(100000).to_list()
    )
    lancedb_ids = {r["id"] for r in lancedb_rows}

    missing = [m for m in sqlite_memories if m.id not in lancedb_ids]
    orphaned = lancedb_ids - sqlite_ids
    superseded_in_sqlite = len(sqlite_all) - len(sqlite_memories)

    print(f"SQLite 有效記憶: {len(sqlite_memories)} 筆（全部 {len(sqlite_all)} 筆）")
    print(f"LanceDB 向量記憶: {len(lancedb_ids)} 筆")
    print(f"缺少向量 (需補): {len(missing)} 筆")
    print(f"向量孤兒 (SQLite 無對應): {len(orphaned)} 筆")
    print(f"已被取代的舊記憶 (兩庫皆保留，標記為過時): {superseded_in_sqlite} 筆")

    if report_only:
        return 0

    if not missing:
        print("✅ 向量庫已是最新，無需補寫。")
        return 0

    ok = 0
    failed = 0
    for i, m in enumerate(missing, 1):
        try:
            await lancedb.add(m)
            ok += 1
            if ok % 5 == 0 or i == len(missing):
                print(f"  [{i}/{len(missing)}] 已補 {ok} 筆 (失敗 {failed})")
        except Exception as e:
            failed += 1
            print(f"  [{i}/{len(missing)}] ❌ 失敗: {e}")

    print(f"✅ 補寫完成：成功 {ok} 筆，失敗 {failed} 筆")
    print(json.dumps({"ok": ok, "failed": failed}, ensure_ascii=False))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
