# OpenCode 常駐型單一窗口 AI Agent 架構規劃書
**對標產品：Claude Duet / ChatGPT Dots / Grok Bot**
**版本**：v1.0（基於 OpenCode v2.3.0 實機驗證）
**日期**：2026-11-14

---

## 0. 核心結論：打破「OpenCode 沒有相關接口」的疑慮

**結論：OpenCode 2.x 不僅有接口，而且底層就是為了這個場景重構的。**

過去（OpenCode 1.x 或舊版 `gateway/orchestrator/opencode.js`）的做法是用 `child_process.spawn("opencode run --session ...")` 每次重開 CLI 行程，既慢、無法即時串流、也無法與桌面視窗同步。

但在本機目前運行的 **OpenCode v2.3.0** 中，架構已經完全改為 **單一背景 Daemon（Background Service）+ 多端共享 Session 狀態**，並且內建了以下**五大關鍵原生接口**（皆已於本機 `/openapi.json` 驗證存在）：

1. **多端同步的單一主線（Shared Live Session）**
   - 背景 Daemon（`opencode serve --service`）統一持有 Session。
   - 不論是 OpenCode Desktop 視窗、TUI、自製浮動視窗，還是背景排程腳本，只要對同一個 `sessionID` 發送訊息或訂閱 `GET /api/event`（SSE 事件流），**畫面會即時同步更新**，完全不需要重開視窗。
2. **無感跨專案切換與背景委派（Session Move & Background Subagents）**
   - **主線瞬移**：內建 `POST /api/session/{sessionID}/move`（以及 Code Mode 的 `tools.opencode.session_move`），可在**不換 Session、不關視窗**的前提下，把當前對話的工作目錄動態切換到任意專案資料夾。
   - **背景分身**：遇到耗時開發任務，主對話可透過 `subagent` 工具或 Client API 在特定專案目錄建立隱藏的子 Session（Worker）平行執行，完成後再回報到主窗口。
3. **原生條件式自我喚醒排程器（`experimental.schedules`）**
   - OpenCode v2.3.0 內建了實驗性但極為完整的 `/api/experimental/schedule` 接口！
   - 支援四種時間觸發：`in`（延遲）、`at`（指定時間）、`every`（固定間隔）、`cron`（排程表達式）。
   - **最關鍵的「條件過濾（Condition Gate）」**：支援在喚醒 LLM 前先跑一段 `shell` 指令或 `code`（Code Mode JS，可保存跨次 `state`）。**只有當條件成立（回傳 `wake: true`）時，才會真正喚醒 Session 消耗 Token 並主動向使用者發話！**
4. **無限對話不失憶的攔截層（Server Plugin Hooks & Instruction Entries）**
   - `ctx.session.hook("context")`：每次送出模型請求前動態注入 `xiaoqing-brain` 的關聯記憶。
   - `PUT /api/experimental/session/{sessionID}/instructions/entries/{key}`：動態掛載/更新 `<context key="...">` 狀態區塊（例如目前背景任務進度、今日待辦），不佔用對話輪次。
   - `ctx.session.hook("compaction")`：當永遠不關的單一 Session 累積過長觸發自動壓縮時，可由 Plugin 攔截並搭配 `xiaoqing-brain` 產生高品質結構化摘要，確保「單一窗口永遠聊下去也不爆 Context、不失憶」。
5. **主動插話與權限把關（Synthetic Message / Permission / Form API）**
   - `POST /api/session/{sessionID}/synthetic`：注入系統通知或環境事件到對話流中。
   - `GET /api/permission/request` 與 `POST /api/session/{sessionID}/permission/{requestID}/reply`：對標 Claude Duet 的「敏感操作先詢問（Ask before acting）」，背景任務遇到危險操作時可在主窗口跳出授權卡。

---

## 1. 競品標竿分析：Duet、Dots 與 Grok Bot 做對了什麼？

| 特性維度 | Claude Duet (Anthropic) | ChatGPT Dots (OpenAI) | Grok Bot (xAI) | 小晴常駐窗口（目標設計） |
| :--- | :--- | :--- | :--- | :--- |
| **互動入口** | 單一持續對話串（Ongoing thread），不再開新 Chat | 單一常駐分身（Dot），跨桌面/Web/Slack 共享同一脈絡 | 單一夥伴視窗，即時回應與背景執行 | **永遠固定一個 `Master Session`（小晴主窗口）**，使用者不需管專案與 Session ID |
| **主動性（Proactivity）** | 早晨簡報、每隔幾小時掃描信箱/行事曆、安靜話題自動追蹤 | 背景工作完成、卡關或需決策時主動傳訊通知 | 事件觸發與定時主動關心 | **雙軌主動引擎**：OpenCode 原生 `Schedule (if: shell/code)` + Server Plugin 事件監聽 |
| **任務與專案處理** | 擁有獨立雲端 VM，背景執行長任務後回報 Artifact | 聊天免費/輕量；重度任務在背景喚醒 Codex / Work 執行 | 背景 Agent 工具鏈呼叫 | **前店後廠模式**：主窗口負責陪伴、決策與輕量操作；重度開發動態 `move` 或派發背景 `Worker Session` |
| **長期記憶** | 綁定帳號全域記憶 + Skills + 連接器狀態 | 跨通道持久記憶，所有委派任務共享同一份認知 | 持續累積個人偏好與歷史脈絡 | **`xiaoqing-brain` (SQLite + LanceDB + BM25)** + `context` / `compaction` 雙向閉環 |
| **安全護欄** | 發信、付款、簽署、刪除前必須等待使用者點擊核准 | 獨立電腦邊界，敏感決策拉回主對話請求確認 | 本機/雲端權限分級 | 沿用 `AGENTS.md` 三級權限 + OpenCode Permission API 攔截確認 |

---

## 2. 系統整體架構設計：「前店後廠」單一窗口模型

為了實現「使用者永遠只面對一個窗口，卻能操控整台電腦的所有專案」，我們將架構分為四層：

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. 單一互動表現層 (Single-Window Presentation Layer)                    │
│    [方案 A: OpenCode Desktop / Web 釘選主 Session + GUI Plugin]          │
│    [方案 B: 自製極簡常駐浮動視窗 (Tauri/Electron/Web) 透過 @opencode/client] │
│    - 永遠綁定 Master Session ID (例如: ses_xiaoqing_master)              │
│    - 即時 SSE 串流 (client.event.subscribe)、系統匣常駐、主動通知彈出     │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │ HTTP API / SSE (/api/session, /api/event)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. OpenCode 2.3 背景常駐核心 (Shared Background Service Daemon)          │
│    - 單一 Master Session：承載所有日常對話、決策、主動問候、狀態彙報       │
│    - 內建實驗性排程器 (experimental.schedules)：Cron / Interval + 條件閘 │
│    - 內建動態目錄切換 (session.move)：輕量跨專案操作直接瞬移             │
│    - 背景 Worker Sessions：重度/平行專案任務由 Subagent 隔離執行         │
└─────────────────┬───────────────────────────────────┬───────────────────┘
                  │ Plugin Context API                │ MCP / Python CLI
                  ▼                                   ▼
┌───────────────────────────────────┐ ┌───────────────────────────────────┐
│ 3. 常駐管家插件 (xiaoqing-daemon) │ │ 4. 永續記憶核心 (xiaoqing-brain)  │
│  ~/.config/opencode/plugins/      │ │  C:/Users/User/xiaoqing/brain     │
│  - hook("context"): 自動記憶注入  │ │  - SQLite + LanceDB (Ollama 4096) │
│  - hook("compaction"): 無損壓縮   │ │  - 被動捕捉 (ingest) + 主動檢索   │
│  - hook("prompt") / "execute"     │ │  - 人物/專案/偏好/日記/記帳結構化 │
│  - 主動排程自舉註冊與狀態同步     │ │  - Master Session 錨點與跨日摘要  │
└───────────────────────────────────┘ └───────────────────────────────────┘
```

---

## 3. 四大核心機制詳細設計

### 3.1 機制一：單一窗口與「無專案感」路由（Project-Agnostic Routing）

使用者痛點是「每次要改 A 專案就要去 A 資料夾開 OpenCode，要改 B 專案又要開另一個視窗，記憶與對話全碎成一地」。

**解決方案：單一 Master Session + 兩級專案調度**

1. **固定主線（Pinned Master Session）**
   - 系統維護一個永久的 `master_session_id`（儲存在 `C:\Users\User\opencode\data\master_session.json` 與 Plugin `ctx.storage`）。
   - 預設大本營目錄設在 `C:\Users\User\opencode`（管家總部）。
2. **第一級調度：輕量跨專案「瞬移」（Session Move）**
   - 當使用者在主窗口說：「幫我看一下 `dk-vault` 裡面的最新設定」，小晴不需要叫使用者換視窗。
   - 小晴可直接讀取絕對路徑，或呼叫內建的 `tools.opencode.session_move({ directory: "C:/Users/User/CluadeCode/Projects/dk-vault" })`。
   - OpenCode V2 會在下一個安全邊界直接把當前這個 Session 的 Location 切換過去，載入該專案的 Git 狀態與參考，**但對話視窗與歷史紀錄完全保持連續**。操作完畢後可再 `session_move` 回總部。
3. **第二級調度：重度任務「後廠委派」（Background Worker Dispatch）**
   - 當使用者說：「幫我在 `project-x` 重構整個認證模組並跑完測試，弄好跟我說，我現在要跟你聊別的事。」
   - 小晴透過內建 `subagent` 工具（或自訂 Plugin 工具呼叫 `ctx.session.create({ directory: "project-x" })` + `ctx.session.prompt()`）在背景啟動一個 Worker Session。
   - Master Session 保持閒置可繼續跟主人聊天；當 Server Plugin 透過 `ctx.event.subscribe()` 監聽到該 Worker Session 觸發 `session.idle` 時，自動把結果透過 `ctx.session.synthetic()` 或 `ctx.session.prompt()` 推進 Master Session，小晴就會在主窗口主動說：「主人～剛剛交代的 `project-x` 認證重構已經跑完測試囉！這是摘要⋯⋯」

---

### 3.2 機制二：持續性長期記憶與「無限單一對話」防爆機制

如果永遠只用一個 Session，不出幾天 Context Window 就會爆滿；如果依賴預設的粗暴截斷，小晴就會忘記前幾天說過的話。

**解決方案：三層記憶注入 + 自訂無損壓縮（Compaction Hook）**

1. **Layer 0：動態狀態面板（Session Instruction Entries）**
   - 利用 OpenCode V2 內建的 `ctx.session.instructions.entry.put({ sessionID, key, value })`。
   - 插件在背景維護幾個固定 Key（不佔對話歷史，永遠置頂於 System Prompt 的 `<context key="...">`）：
     - `xiaoqing/status`：目前時間、當前所在專案目錄、正在背景執行的 Worker 任務清單。
     - `xiaoqing/core-memory`：主人核心偏好、近期重要待辦、今日記帳小計。
2. **Layer 1：回合前主動記憶檢索（`ctx.session.hook("context")`）**
   - **關鍵突破**：以前需要在 `AGENTS.md` 叮囑模型「記得先呼叫 `memory_get_context`」，模型有時會忘記，且多花一次 Tool Call 延遲。
   - 現在改在 Server Plugin 註冊 `ctx.session.hook("context", async (event) => { ... })`：
     - 當使用者送出新訊息時，Plugin 直接在送往 LLM 前，拿最後一則 User 訊息向 `xiaoqing-brain` 查詢 Top-3 相關記憶（BM25 / 向量混合）。
     - 直接注入 `event.system.push({ type: "text", text: "<recalled_memory>...</recalled_memory>" })`。
     - **零 Tool Call 延遲、100% 必觸發、不污染持久對話紀錄！**
3. **Layer 2：回合後被動記憶沉澱（現有 `xiaoqing-memory.js` 已打通）**
   - `prompt` hook + `tool.execute.after` hook + `session.idle` → `memory_ingest.py` → 濃縮寫入 SQLite 與 LanceDB。
4. **Layer 3：無限對話的「無損記憶換頁」（`ctx.session.hook("compaction")`）**
   - 在 `opencode.json` 開啟：
     ```jsonc
     "compaction": {
       "auto": true,
       "keep": { "tokens": 20000 },
       "buffer": "15%"
     },
     "experimental": {
       "background_compaction": true
     }
     ```
   - 同時在 Server Plugin 攔截 `ctx.session.hook("compaction")`：當觸發壓縮時，先確保被壓縮區段的細節已完整落入 `xiaoqing-brain`，並在壓縮摘要中保留「關鍵記憶索引 ID（Memory Anchor IDs）」。這樣就算對話持續一年，舊對話被壓縮成精簡摘要，小晴隨時都能透過記憶檢索把細節抓回來。

---

### 3.3 機制三：兼具主動性的「自我呼叫」引擎（Proactive Self-Invocation）

Claude Duet 最讓人驚豔的是：**「它不是等你開視窗問它，而是它在對的時間主動找你，沒事時保持安靜不燒 Token。」**

在 OpenCode v2.3.0 中，我們不需要再用外部笨重的 `powershell.exe opencode run`（舊版 `gateway` 做法），而是直接啟用 **OpenCode 原生 Schedule 引擎 + 條件閘（Condition Gate）**。

#### 啟用方式
在 `opencode.json` 加入：
```jsonc
"experimental": {
  "schedules": true
}
```

#### 運作原理（兩階段喚醒，極致省 Token）
當我們透過 `POST /api/experimental/schedule` 為 Master Session 註冊一個排程時，可以設定 `when` 與 `if`（Condition）：

1. **階段一：零成本靜默巡檢（`if` Condition Gate）**
   - 每當時間到（例如 `every: "30 minutes"` 或 `cron: "0 8 * * *"`），OpenCode Daemon **不會直接呼叫 LLM**，而是先執行 `if.run`（Shell 腳本）或 `if.code`（Code Mode JS，內建跨次記憶變數 `state`、`now`、`runs`）。
   - 例如：檢查某個背景任務是否完成、特定資料夾是否有新檔案、距離上次關心主人是否超過 4 小且主人正在電腦前、或是讀取待辦事項是否有到期項目。
   - 如果沒事發生，腳本回傳 `{ wake: false, state: newState }` → **直接結束，消耗 0 Token，主窗口完全不跳無意義的廢話！**
2. **階段二：有事才真正喚醒小晴（Session Wake & Proactive Message）**
   - 一旦巡檢發現有值得報告的事，回傳 `{ wake: true, state: newState, message: "偵測到具體事件摘要..." }`。
   - OpenCode Daemon 會自動將 `prompt + message` 送入 Master Session！
   - 小晴被喚醒後，根據情境生成貼心的訊息，直接顯示在主窗口上（並觸發桌面 Toast / 音效通知）。

#### 內建四大主動場景設計

| 排程名稱 | 觸發時間 (`when`) | 條件閘 (`if`) | 喚醒後的行為 (`prompt`) |
| :--- | :--- | :--- | :--- |
| **1. 晨間簡報 (Morning Brief)** | `cron: "0 8 * * *"` (`Asia/Taipei`) | 檢查今日是否尚未發送過早安，並預先抓取昨日日記摘要與今日待辦 | 主動在窗口向主人道早安，整理昨天進度與今天建議關注的事項 |
| **2. 智慧靜默巡檢 (Smart Pulse)** | `every: "30 minutes"` | 執行輕量腳本檢查：(a) 背景 Worker 是否剛完工 (b) 系統磁碟/異常告警 (c) 主人設定的監控項目是否有變化 (`changes: true`) | 僅在有實質事件時主動插話彙報；若無變化則 `wake: false` 完全靜默 |
| **3. 自我排程跟進 (Self-Scheduled Follow-up)** | `in: "2 hours"` 或 `at: "ISO時間"` | 無條件或檢查目標狀態 | **由小晴自己在對話中決定呼叫！** 例如主人說「兩小時後提醒我看烤箱」或小晴自己判斷「我半小時後再幫你確認部署狀態」，小晴直接呼叫工具建立一次性 Schedule 自我喚醒 |
| **4. 夜間沉澱與反思 (Nightly Reflection)** | `cron: "30 23 * * *"` | 檢查今日是否有新增對話記憶 | 自動整理今日 `diary` 與 Knowledge Wiki 更新，靜默寫入記憶庫 |

> 💡 **赋予小晴「自我預約喚醒」的能力**：
> 我們可以在 Server Plugin 中用 `ctx.tool.transform()` 註冊一個專屬工具 `xiaoqing_schedule_self({ when, condition, remind_prompt })`，內部直接轉發給 `/api/experimental/schedule`。這樣小晴在任何對話中，都能**完全自主地設定未來的鬧鐘來呼叫自己**！

---

### 3.4 機制四：使用者面對的「唯一窗口」UI 方案選擇

既然底層的 Master Session、記憶與主動喚醒都已經在 OpenCode 2.3 背景 Daemon 中完美閉環，那麼使用者眼睛看到的「那個唯一窗口」有哪些實作方式？我們規劃了由輕到重的三個演進階段：

#### 方案 A：零前端開發 — 直接改造 OpenCode Desktop / Web（立即可用）
- **做法**：
  1. 利用 OpenCode 2.3 的 **GUI Plugin（`@opencode/plugin/gui`）** 與 **TUI Plugin**。
  2. 在 Titlebar 加入一個「☀️ 小晴主窗口（一鍵回到 Master Session）」按鈕與狀態指示燈（`TitlebarItem` / `ComposerPill`）。
  3. 啟動時自動釘選並鎖定在 `Master Session`，隱藏繁瑣的專案切換概念。
  4. 當背景排程喚醒 Master Session 時，利用 GUI Plugin 的 `main(ctx)`（Electron 主行程權限）發送 Windows 原生系統通知（System Notification / Beep）並將視窗帶到前景。
- **優點**：100% 沿用 OpenCode 強大的 Markdown、Diff、Artifact 預覽、內建瀏覽器與權限核准 UI，開發成本極低。

#### 方案 B：輕量專屬伴侶視窗 — 獨立 Web / PWA 或 Tauri 桌面浮動窗（最像 Claude Duet / ChatGPT Companion）
- **做法**：
  1. 寫一個極簡、漂亮的單頁應用（或透過 `webview` / Tauri 打包成可隨時 `Alt + Space` 呼出的桌面常駐小視窗）。
  2. 底層直接使用官方 `@opencode/client` 與 `@opencode/client/service`：
     - 啟動時呼叫 `Service.ensure()` 連上本機 OpenCode Daemon。
     - 讀取固定的 `master_session_id`（若無則建立一個）。
     - 透過 `client.event.subscribe()` 即時渲染小晴的打字串流、工具執行狀態、以及排程主動推播過來的訊息。
     - 當遇到需要審批的操作時，訂閱 `permission.asked` 事件，在對話框直接渲染「✅ 允許 / ❌ 拒絕」按鈕（呼叫 `POST /api/session/{sessionID}/permission/{requestID}/reply`）。
- **優點**：視覺體驗完全為「個人管家」量身打造，沒有任何多專案、多 Session 清單的干擾，真正做到「一打開就是小晴」。

---

## 4. 新舊架構對比（為什麼這次不會像舊 Gateway 一樣笨重？）

| 比較項目 | 舊版 `opencode/gateway`（已停用） | 新版 OpenCode 2.3 原生常駐架構（本規劃） |
| :--- | :--- | :--- |
| **呼叫方式** | `spawn('powershell.exe', ['opencode run --session ...'])` | 常駐 Daemon 內部執行 + HTTP API / `@opencode/client` |
| **冷啟動延遲** | 每次喚醒都要重啟 Node/CLI 與 MCP Server（耗時數秒至十幾秒） | Daemon 與 MCP (`xiaoqing-brain`) 永遠保持 Warm，毫秒級響應 |
| **主動排程耗能** | 時間到就無腦呼叫 LLM，沒事也燒 Token、產出空洞日記 | 原生 `Schedule` 支援 `if`（Shell/JS 條件閘），**有事才喚醒 LLM** |
| **視窗同步** | 背景跑 `opencode run` 時，前台介面看不到即時過程或容易鎖死 | 所有端點共用單一 Daemon 的 SSE 事件流，背景主動說話前台即時浮現 |
| **記憶注入** | 靠腳本硬拼字串塞進 Prompt 頭部，污染使用者訊息結構 | 透過 `ctx.session.hook("context")` 乾淨注入 System 層，並支援自動無損 `compaction` |

---

## 5. 分階段落地實作藍圖（Implementation Roadmap）

我們不需要一次重寫所有東西，可以分三個 Phase 漸進式上線：

### Phase 1：核心常駐化與單一 Master Session 鎖定（後端與插件層）
1. **更新 `opencode.json` 設定**：
   - 開啟 `"experimental": { "schedules": true, "background_compaction": true }`。
   - 設定 `"compaction": { "auto": true, "keep": { "tokens": 20000 }, "buffer": "15%" }`。
2. **升級 `~/.config/opencode/plugins/xiaoqing-memory.js` 為完整管家插件 `xiaoqing-companion.js`**：
   - **Master Session 錨定**：固定一個主 Session ID（記錄於 `C:/Users/User/opencode/data/master_session.json`）。
   - **自動記憶注入 Hook**：實作 `ctx.session.hook("context")`，每次對話前自動從 `xiaoqing-brain` 檢索相關記憶注入 System Prompt，不再依賴模型記得呼叫 MCP。
   - **無損壓縮 Hook**：實作 `ctx.session.hook("compaction")`，確保單一 Session 無限對話不失憶。
   - **動態狀態看板**：利用 `ctx.session.instructions.entry.put` 即時更新當前時間、工作目錄與背景任務狀態。

### Phase 2：賦予「主動自我呼叫」與「後廠背景委派」能力
1. **封裝自我排程工具（Self-Scheduling Tools）**：
   - 在插件中透過 `ctx.tool.transform` 新增 Direct Tools：
     - `schedule_wakeup`：讓小晴可以在對話中幫自己設鬧鐘或條件監聽（對接 `/api/experimental/schedule`）。
     - `list_schedules` / `cancel_schedule`：管理自己的排程。
     - `delegate_project_task`：在指定專案目錄開啟背景 Worker Session 執行任務，並在完成時自動透過 `synthetic` / `prompt` 回報給 Master Session。
2. **設定預設主動巡檢排程**：
   - 註冊含 `if` 條件閘的晨間簡報與靜默狀態巡檢（預設可透過設定檔一鍵開關，完全受控）。

### Phase 3：單一常駐窗口介面（Single-Window Companion UI）
1. **快速驗證版（Web / Desktop 單一窗口）**：
   - 建立一個輕量本機常駐頁面（或 Desktop 捷徑），透過 `@opencode/client` 直接綁定 `Master Session`。
   - 支援流式對話、主動推播通知（Web Notification / Windows Toast）、權限核准按鈕（Approve / Reject）、以及側邊欄顯示「目前背景執行的專案任務」與「小晴記憶狀態」。

---

## 6. 風險評估與應對措施

1. **`experimental.schedules` 與 `instructions.entries` 屬於 Experimental API**
   - **風險**：OpenCode 未來小版本升級可能調整欄位名稱。
   - **應對**：將所有對 Experimental API 的呼叫封裝在單一 Adapter 模組中（不到 100 行程式碼）。就算未來 API 微調，只需改這一個檔案。
2. **主動喚醒造成的 Token 消耗或打擾失控**
   - **風險**：排程太頻繁或條件沒寫好，導致小晴一直自言自語。
   - **應對**：
     1. 嚴格遵守「先跑 `if`（Shell/JS 零成本檢查），有變化才 `wake: true`」原則。
     2. 設定每日主動喚醒次數上限（Rate Limit）與「勿擾時段（Do Not Disturb，如 00:00 - 07:30）」。
     3. 提供一鍵靜音指令（例如對小晴說 `/quiet` 或切換開關即可暫停所有 Schedule）。
3. **單一 Session 跨專案操作時的檔案路徑混淆**
   - **風險**：在總部目錄下直接改其他專案的檔案，相對路徑可能指錯。
   - **應對**：在 `context` hook 的狀態面板中永遠明確標示當前 `cwd`；跨專案輕量操作優先使用絕對路徑或 `session_move`，重度修改一律派發給綁定該專案目錄的 Worker Session。
