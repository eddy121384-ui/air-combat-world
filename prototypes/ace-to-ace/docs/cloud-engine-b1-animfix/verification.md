# 動畫驗證與本輪判斷

## 結果

本輪交付的是**空間修正實驗**。固定三維表示消除了追隨觀察點的片面、無對應關係的角度剪影混合及整片中心距離 fade；數值與功能檢查通過。**美術與 GPU 成本仍未達整合條件，不能把本輪視為正式 B1 的替換版本。**

| 動態場景 | 實際觀察／判斷 |
|---|---|
| 接近單一前緣雲團 | 大輪廓依三維密度放大，沒有近中心時整幅淡出的模式；外形較圓柔，插畫細節明顯少於原版 |
| 側掠 | 能看出從雲旁及局部穿過邊界的遮蔽；表面不旋轉成正面海報，但缺少清楚的手繪局部特徵，速度感仍可改善 |
| 雲底爬升至雲頂 | 不再從 base 畫切成 side／top 畫；出雲時天空逐步恢復。輪廓過柔及頂部細節不足仍存在 |
| 雲海上方看雲牆 | 空間關係穩定；原版更有插畫層次，新版不構成美術品質提升 |
| 進入 | 沒有片群按中心距離整片消失後由另一層 fog 接手；持續在同一介質內積分。近景會變得偏均勻，不能宣稱雲內結構已完成 |
| 雲內前飛 | density／色調與世界位置相連；本輪仍偏一般霧感，視覺改善有限 |
| 穿出 | 能見度連續恢復，雲留在世界後方；兩版原本都較平順，此項沒有宣稱巨幅改善 |
| 90°／180° 繞行 | 不再以眼睛方向重算雲體朝向／輪廓；低位 180° 後半段有鄰雲真實遮蔽，高位複核另外保留同一目標的外部觀察 |

每段 180 個真實 WebGL 幀、15 fps 離線回放，共九場景的前後對照、兩段 108 秒總覽，另有高位 180° 前後複核。沒有插幀或用生成圖代替執行畫面。最終新 renderer 重新擷取；原 B1 控制組來源雜湊與每幀 pose／direction／density 均核對一致，擷取批次分別保存。

## 逐幀檢查

完整 3,240 個前後 runtime 幀均納入 [motion/report.json](motion/report.json) 的全畫面低解析度 RGB 差檢查；九個新版的密集 16 格序列與四個重點場景最大變化附近的六個**相鄰**幀另作視覺檢查。這比只看固定角度截圖更能暴露轉向或淡出變化。

例如進雲原版最大全畫面平均 RGB delta 約 0.0342，新版約 0.00517；但新版較低反差、較少細節也會降低差值，**不能據此把品質評為較高**。低位 180° 兩版最大差值相近，說明自然遮蔽和相機運動也會造成大變化。檢查未見整張 billboard 翻面或整片中心 fade；仍可見較柔的體積邊界、切線取樣與明暗呼吸風險。

初版材質拉伸與投影條紋保留為 [加權中心問題](iterations/centroid-stretch.jpg)、[法線選圖問題](iterations/normal-projection-stripes.jpg)。最終改為逐點固定世界材質與 explicit LOD。

## 自動驗證

| 檢查 | 結果／證據 |
|---|---|
| 原有五項 regression | PASS：brake-trap、HUD attitude、flight path、airbrake/throttle、mobile power strip |
| B0 CloudField | PASS；[b0-field/field-validation.json](b0-field/field-validation.json)，連續性與視線積分原值不變 |
| 原 B1 配置／霧 | PASS；[b1-layout/layout-validation.json](b1-layout/layout-validation.json) |
| 新 cache | PASS；[volume-validation.json](volume-validation.json)，seed 可重現、不同 seed 改變、風平流誤差小於 1e-9；積雲 max rho error 0.0601、p95 0.0105，層積雲 max 0.0437、p95 0.00841 |
| 九條最終動態路線 | PASS；[final/report.json](final/report.json)，每幀原版／新版 pose、direction、density 一致，移動期間沒有 cache 重建 |
| 高位 180° | PASS；[orbit-review/report.json](orbit-review/report.json)，同一目標、相同路線，沒有移走鄰雲 |
| GPU 視線／原 B0 | PASS；72 條實際 readPixels 透射率對原函數 15 m 中點積分，最大差 0.08144；不是僅比較 CPU 讀數 |
| 最終入雲邊界 | PASS；[perf-final/report.json](perf-final/report.json)，220 m/s、60 Hz 取 120 幀，320×180 buffer 的中心平均 RGB 最大 delta 0.00284，build counter 1→1 |
| Lab 控制 | PASS；[controls.json](controls.json)，鍵鼠自由飛行、風、滑桿、播放、動畫選單／模式切換、觸控；共用 Lab 流程不變，最終 shader 另由上述片段與 timer harness 驗證 |
| B0 Debug 操作 | PASS；[b0-controls.json](b0-controls.json)，保留舊空間／方向／觸控 smoke；略過重複的 B0 GPU benchmark |
| 正式 R2 browser smoke | PASS；[r2-smoke.json](r2-smoke.json)，26 張實際畫面、觸控 power strip、FOX2、對戰結果、Enter 重賽，錯誤清單空 |
| Console／shader／資產 | 動態、控制與 R2 smoke 的錯誤清單均空，最終 shader program runnable |

代表性視線與有限幀序列不代表所有相機／極端參數都已驗證。相同 seed、返回原 pose 像素相同、build counter 不變，各自都不足以單獨證明雲不是 billboard；本輪另以 shader 的固定三維場、實際 GPU 視線對照及移動眼睛的繞行驗證。

## 保留與未過關事項

`cloud-field.js`、`cloud-layout.js`、B0 debug renderer、整個既有 `assets/`、正式 `src/game/`、`src/ai/`、`src/sim/`、`index.html`、`style.css` 與 `unreal/` 相對基準無 diff。沒有增加遊戲依賴或接入正式入口。#35／#41／#42 維持 Draft，不 merge、不 force-push。

GPU elapsed 仍約為原 B1 的 1.9–7.2 倍；詳見 [performance.md](performance.md)。沒有 iPhone Safari 結果，手機可行性未證明。手繪輪廓、雲內筆觸與細節品質也退步，因此本輪不通過正式整合判斷。下一輪宜比較更低 fill-rate 的固定雲殼／世界材質，保留此版作三維可見度與空間一致性的對照。
