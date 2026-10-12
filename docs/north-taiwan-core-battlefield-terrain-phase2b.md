# 北台灣白模 Phase 2B — 核心戰場與地形 Vertical Slice

日期：2026-10-13 · 分支：`feat/ntw-phase2b-north-core-terrain`（疊在 PR #22 `feat/ntw-phase2a-world-bounds` @ `e44fdba` 上）
環境：Windows 11、venv `acw-ntw`（`requirements-ntw.txt`）、Blender 5.2.1 LTS、UE 5.8（僅隔離的臨時專案）。
**未修改**：信義 25 個已接受 GLB、信義 Landscape、正式 Unreal 專案/場景、PR #16/#22 內容。未生成全北台灣建築，未啟動植被 Pilot。

標記：**MEASURED** = 腳本由釘選資料量測；**ESTIMATE** = 依量測推算；**NOT TESTED** = 本輪未做，不宣稱通過。

---

## 0. 結論（Gate 判定）

| 項目 | 結果 |
|---|---|
| 北台灣核心戰場（建議） | **可飛行 112 × 112 km：EPSG:3826 E 224,000–336,000 / N 2,728,000–2,840,000**；生產區 128 × 128 km（E 216,000–344,000 / N 2,720,000–2,848,000）；遠景 = PR #22 的 224 km 世界 |
| 100 km 能否涵蓋必要場景 | 96 km **不可行**；100/104 km 可行但西側海峽縱深最小只剩 4.6/6.6 km；112 km 是能同時保住新竹空軍基地、桃園機場、台北盆地、基隆港、北海岸並留 ≥ 14.6 km 西側 / ≥ 41 km 北側海空縱深的最小 8 km 格網尺寸 |
| DTM 缺口 | **官方 2025 DEM 本身就缺**（新竹縣、新竹市、桃園、苗栗四個官方圖幅包都沒有該區節點）→ 保持 **BLOCKED**；位置在**遠景區**，距生產區 2.2 km、距可飛行區 10.2 km，不影響本輪生產，但會影響遠景 → 列入下一 Gate |
| 兩個相鄰 8 km Cell 地形 | **完成**：官方 TGOS 20 m DEM 原生節點、5 級 LOD、0 缺漏節點 |
| 相鄰 Cell 接縫 | 425 條共用邊（含 25 條跨 Cell）位置 **0 差異**、法線最大 1e-6°、UV 0；跨 LOD 縫隙全部被 skirt 覆蓋 |
| 獨立建置 vs 聯合建置 | 255 個 chunk GLB **逐位元相同**；重複建置 manifest 相同 |
| 信義四邊接縫 | **Stitch strip 在每個 LOD 都水密**：信義邊界頂點 100 % 精確（高度誤差 0.000 m）、所有邊界線段都是網格邊、所有洞邊頂點等於 chunk 頂點 |
| 建築 shard 接縫 | 57/57 tile 逐位元相同、0 重複、0 孤兒、信義 ID 0 筆被重建；但嚴格模式在 1 個 5 mm² 修復碎片上 **fail-closed**（如實保留） |
| Blender 5.2 | 6 個固定鏡頭（150 m / 300 m / 600 m / 800 m / 3 km / 正射）+ LOD0 vs LOD2 + 接縫除錯著色 |
| Unreal | **隔離臨時專案資產匯入：PASS**（51 meshes、三角形數相同、共用頂點高度差 0）。發現 Interchange 會把 glTF node 平移烘進頂點（float32 誤差 5.5 mm）→ UE 匯出改用 identity node（誤差 0.11 mm）。**Runtime 串流、HLOD、碰撞、手機效能：NOT TESTED** |

本輪 Gate 的目的已達成：**從現有信義區可靠地擴展到相鄰真實地形，並為 100 km 級空戰地圖建立參數化的世界架構。** 停在這裡等待審查。

---

## 1. Git 安全

- 開始前檢查：ntw worktree 乾淨、位於 PR #22 HEAD `e44fdba`；PR #16 HEAD `3287005`；無既有 Phase 2B 分支。主 checkout 已被其他任務切到 `research/ac7-forest-visual-benchmark`，**只做唯讀存取**（讀取已接受的信義 Landscape/GLB）。
- 新分支自 `origin/feat/ntw-phase2a-world-bounds` 建立；所有大型資料（TGOS 官方圖幅包、地形 GLB、shard GLB、渲染原圖、UE 臨時專案）都在 git-ignored 目錄或 scratchpad。
- PR #22 審查（Sophira）的要求已納入：Hualien/CCK/台中港 不再是 v1 關鍵設施；海洋 v0 = 向量海岸 + 0 m 水面；DEM 缺口 P0；信義接縫 P0；地形/建築 shard 接縫 P0。

## 2. 北台灣核心戰場尺寸研究（MEASURED，`tools/ntw/battlefield_planner.py`、`worlds/battlefields/north_core_v1.json`）

**必要集合**（全部來自真實資料，可稽核）：臺北市、基隆市、新竹市全境（邊界 2 km）；桃園機場、松山機場、新竹空軍基地（8 km）；基隆港、臺北港、七星山（4 km）；台北盆地（DTM < 20 m 連通區）、淡水河口（Overture 淡水河水域 ∩ 海岸 1 km）、北海岸（淡水河口到基隆港的海岸線）、富貴角（主島最北點）。

- 必要集合實際跨度：**93.7 × 65.1 km**（新竹市海岸 E 237.8 km → 基隆 E 331.5 km）；六縣市全境為 113.8 × 96.7 km（大部分是新竹縣、新北、桃園的山區腹地，不需要可飛行）。
- 台北盆地 < 20 m 連通區 278 km²，經淡水河、基隆河、新店溪河谷延伸到分析視窗邊界 → 以視窗界定（文件註明，不宣稱精確盆地輪廓）。

| 任務尺寸 | 可行位置 | 最佳位置 (EPSG:3826) | 西側海峽縱深 最小/中位 | 北側縱深 最小/中位 | 陸地 % |
|---|---:|---|---:|---:|---:|
| 96 km | **0 / 289** | — | — | — | — |
| 100 km（1 km 步距參考） | 56 / 15,625 | E 234,000–334,000, N 2,731,000–2,831,000 | 4.6 / 19.4 | 32.0 / 50.3 | 46.2 |
| 104 km | 4 / 256 | E 232,000–336,000, N 2,728,000–2,832,000 | 6.6 / 21.4 | 33.0 / 51.5 | 46.1 |
| **112 km（建議）** | 10 / 225 | **E 224,000–336,000, N 2,728,000–2,840,000** | **14.6 / 29.4** | **41.0 / 59.5** | 39.8 |
| 120 km | 18 / 196 | E 216,000–336,000, N 2,728,000–2,848,000 | 22.6 / 37.4 | 49.0 / 67.5 | 34.6 |
| 104 km 旋轉 50°（選項） | — | 多邊形見 study JSON | 13.2 / 26.0* | 45.9 / 55.0* | 43.7 |

\* 旋轉框的「西/北」指旋轉後座標。

**為什麼不是 100 km**：西北海岸是西南—東北走向（新竹 → 富貴角方位 ~47°），北朝上的正方形在新竹市一側只能留下 4–7 km 海面；112 km 才能讓新竹空軍基地進場方向保有 ≥ 14.6 km 海面。旋轉 50° 的 104 km 框縱深與 112 km 相當、面積少 14 %，但會讓小地圖/雷達非北朝上；列為任務變體選項，不作為生產網格（生產永遠用 8 km 對齊 Cell）。

**112 km 方案包含**：臺北、基隆、新竹市 100 %；桃園 95.4 %、新北 92.5 %、新竹縣 55.4 %、宜蘭 25.2 %、苗栗 5.2 %。
**只能在可飛行邊界外以遠景呈現**：雪山主峰/大霸尖山等雪山山脈主稜、宜蘭平原大部、新竹縣/苗栗山區、三貂角（E 351.6 km，生產區外）、蘇澳、花蓮。

### 2.1 四層區域（同一套地理資料，不重複生產）

| 區域 | 範圍 | 地形 | 建築 |
|---|---|---|---|
| 可飛行任務空間 | 112 km 框 | LOD0 20 m（官方節點） | T1 近距逐棟白模 + 遠距 HLOD；T2 街廓量體；T3 無/instancing |
| 地形/建築正式生產區 | 可飛行 + 8 km（128 km） | LOD0 40 m 起 | 只做量體與地標輪廓 |
| 可見但不可飛入的遠景 | 224 km 世界其餘部分 | 160 m 起 | 城市光點/輪廓 impostor |
| 世界邊界外 | — | 不生產幾何 | 海面延伸到地平線 + 遠山 impostor 環 + 大氣淡出 |

8 km Cell 只是**離線生成單位**；執行時串流 chunk 為 1.6 km（每 Cell 5 × 5），LOD/可見距離另行規劃（§5）。

分區統計（MEASURED，`north_core_v1_zones.json`；建築數 = 臺北 WFS + 其他 Overture 下限）：

| 區域 | cells | 陸地 km² | 海 km² | 建築 | 其中 |
|---|---:|---:|---:|---:|---|
| 可飛行 | 196 | 4,990 | 7,554 | 799,907 | T1 32 cells / 1,900 km² / 705,384；T2 33 / 1,626 km² / 70,588；T3 24；海 105 |
| 生產環帶 | 60 | 1,064 | 2,776 | 29,080 | 量體 8 cells；T3 12；海 40 |
| 遠景 | 528 | 9,004 | 24,788 | 464,466 | 城市輪廓 58 cells；地形 99；海 371 |

T1 = 規劃優先順序，**不是**逐棟正式生產的核准（PR #22 審查第 5 點）。

## 3. DTM 缺口：以官方資料核對（MEASURED，`tools/ntw/fetch_tgos_dtm.py`、`tgos_dem.py`）

- 依 data.gov.tw 176927 的官方目錄下載 TGOS 2025 20 m DEM 圖幅包（臺北市、新北市、新竹縣、新竹市、桃園市、苗栗縣；各包 SHA-256 記錄於 ignored manifest）。格式：1/5000 圖幅 `.grd`（E N H 文字）+ `.hdr`（TWD97[2020]、TWVD2001、20 m、LiDAR 來源、測製日期）；**沒有 NODATA 值，缺資料 = 沒有節點**。
- 缺口範圍 E 250,900–263,380 / N 2,704,860–2,717,840：新竹縣包只有 2.56 % 節點，加上新竹市、桃園、苗栗四包也只有 6.76 %（鄰近圖幅測製日 2016-11-01）。→ **缺口存在於官方 2025 產品本身，不是 mirror 轉檔錯誤**。
- 處置：**BLOCKED**。不以 0 m 填補、不跨 12 km 插值。位置在遠景區（距生產區 2.2 km），但從可飛行區看得到（山區遠景）→ 下一 Gate 必須用其他官方來源（較舊版次 DTM、內政部 5 m DEM 等，**授權/可得性未查證**）或明確標示的遠景替代。

## 4. 地形 Vertical Slice（`tools/ntw/build_terrain_cells.py`）

**Cell**：`C+0038+0346`（E 304–312 km, N 2,768–2,776 km，含信義 L3）與南側相鄰的 `C+0038+0345`（N 2,760–2,768 km；信義南緣距共用邊僅 551 m，適合測接縫）。

**來源**：官方 TGOS 臺北市 + 新北市圖幅，50 張圖幅、**0 缺漏陸地節點**，214,976 個跨圖幅重複節點高度差 **0.000 m**；LiDAR 測製 2021-06-18 / 2021-08-30 / 2022-11-22；高程 −4.68 – 622.81 m。官方節點本來就在 EPSG:3826 的 20 m 格點上 → **LOD0 頂點就是官方樣本，無重投影、無重取樣**。

**參數**（`TerrainParams`，非北台灣專用）：chunk 1.6 km；LOD 20/40/80/160/320 m（絕對格網子取樣）；halo 法線；世界座標 UV（1 km tile）；skirt = max(2 m, 2 × LOD 最大誤差)；fail-closed（陸地缺節點即 BLOCKED、任何非有限高度即失敗）。
**輸出**（ignored）：每 Cell 25 chunk × 5 LOD 的 GLB、官方 20 m GeoTIFF、UE Landscape R16（505 × 505、15.873 m、ScaleZ 400、actor Z offset、round-trip ≤ 0.016 m）。

| LOD | 間距 | 三角形/chunk | GLB KB/chunk | 誤差 p99（chunk p95） | 切換距離 @4 px（ESTIMATE） |
|---|---:|---:|---:|---:|---:|
| 0 | 20 m | 12,800 | 374 | 0 | — |
| 1 | 40 m | 3,200 | 100 | 12.9 m | 3.1 km |
| 2 | 80 m | 800 | 29 | 23.0 m | 5.6 km |
| 3 | 160 m | 200 | 10 | 41.7 m | 10.1 km |
| 4 | 320 m | 50 | 4.4 | 78.8 m | 19.2 km |

切換距離模型：螢幕 1125 px、垂直 FOV 60°（假設，非實測鏡頭）。每 8 km Cell LOD0 = 320k 三角形。以 800 m 高度估算一個視點的地形三角形約 0.5 M（ESTIMATE）。目前是規則網格子取樣；陡坡 LOD 誤差偏大，下一階段改用誤差驅動的簡化（或 UE Landscape LOD）。

**重現性（MEASURED）**：聯合建置 manifest `440c022b…` 重複兩次相同；獨立建置 Cell A `3c9b32a3…`、Cell B `526c9212…`，其 255 個 chunk 與聯合建置逐位元相同。

## 5. 接縫 QA（MEASURED，`tools/ntw/terrain_qa.py`，全部讀取實際輸出的 GLB）

**相鄰 Cell / chunk**：425 條共用邊（含 25 條跨 Cell）位置 0 差異、法線 ≤ 1e-6°、UV 0。跨 LOD（LODk vs LODk+1）340 對，最大縫 79.8 m（160 m LOD 的陡坡），**0 對超過 skirt**。813,714 個地表/stitch 面全部朝上、skirt 全部垂直（本輪先發現並修正了繞序錯誤——Blender 渲染時地形全黑，數值驗證後修正並加入永久檢查）。

**信義四邊**（已接受 R16 透過已接受 ENU 公式精確反算）：

| 邊 | 原始官方 DEM − 信義：中位 / p95 / 最大 | 只用平移放置的水平誤差 / 高度誤差 |
|---|---|---|
| 南 | −0.34 / 1.22 / 3.64 m | 平均 6.0 m、最大 10.4 m / 最大 5.6 m |
| 東 | −0.35 / 0.81 / 6.01 m | 5.1 / 10.4 m / 0.6 m |
| 北 | −0.34 / 0.44 / 1.92 m | 10.7 / 15.3 m / 2.7 m |
| 西 | −0.34 / 0.46 / 0.60 m | 8.1 / 15.3 m / 0.6 m |

- 系統性 −0.34 m = 信義當年加的 +0.342 m 全域偏移（官方 DEM − WFS 地面：信義內 −0.36 m、信義外 +0.09 m；1.6 km chunk 中位數 −0.40 ~ +1.03 m）→ **高程基準因地而異，不能用單一全域偏移**。
- 只用平移放置信義：水平誤差最大 15.3 m、坡地高差最大 5.6 m → **證明必須用完整仿射/精確反算，不能只平移**。
- 只做 200 m 融合帶（conform）：中位 ≈ 0，但東邊坡地最大仍 4.3 m（20 m 三角形跟不上 3.97 m 的 Landscape 邊），且南邊法線 p95 由 5.0° 增至 10.8° → 不採用，只保留作比較。
- **出貨方案 = stitch strip**：新地形在信義外框外切出洞，再以 GEOS 約束 Delaunay 只用「信義 Landscape 邊界頂點（精確高度）」與「洞邊 chunk 頂點」三角化。每個 LOD：邊界頂點 0 缺漏、高度誤差 0.000 m、100 % 邊界線段為網格邊、洞邊頂點 100 % 等於 chunk 頂點、缺口/重疊面積 < 0.15 m²（約 20 km 接縫線上的 float32 噪音）。遠距 LOD 的 stitch 邊界會與 LOD0 信義邊緣相差 0.9 m（LOD1）至 19.7 m（LOD4），須與 UE Landscape LOD 一起處理（下一 Gate）。
- 碰撞：stitch 模式下洞被信義 Landscape + stitch 完全覆蓋，信義邊緣垂直落差 0 → 不會掉穿；**Unreal 碰撞 trace NOT TESTED**。
- 資料來源比較：mirror − 官方（同兩個 Cell 5,151 點）中位 0.01 m、p95 2.88 m、最大 12.1 m（Web Mercator 重取樣在坡地的差異）→ 生產改用官方節點。

視覺：`docs/evidence/ntw/terrain/xinyi_seam_profiles.png`（四邊剖面）、`xinyi_seam_conform_diff.png`（融合帶差異圖）、`renders/xinyi_seam_compare.jpg`（150 m/300 m/正射：一般 vs 除錯著色，一般著色下看不到接縫）。

## 6. 建築 shard 接縫（MEASURED，`tools/ntw/building_shard_test.py`；PR #22 審查 P0）

南 shard（E 304–312, N 2,767–2,768 km）、北 shard（N 2,768–2,769 km，含信義南部）、聯合 shard，使用未修改的已接受幾何管線。

- 政策：擁有權 = 頂點平均質心 → 500 m tile → shard（不裁切、不重複）；**fetch halo 0 m**（質心在 shard 內的 part 必與 shard 相交）；culling bounds = 實測輸出物件聯集（南 shard 超出 20 m、北 shard 37 m，政策上限 500 m）；信義 ID 抑制。
- 結果：57/57 tile **逐位元相同**；南 4,810 + 北 11,353 = 聯合 16,163 parts，0 個被兩個 shard 同時擁有，0 孤兒；信義 2,504 parts 被抑制、0 筆被重建。
- **嚴格模式 fail-closed**：`tp_building_height.211054` 的 GEOS 修復碎片只有 4.6 × 10⁻⁶ m²（6 m 長、亞毫米寬的數化尖刺），float32 無法表示 → 已接受的嚴格規則讓整個北 shard 失敗。本輪新增**預設關閉**的全域政策 `FRAGMENT_POLICY`（非最大碎片、< 0.01 m²、量化後塌縮 → 記錄 ID 與面積），只在 shard 測試啟用；正式啟用前必須跑 AGENTS.md 規定的鎖定代表集 + 全信義回歸（審查第 6 點）。

## 7. Blender 5.2 渲染（`tools/ntw/blender_terrain_views.py`）

固定鏡頭（EPSG:3826 + TWVD2001 高度，垂直 FOV 60°）：150 m 接縫、300 m 信義、600 m 山丘、800 m 總覽、3 km 遠景、17 km 正射。場景 = 新地形 chunk + stitch + 由已接受 R16 重建的信義 Landscape + 信義 runtime 建築 tile（唯讀，以量測仿射放置）。輸出 `docs/evidence/ntw/terrain/renders/`（JPEG）與兩張對照圖：`xinyi_seam_compare.jpg`、`lod_compare.jpg`（LOD2 在 800 m 已失去河道細節 → 只能用於 ≥ ~5.6 km）。
Workbench 陰影已關閉：其 shadow volume 需要封閉網格，開放地形 + skirt 會產生假黑塊（非幾何問題）。

## 8. Unreal 隔離測試（`tools/ntw/ue_terrain_pilot_check.py` + `ue_terrain_pilot_analyse.py`）

- 只用 scratchpad 中的**臨時專案** `NTWTerrainPilot.uproject`（PythonScriptPlugin + EditorScriptingUtilities）；正式 `AirCombatWorld` 專案與場景未開啟、未修改。
- UE 5.8 Interchange 匯入兩個 Cell 的 LOD0 50 個 chunk + 信義 stitch：51/51 成功、三角形與頂點數 = GLB、關閉 Nanite（mobile/SM5 基準）。
- **發現**：預設匯出（glTF node 帶 NTW 平移）會被 Interchange **烘進頂點**，頂點距原點 ~80 km → float32 誤差 5.5 mm。改用 identity node 匯出（`--identity-nodes`，與已接受信義合約相同：頂點 tile-local、原點在 manifest）→ 誤差 0.11 mm。
- 兩種匯出在引擎內共用頂點 14,430 個，**高度差 0.0 m**。
- **NOT TESTED**：Landscape actor、World Partition 串流、HLOD、碰撞 trace、浮動原點/LWC 行為、手機效能。本輪不宣稱串流或手機效能通過；30 FPS 是未來驗收目標。

## 9. PR #16 / #22 未解項目處理狀態

| 項目 | 本輪 | 後續 Gate |
|---|---|---|
| DEM 缺口（P0） | 官方核對完成：官方產品缺 → BLOCKED，位於遠景 | 替代官方來源/授權 → 遠景生成 |
| 信義地形接縫（P0） | stitch 水密（高度、法線、覆蓋）；UE 資產層級共用頂點 0 差 | UE Landscape actor + stitch 實際場景、碰撞 trace、Landscape LOD 與 stitch LOD 協調 |
| 地形/建築 shard、halo、culling（P0） | 兩者皆有獨立 vs 聯合逐位元相同證據；halo/culling 政策明文化 | 整個生產區規模 + 跨行政區界 |
| 高程基準 | 量測：信義 −0.36 m vs 其他 +0.09 m、chunk 間 −0.40 ~ +1.03 m | 區域性校正政策；建議建築底座取官方 DEM（非 WFS），待審查 |
| 大量建築高度不足 | 未處理（Phase 2C） | NLSC LOD1 授權/價格/覆蓋 gate |
| 建築 LOD 與 identity | 未處理 | `(provider, record_id, part) → proxy` 多對多映射 |
| Fail-closed 與重現性 | 地形 fail-closed、建築碎片政策（預設嚴格）、所有 manifest/SHA | 碎片政策回歸、標準建置平台（Linux CI） |

## 10. 下一階段（擴展到台北盆地、桃園、新竹、北海岸）的工程工作與驗收門檻

1. **地形生產（可飛行 + 生產區）**：生產區 16 × 16 = 256 個 Cell，其中含陸地 111 個（可飛行 91 + 環帶 20）（其餘海面用 0 m 水面 + 向量海岸）。官方圖幅包需要再加基隆市（已列目錄）。門檻：每個生產 Cell 陸地缺節點 = 0（否則 BLOCKED）；同 LOD 共用邊位置差 = 0；跨 LOD 縫 ≤ skirt；獨立 = 聯合逐位元；重複建置 manifest 相同。
2. **海岸**：向量海岸線切地形；近岸 DEM 0 m/外海 NODATA 一律以向量海岸為準。門檻：海岸線偏差 ≤ 1 個 LOD0 格（20 m）。
3. **遠景**：224 km 世界 L0（160 m）地形 + 城市輪廓 impostor；DTM 缺口區需替代官方來源，否則以明確標示的遠景替代（不得當真實地形）。
4. **UE 整合**：identity-node 匯出 + double 精度 actor 擺放；決定「Landscape vs 靜態網格 chunk」；World Partition 串流格（1.6 km chunk，與 8 km 生成 Cell 解耦）；HLOD；信義 Landscape + stitch 場景與碰撞 trace。門檻：串流測試以 300 m/s 飛越生產區，量測 hitch 與記憶體（數值由實測訂定）；手機實機另測。
5. **建築**：碎片政策回歸後，全臺北 WFS 依 8 km Cell 分片 + checkpoint/resume；L3 信義 ID 抑制保留；高度來源 Phase 2C。
6. **高程基準**：以 WFS 地面（臺北）量測每 Cell 偏移，建築底座取官方 DEM；記錄每 Cell 殘差。

## 11. 已驗證 / 未驗證

已驗證：戰場尺寸比較與位置、四層區域、DTM 缺口官方核對、兩個 Cell 官方 DEM 地形與 LOD、同 LOD/跨 LOD/跨 Cell 接縫、獨立 vs 聯合逐位元、信義 stitch 水密、建築 shard 逐位元與擁有權、Blender 固定鏡頭、UE 隔離資產匯入。測試：`tests/test_ntw_phase2b.py` 17 項 + Phase 1/2A 測試全部通過（64 passed, 9 skipped 為既有略過）。

未驗證：UE runtime 串流/HLOD/碰撞/Landscape actor、手機效能、遠景 L0、DTM 缺口替代資料、NLSC LOD1 授權、建築高度、碎片政策的全信義回歸、跨平台位元重現。

## 12. 重現

```text
python tools/ntw/fetch_tgos_dtm.py 臺北市 新北市 新竹縣 新竹市 桃園市 苗栗縣
python tools/ntw/battlefield_planner.py && python tools/ntw/battlefield_zones.py
python tools/ntw/build_terrain_cells.py --cells C+0038+0346 C+0038+0345 --out data/generated/ntw/terrain/joint_run1
   (重複 joint_run2；--cells 單一 Cell 為 cell_a / cell_b；--xinyi-mode conform → joint_conform；--no-xinyi-conform → joint_raw；
    --identity-nodes → joint_ue_local)
python tools/ntw/terrain_qa.py
python tools/ntw/building_shard_test.py
blender -b --python tools/ntw/blender_terrain_views.py -- --run <abs joint_run1> --lod 0 --out <abs dir>   (另 --lod 2、--debug-seam)
UnrealEditor-Cmd <臨時專案>.uproject -ExecutePythonScript=tools/ntw/ue_terrain_pilot_check.py -unattended -nullrhi
   (env ACW_NTW_TERRAIN_RUN, ACW_NTW_UE_REPORT)；python tools/ntw/ue_terrain_pilot_analyse.py
python -m pytest tests/test_ntw_phase2b.py
```
