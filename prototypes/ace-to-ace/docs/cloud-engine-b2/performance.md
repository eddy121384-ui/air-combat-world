# 成本與限制

Windows／Intel i7-12700、Node v22.23.1、Chromium 151、ANGLE Vulkan SwiftShader。**沒有 iPhone Safari 真機結果，沒有 60 FPS 宣稱。**影片是離線逐幀回放，與此處的 timer elapsed 不同。

## 固定資源

| 項目 | B1 原版 | Animfix | B2 |
|---|---:|---:|---:|
| 固定場景 draw calls | 6 | 5 | 10 |
| 雲相關工作 | 1 雲片＋1 霧合成 | 1 體積合成 | 1 雲殼＋1 局部霧合成，另加真實場景 depth prepass |
| 世界雲片 | 27，54 triangles | 0 | 0 |
| 新增雲幾何 | 很少 | 無 | Cu 68,000／Sc 72,512 triangles；不是每朵這個數量 |
| CPU density 查詢／renderer frame | 108 | 0 | 108 |
| 像素密度積分 | 4 個插值區間 | 最多 32 點 3D texture＋筆觸 | 4 個插值區間，沒有逐像素 density texture lookup |
| active 雲貼圖估計 | 10.67 MiB | 6.27 MiB | 5.33 MiB，共用既有 atlas |
| display geometry buffer | <0.01 MiB | 無 | Cu 1.56／Sc 1.66 MiB |
| 640×360 RT 估計 | 8.79 MiB | 1.76 MiB | 10.55 MiB |

B2 額外 depth pass 解決了雲殼穿面時 fog distance 跳變，確實增加 draw 與 RT 記憶體。RT 數值按 RGBA8＋32-bit depth、MSAA／resolve 估計，未含驅動配置／對齊，不是實測程序總 RAM。

三者都不是一般 back-to-front 排序透明片群。B2 有 **0 個排序混合雲片層**，一個 alpha-to-coverage 殼 draw；可見表面由 depth test／MSAA sample 決定。前後面仍可能先後執行 fragment，存在隱面 overdraw、4× MSAA coverage 量化及 fill-rate 成本；不能把「一個殼 draw」寫成「每個像素只算一次」。未量測真機的實際 overdraw。

Lab 為了切換比較會保留所有模式資源。B2 與 Animfix 共用 B1 atlas，沒有重複圖片載入；但新增 B2 RT 約 10.55 MiB 和 Cu geometry 約 1.56 MiB，**比較頁總保留資源增加**。B2 單模式 active atlas 減量不等於 Lab 總 RAM 減量。建殼時 JS 陣列、索引 map、格點與梯度還有暫時配置，峰值未實測。

## CPU 與圖形後端

[最終原始樣本](performance/report.json)分列 CPU 更新、提交、外部 timer elapsed、draw／triangles、RT 與 geometry。量三個暖身後的新 frame；停用 renderer 內建 timer，等待 query 時不再重畫。所有模式使用同一 field／pose／buffer，沒有把 JS submission 當 GPU 時間。

最終表格由此 JSON 的三筆中位數整理。B2 新增 scene depth pipeline，三者不是隔離單一 shader 的微基準；SwiftShader 在 CPU 執行圖形 API，結果僅供同環境相對診斷。

| 場景／實際 buffer | B1 elapsed | Animfix elapsed | B2 elapsed | B2 比 Animfix |
|---|---:|---:|---:|---:|
| 接近／640×360 | 85.98ms | 553.47ms | 205.28ms | −62.9% |
| 接近／1280×720 | 332.06ms | 1173.45ms | 485.88ms | −58.6% |
| 雲內／640×360 | 70.29ms | 168.11ms | 125.75ms | −25.2% |
| 雲內／1280×720 | 320.76ms | 679.85ms | 356.34ms | −47.6% |

B2 在這些樣本低於 Animfix，**仍比原 B1 高約 11–139%**。中位 CPU 更新 B1 fog 約 0.1–0.2ms、Animfix 約低於0.1ms解析度、B2 約0.1–0.2ms；提交各約0.3–0.6ms。這些與數百毫秒的 SwiftShader elapsed 明確不同。每格只有三筆樣本，不是長時間統計或手機 FPS。

CPU renderer 更新通常約 0.1–0.2ms，可能落在瀏覽器約 0.1ms 計時解析度內；零讀數不代表沒有工作。Lab 的 B0 T500 診斷查詢另外計量。B2 geometry 建立同步進行，桌面約半秒至一秒以上，受測試期間 CPU 負載影響；[hull-validation.json](hull-validation.json)保留實際數值，不能把暖身後建殼時間當手機首次載入時間。飛行、風移動與轉向不重建。

## 手機可行性判斷

B2 減少 Animfix 的逐像素體積 lookup，但用更多 triangles、MSAA、opaque depth pass 與 CPU 霧查詢交換。必須在 iPhone 13 mini Safari 實測半解析度與四分之一解析度、外部雲牆、雲邊／切線、雲內和十分鐘熱負載，才能判斷平台可行性。目前只證明可運行與相對取捨，不證明手機幀率。

下一步若保留雲殼路線，應先降低硬殼／岩塊觀感、減少同步建殼負擔，再依真機資料評估深度 pass／MSAA／霧方向格，而不是再增加 ray march 步數。不能只因比 Animfix 便宜就直接整合正式遊戲。
