# 手機成本

**沒有 iPhone 真機結果。** 本文件不以桌機 SwiftShader 的 FPS 推論 iPhone FPS；SwiftShader 是 CPU 上的軟體 GPU，
它的速度與 Apple GPU 沒有比例關係。這裡量的是**與硬體無關的工作量**（真實畫面的 draw call、instance、
逐像素 fragment invocation 數、每次 invocation 的取樣數、記憶體），再把它放到 iPhone 的解析度上；
真正的幀時間請用 `tools/sky-lab.html?bench&quality=mobile` 在手機上量。

## 量測方法

`tools/sky-cost.mjs` 在真實的 Lab 畫面上把雲 shader 換成計數版本（加法混合、關深度測試），讀回 framebuffer：

- **invocations**：每個像素被雲 quad 光柵化、執行 fragment shader 的次數（含之後被 discard 的）。
- **survivors**：走完整個著色、寫出顏色的次數。

雲 shader 寫 `gl_FragDepth`，Apple GPU 的 hidden-surface removal 對它無效，所以**每個 invocation 都要付費**，
這是 impostor 做法在手機上最大的結構性成本。

## 結果（`cost-high.json`，雲 19,974 個 billow）

| 畫面 | invocations／px | survivors／px | 雲覆蓋 | iPhone 13 mini @2x（M／幀） | iPhone 15 @2x | 15 Pro Max @2x | iPhone 15 @1.5x |
|---|---|---|---|---|---|---|---|
| 飛近終點（離主塔 600 m） | 5.98 | 4.49 | 85% | 7.28 | 8.00 | 9.58 | 4.50 |
| 飛近中段 | 2.90 | 2.30 | 43% | 3.54 | 3.89 | 4.65 | 2.19 |
| 側掠中段 | 2.84 | 2.10 | 36% | 3.46 | 3.81 | 4.56 | 2.14 |
| 繞行中段 | 1.36 | 1.07 | 20% | 1.65 | 1.82 | 2.17 | 1.02 |
| 雲內 | 1.49 | 1.49 | 4% | 1.82 | 2.00 | 2.39 | 1.12 |
| 雲海俯衝 | 4.10 | 3.84 | 71% | 4.99 | 5.49 | 6.57 | 3.09 |
| 雲海下方仰望 | 4.23 | 2.09 | 97% | 5.15 | 5.66 | 6.78 | 3.19 |

迭代中的變化（同一工具）：剔除埋藏 billow 前，飛近終點是 14.75／px、雲內 8.5／px；
剔除後 6.0／px；雲內再加「被 99% 霧遮住的 billow 不畫」降到 1.5／px。

每個 survivor 的取樣數（從 shader 數）：遠於 2.6 km 為 10 次（sun-depth 5、筆觸 2、PCF 旋轉 1、天空色 1、雲底 1），
0.9–2.6 km 加微浮雕 4 次為 14 次，900 m 內 16 次，45 m 內 18 次；被 discard 的 invocation 只做 ray 相交（約 25 個運算）。
ALU 約 250–300 個純量運算／survivor（手算，未經編譯器統計）。

## 其他成本

| 項目 | 數值 |
|---|---|
| Draw calls | Lab 5–7（天空、海、雲、霧團、雲絲＋飛機）；`?sky=opus` 遊戲實戰畫面 20（含飛機、尾跡、特效） |
| 頂點 | 雲 4 × 19,974 ＝ 8 萬頂點，instance 資料靜態，不逐幀上傳 |
| 每幀 CPU | 霧取樣 11 次密度查詢 ＋ 雲絲格點約 400 次查詢；桌機 0.1–2 ms（含其他程序搶 CPU） |
| 開場一次性 | 生成雲場約 0.9–1.5 s（桌機 Node，生成 4.5 萬顆後剔除到 2 萬）；sun-depth pass 一次 |
| GPU 記憶體 | sun-depth 2048×1024（高）＝ 8 MB 深度 ＋ 2 MB R8；手機 1024×512 ＝ 2.5 MB。3D 雜訊 256 KB、海面雲影 64 KB、instance 1.3 MB |
| 下載 | 無新增貼圖；全部程序生成，沿用 R2 天空畫 |

## 推論（明確標示為估計）

最壞畫面（貼近主塔）在 iPhone 15 @2x 約 6 M survivors × 16 次取樣 ≈ 1 億次取樣／幀；60 fps 約 6 G 次／秒，
另約 1.8 G 運算／幀。A15／A16 的 GPU 以公開規格約 1.3–1.8 TFLOPS 級；紙面上 ALU 只佔一小部分，
**較可能的瓶頸是取樣頻寬、無 HSR 的過度繪製與長時間遊玩的降頻**。我的判斷：

- `quality=mobile`（DPR 上限建議 1.5、sun-depth 1024×512）在多數畫面應能接近 60 fps；
- DPR 2 的最壞畫面（貼近濃積雲）有掉到 40–50 fps 的風險；
- 雲內反而是最便宜的畫面。

**這些都必須用 `?bench` 在真機確認**，我不把它寫成已達成。

## 風險與下一步

1. **真機量測**：iPhone 13 mini 與 15，`?bench&quality=mobile` 與 `quality=high` 各跑一次，回報各路線 median／p95 幀時間與 5 分鐘後的降頻。
2. 若超出預算，依代價由小到大：DPR 1.25–1.5；微浮雕縮到 1.2 km；PCF 5 → 3 點；`low` 關閉雲海第二層 billow。
3. **結構性選項**：把 billow 換成 instanced icosphere LOD 幾何（不寫 `gl_FragDepth`、核心不 discard），
   讓 Apple 的 HSR 回來，每像素幾乎只著色一次，代價是頂點量（約 50–150 萬頂點／幀，視 LOD）。
   形狀文法與畫光 shader 可以原樣沿用；本輪先證明美術方向，沒有做這個重構。
4. 開場生成：正式化時應預烘成二進位（約 1.3 MB，gzip 後約 0.4 MB）或放進 Worker。
