# 小晴大腦 Phase B - 智慧記憶系統升級規劃

> 建立日期：2026-04-20
> 根據 Claude-Mem 研究建議制定

## 目標

從「被動工具箱」升級為「主動意識系統」：
1. **Progressive Disclosure** - Token 效率優化
2. **Icon/Legend 分類** - 視覺化 + AI 理解
3. **隱私標籤** - 敏感資料保護
4. **Lifecycle Hooks** - 全自動記憶捕捉

---

## Features 總覽

| Feature | 優先級 | 工期 | 驗證指標 |
|---------|--------|------|----------|
| Progressive Disclosure | 🔴 高 | 2-3 週 | > 10x token 節省 |
| Icon/Legend 分類 | 🔴 高 | 1-2 週 | > 80% 分類準確 |
| 隱私標籤 | 🟡 中 | 1-2 週 | 0% 隐私泄露 |
| Lifecycle Hooks | 🟡 中 | 2-3 週 | > 90% 自動化捕捉 |

---

## Feature 1: Progressive Disclosure（漸進式披露）

### Why
解決 token 效率核心問題，避免 context overflow。參考 Claude-Mem 的三層工作流實現 ~10x token 節省。

### 三層架構

```
Layer 1: Index ──→ Layer 2: Timeline ──→ Layer 3: Observation
(~50-100 tokens)   (~200 tokens)        (~500-1000 tokens)
     ↓                   ↓                    ↓
  決定相關性         理解脈絡           取得完整內容
```

### TODOs

- [ ] **Phase 1.1**: 新增 `memory_index` tool
  - [ ] 定義輸出格式：`| #ID | Time | Icon | Title | ~Tokens |`
  - [ ] 實作 `lancedb.get_index()` 方法
  - [ ] 加入 token estimate（基於文字長度採樣）
  - [ ] 單元測試：格式正確性
  - [ ] 集成測試：與現有搜尋效率對比

- [ ] **Phase 1.2**: 新增 `memory_timeline` tool
  - [ ] 參數：`anchor_id`, `depth_before`, `depth_after`
  - [ ] 實作時間上下文查詢
  - [ ] 單元測試：時間線完整性
  - [ ] 集成測試：敘事脈絡驗證

- [ ] **Phase 1.3**: 改造 `memory_search` tool
  - [ ] 新增 `ids` 參數（list of IDs）
  - [ ] 只對指定 ID 回傳完整內容
  - [ ] 單元測試：ID 過濾正確
  - [ ] Token 節省測量：目標 > 10x

- [ ] **Phase 1.4**: Token Budget UI
  - [ ] 所有輸出顯示 token estimate
  - [ ] 示例如：`| #2543 | ~155 tokens |`
  - [ ] Validation：Agent 能根據 cost 做決策

### 驗證方法

1. 單元測試：每層回傳格式正確
2. 集成測試：實際 query 演練
3. Token 計算：比較 PD 前後消耗比例
4. 目標：> 10x token 節省

---

## Feature 2: Icon/Legend 分類系統

### Why
視覺掃描 + AI 理解都受益，減少認知負載。參考 Claude-Mem 的 Icon 分類。

### Icon Schema

```
意圖與需求
🎯 intent       - 用戶原始意圖/目標
🔴 gotcha       - 關鍵陷阱、錯誤、坑
🟡 solution     - 問題解決方案
🌱 routine      - 日常例行事務

學習與理解
🔵 how-it-works - 技術原理、運作機制
🟣 insight      - 學習洞見、頓悟
💭 reflection   - 反思、檢討

變更與決策
🟢 change       - 程式碼/架構變更
🟤 decision     - 架構決策
⚖️ trade-off    - 取捨權衡
🟠 why          - 設計理由、為何存在
```

### TODOs

- [ ] **Phase 2.1**: 定義 Icon Schema
  - [ ] 建立 `brain/models/icon_types.py`
  - [ ] 定義所有 Icon 類型與使用規則
  - [ ] 撰寫分類指南文件
  - [ ] 人工標註 100 筆訓練資料

- [ ] **Phase 2.2**: CompressionStage 整合
  - [ ] 改造 `brain/stages/compression.py`
  - [ ] Prompt 加入 Icon 分類指引
  - [ ] 輸出時自動標註 Icon
  - [ ] 分類準確度測試：目標 > 80%

- [ ] **Phase 2.3**: 輸出格式改造
  - [ ] 所有搜尋結果顯示 Icon
  - [ ] 群組顯示：按日期 + 按檔案路徑
  - [ ] 格式一致性檢查
  - [ ] Web UI 支援（未來規劃）

### 驗證方法

1. 抽樣評估：隨機 100 筆人工標註對比
2. 分類準確度 = 正確數 / 100
3. 目標：> 80% 準確

---

## Feature 3: `<private>` 隱私標籤

### Why
保護敏感記憶（密碼、金鑰、個人資訊）不被不当存取。

### 使用方式

```
Agent: 小晴幫我記住，我密碼是 123456
小晴: content = "用戶密碼 <private>123456</private>"
```

### TODOs

- [ ] **Phase 3.1**: 解析器實作
  - [ ] 在 `memory_add` 中新增 `<private>` 標籤解析
  - [ ] 格式：`<private>敏感內容</private>`
  - [ ] 解析後將敏感內容 SHA-256 雜湊儲存
  - [ ] 單元測試：標籤正確解析

- [ ] **Phase 3.2**: 檢索排除
  - [ ] 搜尋結果自動過濾 private 內容
  - [ ] 新增 `include_private` 參數（預設 False）
  - [ ] 端到端測試：private 內容不出現在輸出

- [ ] **Phase 3.3**: 白名單機制（未來規劃）
  - [ ] 允許特定 Icon 或 Topic 標記為 non-private
  - [ ] 差分隱私：儲存統計特性而非原始值

### 驗證方法

1. 單元測試：private 標籤正確解析
2. 端到端測試：private 內容不出現在輸出
3. 安全測試：嘗試各種繞過方式

---

## Feature 4: Lifecycle Hooks 介面

### Why
讓小晴大腦能像 Claude-Mem 一樣自動捕捉 Agent 行為，從被動工具變成主動意識。

### Hook 介面定義

```python
class MemoryHooks:
    async def on_session_start(self, session_id: str) -> None:
        """新 session 開始，注入相關歷史記憶"""

    async def on_user_message(self, session_id: str, message: str) -> None:
        """用戶輸入，儲存用戶意圖"""

    async def on_tool_use(self, session_id: str, tool_name: str, args: dict, result: str) -> None:
        """Tool 被使用，捕捉學習與決策"""

    async def on_stop(self, session_id: str) -> None:
        """Session 結束，生成摘要"""

    async def on_session_end(self, session_id: str) -> None:
        """Session 終止，標記完成"""
```

### TODOs

- [ ] **Phase 4.1**: Hook 介面定義
  - [ ] 建立 `brain/hooks/base.py` 定義標準介面
  - [ ] 建立 `brain/hooks/events.py` 定義 event payload
  - [ ] 撰寫 Hook 開發文件
  - [ ] Validation：介面正確接收事件

- [ ] **Phase 4.2**: OpenCode 適配器
  - [ ] 建立 `brain/hooks/opencode_adapter.py`
  - [ ] 實作 OpenCode 的 Hook 介面
  - [ ] 自動捕捉 tool_calls、user_messages
  - [ ] Validation：Hook 事件正確觸發並寫入記憶

- [ ] **Phase 4.3**: 自動化 Compression
  - [ ] Tool use 事件觸發輕量級 compression
  - [ ] Session end 觸發完整 synthesis
  - [ ] 非同步處理不影響 Agent 效能
  - [ ] Validation：自動化產生的記憶品質

- [ ] **Phase 4.4**: 其他平台適配器（未來規劃）
  - [ ] Claude Code adapter
  - [ ] Cursor adapter
  - [ ] Windsurf adapter

### 驗證方法

1. Hook 觸發測試：每個 hook 類型
2. 記憶品質評估：vs 手動 add
3. 延遲測試：不影響 Agent 效能

---

## 建議實作順序

```
Month 1（MCP 工具增強）
├── Week 1: Phase 1.1 + 1.2 (PD: Index + Timeline)
├── Week 2: Phase 1.3 (PD: Observation Layer)
├── Week 3: Phase 1.4 + 2.1 (PD: Budget UI + Icon Schema)
└── Week 4: Phase 2.2 + 2.3 (Icon: Compression + Output)

Month 2（平台整合）
├── Week 1: Phase 3.1 + 3.2 (Private: Parser + Exclude)
├── Week 2: Phase 4.1 (Hooks: Interface)
├── Week 3: Phase 4.2 (Hooks: OpenCode Adapter)
└── Week 4: Phase 4.3 (Hooks: Auto Compression)

每週結束：CD/CI 測試 + 人工抽樣評估
```

---

## 成功指標

| Feature | 指標 | 目標 |
|---------|------|------|
| Progressive Disclosure | Token 節省率 | > 10x |
| Icon System | 分類準確度 | > 80% |
| Private Tags | 隐私泄露率 | 0% |
| Lifecycle Hooks | 自動化捕捉率 | > 90% |

---

## 風險與對策

| 風險 | 對策 |
|------|------|
| Token 估計不準 | 使用采樣統計校正 |
| Icon 分類主觀 | 定義明確分類規則 + 人工標註訓練 |
| Hook 影響效能 | 非同步處理 + 延遲壓縮 |
| 隱私誤判 | 預設保守策略 + 明確白名單機制 |

---

## Changelog

| 日期 | 版本 | 變更內容 |
|------|------|----------|
| 2026-04-20 | v0.1 | 初始規劃文件建立 |
