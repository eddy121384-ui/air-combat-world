# B0 畫面成本

測量日期：2026-10-18T13:09:48.794Z；Chromium 151.0.7922.34。

實際 renderer：ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)。

**這是 SwiftShader 軟體渲染結果，GPU timer 是渲染後端的計時，不是 iPhone 或任何硬體 GPU 實測。沒有用 FPS 推論手機效能。**

方法：固定層積雲內鏡頭，96 個視線積分樣本；同一場景分別開啟／關閉雲遮蔽。使用 EXT_disjoint_timer_query_webgl2，分離 JS 提交時間；每次切換後暖機，並丟棄第一個完成的 query，排除切換前唯一可能仍在途的畫格，再收集六個新的有效 timer 樣本。

| 內部解析度 | 雲遮蔽 | 畫面 timer 中位數 ms | timer 範圍 ms | CPU render submission 中位數 ms |
|---|---|---:|---:|---:|
| 320×180 | 開 | 43.91 | 41.18–65.55 | 0.30 |
| 320×180 | 關 | 1.52 | 1.38–6.17 | 0.30 |
| 640×360 | 開 | 170.47 | 163.99–220.35 | 0.35 |
| 640×360 | 關 | 4.40 | 4.32–4.47 | 0.20 |
| 1280×720 | 開 | 848.72 | 783.77–961.03 | 0.25 |
| 1280×720 | 關 | 26.29 | 18.10–28.76 | 0.30 |

本次層積雲密度快取建構 312.2 ms；密度體積 96×48×80，共 360 KiB，不含 color/depth render targets、幾何與驅動額外配置。雲內場景總共 9 draw calls。

上表為兩 pass 的完整畫面成本：opaque scene + 雲合成，不是單一密度函式的成本。CPU 雲場查詢獨立量測見 verification.md；不能把 render submission 當成 GPU 完成時間。

軟體後端在完整解析度尤其昂貴，B0 沒有以此聲稱達到手機效能目標。六個樣本只提供有界診斷，不代表持續負載、熱降頻或穩定尾端延遲。B1 應以世界座標錨定的少量手繪雲片與近場霧替換此 Debug 積分器，並在真 iPhone Safari 上測量。

原始資料：browser-validation.json，包含所有有效樣本與 JS 提交時間。
