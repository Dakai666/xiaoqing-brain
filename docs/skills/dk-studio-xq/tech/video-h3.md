# 影片（MiniMax H3）

## 目錄
1. 預設流程與開關
2. 參考圖怎麼給
3. 六段提示詞格式
4. 寫法規則（含「提到就觸發」）
5. H3 技法庫
6. 錨點：首幀、尾幀、循環、多錨點、只錨聲音
7. 解析度：720p、1080p（Open-H3）、2K
8. 已知會出錯的地方
9. 速度參考

---

## 1. 預設流程與開關

**影片主力是 PRISM**（`COMFY_VIDEO_UNET=Minimax-h3_Singularity_x_10Eros-Max_PRISM_int8.safetensors COMFY_VIDEO_STEPS=8 COMFY_VIDEO_SAMPLER=euler COMFY_VIDEO_SCHEDULER=beta`，8 步蒸餾、不開 CFG）：DK 同 seed 看片勝過 FastH3〈2026-10-31〉，也比 H3 原版 20 步細緻，**原版 20 步不再使用**〈DK 2026-11-02〉。PRISM 的品質旋鈕是解析度，不是步數。不設環境變數時腳本仍是下面的 H3 原版流程（舊專案重跑用）。

**MV 流程（DK 2026-11-02）**：草稿出 480p 看分鏡 → 過關的鏡頭直接升 Open-H3 1080p，不等最終版。
- 一般橋段：`shot.py vid <鏡號> --draft`（480p，5 秒約 1.5 分鐘）→ `--hd`（拿最新草稿升 1080p，5 秒約 6.5 分鐘）。
- 極度細緻的鏡頭：`--draft 0.9`（720p 精緻草稿，5 秒約 6 分鐘）→ `--hd`。
- `refshot.py` 一樣有 `--draft`／`--hd`。草稿裡的瑕疵（動態模糊、半透明的腳）放大不會修掉，看草稿時就要挑出來。
- 480p 直上 1080p 跟 720p→1080p 品質一樣，但更貼近草稿、快約 18%；舞蹈、武打大動作也守得住〈H3_2K放大測試 第三、四輪〉。

**舊預設（H3 原版）：480p 跑 20 步 → latent 3D 放大 → Lightning 2 步精修到 720p**（`shot.py vid`，底層 `h3_upscale.py gen --full`，精修 `--refine lo`＝sigma 0.63 起）。比直接生 720p（4 步）細膩、聽提示詞、忠於關鍵幀，重抽次數少。

| 情況 | 用法 |
|---|---|
| 一般鏡頭 | `shot.py vid <鏡號>`（預設） |
| **刷第一版（MV、短劇）** | **已由 PRISM 取代**（DK 2026-11-04：短劇也改 PRISM，FastH3 不再用〈這個系統太狗 EP11〉）。舊紀錄：**FastH3 OmniRef**（8 步蒸餾的參考版，`ComfyUI-Shared\models\diffusion_models\fasth3_omniref_8step_pruned_int8_convrot.safetensors`）＋預設流程：環境變數 `COMFY_VIDEO_UNET=fasth3_omniref_8step_pruned_int8_convrot.safetensors COMFY_VIDEO_STEPS=8 COMFY_VIDEO_SAMPLER=euler`，`shot.py vid`／`refshot.py`／`h3_upscale.py` 都吃，不要加 `--fast`（精修段偵測到 FastH3 會自動不疊 Lightning）。10 秒約 7 分鐘、15 秒約 13 分鐘；RefMod＋場景圖、舞蹈 LoRA 都能用。直出 720p（`--direct --full` 加同樣的環境變數）15 秒 25 分鐘，DK：約原版 720p 直出的 85%〈H3舞蹈LoRA測試，2026-10-26，DK：極具戰略價值〉。**短劇同 seed 對照（9 鏡）：品質跟 20 步差不多、快約 1.6 倍，但特寫首幀、多段特寫一鏡到底常被拉成中景／全身**（20 步比較守得住）→ 整集用 FastH3 刷，臉部特寫、多段特寫鏡改 20 步；DK 看成片：有挑選的前提下 FastH3 品質不輸，蓄勢一鏡到底（G31b）DK 反而選 FastH3 版〈這個系統太狗 EP07，2026-10-28〉 |
| **夜景、天空、窗外有亮光** | `--direct`（直接生 720p，4 步）：預設流程約 1/3 會在後半冒日出 |
| 只是趕時間 | `--fast`（480p 改 4 步，比較不聽話）；快速動作不要用，連續破綻多 |
| 先挑動作再放大 | `h3_upscale.py gen` 大量跑低畫質，挑中的再 `h3_upscale.py vid 影片.mp4` 放大 |
| 換影片模型（Dasiwa Hybrid v3 等） | 環境變數 `COMFY_VIDEO_UNET=…`，流程不變 |

- 換步數等於重抽，同一個 seed 也會出不同的動作。
- `--refine hi`（作者預設 0.9）會改動作、換臉、冒路人，不要用。
- 每鏡的提示詞存成 `shots/<鏡號>/<鏡號>_vid_prompt.txt`；`--dry` 只印不送。
- 16GB 顯存：直接生 720p × 15 秒加控制會卡死整台，一定走「低畫質 → 放大 → 精修」。15 秒是 H3 訓練長度上限，更長的鏡頭分兩段接。
- 影片長度是 17k+5 格、24fps；H3 輸出 1280×736，自帶生成的音軌。

## 2. 參考圖怎麼給

| 鏡頭 | 參考 |
|---|---|
| 首幀已經有人、看得到臉 | 關鍵幀＋臉部參考（臉更穩） |
| 其他有關鍵幀的鏡頭 | **`--noref`**（只給關鍵幀）。人物參考會把影片拉走：首幀不跟關鍵幀、變成灰底大頭照、換臉、冒人（約 1/4） |
| 人物會抬頭、轉頭 | 關鍵幀先露出那張臉＋附臉部參考；低頭的首幀抬頭後 H3 會編一張別人的臉 |
| 從背面轉到正面 | 附正面的服裝參考，否則轉過來的衣服是模型編的 |
| 無人鏡頭 | shots.json 標 `"empty": true`（改用 `video_suffix_empty`）；通用後綴寫了「她」就會補一個人出來 |
| 對話鏡（短劇） | RefMod＋無人場景圖、不做關鍵幀（`cast-refmod.md`） |

- **巡檢先看首幀**：首幀跟選定的關鍵幀不一樣，就是被參考圖拉走了，`--noref` 重跑。
- 偶發「中段突然換成灰底攝影棚、灰毛衣」：有臉部參考的鏡頭會遇到。背影鏡用 `--noref`；其他換 seed，或只取正常段（`cleancut.py` 可自動偵測）。
- **首幀縮放跳一下**＝關鍵幀和影片的長寬比不同（9:16 關鍵幀 768×1376 vs 影片 736×1312）。事前把關鍵幀裁成影片比例；剪輯時每鏡**跳過開頭 0.2 秒**（`editing.md`）。

## 3. 六段提示詞格式（官方 Ref2VA）

本機只有 H3-Base，沒有官方的 Context-IR 改寫器，所以我們自己寫成 H3 訓練時的格式。`shot.py vid` 會自動組好：

1. `subject_definitions`：每張參考是誰、是什麼。
2. `summary`：任務標籤（`[keyframe completion]`、`[reference generation]`、`+ multi-shot`）＋一句總結。
3. `retention_analysis`：每個參考的保留程度（`fully_preserved`、`partially_preserved`）。
4. `detailed_description`：先一句風格句，再寫 `[Shot 1] The shot begins from <Picture 1>. …`。
5. `overall_soundscape`：環境音。
6. `non_diegetic_music`：配樂，寫樂器、速度、動態，不寫情緒形容詞；沒有就寫 `N/A`。

shots.json 欄位（完整清單見 `reference/shots-json.md`）：`vid` 只寫動作、運鏡、變化路徑；`first`（首幀描述）、`last`＋`lastdesc`（尾幀）、`sound`、`music`、`line`／`voice`／`vo`、`tail`、`changes`。`--legacy` 改回舊白話寫法（舊專案重跑用）。

AI 寫手（Qwen3-VL 8B 自動寫六段）給 DK 隨手玩；正式作品的提示詞由 Claude 寫。規則在 `prompt_writer/`。

## 4. 寫法規則

- **運鏡＝類型＋幅度＋速度**：`pushes in with small amplitude at slow speed`、`arcs around her from her right side toward her left with small amplitude at slow speed`、`holds a static shot`。
- 鏡內剪接：`[Shot 2] At 00:02.000, the camera cuts to …`，第一鏡不加時間。tail 寫同一人、同服裝、同光線 across all shots。
- 台詞：`(S1) says: <d>[Chinese] 原文</d>`；畫外音：`says in an off-screen voiceover: <d>…</d> while her lips remain completely closed`。
- 畫面上的字放進英文雙引號、保留原文。
- 臉：`three-quarter view, never fully frontal`，避免證件照式正臉。
- **人物不能罰站**：只寫站著看遠方，影片會很呆。給一個簡單動作（慢慢走、撥頭髮、轉頭）。
- 寫變化的**路徑**，不只寫結果；先概括，再照時間展開。
- 一張參考圖只負責一件事。
- 速度感：寫「快三倍」只快約 20%。
- **提到就觸發**（最重要的反直覺規則）：要擋的東西一個字都不要寫。
  - 寫 no sun／no sunrise／no lens flare → 太陽更多。改寫 `The light level and colors stay exactly as in the first frame from start to end`。
  - 寫 the disc never lights up → 圓片全亮；寫 No text appears → 浮出字；寫 no mist from her mouth → 吐白霧。
  - 寫 listening／answering／asks → H3 自己腦補成對話、嘴巴動。閉嘴鏡只寫具體身體動作（吃泡麵、轉頭看、眨眼）。
  - 影片的風格句不要列調色盤顏色（寫 coral-pink palette，衣服就被染成珊瑚粉）。
- 華麗特效要明寫 `cinematic, epic blockbuster visual effects, blinding explosive laser beam, shockwaves, debris`；只寫 golden light 會變成飄飄的金光。
- **系統面的變化或 bug（跳過、快轉、傳送、重置）走數位感，不用金光**：寫 `corrupted video data, horizontal bands of pixels tear, RGB channels split, datamosh, a tiny black hole pulls the whole picture in`，並明寫 `No golden light, no glow`；傳送寫成 `dissolves into a storm of small square pixel blocks`／`pixel blocks snap together and assemble into him`，H3 都做得出來。原因：DK 覺得修仙不等於金光燦燦，金光看起來廉價〈這個系統太狗 EP03 A22、A04、A05〉。
- 鏡頭後半常自己拉遠、轉向鏡頭、冒陌生人：寫 `Locked-off camera`、`no other person enters the frame`，剪輯只用前段。
- **畫面裡寫到名牌、告示、檔案，H3 會自己寫字**（簡體、而且字會一直變）：讀字的鏡頭寫成看畫面外的東西、`Nothing is written anywhere in the frame`，字另外用 PIL 疊成插入鏡〈這個系統太狗 EP11 H18〉。
- 真實速度：`Real-time footage at normal speed, not a time-lapse… sway slowly and gently`（窗簾抖得像縮時時用）。
- 多一隻腳、鬼影：`exactly two feet, only one woman, no duplicated limbs, no ghosting, no motion-blur trails`，舞步改成簡單、清楚、不急，用 `--direct` 重跑兩支挑。
- 念錯字就換同音字：女聲把「鑰匙」念成 you-shi → 提示詞寫「藥石」，字幕照寫原字。

## 5. H3 技法庫

範例在 `風格探索測試/提示詞練習/shots.json`，可直接複製欄位。

| 技法 | 寫法重點 | 狀態 |
|---|---|---|
| 鏡內剪接（一次生成的蒙太奇） | `[Shot N] At 00:0X.000, the camera cuts to …`，tail 寫 across all shots | ✅ 切點準 |
| **廣告一鏡到底**（多鏡頭＋旁白＋台詞一次生） | RefMod＋場景圖，9 秒寫 5 個 `[Shot N]`（腳→高衩→飾品→抬眼→靠近說台詞），旁白寫 `A deep, booming, epic male movie-trailer narrator voice-over says…`、角色台詞寫在最後一鏡；兩個 seed 都成功，比分開拍四連特寫＋另配旁白更順（DK：效果不錯，以後多用〈這個系統太狗 EP01 夜凰廣告〉） | ✅ |
| **限制生成長度讓 H3 自己講快** | 片長故意設得比自然語速短（旁白 4.7 秒的句子給 3 秒），H3 會把台詞壓進去，字照樣念對（旁白 4.72→2.84、陸沉 4.56→3.50）；提示詞補 `The line is spoken briskly so that it fits within the shot.`。要壓整集長度時優先用這招，不要事後 time-stretch（DK〈這個系統太狗 EP01 v6〉） | ✅ |
| 手繪／水墨水彩疊實景 | `Mixed media: live-action with flat hand-drawn … layered onto the real surfaces`；線條貼著實物；`matte and flat like paint on paper, with no glow`；人物 `remain live-action and unpainted` | ✅ DK：很有潛力 |
| 畫面文字逐筆出現 | `small and refined handwritten white characters reading "下一站" appear stroke by stroke on the fogged glass, never covering her face` | ✅ 中文清楚 |
| 卡通疊實景（噴漆妖怪、浪從 LED 溢出） | 人物 `stays live-action and unpainted`；寫明卡通物件維持大小 | ✅ 很穩 |
| 平塗 2D 動畫 | `video_style`：`flat 2D hand-painted animation… never photographic, never 3D`；tail：`remains a flat 2D painting` | ✅ 10 秒撐得住；半寫實（有體積光影）會被拉回寫實 |
| 焦散光 | 關鍵幀先畫出焦散且有光源；`vid` 寫光紋隨水流動；**光源要先動**（踢水、倒水） | ✅ 泳池；△ 水杯 |
| 變形鏡頭光暈 | 關鍵幀只放光源；`vid` 寫條件式「as its headlights turn and face straight into the camera, each headlight stretches into a thin horizontal blue anamorphic lens flare streak…」；tail 寫 it stays night | ✅ |
| 首尾幀轉場 | `--last 圖.png`；**一律 10 秒慢轉場**，依時間寫階段（From 00:02.000… by 00:08.000…），強調 slowly and gradually | ✅ DK：5 秒太急太假 |
| 先近再拉遠 | 關鍵幀拍中近景鎖臉。快版（高能量段）：`starts close on her face… pulls back with large amplitude at fast speed, finishing within the first three seconds`；**慢版（抒情歌）**：`starts close on her face; the camera slowly pulls back with medium amplitude at slow speed to reveal …`〈不將不迎〉 | 約一半成功；有時首幀直接跳成正臉大特寫。跟 `--direct` 併用還沒測 |
| 同一人多分身、同機位跳接、真人化成水墨淡出 | 直接寫 | ✅ |
| H3 物理 | 砸玻璃、相框震倒、吃東西咀嚼、剝龍蝦都撐得住；「滑過櫃檯」做不出滑行 | ✅／✗ |
| 縮時＋固定構圖錨點 | `Time-lapse. The camera holds a static shot; … stay completely fixed`＋`changes: true` | △ 光線變化很弱 |
| 畫外音獨白 | `line`＋`vo: true` | △ 聲音可用，嘴中段會微張 → 改拍背影或切掉 |
| 全像光 | 會被 H3 當成衣服圖案跟著動 | ✗ 只用在靜態鏡 |
| **打鬥一鏡到底**（攻擊者一支、目標一支，都是 RefMod＋場景圖、多個 `[Shot N]`） | 攻擊者：特寫喊招 → 揮劍 → 劍氣脫出就收；目標：正面迎擊 → 臉 → 閃避／卡位 → 撞上護罩爆炸 → 塵埃落定無恙。前一鏡做過的動作，下一鏡不要再做一次（舉劍揮劍兩次＝重複）。空間連續要明寫「爆炸後仍在原位、兩側物件到結尾都在」。劍氣寫 `a thin, wide, flat crescent arc of energy (no sword, no blade object, no beam)`，否則會變成金色巨劍。DK：打鬥要高動態動作片運鏡，鏡頭一定要動〈這個系統太狗 EP02〉 | ✅ |
| 兩人武打鏡（RefMod 兩個） | 主動方 1.0、被壓制方 0.6（勢均力敵的碰撞鏡 0.8），在 body 每段寫明誰對誰做什麼（`<Subject 1> (the empress in black armor)`）。一支 10 秒寫 4 段攻防就穩；空手角色寫招式外型（掌心霜光、夾槍凍住、背後滿月）比寫「法術」具體。手部動作寫 `never waving, a fighter's stance`，否則舉手會變成揮手打招呼〈這個系統太狗 番外〉 | ✅ |
| **動態 LoRA**（FourBunny：`Motion_Repair_V2`＋`Bunny_weapon_combatV1`） | `COMFY_VIDEO_LORA="Motion_Repair_V2.safetensors:0.7,Bunny_weapon_combatV1.safetensors:0.7"`，低畫質與精修兩段都會吃到。0.7：衝刺步幅大、爆炸是整片強光；1.0：人變半透明、閉眼；不掛：爆炸最弱。不會變慢〈這個系統太狗 EP02 E24，DK 定 0.7〉。**高動態武打鏡一律掛 0.7**：同 seed 對照構圖幾乎一樣、差在動態，DK：差異顯著；對話、特寫、僵持這類低動態鏡不必掛（不掛版的僵持特寫反而有對視）。動作戲仍難：正戲的武打鏡預設多抽幾個 seed、挑段落拼剪〈這個系統太狗 番外 女帝 vs 蘇清雪〉 | ✅ |
| **單一物件低畫質（144p 龍王）** | H3 照常生高解析 → SAM3 文字「dragon」逐格摳 → 只對物件做 **5px 方格（720 寬＝真 144p）＋每 3 格才更新**，遮罩本身也方格化，背景維持原畫質；看起來是物件本身低解析，不像打碼。16px（約 80p）大臉特寫會像馬賽克；3px（256p）手機上看不出來；8bit 精靈圖 DK 看不懂。升格＝方格在前 3 秒縮回原畫質。聲音可壓成低位元破音。工具 `這個系統太狗/ep06/pixel_dragon.py`（`--block 5 --hold 3`、`--mode upgrade --up_sec 3`、`--crush`）〈這個系統太狗 EP06，DK：效果很讚〉 | ✅ |
| **伺服器補判殘影**（某人的分身疊到另一人身上） | H3 畫不出「看得出是誰」的殘影：RefMod 兩人同框、都站定 → SAM3 文字各摳一人 → 把 A 複製成灰白冷色方格殘影（保留明暗才認得出帽T跟臉、RGB 錯位、閃爍、方格外框），先在他身上分身 0.25 秒、再 0.6 秒滑到 B 身上、腳對齊 → 旁白「補正」時紅色鎖定框收縮扣上。下一鏡拿合成片最後一格（不帶框）當首幀、**掛 B 的 RefMod**，光柱才會砸在 B 身上。工具 `這個系統太狗/ep08/ghost.py`〈這個系統太狗 EP08，DK：因果讀得出來〉 | ✅ |
| 手遊廣告介面（倒數、✕、按鈕） | 廣告本體 RefMod 一鏡到底，介面字用 PIL 疊上（每秒倒數），不讓 H3／Qwen 寫字；舊廣告拼進光幕的黑色螢幕區，DK：版面不對 → 全螢幕廣告重拍更好。工具 `這個系統太狗/ep08/adui.py`〈這個系統太狗 EP08〉 | ✅ |
| 系統光幕寫字 | Qwen 寫字關鍵幀（光幕＋虛焦人物）→ H3 3 秒，寫 `Locked-off camera; the panel and its text stay perfectly still and unchanged`，旁白在片內念同一句。字整支沒跑掉〈這個系統太狗 EP02「非戰鬥狀態」〉 | ✅ |

## 6. 錨點

| 需求 | 用法 |
|---|---|
| 首幀 | 第一張 `--ref` 只是參考，**要用 `--first`（`first=True`）才用 AddGuide 硬錨在第 0 格**。`shot.py vid` 預設開（shots.json `"first": false` 關掉），各集 `kvid` 也預設開（`NO_FIRST` 排除）；RefMod＋空場景圖（`refshot.py`）不要開，不然空場景會變首幀〈這個系統太狗 EP09，DK 2026-10-28 定預設〉 |
| 尾幀 | `--last 圖.png`（錨在 frame -1） |
| 無縫循環 | `--loop`：同一張圖錨在第 0 格和最後一格；**錨定過的片都要過 `seamfix.py`**（頭尾 2～3 格比片身小約 0.5～1%），用 `loopcheck.py` 驗證 |
| 多錨點鏡內剪接 | shots.json 寫 `anchors: [["G07", 3.8]]`，`vid` 用 `{A1}` 指那張關鍵幀；精修時會重錨。切點不保證準（有一支整個晚 2.7 秒），剪輯前用相鄰格差異量實際切點 |
| 對嘴音軌 | `--audio x.wav` 或 shots.json `"audio"`；見 `lipsync.md` |
| 只錨聲音、不錨首幀 | `H3_AUDIO_ONLY=1`：RefMod＋空場景圖的對嘴鏡用，否則空場景會被當成首幀 |

- 錨點幀先裁成低畫質的比例（480p＝864×480，1.8）再送。

## 7. 解析度

- **交件**：MV、解說 1080p；短劇 720p；動畫風不升 1080p（DK：要糊糊的老動畫感）。
- **16:9 一律 1080p、短劇 720p**（DK 2026-11-02：這個品質和速度，16:9 都直上 1080p）。
- **1080p 走 Open-H3**（`--hd`；NVIDIA Open-H3-Regenerate-2K 的精修 LoRA，Kijai 版 `minimax_h3_open_regenerate_2k_refiner_rank_384_bf16`）：草稿 latent 3D 放大到約 2.09MP（照畫面比例，16:9＝1920×1088）→ PRISM＋精修 LoRA 1.0、sigma 0.8 三步 → 分塊解碼。DK 看播放：SeedVR2 的遠景建築、水面會抖，人物也沒有 Open-H3 美 → Open-H3 完勝〈H3_2K放大測試，2026-11-02〉。
  - ⚠️ **`--refine hd` 不是 `--hd`**：前者只是把精修參數設成 hd、解析度不變（仍是 1312×736），
    後者才會換成 Open-H3 流程（1920×1088）。兩者名字很像、很容易搞混〈紅海盜的小酒館，2026-11-15〉。
  - sigma 用 0.8：官方 0.909 重畫太多（石橋拱下冒出電線）；0.8 跟官方差距小、比較貼近草稿。
  - 會重畫臉：通常更像演員檔（精修也帶 RefMod），神情更定（DK）。中遠景的小臉一樣偏糊，事前避開的做法照第 8 節。
  - 成品不用再疊原片質地（SeedVR2 才有的油亮問題）。
  - MV 出片：`picks_vid_1080.json`（鏡號 → `_hd` 片）＋`MV_RES=1080` 跑 `finalcut.py`、`roughcut.py --export`，不設 `MV_BLEND`；字幕 size 放大 1.5 倍。（這條路還沒整支 MV 實跑過，第一次用時要檢查。）
  - 只有 RefMod 演員檔跟著走；舞蹈 LoRA、動作戲 LoRA 只在草稿那段掛就好。
- **2K**（`regen2k.py --wh 2560 1440`，在 `H3_2K放大測試\`）：有料但慢，16GB 的上限約 5 秒（21 分鐘）；10 秒 2K 顯存溢出，一整天跑不完，不要跑。史詩遠景才考慮。

## 8. 已知會出錯的地方

- **夜景、天空會冒日出**；畫面有月亮、亮點會被變成帶星芒的太陽；琥珀色地平線一定補成日出 → `--direct`，或改靜態推近（`still: true`）。
- **大面積純白場景**中段會暗成聚光燈舞台，擋不住 → 靜態推近或只用前 1.5 秒。
- 影片後半常出問題（變亮、換場景、表情變）→ 分鏡表「剪輯注意」標「只用前半」，由剪輯避開，不硬重抽。
- 自己補東西：欄杆上的鳥、寶塔、吐氣白霧；碰到敏感意象（宗教）的鏡頭要特別檢查。
- 手部特寫容易斷指，能換成物件特寫就換。手入鏡寫 `fitted cuff, only the forearm`，不然袖子會垂成一大片布。
- 服裝顏色在光線變化時會飄（深紫在藍光變淺藍）：明寫顏色，光線改暖。
- 室內下雨變成停滯水絲：雨放窗外，室內用牆面水幕、地面淺水流。
- 720p 中遠景的臉一定崩：正臉只拍 3/4 中景以內；全身動作拍下半身或背影；遠景用「先近再拉遠」。**事後補救：`face_refine.py`**（逐格追臉 → 裁成滿版 → FastH3 OmniRef＋RefMod 局部重繪 → SeedVR2 1 倍修復 → 只把臉貼回），全身舞蹈鏡（臉約 80 像素）眼睛和五官變清楚、臉型變穩，看不出接縫；追臉 243 格沒有掉格〈H3舞蹈LoRA測試 龍女 D01，2026-10-26〉。臉更小的遠景還沒測。
- 影片用的髮型越簡單越好（左右對稱、沒有髮飾）；半紮髮髻＋髮簪每鏡都不一樣。
- 道具數量會飄；要鎖住數量和位置，拿場景圖裁特寫當首幀。**數得出來的小道具（三顆玉珠兩紅一綠）連關鍵幀都會畫錯、H3 重拍還會改顆數和顏色** → 用 PIL 把關鍵幀修對，再做靜態推近，不走 H3〈這個系統太狗 EP08〉。
- **K 鏡裡露臉的人沒掛 RefMod，臉會漂成別人**（阿呆中景變成年輕人）：KMOD 掛上那個人〈這個系統太狗 EP08 J18〉。
- **K 鏡首幀不一定被照用**（`ep.py kvid`＝`h3_upscale gen`，首幀只靠「Use <Picture 1> as the exact first frame」）：特寫首幀被換成全身、換衣服、燒字幕；**掛 KMOD 時 <Picture 1> 還會被演員檔的第一張（全身正面、笑臉）頂掉**。改用 AddGuide 硬錨第 0 格（`first=True`，現在是預設，見 §6），四支特寫全部照首幀走〈這個系統太狗 EP09 P14／P15／P17／P24〉。
- **用 edit 從底圖拿掉的東西，`scene_desc` 還寫著就會被 H3 補回來**（拔針後光霧）：改了底圖，scene_desc 和鏡頭提示詞一起改〈這個系統太狗 EP09〉。
- **寫「看著鏡頭上方浮著的光幕」，H3 會在畫面頂端畫一塊空白灰色面板**：寫「天空是空的、畫面裡沒有任何面板」，光幕另外用一鏡〈這個系統太狗 EP08 J21〉。
- **寫「眼睛從上往下掃，像在讀一長頁」，H3 會塞一本書到他手上**：寫「看著面前空中的光、手上什麼都沒有、手不入鏡」〈這個系統太狗 EP10 Z25〉。
- **PIL 疊在米白／淡金光幕上的字要用深墨色**（深棕標題、深灰內文、淡色外暈）；金字、白字在亮光幕上看不見。畫面上沒有光幕的地方，疊半透明深色底框〈這個系統太狗 EP10〉。
- **鏡頭在動時，光幕上的字要追蹤**：每格抓亮區當框（`scipy.ndimage.label`，只取不碰畫面上緣、面積最大的那塊，天空也很亮；兩面光幕取最大兩塊、依 x 排左右），前後各 3 格平滑再疊字〈這個系統太狗 EP12 M19、M25；`ep12/ui.py`〉。光幕比旁邊的玻璃反光暗時會抓錯（抓到反光），鏡頭只是慢推的話，改成量首尾格的光幕框、逐格線性內插〈EP13 N22〉。
- **旁白寫「At 00:04.500」H3 不一定照做**，可能從第 0 秒就開始念，跟後製疊的 TTS 撞在一起：量出旁白實際位置，原聲靜音、用 `vo` 把旁白接到想要的時間，尾巴可以蓋到下一鏡〈這個系統太狗 EP12 M25〉。
- 運鏡最難控：環繞常變成推近，或人跟著轉身面向鏡頭。動態小樣先跑物理、自然動態最划算。鏡內分鏡的其中一段寫「人停住、鏡頭繞半圈」，兩個 seed 有一個做到約 90 度，可以試〈這個系統太狗 EP03 冷開場〉。
- 縮時光影方向反了就倒放（`reverse: true`）。
- **同鏡的金色道具會把別的物件帶成金色**（龍傲天的金龍大刀 → 翡翠綠龍王變金龍，兩個 seed 都是）：主要物件的顏色每鏡寫死＋`never golden`〈這個系統太狗 EP06〉。
- **寫「喉嚨裡的光越來越亮」，H3 一定會噴出雷射**（寫了不准噴也沒用）：要它不噴，就寫成「光閃了閃、像啞火一樣熄掉、冒一縷煙」〈這個系統太狗 EP06 龍王只會普攻〉。
- **前景人物和背景人群比例會錯**（站著的人變巨人、跪列變很小）：關鍵幀寫明相對尺寸（「跪著的人只到他腰」）並放低機位〈這個系統太狗 EP06 F10〉。
- **提示詞寫「念出浮空的一行字」，H3 會把台詞當字幕燒進畫面**：改寫「抬眼看鏡頭上方的東西」，並加「Absolutely no text on screen」〈這個系統太狗 EP05〉。
- **特寫裡寫「巨大的手／火貼在他臉旁」，H3 會拼成分割畫面**（一邊大臉、一邊大手）：特效放在遠處天空、人用胸上近景，並寫「One continuous single frame, no split screen, no collage」〈這個系統太狗 EP13 N17〉。
- **黑底剪影（不露臉的預告）H3 撐不住**：一個 seed 2.6 秒跳成灰棚、露出一張臉；另一個剪影 0.2 秒就暗掉，還把台詞燒成簡體字幕 → 畫面用剪影關鍵幀做靜態慢推，只借 H3 片的聲音〈這個系統太狗 EP13 N02〉。
- **聲音段寫「looping chimes」「music」，H3 會把鈴聲／配樂燒進片子**，剪輯時拆不掉（只能人聲分離）：聲音段只寫環境、腳步、風、人聲，寫明 `no music, no chimes`〈這個系統太狗 EP13〉。
- **「跪向某處／面向某物」常拍反**（人背對要面對的東西）：方向畫進關鍵幀，最穩的是從他背後拍、目標在他前方〈這個系統太狗 EP05 踩背〉。

## 9. 速度參考（5070 Ti 16GB）

| 內容 | 時間 |
|---|---|
| **PRISM 480p 草稿（`--draft`）**：5 秒／10 秒 | 約 1.5 分鐘／約 3 分鐘 |
| **PRISM 720p 精緻草稿（`--draft 0.9`）**：5 秒／10 秒 | 約 6 分鐘／約 12 分鐘 |
| **Open-H3 1080p（`--hd`）**：5 秒／10 秒 | 約 6.5 分鐘／約 23 分鐘 |
| Open-H3 2K：5 秒 | 約 21 分鐘 |
| 3 秒（預設流程） | 約 100 秒 |
| 5 秒（預設流程） | 約 4 分鐘 |
| 8.5 秒多錨點 | 約 12 分鐘 |
| 12.7 秒長對嘴鏡 | 約 18 分鐘 |
| 15 秒 480p 低畫質 | 約 4.5 分鐘 |
| 15 秒（預設流程，升 720p） | 約 20 分鐘 |
| FastH3：10 秒／15 秒（預設流程，升 720p） | 約 7 分鐘／13 分鐘 |
| FastH3：15 秒 720p 直出 8 步 | 約 25 分鐘 |
| 60 鏡 MV 全批 | 約 3～4 小時 |
