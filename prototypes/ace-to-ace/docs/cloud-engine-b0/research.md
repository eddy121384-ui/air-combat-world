# Cloud Engine B0：物理依據與遊戲近似

查閱日期：2026-10-18。目的為建立可穿越的三維空間，再讓 B1 的 2.5D 手繪顯示有依據；不是預報、流體或微物理模型。下列內容為摘要，沒有移用來源圖片或美術素材。

## 可採用的真實特徵

| 主題 | 研究依據 | B0 決策與簡化 |
|---|---|---|
| 積雲形成、雲底 | 濕空氣上升冷卻至凝結；近似一致的凝結高度可形成較平的雲底。混入乾空氣會侵蝕邊緣。[NOAA/NWS](https://www.weather.gov/fgz/CloudsContrails) | 用共同雲底與平滑過渡表示凝結層；不用溫度、濕度解算，也不模擬上升氣流。 |
| 積雲外形 | 分離的雲體、向上發展的圓頂與花椰菜隆起；受光部位明亮，底部較暗。[WMO 定義](https://cloudatlas.wmo.int/en/clouds-genera-cumulus.html) | 每個雲團三個重疊橢球，較高的垂直比例，共用底界。輪廓比真實尖銳雲邊更柔，供高速飛行測試。 |
| 積雲厚度 | humilis 垂直尺度為數十至數百公尺；mediocris 為數百公尺至約 2 km；congestus 有時超過 5 km。[WMO 航空觀測](https://cloudatlas.wmo.int/en/observation-of-clouds-from-aircraft-descriptions-cumulus.html) | 選 1,200 m 的 mediocris 尺度包絡，沒有模擬 congestus 或雷暴。 |
| 層積雲形成 | 積雲在穩定層下展開、風切、層雲的對流或紊流轉化等都可形成層積雲。[WMO 形成路徑](https://cloudatlas.wmo.int/en/stratocumulus-may-form.html) | 使用相連的寬而扁雲團，表示受穩定層限制的層狀結構；不計算穩定度、風切或生成消散。 |
| 層積雲幾何 | 灰白相間、含圓塊或滾軸、可合併成片。[WMO 定義](https://cloudatlas.wmo.int/en/clouds-genera-stratocumulus.html) 通常位於 2 km 以下，厚度約 500–1,000 m。[WMO 航空觀測](https://cloudatlas.wmo.int/en/observation-of-clouds-from-aircraft-descriptions-stratocumulus.html) | 厚度選 700 m；**實驗雲底抬至 2,650 m，不代表典型層積雲高度**。目的是與 2,600–3,600 m 交戰高度重疊。可調回 base=900、top=1600。 |
| 水平尺度 | 雲團可以分離、合併成層或沿風向排列；上述分類不給單一固定水平尺寸。[WMO 術語 cloud streets](https://cloudatlas.wmo.int/en/glossary.html) | 6×5 km 有限雲區、3×3 雲團；cellSize 為積雲 1,700 m、層積雲 2,300 m 的遊戲控制量，**不是來源提供的統計平均直徑**。實際雲體略受 seed、橢球重疊與邊界裁切影響。 |
| 密度與雲內能見度 | 積雲內可有極低或近零能見度；層積雲內像濃霧，能見度有空間變化。[WMO 積雲](https://cloudatlas.wmo.int/en/cumulus-mediocris.html)、[WMO 層積雲](https://cloudatlas.wmo.int/en/stratocumulus-stratiformis-occur-sheet-layer-detached-elements.html) | 密度 0–1 為無單位佔有／消光代理，並非 g/m³。核心較密，雲底、頂、邊緣漸淡，兩個尺度的連續 noise 表示不均勻，不能據此推斷真實水含量剖面。 |
| 風與移動 | 雲街可沿風向排列；暖海面上方的濕對流和逆溫可形成雲街。[NASA 實例](https://earthobservatory.nasa.gov/images/49254/winter-cloud-streets-north-atlantica) | 固定風 (8, 0, 3) m/s，查詢座標反向平移 `p - wind*time`。形狀不變、無風切、無週期跳回；這是運動學平流，不是真實雲滴生命週期。 |
| 光照 | 雲滴主要散射可見光，光學厚度衡量沿路徑的衰減。[NASA MODIS](https://svs.gsfc.nasa.gov/30398) 側光、逆光會有不同明暗，積雲底通常偏灰。[WMO 說明](https://cloudatlas.wmo.int/en/explanatory-remarks-and-special-clouds-cumulus.html) | 可調固定日光方向，以沿光方向的局部密度差與高度混合亮暗色。沒有多重散射、真實投影陰影或銀邊解算；亮暗僅為幾何診斷。 |

## 從物理概念到 B0 合約

`createCloudField()` 為純 JavaScript，無渲染器依賴。Y 是海拔公尺、海面 0，time 是秒。建構後參數、風、幾何與 bounds 固定；調參用新 field。`bounds`、`lobes` 是 **time=0** 的雲座標，世界位置須加上 `wind*time`。

積雲：base=2450、top=3650；層積雲實驗：base=2650、top=3350。包絡不代表每個 x/z 都有雲。共同雲底以 85 m、頂界以 130 m 平滑淡化，水平雲區邊界以 180 m 淡化；全部是可讀性與連續性的遊戲選擇。

各橢球的平滑密度以 `1 - product(1 - density_i)` 合併，再乘連續 noise、密度參數與上下邊界淡化。沒有二元 inside/outside 開關。固定 seed 決定位置、大小及細節；sample 不使用隨機狀態、鏡頭或畫格資訊。

視線診斷使用中點積分：`columnDensity = Σ rho_i * ds`、`tau = 0.012 * columnDensity`、`T = exp(-tau)`。0.012 m⁻¹ 為調整可讀性的消光係數，不是由量測液水含量換算。完整密度下直線飛行 250 m，直達光 T 約 0.05；密度一半時約 0.22。這描述離開視線方向的衰減，不能把它當成純吸收或氣象能見度預報。

因此接近時遠方物體先變淡，進雲後近景也逐漸消失，離開後依視線剩餘雲量恢復。相同位置轉頭，局部密度相同，但前方 T 可以不同。飛機視覺變淡不回饋到控制、物理、AI、鎖定或導引。

## B1 建議

1. 保留這個場作為三維錨點與穿雲診斷。先從雲團／lobes 取得穩定的位置、尺寸、上下界及 seed，再建立少量多方向手繪雲片；不要依鏡頭重新抽樣雲的位置。
2. 延續已接受 R2 的天空構圖與色盤；獨立製作 B1 素材與名稱。京都動畫、新海誠式的分層筆觸、柔光和空氣感留待 B1 正式研究，B0 不產生替代天空。
3. 為側面、上方、下方準備不同外形或交叉雲片，受光方向以世界日光向量決定。視角／LOD 切換採連續交叉淡化，避免單張面向鏡頭的圖片在近距離暴露厚度不足。
4. 遠處用手繪輪廓，中距用少量深度分層，近處以同一密度場導出的局部霧過渡。讓背景、前後雲片、飛機和信標共用深度遮蔽；沿用 B0 的回轉、上下及穿入／穿出路線驗證空間一致性。
5. 任何正式遊戲試接都另設預設關閉的旗標；先在真 iPhone Safari 測 fill-rate、記憶體、透明重疊與觸控，再選渲染預算。
