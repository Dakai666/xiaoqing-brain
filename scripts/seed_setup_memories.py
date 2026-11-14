"""小晴大腦：正式記錄主人環境（第一筆有意識的記憶存入）"""
import asyncio
import sys
import os

BRAIN_DIR = r"C:\Users\User\xiaoqing\brain"
os.chdir(BRAIN_DIR)
sys.path.insert(0, r"C:\Users\User\xiaoqing")
sys.path.insert(0, BRAIN_DIR)

from brain.stages.compression import CompressionStage
from brain.retrieval.hybrid import HybridRetriever
from brain.storage.sqlite import SQLiteStorage
from brain.storage.markdown import MarkdownBackup
from brain.models.memory_unit import IntentType, DecayRate


ENTRIES = [
    {
        "session_id": "setup-2026-09-10",
        "title": "xiaoqing-brain 安裝位置與結構",
        "content": (
            "xiaoqing-brain 安裝在 Windows 主機，路徑 C:\\Users\\User\\xiaoqing\\。"
            "結構：brain/ 為 MCP server 套件（Python 3.12 venv）；"
            "brain/mcp_server.py 是入口；brain/data/ 存 SQLite + LanceDB + Markdown backup。"
            "13 個 MCP tools：memory_health/index/timeline/search/add/get_by_topic/get_by_person/get_context、"
            "accounting_add/summary/today/all、lifecycle_event。"
            "已透過 opencode.json 的 mcp.xiaoqing-brain 區塊註冊。"
        ),
        "intent": "fact",
        "decay": "slow",
    },
    {
        "session_id": "setup-2026-09-10",
        "title": "LLM 與 embedding 設定",
        "content": (
            "主人電腦的 LLM 與 embedding 設定。"
            "預設 LLM backend：Ollama（http://127.0.0.1:11434），模型 qwen3.5:9b（6.59 GB）。"
            "預設 embedding：qwen3-embedding:latest，維度 4096。"
            "備用 LLM：MiniMax API（https://api.minimax.io/anthropic/v1，Anthropic Messages API 格式），"
            "但 opencode.json 的 sk-cp-... key 已失效（4 種 header 變體都回 401），目前無法使用。"
            "LMStudio（http://localhost:1234/v1）有設定但未啟動。"
            "環境陷阱：Windows 上 OLLAMA_HOST=0.0.0.0 是 bind 用不能 connect，已繞過。"
            "相關環境變數：XIAOQING_LLM_MODEL, XIAOQING_EMBED_MODEL, XIAOQING_EMBED_DIM, XIAOQING_DATA_DIR, "
            "MINIMAX_API_KEY, MINIMAX_BASE_URL。"
        ),
        "intent": "fact",
        "decay": "slow",
    },
    {
        "session_id": "setup-2026-09-10",
        "title": "採用 xiaoqing-brain 的關鍵決策",
        "content": (
            "主人 2026-09-10 對 xiaoqing-brain 的關鍵決策："
            "1. 採用 xiaoqing-brain 而非 opencode-mem：因為小晴大腦是主人親手做的，"
            "個人化更深、有 decay/conflict/progressive disclosure 等 opencode-mem 沒有的功能。"
            "opencode-mem config 已改為 .disabled。"
            "2. 採用 Ollama 本機模型而非 MiniMax API：因為 MiniMax API key 失效、Ollama 免費且隱私。"
            "3. 採用 Anthropic Messages API 格式作為 MiniMax 通訊協議：比 OpenAI 格式穩定。"
            "4. 從 Linux 移植到 Windows 的目錄結構為 C:\\Users\\User\\xiaoqing\\，"
            "模擬原本 /home/user/.kimaki/projects/xiaoqing/。"
        ),
        "intent": "preference",
        "decay": "none",
    },
    {
        "session_id": "setup-2026-09-10",
        "title": "已清理的舊環境",
        "content": (
            "已清理主人電腦上的舊環境（2026-09-10），總共 ~706 MB。"
            "刪除 ~/.opencode-mem/（空的、從未使用）、"
            "~/.embedchain/（schema 在但全空表）、"
            "~/.basic-memory/（停用很久、log 顯示 2025-09 之後沒新活動）、"
            "~/.kimaki/（舊的 kimaki plugin）、"
            "~/.dsh/（今天測試的 DeepSeek Harness）、"
            "以及 3 個 npx cache（DSH 222 MB + kimaki 462 MB）。"
            "保留 ~/.config/opencode/opencode-mem.jsonc.disabled（反悔用），"
            "改回 .jsonc 即可恢復 opencode-mem。"
        ),
        "intent": "fact",
        "decay": "normal",
    },
    {
        "session_id": "setup-2026-09-10",
        "title": "已知的記憶 bug 與未來升級路徑",
        "content": (
            "目前已修復 / 待辦："
            "1. storage/lancedb.py 的 _embed() 已修：之前直接 import ollama 會被 OLLAMA_HOST=0.0.0.0 卡住，"
            "現在改用統一 OllamaBackend。"
            "2. 小晴是 MiniMax-M3，但 opencode.json 裡 minimax provider 沒列 M3，只有 M2.5/M2.7/highspeed。"
            "MCP server 用的 LLM 模型名稱如果主人要改，可在 .env 設 XIAOQING_LLM_MODEL。"
            "3. 升級方向（主人提出）：Knowledge Wiki（使用者端 vs agent 端知識庫切分）、"
            "更強的 Reflection loop。"
            "4. opencode-mem 是否完全取代 xiaoqing-brain：目前是 xiaoqing-brain 為主，"
            "opencode-mem 已關閉（檔案改名 .disabled）。"
        ),
        "intent": "fact",
        "decay": "normal",
    },
]


async def main():
    compression = CompressionStage(model="qwen3.5:9b")
    retriever = HybridRetriever()
    sqlite = SQLiteStorage()
    markdown = MarkdownBackup()

    print(f"=== 準備寫入 {len(ENTRIES)} 筆記憶 ===\n")
    total_added = 0

    for i, entry in enumerate(ENTRIES, 1):
        print(f"[{i}/{len(ENTRIES)}] {entry['title']}")
        try:
            memories = await compression.process(entry["content"])
            for m in memories:
                m.session_id = entry["session_id"]
                m.intent_type = IntentType(entry["intent"])
                m.decay_rate = DecayRate(entry["decay"])
                await retriever.add_memory(m)
            total_added += len(memories)
            print(f"    OK {len(memories)} memory units")
        except Exception as e:
            print(f"    ERROR: {e}")
        print()

    print(f"=== 完成，總共新增 {total_added} 個 memory unit ===")

    sqlite_total = len(sqlite.search("", 10000))
    print(f"SQLite 總計：{sqlite_total} 筆")


if __name__ == "__main__":
    asyncio.run(main())
