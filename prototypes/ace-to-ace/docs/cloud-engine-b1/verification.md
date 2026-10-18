# B1 驗證紀錄

2026-10-19，本機 Windows／Node v22.23.1／Chromium 151.0.7922.34。B1 基準為 B0 `a75ea74fcadcf73464c9aea42164dcb96b57509a`，獨立 worktree 與 `spike/ace-cloud-engine-b1` 分支。

## 測試結果

| 檢查 | 結果／證據 |
|---|---|
| 既有五項 regression | 全部 PASS：brake-trap、HUD attitude、flight path、airbrake/throttle、mobile power strip；`npm run test:regression` |
| B0 CloudField | PASS；每雲形 5,000 deterministic probes、位置連續性、風平流、不同高度與方向、視線積分；[field-validation.json](b0-field/field-validation.json) |
| B1 配置與霧 | PASS；seed 一致、27 個 anchor 精確等於 B0 lobes、風移動一致、密度有界、空區為零、常數場採樣；[layout-validation.json](layout-validation.json) |
| B1 WebGL 固定比較 | PASS；十組 B0/B1 pose、field、density 一致；shader runnable、draw/triangle 上限；[final/report.json](final/report.json) |
| 世界位置／轉頭 | PASS；轉開再回原 pose 的 framebuffer hash 完全相同；不重抽 seed 或位置 |
| 連續穿雲 | PASS；25 個連續位置、250 個實際 RAF 驅動步進的 [WebGL 錄影](final/traversal.webm)，最後進度 0.97189、eye density 0 |
| 入雲邊界 | PASS；220 m/s、60 Hz 的 120 幀採樣，中心 16² 平均 RGB 最大相鄰變化 0.00008170；geometryBuilds 3 → 3 |
| B0 Lab 全套 smoke | PASS；八個固定視角、六方向、返回原 pose、真實鍵盤／滑鼠／路線／風、三解析度各 cloud/clear GPU samples、觸控；[b0-lab-smoke.json](b0-lab-smoke.json) |
| B1 Lab 操作 smoke | PASS；同一套空間、鍵盤／滑鼠、播放／滑桿、風及觸控測試；[b1-controls.json](b1-controls.json)、[觸控 runtime](touch.png) |
| 正式 R2 全流程 smoke | PASS；26 張實際畫面、lookdev、手動操控、FOX2、touch stick／power strip、AI vs AI、完整對戰結果、Enter 重賽；[r2-smoke.json](r2-smoke.json) |
| 錯誤 | B0 Lab、B1 Lab 及 R2 的 console／page／HTTP asset 錯誤清單均為空，未發現 shader link 錯誤 |

B0 連續性仍為原模型：積雲最大逐幀 density delta 0.01834，層積雲 0.02083；最大逐幀 T delta 0.01697。B1 連續畫面在進度 0.10 時 density 0／T500 1，中段約 0.8253／0.00790，0.90 時回到 0／1。

邊界 pixel sweep 只量中心小區域，無法證明整張畫面所有角度均無瑕疵；十視角及連續畫面另外逐張視覺檢查。未見大面積透明排序翻轉、交叉平面或整片閃現。已完成多輪迭代，保留[前後對照](visual-iterations.md)。仍可見重複剪影、部分 MSAA 邊緣與近景視角近似。

R2 smoke 的完整 26 張原始擷取位於本機忽略目錄 `tools/out/b1-r2-smoke/`；JSON 只把絕對檔名轉成 basename。提交中另保留 [R2 chase](r2-chase.png) 與 [R2 touch](r2-touch.png)。Smoke 中 FPS 是軟體渲染診斷，非行動 GPU 測試。

## 保留範圍

相對 B0 的以下路徑 `git diff --exit-code` 為空：`src/cloud/cloud-field.js`、`src/cloud/cloud-debug-renderer.js`、`src/game/`、`src/ai/`、`src/sim/`、正式 `index.html`、`style.css`、`assets/lookdev/` 與 repository 的 `unreal/`。實作及文件全在 `prototypes/ace-to-ace/`，未新增 npm runtime 依賴。原 R2 與 B0 worktree 的 `git status --porcelain` 皆空。

R2 原始素材 Git blob 保持：

```text
sky-painting-r2.jpg     77b28531cbaf7747cb3a021d566a6d230b7e0340
cloud-paintings-r2.png  22e7e45fc6807b3f3b66cbbe25793e7a4e0dd758
```

正式 R2 入口不 import B1／CloudField；沒有新玩家按鈕、實驗開關或遊戲接線。Lab 使用既有 R2 sky texture 及 lookdev shaders 作為共同比較背景，僅唯讀，未重生／覆寫原圖或更動正式遊戲鏡頭。

## 結論與下一步

B1 已可運行並證明固定三維密度場、世界風、位置與穿雲遮蔽可共用於手繪雲渲染。兩張原創 atlas、浮雕層和局部霧具備最低可檢查成果；**尚不建議正式整合**。需先改善多方位配對與重複輪廓，並取得 iPhone 13 mini Safari 的 MSAA／depth resolve、fill-rate、記憶體及持續運行結果。完整成本與限制見 [performance.md](performance.md)，不宣稱真機 60 FPS。
