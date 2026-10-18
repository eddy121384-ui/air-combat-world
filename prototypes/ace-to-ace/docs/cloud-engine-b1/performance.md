# B1 效能紀錄與限制

測試：Windows、Intel i7-12700、Node v22.23.1、Chromium 151.0.7922.34，ANGLE Vulkan SwiftShader。**沒有 iPhone 或 Safari 真機結果，不能宣稱 iPhone 13 mini 達到 60 FPS。** GPU timer 在此是軟體圖形後端的 elapsed time，並非實體 GPU 效能。

## CPU

獨立 Node benchmark，與 GPU 繪圖分開：

| 工作 | 中位數 | 證據 |
|---|---:|---|
| B0 密度，混合位置 | 0.4273 μs/query | [field-validation.json](b0-field/field-validation.json)，每組 100,000 次、5 組 |
| B0 密度，雲內位置 | 0.9223 μs/query | 同上 |
| B1 108 次霧查詢，積雲 | 0.0844 ms/frame | [layout-validation.json](layout-validation.json)，每組 1,000 幀、7 組 |
| B1 108 次霧查詢，層積雲 | 0.0845 ms/frame | 同上 |

瀏覽器手動逐幀實測：½ 解析度的 B1 霧採樣中位數約 0.10 ms，render submission 約 0.25 ms；1× 約 0.20 / 0.30 ms。時間精度約 0.1 ms，submission 不含 GPU 完成等待，不可當成總幀耗時。Lab 額外 T500／eye／plane 密度診斷約 0.10 ms，亦與渲染分列。27 層配置本輪建立約 0.20 ms；畫面連續 120 幀期間 geometryBuilds 始終為 3（先前切換雲形造成的三次），沒有逐幀重建。

## 圖形後端畫面成本

同一積雲內位置 `[0,3062,60]`、同一場景與鏡頭；停用自動 RAF 繪圖，手動 render 後 `gl.finish()`，讀取 `EXT_disjoint_timer_query_webgl2`，狀態切換後丟棄前兩個新樣本。完整兩 pass 成本，包含 R2 天空、海面與測試戰機，不是雲 shader 的隔離時間。

| 顯示／實際 buffer | 新樣本數 | elapsed 中位數 | 範圍 |
|---|---:|---:|---:|
| B1 640×360 | 6 | 72.99 ms | 61.94–77.57 ms |
| B0 640×360 | 6 | 225.29 ms | 179.18–243.24 ms |
| B1 1280×720 | 4 | 281.59 ms | 271.88–289.00 ms |
| B0 1280×720 | 4 | 896.17 ms | 839.12–938.71 ms |

完整樣本在 [final/report.json](final/report.json)。目標六個 fresh samples；1× 的軟體 timer 在有界等待內只完成四個，保留實際數量，未複製樣本補足。所有已收樣本 disjoint 為 0。這只支持此環境中 B1 比 B0 96-step Debug 便宜；不推論 Safari FPS、功耗或持續熱降頻。

## Draw、貼圖、記憶體與 fill-rate

- 雲本身：1 個 instanced draw、27 層、54 三角形；shader 讓 18 個次要層在 4.5–7.5 km 漸退，但仍提交 27 instances。沒有大量透明排序 draw 或每幀 3D cache。
- 完整固定場景：B1 6 calls／2,162 triangles；B0 5 calls／2,108 triangles，包含 sky、sea、fighter、合成；信標／網格預設關閉。B1 多一個雲 draw，單一深度感知霧合成 pass。
- 兩張 1024² WebP 共 **609,270 bytes（595 KiB）**；解碼成 RGBA8、含完整 mip 約 **10.67 MiB**。WebP 縮小傳輸，不是 GPU 壓縮格式。原始 PNG 僅存檔，不在 runtime 載入。
- B1 RGBA8＋depth＋4× MSAA offscreen target 粗估：640×360 約 **8.79 MiB**，1280×720 約 **35.16 MiB**。Lab 為即時切換另保留 B0 color/depth target，分別約 1.76／7.03 MiB；B0 3D 密度快取載入後另有 360 KiB。未計 canvas、R2 共用貼圖、驅動對齊、暫存 resolve 等，並非實測程序總記憶體。
- 每個覆蓋像素會讀側／頂或底兩次 atlas；霧 pass 讀三向筆觸、scene color、scene depth。27 張大輪廓仍可重疊，低 draw call 不代表低 fill-rate。4× MSAA、`discard` 與 `gl_FragDepth` 也可能限制行動 GPU 的 early-Z／tile 效率，需實測。
- 預設半解析度、pixel ratio 1，避免 DPR 放大成本。最遠次要層漸退、近片讓霧接手，限制無效覆蓋；不做 TAA、blur chain 或 B1 96-step fullscreen ray march。

## 真機驗證門檻

在 iPhone 13 mini Safari 驗證 shader／atlas、4-sample MSAA 與 depth resolve、所有角度及觸控；分別測 quarter／half／full 解析度，空場／外部雲牆／雲內／擦邊，記錄 CPU、GPU 可取得的測量、記憶體與至少十分鐘持續運行。若 fill-rate 或記憶體超預算，優先減少 MSAA／buffer 解析度、atlas 面積與近片重疊，不能只根據 SwiftShader FPS 調整遊戲品質。
