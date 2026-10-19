# Cloud Engine B2 — 固定手繪雲殼／局部霧實驗

從 B1 `996329258379383f6ed1d8bdb4ea992589be6c14` 建立獨立 worktree 與 `spike/ace-cloud-engine-b2-hybrid`。Animfix `abab83a84212c20406494784e7a3ea5ab4342630` 的 renderer／volume 原樣帶入作比較，沒有合併該分支。所有變更限於本原型。

本輪是可執行的混合方案：遠景沿用原 R2 天空；中景用固定三維雲殼與世界筆觸；近景用 B0 密度控制的四區間局部霧。它沒有 observer-facing 中景片、角度換剪影或全螢幕高步數體積積分。空間骨架與成本取捨已可檢查，**美術仍未達動畫電影品質，不建議接入正式遊戲**。

## 操作與動畫證據

在 `prototypes/ace-to-ace/` 執行 `node tools/cloud-lab-serve.mjs`，開啟 `http://127.0.0.1:8096/tools/cloud-lab.html`。此簡單靜態伺服器支援影片 byte Range，便於比較頁拖曳／逐格；沒有新依賴。

- 四個模式：B0 Debug、B1 anime billboard、B1 Animfix stable volume、B2 hybrid。切換共用 field、seed、風時間與同一 camera。
- 動畫選單含十條路線：接近、側掠、爬升、俯瞰、擦邊、進雲、雲內、出雲、90° 與 180° 繞行。拖進度／播放／鍵鼠自由飛行／觸控環視均保留在 Lab。
- 轉向路線位於雲頂上 200m，避免鄰雲遮住同一目標；低視角由側掠與爬升檢查。相機真的繞行，並非只在原地 yaw。
- [同步逐格比較頁](gallery.html)提供三模式影片。每場景每模式 90 張真實 Chromium WebGL 幀，15fps 編碼，6 秒播放涵蓋 12 秒模擬路線。沒有插幀；影片播放率不是裝置 FPS。

| 動畫 | B1 | Animfix | B2 |
|---|---|---|---|
| 十場總覽 | [影片](final/overview-anime.webm) | [影片](final/overview-stable.webm) | [影片](final/overview-hybrid.webm) |
| 側掠 | [影片](final/side-pass-anime.webm) | [影片](final/side-pass-stable.webm) | [影片](final/side-pass-hybrid.webm) |
| 純外側側掠 | [影片](side-review/side-pass-anime.webm) | [影片](side-review/side-pass-stable.webm) | [影片](side-review/side-pass-hybrid.webm) |
| 90° | [影片](final/turn90-anime.webm) | [影片](final/turn90-stable.webm) | [影片](final/turn90-hybrid.webm) |
| 180° | [影片](final/turn180-anime.webm) | [影片](final/turn180-stable.webm) | [影片](final/turn180-hybrid.webm) |
| 連續進入／穿越／離開 | [影片](traverse-review/traverse-anime.webm) | [影片](traverse-review/traverse-stable.webm) | [影片](traverse-review/traverse-hybrid.webm) |

總覽每 6 秒切換一個場景，切點是剪接。連續穿雲另外錄製原 Lab 穿越路線全長 7,400m，每模式 240 幀、16 秒播放，首尾在雲外、中途進入密區，沒有把不同雲團的進／內／出片段剪成假連續路線。正常以 220m/s 播放此路線約需 33.6 秒；離線影片播放速度不同。

各路線六個固定時刻的比較截圖是 `final/{route}-{mode}.jpg`。`motion/` 提供密集時間格與最大變化附近的相鄰格；不是只挑漂亮的一幀。原始完整 JPG 位於忽略目錄 `tools/out/cloud-b2/{round}/`，影片、接觸表與每幀 pose／density／來源雜湊提交在 [final/report.json](final/report.json)、[side-review/report.json](side-review/report.json)、[traverse-review/report.json](traverse-review/report.json)。

## 修改檔案

| 路徑 | 用途 |
|---|---|
| `src/cloud/cloud-hull.js` | B0 密度內的雕刻等值雲殼、封閉 marching tetrahedra 網格 |
| `src/cloud/cloud-hybrid-renderer.js` | 固定法線手繪投影、冷暖塊面、獨立 opaque depth 與局部霧 |
| `src/cloud/cloud-stable-renderer.js`、`cloud-volume.js` | 原樣帶入 Animfix 比較組 |
| `src/cloud/cloud-anime-renderer.js` | 僅公開既有 atlas；原 B1 shader／行為保留 |
| `tools/cloud-lab.js`、`cloud-lab.html` | 四模式與共用動畫路線；僅 Lab |
| `tools/cloud-animation-paths.js` | 共用可重現世界路線 |
| `tools/test-cloud-b2.mjs` | seed、封閉拓撲、繞序、有限數、密度支撐與路線測試 |
| `tools/cloud-b2-check.mjs` | 三模式真實逐幀錄影／截圖及世界 pose 一致性 |
| `tools/cloud-b2-perf.mjs` | 外部 GPU timer 與 CPU／資源成本、入雲連續幀檢查 |
| `tools/cloud-b2-motion.py` | 全部 JPEG 相鄰變化定位與連續幀 QA 表 |
| `tools/cloud-lab-serve.mjs`、`tools/cloud-b2-gallery-check.mjs` | 支援 byte Range 的靜態預覽，以及影片 metadata／同步播放／逐格 smoke |
| `tools/cloud-lab-check.mjs` | 新模式、播放與切換的操作 smoke |
| `tools/test-cloud-b1.mjs` | `--out` 另存結果，保留歷史 B1 證據 |
| `package.json` | 三個 B2 測試命令；無新 runtime dependency |
| `docs/cloud-engine-b2/` | 研究、成本、限制、動畫與數值證據 |

## 研究與驗證

- [方案、根因與素材](research.md)
- [逐場動畫判斷與測試](verification.md)
- [分開的 CPU／GPU／貼圖成本](performance.md)

```sh
npm run test:regression
node tools/test-cloud-field.mjs --out docs/cloud-engine-b2/b0-field
node tools/test-cloud-b1.mjs --out docs/cloud-engine-b2/b1-layout
npm run test:cloud-b2
npm run test:cloud-b2-browser
node tools/cloud-b2-check.mjs --round side-review --scene side-pass --clear-side
node tools/cloud-b2-check.mjs --round traverse-review --traverse --frames 240
npm run test:cloud-b2-perf
python tools/cloud-b2-motion.py
python tools/cloud-b2-motion.py side-review
python tools/cloud-b2-motion.py traverse-review
node tools/cloud-lab-check.mjs --renderer hybrid --skip-perf --out tools/out/b2-controls
node tools/cloud-lab-check.mjs --renderer debug --skip-perf --out tools/out/b2-debug-controls
node tools/browser-check.mjs --scenario all --out tools/out/b2-r2-smoke
# 另開終端啟動 node tools/cloud-lab-serve.mjs，再執行：
node tools/cloud-b2-gallery-check.mjs
```

瀏覽器測試沿用環境既有 Playwright／Chromium（本機 `NODE_PATH` 指向 Codex bundled Node modules、`PLAYWRIGHT_BROWSERS_PATH` 指向既有 ms-playwright cache）；影片用 FFmpeg，QA 接觸表用 Python Pillow／NumPy。沒有增加遊戲依賴。R2 天空、B0 field、正式玩法與 Unreal 不變。沒有真機 Safari 結果，不宣稱手機 60fps。
