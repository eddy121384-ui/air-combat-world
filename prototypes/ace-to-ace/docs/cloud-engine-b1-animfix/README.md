# Cloud Engine B1 — Animfix 空間修正實驗

基準 `996329258379383f6ed1d8bdb4ea992589be6c14`；分支 `spike/ace-cloud-engine-b1-animfix`。本輪以動畫空間一致性為優先，不生成新插畫，不更動 R2 正式遊戲。

**結果：**新增固定三維密度＋世界筆觸的可執行比較模式，移除近中景追隨觀察點的雲片、視角剪影混合與中心距離 fade。原 B1 保留供同路線對照。空間表示穩定性改善，但原版精緻插畫剪影沒有完整保留下來，仍是研究原型，不建議接入正式遊戲。

## 操作

在 `prototypes/ace-to-ace/` 執行 `python -m http.server 8080`，開啟 `/tools/cloud-lab.html`。

- 預設 **B1 Animfix 固定體積**；可切 **B1 原版 billboard** 或 **B0 Debug**。共用 CloudField、seed、鏡頭、參數與風時間。
- 動畫驗證選單提供九條連續路線，按「播放動畫驗證」；每條 12 秒模擬時間。亦可拖進度、使用原來的自由飛行與環視控制。
- 診斷選項「原版雲片／新體積法線」：原版顯示 UV 配置，新版顯示世界密度梯度。原版密度霧開關只作用於原 B1；Animfix 的內外遮蔽是同一介質，沒有獨立霧接手。
- 風移動只更新世界偏移，不重建 cache。雲場套用／切換雲形時，才同步建立顯示 cache，會有短暫停頓。

## 先看動畫

[同步、逐格比較頁](gallery.html)提供同一場景的前後錄影、進度列與前後一格。每段為 180 個真實 Chromium WebGL 幀，15 fps 編碼、12 秒播放；這是固定路線的離線逐幀回放，不能作為裝置 FPS。未插幀，也未用生成圖片取代執行畫面。

| 場景 | 原 B1 | Animfix |
|---|---|---|
| 九場景總覽（108 秒） | [影片](final/overview-anime.webm) | [影片](final/overview-stable.webm) |
| 接近單一前緣雲團 | [影片](final/approach-anime.webm) | [影片](final/approach-stable.webm) |
| 側面掠過 | [影片](final/side-pass-anime.webm) | [影片](final/side-pass-stable.webm) |
| 雲底爬升至雲頂 | [影片](final/climb-anime.webm) | [影片](final/climb-stable.webm) |
| 雲海上方看雲牆 | [影片](final/sea-wall-anime.webm) | [影片](final/sea-wall-stable.webm) |
| 進入雲層 | [影片](final/entry-anime.webm) | [影片](final/entry-stable.webm) |
| 雲內前飛 | [影片](final/inside-anime.webm) | [影片](final/inside-stable.webm) |
| 穿出雲層 | [影片](final/exit-anime.webm) | [影片](final/exit-stable.webm) |
| 繞同一雲團轉向 90° | [影片](final/turn90-anime.webm) | [影片](final/turn90-stable.webm) |
| 繞同一雲團轉向 180° | [影片](final/turn180-anime.webm) | [影片](final/turn180-stable.webm) |
| 較高視點 180° 複核 | [影片](orbit-review/turn180-anime.webm) | [影片](orbit-review/turn180-stable.webm) |

轉向採用移動眼睛的繞行，能揭露原版 billboard；只在同一位置轉鏡頭不足以驗證這個問題。低位 180° 後半段會被其他雲團真實遮蔽，因此另附較高視點複核；沒有移走鄰雲或重寫 CloudField。前緣單一目標雲團取自原場右前組，遠處其他雲仍存在。

每個場景另外有六個連續時刻的 contact sheet JPEG；完整逐格 JPG 在忽略目錄 `tools/out/cloud-animfix/{round}/`。錄影與 [final/report.json](final/report.json)一起提交，包含每幀世界 pose、density、T500、build 次數與核心來源雜湊。

## 實作與修改檔案

| 檔案 | 改動 |
|---|---|
| [cloud-volume.js](../../src/cloud/cloud-volume.js) | 新增固定 RGBA8 density／gradient cache 與數值重建 helper |
| [cloud-stable-renderer.js](../../src/cloud/cloud-stable-renderer.js) | 新增有界 32 點積分、逐點世界筆觸及深度遮蔽；無 billboard |
| [cloud-anime-renderer.js](../../src/cloud/cloud-anime-renderer.js) | 僅公開既有 atlas 供共用，原 B1 shader 與行為保留 |
| [cloud-animation-paths.js](../../tools/cloud-animation-paths.js) | 九條共用、連續、可重現路線 |
| [cloud-lab.html](../../tools/cloud-lab.html)、[cloud-lab.js](../../tools/cloud-lab.js) | 比較模式、動畫播放及檢查 API，僅 Lab |
| [test-cloud-animfix.mjs](../../tools/test-cloud-animfix.mjs) | 新增 cache deterministic、誤差、風移動、路線與採樣區域測試 |
| [cloud-animfix-check.mjs](../../tools/cloud-animfix-check.mjs) | 真實 WebGL 逐幀、影片、視線對照、CPU／GPU 比較與邊界檢查 |
| [cloud-animfix-motion.py](../../tools/cloud-animfix-motion.py) | 檢查完整連續幀，定位最大畫面變化並產生密集／相鄰幀 QA 接觸表 |
| [cloud-animfix-perf.mjs](../../tools/cloud-animfix-perf.mjs) | 獨立 raw GL timer；等待 query 時不重畫，分列 CPU／GPU |
| [cloud-lab-check.mjs](../../tools/cloud-lab-check.mjs) | 增加 stable 模式及真實動畫選單／模式切換 smoke |
| [test-cloud-b1.mjs](../../tools/test-cloud-b1.mjs) | 增加 `--out`，避免改寫舊 B1 證據 |
| [package.json](../../package.json) | 新增兩個 animfix 測試命令，無新依賴 |
| `docs/cloud-engine-b1-animfix/` | 原因分析、錄影、逐格接觸表、驗證與成本紀錄 |

## 研究與驗證

- [根因、方案比較與三層距離策略](analysis.md)
- [逐場景判斷、測試結果及未解問題](verification.md)
- [CPU／GPU／貼圖／render target 成本](performance.md)
- [cache 數值結果](volume-validation.json)

```sh
npm run test:regression
node tools/test-cloud-field.mjs --out docs/cloud-engine-b1-animfix/b0-field
node tools/test-cloud-b1.mjs --out docs/cloud-engine-b1-animfix/b1-layout
npm run test:cloud-animfix
npm run test:cloud-animfix-browser
npm run test:cloud-animfix-perf
node tools/cloud-animfix-check.mjs --round orbit-review --scene turn180 --elevated --clips-only
python tools/cloud-animfix-motion.py
node tools/cloud-lab-check.mjs --renderer stable --skip-perf --out tools/out/animfix-controls
node tools/cloud-lab-check.mjs --renderer debug --skip-perf --out tools/out/animfix-b0-controls
node tools/browser-check.mjs --scenario all --out tools/out/animfix-r2-smoke
```

瀏覽器驗證需環境既有 Playwright／Chromium；影片編碼使用 FFmpeg，逐幀 QA 使用 Pillow。cache／數值測試只需 Node。沿用既有原創 [B1 素材與 prompts](../../assets/cloud-b1/README.md)，沒有新增圖片或重新生成 R2 天空。

最終 Animfix 重新擷取後，原 B1 控制組使用 [baseline-reference.json](iterations/baseline-reference.json) 與 [orbit-baseline-reference.json](iterations/orbit-baseline-reference.json) 的實際舊錄製。工具先核對 field、原 B1 renderer、Lab 與路線來源雜湊，再核對每幀位置、方向及 density。兩批擷取時間與來源分開記錄，沒有用新模式冒充原版。

## 尚未完成

固定體積解決了表示法的主要矛盾，卻沒有自動解決美術或成本。雲輪廓較圓、柔，近景筆觸與暗部層次偏弱；粗採樣可能呼吸，且參數變更會同步建立 cache。最終 SwiftShader elapsed 仍比原 B1 高約 1.9–7.2 倍，手機可行性尚未證明，不宣稱 60 FPS。此版僅是空間修正實驗，**不通過正式整合判斷**。下一步應比較更低 fill-rate 的固定殼／世界材質方案，並保留本版作三維一致性對照。
