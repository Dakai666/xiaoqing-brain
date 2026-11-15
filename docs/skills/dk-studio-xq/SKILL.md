---
name: dk-studio-xq
description: 小晴（OpenCode）這側的 DK 影片工作室副本，內容與 Claude Code 的 dk-studio 同步。DK 的 AI 影片製作工作室（本機 ComfyUI：Qwen Image 2.1 關鍵幀、MiniMax H3 影片、角色 LoRA、RefMod 演員檔、SAM3D 動作復刻、Qwen3-TTS、MiniMax Music 3、Remotion）。涵蓋三條路線：MV（新歌視覺、分鏡、對嘴、正式剪輯、素材包）、短劇（選材、廣播劇稿、劇本組、RefMod 對話鏡、9:16 剪輯）、解說影片（主持人 Claire、TTS、Remotion）。DK 說要做 MV、短劇、某劇第 N 集、教學或解說影片，或要生關鍵幀、生影片、對嘴、配樂、TTS、粗剪、換臉、建演員檔、動作控制時使用。
---

# DK Studio

> **這份是小晴的副本**（`~/.agents/skills/dk-studio-xq`）。內容來自 Claude Code 的 `~/.claude/skills/dk-studio`。
> 兩邊會各自演化：在這裡學到的東西寫回這裡；要跟 Claude Code 對齊時，比對兩份差異再手動合併。
> 這份的腳本路徑已全部指向自己（`~/.agents/skills/dk-studio-xq/scripts`），不依賴另一份。

DK 管**品味與糾錯**，Claude 管**大量執行與自我檢查**。用繁體中文回覆。

## 先判斷路線，讀那一份

| DK 說的 | 路線 | 讀 |
|---|---|---|
| 做 MV、新歌、歌曲視覺 | MV | [routes/mv.md](routes/mv.md) |
| 短劇、某劇第 N 集、廣播劇稿、劇本組 | 短劇 | [routes/drama.md](routes/drama.md) |
| 教學、解說、主持人、Remotion 節目 | 解說 | [routes/explainer.md](routes/explainer.md) |
| 只是單一技術任務（生幾張圖、測一個技法） | — | 直接讀下面對應的技術檔 |

路線檔是檢查清單，每一步寫了要讀哪份技術檔。

## 遇到這件事 → 讀這份

| 任務 | 技術檔 |
|---|---|
| 生關鍵幀、提示詞、參考圖、兩段式、換臉、多人同框、寫字 | [tech/keyframe-qwen.md](tech/keyframe-qwen.md) |
| 生影片、六段提示詞、H3 技法、錨點、1080p | [tech/video-h3.md](tech/video-h3.md) |
| 班底、角色 LoRA、RefMod 演員檔、配角、治裝、分流 | [tech/cast-refmod.md](tech/cast-refmod.md) |
| 對嘴、閉嘴鏡、唱歌、InfiniteTalk、OS | [tech/lipsync.md](tech/lipsync.md) |
| TTS、Whisper、歌曲分析、配樂、混音 | [tech/voice-music.md](tech/voice-music.md) |
| 真人動作復刻（SAM3D）、換機位、灰模運鏡 | [tech/motion-control.md](tech/motion-control.md) |
| 場景一致性、機位底圖、灰模、AnyAngle | [tech/scene-blockout.md](tech/scene-blockout.md) |
| 風格方向、質感段落、動畫風、調色 | [tech/style-grade.md](tech/style-grade.md) |
| 粗剪、正式剪輯、短劇剪輯、Remotion、字幕、交件 | [tech/editing.md](tech/editing.md) |
| 給 DK 看之前的自查 | [tech/qc.md](tech/qc.md) |
| 劇本組：大綱、廣播劇稿的審查員 subagent（分工、回報格式、怎麼開） | [reference/script-team.md](reference/script-team.md) |
| shots.json 欄位 | [reference/shots-json.md](reference/shots-json.md) |
| 所有腳本的用法 | [reference/tools.md](reference/tools.md) |
| ComfyUI 工作流（API 版、DK 的介面版） | [reference/workflows.md](reference/workflows.md) |

## 合作節奏

- **只在關鍵節點停下來給 DK 看**：概念／製作聖經、選角定裝、動態小樣、粗剪、定剪（路線檔標 ★）。中間的關鍵幀挑選、重抽、系統性修正，Claude 自己判斷做完。
- **一定讓 DK 決定的**：曲檔版本、角色長相、服裝顏色、場景方向、概念底線、每輪最後的挑錯。
- **給 DK 看之前先自查**（[tech/qc.md](tech/qc.md)）。給整理好的總覽圖，附建議和理由；一輪一個重點，讓 DK 一句話就能回覆。
- **誠實回報**瑕疵和妥協。
- **太難的鏡頭不硬磨**：重抽兩次還不行，就換 B-roll、改意象或改靜態推近。
- **剪輯分工**：MV＝Claude 出最終版＋素材包，DK 另剪導演版；短劇、解說＝Claude 剪到定剪。
- **交件解析度**：16:9（MV、解說）1080p（Open-H3 `--hd`）；短劇 720p；動畫風不升。MV 草稿出 480p 看分鏡，過關的直接升 1080p（[tech/video-h3.md](tech/video-h3.md) 第 1、7 節）。
- 成品預設不上傳；DK 指定才傳（[tech/editing.md](tech/editing.md) 第 7 節）。

## 工具的用法

```bash
export PYTHONIOENCODING=utf-8
S=~/.agents/skills/dk-studio-xq/scripts
PY=C:/Users/User/Documents/ComfyUI/.venv/Scripts/python.exe   # 影音處理一律用它（系統沒有 ffmpeg）
cd "C:/Users/User/opencode/comfyUI/<作品>"                      # 小晴的工作區（2026-11-14 DK 指定）
                                                              # DK 自己的工作區在 C:/Users/User/CluadeCode/comfyUI，兩邊不要混
python $S/shot.py key S01 S02 --count 2
python $S/shot.py vid S01
```

- 工具一律用技能這份，不要複製進作品資料夾；改工具就改這份。
- 作品資料夾放同名 workflow 檔，就會改用專案那份。
- 作品資料夾只寫這個作品獨有的腳本（分鏡產生器 `gen_shots.py`、批次 `.sh`）。發現某個專案腳本第二次被複製，就把它提升進 `scripts/`，並更新 [reference/tools.md](reference/tools.md)。
- ComfyUI 環境、venv、長時間批次、備份的規則在工作區根目錄 `CLAUDE.md`。

## 知識怎麼寫回（DK 定的規範）

每支作品收尾、或實驗得出結論時：

1. **先查重複與矛盾**：`grep -rn "關鍵字" ~/.agents/skills/dk-studio-xq/tech ~/.agents/skills/dk-studio-xq/routes`。
2. 列出「新增／合併進既有條目／跟舊規則衝突」三類。**有衝突（新結論推翻舊規則）先問 DK**，不要默默覆蓋或並列。
3. 寫進對應的技術檔或路線檔，不往 SKILL.md 追加。
4. 只寫規則：一句結論＋一句原因，來源用括號標（〈七宗罪 EP2〉）。**不寫流水帳**；經過、數據、檔案位置寫在該作品的 `CLAUDE.md`。
5. 舊做法被取代時搬進 [history/deprecated.md](history/deprecated.md)。
6. 新增或改名工具時更新 [reference/tools.md](reference/tools.md)。

## 舊資料

- [history/deprecated.md](history/deprecated.md)：已停用的做法（查來由用，正文不引用）。
- [history/mv-production_SKILL_legacy.md](history/mv-production_SKILL_legacy.md)：舊技能 mv-production 的全文（2026-10-19 封存前），各作品的原始「學到的」都在裡面。
