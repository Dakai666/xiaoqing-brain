# 關鍵幀（Qwen Image 2.1）

## 目錄
1. 提示詞寫法
2. 參考圖：什麼時候放、會帶進什麼
3. 有人物的關鍵幀：三種做法
4. 換臉決策表
5. 多人同框
6. 寫字（信、當票、封面）
7. 場景一致性
8. 常見的坑

---

## 1. 提示詞寫法

- **CFG 1 時負面提示詞完全沒作用**（ComfyUI 在 CFG 1 會跳過負面條件，我們的 Qwen workflow 預設 CFG 1）。想避開的東西一律寫成「要看到的樣子」：
  - 不寫 no smile → 寫 `calm neutral face, lips gently closed`
  - 不寫 never frontal → 寫 `three-quarter view, her gaze lowered toward …`
  - 不寫 not full body → 開頭寫 `Medium shot framed from the waist up`
  - 只有改用 CFG > 1（例如 AnyAngle 的 `--cfg 3.0`）時，`--neg` 才有效。
- **取景句放最前面**：角色 LoRA 會把特寫拉回中景，取景寫在最前面才壓得住。
- **只描述畫面裡看得到的東西**：Qwen 2.1 很聽話，寫了畫面外的東西就會塞進畫面（上半身鏡頭寫高跟鞋，腿會被塞進來；寫更衣室，背景就多一間）。
- **眼神、姿勢、手寫成看得到的狀態**：`gaze lowered toward the counter, both hands on the carved armrests as if about to stand`。動作寫清楚起點和方向：`pinch the corner and draw it upward from between the pages`。
- **道具給位置**：`in the upper centre directly above the chair`、`across the lower third`、`on the far right edge`。
- **光線獨立寫一句**：光源、方向、陰影落在哪裡。
- **寫死，不要 hedge**：不寫 appears to be、wood or laminate；畫面裡的東西都是導演指定的。
- 角色 LoRA 的觸發詞放在主詞位置（`The image is a vertical realistic cinematic photograph of d05girl, …`），並寫出她招牌的外觀（膚色、髮型、表情）。Aria 一定要寫 `warm golden-brown skin`，否則會被風格 LoRA 洗白。
- 重要鏡頭可以寫到 250～400 字（補背景材質、角落的東西）；一般鏡頭 80～150 字。
- **提到就觸發**：寫「沒有 X」常常反而生出 X（見 `video-h3.md` 第 4 節），圖片也一樣，要擋的東西一個字都不寫。
- **生已知 IP 的角色不要寫 IP 名稱**，改寫物理特徵（`bulky crimson red power armour`、
  `torn ragged edges hanging from the shoulder plates`、`brass skull badge`、`jetpack backpack`）：
  寫了專有名詞模型會套用遊戲既有截圖的構圖，改寫特徵反而更準〈紅海盜的小酒館，2026-11-15〉。
- **「手塗／上舊」感要明寫**，模型不會自己理解：崩邊掉漆（`deliberate chipped paint along the armour edges`）、
  崩爛布條、鏽、油污、油漬痕跡，一個字不寫就會變成全新出廠的乾淨模型〈紅海盜的小酒館，2026-11-15〉。
- **小道具用形狀描述**：`Imperial cog-shaped metal parts` 比寫專有名詞穩。
- 質感段落（玻璃版、木刻）見 `style-grade.md`，每支作品開工時問 DK 要不要用。

## 2. 參考圖：什麼時候放、會帶進什麼

參考圖會把它的**背景、姿勢、構圖、視線、表情、鞋子**一起帶進來。

| 參考圖 | 會帶進來的 | 對策 |
|---|---|---|
| 人物全身照 | 全身站姿；中景、特寫也被畫成全身 | 人物參考一律純色背景全身照；中景以內只放頭肩照 |
| 臉部參考（正面） | 畫面被拉回正面置中、直視鏡頭 | 要特殊角度就走兩段式（第 3 節） |
| 場景照片 | 構圖被鎖成那張照片的機位 | 近景別放；要不同機位就純文字生（見 `scene-blockout.md`） |
| 有人的場景圖 | B-roll 冒人、姿勢被鎖 | 場景參考一律用無人版 |
| 表情（微笑的參考） | 每張都在笑 | 準備「平靜不笑」版當預設 |
| 風格色偏烤進錨點圖 | 染到每一張臉 | 人物錨點圖一律中性乾淨 |
| 舊參考圖的瑕疵 | 碎亮片、髮帶被傳染 | 換人設時先 edit 清乾淨 |

- 微距、手部鏡頭不要放人物參考。
- 沒寫衣服時，參考圖的衣服（灰毛衣）會被照抄：每個情境都指定服裝。
- 風格參考圖在掛角色 LoRA 時幾乎沒作用，風格要靠文字。

## 3. 有人物的關鍵幀：三種做法

| 情況 | 做法 |
|---|---|
| **有角色 LoRA（班底五人）**，一般鏡頭 | `shot.py key`，掛 LoRA 直接 t2i，不放臉部參考 |
| 要特殊角度（仰拍、俯拍、過肩、側面）或特定姿勢 | **兩段式**：① 不放任何參考，只靠文字生構圖 ② 以 ① 為 `--layout`，用 edit 換成這個人的臉與服裝（第 4 節） |
| 構圖、站位、機位要精準 | 灰模 `--layout`（見 `scene-blockout.md`） |

- 純背影不 edit（edit 會吃掉頭髮），第 ① 段直接用。
- 中景以內的鏡頭不要寫裙長和鞋。
- `--layout` 加 `--denoise < 1` 時，`comfy.py` 會改用 VAEEncode 當起點；部分重繪換不了臉，換臉一律 denoise 1.0。

## 4. 換臉決策表（`scripts/faceswap.py`）

| 情況 | 模式 | 原因 |
|---|---|---|
| 主角（有 LoRA），第 ① 段構圖要完全保住 | `stitch`：YOLO 找臉 → 裁正方形 → edit 換臉 → 羽化貼回 | 整張 edit 會被全身造型圖拉回站姿〈Musta-Krakish〉 |
| **之後要送進 H3 的鏡頭**、無 LoRA 配角 | `edit`：整張 edit 換人 | stitch 的接縫在靜態圖看不出，但 H3 會把那圈色帶當成畫面保留〈七宗罪 EP1〉 |
| 兩人鏡 | `both`：一次 edit 換兩張臉（Picture 2＝左、Picture 3＝右） | 每多一次整張 edit 畫質就掉一層；換兩次噪點變 2～2.5 倍〈七宗罪 EP2〉 |
| 一般對話鏡（短劇） | 不換臉，走 RefMod＋場景圖 | 見 `cast-refmod.md` |

換臉提示詞的寫法：
- 用「Replace the woman in Picture 1 with the woman from Picture 2: her exact face, eyes, nose, lips … Dress her exactly in the outfit from Picture 3 … Keep the pose, head angle, camera angle, framing, lighting and background of Picture 1」。「Keep Picture 1 exactly, only change the facial features」幾乎不會換。
- **逐臉寫出這鏡的表情和視線**（`His expression: …, eyes looking down at …, not at the camera`），不寫會被洗成參考圖的平靜臉、看鏡頭。
- 臉佔畫面大的特寫只給臉部特寫（`--faceonly`）：給了全身造型圖，構圖會被拉成正面半身。
- 換臉參考用**高解析頭部特寫**（裁下來再 edit 精修成 1024，`framing from the top of the head to the collarbones`），並依第 ① 段的頭部角度挑一張（正面、3/4 左右、側面、低頭）。
- 唱歌張開的嘴會被闔上：stitch 模式加 `--mouth open`。

## 5. 多人同框

- **一鏡最多兩人**（短劇）：沒有 LoRA 的臉越多越崩。群戲改兩兩一組快切，或過肩鏡帶第二人。
- **多個有 LoRA 的角色同框**：先 t2i 排好站位和造型 → 每張臉裁塊做純 img2img（denoise 0.6），只掛她自己的 LoRA，緊遮罩貼回。不要把多個角色 LoRA 一起掛。參考 `女主角選角/group_lora.py`、`ComfyUI教學影片/主持人試鏡/duo.py`（讀它當參考）。
- 多人合照用 crop & stitch 逐張換臉，還是會留殘影；要穩只能靠角色 LoRA。
- **人數、站位要畫進關鍵幀**，不要交給 H3 的文字（`exactly two executioners` 三次都生出四個）。

## 6. 寫字（信、當票、封面）

- Qwen 2.1 寫中文字很可靠：信（直書也行）、當票、印章、鑑定簿、宋體標題，完整文字寫進提示詞，8/8 逐字正確〈七宗罪 EP8〉。
- 文字放在雙引號裡，寫明位置、字體（`elegant traditional Song-style serif`）、`small and refined`。
- 封面：1:1、1.5MP、出 3 張候選。
- 要讓字出現在影片裡：H3 會讓字一行行長出來或變假字 → 取影片最後一幀用 Qwen edit 改字，再做推近靜態鏡（`still.py`），兩段用 0.4 秒溶接。

## 7. 場景一致性

- 同一個場景每鏡只靠文字生，每鏡都長得不一樣。會重複出現的場景：整座做成灰模，或先做機位底圖（`scene-blockout.md`）。
- 風格前綴寫死房間格局（一扇窗、機櫃在右牆、輕鋼架天花板…）就夠穩；這比加場景參考圖好，參考圖會鎖機位。
- **場景風格字串太具體會污染所有鏡頭**（寫了 wooden house，B-roll 全變同一棟房子）。B-roll 用中性風格並寫明沒有人。
- 室內鏡頭寫 `Entirely indoors`，風格字串不放外景字眼；戶外鏡頭另設一個 world（例如 `ext`）。
- **會重複出現的小道具**（相框裡的照片）：先照常生，再用一次 edit「只換框內照片」，參考圖是第一次出現的那張（`短劇_七宗罪/ep4/photofix.py`，讀它當參考）。
- 道具數量會飄（茶杯、鑰匙、鎖），一律抽 2～4 張逐一數。

## 8. 常見的坑

- **浮空的半透明光幕（拖著走、捏著拉）會被畫成實體看板**（扛在手上、有厚度）：不做關鍵幀，改 RefMod＋場景底圖讓 H3 一鏡到底，光幕就是透明發光的〈這個系統太狗 EP07：G04→G04r〉。原則：Qwen 重抽兩次還畫不出來的構圖，先試 H3 一鏡到底再考慮換意象（DK）。
- **只寫局部（「跪著的人只露出膝蓋以下的裙襬」）不寫人，會畫成一件沒有人的空衣服鋪在地上**：插入鏡直接拿無人場景底圖當首幀，讓 H3 把道具（落下的傘）帶進來〈這個系統太狗 EP07：G12u〉。
- **工具「平放在地上」文字生兩輪都畫成直立**（鋤頭、農具，連負面提示詞也擋不住）：先照構圖生一張，再 edit「全部平放在地上、沒有人拿著，其他不變」，一次對〈這個系統太狗 EP10 Z30〉。
- 倒影會被畫成第二個人：寫 `She is alone: the other figure exists only as a faint translucent reflection inside the glass`。
- 兩套服裝顏色太接近就分不出誰是誰；造型要拉開色彩，提示詞寫袖子材質。
- 灰模裡發光的細線（光縫）會被畫成金屬桿，要寫明那是光。
- 正面圖會把背後的蝴蝶結畫到前面：寫「從正面看只是一條平滑腰帶，結藏在背後」。
- 耳機會變成髮飾、手持麥克風每鏡不一樣：不戴耳機；麥克風沿用同一張關鍵幀。
- 角色 LoRA 會洩漏到沒寫觸發詞的其他女生；多人同框出問題時再練 v2（`diff_output_preservation`）。
- 「長臉、單眼皮、清淡」是模型的預設臉，大眾臉風險最高；選新角色寫具體骨相。
- Windows 不分大小寫：鏡號 `N08b` 和 `N08B` 共用資料夾，一律用 picks 或 `--key` 指定檔名。
