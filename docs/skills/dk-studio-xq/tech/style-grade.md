# 風格、質感、調色

## 目錄
1. 方向（DK）
2. 分工：圖片做質感、影片做光影、後期做色調
3. 質感段落（開工時問 DK）
4. 動畫風
5. 後期調色 filmgrade
6. 風格 LoRA 與換模型
7. 不採用的寫法

---

## 1. 方向（DK）

- 避開 AI 影片的恐怖谷：「普通寫實」最危險（本地跑的瑕疵會變穿幫）。要嘛風格化／半寫實，要嘛超寫實（比現實更美）。
- 不是過去作品的影子、不是常見的電影調色、不是對岸漫劇的 2.5D：要能固化、能重複套用的個人風格。
- 視覺典雅、留白、不急；常用色調靛藍配暖琥珀。
- 不要旋轉、奇幻發光、漩渦雲、吐氣白霧、像鬼片的窗外人影；修行、心靈意象不帶宗教色彩（不要寺廟、佛像、香、僧道，改用深山山居、蠟燭、靜坐）。
- 表情收斂：過度表情化是 AI 味。
- 水墨水彩疊實景是 DK 認可的風格方向（`video-h3.md` 技法庫）。

## 2. 分工

像真實攝影「前期拍乾淨、後期調色」：
- **圖片階段只做質感**（顆粒、柔焦、暗角；動畫用木刻刻線、木紋、桑皮紙）。不寫調色盤。
- **光影交給影片**（焦散光、變形鏡頭光暈，見 `video-h3.md`）。
- **色調在最後剪輯時調**（`filmgrade.py`），可重現、整片統一。

## 3. 質感段落（每支作品開工時問 DK 要不要用、用哪種）

寫法：開場用媒材詞 `The image is a wide <媒材> of <內容>`，結尾接固定質感段落，每鏡一字不改＝濾鏡。

- **寫實**：媒材 `early autochrome colour photograph`，段落：
  `In this image the colours are built from a visible mosaic of tiny dyed starch grains like an early autochrome plate, with a gentle soft focus and a slightly dim vignette.`
- **動畫**：媒材 `colour woodblock print of a realistic scene`，段落：
  `In this image it is carved and printed like a colour woodblock print: flat layered colour areas, visible wood-grain texture inside every colour area, crisp carved outlines and the soft absorbent texture of mulberry paper; the colours are built from a visible mosaic of tiny dyed starch grains like an early autochrome plate, with a gentle soft focus and a slightly dim vignette.`
- 影片的 `video_style` 寫媒材＋`exactly like <Picture 1>`＋`never becomes photographic or 3D`；tail 寫 `remains a flat woodblock-print animation throughout`。H3 撐得住。
- 寫實質感的瓷肌柔焦會把臉磨稚氣，五官描述要加重。
- 還沒看過：長鏡頭和大動作時顆粒會不會閃爍。

### 光源：冷暖對比最快出世界觀

- 一冷一暖兩個光源同時寫進去，畫面的世界觀立刻出來，比任何濾鏡都有效：
  廢土／戰鎚類用 `a small oil lamp casting warm amber light` ＋
  `cold blue daylight leaking through a narrow arrow slit`〈紅海盜的小酒館，2026-11-15〉。

## 4. 動畫風（〈PARALLAX RIDE〉、動畫風格測試）

- Qwen 2.1 光靠提示詞就畫得出 80～90 年代賽璐珞（墨線、平塗單層硬陰影、水粉背景、褪色底片顆粒）。
- **DK 要寫實比例**：`realistic adult proportions, about seven and a half heads tall, realistic narrow eyes with small irises`；卡通比例、側面跟拍會有點逗。不要 chibi、moe、大眼圓臉。
- 用 edit 從定裝照重畫會偏現代動畫（大眼、唇色）；直接掛角色 LoRA t2i 比較好。
- 動畫不升 1080p、維持 24fps（不做一拍二）。
- 速度感來自畫面變化和車身微震：跟著 150Hz 以下的鼓點起音震 **1 像素**（3 像素看久會晃）；開場人物鏡不震。

## 5. 後期調色 `filmgrade.py`

`filmgrade.py 輸入 輸出 --preset expired|warm|cool [--strength] [--grain 0]`（圖片或影片）。

- 色偏打在暗部和亮部，中間調（臉）幾乎不動。
- `expired`：浮黑、綠暗部、琥珀亮部，適合白天、回憶。`warm`：乾淨暖調。`cool`：夜景、雨天（夜景套 expired 會髒）。
- 顆粒預設 0，只在特定情境用。
- 可以依段落換預設（回憶 expired、現在式 cool），本身就是一種結構裝置。
- 素材是 8-bit 成品，要輕推，推太重天空會有色階斷層。
- 短劇的回憶閃回：`dramacut.py` 的 `grade: "flash"`（去飽和 60%、黑位微抬、輕暗角）或 `grade: "memory"`（暖褐、顆粒）。

## 6. 風格 LoRA 與換模型

- 開關（`comfy.py`，所有腳本共用）：`--lora "檔名:強度"` 或 `COMFY_IMAGE_LORA`；換模型 `COMFY_VIDEO_UNET`、`COMFY_IMAGE_UNET`。
- RadianceChrome（Qwen 2.1）0.7：對比更強、更有電影感；臉偏年輕日系、會改衣服。
- Dasiwa H3 Hybrid v3（int8）：跟官方 ref2va 同架構，換模型名就能跑；寫實首幀下跟官方幾乎一樣、稍飽和。對嘴錨點還沒在 Dasiwa 上測。
- **質感單調的根源常在底模本身**，提示詞和濾鏡救不太回來；換底模前用同 seed、同參數橫向比較（〈底模比較測試〉）。
- redqw（`qwen_image_redqw21UNLOCKEDV2TI2I_redqw21UNLOCKEDV1T2I_fp8`，同 Qwen 2.1 架構，角色 LoRA 可用）：場景會自己補敘事、布料細節多、構圖像電影；掛角色 LoRA 後臉會被拉成固定的網美臉，DK 當成模型自帶美顏，可以省掉上妝 LoRA。仍在探索，還沒列為預設（〈底模比較測試〉）。
- UC（`qwen-image-2.1-UC-int8_convrot`）不採用：掛角色 LoRA 後臉完全不像，而且不好看（〈底模比較測試〉）。
- Krea2（`vxpKrea2Nsfw_beta31INT8`）是另一套架構，Qwen LoRA、edit、RefMod 都不能直接接；風格特色最強，DK 打算用在半寫實或設計感重的作品（〈底模比較測試〉）。
- 半寫實（油畫質地）首幀在 2～3 秒內被 H3 拉回寫實；平塗 2D 撐得住。

## 7. 不採用的寫法

- 網點類的詞（halftone、dot dithering、moiré）：Qwen 只畫成極細的點，進 H3 變雜訊。
- 調色盤寫進圖片或影片提示詞：無差別作用（綠衣服、綠招牌全被吃掉）。
- 全像稜鏡光：H3 會當成衣服圖案跟著動，只用在靜態鏡（封面、劇照、`still`）。
- 水彩暈染（破壞畫面）、抽象的「童話、哥德浪漫」（只被讀成細膩線條）。
- 具體的哥德裝飾（鐵藝捲紋、尖拱）效果明顯但 Qwen 會過度增生；留給架空世界的劇本（寫法在 `Qwen風格化測試/explore6.py`）。
- 舊的紅外線預設見 `history/deprecated.md`。
