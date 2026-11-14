# 小晴大腦 - 記憶系統 (xiaoqing-brain v2.0)

> 基於 SimpleMem 核心理念：有效率的記憶壓縮、整合與檢索
> **2026-11-14 v2.0 重大更新**：深度結合 **OpenCode 2.3 常駐型單一窗口 Agent 架構**（對標 Claude Duet / ChatGPT Dots）！
> - **0 延遲自動記憶雷達 (`context` Hook + `memory_context_fast.py`)**：對話前毫秒級自動注入記憶，不再依賴模型自覺呼叫 MCP
> - **主動/被動雙向記憶翻新 (`memory_refresh` + Supersede 自動衝突取代)**：舊設定或決策變更時自動淘汰舊記憶
> - **自我呼叫排程鬧鐘 (`xiaoqing_wakeup_schedule`)**：小晴能自己改排程、打給未來的自己起床！
> - **跨專案後廠委派 (`xiaoqing_delegate_project`)** 與 **常駐主窗口釘選 (`/master`)**

## 整體架構 (V2 Hook + MCP 雙軌閉環)

```
[回合前：0 延遲記憶雷達注入]
使用者發話 ──→ OpenCode 2.3 Server Plugin (`ctx.session.hook("context")`)
                     ↓
         `scripts/memory_context_fast.py` (<300ms SQLite 有效記憶 + Jieba BM25)
                     ↓
         自動注入 `<xiaoqing-companion-radar>` 至 System Prompt
         (含關聯記憶 [ID:xxxxxxxx]、核心偏好、主動寫入與翻新守則)

[回合中：主動固化、翻新與自我排程]
小晴 Agent ──→ 發現新重點：呼叫 `memory_add`
           ──→ 發現舊記憶過時：呼叫 `memory_refresh` (標記舊記憶 `is_superseded=1`)
           ──→ 預約未來任務：呼叫 `xiaoqing_wakeup_schedule` / `schedule_create`

[回合後：背景自動沉澱與衝突取代]
Session Idle ──→ `scripts/memory_ingest.py` ──→ BM25 預檢相關舊記憶
                     ↓
               CompressionStage (MiniMax-M2.7 抽取 + 自動判斷 `supersedes_id`)
                     ↓
               SynthesisStage (日記濃縮) ──→ LanceDB + SQLite + Markdown
```

**記帳模組（獨立運作）**
```
用戶輸入 ──→ AccountingParser ──→ SQLite (data/accounting.db)
              自然語言解析
```

## 環境設定

```bash
cd brain
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 啟動 MCP Server（由 OpenCode 自動管理）
python brain/mcp_server.py
```

## 模組結構

```
brain/
├── accounting/              # 🌟 記帳模組（2026-04 新增）
│   ├── __init__.py
│   └── service.py           # AccountingService + AccountingParser
├── models/
│   ├── memory_unit.py       # MemoryUnit 資料結構（攜帶豐富元數據）
│   └── topics.py            # 主題分類常數 (TOPICS)
├── stages/
│   ├── compression.py       # CompressionStage（LLM 過濾 + 結構化）
│   ├── synthesis.py         # SynthesisStage（同 session 整合）
│   ├── consolidation.py     # ConsolidationScheduler（每日跨 session 整合）
│   └── conflict.py          # 衝突解決策略
├── storage/
│   ├── lancedb.py           # LanceDB 向量儲存
│   ├── sqlite.py            # SQLite 結構化儲存（記憶 + 記帳）
│   └── markdown.py          # Markdown 備份
├── retrieval/
│   ├── bm25.py              # BM25 + jieba 關鍵詞檢索
│   ├── hybrid.py            # HybridRetriever（向量+BM25 混合）
│   └── intent.py            # IntentRetriever（意圖感知檢索）
├── utils/
│   └── llm_backend.py       # LLM 後端抽象層（支援 Ollama / MiniMax）
├── mcp_server.py            # MCP Server 單一入口（對外接口）
└── README.md
```

## 技術規格

| 组件 | 型號 | 用途 |
|------|------|------|
| LLM | MiniMax-M2.7 | 對話壓縮、合成、意圖分析 |
| Embeddings | qwen3-embedding:4b (Ollama) | 向量嵌入（MiniMax 限流時 fallback） |
| 向量DB | LanceDB | 語義檢索 |
| 結構化DB | SQLite | 時間/話題/人過濾 + 記帳資料 |
| 關鍵詞 | BM25 + jieba | 關鍵詞匹配 |
| MCP | Model Context Protocol | 跨 Agent 溝通 |
| 記帳解析 | AccountingParser | 自然語言支出/收入解析 |

## MCP Tools（記憶系統）

### memory_health
檢查記憶系統健康狀態
```json
{ "name": "memory_health", "inputSchema": {} }
```

### memory_index 🌟 NEW
Progressive Disclosure Layer 1 - 取得記憶索引（只回傳 ID、標題、時間、token 估計）
```json
{ "name": "memory_index", "inputSchema": { "limit": 50, "date": "YYYY-MM-DD" } }
```

### memory_timeline 🌟 NEW
Progressive Disclosure Layer 2 - 以某筆記憶為中心，回傳前後發生了什麼
```json
{ "name": "memory_timeline", "inputSchema": { "anchor_id": "string", "depth_before": 3, "depth_after": 3 } }
```

### memory_search
搜尋相關記憶（支援 Layer 3 指定 ID 取得完整內容）
```json
{ "name": "memory_search", "inputSchema": { "query": "string", "ids": ["string"], "top_k": 5 } }
```

### memory_add
新增對話到記憶（支援 `<private>` 隱私標籤）
```json
{ "name": "memory_add", "inputSchema": { "session_id": "string", "content": "string" } }
```

### memory_get_by_topic
依主題取得記憶
```json
{ "name": "memory_get_by_topic", "inputSchema": { "topic": "string" } }
```

### memory_get_by_person
依人員取得記憶
```json
{ "name": "memory_get_by_person", "inputSchema": { "person": "string" } }
```

### memory_get_context
主動記憶注入（主動援引相關記憶）
```json
{ "name": "memory_get_context", "inputSchema": { "context": "string", "top_k": 3 } }
```

### memory_refresh 🌟 NEW (2026-11-14)
翻新（Supersede）一筆舊記憶：當主人的偏好、專案狀態、模型設定或決策發生改變時，將舊記憶標記為已過時（`is_superseded=1`），並寫入最新版本的記憶，確保檢索不會讀到過期資訊。
```json
{
  "name": "memory_refresh",
  "inputSchema": {
    "old_memory_id": "string (完整 ID 或前 8 碼)",
    "new_content": "string (最新完整內容)",
    "topic": "preference | decision | technical | project | ...",
    "keywords": ["string"]
  }
}
```

### memory_delete 🌟 NEW (2026-11-14)
刪除一筆錯誤或不再需要的記憶（完整 ID 或前 8 碼皆可）
```json
{ "name": "memory_delete", "inputSchema": { "memory_id": "string" } }
```

---

## OpenCode 2.3 常駐管家插件 (`opencode_plugin/xiaoqing-memory.js`) 🌟 NEW (2026-11-14)

搭配 OpenCode 2.3 的 Server Plugin 架構（安裝於 `~/.config/opencode/plugins/xiaoqing-memory.js`），提供以下原生能力：

- **Direct Tools**：
  - `xiaoqing_wakeup_schedule`：小晴自我呼叫鬧鐘（支援 `in`、`at`、`every`、`cron` 與零成本 `if_shell_run` 條件閘）
  - `xiaoqing_wakeup_manage`：列出、暫停、恢復、刪除排程
  - `xiaoqing_delegate_project`：前店後廠模式，派發背景 Worker Session 到指定專案目錄施工，完工自動回報主窗口
  - `xiaoqing_master_window`：查看或釘選唯一常駐主窗口（Master Session）
- **Slash Commands**：
  - `/master`：將當前視窗釘選為「☀️ 小晴常駐主窗口」並檢視狀態
  - `/wakeup`：快速檢視或設定自我喚醒排程

## Phase B: 智慧記憶系統升級 (2026-04-20) 🌟

### Progressive Disclosure（漸進式披露）
Token 效率優化，~10x token 節省

```
Layer 1: Index ──→ Layer 2: Timeline ──→ Layer 3: Observation
(~50-100 tokens)   (~200 tokens)        (~500-1000 tokens)
```

### Icon/Legend 分類系統
```markdown
🔵 fact      - 用戶明確陳述的事實
💫 impression - 推斷、印象、猜測
🎯 preference - 偏好、喜歡、厭惡
🌱 habit     - 習慣、日常行為
```

### <private> 隱私標籤
敏感資料保護，`<private>敏感內容</private>` 自動脫敏

## MCP Tools（記帳系統）🌟

### accounting_add
自然語言或結構化輸入新增帳目
```json
{
  "name": "accounting_add",
  "inputSchema": {
    "text": "string（例：今天中午吃飯花了200元 或 expense:200:food:午餐）",
    "session_id": "string"
  }
}
```

**支援格式：**
- 自然語言：「今天中午吃拉麵花了200元」「本月薪水入帳35000元」
- 結構化：`expense:120:food:午餐` 或 `income:35000:salary:薪水`

**自動偵測：** 吃/飯/食→food，車/捷運→transport，買→shopping，醫/葯→health，賺/收入/入帳→income

### accounting_summary
本月收支摘要（含分類長條圖）
```json
{ "name": "accounting_summary", "inputSchema": { "days": 30 } }
```

### accounting_today
今天的所有記錄
```json
{ "name": "accounting_today", "inputSchema": {} }
```

### accounting_all
所有記錄（最近50筆）
```json
{ "name": "accounting_all", "inputSchema": {} }
```

## 效能數據

| 操作 | 時間 | 備註 |
|------|------|------|
| CompressionStage | ~10-16s/次 | MiniMax-M2.7 |
| SynthesisStage | ~10s/次 | MiniMax-M2.7 |
| Intent 分析 | ~2s/次 | MiniMax-M2.7 |
| 向量檢索 | ~0.6s | Ollama fallback |
| BM25 檢索 | <10ms | 快速 |
| 記帳解析 | <1ms | 本地 Regex 解析 |

## 主題分類

```python
TOPICS = {
    "personal",      # 個人資訊（姓名、習慣）
    "technical",     # 技術知識（程式、工具）
    "preference",    # 偏好設定
    "project",       # 專案相關
    "event",         # 事件記錄
    "decision",      # 重要決定
    "learning",      # 學習心得
    "routine",       # 日常作息
    "general",       # 一般（預設）
}
```

## 記帳分類

```python
Category = {
    "food",           # 餐飲、食物
    "transport",      # 交通費用
    "entertainment",  # 娛樂、遊戲、影視
    "shopping",       # 購物、網購
    "health",         # 醫療、健康
    "education",      # 教育、學習
    "living",         # 房租、水電、生活
    "other",          # 其他
}
```

## 記憶元數據

每筆記憶攜帶豐富的元數據：

```python
class MemoryUnit:
    id: str                           # 唯一識別
    lossless_text: str                # 原始文字（保留）
    keywords: List[str]               # 關鍵詞標籤
    timestamp: str                    # ISO 時間戳
    date: str                        # 日期（YYYY-MM-DD）
    persons: List[str]                # 相關人員
    topic: str                       # 主題分類
    session_id: str                   # 所屬 session
    intent_type: IntentType           # fact, impression, preference, habit
    source_reliability: float        # 0.6-1.0
    decay_rate: DecayRate             # fast(50%/天), normal(10%/天), slow(2%/天), none
    confidence: float                 # 0.0-1.0，隨時間衰減
    is_superseded: bool              # 是否被新記憶取代
    replaced_by: str                  # 取代者 ID
    needs_confirmation: bool         # 是否需用戶確認
```

### Decay 衰減公式

| 等級 | 衰減率 | 範例 |
|------|--------|------|
| fast | 50%/天 | 天氣、新聞 |
| normal | 10%/天 | 一般對話 |
| slow | 2%/天 | 偏好、習慣 |
| none | 0% | 身份、永久事實 |

## 使用方式

### Python 直接呼叫（記憶系統）

```python
import os
from brain.utils.llm_backend import MiniMaxBackend, set_llm_backend
from brain import (
    CompressionStage,
    SynthesisStage,
    HybridRetriever,
)

set_llm_backend(MiniMaxBackend())

async def main():
    compression = CompressionStage(model='MiniMax-M2.7')
    synthesis = SynthesisStage(model='MiniMax-M2.7')
    retriever = HybridRetriever()

    memories = await compression.process("使用者說他喜歡 Python")
    for m in memories:
        synthesis.add(m)

    if synthesis.should_synthesize():
        synthesized = await synthesis.synthesize_if_needed()

    for m in memories:
        await retriever.add_memory(m)

    results = await retriever.search("程式語言偏好")
```

### Python 直接呼叫（記帳系統）

```python
from brain.accounting import AccountingService

svc = AccountingService()

# 新增帳目（自然語言）
ok, msg, tx = svc.add_transaction('今天中午吃拉麵花了200元', 'session-123')

# 查看本月摘要
print(svc.get_summary())

# 查看今日記錄
print(svc.get_today())
```

### MCP Server（MCP 協議呼叫）

```bash
# MCP Server 由 OpenCode 自動啟動
python brain/mcp_server.py
```

其他 Agent 透過 MCP 協議呼叫 tools（見上方 MCP Tools 章節）。

## 測試腳本

```bash
cd /home/user/.kimaki/projects/xiaoqing/brain

# P1+P2 完整測試
PYTHONPATH=. python scripts/test_p2_complete.py

# MCP Server 測試
PYTHONPATH=. python scripts/test_mcp.py

# 記憶系統壓縮測試
PYTHONPATH=. python scripts/test_synthesis.py

# 獨立測試記帳解析
PYTHONPATH=. python -c "
from brain.accounting import AccountingService
svc = AccountingService()
ok, msg, _ = svc.add_transaction('LLM訂閱費 4000元', 'test')
print(msg)
print(svc.get_summary())
"
```

## 資料庫位置

| 資料 | 路徑 |
|------|------|
| 記憶資料 | `data/memories.db` (SQLite) |
| 向量資料 | `data/lancedb/` |
| 備份文字 | `data/backups/YYYY-MM-DD.md` |
| 記帳資料 | `data/accounting.db` (SQLite) |

## 開發進度

- [x] **Phase 1: MVP（核心功能）**
  - [x] 專案結構
  - [x] MemoryUnit
  - [x] CompressionStage
  - [x] StorageStage (LanceDB + SQLite + Markdown)
  - [x] 檢索 (向量 + BM25)

- [x] **Phase 2: 強化**
  - [x] SynthesisStage（同 session 整合）
  - [x] Intent-Aware Retrieval
  - [x] ConsolidationScheduler（每日整合）
  - [x] MiniMax-M2.7 支援

- [x] **Phase 3: MCP 整合** ✅
  - [x] 建立 MCP Server
  - [x] 對外提供檢索接口
  - [x] 小晴本體成功呼叫 MCP Tools
  - [x] 成功記憶 Dakai 的個人資料

- [x] **Phase 4: 優化** ✅ 2026-04-08
  - [x] 修復 LanceDB query API 相容性問題
  - [x] 自動記憶注入（memory_get_context tool）
  - [x] 記憶 decay 機制
  - [x] 衝突解決策略
  - [x] 壓縮率統計

- [x] **Phase 5: 記帳系統** ✅ 2026-04-09
  - [x] 獨立 AccountingService + AccountingParser
  - [x] SQLite 記帳儲存（data/accounting.db）
  - [x] 自然語言解析（支出/收入自動判斷）
  - [x] 4 個 MCP Tools（add/summary/today/all）
  - [x] 分類自動偵測（food/transport/shopping/health...）
  - [x] 月摘要文字報告（含分類長條圖）

- [x] **Phase B: 智慧記憶系統升級** ✅ 2026-04-20
  - [x] Progressive Disclosure 三層架構（memory_index + memory_timeline + memory_search ids）
  - [x] Icon/Legend 分類系統（🔵💫🎯🌱）
  - [x] <private> 隱私標籤（自動脫敏 + 搜尋過濾）
  - [ ] Lifecycle Hooks 介面（進行中）

---

*小晴大腦 v0.3 - 記憶 + 記帳 + 智慧檢索三系統運作中！2026-04-20*