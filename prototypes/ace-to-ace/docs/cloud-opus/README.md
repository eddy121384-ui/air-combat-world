# Ace to Ace — Opus Sky（雲的美術方向重新設計）

分支 `spike/ace-cloud-opus-art-direction`，從 B1 `996329258379383f6ed1d8bdb4ea992589be6c14` 建立的獨立 worktree。
所有變更限於 `prototypes/ace-to-ace/`。B0/B1/Animfix/B2 的程式與證據不動；正式遊戲只多一個預設關閉的 `?sky=opus`。

**一句話：形狀用 3D 生成，光用 shader 畫，遠方交給畫。**
雲是由橢球 billow 分形堆疊的世界固定 3D 物件，在面向相機的 quad 上做精確 ray-cast（畫的是幾何，不是圖片，
所以任何角度都是同一個物體）；動畫電影的明暗、晨昏線、銀邊、帶顏色的陰影全部在 shader 裡「畫光」；
無限遠仍是已接受的 R2 天空畫。為什麼前三版做不到，見 [analysis.md](analysis.md)；做法細節見 [technique.md](technique.md)。

## 看效果

| 證明什麼 | 影片（真實 Chromium WebGL 逐格渲染，24 fps） | 八格接觸表 |
|---|---|---|
| 飛近主塔（離外緣 billow 4.8 km → 0.6 km） | [approach.mp4](final/approach.mp4) | [sheet](final/approach-sheet.jpg) |
| 側掠受光雲牆（離 billow 約 140 m，壓坡度） | [sidepass.mp4](final/sidepass.mp4) | [sheet](final/sidepass-sheet.jpg) |
| 180° 繞行：順光 → 側光 → 逆光 | [orbit180.mp4](final/orbit180.mp4) | [sheet](final/orbit180-sheet.jpg) |
| 穿入、雲內、穿出積雲 | [traverse.mp4](final/traverse.mp4) | [sheet](final/traverse-sheet.jpg) |
| 雲海：俯衝穿層、雲下、拉起再穿出 | [deck.mp4](final/deck.mp4) | [sheet](final/deck-sheet.jpg) |

- 每一格都在路線的精確時間點渲染（`tools/sky-capture.mjs`），影片播放速度＝模擬速度；這是畫面證據，**不是裝置 FPS**。
- 正式遊戲實機流程（真的飛行模型、AI、HUD、自動駕駛，`?sky=opus`）：[game/](game/)，含 iPhone 13 mini 尺寸觸控 HUD 畫面。
- 本機同步看五段影片：[gallery.html](gallery.html)。
- 迭代過程（同視角、各輪對照）：[iterations/](iterations/)，說明在 [iterations.md](iterations.md)。

## 自己飛

```sh
cd prototypes/ace-to-ace && python3 -m http.server 8080
# Lab：路線播放／拖時間軸／自由飛行（方向鍵或 WASD，觸控左下拖曳）
open http://localhost:8080/tools/sky-lab.html
# 正式遊戲換上 Opus Sky（操控、HUD、AI、武器、物理完全不變）
open "http://localhost:8080/index.html?sky=opus"
# iPhone 實機效能（同一 Wi-Fi，Safari 開啟，會自動跑完五條路線並列出幀時間）
open "http://<電腦IP>:8080/tools/sky-lab.html?bench&quality=mobile"
```

Lab 參數：`?route=traverse`、`?seed=N`、`?quality=high|mobile|low`、`?bench`。

## 檔案

| 路徑 | 用途 |
|---|---|
| `src/sky/cloudscape.js` | 純 JS：佈局、積雲／雲海文法、埋藏剔除、密度與梯度查詢、海面雲影光柵、`lift` |
| `src/sky/sky-shaders.js` | billow ray-cast、畫光、sun-depth pass、天空／海／霧、雲絲、霧團 |
| `src/sky/sky-renderer.js` | three.js 組裝、一次性 sun-depth、3D 雜訊貼圖、每幀霧／雲絲、霧時間濾波 |
| `src/game/render.js` | 只加 `?sky=opus` 的開關；R2 天空／海／雲照建、隱藏 |
| `tools/sky-lab.html` / `sky-lab.js` | Lab、品質分級、自由飛行、`?bench` 實機量測 |
| `tools/sky-routes.js` | 五條確定性路線（依太陽與主塔自動取向） |
| `tools/sky-capture.mjs` | 逐格擷取 → mp4 ＋ 接觸表 |
| `tools/sky-cost.mjs` | 真實畫面的逐像素片段計數，換算到 iPhone 解析度 |
| `tools/test-opus-sky.mjs` | Node 測試：決定性、預算、形狀規則、密度、太陽走廊、路線連續性與穿雲 |
| `tools/browser-check.mjs` | 新增 `--query sky=opus`，用既有實機流程測試新天空 |

## 驗證與成本

[verification.md](verification.md)、[performance.md](performance.md)。重點：

- Chromium 實機流程（`fight` 情境，`?sky=opus`）0 console／shader／資源錯誤；五項既有回歸測試通過。
- 雲本體 1 draw call（約 2 萬個 instance），整個天空 5–7 draw calls；實測每像素雲片段 1.3–6.0 次，
  換算 iPhone 15 @2x 每幀 1.8–8 M 次 fragment invocation。**沒有 iPhone 真機數字**；`?bench` 頁是給真機量測用的。

## 尚未解決

見 [technique.md](technique.md#尚未解決刻意不做) 與 [performance.md](performance.md#風險與下一步)。最重要的三件：
近距陰影面的 billow 仍有「氣球」感；背光側缺少噴槍式柔邊；iPhone Safari 幀時間未量。
