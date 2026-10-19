# 表示法、根因與取捨

## 先前成果的判斷

B1 用 eye-to-centre 建立 billboard basis；仰角還控制片高與互不對應的 top／side／base RGB/alpha。世界錨點沒有動，但表面與剪影會動。中心距離的整片淡出與獨立霧接手進一步造成融化。原 B1 alpha-to-coverage 並非一般排序透明；近距破綻不能全部歸因於排序。

Animfix 移除表面，使用固定 B0 density/gradient cache 的 32 點體積合成。空間一致，但沿用平滑橢球密度會產生柔圓輪廓；大量逐像素取樣與三向筆觸使成本上升。此輪原樣保留其兩個 source 作比較，不重新建造密度物理。

| 方案 | 優點 | 風險／本輪選擇 |
|---|---|---|
| 固定交叉片 | 幾何少、可沿用插畫 | 交線、側面薄片、透明重疊；不選為中景本體 |
| 固定曲面簇 | 方向固定 | 相交曲面、內部接縫與多層覆蓋；暫不增加 |
| 封閉三維雲殼＋局部霧 | 剪影、法線、筆觸屬於同一固定物體；深度測試控制可見面 | 表面過硬、穿面交接；選作 B2 可檢查的最小方案 |
| 繼續增加體積採樣 | 邊界軟、介質連續 | 已知的成本／柔圓問題；不增加步數 |

## B2 的三層

遠景完全沿用 R2 `sky-painting-r2.jpg` 與原天空 shader，沒有重畫天空，也沒有讓遠景圖承擔近景物體。B1 世界 billboard 只在原版比較模式出現。

中景用 B0 density 的正支撐建立等值殼。固定斜向肩部／凹口控制等值門檻，再由三組不等高、斜向塔頂與較平雲底雕刻外形；這些是**顯示設計**，不是新的物理。塔頂取整個場的連續最大值，避免最近群組切換的 Voronoi 斷面。沒有球體 mesh 堆疊、頂點 shader 噪聲位移或視角換剪影。

60×26×50 格點只在 field／參數套用時建立。六個一致 tetrahedra 分割每個 cell，共用邊頂點，保留封閉表面；非常接近零的格值保持原符號並作小幅鉗制，避免浮點極細三角形。繞序根據 tetra 的內外方向，不用可能不可靠的平滑梯度逐面翻向。全部雲群合成一個 indexed geometry，一次殼 draw；無逐幀 cache 重建或距離 LOD 換模。

手繪外觀取既有原創 B1 atlas 的一格，依固定表面法線作三向投影。法線決定投影權重，鏡頭不參與。RGB 的局部明度用作筆觸和大塊冷暖分區；暖白／金、藍紫、底部冷暗與空氣透視採設計化光照，沒有真實多重散射、PBR 高光或黑描邊。它仍可能像貼了畫的硬物體，不能因用了原畫就宣稱達到電影美術。

近景使用 3×3 視線、4 區間、每區間 3 個 B0 density probe，共 108 次 CPU 查詢。區間為 0–60–180–400–900m；GPU 只合成四段透射，不作逐像素 density ray march。世界固定的三維 pigment value field 保留淡冷暖層次，不依鏡頭切換圖。霧仍是方向插值近似，不能當成數值真值。

雲殼始終存在；只有距離眼睛 2–90m 的局部表面 coverage 逐漸降低，沒有整團中心 fade。霧也一直存在，沒有進雲開關。重要修正是獨立 opaque depth prepass：雲殼不是霧的 opaque 終點，否則穿越表面時 fog distance 會跳變。真實戰機／海面仍依深度限制霧，代價是多一個深度 pass／render target。

## 實際淘汰的迭代

1. 各向平均 2D 材質投影形成垂直／水平尺紋，失敗。表面改為固定法線加權，內部改為三維 pigment；沒有回到視角選圖。
2. 低格距和太短的凹口波長讓殼變尖碎。增至目前格數、放寬雕刻尺度，並加入塔頂／雲底設計。外形仍有面片感，屬已知限制。
3. 刪去極細三角形產生 22 條開口；修正格值與拓撲，不略過三角形。梯度逐面決定繞序又造成 224 條不一致邊，改用 tetra 內外方向後兩種雲形均為零。
4. 共用 hull depth 的入雲測試最大中心 RGB delta 0.0776，未通過既有 0.06 門檻。[失敗紀錄](iterations/depth-handoff-failure.json)保留；改用獨立 opaque depth 與局部霧後複測，沒有放寬門檻。

`iteration-1/` 至 `iteration-5/` 為真實早期接觸表，不是最終品質證據。最終交付依 `final/` 及 `motion/` 判讀。

## 來源與素材

- [Three.js BufferGeometry](https://threejs.org/docs/pages/BufferGeometry.html)：頂點、法線、索引及 buffer 表示。本輪合併網格減少 draw，封閉性另外用拓撲測試驗證。
- [Three.js Material](https://threejs.org/docs/pages/Material.html)：alpha-to-coverage 需要 MSAA；它不是排序透明，也不保證沒有覆蓋率量化。
- [NVIDIA GPU Gems 39](https://developer.nvidia.com/gpugems/gpugems/part-vi-beyond-triangles/chapter-39-volume-rendering-techniques)：密度、重建與透射的基本概念。此輪只保留便宜的局部近似，沒有照搬完整體積算法。

沿用 [B1 原創素材、prompts 與處理紀錄](../../assets/cloud-b1/README.md)，不生成新圖片，也不複製特定動畫作品。既有原始與壓縮素材均未修改。
