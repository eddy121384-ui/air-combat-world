# 驗證

環境：雲端容器，Node 22，Playwright 1.56 Chromium headless（ANGLE／SwiftShader 軟體 WebGL2）。
**沒有 iPhone、沒有 Safari／WebKit 執行環境**（容器只有 Chromium，未另行下載瀏覽器）。

## 指令與結果

| 指令 | 檢查 | 結果 |
|---|---|---|
| `npm run test:regression` | 既有五項：brake trap、HUD 姿態、FPM 飛行路徑、減速板／油門、手機動力條 | PASS |
| `npm run test:sky` | 同 seed 位元相同、不同 seed 不同；全部有限值；billow 預算 8k–26k；各類雲數量；每顆 billow 在平底之上有體積；核心密度 1、9 km 高空 0、雲海底下 0；梯度為單位向量；**主塔太陽走廊 24 個取樣中被遮 ≤ 2**；海面雲影可重現且覆蓋 15–85%；`lift` 精確平移；五條路線全程有限且相機連續；traverse 真的入雲出雲、deck 真的穿過雲海 | PASS（19,974 billow、生成 0.9 s） |
| `node tools/sky-capture.mjs --stills` | 五條路線 × 多時刻真實 WebGL 截圖，收 console／pageerror／資源錯誤 | 每輪 0 錯誤（R0–R18） |
| `npm run sky:videos` | 五條路線逐格渲染 mp4（24 fps，960×540） | 見 [final/report.json](final/report.json) |
| `node tools/sky-cost.mjs` | 真實畫面逐像素片段計數 | [cost-high.json](cost-high.json)、[cost-mobile.json](cost-mobile.json) |
| `node tools/sky-bench-check.mjs` | 實機量測頁 `?bench=quick&quality=mobile` 跑完五條路線並輸出可複製結果 | PASS |
| `npm run test:sky-game` | 正式遊戲 `?sky=opus`：自動駕駛 pvai 對戰 30 秒，6 張截圖、狀態、console | 0 錯誤；AI `ENGAGE/intercept` 正常、玩家機 2.99–3.06 km 高度飛行 |
| `browser-check.mjs --scenario touch --query sky=opus` | iPhone 13 mini 尺寸觸控：搖桿放手保持、重觸、油門＋搖桿同時、AB／BRK、飛彈 | PASS，0 錯誤（[畫面](game/iphone-touch-stick-turn.jpg)） |
| `browser-check.mjs --scenario lookdev`（不加參數） | 原 R2 路徑：天空／雲圖載入、shader、近雲、俯衝、接縫、天頂、殘骸 | PASS，0 錯誤：預設遊戲未受影響 |
| `npm test` | regression ＋ B0 cloud field ＋ Opus Sky | PASS |

## 確認沒有動到的東西

- `src/sim/`、`src/ai/`、`src/game/hud.js`、`input.js`、`main.js`、`models.js`、`lookdev.js`：未修改。
- `src/game/render.js`：只增加 `?sky=opus` 才執行的 `buildOpusSky()`／`updateOpusSky()`；沒有參數時走原 R2 路徑。
- B0 `cloud-field.js`、B1 `cloud-anime-renderer.js` 與所有既有素材、文件、證據：未修改。
- 未新增任何 npm 依賴或外部素材；沿用 vendored three.js r180 與 R2 天空畫。
- `tools/browser-check.mjs` 只多 `--query`，預設行為不變。

## 這些測試證明不了的

- iPhone Safari 的幀時間、降頻、MSAA alpha-to-coverage 的實際外觀。
- 長時間自由飛行時，玩家會不會在某些角度覺得雲「假」——目前證據是五條設計過的路線加一段 AI 對戰。
- 美術品質是否達到「動畫電影」：這是主觀判斷，請直接看 [final/](final/) 影片。
