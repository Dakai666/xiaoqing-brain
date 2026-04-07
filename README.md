# 小晴大腦 - 記憶系統

> 基於 SimpleMem 核心理念：有效率的記憶壓縮、整合與檢索

## 架構

```
原始對話 → CompressionStage → SynthesisStage → StorageStage → RetrievalStage
                    ↓                  ↓               ↓              ↓
              MiniMax-M2.7    MiniMax-M2.7     LanceDB+         向量+BM25
                                                 SQLite+MD       混合檢索
```

## 環境設定

```bash
cd brain
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 模組

### Models
- `models/memory_unit.py` - MemoryUnit 資料結構
- `models/topics.py` - 主題分類常數 (TOPICS)

### Stages
- `stages/compression.py` - CompressionStage (LLM 過濾 + 結構化)
- `stages/synthesis.py` - SynthesisStage (同 session 整合)
- `stages/consolidation.py` - ConsolidationScheduler (每日跨 session 整合)

### Storage
- `storage/lancedb.py` - LanceDB 向量儲存
- `storage/sqlite.py` - SQLite 結構化儲存
- `storage/markdown.py` - Markdown 備份

### Retrieval
- `retrieval/bm25.py` - BM25 + jieba 關鍵詞檢索
- `retrieval/hybrid.py` - HybridRetriever (向量+BM25 混合)
- `retrieval/intent.py` - IntentRetriever (意圖感知檢索)

### MCP Server
- `mcp/server.py` - MCP Server（記憶系統對外接口）

### Utils
- `utils/llm_backend.py` - LLM 後端抽象層（支援 Ollama / MiniMax）

## 技術規格

| 组件 | 型號 | 用途 |
|------|------|------|
| LLM | MiniMax-M2.7 | 對話壓縮、合成、意圖分析 |
| Embeddings | qwen3-embedding:4b (Ollama) | 向量嵌入（MiniMax 限流時 fallback） |
| 向量DB | LanceDB | 語義檢索 |
| 結構化DB | SQLite | 時間/話題/人過濾 |
| 關鍵詞 | BM25 + jieba | 關鍵詞匹配 |
| MCP | Model Context Protocol | 跨 Agent 溝通 |

## MCP Tools

```json
{
  "name": "memory_health",
  "description": "檢查小晴記憶系統健康狀態",
  "inputSchema": {}
}

{
  "name": "memory_search",
  "description": "搜尋小晴的記憶",
  "inputSchema": {
    "query": "string",
    "top_k": "integer (optional, default: 5)"
  }
}

{
  "name": "memory_add", 
  "description": "新增對話到小晴的記憶",
  "inputSchema": {
    "session_id": "string",
    "content": "string"
  }
}

{
  "name": "memory_get_by_topic",
  "description": "依主題取得小晴的記憶",
  "inputSchema": {
    "topic": "string"
  }
}

{
  "name": "memory_get_by_person",
  "description": "依人員取得小晴的記憶",
  "inputSchema": {
    "person": "string"
  }
}

{
  "name": "memory_get_context",
  "description": "取得上下文相關的記憶，方便小晴在回覆時引用（主動記憶注入）",
  "inputSchema": {
    "context": "string",
    "top_k": "integer (optional, default: 3)"
  }
}
```

## 效能數據

| 操作 | 時間 | 備註 |
|------|------|------|
| CompressionStage | ~10-16s/次 | MiniMax-M2.7 |
| SynthesisStage | ~10s/次 | MiniMax-M2.7 |
| Intent 分析 | ~2s/次 | MiniMax-M2.7 |
| 向量檢索 | ~0.6s | Ollama fallback |
| BM25 檢索 | <10ms | 快速 |

## 主題分類

```python
TOPICS = {
    "personal",      # 個人資訊
    "technical",     # 技術知識
    "preference",    # 偏好設定
    "project",       # 專案相關
    "event",         # 事件記錄
    "decision",      # 重要決定
    "learning",      # 學習心得
    "routine",       # 日常作息
    "general",       # 一般（預設）
}
```

## 記憶元數據

每筆記憶攜帶豐富的元數據：

```python
class MemoryUnit:
    intent_type: IntentType  # fact, impression, preference, habit
    source_reliability: float  # 0.6-1.0
    decay_rate: DecayRate  # fast(50%/天), normal(10%/天), slow(2%/天), none
    confidence: float  # 0.0-1.0，隨時間衰減
    is_superseded: bool  # 是否被新記憶取代
    replaced_by: str  # 取代者 ID
    needs_confirmation: bool  # 是否需用戶確認
```

### Decay 公式

| 等級 | 衰減率 | 範例 |
|------|--------|------|
| fast | 50%/天 | 天氣、新聞 |
| normal | 10%/天 | 一般對話 |
| slow | 2%/天 | 偏好、習慣 |
| none | 0% | 身份、永久事實 |

## 使用方式

### 基本流程

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

### MCP Server

```bash
# 直接運行 MCP Server（由 OpenCode 自動調用）
python brain/mcp_server.py
```

其他 Agent 可透過 MCP 協議呼叫：
- `memory.search(query, top_k)` - 搜尋記憶
- `memory.add(session_id, content)` - 新增記憶
- `memory.get_by_topic(topic)` - 依主題取得
- `memory.get_by_person(person)` - 依人員取得
- `memory.get_context(context, top_k)` - 主動記憶注入（回傳時間距離+信心度）

## 測試腳本

```bash
# P1+P2 完整測試
PYTHONPATH=. python scripts/test_p2_complete.py

# MCP Server 測試
PYTHONPATH=. python scripts/test_mcp.py
```

## 開發進度

- [x] Phase 1: MVP（核心功能）
  - [x] 專案結構
  - [x] MemoryUnit
  - [x] CompressionStage
  - [x] StorageStage (LanceDB + SQLite + Markdown)
  - [x] 檢索 (向量 + BM25)

- [x] Phase 2: 強化
  - [x] SynthesisStage（同 session 整合）
  - [x] Intent-Aware Retrieval
  - [x] ConsolidationScheduler（每日整合）
  - [x] MiniMax-M2.7 支援

- [x] Phase 3: MCP 整合 ✅
  - [x] 建立 MCP Server
  - [x] 對外提供檢索接口 (memory.search/add/get_by_topic/get_by_person)
  - [x] 小晴本體成功呼叫 MCP Tools
  - [x] 成功記憶 Dakai 的個人資料

- [x] Phase 4: 優化 ✅ 2026-04-08
  - [x] 修復 LanceDB query API 相容性問題
  - [x] 自動記憶注入（memory_get_context tool）
  - [x] 記憶 decay 機制（A2）
  - [x] 衝突解決策略（A3）
  - [ ] 壓縮率統計

---

*小晴筆記 - Phase 3 成功！記憶系統正式上線！2026-03-26*
