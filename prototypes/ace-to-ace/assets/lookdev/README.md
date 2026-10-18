# Ace to Ace — original NPR assets

## 第二輪：背景畫與少量中景雲（目前 runtime 使用）

使用內建 **ImageGen** 產生兩張原創背景畫，無外部圖像輸入、無電影畫面取樣。
本輪保留生成原圖和完整 prompt，並提交所有遊戲實際載入的輸出：

| 檔案 | 用途 |
|---|---|
| `source/r2-sky.png` | 原始 1774 × 887 天空畫，作者素材，不由遊戲載入 |
| `source/r2-clouds.png` | 原始 1774 × 887 RGBA 雲形畫，作者素材，不由遊戲載入 |
| `r2-generation-prompts.json` | 內建 ImageGen 的兩段完整 prompt；生成本身非決定性 |
| `sky-painting-r2.jpg` | 1536 × 768 runtime 天空背景，355,817 bytes；海面共用同張貼圖 |
| `cloud-paintings-r2.png` | 1024 × 512 四格 runtime 雲畫，358,372 bytes |

從已提交原圖重新匯出（不需 API 或網路）：

```sh
python tools/prepare-lookdev-r2-assets.py
```

工具只做尺寸、JPEG 壓縮、明確記錄的四個裁切區域、透明 gutter 與 alpha 邊緣整理。
Pillow / NumPy 僅為作者工具依賴。近零 alpha 內的不可見色值不參與濾波，保留原圖以供檢查。
runtime 兩張貼圖約 **697 KiB**；按 RGBA8 加完整 mip chain 估算約 **8.67 MiB GPU 記憶體**，
其中天空約 6 MiB、雲圖約 2.67 MiB。原始 PNG 合計約 3.73 MiB，不在遊戲的請求路徑內。

## 第一輪：程序雲（歷史實驗，保留以便回退）

`cloud-atlas.png`：1024 × 512 RGBA，四格各 512 × 256。低雲、雲塔與不對稱雲冠，
以奶油色亮面、珍珠灰中間調及藍紫色陰影組成，含輕微筆觸與透明邊緣。

來源是本原型的 [`tools/generate-lookdev-clouds.py`](../../tools/generate-lookdev-clouds.py)，
由固定種子的橢圓距離場、分階色塊與程序噪聲產生。沒有使用外部圖片、網路下載、
使用者參考圖的像素，或第三方美術素材；沒有外部圖像授權依賴。

重新產生（只有作者工具需要 Python、NumPy 與 Pillow；遊戲不需要）：

```sh
python tools/generate-lookdev-clouds.py
```

本次生成環境：Python 3.12.14、NumPy 2.3.5、Pillow 12.3.0。
PNG 約 185 KiB；RGBA 解碼加完整 mip chain 約 2.67 MiB。
四格均留透明邊，避免 mipmap 採到相鄰雲形；透明 texel 保留淡灰 RGB 以減少黑邊。
僅供 Ace to Ace 小型風格實驗使用，並不定義 Skyfront Homeland 主專案美術方向。
