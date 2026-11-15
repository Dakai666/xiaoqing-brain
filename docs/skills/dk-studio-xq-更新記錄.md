# 小晴的 dk-studio-xq 技能更新記錄

> 小晴的技能副本在 `C:\Users\User\.agents\skills\dk-studio-xq`，DK 的在 `C:\Users\User\.claude\skills\dk-studio`。
> 兩邊各自演化；這份記錄小晴改了什麼，方便日後跟 DK 對齊時手動合併。
> （快照副本存在 `docs/skills/dk-studio-xq/`。）

---

## 2026-11-15 《紅海盜的小酒館》實戰後的規則新增

依技能自身的「知識怎麼寫回」規範：先 grep 查重複與矛盾、確認沒有跟舊規則衝突，再寫進對應技術檔。

### `tech/keyframe-qwen.md`（第 1 節 提示詞寫法）

| 新增規則 | 原因 |
|---|---|
| **生已知 IP 的角色不要寫 IP 名稱**，改寫物理特徵（`bulky crimson red power armour`、`torn ragged edges hanging from the shoulder plates`、`brass skull badge`、`jetpack backpack`） | 寫了專有名詞模型會套用遊戲既有截圖的構圖，改寫特徵反而更準 |
| **「手塗／上舊」感要明寫**：崩邊掉漆（`deliberate chipped paint along the armour edges`）、崩爛布條、鏽、油污 | 模型不會自己理解，一個字不寫就會變成全新出廠的乾淨模型 |
| **小道具用形狀描述**：`Imperial cog-shaped metal parts` | 比寫專有名詞穩 |

### `tech/video-h3.md`（第 7 節 解析度）

| 新增規則 | 原因 |
|---|---|
| ⚠️ **`--refine hd` 不是 `--hd`**：前者只是把精修參數設成 hd、解析度不變（仍 1312×736）；後者才會走 Open-H3（1920×1088） | 兩個名字很像、很容易搞混，我第一次就搞錯了 |

### `tech/editing.md`（第 2 節 之後新增「自己用 av 組短片時」）

| 新增規則 | 原因 |
|---|---|
| 靜物片段要先放大到跟影片同尺寸：`still.py … --size 1920x1088`；`--size` 的值要寫成**單一字串** | 寫成 `--size 1920 1088` 會被 argparse 當成多餘參數直接報錯 |
| **混音的交叉溶接要以 48kHz 樣本為單位**，不是影格數 | 用影格數當單位會變成每秒 24 個樣本，出來的音軌是雜訊而且長度對不上影片 |
| 影片和靜物片段尺寸不一致時先統一再接 | av 不會自動縮放 |

### `tech/style-grade.md`（第 3 節 質感段落 之後）

| 新增規則 | 原因 |
|---|---|
| **光源冷暖對比最快出世界觀**：一冷一暖兩個光源同時寫進去（廢土／戰鎚用 `a small oil lamp casting warm amber light` ＋ `cold blue daylight leaking through a narrow arrow slit`） | 比任何濾鏡都有效 |

### `reference/tools.md`（工具一覽）

| 工具 | 新增規則 |
|---|---|
| `comfy.py` | **`--aspect` 要給完整字串**（`"3:2 (Photo)"`、`"16:9 (Widescreen)"`），只寫 `"3:2"` 會被節點拒絕、`POST /prompt` 回 400 |
| `still.py` | **`--size` 的值是單一字串**（`1920x1088`） |
| free（`/free`） | 補：ComfyUI **閒置時也不會自己卸模型**，會一直占住 13.9GB VRAM；下次開工前先 `POST /free {"unload_models":true,"free_memory":true}` |

---

## 2026-11-14 工作區路徑

`SKILL.md` 的工具用法段落改成 `cd "C:/Users/User/opencode/comfyUI/<作品>"`（小晴的工作區），
並註明 DK 自己的工作區在 `C:/Users/User/CluadeCode/comfyUI`，兩邊不要混。
