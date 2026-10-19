# 成本與行動裝置限制

環境：Windows、Intel i7-12700、Node v22.23.1、Chromium 151 / ANGLE Vulkan SwiftShader。沒有 iPhone Safari 真機結果，不宣稱 60 FPS，也不從離線影片的 15 fps 推論執行速度。

## 固定資源與工作量

| 項目 | 原 B1 | Animfix | 差異／解讀 |
|---|---:|---:|---|
| 雲相關 draw | 雲片 1＋霧合成 1 | 體積合成 1 | 少一個 draw |
| 一般固定場景 draw／triangles | 6／2162 | 5／2108 | 包含既有天空、海面與戰機；無信標 |
| 雲片 | 27 張、54 triangles | 0 張 | 原版是 alpha-to-coverage，不是一般排序透明混合 |
| 一條有效視線 | 多片覆蓋＋4 段霧 | 最多 32 點；每個非空點 density/normal 1 次＋paint 3 次 lookup | 不以低 draw call 代替 fill-rate 評估 |
| GPU active texture 估計 | 10.67 MiB，兩張 1024² 含 mip | 6.27 MiB，一張 atlas＋0.9375 MiB RGBA8 volume | 約少 4.40 MiB／41.2%；非整個 Lab 程序記憶體 |
| CPU 每幀密度查詢（renderer） | 108 次 | 0 次 | 變為 GPU cache 查詢；Lab T500 診斷仍另外查原 B0 |
| 參數套用的工作 | 27 anchor／尺寸配置 | 245,760 個 B0 density 值＋世界梯度 | 同步建 cache，首次積雲約 229 ms、層積雲約 207 ms |
| 640×360 renderer RT 估計 | 8.79 MiB，4× MSAA＋resolve | 1.76 MiB，color＋depth | 少約 7.03 MiB；戰機邊緣也失去這層 MSAA |

獨立 cache 建立與誤差見 [volume-validation.json](volume-validation.json)。CPU cache 只在 field／參數改變時建立，飛行、鏡頭轉向與風移動不重建。暫存 float density 約 0.94 MiB，輸出 RGBA8 再約 0.94 MiB；這些是數組大小，未含 GC／驅動等程序成本。

比較 Lab 保留三個 renderer。Animfix 共用原 B1 的 atlas Texture，沒有重複載入，但仍保留原版第二張 atlas 與所有 render targets，所以 **Lab 總保留資源反而增加**：新增 0.94 MiB volume，半解析度再加約 1.76 MiB RT。B0 選用後另有原來的 360 KiB density cache。不能把 active renderer 的減量寫成比較頁總記憶體減量。

## 同機 CPU／圖形後端測量

最終獨立樣本見 [perf-final/report.json](perf-final/report.json)。同一 field／pose、相同實際 buffer，停用自動 RAF 及 renderer 內建 timer；暖身後，以外部 raw GL query 分別量三個新幀。等待 query 可讀時只輪詢，不再重畫。所有數值為完整 scene＋composite，不是雲 shader 隔離成本。CPU update／fog、submission、timer elapsed 分列。

| 場景／buffer | 原 B1 elapsed 中位數 | Animfix elapsed 中位數 | 比率 | 各模式樣本 |
|---|---:|---:|---:|---:|
| 接近／640×360 | 65.61 ms | 472.70 ms | 7.21× | 3 |
| 接近／1280×720 | 265.73 ms | 967.54 ms | 3.64× | 3 |
| 雲內／640×360 | 72.32 ms | 139.44 ms | 1.93× | 3 |
| 雲內／1280×720 | 282.10 ms | 557.32 ms | 1.98× | 3 |

本機 CPU update 的新模式中位數低於瀏覽器約 0.1 ms 的計時解析度，不能寫成零成本；原 B1 fog CPU 約 0–0.3 ms。兩者 submission 約 0.3–0.4 ms，與 elapsed 明確不同。`finishWallMs` 與 timer 結果在此環境不一致，因此不拿它作 GPU 完成時間。

初版 query 輪詢會重畫大量未計量幀，效能資料保留在 [baseline-reference.json](iterations/baseline-reference.json) 的 `perf`，僅供迭代追溯，不與本表混用。明確 LOD 修正了非一致控制流內的 mip 查詢定義，但**最終量測仍比原 B1 昂貴，沒有通過輕量效能判斷**。少一個 draw 和較少 active texture 都無法抵銷逐像素的體積／筆觸採樣。

GPU 比較包含兩個 renderer 的不同 pipeline：原版有 4× MSAA 及透明覆蓋率片，Animfix 沒有 MSAA，但增加體積／筆觸採樣。這不是單一 shader 的隔離實驗。SwiftShader 在 CPU 實作圖形 API，elapsed 只是相對診斷，不代表 iPhone GPU、熱降頻或 Safari 相容性。

## 尚需真機確認

32 個步進仍可能受 fragment／texture bandwidth 限制；世界 cache 讓形體穩定，沒有自動令積分變便宜。先在 iPhone 13 mini Safari 比較 quarter／half 解析度、外部雲牆／切線側掠／雲內及十分鐘持續運行，分開量 JS、GPU 可取得的成本及記憶體。首次約 0.2 秒的桌面同步建 cache，在手機可能更慢；目前不支援飛行中持續改參數的平滑重建。

粗 cache／有限步進會犧牲細雲絲、切線精度與明暗穩定；原版 MSAA 移除後，戰機細邊可能較鋸齒。應先以實機資料決定步數、解析度與 cache 策略，不能僅依 SwiftShader FPS 增減品質。
