# Ace to Ace — Cloud Engine B1

可執行的 2.5D 手繪雲最小原型。基於 B0 `a75ea74fcadcf73464c9aea42164dcb96b57509a`，分支 `spike/ace-cloud-engine-b1`；所有變更限於 `prototypes/ace-to-ace/`。

B0 CloudField 原封保留。B1 以 27 個固定世界錨點、原創多視角雲 atlas、浮雕深度及密度霧呈現可接近、擦邊、穿入與離開的雲區。雲片朝向是渲染近似，雲的位置不跟著鏡頭生成。這是可飛行與比較的原型，尚未達最終動畫電影美術品質。

## 啟動

在 `prototypes/ace-to-ace/` 執行 `python -m http.server 8080`，開啟 `http://localhost:8080/tools/cloud-lab.html`。無 build、無新 npm runtime dependency，沿用 vendored Three.js。

- 預設 **B1 Anime**，可切 **B0 Debug**；兩者共用同一 field、seed、風時間與鏡頭。Debug 快取只在需要時建立。
- 穿越／擦邊路線以 220 m/s 行進；播放或拖動進度。亦可繞行、上方、下方、自由飛行。
- 畫面拖曳環視；自由飛行 W/S 前後、A/D 側移、Q/E 升降，Shift 加速。觸控支援拖曳環視和路線滑桿。
- 雲場參數套用後才重建；診斷選項可開啟信標、網格、雲片 UV 配置，關閉密度霧或雲顯示；日光方位與高度可調。解析度預設 ½，不隨 DPR 擴大。
- `eye / plane density` 和 T500 是 B0 原始密度場診斷，不修改 AI 或飛彈鎖定。

## Runtime 證據

[固定視角比較與連續畫面檢視器](gallery.html)可在同一視角切換 B0／B1。所有下列畫面都由 Playwright 啟動本機 HTTP 與真實 Chromium WebGL 擷取，沒有使用概念圖替代。來源雜湊、座標、密度及時間保存在 [final/report.json](final/report.json)。

| 固定視角 | B0 | B1 |
|---|---|---|
| 遠方雲牆 | [Debug](final/01-wall-debug.jpg) | [Anime](final/01-wall-anime.jpg) |
| 側面繞行 | [Debug](final/02-side-debug.jpg) | [Anime](final/02-side-anime.jpg) |
| 層積雲海俯瞰 | [Debug](final/03-cloud-sea-debug.jpg) | [Anime](final/03-cloud-sea-anime.jpg) |
| 雲底仰視 | [Debug](final/04-base-debug.jpg) | [Anime](final/04-base-anime.jpg) |
| 擦過雲邊 | [Debug](final/05-skim-debug.jpg) | [Anime](final/05-skim-anime.jpg) |
| 進入 | [Debug](final/06-entry-debug.jpg) | [Anime](final/06-entry-anime.jpg) |
| 雲內 | [Debug](final/07-interior-debug.jpg) | [Anime](final/07-interior-anime.jpg) |
| 離開 | [Debug](final/08-exit-debug.jpg) | [Anime](final/08-exit-anime.jpg) |
| 同位置轉 90° | [Debug](final/09-turn90-debug.jpg) | [Anime](final/09-turn90-anime.jpg) |
| 同位置轉 180° 回看 | [Debug](final/10-turn180-debug.jpg) | [Anime](final/10-turn180-anime.jpg) |

另有 25 張同一路線連續位置的 `final/flight-00.jpg` 至 `flight-24.jpg`，以及 [實際 WebGL 穿雲錄影](final/traversal.webm)。錄影每個實際 RAF frame 推進 0.12 秒模擬時間，共 250 步；軟體渲染時的播放速度、影片編碼幀率都不能作為裝置 FPS。

## 程式、研究與驗證

| 路徑 | 用途 |
|---|---|
| [cloud-layout.js](../../src/cloud/cloud-layout.js) | 從 B0 lobes 建立固定配置、108 次局部霧採樣 |
| [cloud-anime-renderer.js](../../src/cloud/cloud-anime-renderer.js) | instancing、視角混合、深度、日光、LOD、霧合成 |
| [Cloud Lab](../../tools/cloud-lab.html) | 共用空間的 B0/B1 調試與飛行 |
| [素材與 prompts](../../assets/cloud-b1/README.md) | 原始與壓縮 atlas、來源和處理 |
| [research.md](research.md) | 美術判讀、技術比較、空間契約與簡化 |
| [visual-iterations.md](visual-iterations.md) | 實際截圖檢查與多輪修正 |
| [verification.md](verification.md) | 測試結果與 R2 保留證據 |
| [performance.md](performance.md) | CPU、GPU、貼圖與記憶體分開記錄 |

```sh
npm run test:regression
node tools/test-cloud-field.mjs --out docs/cloud-engine-b1/b0-field
npm run test:cloud-b1
npm run test:cloud-b1-browser
node tools/cloud-lab-check.mjs --out tools/out/b1-b0-lab-smoke
node tools/cloud-lab-check.mjs --renderer anime --skip-perf --out tools/out/b1-controls
node tools/browser-check.mjs --scenario all --out tools/out/b1-r2-smoke
```

Browser tests 需 Playwright／Chromium；可透過 `NODE_PATH` 與 `PLAYWRIGHT_BROWSERS_PATH` 使用環境既有安裝。沒有加入專案新依賴。

## 是否適合整合正式遊戲

**目前建議保留 Cloud Lab，尚不接入正式 Ace to Ace。** 原型證明 B0 三維密度可驅動穿雲、遮蔽與風移動，並用低幾何成本呈現手繪大輪廓。仍有重複剪影、視角近似、粗霧網格與 MSAA 邊緣的限制，也沒有 iPhone Safari 真機效能與相容性結果。

先完成真機測試及美術深度／多方位配對，再評估預設關閉的實驗接線。此版正式 R2 入口未載入 B1，天空原始圖、玩家操控、HUD、飛行物理、AI、武器及 Unreal 均未修改。
