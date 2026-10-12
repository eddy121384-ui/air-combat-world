# 北台灣白模 Phase 2A — World Bounds & Terrain Coverage

日期：2026-10-12 · 分支：`feat/ntw-phase2a-world-bounds`（疊在 PR #16 `feat/north-taiwan-whitebox-foundation` @ `3287005` 之上）
環境：Windows 11，venv `D:\Users\EDDY\.venvs\acw-ntw`（`requirements-ntw.txt`），Overture `2026-09-23.1`，MOI 2025 20 m DTM（z13 mirror）。
本輪**不生成建築、不改動 Unreal 正式場景、不修改已接受的信義區幾何**。

標記：**MEASURED** = `tools/ntw/` 腳本由釘選資料算出，證據在 `data/ntw/world/`；**ESTIMATE** = 依量測值推算並註明假設；**UNKNOWN** = 無法量測，不填數字。

---

## 0. 結論

| 問題 | 結論 |
|---|---|
| 224 × 224 km 放在哪？ | **建議 SW 角 EPSG:3826 (184,000, 2,648,000)**，邊界 E 184,000–408,000 / N 2,648,000–2,872,000；28 × 28 個 8 km cell，全部對齊 8 km 格網。 |
| 指定要素都在範圍內？ | **是。** 新竹市/縣、桃園、臺北、新北、基隆、宜蘭全境（主島部分 100%），雪山、南湖大山、中央尖山、大霸尖山、七星山，桃園/松山/新竹空軍基地，基隆港/臺北港/蘇澳港，全部距邊界 ≥ 41 km。另含清泉崗、花蓮機場、佳山基地、臺中港、花蓮港。 |
| 西、北、東海空縱深 | 從核心區海岸線量起：**西 54.6 km（中位 69.4）/ 北 73.0 km（中位 92.2）/ 東 56.5 km（中位 73.3）**。 |
| 海陸比例 | 台灣陸地 15,058 km²（**30.0 %**）、海 35,118 km²（**70.0 %**）、外國陸地 **0**；框內海岸線 591 km。 |
| 外國領土 | 框內 0。最近外國陸地：日本與那國 38.1 km、福建外島 40.9 km（框外）。 |
| 信義相容 | **相容，且零修改。** 信義 L3 sector 完整在世界內（距邊界 ≥ 100 km）；以來源 ID 抑制 NTW 重建：11,132/11,132 個信義 ID 在今日 WFS 中幾何完全相同，非信義建物與信義 footprint 重疊 **0**；25/25 GLB SHA-256 未變。 |
| 地圖尺寸可變？ | **是。** `WorldSpec` 由 `worlds/*.json` 定義尺寸/位置；192/224/256/288 km 以同一程式比較（§9）。224 km 是本研究的甜蜜點。 |
| 新發現的資料問題 | **DTM mirror 在新竹縣山區有 154.6 km² 資料缺口**（周邊中位高程 1,400 m，該處卻是 0 m/NODATA）；且 mirror 在海岸 6 km 內把海存成 **0.0 m 而非 NODATA**。Phase 1 的「442 tiles 全部存在」只代表 tile 存在，不代表陸地像素有效——此處更正。 |

---

## 1. 範圍與 Git 安全

- 在既有獨立 worktree `..\air-combat-world-ntw`，從 `origin/feat/north-taiwan-whitebox-foundation`（PR #16 head `3287005`）開新分支；主 checkout 與其未追蹤 Unreal 內容未碰。
- 不改 `tools/citygen_v2`、`tools/compiler`、`unreal/`、任何已接受 GLB；Draft PR 目標為 PR #16 分支（stacked），不 merge。
- 大型資料（Overture parquet、874 個 DTM tile、WFS 快取）全在 git-ignored `data/generated/ntw/`。

## 2. 世界位置選擇（MEASURED，`tools/ntw/world_planner.py`）

方法：在 8 km 格網上掃描 725 個 SW 角候選（E 64–288 km × N 2,544–2,736 km）。

- **硬條件**：7 個指定行政區的主島部分 + 必要要素（3 機場、3 港口、5 山峰）全部在內且距邊界 ≥ 8 km（一個 cell）；**框內不得有外國（中國/日本）陸地**。
- **目標**：最大化 min(西, 北, 東) 海岸到邊界距離；只計「核心海岸」——該掃描線最外側海岸點屬於指定行政區（因此苗栗/臺中海岸靠近西邊界不會誤導分數）；其次最大化 optional 要素、再北向縱深。
- 131 / 725 可行。最常見的不可行原因：外國陸地入框（424）、新北/宜蘭未完整入框（419）。

| 方案 | SW 角 (EPSG:3826) | 西 / 北 / 東 核心縱深 km | 陸地 % | 差異 |
|---|---|---|---:|---|
| **建議：north_taiwan_224** | **(184,000, 2,648,000)** | **54.6 / 73.0 / 56.5** | 30.0 | 含花蓮機場、佳山、花蓮港、奇萊；南邊界距花蓮港 5.7 km、花蓮機場 9.8 km |
| alt `north_deep` | (184,000, 2,680,000) | 54.6 / **105.0** / 56.5 | 21.9 | 北向最深；**失去**花蓮機場/佳山/花蓮港/奇萊 |
| alt `south_safe` | (184,000, 2,640,000) | 54.6 / 65.0 / 56.5 | 32.0 | 花蓮市與港距南邊界 ≥ 13 km |

東西向的 8 km 步距下，x0 = 184 km 是唯一讓西/東都 ≥ 54 km 的位置（西 54.6 / 東 56.5）；南北位置是「北向縱深 vs 是否納入花蓮空軍目標」的設計取捨，**需要審查者決定**（建議案保留花蓮，因佳山/花蓮基地是東部空戰重要目標，北向 73 km 仍是三面中最深）。

**海峽中線註記**：常見引用的「海峽中線」端點 (27°N,122°E)–(23°N,118°E) 為**近似、非官方**；建議案有 3.7 % 面積位於其西北側（框西北角海面），未含任何中國陸地或馬祖。若遊戲需完全避開此敏感區，可改用 `north_deep`（8.3 %）以外的方案或縮小西北角——列為設計審查項。

## 3. 世界邊界座標（`data/ntw/world/north_taiwan_224_bounds.geojson`）

| 項目 | 值 |
|---|---|
| CRS | EPSG:3826（TWD97 / TM2 121） |
| SW / SE / NE / NW (m) | (184,000, 2,648,000) / (408,000, 2,648,000) / (408,000, 2,872,000) / (184,000, 2,872,000) |
| SW / SE / NE / NW (lon, lat) | (120.3516, 23.9352) / (122.5520, 23.9287) / (122.5775, 25.9504) / (120.3410, 25.9575) |
| 8 km 絕對格網索引 | X 23–50、Y 331–358（`cell_id = C{ix:+05d}{iy:+05d}`，與世界大小無關） |
| Runtime（UE）原點 | 世界中心 (296,000, 2,760,000)；UE 範圍 X/Y ±11,200,000 cm（±112 km）|
| Phase 1 NTW 儲存座標 | (−40,000, −40,000)–(184,000, 184,000)；tile key 仍用 PR #16 的 NTW 原點 (224,000, 2,688,000)，**不隨地圖尺寸改名** |
| 每 cell L2 tile | 16 × 16 = 256 個 500 m tile |
| UE 軸 | 沿用已接受合約：UE X = 東 × 100、UE Y = −北 × 100、UE Z = 上 × 100 |

另提供：`north_taiwan_224_cells_epsg3826.geojson`（784 個 cell 多邊形 + 全部屬性）、經 4 km 加密的 WGS84 外框（TM2 直線在經緯度上微彎）、`xinyi_l3_mask_epsg3826.geojson`。

## 4. 指定要素檢核（MEASURED；位置取自 Overture 記錄並保存 ID，`data/ntw/world/features.json`）

| 要素 | 最近邊界 | | 要素 | 最近邊界 |
|---|---:|---|---|---:|
| 臺灣桃園國際機場 | 89.5 km (W) | | 基隆港 | 83.1 km (E) |
| 臺北松山機場 | 98.6 km (N) | | 臺北港 | 89.5 km (N) |
| 空軍新竹基地 | 60.0 km (W) | | 蘇澳（漁）港 | 70.3 km (E) |
| 雪山主峰 3,885 m | 49.5 km (S) | | 七星山 1,118 m | 87.2 km (N) |
| 南湖大山 3,741 m | 47.2 km (S) | | 中央尖山 3,698 m | 41.4 km (S) |
| 大霸尖山 3,490 m | 57.7 km (S) | | optional：清泉崗 27.8 / 臺中港 17.4 / 奇萊主山 16.6 / 佳山 10.2 / 花蓮機場 9.8 / 花蓮港 5.7 km |

- 行政區入框比例：新竹市/縣、桃園、臺北、新北、基隆、宜蘭 **100 %**；周邊：苗栗 100 %、臺中 100 %（主島部分）、彰化 52.5 %、花蓮 34.2 %、南投 34.2 %。
- 北台灣 2,500 m 以上高山 z13 tile：108/108 在框內。
- 框外：馬祖（臺灣，距西邊界 34–38 km）、福州長樂機場、與那國機場。
- 誠實註記：港口以 Overture place 代表點標示（有的是碼頭/漁港記錄，如蘇澳以「蘇澳漁港」代表），非港區範圍；宜蘭「太平山」在 Overture 查無此名，記為 NOT_FOUND，未以記憶補座標。

## 5. 地形覆蓋（MEASURED，874 個 DTM tile、250 m 取樣 802,816 點）

- 框內陸地最高 3,795 m（取樣後；雪山 3,885 m 點位在 Overture 中）；陸地 **32.5 % > 1,000 m、11.7 % > 2,000 m**。
- 陸地多邊形與 DTM 有效性一致 97.2 %。
- **發現 1：海在海岸 ~6 km 內被存成 0.0 m**（21,832 個「DTM 有效但在海上」的點，96.9 % |z| < 0.5 m）。→ 陸海遮罩必須用向量海岸線，絕不能用 DTM 有效性。
- **發現 2：資料缺口 154.6 km²**，位於 121.009–121.132°E、24.450–24.567°N（新竹縣山區），cells `C+0031+0338`、`C+0031+0339`、`C+0032+0338`、`C+0032+0339`；周邊陸地中位高程 1,400 m，缺口內為 NODATA/0 m（tile 6850/3520 在 mirror 中不存在，鄰 tile 約 40 % 陸地像素為 0）。偵測器以「離岸 > 2 km、|z|<0.5 或 NODATA、形狀寬於 ~1.25 km 且 ≥ 4 km²」判定，河道/潟湖/魚塭等細長真低地不列入（共 24.9 km² 另列）。該 4 個 cell 的地形在官方 TGOS DTM 圖幅核對前**不得以此 mirror 生成**。
- 外海：無水深資料（近岸 0 m、外海 NODATA）。海面平面或水深來源是獨立決策（UNKNOWN）。

## 6. 分區統計與精度分級（MEASURED，`north_taiwan_224_summary.json`）

**建築數量**：臺北市 = WFS 369,960 筆（另 3,572 筆 WFS 質心落在 Overture 臺北陸地多邊形外，為避免重複計數另列）；其他 = Overture 923,493 列（**下限**，Phase 1 已證明 Overture 在臺北僅有 WFS 的 29 % 筆數）。合計 1,293,453。

**分級規則**（參數化，`world_cells.py --tiers`，非 224 專用）：
- T4 海：陸地 < 0.5 % 且無關鍵設施。
- T1 高精度：含信義 L3、或含機場/港口、或「核心戰區」（陸地 ≥ 50 % 屬 7 個指定行政區）且 footprint/陸地 ≥ 6 % 或 ≥ 6,000 棟。
- T2 中精度：核心戰區且 ≥ 1.2 % 或 ≥ 800 棟。
- **T2p 周邊都市（只做量體）**：非核心戰區但達 T2 門檻（臺中、彰化、苗栗等）。
- T3m 山區低精度：平均高程 ≥ 500 m；T3 鄉村/海岸低精度：其餘。

| 分級 | cells | 陸地 km² | 海 km² | 建築（best） | footprint km² |
|---|---:|---:|---:|---:|---:|
| **T1 高精度** | 40 | 2,240.7 | 319.3 | 758,166 | 187.1 |
| T2 中精度（核心） | 38 | 1,834.6 | 597.4 | 76,865 | 22.4 |
| T2p 周邊都市 量體 | 59 | 3,469.6 | 306.4 | 439,448 | 142.8 |
| T3 鄉村/海岸 | 25 | 757.9 | 842.1 | 5,720 | 1.0 |
| T3m 山區 | 106 | 6,755.0 | 29.0 | 13,240 | 2.4 |
| T4 海 | 516 | 0.4 | 33,023.6 | 14 | 0.0 |

→ 需要高精度建模的陸地僅 **2,241 km²（世界面積 4.5 %）**，卻含 59 % 的建築；**50 % 的陸地（T3/T3m，7,513 km²）只需低精度環境、另 23 % 為周邊都市量體（T2p）**；70 % 的世界是海。

**海域分區**（以最近主島海岸方向）：東海/北方 16,682 km²、太平洋/東方 11,699 km²、臺灣海峽/西方 5,880 km²、南方 420 km²。

**行政區（框內）**：臺北 269.8 km²/369,960（WFS）；新北 2,059.7/134,871；桃園 1,205.8/141,139；新竹市 107.1/27,634；新竹縣 1,407.0/53,795；基隆 134.1/14,001；宜蘭 2,192.8/63,258；周邊：臺中 2,242.6/209,611、苗栗 1,811.0/68,508、彰化 653.0/112,369、花蓮 1,573.3/60,233、南投 1,402.1/38,013。L0 32 km 區塊（49 塊）全表在 summary JSON。

**高度可用性（審查第 4 點，已在本輪修正）**：Overture（臺北以外、框內 923,493 列）有效高度 2,163、僅有效樓層 37,651、**有值但無效 7**、缺值 883,672。Phase 1 的「presence-based」fallback 數與「validated」不可用數幾乎相同：核心 6 區 434,468 vs 434,484（只多 16 筆有值但越界）。邊界效應：Phase 1 bbox 篩選 vs 本輪質心 + 全解析度邊界，各區差 −7 ~ +94 筆；150 m 簡化邊界造成的歸屬翻轉 5–442 筆/區（< 0.7 %）。`coverage_survey.py` 已同時輸出兩種口徑。

## 7. 信義區相容性（MEASURED，`xinyi_compat.json`）

- 信義 25 個 ENU tile 以**已接受 ENU 公式的精確反算**轉為 EPSG:3826 外框（面積 6.2222 km² = 6.25 × 1.00054 × 0.99503），位於單一 8 km cell `C+0038+0346`，距世界邊界 W 121.6 / E 99.9 / S 120.6 / N 101.0 km，觸及 36 個 NTW L2 tile。
- 信義 ENU 原點 = EPSG:3826 (307,056.82, 2,769,551.84)，在世界 UE 座標中為 (1,105,681.89, −955,185.82) cm。
- **Xinyi-level UE → 世界 UE（cm）仿射**：`[[1.000531273, 0.004154954], [−0.004177942, 0.995025997]]`，平移 (1,105,681.89, −955,185.82)，Z 不變（同為 TWVD2001）。det = 0.99557（非等向，PR #16 已量測）。
- **L3 抑制規則（審查第 2 點）**：信義與 NTW 都來自同一 WFS 圖層，因此以**來源 ID** 抑制，不以 tile 或幾何遮罩：NTW 跳過信義釘選來源的 11,132 個 ID；信義 hero 抑制（台北 101）仍由信義擁有。今日 WFS 驗證：11,132/11,132 ID 存在且幾何完全相同、0 個信義 ID 消失、fetch bbox 內 0 個新 feature、附近 15,679 個非信義 feature 與信義 footprint 重疊 **0**。→ 不會重複渲染，也不會留下建物缺口（WFS 變動時需重驗，列入 Phase 2B gate）。
- 因信義 tile 相對 TM2 旋轉 0.239°、縮放 1.00054/0.99503，**永遠無法與 NTW L2 tile 對齊**；所以 ownership 必須用來源身分，tile 只用於串流。
- 已接受 GLB 完整性：本機 accepted run 25/25 tile SHA-256 符合報告（manifest `14c2890b…`），tile key 與常數一致。**地形接縫（Landscape vs NTW 地形）、法線、碰撞仍未驗證**，見 §10。

## 8. 可變地圖尺寸架構（`tools/ntw/world_spec.py`、`worlds/*.json`）

- 世界 = EPSG:3826 中的軸向矩形；尺寸、cell 大小、SW 角全部來自 JSON。`validate()` 強制：尺寸為 cell 整數倍、SW 角在絕對格網上、cell 為 500 m L2 tile 的整數倍、NTW 儲存原點也在格網上。
- **三層座標分離**：(1) 儲存/tile key：PR #16 NTW 框架（與世界無關）；(2) 世界邊界與 cell id：絕對 EPSG:3826 格網索引（不同尺寸的世界共享同一 cell id）；(3) runtime 原點：世界中心對齊格網（每個世界不同，只影響引擎座標）。
- 改尺寸 = 新增一個 `worlds/<name>.json`，重跑 `world_planner.py --size-km N`、`world_cells.py --world …`、`render_world_maps.py --world …`；tile 與 cell 不需改名。測試覆蓋 160–320 km 與非正方形（224 × 160 km）。

| 尺寸 | 最佳位置 SW | 最小核心縱深 | 陸地 % | 最近外國陸地 |
|---|---|---:|---:|---:|
| 192 km | (200,000, 2,640,000) | 38.6 km | 39.7 | 54.1 km |
| **224 km** | (184,000, 2,648,000) | **54.6 km** | 30.0 | 38.1 km |
| 256 km | (168,000, 2,656,000) | 70.6 km | 23.1 | 22.1 km |
| 288 km | (152,000, 2,600,000) | 86.6 km | 19.6 | **2.8 km** |

288 km 已逼近外國陸地（不可再大而不含外國領土），256 km 可行但西北角 10 % 在近似中線外；224 km 兼顧三面 ≥ 54 km 縱深與 ≥ 38 km 外國緩衝。

## 9. 可審查視覺成果（`docs/evidence/ntw/world/`）

- `north_taiwan_224_plan.png`：DTM hillshade、海岸線、世界框（紅）、替代方案（藍）、8/32 km 格網、核心行政區、信義 L3、機場/港口/山峰、近似海峽中線、UE 原點、資料缺口（洋紅）。
- `north_taiwan_224_tiers.png`：每個 8 km cell 的精度分級與建築量。
- `size_options.png`：192/224/256/288 km 最佳位置比較。

## 10. PR #16 審查未解項目 → 工程規劃

| # | 審查項目 | 本輪處理 | 後續 gate |
|---|---|---|---|
| 1 | 高度/完整度來源（P0） | 以 validated 口徑量化：框內 Overture 95.7 % 無可用高度（883,672/923,493）；分級把高精度限縮到 T1 2,241 km² | **Phase 2C 來源 gate**：NLSC LOD1 KMZ 覆蓋/年份/價格/**商用遊戲再散布授權**/衍生資產授權書面確認；每棟建物 source/confidence tier（surveyed / derived / floors / fallback）；未通過前 T1 以外不做逐棟高度 |
| 2 | 信義接縫/優先權（P0） | **ID 抑制規則 + 今日 WFS 驗證（0 重疊、0 缺失）**；L3 外框與 UE 仿射 | **Phase 2B 接縫 gate**：信義四邊地形/建物接縫 QA（高差、datum、法線、碰撞），比較「信義 Landscape + 仿射」與「NTW 地形重生成信義範圍」兩案；不改 GLB；WFS 變動時重跑抑制驗證 |
| 3 | Shard 邊界/串流正確性（P0） | 定義世界 cell（8 km、256 tile/cell）、cell id、runtime 原點 | **Phase 2B**：source-owned L1 shard + fetch halo（≥ 最大 overhang；PR #16 實測 164 m → 建議 halo 250 m）；每個 shard 記錄 culling bounds = 擁有物件聯集 bbox；相鄰 shard 獨立建置 vs 聯集建置比對（含跨 L1、跨行政區界）；無縫/無重複 |
| 4 | Coverage vs validity（P1） | **已修正**：`coverage_survey.py` 與 `world_cells.py` 套用 `heights.py` 真實邊界，區分 presence/validated/invalid；邊界誤差量化（§6）；新增測試 | 完成；Overture 數量一律標為「下限」 |
| 5 | LOD 與身分（P1） | 分級提供 T2p（只做量體）與 T3/T3m（無逐棟）政策 | `(provider, record_id, part) → 多個 proxy` 映射（修正 `idmap` 覆寫）；稀疏區改用 instancing/省略/billboard；距離品質比較後才進 UE |
| 6 | Fail-closed 與證據（P1） | DTM 缺口以 fail-loud 方式回報（4 cells 禁止生成）；新偵測器有合成資料測試 | 全域 rejection 門檻/警報；被拒 polygon 空間報告；CI/artifact 保存 build+Blender 證據與輸入 checksum；指定**標準建置平台**（建議 Linux CI，因 5/11,130 信義節點跨平台不同） |
| 7 | 第一次全市建置（P1） | 不在本輪 | 8 km shard + checkpoint/resume + 冪等 manifest + retry → 全臺北 WFS 建置 → 正射抽查、高度直方圖、輸入/輸出計數、兩鄰 shard 接縫測試 |

## 11. 下一階段工程建議（依序，各自為 gate）

1. **審查決策**：確認 224 km 與南北位置（建議案 / north_deep / south_safe）、是否接受近似中線西北角 3.7 % 海面、外海策略（海平面 vs 水深）。
2. **Phase 2B — 地形與信義接縫**：(a) 核對 TGOS 官方 DTM 對新竹縣缺口圖幅，修補後再生成 4 個 cell；(b) 以世界 cell 為單位生成 NTW 地形（L0/L1 解析度先行）；(c) 信義四邊接縫 QA；(d) source-owned shard + halo 規格與相鄰 shard 測試（審查 #3）。
3. **Phase 2C — 高度來源 gate**（審查 #1）：NLSC LOD1 授權/價格/覆蓋書面確認；source/confidence tier 欄位；決定 T1 以外是否逐棟。
4. **Phase 2D — 全臺北 WFS 建置**（審查 #7、#6）：sharding + resume + 標準平台 + CI 證據；完成後才擴大到 T1 其他 cell。
5. 之後才考慮 UE World Partition/HLOD 匯入實驗與手機實機量測（尚未做，**不宣稱任何效能結果**）。

## 12. 已驗證 / 未驗證

已驗證（MEASURED + 測試）：世界邊界/格網/對齊、要素入框與距離、海陸比例、海岸線、外國陸地 0、海岸縱深、地形統計與資料缺口、分級統計、信義外框精確反算、ID 抑制（今日 WFS）、GLB 完整性、尺寸可變（160–320 km、非正方形）。`tests/test_ntw_world.py` 16 項 + `tests/test_ntw_foundation.py` 14 項通過，既有 `test_compiler`/`test_citygen_v2` 不受影響。

未驗證：Unreal 中的任何東西（未啟動）、手機效能、信義地形/碰撞接縫、官方 DTM 是否同樣有缺口、海峽中線的正式位置（僅近似）、NLSC LOD1 授權、Overture 在臺北以外的真實完整度。

## 13. 檔案與重現

```text
python tools/ntw/world_geography.py                                   # 陸地多邊形 + 要素（Overture ID）
python tools/ntw/world_planner.py --size-km 224                       # 亦可 192 / 256 / 288
python tools/ntw/fetch_dtm_tiles.py --world worlds/north_taiwan_224.json
python tools/ntw/extract_overture_buildings.py --release 2026-09-23.1 --centroid --ymin 23.90 --ymax 26.00 --xmin A --xmax B --out data/generated/ntw/world/ovt_world_bandN.parquet
     (bands: 120.30/120.85/121.20/121.45/121.70/122.65)
python tools/ntw/xinyi_world_compat.py --world worlds/north_taiwan_224.json
python tools/ntw/world_cells.py --world worlds/north_taiwan_224.json
python tools/ntw/render_world_maps.py --world worlds/north_taiwan_224.json
python -m pytest tests/test_ntw_world.py tests/test_ntw_foundation.py
```

新增：`worlds/north_taiwan_224.json`、`tools/ntw/{world_spec,world_geography,world_planner,fetch_dtm_tiles,world_cells,xinyi_world_compat,render_world_maps}.py`、`data/ntw/world/*`（約 0.7 MB）、`docs/evidence/ntw/world/*.png`（約 1 MB）、`tests/test_ntw_world.py`、`requirements-ntw.txt`。
修改：`tools/ntw/coverage_survey.py`（validated 口徑）、`tools/ntw/extract_overture_buildings.py`（`--centroid`，預設行為不變）、`data/ntw/coverage_manifest.json`（新增 validated 欄位）。
