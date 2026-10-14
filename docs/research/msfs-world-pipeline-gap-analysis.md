# 北台灣世界生成流程 × MSFS 架構對照研究（Issue #28）

日期：2026-10-14 · 分支：`research/issue-28-msfs-world-pipeline`（自 `origin/main` @ `08afe38` 建立）

> **盤點時間快照：** 本報告的「`main` 只合併 PR #1」是 **2026-10-14 建立研究分支時** 的 Git 狀態，不是持續更新的即時清單。後續 PR（例如歷史文件 #4）可能已合併；請以 GitHub 的即時 base/head 與合併紀錄為準。本報告不代表授權未確認的資產已可出貨。

性質：**純研究、唯讀盤點**。未修改任何生成器、Unreal runtime、信義區資產或其他 PR 分支；未下載 GIS 資料。
修訂：rev 1（回應 PR #29 Sophira Review #5512312587）— 更正 WorldCover 授權敘述並補品質限制；台灣官方資料授權改為資料集層級核對；移除無證據的「比 MSFS 嚴格」比較；分開證據等級；地表語意 v0 驗收改為單一 Cell 一份 raster + 小型 manifest。研究範圍不變。

證據標記：

| 標記 | 意義 |
|---|---|
| **[SDK]** | Microsoft Flight Simulator 官方 SDK 文件（docs.flightsimulator.com） |
| **[MS]** | Microsoft／Asobo 官方文章（第一手） |
| **[媒體]** | 媒體報導或媒體轉述的訪談（含 Blackshark.ai 相關報導）；二手資料，不等同官方技術文件 |
| **[社群]** | 開發者論壇、玩家觀察；只當線索，不當事實 |
| **[Repo]** | 本 repo 指定分支上的實際檔案；多數位於未合併的 Draft PR，屬進行中實驗，狀態以 §1.2 標籤為準 |
| **[Gov]** | 台灣官方網站或 data.gov.tw 資料集描述（經搜尋摘要） |
| **[審查核對]** | PR #29 審查者在本 session 網路受限時，親自讀取官方頁面後提供的核對結果 |
| **[推論]** | 本報告的判斷，非外部事實 |

> **來源限制（必讀）**：本環境的網路政策封鎖了 `docs.flightsimulator.com`、`blackshark.ai`、`techcrunch.com`、`data.gov.tw` 等網域的直接讀取，外部資料全部經由搜尋工具的**摘要**取得，**未逐頁親讀**。因此：每項外部結論都附原始連結，供人工複核；授權欄位除標 **[審查核對]** 者外，只代表搜尋摘要與既有 repo 文件一致。即使是資料集層級已核對的授權，實際下載檔案仍須記錄來源與版次；商業出貨前須留存原頁截圖。

---

## 0. 結論先講

1. **MSFS 真正值得借的不是 AI 或雲端，而是「一份語意母資料驅動所有層」的資料架構。** 官方 SDK 把建物 footprint、biome、水系／道路向量和高程一起放進同一套四分樹資料（CGL），再依品質等級決定要用攝影測量、航照，還是「DEM + 程序合成地表」[SDK]。我們的 repo 在高程和建物幾何上已有明文記錄、可重現的 QA 與 manifest（MSFS 內部 QA 未公開，因此不做優劣比較），**最大的缺口是「地表語意層」：目前沒有任何土地覆蓋分類資料**，所以地面材質、植被、森林邊界、水岸都只能在信義區靠 OSM 標籤手工拼湊 [Repo]。
2. **MSFS 的建築是「統計上大致正確」，錯誤率被公開承認** [媒體]。我們不需要訓練模型，但可以借它的思路：用區域先驗（土地利用 + footprint 形態 + 已知樓層分布）推論類別與高度，並且**用台北 WFS 真值做盲測**，量出錯誤率再決定能不能用。
3. **MSFS 的多畫質是「換表示法」，不只是減面**：低品質等級改用合成地表、LOD 用螢幕佔比而非距離 [SDK]。另外，「遠景森林以地面貼圖呈現」是 repo Draft PR #20 對 AC7 畫面的觀察 [Repo]，不是 MSFS 的事實。repo 已經自己量到「稀疏區的街廓合併 LOD 只省 1.2–1.3×」，正好說明需要換表示法而不是繼續減面。
4. **大部分既有工程不需要動**：建築幾何管線、NTW 座標框架、8 km Cell／1.6 km chunk、官方 20 m DEM 地形鏈、World Partition 串流設定、信義 L3 抑制規則、hero 地標層、manifest/SHA 稽核，全部維持（§6）。
5. **授權是比工程更硬的瓶頸**：正射影像、國土利用 shp、NLSC 三維建物、台北建物高度 WFS 的「商業再散布」都**未確認**；可商用（需署名）的主要是資料集層級標示 OGDL v1 的官方資料（176927 DEM、57873 林型已經審查核對）、ESA WorldCover（CC BY 4.0）與 Copernicus Sentinel（§4）。

**最值得優先做的三件事**（§5，詳細成本與驗收）：
① 地表語意層 v0（兩個既有 Cell）；② 建築語意屬性 + 區域先驗，以台北 WFS 盲測；③ 多畫質「表示法分層」規格（離線、只出表格）。
這是建議排序，**不是三項同時開工的核准**：由使用者選定第一個 pilot 後才開 issue 或寫程式。

---

## 1. Repo 現況盤點

### 1.1 先釐清「已接受」的意思

`main` 只有 PR #1（信義 2 km 灰盒，UE 5.8 GUI 驗證）[Repo `main` @ `08afe38`]。其餘所有北台灣與信義 v2 工作都在**未合併的堆疊 Draft 分支**：

```text
main (PR #1 greybox)
 └ feat/xinyi-terrain-v0 → feat/xinyi-unreal-v2 (PR #9) → feat/opus55-xinyi-visual-quality
     ├ PR #16 NTW Phase 1 → PR #22 Phase 2A → PR #23 Phase 2B → PR #25 runtime gate → PR #26 seam/LOD closure
     ├ PR #14 material ImageGen · PR #15 環境資產盤點 · PR #18 植被 pilot · PR #20 AC7 森林研究
     └ PR #24 / #27 ForestSpike（#27 base = #24）
```

因此本報告的 **ACCEPTED** 指「repo 文件記錄為已通過擁有者審查的 gate」（主要見 PR #26 分支上的 `AGENTS.md`），**不代表已合併到 `main`**。

### 1.2 能力盤點表

狀態：**ACCEPTED** 已通過 gate · **EXPERIMENTAL** 有程式／有量測但未接受 · **PROPOSED** 只有設計 · **MISSING** 沒有 · **BLOCKED** 被資料或授權卡住。

| 能力 | 狀態 | 證據（分支：檔案） |
|---|---|---|
| GIS 來源釘選、SHA、manifest | ACCEPTED（模式） | PR #26：`AGENTS.md` §Source/policy drift、`docs/north-taiwan-world-foundation-v0.md` §13 |
| 座標：EPSG:3826 − 固定原點的 NTW frame；幾何 tile-local float32、世界位置 double | EXPERIMENTAL（Phase 1 提案，Phase 2B/#25 引擎實測 0.0 cm 擺放誤差） | `tools/ntw/frame.py`；`docs/north-taiwan-runtime-gate-phase2b.md` §0 |
| 信義 25 tile 建築幾何（GEOS 修復 → 500 m tile → float32 量化 → GEOS CDT → trimesh → 嚴格 QA → Blender） | ACCEPTED | `AGENTS.md`；`docs/xinyi-v2-full-xinyi-cloud-result.md` |
| 信義 MOI 20 m DTM 地形 + UE Landscape（631² R16） | ACCEPTED（文件稱 PASS candidate，後續 PR 以「accepted Landscape」引用） | `docs/xinyi-terrain-v0-dtm-result.md`；`docs/xinyi-unreal-v2-contract-result.md` |
| 北台灣三個 2.5 km 建築 pilot（WFS / Overture） | EXPERIMENTAL（0 失敗、可重現） | `docs/north-taiwan-world-foundation-v0.md` §9 |
| 112 km 可飛行 / 128 km 生產 / 224 km 遠景 世界界定 | PROPOSED（參數化，等審查） | PR #22/#23：`worlds/battlefields/north_core_v1.json` |
| 官方 TGOS 20 m DEM、5 級地形 LOD、相鄰 Cell 接縫、信義 stitch | EXPERIMENTAL（離線 PASS） | PR #23：`tools/ntw/build_terrain_cells.py`、`docs/north-taiwan-core-battlefield-terrain-phase2b.md` §4–5 |
| UE 5.8 隔離 PIE：WP 1.6 km/8 km 格、300 m/s 串流、碰撞 trace | EXPERIMENTAL（桌機 iGPU、兩個 Cell PASS） | PR #25：`tools/ntw/ue_gate/`、`data/ntw/runtime/runtime_gate_result.json` |
| 固定洞 stitch、混合 LOD、collision-only flange | EXPERIMENTAL（大部分 PASS；south@0.55 物理穿透、1 px 殘留仍 FAIL） | PR #26：`docs/north-taiwan-seam-lod-closure-phase2b-c.md` §0 |
| 跨 Cell 建築 shard（擁有權、0 重複、逐位元相同） | EXPERIMENTAL（機制 PASS，生產 FAIL：退化 part、跨提供者重疊） | PR #25 §7.3；`tools/ntw/building_cell_shard_test.py` |
| 建築高度（台北以外） | **BLOCKED**（Overture 90.6 % 退回 9.6 m） | `docs/north-taiwan-world-foundation-v0.md` §5 |
| 新竹縣山區 DTM 缺口（154.6 km²，官方 2025 產品本身缺） | **BLOCKED**（位於遠景區） | PR #23 §3 |
| 建築類別（8 類：low / walkup / huaxia / res_tower / office / podium / civic / school） | EXPERIMENTAL，**只在信義 lookdev**，依 WFS 樓層、層高、面積判斷 | `tools/lookdev/build_look_tiles.py::classify`、`tools/lookdev/profiles/facade_taipei_xinyi_v0.json` |
| 建築年代 metadata（通用 schema + 台北使照 adapter） | EXPERIMENTAL（資料基礎，未被渲染使用） | `tools/building_era/`、`docs/taipei-building-era-metadata-v0.md` |
| 建築 LOD：L2 逐棟 / L1 街廓聯集 / L0 剪影 | EXPERIMENTAL（尺寸研究；稀疏區 L1 只省 1.2–1.3×） | `tools/ntw/lod_prototype.py`、`data/ntw/lod_prototype.json` |
| 建築 HLOD 進引擎 | MISSING（明確 NOT TESTED） | PR #25 §0 |
| 道路 | EXPERIMENTAL（信義：OSM 道路 SDF 資料貼圖 + 標線網格）；北台灣：只統計 Overture 數量 | `tools/lookdev/build_ground.py`；Phase 1 §5 |
| 橋樑、高架、匝道（Layer B） | PROPOSED（設計）/ MISSING（`build_ground.py` 直接跳過 bridge/tunnel） | `docs/architecture.md` §3B；PR #15 §2.1 |
| 水系、海岸 | 信義：地面資料貼圖中的一個類別；北台灣：「向量海岸 + 0 m 水面」為 PROPOSED | `build_ground.py`；PR #23 §10 |
| **土地利用／地表覆蓋分類** | **MISSING** | PR #15 §2.2（grep 確認無 paddy / greenhouse / landcover） |
| 植被：信義街樹（28 三角形 blob）、山林 clump（100 三角形） | EXPERIMENTAL（lookdev） | `build_ground.py::write_tree_mesh / write_forest_clump` |
| 植被：4 種樹冠原型 × 3 LOD | EXPERIMENTAL（待美術審查） | PR #18：`tools/vegetation_pilot/` |
| 森林遠景表現（AC7 對照） | EXPERIMENTAL（B1a 四臂比較，F10 接縫 FAIL） | PR #20 研究；PR #24、#27 |
| 材質：程序化立面／屋頂 HLSL | EXPERIMENTAL（lookdev，信義專用） | `tools/lookdev/shaders/`、`docs/xinyi-look-v1-visual-pass.md` |
| 材質：AI 生成表面候選 6 張 | EXPERIMENTAL（未核准、0 runtime 使用） | PR #14 |
| 材質庫規格 | PROPOSED | `docs/xinyi-custom-material-library-spec-v0.md` |
| QA：嚴格幾何 gate、Blender 匯入稽核、CI workflow | ACCEPTED（信義）；NTW 用同一套 | `.github/workflows/xinyi-*.yml`、`tools/citygen_v2/strict_qa.py` |
| 手機效能、packaged build | MISSING（全部 NOT TESTED） | PR #25/#26 §0 |
| 資料授權欄位進 manifest | MISSING（授權只寫在文件，manifest 沒有欄位） | Phase 1 §13；PR #15 §11 |

**一句話**：幾何與地形骨架已經相當成熟；缺的是「地表長什麼樣子」的語意資料，以及台北以外的建築屬性。

---

## 2. MSFS 2020／2024 公開可確認的做法

| 主題 | 公開事實 | 等級 | 來源 |
|---|---|---|---|
| 世界品質三級 | Level 1 攝影測量；Level 2 DEM + 航照；Level 3 DEM + **texture-synthesized** 地表。Level 3 用於離線世界，或航照品質不足的地方 | [SDK] | [Using The SDK (MSFS 2024)](https://docs.flightsimulator.com/msfs2024/html/1_Introduction/Using_The_SDK.htm) |
| 世界資料容器 | CGL 存影像、高程、向量（水、道路）、**建物 footprint、biome 資訊**；四分樹、Mercator 投影；目前 add-on 不能編輯 | [SDK] | [CGL Files](https://docs.flightsimulator.com/msfs2024/html/2_DevMode/Project_Editor/File_Formats/CGL_Files.htm) |
| 植被 | Biome = 規則集；物種定義檔 + biome 定義檔（XML），biome 依「自然植被類型」與「生態區」組織；可用多邊形覆寫 biome 或排除植被 | [SDK] | [Biomes And Vegetation](https://docs.flightsimulator.com/msfs2024/html/5_Content_Configuration/Environment/Vegetation/Biomes_And_Vegetation.htm)、[Biome Definitions](https://docs.flightsimulator.com/html/Content_Configuration/Environment/Vegetation/Biome_Definitions.htm)、[Polygon Objects](https://docs.flightsimulator.com/msfs2024/html/2_DevMode/Scenery_Editor/Objects/Polygon_Objects.htm) |
| 程序化建築 | `ProceduralAssets`：以少量基礎模型 + 參數隨機生成建築；roof／footprint 參數未公開 | [SDK] | [Asset Types](https://docs.flightsimulator.com/msfs2024/html/2_DevMode/Project_Editor/Asset_Types.htm) |
| 手工覆寫 | Exclusion 多邊形／矩形移除自動生成的建築、植被；2024 的程序建築須用 rectangle `excludeAllObjects` | [SDK][社群] | [Polygon Objects](https://docs.flightsimulator.com/msfs2024/html/2_DevMode/Scenery_Editor/Objects/Polygon_Objects.htm)、[DevSupport 討論](https://devsupport.flightsimulator.com/t/buidling-exclude-not-working-within-the-scenery-editor/13404) |
| LOD | 2024 依**螢幕空間**選 LOD：`minSize` = 投影包圍球垂直螢幕佔比 %；景物建議 ≥ 4 級，每級約減半；2020 有強制下限規則 | [SDK] | [LOD Selection System](https://docs.flightsimulator.com/msfs2024/html/3_Models_And_Textures/Modeling/LODs/LOD_Selection_System.htm)、[Scenery LODs](https://docs.flightsimulator.com/msfs2024/html/3_Models_And_Textures/Modeling/Landscape/LODs.htm)、[2020 LODs](https://docs.flightsimulator.com/html/Asset_Creation/3D_Models/LODs.htm) |
| 規模與串流 | 2.5 PB 以上 Bing 資料；1.5 B 建物、2 T 樹；攝影測量、向量地圖、樹與環境遮罩預處理後存 Azure、串流給玩家 | [MS] | [Microsoft Game Dev 文章（2021-07）](https://developer.microsoft.com/en-us/games/articles/2021/07/microsoft-flight-simulator-the-future-of-game-development/) |
| AI 建物重建（Blackshark.ai） | 以深度學習從 2D Bing 影像分割分類建物、植被、道路；推 footprint、高度、屋頂與類型；缺 GIS 高度時用陰影線索；立面依位置與脈絡補上；全球處理 < 72 小時 | [媒體]（二手報導） | [TechCrunch（2020-08）](https://techcrunch.com/2020/08/17/meet-the-startup-that-helped-microsoft-build-the-world-of-flight-simulator)、[Trending Topics](https://www.trendingtopics.eu/blackshark-ai-grazer-konstruieren-15-milliarden-gebaeude-fuer-flight-simulator/)、[stormbirds 整理](https://stormbirds.blog/2020/08/07/how-microsoft-flight-simulators-world-comes-together-with-blackshark-ai/) |
| 已知錯誤 | 墨爾本 200 層大樓：OSM 錯誤資料被直接採用；方法是統計式，個別建物會錯 | [媒體] | [PCGH](https://www.pcgameshardware.de/Microsoft-Flight-Simulator-Spiel-15259/News/Azure-KI-Hochhaus-Spielwelt-nachbauen-1356585/) |
| 2024 地表與樹 | 約 28,000 個代表性 tile 人工標註 → ML 產生候選 → 人工審查 → 重訓，共四輪；ML 辨識樹種並放置；約 30 種 biome（後者為媒體轉述） | [媒體]（轉述主管訪談） | [GameSpot 轉述 RPS 訪談](https://www.gamespot.com/articles/ms-flight-sim-24-dev-on-why-the-game-needed-to-use-machine-learning-and-ai/1100-6527889/)、[Flightsim.to](https://news.flightsim.to/jorg-neumann-reveals-details-on-microsoft-flight-simulator/)、[CO/AI](https://getcoai.com/news/microsoft-flight-simulator-2024-adds-ai-terrain-and-new-career-modes) |
| OSM 的角色 | 玩家觀察到 `building:levels` 會影響建物、樹與水似乎不來自 OSM | [社群，未證實] | [MSFS 論壇](https://forums.flightsimulator.com/t/osm-openstreetmap-data/675662)、[AVSIM 整理](https://www.avsim.com/forums/topic/574363-a-nice-summary-of-the-infrastructure-types-in-msfs/) |
| Microsoft 開放建物 footprint | 約 1.4 B 棟、ODbL、有估計高度欄位（缺值 = −1） | [社群]（OSM wiki／論壇） | [OSM wiki: GlobalMLBuilding](https://wiki.openstreetmap.org/wiki/Import/Catalogue/GlobalMLBuilding)、[OSM 社群](https://community.openstreetmap.org/t/why-aren-t-we-using-globalmlbuildingfootprints/106872) |

**範圍提醒**：SDK 確認的是世界資料的分級（三個品質等級、Level 3 離線退回）與容器（CGL），**不代表我們取得或了解 Microsoft 的全球推論與 runtime 管線**。

**未知（不推測）**：模型架構與訓練資料、2024 的 DEM 解析度、品質等級在 runtime 如何切換、程序建築的屋頂文法參數、texture synthesis 的演算法。

---

## 3. 工程方法比較

### 3.1 對照表

| 面向 | MSFS 公開做法 | 我們現況 | 判斷 |
|---|---|---|---|
| 資料架構 | 同一份四分樹資料承載 footprint、biome、向量、高程 [SDK] | GIS → WorldModel/ledger → GLB 的分離已存在；**缺地表語意** | **借**：補上語意層，不改容器 |
| 地形 | 全球 DEM + 攝影測量；細節依需要生成 [SDK][媒體] | 官方 20 m DEM 原生節點、5 級 LOD、逐位元可重現（兩個 pilot Cell 的圖幅 header 記載 LiDAR 與 2021–2022 不同測製日期，不假設全區相同） | **不改**：來源、版次、圖幅測製日期可追溯；MSFS 的 DEM 來源未公開，不做優劣比較 |
| 地表外觀 | 三級：攝影測量 / 航照 / **語意合成地表** [SDK] | 只有信義 OSM 類別貼圖；航照授權未確認 | **借 Level 3 思路**：類別 → 材質，不依賴航照 |
| 建築 | ML 推 footprint / 高度 / 屋頂 / 類型，統計上正確 [媒體] | 台北：WFS 真值 + 8 類規則（僅信義）；台北外：只有 footprint | **借「區域先驗 + 量化錯誤率」**，不借 ML |
| 植被 | Biome 規則表（物種 × 生態區）+ 遮罩；多邊形覆寫 [SDK] | 單一 blob 樹、山林 clump；4 種原型待審 | **借 biome 規則表**，由語意層驅動 |
| LOD | 螢幕空間 `minSize`、≥ 4 級、每級減半 [SDK] | 地形依距離估切換；建築 L2/L1/L0 研究；已得出「預算不能用半徑」 | **借螢幕佔比 + 換表示法** |
| 手工覆寫 | Exclusion 多邊形 / 手工 POI 疊在程序結果上 [SDK] | Hero 地標層 + 信義 L3 以來源 ID 抑制 | **已具備**，不改 |
| 串流 | 雲端串流 PB 級資料 + 本地快取 [MS] | 本地 WP 1.6 km / 8 km 格，300 m/s 實測 PASS（兩 Cell） | **不借**：單一區域遊戲不需要雲端串流 |
| QA | 未公開；公開承認有錯 | 嚴格 fail-closed gate、Blender 稽核、可重現 hash | **不改**；但對「推論屬性」需要另一種統計 QA |

### 3.2 三類分界

| 可模仿的工程思想 | 需要自行實作 | 不可取得／授權未確認 |
|---|---|---|
| 一份語意資料驅動地面、植被、建築 | 北台灣地表類別 → 材質／biome 對照表 | Bing 航照與攝影測量、Blackshark 模型與 SYNTH3D、MSFS 資產 |
| 航照不足時退回「語意合成地表」 | 台灣建築類別的區域先驗表 | Azure 處理管線、MSFS 串流架構 |
| 在代表性樣本上人工校正、反覆修正（28,000 tiles 的縮小版） | 盲測工具：用台北 WFS 真值量推論錯誤率 | NLSC 正射影像的烘焙／再散布權（UNKNOWN） |
| 螢幕佔比 LOD、遠景換表示法 | 每類別、每畫質的表示法規格 | Google 3D Tiles（repo 政策已排除） |
| 程序結果 + 手工覆寫分層 | （已有 hero／抑制層） | 國土利用調查 shp（限機關申請） |

---

## 4. 北台灣資料來源與授權

「可取得」≠「可商業再散布」。**商用確認**欄只在找到明確授權條款時填「是」。

| 資料 | 來源 | 解析度／規格 | 覆蓋 | 更新 | 可取得 | 商用再散布／衍生 | 備註 |
|---|---|---|---|---|---|---|---|
| 20 m DEM（2025） | 內政部 TGOS，data.gov.tw 176927 | 20 m 格點，TWVD2001；測製方法與日期依圖幅 `.hdr` 而異 | 北台灣，但**新竹縣山區缺 154.6 km²** | 版次制 | 是（已在 repo 使用） | **是（OGDL v1，須顯名）** [審查核對] [資料集頁](https://data.gov.tw/en/datasets/176927) | 資料集層級授權已核對；實際檔案仍逐包記錄 SHA 與版次 |
| DTM Terrarium mirror | HF `yhzkiki/…` | z13 | 全台 | — | 是 | **UNKNOWN**（`license:other`） | repo 已規定不得出貨 |
| 正射影像 WMTS（PHOTO2） | 國土測繪中心 | 圖磚 z19 | 全台 | 不定 | 可瀏覽／介接 | **UNKNOWN**（目錄標「授權未指定」；原始航照來自農林航測所） | **不得烘焙進資產** [Gov] [depositar](https://data.depositar.io/dataset/wmts-nlsc)、[NLSC 公告](https://www.nlsc.gov.tw/NLSC_Content.aspx?n=11987&s=183225) |
| Sentinel-2 影像 | Copernicus | 10 m | 全球 | 數日一次（一般知識，未查證） | 是 | **是**（自由、完整、開放；修改後須註明 "Contains modified Copernicus Sentinel data [年]"） | 太粗，只適合當色彩校正參考 [Sentinel 授權](https://ads.atmosphere.copernicus.eu/licences/ec-sentinel) |
| ESA WorldCover | ESA | 10 m，11 類 | 全球 | 2020、2021 兩版（無後續年度） | 是 | **是（CC BY 4.0，without restriction of use；須署名／引用）** [審查核對] | 地表語意 v0 的主要來源。**品質限制**：2021 版全球整體分類準確度約 76.7 % [審查核對]；10 m 像元不能當地籍或河岸的精確邊界；窄路、水田、埤塘、工業區在台灣的分類準確度 **UNKNOWN**，須在 pilot 人工抽查 [資料存取頁](https://esa-worldcover.org/en/data-access)、[AWS Registry](https://registry.opendata.aws/esa-worldcover-vito/index.html) |
| 國土利用現況調查 | 國土測繪中心 | 細分類向量 | 全台 | 定期 | **shp 限機關公文申請**；只開放統計 CSV | **BLOCKED** | [供應對象](https://www.nlsc.gov.tw/cp.aspx?n=1549)、[開放公告](https://www.nlsc.gov.tw/NLSC_Content.aspx?n=11987&s=315995) |
| 第四次森林資源調查林型分布圖 | 林業及自然保育署，data.gov.tw 57873 | 航照判釋多邊形（約 4,231 圖幅） | 全台林地 | 第四次調查（民國 97 年起） | 資料集已開放；目前列出 JSON／檔案連結資源，**實際空間向量檔能否取得、比例尺能否與 10 m raster 比較：UNKNOWN** | **是（OGDL v1，須顯名）** [審查核對] | [資料集頁](https://data.gov.tw/en/datasets/57873)；授權已核對，但在取得空間檔前不可宣稱可直接套疊 |
| 河川（河道）／支流 | 經濟部水利署 | 向量（13,262／2,015 筆） | 全台 | 2020 版鏡像 | 是 | **OGDL v1（僅 NCHC 鏡像的搜尋摘要；data.gov.tw 現版未核對）** | [NCHC 鏡像](https://scidm.nchc.org.tw/en/dataset/best_wish25781) |
| 國道／省道中線 | 國土測繪中心，data.gov.tw 73232 | 向量 | 只有國道、省道 | — | 是 | **OGDL v1、免費（搜尋摘要；未經審查核對）** | [data.gov.tw 73232](https://data.gov.tw/en/datasets/73232) |
| 一般道路、水域、機場 | Overture `transportation`／`base`、OSM | 向量 | 全區 | 每月 | 是（repo 已量測） | **有條件**：ODbL 署名 + 衍生資料庫 share-alike；遊戲 3D 屬「produced work」還是「derivative database」**社群無定論** | [OSM legal-talk](https://lists.openstreetmap.org/pipermail/legal-talk/2021-February/009059.html)、[Overture 授權](https://docs.overturemaps.org/attribution) |
| 台北建物 footprint + 高度 | 臺北市 Dashboard WFS | 逐戶紀錄，99.98 % 有高度 | 只有臺北市 | 不定 | 是（373,532 筆） | **UNKNOWN**（未找到授權聲明） | repo 已標 UNVERIFIED |
| 全國三維建物 LOD1（約 536 萬棟） | NLSC 多維度平台 | LOD1 稜柱（含高度） | 全國，**但臺北市不供應** | 109 年更新、111 年再更新 | 憑證線上申請，每次約 13,000 棟 | **UNKNOWN**（只確認須顯名；AI 語料版本「僅限 AI 訓練」） | 與台北 WFS 剛好互補 [Gov] [E政府申請頁](https://www.gov.tw/News_Content_2_679471)、[taic.moda](https://taic.moda.gov.tw/datasets/d536499c-c3c6-4e95-8fcc-15ac5258215a) |
| Overture buildings | Overture | footprint；台北外高度 < 6 % | 全區 | 每月 | 是 | **有條件**（ODbL：OSM、Microsoft、Esri；Zenodo ML 列為 CC BY 4.0） | repo Phase 1 §13 |
| Microsoft ML 建物 | Microsoft | footprint + 估計高度（常為 −1） | 全球 | 2014–2024 影像 | 是 | **有條件（ODbL）** | 台灣高度覆蓋率未驗證 |

**授權框架**：政府資料開放授權條款 v1（OGDL-Taiwan-1.0）允許商業利用與改作、可再授權，且與 CC BY 4.0 相容；必須附顯名聲明，機關可以停止提供 [審查核對] [官方條款](https://data.gov.tw/license)、[SPDX](https://spdx.org/licenses/OGDL-Taiwan-1.0.html)。**授權是逐資料集標示的**：176927、57873 的核對結果不能外推到 data.gov.tw 以外的服務；NLSC 正射影像、台北 `tp_building_height` WFS、NLSC 三維建物 LOD1、ODbL 衍生輸出的商業再散布權仍為 **UNKNOWN**，直到取得該資料集的明確條款。

**已知 BLOCKED**：① 台北以外的建築高度（NLSC LOD1 商用授權未確認）；② 新竹縣山區 DTM 缺口；③ 國土利用 shp（限機關）；④ 正射影像烘焙權；⑤ 台北 WFS 再散布權。

---

## 5. 建議（最多三項）

### 架構圖：語意母資料 → 程序輸出 → 引擎（★ = 建議新增；其餘已存在）

```text
 來源層（釘選 + SHA + ★授權等級）
   官方 DEM │ ★WorldCover／林型／水系 │ 道路(Overture/OSM/國省道) │ 台北 WFS │ Overture 建物 │ hero 登錄
        │
        ▼
 語意母資料層（引擎無關；EPSG:3826 / NTW frame；8 km Cell）        ← MSFS：CGL（footprint + biome + 向量）
   地形格點 │ ★地表類別 raster（10 m）│ 水／路／海岸向量 │ 建物紀錄 + ★class/height_source/confidence │ L3 抑制、hero
        │
        ▼
 程序輸出層（依 ★畫質分層 選表示法）                                ← MSFS：Level 1/2/3、ProceduralAssets、biome
   地形 LOD 0–4 │ 建物 L2/L1/L0 GLB │ ★地面材質遮罩 │ ★植被實例 ↔ 遠景森林貼圖 │ manifest
        │
        ▼
 引擎轉接層      UE 5.8（WP 1.6 km / 8 km）│ Godot 灰盒 │ 其他引擎
        │
        ▼
 遊戲            空戰 │ 地面 │ 塔防 │ 模擬 —— 只讀語意層與輸出，不回寫
```

規則：語意層不知道引擎存在；引擎不修資料錯誤（沿用 `AGENTS.md`「Unreal 不得用來掩蓋來源缺陷」）。

### 建議一覽

| # | 改善 | 效益 | 工程成本 | 授權風險 | 依賴 |
|---|---|---|---|---|---|
| 1 | **地表語意層 v0** | 高：一份資料同時驅動地面材質、植被 biome、森林邊界、水岸；空戰高度最看得見 | 中：約 1–2 週，用現有 rasterio / shapely，不需新框架 | 低（WorldCover CC BY 4.0；只用已核對 OGDL 的向量） | 無 |
| 2 | **建築語意屬性 + 區域先驗，用台北盲測** | 高：台北以外不再是 9.6 m 平板；量化錯誤率後才決定採用 | 中：約 1–2 週，泛化既有 `classify()` 與 `building_era` | 中：推論本身不需新資料；NLSC LOD1 仍 BLOCKED | #1 的地表類別（可先用 Overture 土地使用暫代） |
| 3 | **多畫質「表示法分層」規格** | 中：避免繼續在 L1 減面上投資；讓低／中／高畫質共用同一份語意資料 | 低：約 3–5 天，只出規格與離線統計表 | 無 | #1、#2 的類別欄位 |

#### ① 地表語意層 v0

- **做什麼**：每個既有 8 km Cell **恰好輸出一張獨立版本化的 10 m 語意 raster + 一份小型 provenance manifest**，可重現、不烘焙進 Unreal、不自動升級為生產資料。初版輸入**只用 WorldCover**，加上授權與空間檔都已確認可取得的開放向量（目前尚無一項同時滿足兩者，所以 v0 可能就是純 WorldCover）。**不做 ML**。
- **Provenance**：manifest 逐項列出輸入圖層（來源、版次、授權、SHA）；混合像素以**選用的整數 source-code mask** 指向 manifest 的輸入編號，不在每個像素寫授權字串。
- **借鏡點**：MSFS Level 3「DEM + 語意合成地表」與 biome 規則表 [SDK]；PR #15 也獨立得出「地表類別是 P0」。
- **最小驗證範圍**：**只限**既有兩個相鄰 Cell `C+0038+0346`、`C+0038+0345`（信義 + 南側丘陵、森林、溪流，地形與 UE 場景都已存在）。不擴到其他 Cell。
- **驗收**：
  1. 重複建置逐位元相同；manifest 完整列出每個輸入。
  2. 每個 Cell 一張表：覆蓋率（有效像素 %）、各類別像素分布。
  3. 少量人工抽查區（森林邊界、水體／都市交界、農地；兩個 Cell 內若沒有農地就標 N/A），逐區寫下判讀結果與不確定度。
  4. 與林型圖、水利署河道的重疊率**只列為參考，不作硬性過關條件**；要等空間向量檔確認可取得、幾何與比例尺可比較後才考慮升級。
  5. 審查通過也只代表「v0 研究產出可用」，不自動成為生產圖層。
- **不做**：材質美術、植被放置、改 UE 場景、其他 Cell。

#### ② 建築語意屬性 + 區域先驗（台北盲測）

- **做什麼**：把信義 lookdev 內的 8 類規則提升為通用建物紀錄欄位：`building_class`、`class_source`、`height_m`、`height_source`、`confidence`。台北以外用「地表類別 + footprint 形態（面積、長寬比、連棟偵測）+ 區域高度分布」推論；台北 WFS 有值的地方永遠以真值為準。
- **借鏡點**：Blackshark 用「當地典型樓層數」與脈絡補屬性，且公開承認統計誤差 [媒體]。我們的做法是先量誤差再決定。
- **最小驗證範圍**：Pilot A 台北車站（24,353 棟 WFS 真值）**遮掉高度與樓層**做盲測，量類別混淆矩陣與高度誤差（中位、P90）；通過後才套到 Pilot C 板橋（Overture、91.9 % 退回 9.6 m）。
- **驗收**：無逐棟特例；推論可重現；台北盲測誤差達到事先寫下的門檻（例：類別正確率、高度 P90 誤差，數值在開工前由審查者定）；`*_source` 欄位 100 % 填寫。
- **不做**：重新網格化信義、改幾何管線、申請或下載 NLSC LOD1（授權確認前維持 BLOCKED）。

#### ③ 多畫質「表示法分層」規格

- **做什麼**：一份小型規格，為每個語意類別 × 畫質（低／中／高）寫明表示法與螢幕佔比門檻。例：森林 = 近處實例樹 → 中距 clump／impostor → 遠處只剩地面貼圖；建築 = L2 → L1 → L0 剪影；地形 LOD 下限依畫質不同。
- **借鏡點**：MSFS 螢幕空間 `minSize` 與「每級減半」[SDK]；repo 已量到「預算要按 Cell，不能用半徑」與「稀疏區 L1 只省 1.2–1.3×」[Repo]；AC7 研究觀察到遠景森林是地面貼圖 [PR #20]。
- **最小驗證範圍**：同兩個 Cell，用既有離線輸出統計每個畫質的三角形數、實例數、貼圖數，不進引擎。
- **驗收**：一張表能回答「低畫質在這兩個 Cell 最多畫多少東西」；規格不引用任何引擎專有 API。
- **不做**：改 UE LOD 設定、HLOD 生成、手機實測（另立 gate）。

---

## 6. 不需要更動的既有工程

| 既有工程 | 理由 |
|---|---|
| 建築幾何管線（GEOS 修復 → 500 m tile → float32 量化 → GEOS CDT → trimesh → 嚴格 QA → Blender） | 幾何與 manifest QA 有明文記錄且可重現（MSFS 內部 QA 未公開，不做比較）；新建議只加屬性，不碰網格 |
| NTW 座標框架（EPSG:3826 − 原點、tile-local + double 擺放） | 北台灣尺度下公尺級真實；MSFS 的全球 Mercator 四分樹不適用 |
| 8 km 生成 Cell／1.6 km 串流 chunk／5 級地形 LOD | 已在 PIE 300 m/s 驗證；語意層沿用同一 Cell 鍵即可 |
| 官方 TGOS 20 m DEM 為地形主來源 | 有授權、有測製日期、原生節點零重取樣 |
| World Partition runtime grid 設定（PR #25） | 與本研究無衝突 |
| 信義 L3 sector 與來源 ID 抑制、hero 地標層 | 等同 MSFS「程序結果 + 手工覆寫」，已具備 |
| manifest／SHA／fail-closed 稽核 | 只需加一個授權等級欄位（併入 ①） |
| PR #26 殘留問題（south@0.55 物理穿透、1 px） | 屬引擎接縫問題，與本研究無關；不因此研究重開 |
| 不採用：攝影測量、Bing／Azure、雲端串流、ML 訓練 | 授權不可得、成本不成比例、單一區域遊戲不需要 |

---

## 7. 待人工複核

1. 176927（DEM）、57873（林型）的資料集層級授權已由審查核對為 OGDL v1；仍待確認的是：57873 的實際空間檔能否取得、水利署河道現版與 73232 的授權欄位，以及截圖留存。
2. 向國土測繪中心書面詢問：三維建物 LOD1、正射影像用於商業遊戲衍生資產的條件。
3. 台北 WFS `tp_building_height` 的授權聲明。
4. 法務判斷：由 Overture／OSM 衍生的建築 GLB 屬 produced work 還是 derivative database。
5. MSFS SDK 頁面在本輪只經搜尋摘要取得；引用前建議親讀上列連結。
