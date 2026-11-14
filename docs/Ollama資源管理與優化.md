# Ollama / GPU 資源管理與優化記錄

**日期**：2026-11-14
**硬體**：NVIDIA GeForce RTX 5070 Ti（16,303 MiB VRAM）、AMD Ryzen 7 9800X3D（8C/16T）、63.65 GB RAM、C 槽 1.9 TB（可用 750 GB）
**Ollama**：0.40.16，服務端點 `http://127.0.0.1:11434`
**模型磁碟佔用**：15.36 GB（qwen3.5:9b 6.14 GB、qwen3:8b 4.87 GB、qwen3-embedding 4.36 GB）

---

## 一、結論：為什麼是「服務常駐 + 模型自動卸載」

| 方案 | 實測成本 | 結論 |
|---|---|---|
| **服務完全常駐** | 101 MB RAM（serve 54 + app 46）、CPU 0.15%、38 分鐘累積 3.2 秒 CPU | ✅ **採用**。成本低到不值得為它做按需啟動 |
| **按需啟動整個服務** | 每次數秒啟動延遲；且服務會隨 agent shell 的 Job Object 一起死，得靠 `wscript.exe` 脫離式啟動 | ❌ 收益（101 MB）遠小於風險 |
| **模型永久常駐**（keep_alive=-1） | 永久吃掉 10.54 GB VRAM，把 16 GB 卡剩餘空間砍到 3.8 GB | ❌ Ollama 本來就會自動卸載，沒理由手動釘住 |
| **混合方案** | 服務常駐 + 模型 keep_alive 120 秒後自動卸載 + num_ctx 下修 | ✅ **最終採用** |

### 記憶系統對 Ollama 的依賴度

```
opencode_adapter.on_user_message()
  ├─ BM25 pre-check（SQLite + BM25）              ← 不需要 Ollama ✅
  ├─ compression.process()（LLM，走 MiniMax API）  ← 不需要 Ollama ✅
  └─ retriever.add_memory()
       └─ hybrid.add_memory()
            ├─ lancedb.add() → _embed() → POST /api/embeddings  ← ★ 唯一需要 Ollama 的點
            ├─ sqlite.add() / markdown.add() / bm25.add()        ← 不需要 ✅
```

- `memory_context_fast.py`（每回合自動注入的記憶雷達）**完全不需要 Ollama** → 就算 Ollama 關掉，雷達照常運作
- `hybrid.py` 的檢索與寫入**兩條路徑都有降級**（try/except → 退回純 BM25）→ Ollama 掛掉不會讓記憶遺失

---

## 二、關鍵優化：num_ctx 下修（零品質風險）

`qwen3-embedding:latest` 的 `qwen3.context_length = 40960` 燒在模型裡，llama.cpp 會依此配置 KV cache 與 compute buffer。
但記憶是短文字，40960 完全用不到。

| num_ctx | VRAM (size_vram) | nvidia-smi 實測 | llama-server Private | 冷啟動 |
|---|---|---|---|---|
| 40960（預設） | 10.54 GB | 12,152 MiB | 12,363 MB | 2,241 ms |
| **2048（採用）** | **5.05 GB** | **~7,600 MiB** | **6,669 MB** | 1,908 ms |
| 1024 | 4.70 GB | 6,184 MiB | 6,141 MB | 2,684 ms |

**正確性驗證**（同一段文字）：
```
cos(ctx2048, ctx40960) = 1.0000000000   maxdiff = 0.000e+00
cos(ctx1024, ctx40960) = 1.0000000000   maxdiff = 0.000e+00
```
✅ **向量逐位元相同**，零品質風險，省下約 5.5 GB VRAM + 5.7 GB RAM。

### 實作位置

| 檔案 | 變更 |
|---|---|
| `utils/llm_backend.py` | `OllamaBackend.embeddings(model, prompt, **kwargs)` 支援 `options` 與 `keep_alive` 透傳 |
| `storage/lancedb.py` | 新增 `EMBED_OPTIONS = {"num_ctx": EMBED_NUM_CTX}`、`EMBED_KEEP_ALIVE`；`_embed()` 帶上這兩個參數 |
| `.env` | `XIAOQING_EMBED_NUM_CTX=2048`、`XIAOQING_EMBED_KEEP_ALIVE=120` |
| `opencode.json` (mcp.servers.xiaoqing-brain.environment) | 同上兩個變數（優先於 .env） |

> ⚠️ **keep_alive 要明確指定**：Ollama API 請求層的預設是 5 分鐘，會蓋過伺服器端設定的 `OLLAMA_KEEP_ALIVE=2m`。
> 所以程式裡直接傳 `keep_alive=120`，不依賴伺服器環境變數。
> ⚠️ **不要設 keep_alive=0**：寫入模式是「一批 1–6 筆連續寫入」，keep_alive=0 會讓每一筆都重新載入模型（+2.2 秒 × 6 筆 = +13 秒）。

---

## 三、修正的三個 Bug

### BUG #1 — MCP stdout 污染（🔴 最重要）

`mcp_server.py` 與 hook 在**同一個行程**內執行，但 hook 裡的 `print()` 沒有 `file=sys.stderr`，
會寫進 MCP 的 JSON-RPC stdout 通道。

**因果鏈**：Ollama 掛掉 → 向量寫入失敗 → 走 `hybrid.py` 的降級路徑 → `print()` 污染 stdout → **MCP 連線層出錯**。

```
opencode.log: Invalid MCP stdio message from xiaoqing-brain:
  SyntaxError: JSON Parse error: Unexpected identifier "HybridRetriever"
```
修復前累積 **19 次**（11/13：16 次、11/14：3 次）。

**修法**：以下檔案的 `print()` 全部補上 `file=sys.stderr`：
`retrieval/hybrid.py`、`hooks/opencode_adapter.py`、`hooks/base.py`、`storage/lancedb.py`、
`retrieval/intent.py`、`stages/compression.py`、`stages/synthesis.py`

### BUG #2 — `pulse_check.check_vector_drift()` 是死碼（🟠）

`pulse_check.py` 由 `pulse_check.cmd` 執行 → Python 只把 `scripts/` 放進 `sys.path[0]`，
而 `brain` 套件在上一層 → `from brain.storage.lancedb import ...` 永遠 ImportError，
又被 `except Exception: pass` 靜默吞掉。

→ **「向量庫不同步」的警示從來沒有生效過。**

**修法**：`pulse_check.py` 開頭補 `sys.path.insert(0, PROJECT_ROOT)`。

### BUG #3 — 儲存層使用相對路徑（🟠）

`SQLiteStorage(db_path="./data/memories.db")` 與 `LanceDBStorage(db_path="./data/lancedb")`
綁定 **CWD**。目前靠 `opencode.json` 的 `"cwd": "C:/Users/User/xiaoqing/brain"` 釘住，
但從其他目錄執行就會開出一個空庫。

**修法**：改用 `XIAOQING_DATA_DIR`（已設定）拼出絕對路徑，預設 fallback 到 `brain/data/`。

---

## 四、Ollama 啟動方式整理（消除埠競爭）

### 問題
Startup 資料夾同時有兩個機制搶 11434 埠：
- `Ollama.lnk`（2026/2/22，→ `ollama app.exe`）— App 自己會帶起 `ollama serve`
- `Ollama_Serve.vbs`（2026/11/14 10:22，我們放的）— 也直接跑 `ollama serve`

`server.log` 因此出現一串 `listen tcp 0.0.0.0:11434: bind: Only one usage of each socket address`。

### 解法
- 刪除 `Ollama.lnk` 與舊的 `Ollama_Serve.vbs`
- 統一改用 **`Ollama_App.vbs`**（單一進入點）：

```vbs
Set shell = CreateObject("WScript.Shell")
Set env = shell.Environment("PROCESS")
env("OLLAMA_MAX_LOADED_MODELS") = "1"
env("OLLAMA_KEEP_ALIVE") = "2m"
shell.Run """C:\Users\User\AppData\Local\Programs\Ollama\ollama app.exe""", 0, False
```

> **為什麼用 App 而不是直接 `ollama serve`**：App 自己會把 server 帶起來，兩者一起跑才會搶埠。
> 環境變數在 VBS 的 PROCESS scope 設定 → App 繼承 → App 啟動的 server 再繼承 → 全部生效。

### 環境變數設定（User scope）
| 變數 | 值 | 理由 |
|---|---|---|
| `OLLAMA_MAX_LOADED_MODELS` | `1` | 明確限制同時只載 1 個模型，VRAM 上限可控（原本 `0` = 自動推算，可能同時載兩個爆卡） |
| `OLLAMA_KEEP_ALIVE` | `2m` | 模型閒置 2 分鐘自動卸載 |
| `OLLAMA_HOST` | `0.0.0.0`（既有） | ⚠️ 區域網其他裝置可連到 11434。若只想本機用，改為 `127.0.0.1` |

### 重啟驗證
```
server.log: OLLAMA_KEEP_ALIVE:2m0s   OLLAMA_MAX_LOADED_MODELS:1
           vram-based default context  total_vram="15.9 GiB"  default_num_ctx=4096
bind 錯誤數：0 ✅
VRAM 峰值：12152 MiB → ~7600 MiB ✅
```

---

## 五、實測延遲參考

| 操作 | 耗時 |
|---|---|
| embedding 冷啟動（模型載入 + 推論） | 2,241 ms（num_ctx=40960）/ 1,908 ms（2048） |
| embedding 熱載入推論 | **39 ms** |
| embedding 熱載入 + `keep_alive=0`（含卸載） | 39 ms，< 3 秒內 VRAM 回到基線 |
| qwen3.5:9b 冷啟動 + generate | 34,588 ms（ctx=131072 的 KV cache 龐大所致） |

---

## 六、未來可考慮

1. `OLLAMA_CONTEXT_LENGTH=131072` 是 Ollama App 的設定，對 9b 有效（也是 34 秒冷啟動的原因）。
   若主人常用 9b 做長文推理，可另外評估。
2. `qwen3:8b`（4.87 GB）與 `qwen3.5:cloud` 目前沒有任何流程使用 → 可考慮移除以省磁碟。
3. `OLLAMA_HOST=0.0.0.0` 對外開放，若不需要區域網存取建議收成 `127.0.0.1`。

---

*記錄於 2026-11-14 ｜ 完整原始調查報告由 GPU 調查 worker 產出*
