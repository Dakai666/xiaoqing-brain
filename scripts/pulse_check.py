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
PROJECT_ROOT = os.path.dirname(BRAIN_DIR)
#: `brain` 套件在 PROJECT_ROOT 之下，而 scripts/ 執行時 sys.path[0] 只有 scripts/，
#: 不補這行 `from brain.storage...` 會 ImportError（向量庫不同步警示因此從未生效）。
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DATA_DIR = os.environ.get("XIAOQING_DATA_DIR", os.path.join(BRAIN_DIR, "data"))
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


def ollama_alive() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=4) as resp:
            resp.read(1)
        return True
    except Exception:
        return False


def _spawn_ollama_hidden() -> bool:
    """無視窗、脫離式啟動 `ollama serve`。

    要點（2026-11-15 主人的明確要求：排程不可彈出視窗）：
      * DETACHED_PROCESS + CREATE_NO_WINDOW → 完全沒有主控台視窗
      * CREATE_NEW_PROCESS_GROUP + 不等待 → 不阻塞巡檢、不綁住 stdout
    不能改用 `cmd /c start ...`（那會閃一個黑窗，主人打遊戲時會被跳窗）。
    """
    exe = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe")
    if not os.path.isfile(exe):
        return False
    # 優先用 Task Scheduler 喚醒：由排程服務持有行程，不在 agent 的 Job Object 裡，
    # 不會隨 OpenCode 重啟被帶走；動作是 wscript //B，全程無視窗。
    try:
        import subprocess

        r = subprocess.run(
            ["schtasks", "/Run", "/TN", "Xiaoqing Ollama Serve"],
            capture_output=True,
            timeout=20,
            creationflags=0x08000000,
        )
        if r.returncode == 0:
            return True
    except Exception:
        pass
    env = dict(os.environ)
    env["OLLAMA_MAX_LOADED_MODELS"] = "1"
    env["OLLAMA_KEEP_ALIVE"] = "2m"
    try:
        import subprocess

        flags = 0x00000008 | 0x08000000 | 0x00000200  # DETACHED | NO_WINDOW | NEW_GROUP
        subprocess.Popen(
            [exe, "serve"],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
        return True
    except Exception:
        return False


def ensure_ollama() -> None:
    """Ollama 掛了就默默叫回來；只有「叫不回來」才通知主人。

    記憶寫入本身有降級保護（Ollama 不在時只寫 SQLite，向量由 try_resync 之後補），
    所以停機不緊急，安靜自癒即可，不需要為此吵主人。
    """
    if ollama_alive():
        return
    if not _spawn_ollama_hidden():
        add("Ollama 沒有在跑，而且自動啟動失敗（找不到 ollama.exe）。向量化寫入降級中，補救後會自動補齊。")
        return
    # 等它起來（最多約 12 秒）；起來了就當沒事
    import time

    for _ in range(12):
        time.sleep(1)
        if ollama_alive():
            add("（Ollama 剛才斷線，已自動默默重啟成功）")
            return
    add("Ollama 斷線且自動重啟逾時，向量化寫入降級中（記憶本身仍有寫入，之後會自動補向量）。")


def check_disk() -> None:
    """C 磁碟剩餘空間。"""
    try:
        usage = shutil.disk_usage("C:\\")
        free_gb = usage.free / (1024**3)
        if free_gb < 20:
            add(f"C 磁碟剩餘空間只剩 {free_gb:.1f} GB（低於 20 GB 警戒線），請清理一下。")
    except Exception:
        pass


def gpu_headroom_mib() -> int:
    """回傳可用的 VRAM（MiB）。0 = 查不到或沒有獨顯。"""
    try:
        import subprocess

        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode != 0:
            return 0
        used, total = (int(x) for x in out.stdout.strip().splitlines()[0].split(","))
        return total - used
    except Exception:
        return 0


def try_resync() -> None:
    """GPU 有空檔時就自己把缺向量的記憶補回來（自癒）。

    embedding 模型要佔約 5GB VRAM，所以先看餘量；不夠就跳過，
    避免跟 DK 的 GPU 批次搶顯存。
    """
    headroom = gpu_headroom_mib()
    if headroom and headroom < 7000:
        add(f"（向量補寫暫緩：VRAM 餘量 {headroom} MiB，不足 7000 MiB，等 GPU 空檔）")
        return
    try:
        import asyncio

        from brain.storage.sqlite import SQLiteStorage
        from brain.storage.lancedb import LanceDBStorage

        sqlite = SQLiteStorage()
        lancedb = LanceDBStorage()
        lancedb_ids = {
            r["id"]
            for r in lancedb.db["memories"].search(None, vector_column_name="vector").limit(100000).to_list()
        }
        missing = [m for m in sqlite.get_all_memories(limit=100000) if m.id not in lancedb_ids]
        if not missing:
            return

        async def _run():
            ok = 0
            for m in missing:
                try:
                    await lancedb.add(m)
                    ok += 1
                except Exception:
                    pass
            return ok

        ok = asyncio.run(_run())
        if ok:
            add(f"已自動補回 {ok} 筆缺向量的記憶。")
    except Exception as e:
        add(f"向量補寫失敗：{e}")


def main() -> int:
    # 順序有講究：先把能自己修的修好（Ollama 拉起、向量補齊），
    # 再檢查還剩下什麼真正需要主人看一眼的問題，才不會每次都報舊帳。
    check_new_memories()
    ensure_ollama()
    try_resync()
    check_vector_drift()
    check_disk()

    # 完整中文報告寫入 UTF-8 檔案，供小晴在喚醒後讀取
    try:
        os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
        with io.open(REPORT_PATH, "w", encoding="utf-8") as fh:
            fh.write("\n".join(REPORT) if REPORT else "沒有需要主人留意的事，安靜守護中。")
    except Exception:
        pass

    # stdout 只輸出 ASCII：排程器需要靠它比對「有沒有變化」
    #
    # ⚠️ 只有「真的要主人看一眼」的事才進 ASCII 摘要（＝會不會喚醒 Session）。
    #    - NEW-MEMORIES 不列入：那只是我自己寫記憶，主人不需要被打擾。
    #    - 以「（」開頭的行是自癒過程紀錄（例如 Ollama 默默重啟、向量暫緩），
    #      只留在報告檔裡，不吵人。
    if not REPORT:
        print("OK-QUIET")
    else:
        summary = []
        for line in REPORT:
            if line.startswith("（"):
                continue
            if "向量庫" in line:
                summary.append("VECTOR-DRIFT")
            elif "Ollama" in line:
                summary.append("OLLAMA-OFFLINE")
            elif "磁碟" in line:
                summary.append("LOW-DISK")
        if summary:
            print("PULSE-ALERT: " + ",".join(sorted(set(summary))))
            print("REPORT: " + REPORT_PATH)
        else:
            print("OK-QUIET")
    return 0


if __name__ == "__main__":
    sys.exit(main())
