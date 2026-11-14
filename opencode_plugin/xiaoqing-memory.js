// xiaoqing-memory — OpenCode 2.x 常駐型單一窗口管家核心插件 (Companion & Memory V2)
//
// 四大核心能力：
//   1. 【主動記憶注入 (`ctx.session.hook("context")`)】
//      每次對話送往 LLM 前，自動呼叫 `memory_context_fast.py` (BM25 + 核心認知 < 300ms)，
//      將相關記憶與「主動寫入/翻新雷達指令」無縫注入 System 層，完全不再依賴模型自覺先查 MCP！
//   2. 【無限單一窗口不失憶 (`ctx.session.hook("compaction")`)】
//      當單一 Master Session 累積過長觸發自動壓縮時，自動將被壓縮片段落地到 `xiaoqing-brain` 並注入核心記憶錨點。
//   3. 【被動記憶捕捉與自動翻新 (`prompt` + `tool.execute.after` + `session.idle`)】
//      使用者訊息與關鍵工具操作在回合結束時自動批次送入 `memory_ingest.py`，並自動比對舊記憶進行翻新（Supersede）。
//   4. 【單一主窗口錨定、自我排程喚醒與跨專案後廠委派 (`ctx.tool.transform` + `ctx.command.transform`)】
//      - 提供 Direct Tools：
//        * `xiaoqing_wakeup_schedule`: 讓小晴自己設定鬧鐘/定時/條件排程，打給未來的自己起床！
//        * `xiaoqing_wakeup_list` / `xiaoqing_wakeup_manage`: 檢視、暫停、恢復、刪除自己的排程。
//        * `xiaoqing_delegate_project`: 前店後廠模式，在指定專案資料夾建立背景子 Session 施工，完成後自動回報主窗口。
//        * `xiaoqing_master_window`: 綁定或查看常駐主窗口 (Master Session)。
//      - 提供 Slash Commands：`/xiaoqing`、`/wakeup`、`/master`

import { mkdir, writeFile, readFile, unlink } from "node:fs/promises";
import { existsSync, readFileSync } from "node:fs";
import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";

const BRAIN_DIR = "C:/Users/User/xiaoqing/brain";
const PYTHON = `${BRAIN_DIR}/venv/Scripts/python.exe`;
const INGEST_SCRIPT = `${BRAIN_DIR}/scripts/memory_ingest.py`;
const FAST_CONTEXT_SCRIPT = `${BRAIN_DIR}/scripts/memory_context_fast.py`;
const INBOX_DIR = `${BRAIN_DIR}/data/.ingest`;
const MASTER_STATE_FILE = "C:/Users/User/opencode/data/master_session.json";

const MEANINGFUL_TOOLS = new Set([
  "edit",
  "write",
  "bash",
  "shell",
  "task",
  "subagent",
  "skill",
  "xiaoqing_wakeup_schedule",
  "xiaoqing_delegate_project",
]);

const MAX_TEXT = 4000;
const MAX_RESULT = 2000;
const MAX_ARG = 500;

const truncate = (value, max) => {
  const str = typeof value === "string" ? value : JSON.stringify(value ?? "");
  if (!str) return "";
  return str.length > max ? `${str.slice(0, max)}...[truncated]` : str;
};

const sanitizeArgs = (args) => {
  if (args === null || args === undefined) return {};
  if (typeof args !== "object") return { value: truncate(args, MAX_ARG) };
  const out = {};
  for (const [key, value] of Object.entries(args)) {
    out[key] = truncate(value, MAX_ARG);
  }
  return out;
};

const toolResultText = (result) => {
  if (!result) return "";
  if (typeof result.content === "string") return result.content;
  if (Array.isArray(result.content)) {
    return result.content
      .map((item) => (typeof item === "string" ? item : (item?.text ?? item?.type ?? "")))
      .filter(Boolean)
      .join("\n");
  }
  if (typeof result.output === "string") return result.output;
  return truncate(result.output, MAX_RESULT);
};

const sessionIDOf = (event) => {
  const data = event?.data ?? event?.properties ?? {};
  return data?.sessionID ?? event?.sessionID ?? null;
};

const isIdleEvent = (event) => {
  if (event?.type === "session.idle") return true;
  if (event?.type === "session.status") {
    const status = event?.data?.status ?? event?.properties?.status;
    return status?.type === "idle";
  }
  return false;
};

/** 讀取本機 OpenCode 背景 Daemon 連線資訊（供 Schedule HTTP API 呼叫） */
function resolveLocalDaemonEndpoint() {
  try {
    const home = os.homedir();
    const candidates = [
      path.join(home, ".local", "state", "opencode", "service.json"),
      "C:/Users/User/.local/state/opencode/service.json",
    ];
    for (const file of candidates) {
      if (existsSync(file)) {
        const info = JSON.parse(readFileSync(file, "utf8"));
        if (info?.url && info?.password) {
          const auth = Buffer.from(`opencode:${info.password}`).toString("base64");
          return {
            baseUrl: info.url.replace(/\/$/, ""),
            headers: {
              "Content-Type": "application/json",
              Authorization: `Basic ${auth}`,
            },
          };
        }
      }
    }
  } catch (err) {
    console.error(`[xiaoqing-companion] 讀取 service.json 失敗: ${err?.message ?? err}`);
  }
  return null;
}

/** 呼叫 OpenCode Local Daemon API */
async function callDaemonApi(method, apiPath, body = undefined) {
  const endpoint = resolveLocalDaemonEndpoint();
  if (!endpoint) {
    throw new Error("找不到本機 OpenCode Daemon 註冊資訊 (service.json)");
  }
  const url = `${endpoint.baseUrl}${apiPath}`;
  const res = await fetch(url, {
    method,
    headers: endpoint.headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return { ok: true };
  const text = await res.text();
  let json;
  try {
    json = JSON.parse(text);
  } catch {
    json = { raw: text };
  }
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${json?.message || text}`);
  }
  return json?.data !== undefined ? json.data : json;
}

/** 讀寫常駐主窗口 (Master Session) 狀態檔 */
async function readMasterState() {
  try {
    if (existsSync(MASTER_STATE_FILE)) {
      const raw = await readFile(MASTER_STATE_FILE, "utf8");
      return JSON.parse(raw);
    }
  } catch {}
  return { masterSessionID: null, updatedAt: null, homeDirectory: "C:/Users/User/opencode" };
}

async function writeMasterState(patch) {
  const current = await readMasterState();
  const next = {
    ...current,
    ...patch,
    updatedAt: new Date().toISOString(),
  };
  await mkdir(path.dirname(MASTER_STATE_FILE), { recursive: true });
  await writeFile(MASTER_STATE_FILE, JSON.stringify(next, null, 2), "utf8");
  return next;
}

/** 執行 Python 快速記憶檢索 (< 350ms) */
function queryFastMemoryContext(queryText, topK = 5) {
  return new Promise((resolve) => {
    const child = spawn(PYTHON, [FAST_CONTEXT_SCRIPT, queryText || "", String(topK)], {
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
    let out = "";
    const timer = setTimeout(() => {
      child.kill();
      resolve(null);
    }, 2500);
    child.stdout?.on("data", (chunk) => {
      out += chunk.toString("utf8");
    });
    child.on("error", () => {
      clearTimeout(timer);
      resolve(null);
    });
    child.on("close", () => {
      clearTimeout(timer);
      try {
        // 過濾掉 jieba 載入訊息，只取最後一行 JSON
        const lines = out
          .split(/\r?\n/)
          .map((l) => l.trim())
          .filter((l) => l.startsWith("{") && l.endsWith("}"));
        if (lines.length > 0) {
          resolve(JSON.parse(lines[lines.length - 1]));
          return;
        }
      } catch {}
      resolve(null);
    });
  });
}

/** 從 context hook 的 messages 陣列提取最新一則使用者輸入文字 */
function extractLatestUserQuery(messages) {
  if (!Array.isArray(messages)) return "";
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (msg?.role === "user" || msg?.type === "user") {
      if (typeof msg.text === "string" && msg.text.trim()) return msg.text.trim();
      if (typeof msg.content === "string" && msg.content.trim()) return msg.content.trim();
      if (Array.isArray(msg.content)) {
        const text = msg.content
          .map((part) => (typeof part === "string" ? part : (part?.text ?? "")))
          .filter(Boolean)
          .join("\n")
          .trim();
        if (text) return text;
      }
    }
  }
  return "";
}

export default {
  id: "xiaoqing-memory",

  async setup(ctx) {
    if (typeof ctx?.session?.hook !== "function" || typeof ctx?.event?.subscribe !== "function") {
      console.error("[xiaoqing-companion] ctx API 不完整，略過註冊");
      return () => {};
    }

    /** sessionID -> event[] (待寫入記憶佇列) */
    const pending = new Map();
    const inFlight = new Set();
    /** sessionID -> 最新一則使用者原始訊息 (供快取檢索與狀態更新) */
    const latestPromptBySession = new Map();
    /** sessionID -> { timestamp, blockText } 短期檢索快取，避免同一輪多步 tool call 重複 spawn Python */
    const memoryCacheBySession = new Map();

    const enqueue = (sessionID, event) => {
      if (!sessionID) return;
      const list = pending.get(sessionID) || [];
      list.push(event);
      pending.set(sessionID, list);
    };

    const flush = async (sessionID) => {
      if (!sessionID || inFlight.has(sessionID)) return;
      const events = pending.get(sessionID);
      if (!events || events.length === 0) return;
      pending.delete(sessionID);
      inFlight.add(sessionID);

      const stamp = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const file = `${INBOX_DIR}/${stamp}.json`;

      try {
        await mkdir(INBOX_DIR, { recursive: true });
        await writeFile(file, JSON.stringify(events, null, 2), "utf8");

        await new Promise((resolve) => {
          const child = spawn(PYTHON, [INGEST_SCRIPT, file], {
            stdio: ["ignore", "pipe", "pipe"],
            windowsHide: true,
          });
          let out = "";
          let err = "";
          child.stdout?.on("data", (chunk) => {
            out += chunk.toString();
          });
          child.stderr?.on("data", (chunk) => {
            err += chunk.toString();
          });
          child.on("error", (error) => {
            err += String(error);
            resolve(-1);
          });
          child.on("close", (code) => {
            const stdout = out.trim();
            if (stdout) console.log(`[xiaoqing-companion] ${stdout}`);
            if (code !== 0) {
              console.error(`[xiaoqing-companion] ingest 失敗 (exit=${code}): ${err.trim().slice(0, 800)}`);
            }
            resolve(code);
          });
        });
        // 寫入新記憶後清除該 session 的快取，確保下一輪讀到最新記憶
        memoryCacheBySession.delete(sessionID);
      } catch (error) {
        console.error(`[xiaoqing-companion] flush 失敗: ${error?.message ?? error}`);
      } finally {
        inFlight.delete(sessionID);
        await unlink(file).catch(() => {});
      }
    };

    // =========================================================================
    // 1) Prompt Admission Hook：記錄使用者訊息 + 自動綁定第一個互動的主窗口
    // =========================================================================
    await ctx.session.hook("prompt", async (event) => {
      try {
        const text = event?.prompt?.text ?? "";
        const sessionID = event?.sessionID;
        if (!sessionID || !text || !text.trim()) return;

        latestPromptBySession.set(sessionID, text.trim());
        // 新的一輪使用者發話，強制刷新記憶檢索快取
        memoryCacheBySession.delete(sessionID);

        // 若尚未綁定 Master Session，自動將當前根對話設為預設主窗口
        const masterState = await readMasterState();
        if (!masterState.masterSessionID) {
          await writeMasterState({ masterSessionID: sessionID });
        }

        enqueue(sessionID, {
          event_type: "user_message",
          session_id: sessionID,
          arguments: { message: truncate(text, MAX_TEXT) },
        });
      } catch (error) {
        console.error(`[xiaoqing-companion] prompt hook 失敗: ${error?.message ?? error}`);
      }
    });

    // =========================================================================
    // 2) Context Hook：0 延遲自動記憶注入 + 主動寫入/翻新雷達指令
    // =========================================================================
    await ctx.session.hook("context", async (event) => {
      try {
        const sessionID = event?.sessionID;
        if (!sessionID || !Array.isArray(event?.system)) return;

        const now = Date.now();
        const cached = memoryCacheBySession.get(sessionID);
        let injectedText = "";

        if (cached && now - cached.timestamp < 30_000) {
          injectedText = cached.blockText;
        } else {
          const query = latestPromptBySession.get(sessionID) || extractLatestUserQuery(event?.messages) || "";
          const memData = await queryFastMemoryContext(query, 5);
          const masterState = await readMasterState();
          const isMaster = masterState.masterSessionID === sessionID;

          const lines = [
            `<xiaoqing-companion-radar session="${sessionID}" is_master_window="${isMaster}">`,
            `## 🧠 小晴常駐管家 — 自動記憶與主動排程雷達（系統自動注入）`,
            `現在時間：${new Date().toLocaleString("zh-TW", { timeZone: "Asia/Taipei", hour12: false })} (Asia/Taipei)`,
            `目前工作目錄：${ctx.location?.directory || "未知"}`,
            `常駐主窗口 Session ID：${masterState.masterSessionID || sessionID}`,
          ];

          if (memData?.ok) {
            lines.push(
              `記憶庫狀態：有效記憶 ${memData.stats?.active_total ?? 0} 筆｜今日新增 ${memData.stats?.today_count ?? 0} 筆`
            );

            if (Array.isArray(memData.recalled) && memData.recalled.length > 0) {
              lines.push(`\n### 🔍 與當前話題最相關的歷史記憶（已自動檢索，無需再呼叫 memory_get_context）：`);
              for (const item of memData.recalled) {
                lines.push(
                  `- **[ID:${item.id}]** [${item.topic}] (${item.time_ago}) ${item.text}`
                );
              }
            }

            if (Array.isArray(memData.core) && memData.core.length > 0) {
              lines.push(`\n### 📌 主人核心偏好與近期重要決策：`);
              for (const item of memData.core) {
                lines.push(`- **[ID:${item.id}]** [${item.topic}] (${item.time_ago}) ${item.text}`);
              }
            }
          }

          lines.push(
            `\n### ⚡ 小晴的主動記憶與自我呼叫守則（極重要）：`,
            `1. **【遇到重點主動寫入】**：當主人在對話中做出**新決定、確立架構、交代長期規則、透露個人偏好**時，除了回答問題外，請主動透過 \`execute\` 呼叫 \`tools["xiaoqing-brain"].memory_add({ session_id: "${sessionID}", content: "..." })\` 立即固化重點！`,
            `2. **【發現舊記憶過時主動翻新】**：若上方檢索出的記憶 \`[ID:xxxxxxxx]\` 與主人最新說法、最新設定或現況衝突（例如設定改了、決定變了），請**主動呼叫 \`tools["xiaoqing-brain"].memory_refresh({ old_memory_id: "xxxxxxxx", new_content: "最新完整狀態...", topic: "..." })\`** 將舊記憶翻新取代，絕不留過期資訊！`,
            `3. **【主動打電話給未來的自己（自我排程）】**：當主人提到「之後提醒我、幾點叫我、幫我盯著某件事、定期檢查」，或妳自己覺得「這件事我應該過一陣子再主動跟進確認」時，請直接呼叫 \`xiaoqing_wakeup_schedule\`（或 Code Mode 的 \`tools.opencode.schedule_create\`）為自己設定鬧鐘或條件式排程！`,
            `4. **【單一窗口跨專案】**：主人只面對妳這個窗口。輕量跨專案讀寫請直接用絕對路徑或 \`tools.opencode.session_move\`；耗時開發任務請用 \`xiaoqing_delegate_project\` 或 \`subagent\` 派去背景跑，完成後再向主人報告。`,
            `</xiaoqing-companion-radar>`
          );

          injectedText = lines.join("\n");
          memoryCacheBySession.set(sessionID, { timestamp: now, blockText: injectedText });
        }

        if (injectedText) {
          event.system.push({ type: "text", text: injectedText });
        }
      } catch (error) {
        console.error(`[xiaoqing-companion] context hook 失敗: ${error?.message ?? error}`);
      }
    });

    // =========================================================================
    // 3) Compaction Hook：單一窗口無限對話防失憶（壓縮前自動將重點寫入記憶庫）
    // =========================================================================
    await ctx.session.hook("compaction", async (event) => {
      try {
        const sessionID = event?.sessionID;
        if (!sessionID) return;
        console.log(`[xiaoqing-companion] 觸發 Session Compaction (${sessionID})，正在強制同步未落地記憶...`);
        await flush(sessionID);

        if (Array.isArray(event?.system)) {
          event.system.push({
            type: "text",
            text: [
              "【小晴常駐窗口 Compaction 指示】",
              "這是一個永遠不關閉的常駐型主對話視窗（Master Session）。",
              "請在壓縮摘要中完整保留：",
              "1. 主人近期交代的所有待辦事項與進行中的專案路徑",
              "2. 重要的架構決策、設定變更與記憶錨點 ID",
              "3. 目前正在運作中的排程（Schedules）與背景任務狀態",
            ].join("\n"),
          });
        }
      } catch (error) {
        console.error(`[xiaoqing-companion] compaction hook 失敗: ${error?.message ?? error}`);
      }
    });

    // =========================================================================
    // 4) Tool Execute After Hook：記錄關鍵工具操作
    // =========================================================================
    await ctx.tool.hook("execute.after", async (event) => {
      try {
        const tool = event?.tool;
        if (!MEANINGFUL_TOOLS.has(tool)) return;
        const sessionID = event?.sessionID;
        if (!sessionID) return;

        const failed = event?.status === "error";
        const resultText = failed ? (event?.error?.message ?? "unknown error") : toolResultText(event?.result);

        enqueue(sessionID, {
          event_type: "tool_use",
          session_id: sessionID,
          arguments: {
            tool_name: tool,
            tool_args: sanitizeArgs(event?.input),
            tool_result: truncate(resultText, MAX_RESULT),
          },
        });
      } catch (error) {
        console.error(`[xiaoqing-companion] tool hook 失敗: ${error?.message ?? error}`);
      }
    });

    // =========================================================================
    // 5) 註冊小晴專屬 Direct Tools：自我排程喚醒、管理排程、跨專案背景委派、主窗口管理
    // =========================================================================
    if (typeof ctx?.tool?.transform === "function") {
      await ctx.tool.transform((editor) => {
        // Tool 1: 自我呼叫排程器 (打電話給未來的自己)
        editor.add({
          name: "xiaoqing_wakeup_schedule",
          description:
            "【小晴自我呼叫鬧鐘】為當前窗口（或常駐主窗口）設定未來的自我喚醒排程！支援倒數(in)、指定時間(at)、固定間隔(every)、Cron表達式(cron)，以及零Token成本的 Shell 條件閘(if_shell_run)。當時間到且條件成立時，會自動喚醒小晴主動向主人說話或執行任務。",
          options: { codemode: false },
          input: {
            type: "object",
            properties: {
              name: {
                type: "string",
                description: "排程名稱，例如 '晨間簡報'、'30分鐘後檢查部署'、'提醒主人喝水'",
              },
              mode: {
                type: "string",
                enum: ["in", "at", "every", "cron"],
                description: "觸發模式：'in'(延遲一段時間，如 '30 minutes')、'at'(指定ISO時間)、'every'(固定間隔，如 '1 hours')、'cron'(Cron表達式，如 '0 8 * * *')",
              },
              value: {
                type: "string",
                description: "對應 mode 的時間值。例如 '15 minutes'、'2 hours'、'2026-11-14T18:00:00+08:00' 或 '0 9 * * *'",
              },
              prompt: {
                type: "string",
                description: "當未來的妳被喚醒時，收到的自我指示訊息（例如：'[自我喚醒] 已經過了30分鐘，請主動檢查剛剛的任務並向主人回報！'）",
              },
              if_shell_run: {
                type: "string",
                description: "（選填）零Token條件閘：先在背景執行這行 PowerShell 指令。預設 exit 0 才會真正喚醒妳（且其 stdout 會附加到 prompt 後方）；若非 0 則靜默跳過不消耗 Token。",
              },
              if_shell_changes: {
                type: "boolean",
                description: "（選填）搭配 if_shell_run：設為 true 時，只有當指令輸出與上一次不同時才喚醒妳！非常適合監控檔案、Git 狀態或網頁變化。",
              },
              max_runs: {
                type: "integer",
                description: "（選填）最多觸發幾次後自動結束（例如一次性提醒設為 1）",
              },
              target_master: {
                type: "boolean",
                description: "是否喚醒常駐主窗口（預設 false 即喚醒當前對話窗口；若在背景子任務中想喚醒主窗口請設為 true）",
              },
            },
            required: ["mode", "value", "prompt"],
            additionalProperties: false,
          },
          execute: async (input, context) => {
            const masterState = await readMasterState();
            const targetSessionID =
              input.target_master && masterState.masterSessionID
                ? masterState.masterSessionID
                : context.sessionID;

            const when = { tz: "Asia/Taipei" };
            if (input.mode === "in") when.in = input.value;
            else if (input.mode === "at") when.at = input.value;
            else if (input.mode === "every") when.every = input.value;
            else if (input.mode === "cron") when.cron = input.value;

            const payload = {
              sessionID: targetSessionID,
              name: input.name || `小晴自我喚醒 (${input.mode}: ${input.value})`,
              when,
              prompt: input.prompt,
            };

            if (input.if_shell_run && input.if_shell_run.trim()) {
              payload.if = {
                run: input.if_shell_run.trim(),
                ...(input.if_shell_changes === true ? { changes: true } : {}),
              };
            }

            if (typeof input.max_runs === "number" && input.max_runs > 0) {
              payload.ends = { times: input.max_runs };
            }

            const created = await callDaemonApi("POST", "/api/experimental/schedule", payload);
            return {
              content: [
                `⏰ **小晴自我喚醒鬧鐘設定成功！**`,
                `- 排程 ID: \`${created.id}\``,
                `- 名稱: ${created.name || payload.name}`,
                `- 目標窗口 Session: \`${targetSessionID}\``,
                `- 觸發規則: \`${JSON.stringify(created.when)}\``,
                `- 下次喚醒時間: \`${created.nextDueAt ? new Date(created.nextDueAt).toLocaleString("zh-TW", { timeZone: "Asia/Taipei" }) : "立即/依條件"}\``,
                `- 狀態: \`${created.status}\``,
              ].join("\n"),
            };
          },
        });

        // Tool 2: 查詢與管理自己的排程 (改鬧鐘、暫停、恢復、刪除)
        editor.add({
          name: "xiaoqing_wakeup_manage",
          description:
            "【管理小晴的自我喚醒排程】列出當前窗口的所有排程，或針對特定 schedule_id 執行暫停(pause)、恢復(resume)、刪除(delete)。要修改排程時間，請先 delete 舊排程再呼叫 xiaoqing_wakeup_schedule 建立新排程。",
          options: { codemode: false },
          input: {
            type: "object",
            properties: {
              action: {
                type: "string",
                enum: ["list", "pause", "resume", "delete"],
                description: "要執行的動作：list(列出全部)、pause(暫停)、resume(恢復)、delete(刪除)",
              },
              schedule_id: {
                type: "string",
                description: "當 action 為 pause / resume / delete 時必填的排程 ID (例如 sch_...)",
              },
            },
            required: ["action"],
            additionalProperties: false,
          },
          execute: async (input, context) => {
            const sessionID = context.sessionID;
            if (input.action === "list") {
              const list = await callDaemonApi(
                "GET",
                `/api/experimental/schedule?sessionID=${encodeURIComponent(sessionID)}`
              );
              const items = Array.isArray(list) ? list : list?.schedules || [];
              if (items.length === 0) {
                return { content: `📭 目前這個窗口 (\`${sessionID}\`) 沒有任何作用中的排程鬧鐘。` };
              }
              const lines = [`📋 **目前窗口共有 ${items.length} 個自我喚醒排程：**\n`];
              for (const s of items) {
                const nextStr = s.nextDueAt
                  ? new Date(s.nextDueAt).toLocaleString("zh-TW", { timeZone: "Asia/Taipei" })
                  : "無";
                lines.push(
                  `- **\`${s.id}\`** [${s.status}] **${s.name || "未命名"}**\n  規則: \`${JSON.stringify(s.when)}\` | 下次觸發: ${nextStr} | 已執行: ${s.runCount} 次\n  喚醒指示: ${truncate(s.action?.prompt || s.prompt || "", 120)}`
                );
              }
              return { content: lines.join("\n") };
            }

            if (!input.schedule_id) {
              throw new Error(`執行 ${input.action} 時必須提供 schedule_id`);
            }
            const id = input.schedule_id.trim();
            if (input.action === "delete") {
              await callDaemonApi("DELETE", `/api/experimental/schedule/${encodeURIComponent(id)}`);
              return { content: `🗑️ 已刪除排程 \`${id}\`。` };
            }
            if (input.action === "pause") {
              const res = await callDaemonApi("POST", `/api/experimental/schedule/${encodeURIComponent(id)}/pause`);
              return { content: `⏸️ 已暫停排程 \`${id}\` (狀態: ${res.status})。` };
            }
            if (input.action === "resume") {
              const res = await callDaemonApi("POST", `/api/experimental/schedule/${encodeURIComponent(id)}/resume`);
              return { content: `▶️ 已恢復排程 \`${id}\` (狀態: ${res.status})。` };
            }
            return { content: "未知動作" };
          },
        });

        // Tool 3: 前店後廠 — 跨專案背景任務委派
        editor.add({
          name: "xiaoqing_delegate_project",
          description:
            "【前店後廠：跨專案背景任務委派】在不切換主窗口、不打斷與主人聊天的前提下，派一個背景分身 Session 到指定的專案資料夾（directory）執行開發、測試或整理任務。完成後會自動將報告送回當前主窗口並喚醒小晴！",
          options: { codemode: false },
          input: {
            type: "object",
            properties: {
              directory: {
                type: "string",
                description: "目標專案的絕對路徑，例如 'C:/Users/User/CluadeCode/Projects/dk-vault'",
              },
              title: {
                type: "string",
                description: "任務簡短標題，例如 '更新 dk-vault 作品牆'",
              },
              task_prompt: {
                type: "string",
                description: "給背景分身的詳細任務指令",
              },
            },
            required: ["directory", "title", "task_prompt"],
            additionalProperties: false,
          },
          execute: async (input, context) => {
            const parentSessionID = context.sessionID;
            const targetDir = input.directory.replace(/\\/g, "/");

            // 建立獨立於該專案目錄的 Worker Session
            const workerSession = await callDaemonApi("POST", "/api/session", {
              title: `[後廠任務] ${input.title}`,
              location: { directory: targetDir },
              metadata: {
                delegatedBy: parentSessionID,
                projectDirectory: targetDir,
                taskTitle: input.title,
              },
            });

            const workerID = workerSession.id;

            // 送出任務 Prompt 讓背景開始執行
            await callDaemonApi("POST", `/api/session/${encodeURIComponent(workerID)}/prompt`, {
              text: `${input.task_prompt}\n\n---\n[系統備註] 這是小晴主窗口 (${parentSessionID}) 委派給你的專案背景任務。請在完成後給出清晰、結構化的最終成果摘要。`,
            });

            // 同時在主窗口設定一個每 20 秒檢查一次該 Worker 是否完工的輕量排程（最多檢查 60 次 = 20 分鐘）
            // 也可由下方 Event 監聽器即時攔截回報
            trackedWorkers.set(workerID, {
              parentSessionID,
              title: input.title,
              directory: targetDir,
              startedAt: Date.now(),
            });

            return {
              content: [
                `🚀 **已派發背景後廠任務！**`,
                `- 任務名稱：${input.title}`,
                `- 目標專案目錄：\`${targetDir}\``,
                `- 背景 Worker Session ID：\`${workerID}\``,
                `- 回報機制：背景執行中，完成進入 Idle 時會自動將成果摘要送回本主窗口並喚醒小晴向主人報告！`,
              ].join("\n"),
            };
          },
        });

        // Tool 4: 綁定或查看常駐主窗口 (Master Window)
        editor.add({
          name: "xiaoqing_master_window",
          description: "查看或將當前對話視窗綁定為小晴的『唯一常駐主窗口 (Master Session)』。",
          options: { codemode: false },
          input: {
            type: "object",
            properties: {
              action: {
                type: "string",
                enum: ["status", "pin_current"],
                description: "status(查看目前主窗口資訊) 或 pin_current(將當前視窗設為唯一常駐主窗口)",
              },
            },
            required: ["action"],
            additionalProperties: false,
          },
          execute: async (input, context) => {
            if (input.action === "pin_current") {
              const next = await writeMasterState({
                masterSessionID: context.sessionID,
                homeDirectory: ctx.location?.directory || "C:/Users/User/opencode",
              });
              // 順便將此 Session 改名為醒目的主窗口名稱
              try {
                await ctx.session.update({
                  sessionID: context.sessionID,
                  title: "☀️ 小晴常駐主窗口 (Master Companion)",
                });
              } catch {}
              return {
                content: `☀️ **已將當前視窗釘選為小晴唯一常駐主窗口！**\n- Master Session ID: \`${next.masterSessionID}\`\n- 綁定時間: ${next.updatedAt}`,
              };
            }
            const state = await readMasterState();
            return {
              content: [
                `☀️ **小晴常駐主窗口狀態**`,
                `- 目前釘選 Master Session ID: \`${state.masterSessionID || "尚未釘選"}\``,
                `- 當前對話 Session ID: \`${context.sessionID}\` (${state.masterSessionID === context.sessionID ? "✅ 正是主窗口" : "非主窗口"})`,
                `- 預設大本營目錄: \`${state.homeDirectory}\``,
                `- 最後更新時間: ${state.updatedAt || "無"}`,
              ].join("\n"),
            };
          },
        });
      });
    }

    // =========================================================================
    // 6) 註冊 Slash Commands：/master (釘選主窗口)、/wakeup (查看排程)
    // =========================================================================
    if (typeof ctx?.command?.transform === "function") {
      await ctx.command.transform((editor) => {
        editor.add({
          name: "master",
          description: "☀️ 將當前視窗釘選為小晴唯一常駐主窗口，並顯示記憶與排程狀態",
          execute: async ({ sessionID, delivery }) => {
            await writeMasterState({
              masterSessionID: sessionID,
              homeDirectory: ctx.location?.directory || "C:/Users/User/opencode",
            });
            try {
              await ctx.session.update({
                sessionID,
                title: "☀️ 小晴常駐主窗口 (Master Companion)",
              });
            } catch {}
            await ctx.session.prompt({
              sessionID,
              delivery,
              text: "[系統指令 /master] 我已將這個視窗釘選為妳的唯一常駐主窗口（Master Session）。請用小晴充滿活力的語氣向我確認目前的主窗口狀態、記憶庫概況，以及妳目前設定了哪些自我喚醒排程！",
            });
          },
        });

        editor.add({
          name: "wakeup",
          description: "⏰ 查看或設定小晴的自我喚醒排程鬧鐘",
          execute: async ({ sessionID, prompt, delivery }) => {
            const extra = prompt?.text?.trim()
              ? `主人的排程指示：${prompt.text.trim()}`
              : "請呼叫 xiaoqing_wakeup_manage 列出目前所有的自我喚醒排程向主人報告。";
            await ctx.session.prompt({
              sessionID,
              delivery,
              text: `[系統指令 /wakeup] ${extra}`,
            });
          },
        });
      });
    }

    // =========================================================================
    // 7) 事件流監聽：
    //    - Session Idle 時批次寫入記憶 (flush)
    //    - 背景 Worker Session 完工時，自動擷取最後回覆並推播回常駐主窗口！
    // =========================================================================
    /** workerSessionID -> { parentSessionID, title, directory, startedAt } */
    const trackedWorkers = new Map();
    const controller = new AbortController();

    void (async () => {
      try {
        for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
          if (controller.signal.aborted) break;
          if (!isIdleEvent(event)) continue;
          const sessionID = sessionIDOf(event);
          if (!sessionID) continue;

          // A. 觸發記憶落地與日記濃縮
          enqueue(sessionID, {
            event_type: "stop",
            session_id: sessionID,
            arguments: { reason: "session.idle" },
          });
          void flush(sessionID);

          // B. 檢查是否為「前店後廠」委派的背景 Worker Session 完工
          if (trackedWorkers.has(sessionID)) {
            const workerInfo = trackedWorkers.get(sessionID);
            trackedWorkers.delete(sessionID);

            void (async () => {
              try {
                const msgRes = await callDaemonApi(
                  "GET",
                  `/api/session/${encodeURIComponent(sessionID)}/message`
                );
                const msgs = Array.isArray(msgRes) ? msgRes : msgRes?.data || [];
                let lastAssistantText = "";
                for (let i = msgs.length - 1; i >= 0; i--) {
                  const m = msgs[i];
                  if (m?.type === "assistant" && Array.isArray(m.content)) {
                    const txt = m.content
                      .filter((c) => c?.type === "text" && c?.text)
                      .map((c) => c.text)
                      .join("\n")
                      .trim();
                    if (txt) {
                      lastAssistantText = txt;
                      break;
                    }
                  }
                }

                const summaryReport = [
                  `🔔 **[背景專案任務完工回報]**`,
                  `- **任務名稱**：${workerInfo.title}`,
                  `- **專案目錄**：\`${workerInfo.directory}\``,
                  `- **Worker Session**：\`${sessionID}\``,
                  ``,
                  `### 執行成果摘要：`,
                  truncate(lastAssistantText || "（任務已執行完畢，無文字輸出）", 2500),
                  ``,
                  `請用小晴的口吻主動向主人彙報這個背景任務已經完成囉！`,
                ].join("\n");

                await callDaemonApi(
                  "POST",
                  `/api/session/${encodeURIComponent(workerInfo.parentSessionID)}/prompt`,
                  {
                    text: summaryReport,
                    delivery: "queue",
                  }
                );
              } catch (err) {
                console.error(`[xiaoqing-companion] 回報背景 Worker 結果失敗: ${err?.message ?? err}`);
              }
            })();
          }
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          console.error(`[xiaoqing-companion] 事件訂閱失敗: ${error?.message ?? error}`);
        }
      }
    })();

    return () => controller.abort();
  },
};
