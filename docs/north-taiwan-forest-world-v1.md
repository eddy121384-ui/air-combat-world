# North Taiwan Forest World v1 — 陽明山 / 大屯火山群 森林世界（UE 5.8 實機）

日期：2026-10-19 · 分支 `feat/ntw-forest-integration-v1`（自 PR #39 `feat/north-taiwan-forest-coverage-v1` @ `e00dad5`）· worktree `air-combat-world-ntwforest`
主機：i7-12700 + **Intel UHD 770 內顯**、16 GB RAM、UE 5.8、TreeLookdev 隔離專案（未開啟正式 AirCombatWorld / 信義場景）。**Draft，勿 merge。**

## 0. 結論

| 項目 | 結果 |
|---|---|
| 實際完成範圍 | **26.46 × 26.46 km（700 km²）連續真實山區**：淡水河口／觀音山 → 北投、士林、天母盆地邊緣 → 大屯火山群（七星山 1,117 m、大屯山、竹子山、小觀音山）→ 擎天崗、磺嘴山 → 三芝、石門、金山、萬里北海岸。EPSG:3826 E 289,540–316,000 / N 2,773,540–2,800,000。**不是整個北台灣**（§8）。 |
| 森林 | 317 km² 樹木覆蓋全部由 3D 樹木 + 烘焙林冠構成：**3,859,205 棵**（紅楠 A 1.62 M、紅楠第二冠形 B 0.87 M、相思樹 0.63 M、柳杉 0.73 M），573 個 1 km World Partition tile actor、4,454 個 HISM。 |
| 遠近銜接 | 近景 3D 樹 → 每棵樹各自的隨機消失距離（450 m–2.4 km，dither 溶解，無方格切線）→ Landscape 上「由同一批遊戲樹烘焙」的林冠層 + 林冠殼 WPO（保留稜線林冠輪廓）。117 s 飛越 3,518 個影格轉換、**0 個全畫面跳變尖峰**（>3× 局部中位）。 |
| 視覺 | 原生 UE 5.8 MRQ 1080p30 **117 s / 28 km / 240 m/s（864 km/h）、離地 105–358 m（中位 188 m）** 北台灣山林高速飛越：`docs/evidence/ntw/forest_world/fly_yangmingshan_north_1080p.mp4`；6 張代表性空中截圖 + 8 張飛越影格。 |
| 串流 | 240 m/s 即時飛越中 World Partition **0 次串流狀態變化（無 Slow / Critical）**，四次執行皆同；所有 Critical 都在靜態鏡頭之間數公里的瞬移（預期）。事件時間以引擎影格號對應 CSV 推算（`perf_streaming_events.json`）。 |
| 效能（UHD 770，1080p，即時） | 無樹／建物基線 GPU 33 ms；**PC 檔森林飛越 GPU 中位 109 ms（p95 frame 326 ms）**；**行動檔 80 ms（p95 128 ms）**；行動檔 + 提早 LOD + 50 % 解析度 59 ms。這台內顯上**森林層是主要成本、未達可玩幀率**（§6）。手機實機 **NOT TESTED**。 |

## 1. 盤點後選的技術路線

| 既有成果 | 本輪如何使用 |
|---|---|
| NTW Phase 2B（`air-combat-world-ntw`）：官方 TGOS 2025 20 m DEM 讀取器 `tools/ntw/tgos_dem.py`、WorldSpec 座標、`NtwGateLibrary`（WP runtime grid）、`XinyiLandscapeBridge`（無頭建立 Landscape） | 直接沿用：同一 DEM 圖幅、同一 UE 座標（X=(E−296000)×100、Y=−(N−2760000)×100）、同一外掛（複製 NTW 隔離專案已編譯版本）。 |
| PR #39 土地覆蓋（Esri/Sentinel-2 2021 20 m，`data/ntw/forest/inputs_v1/esri2021_20m.tif`） | 森林只來自來源 Trees 類別；草地／農地／都市／水域照原樣留白。 |
| PR #33/#36/#43 三樹種遊戲資產（TreeLookdev 專案，4 級 LOD、葉卡材質、色調變體） | 原封引用 mesh；材質**複製**一份加距離淡出（原件未動）；色調變體沿用 hillside 已接受的 10 組參數。 |
| PR #27 ForestSpike F10（3D 林冠 → 平面遠景有可見接縫） | 本輪重點：遠景林冠不再是另畫的平面，而是**同一批遊戲樹的正射烘焙** + 林冠殼位移 + 逐棵隨機淡出。 |

**不用** Nanite（手機優先）、Lumen、PCG runtime（無頭建圖風險高、需可審核的離線結果）。用：Landscape + World Partition + HISM + Landscape 材質 + MPC 分級參數。

## 2. 資料與區域（`tools/ntw/forest_world/build_region.py`，決定性，seed 20261019）

- **地形**：TGOS 臺北市 + 新北市 124 張 20 m 圖幅、0 個重複節點差異；10 m Landscape 頂點用插值三次樣條（每個官方節點原樣通過），16-bit 量化 2 cm。**官方節點 vs Landscape 頂點最大差 1.0 cm**；**區域內土地覆蓋為陸地但沒有官方節點的像元 = 0**（基隆市與桃園缺口刻意排除在外）。無節點處 = 海，以海岸高度往外緩降的海床填補，0 m 海面。Landscape 2647² 頂點、21×21 component。
- **土地覆蓋（km²）**：樹木 316.5、都市 191.5、水域 167.3、農地 13.8、草地 10.3、其他 < 1。
- **樹種政策（美術指導 v1，非林業調查；官方林型圖 HTTP 403 仍未取得）**：
  - **柳杉造林地**：~280 m 的 Voronoi 地塊，條件為平均海拔 320–980 m、坡度 ≤ 32°、樹木覆蓋 ≥ 75 %；以 ~1.5 km 的「造林區」雜訊群聚選取 → 357 塊直邊深色林分、27.6 km²，6 m 行距（~280 棵/ha）。
  - **相思樹**：< ~420 m 低丘、凸坡偏好、~220 m 群聚，58.5 km²。
  - **紅楠 A / 第二冠形 B**：其餘樹木覆蓋，B 偏好稜線與林緣；~750 m 以上樹高遞減（風衝矮林）。
  - 草原（擎天崗、七星山頂箭竹／芒草）只來自土地覆蓋，不種樹；草地／農地有少量散生樹，避免林緣像剪紙。
  - 平均 **121 棵/ha 樹木覆蓋**。種類分布圖：`docs/evidence/ntw/forest_world/species_map.jpg`。
- **城鎮**（`build_buildings.py`）：Esri「都市」占陸地約 36 %，畫成貼圖時像地磚。改用本機 Overture world band 的建物質心 + 面積（+ 少量高度／樓層）→ **74,907 個方塊**（HISM，常駐不串流），坡地沿等高線、平地依街區角度；高度缺值時依面積種子化樓層。**不是正式城市幾何**（不用輪廓、只用質心與面積）；信義／台北正式建物管線完全未碰。

## 3. UE 5.8 森林系統（`adapters/unreal/ntwforest/`）

| 層 | 做法 | 驗證 |
|---|---|---|
| 地形 | `XinyiLandscapeBridge.create_landscape_from_raw16`，全部 Landscape actor **非空間載入**（26 km 地形常駐，heightmap ~14 MB） | `nf_build.report.json`：441 components、Z 範圍 −45.7 ~ 1,117 m |
| 近景樹 | 每 1 km tile 一個 actor、每（樹種, 色調）一個 HISM；WP grid 1 km / 載入 3.2 km；HISM end cull 2.6 km；無碰撞、有陰影 | 3,859,205 = 預期數；ISM usage 旗標存檔讀回 |
| 逐棵淡出 | `M_NF_*`（複製自 `M_TL_*`）加 keep mask：樹 i 的消失距離 T_i = Near + (End−Near)·rand_i^γ，FadeWidth 內以螢幕空間 interleaved-gradient dither 溶解；樹皮改 Masked 一起溶解 | 沒有任何一條固定的剔除線；密度隨距離漸減 |
| 遠景林冠 | `nf_bake.py`：三種 96 m 環面排列林分（闊葉／相思／柳杉行列），強制 LOD1，正射擷取 BaseColor / 世界法線 / 深度 → `pack_canopy.py` 打包。Landscape 依實際種下樹種比例混合三層，各兩個尺度 + 高度混合（冠形邊界、看不到 96 m 重複），法線彎曲、林隙以冠高壓暗、林分尺度色調斑塊 | 烘焙統計：闊葉覆蓋 94 %／冠高中位 10.9 m；相思 64 %／6.9 m；柳杉 88 %／17.8 m |
| 林冠殼 | Landscape WPO：遠處把森林區抬高「該處實際樹高 × 0.8」，700 m → 2 km 漸入，稜線在 3D 樹淡出後仍保有林冠輪廓 | — |
| 分級 | MPC_NF_Forest 一組數字同時控制樹與地形：PC（450 m / 2.4 km、殼 0.7–2 km）、行動（250 m / 1.1 km、殼 0.3–0.9 km）+ `foliage.MaxEndCullDistance` | `nf_tier.py`；正式遊戲以 SetScalarParameterValue 在啟動時設定 |

## 4. 迭代中發現並修正的問題（證據保留於 `iterations/`）

1. **Custom 節點的 WorldPosition 在 LWC 下不是絕對座標** → 第一版遮罩隨相機滑動，山上出現大片「都市」貼圖（`stills01.jpg`）。改用標準節點算 UV／距離／高度，只把 float 傳入 Custom（`nf_landscape.py`）。
2. 都市貼圖像地磚（`stills02`）→ 改為 Overture 建物量體 + 屋頂點陣 + 院落綠地（`stills03–05`）。
3. **在 `-nullrhi` 建立的建物材質沒存到 ISM usage** → 引擎預設 WorldGrid 材質（白盒＋細格線，看似窗帶）；之後的重設材質又因 **WP 外部 actor 未標 dirty** 而沒存檔。修正：以 RHI 建立並讀回旗標；`modify()` + `save_dirty_packages`（外部 actor 屬 map packages）。
4. **反照率尺度**：遊戲樹葉 base color 約為真實林冠的 1/3，曝光因此偏高；建物／鋪面／農地改用 ~0.3× 真實反照率。
5. **關卡自動播放的效能序列與 MRQ 搶相機**（`nf_flight_n_05` 渲染出效能序列的靜態鏡頭、甚至翻轉畫面）→ 新增 `nf_autoplay.py`：MRQ 時關、效能測試時開。`iterations/stills01–05.jpg` 是在此問題存在時渲染的，畫面對應不到靜態鏡頭清單，只作材質狀態的證據。
6. 第一條航線（淡水河 → 北投西側丘陵）主要在建成區上空且偏高 → 改走大屯火山群北坡森林（三芝海岸 → 竹子山／七星山鞍部 → 擎天崗 → 磺嘴山 → 金山海岸）。
7. 農田棋盤格 → 依鄰里角度旋轉、扭曲、加田埂。

## 5. 交付物（`docs/evidence/ntw/forest_world/`）

- **`fly_yangmingshan_north_1080p.mp4`**：原生 MRQ（standalone `-game`、固定步長 30 fps、TSR、無遊戲覆寫），117 s，海面 → 三芝相思林 → 大屯北坡柳杉造林與闊葉林 → 七星／竹子鞍部 → 擎天崗草原 → 磺嘴山 → 金山農田與聚落 → 北海岸。第 0 格為序列前的暖機畫面，已排除。
- `stills/1–6_*.jpg`：300 m 望七星山、1,500 m 總覽、**120 m 柳杉造林地**、200 m 擎天崗草原、3,000 m 淡水河／關渡、400 m 盆地邊緣；`stills/flight_f*.jpg` 8 張飛越影格。
- `canopy_bake_sheet.jpg`、`species_map.jpg`、`flight_temporal_check.json`、`perf_uhd770.json`、`perf_streaming_events.json`、`perf_raw/*`（CSV gz）、`receipts/*`（各 UE stage 收據）。
- `data/ntw/forest_world/v1/`：manifest（輸入／輸出雜湊、樹數、面積）、terrain、canopy 統計、建物索引。

## 6. 效能（EXPLORATORY；UHD 770 iGPU 1080p、未封裝 `-game`、即時播放、單次）

| 執行 | 飛越 GPU 中位 | frame 中位 / p95 / p99 | >50 ms 影格 | 300 m 七星 / 120 m 柳杉 / 200 m 擎天崗 GPU |
|---|---:|---:|---:|---|
| 無 HISM（樹＋建物剔除，`foliage.MaxEndCullDistance 1`） | 33.5 ms | 35 / 41 / 43 ms | 0.4 % | 27 / 32 / 30 ms |
| **PC 檔** | **108.9 ms** | 110 / 326 / 402 ms | 71 % | 246 / 37* / 281 ms |
| **行動檔**（MPC mobile、cull 1.3 km、SP 67 %、陰影 1） | **79.7 ms** | 81 / 128 / 155 ms | 57 % | 60 / 168 / 106 ms |
| 行動 + `r.StaticMeshLODDistanceScale 3` + SP 50 % | 58.9 ms | 60 / 108 / 134 ms | 52 % | 50 / 147 / 91 ms |

\* 靜態鏡頭的時間對齊是以載入停頓推算，PC 檔各鏡頭只有十幾到數十個影格，個別數字不穩（例如 PC 的柳杉 37 ms 明顯低於行動檔）；飛越段樣本數足夠。

- 高空（1.5–3 km）與盆地邊緣：20–36 ms，地形 + 大氣為主。
- 成本集中在**低空密林**：120 m 柳杉造林地（~280 棵/ha、LOD0/1 遮罩葉卡）行動檔仍 147–168 ms。
- 記憶體：峰值 working set 1.9–2.0 GB（未封裝編輯器 `-game`）；CSV `PhysicalUsedMB` 中位 3.4–3.6 GB、iGPU 本地 0.73–0.86 GB。無 HISM 時數字幾乎相同 → 這台機器上記憶體由引擎／地形／編輯器開銷主導，WP 只載入 3.2 km 內的樹 tile。磁碟：樹 tile actor 840 MB（外部 actor 套件）。
- 載入：開場 30–37 s 停頓（地圖 + 首批串流 + 未封裝的 shader 載入）。

## 7. 驗證與重現

```powershell
$py = "D:\Users\EDDY\.venvs\acw-xinyi\Scripts\python.exe"; $ntw = "D:\Users\EDDY\.venvs\acw-ntw\Scripts\python.exe"
& $py tools/ntw/forest_world/build_region.py --out data/generated/ntw/forest_world/v1 --tgos-dir <ntw worktree>/data/generated/ntw/tgos
& $py tools/ntw/forest_world/make_noise.py data/generated/ntw/forest_world/v1
& $ntw tools/ntw/forest_world/build_buildings.py --run data/generated/ntw/forest_world/v1 --world-dir <ntw worktree>/data/generated/ntw/world
& $py tools/ntw/forest_world/flight_path.py data/generated/ntw/forest_world/v1 --route north
# UE stages (one UnrealEditor-Cmd each; env vars set in the calling shell):
run_nf.ps1 nf_probe.py → nf_assets.py → nf_build.py (-nullrhi) → nf_bake.py → (pack_canopy.py) → nf_buildings.py →
  nf_buildings.py ACW_NF_BLD_MAT_ONLY=1 ACW_NF_BLD_REV=6 ACW_NF_BLD_ALBEDO=0.3 (RHI) → nf_landscape.py ACW_NF_LMAT_REV=6 →
  nf_sequence.py (+ ACW_NF_VIEWS=views_north.json ACW_NF_SEQ_SUFFIX=_N) → nf_autoplay.py ACW_NF_AUTOPLAY=0 → nf_mrq_configs.py ACW_NF_MRQ_REV=09
run_nf_mrq.ps1 -Rev 09 -Tag nf_flight_n_09
nf_autoplay.py ACW_NF_AUTOPLAY=1; run_nf_perf.ps1 -Tag pc_r1 ...; nf_tier.py ACW_NF_TIER=mobile; run_nf_perf.ps1 -Tag mobile_r1 -ExecCmds "foliage.MaxEndCullDistance 130000,r.ScreenPercentage 67,sg.ShadowQuality 1"
& $py tools/ntw/forest_world/perf_summary.py unreal/TreeLookdev/Saved/NorthForest/perf docs/evidence/ntw/forest_world/perf_uhd770.json
```
UE 內容（`unreal/TreeLookdev/Content`、Plugins）未進版控：本 worktree 由 `air-combat-world-cryptounreal` 複製 TreeLookdev 專案、`XinyiLandscapeBridge` 換成 NTW 隔離專案已編譯版本（含 NtwGateLibrary）。
未跑：自動化測試（新程式為離線建置腳本 + UE stage，驗收以收據與原生畫面為準）。

## 8. 尚未解決的主要限制

1. **範圍**：只有陽明山／大屯火山群 700 km²；北台灣其他山區（基隆、雪山山脈北段、新竹桃園丘陵）未做。基隆市 DEM 圖幅未下載；區外沒有遠景地形，從高空可看到地形邊界外只有海面／天空。
2. **效能**：UHD 770 上森林飛越 9–17 fps，未達可玩；低空密林（特別是柳杉造林）最重。下一步：行動專用 LOD 鏈（LOD0 = 現在的 LOD2）、近景密度與林冠殼分工再調、遠景冒出樹改用 impostor／HLOD、封裝後在獨顯 PC 與手機實測。**手機與獨顯 PC 皆 NOT TESTED**；ES3.1 行動渲染器也未跑。
3. **樹種分布是美術規則**，不是林型圖；柳杉造林地位置、相思樹範圍皆為合理化推論，需要官方林型資料（目前 403）校正。
4. **城鎮是方塊量體**（質心 + 面積），無輪廓、無屋頂細節、沒有道路網；部分落在樹木像元的建物與樹重疊。
5. 天氣 / 雲、季節色、近地 200 m 以下的灌木與地被、水面波浪、海岸消波塊等均未做。
6. 靜態鏡頭的效能數字只有少量影格；未做交錯重複量測（之前的 harness 經驗：單次量測漂移數 ms）。
7. 碰撞：樹與建物無碰撞；Landscape 有預設碰撞，未做碰撞 gate。
