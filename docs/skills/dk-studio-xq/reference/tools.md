# 工具一覽（`scripts/`）

全部在作品資料夾裡執行，讀寫目前所在的資料夾。`S=~/.agents/skills/dk-studio-xq/scripts`。

- **py**＝ComfyUI venv python（`C:/Users/User/Documents/ComfyUI/.venv/Scripts/python.exe`，影音處理一律用它）
- **tts**＝tts-venv python（`C:/Users/User/Documents/ComfyUI/tts-venv/Scripts/python.exe`）
- **G**＝會送工作給 ComfyUI（要開著；佇列排隊，不會打斷別人的批次）
- **free**＝會打 `/free` 卸掉 ComfyUI 的模型：**H3 批次在跑時不要跑**。
  ComfyUI **閒置時也不會自己卸模型**，會一直占住 13.9GB VRAM；下次開工前先
  `POST /free {"unload_models":true,"free_memory":true}` 才跑得動新工作〈紅海盜的小酒館，2026-11-15〉
- 路徑用相對路徑或 `C:/…`；Git Bash 的 `/c/…` 寫在 `鏡號=路徑` 這種參數裡時，Windows 的 Python 開不了。

## 目錄
1. 生成
2. 角色與演員檔
3. 聲音
4. 動作控制與灰模
5. 剪輯與後製
6. 檢查
7. 工作流建置

---

## 1. 生成

| 工具 | 用法 | 備註 |
|---|---|---|
| `comfy.py` | `image "提示詞或@檔.txt" [--ref 圖] [--layout 圖] [--aspect] [--mp] [--seed] [--count] [--lora 檔:強度] [--cfg]`；`video … [--audio] [--first] [--last] [--loop] [--control]`；`aspects` | G。底層：套 `workflows/` 的 API workflow、上傳、等待、下載。環境變數 `COMFY_IMAGE_LORA`、`COMFY_VIDEO_LORA`（H3 動態 LoRA，`tech/video-h3.md` 第 5 節）、`COMFY_IMAGE_UNET`、`COMFY_VIDEO_UNET`、`H3_REFMOD`、`H3_AUDIO_ONLY`。**`--aspect` 要給完整字串**（`"3:2 (Photo)"`、`"16:9 (Widescreen)"`），只寫 `"3:2"` 會被節點拒絕、`POST /prompt` 回 400〈紅海盜的小酒館，2026-11-15〉 |
| `shot.py` | `key <鏡號…> [--count 2]`、`vid <鏡號…> [--noref] [--direct] [--fast] [--key 檔] [--seed] [--dry] [--legacy] [--draft [0.9]] [--hd]`、`all` | G。讀 shots.json → `shots/<鏡號>/`。影片預設 480p 20 步 → 720p。**MV 流程（DK 2026-11-02）**：`--draft` 只出 480p 草稿 `_d480`（`--draft 0.9`＝720p 精緻草稿 `_d720`）→ 過關的 `--hd` 拿最新草稿升 Open-H3 1080p `_hd`（沒草稿就 480p 生成後直接升） |
| `refshot.py` | `<鏡號…> [--seed 11] [--dry] [--draft [0.9]] [--hd]`（`--draft`→`_ro_s<seed>_d480`、`--hd`→同 seed 最新草稿升 1080p `_ro_s<seed>_hd`） | G。RefMod＋場景圖、不做關鍵幀（route `ro`）→ `_ro_s<seed>_`（`COMFY_VIDEO_UNET` 是 FastH3 時存成 `_ro_fast_s<seed>_`，跟 20 步版並存）。鏡頭有 `audio` 就對嘴，自動只錨聲音；每鏡可寫 `scene_desc`（多場景必寫）、`music`、`acting` |
| `h3_upscale.py` | `gen "提示詞" --ref 圖 --sec N --full [--first] [--control 影片] [--audio]`；`vid 影片.mp4 "提示詞" --ref 首幀` | G。低畫質 → latent 放大 → 精修；`--refine lo`（預設）；`--first` 關鍵幀硬錨第 0 格（關鍵幀起手時開）；**`--hd`＝Open-H3 1080p**（照畫面比例約 2.09MP、PRISM＋`minimax_h3_open_regenerate_2k_refiner_rank_384_bf16` 精修 LoRA、sigma 0.8 三步、分塊解碼；5 秒約 6.5 分鐘、10 秒約 23 分鐘；16GB 的 2K 上限約 5 秒） |
| `face_refine.py` | `影片.mp4 [--refmod cast/x] [--prompt …] [--denoise 0.5] [--large 0.35] [--seed] [--no-seedvr] [--name]` | G。成片的臉部精修：逐格追臉、裁成 768 滿版，用 FastH3 OmniRef＋RefMod 局部重繪 → **預設再過 SeedVR2 1 倍修復**（混回 35% H3 質感；眼睛、睫毛、唇線更銳利，DK 定為預設）→ 只把臉貼回（`ComfyUI-H3-FaceRefine` 節點包）。10 秒約 9 分鐘（`--no-seedvr` 約 6.5 分鐘）；另存 `_crops_` 檢查用 |
| `faceswap.py` | `stitch｜edit｜both 原圖 輸出 …` | G。三種換臉（`tech/keyframe-qwen.md` 第 4 節） |
| `itk.py` | `gen <鏡號…> [--scale] [--who]`；`up <鏡號> 影片.mp4` | G。InfiniteTalk 對嘴 → 放大到 720p |
| `seedvr.py` | `影片.mp4 [--mult 1.5] [--chunk] [--name]` | G。SeedVR2 升 1080p → `outputs/seedvr/` |
| `music.py` | `@caption.txt [--lyrics @歌詞.txt] --sec 28 --count 3 --name bgm` | G。MiniMax Music 3 → `outputs/<name>_*.flac` |

## 2. 角色與演員檔

| 工具 | 用法 | 備註 |
|---|---|---|
| `refmod.py` | `make cast/<名> 1.png … 8.png` | G。建 RefMod 演員檔（約 4 秒） |
| `wardrobe8.py` | `run 造型圖.png --char D05 --desc "…" [--only 視角] [--style none]`；`pick <名> a b …`；`build` | G。有 LoRA 的班底：八視角＋建檔（預設疊 RadianceChrome 0.7） |
| `castfile.py` | `audition <代號…>`；`run <代號…>`；`pick <代號> a b a a` | G。無 LoRA 配角：定裝 → 模板 → 補四視角 → 建檔。讀 `cast.json` |

## 3. 聲音

| 工具 | 用法 | 備註 |
|---|---|---|
| `tts.py` | `[台詞id …]` | **tts**、free。讀 `lines.json` → `audio/<id>.wav`、`audio/lines_report.json` |
| `host.py` | `prep`／`chain <鏡> <上一鏡>` | 解說主持人鏡。讀 `host.json`（鏡頭→台詞、關鍵幀、動作）→ `audio/pad/`、`shots.json`、`picks.json`；之後 `shot.py vid` |
| `vocals.py` | `歌曲.mp3 --name x` | G。人聲分離 → `outputs/audio/x_vocals_00001.flac` |
| `singaudio.py` | `人聲.flac [鏡號…]` | py。`sing: true` 的鏡頭切 in→out、補靜音 → 鏡頭的 `audio` |
| `analyze.py` | `歌曲.mp3 [--lang zh] [--vocals 人聲.flac]` | py、free。`energy.txt`、`whisper.txt`、`whisper.json` |
| `asr.py` | `檔案… [--lang zh] [--cpu]` | py。Whisper 逐字＋時間 |
| `speech.py` | `檔案…`；`--shots` | py。RMS 說話段落、建議入出點 |
| `musiccheck.py` | `<前綴>` | py。配樂的長度、節拍、峰值、人聲 → `_env_<前綴>.png` |

## 4. 動作控制與灰模

| 工具 | 用法 | 備註 |
|---|---|---|
| `prep.py` | `原片.mp4 名稱` | py。轉 24fps＋縮圖表 |
| `trim.py` | `in.mp4 out.mp4 起始格 格數` | py。切成 17k+5 格 |
| `sam3d_extract.py` | `X_src.mp4 --name X --styles mesh [--cam 角,俯,zoom] [--no-follow] [--glb]` | G。SAM 3D Body 白模（`cam3d.py` 是它用的換機位模組） |
| `sam3_mask.py` | `X_src.mp4 --name X [--text woman]` | G。SAM3 摳人遮罩 |
| `meshsil.py` | `白模.mp4 遮罩.mp4 out.mp4` | py。白模疊服裝剪影 |
| `run_ctrl.py` | `@prompt.txt --ref 定裝.png --sec N --c 控制.mp4:0.85 [--c 第二支:0.6] [--end 0.6]` | G。480p 控制生成（小樣） |
| `pose_extract.py`、`depth_extract.py` | 見檔頭 | G。SDPose／深度合成（備案） |
| `blockout/blockout.mjs` | `node blockout.mjs 場景.json --frames 124 --modes depth --mp4` | 灰模圖、深度圖、運鏡深度影片（格式 `blockout/README.md`） |

## 5. 剪輯與後製

| 工具 | 用法 | 備註 |
|---|---|---|
| `roughcut.py` | `[--label] [--edit edit_v2.json] [--export]` | py。MV 粗剪、素材包。環境變數 `MV_RES=1080`、`MV_PICKS_VID`、`MV_BLEND` |
| `finalcut.py` | `final.json [--nosubs]` | py。MV 正式剪輯（格式見檔頭；範例 `edit_example.json`） |
| `dramacut.py` | `edit.json` | py。9:16 短劇剪輯（格式見檔頭、`tech/editing.md` 第 4 節）；劇情字卡 `card_style: "title"`、旺財貼圖 `sticker`、疊影 `ghost`（開頭疊上一鏡最後一格） |
| `still.py` | `圖 輸出.mp4 秒數 [--zoom 1.04] [--center x y] [--size WxH]`；`--pick 鏡號 秒數` | py。靜態推近。**`--size` 的值是單一字串**（`1920x1088`），寫成兩個數字會被 argparse 當多餘參數 |
| `filmgrade.py` | `輸入 輸出 --preset expired｜warm｜cool [--strength] [--grain]` | py。後期調色 |
| `seamfix.py`、`loopcheck.py` | 見檔頭 | py。循環片接縫修正、驗證 |
| `render_storyboard.py` | （無參數） | shots.json → `<title>_分鏡表.md` |

## 6. 檢查

| 工具 | 用法 | 備註 |
|---|---|---|
| `review.py` | `[段落…]` | py。關鍵幀檢查圖（a/b 候選） |
| `vidreview.py` | （無參數） | py。每支影片抽 4 格 |
| `look.py` | `strip out.jpg 鏡號=影片[:格,格] …`；`grid out.jpg 欄數 [標題\|]檔案…`；`window in.mp4 out.jpg 起秒 迄秒 張數` | py。抽格、拼圖、密集格 |
| `sheet.py` | `out.png 檔案…` | py。圖片直接放、影片取首中尾 |
| `stack_cmp.py` | `out.mp4 每欄寬 名稱=影片 …` | py。多支影片並排成一支 |
| `cleancut.py` | `檔案… [--json out.json]` | py。灰底定裝照格偵測；作品腳本可 import `studio_mask`／`clean_range` |

## 7. 工作流建置

| 工具 | 用途 |
|---|---|
| `build_sam3d_mv_workflow.py [--cam｜--all]` | 產生 SAM3D 疊影／換機位／集大成工作流的 API 與 layout JSON |
| `build_qwen_ai_workflow.py` | 產生 `Qwen-Image_AI寫提示詞` 工作流 |
| `comfy_ui_build.js` | 在 ComfyUI 前端把 API JSON 轉成介面版（檔頭有用法和三個前端地雷） |

## 讀它當參考（作品資料夾裡的專用腳本，不要直接跑）

| 腳本 | 參考什麼 |
|---|---|
| `女主角選角/group_lora.py`、`ComfyUI教學影片/主持人試鏡/duo.py` | 多個有 LoRA 的角色同框：逐臉 img2img 各掛自己的 LoRA |
| `女主角選角/lora_data.py`、`build_train.py`、`lora_test.py` | 角色 LoRA 訓練素材、訓練集、檢查點比較 |
| `不將不迎/pool_blockout.py`、`pool_shots.py` | 整座場景灰模、每鏡相機、只寫看得到的東西 |
| `這個系統太狗/ep01/v4/plates_t2i.py` | 機位底圖 |
| `這個系統太狗/ep01/v4/shots_v4.py`、`cleancut.py` | TTS 主音軌短劇：鏡長由音軌算、自動選版本與剪點寫進 Remotion |
| `這個系統太狗/選角/details.py` | 從定裝圖裁局部重畫成高解析細節特寫 |
| `短劇_七宗罪/ep4/photofix.py` | 只換相框裡的照片（重複出現的小道具） |
| `一地殘紅v2/post.py` | 後製特效：細水紋、柔邊對話框、拉慢補幀 |
| `PARALLAX RIDE/gen_night.py`、`assemble.py` | 循環片批次＋自動 seamfix、整支接整支組片、車身微震 |
| `ComfyUI教學影片/ep01_選角/v2/build.py`、`host.py` | 解說影片：TTS 時間軸 → Remotion、主持人鏡補靜音與接續鏡 |
