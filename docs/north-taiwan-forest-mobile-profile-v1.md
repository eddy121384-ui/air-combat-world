# North Taiwan Forest — Mobile Forest Profile v1

日期：2026-10-21 · 分支 `feat/ntw-forest-mobile-profile-v1`（自 PR #52 `gate/ntw-forest-runtime` @ `8d0e14d`）· worktree `air-combat-world-ntwforest-mobile`
主機：i7-12700 + **Intel UHD 770 內顯**、16 GB RAM、UE 5.8 安裝版。沒有新增樹種、沒有重做 Golden、沒有擴張地圖。**Draft，勿 merge。**

> **重要區分**：本文所有「行動」數字都是 **PC 上的 ES3.1 行動渲染器預覽**（`-featureleveles31`，D3D12 ES3_1，UHD 770），是行動渲染路徑與內容成本的**相對**證據，**不是手機實測**。本機沒有 Android 平台支援、SDK／NDK、實機（見 PR #52 §5.1），iOS 需要 Mac。

## 0. 結論

| 項目 | 結果 |
|---|---|
| 地形異常（`t020`）| **確認＝工程缺陷並已修正**：cooked build 的 Landscape heightmap mip 串流在鏡頭切換後晚到，粗 mip 被 point 取樣成平台＋垂直面。地形資料、Landscape LOD、World Partition 都不是原因。修正後新封裝版同一畫面第一格即平滑（§1） |
| Mobile Forest Profile | **已實作在同一個世界裡**：渲染器選數字（`#if SHADING_PATH_MOBILE` + MPC 行動雙胞胎）、樹依 PR #50 消失順位帶 Detail Mode（手機 cook 剝掉 45 %）、手機 device profile、行動天空罩、樹皮遮蔽。PC 畫面不變（同視角逐像素差 0.05/255；SM5 GPU 282.5 → 286.6 ms，量測誤差內）（§2）|
| ES3.1 行動預覽 GPU（編輯器固定步長，PR #52 同協定）| 飛越 **168.2 → 67.2 ms（−60 %）**、p95 255 → 92 ms；draw calls 1970 → 750；GPU scene instances 中位 809 k → 479 k、最大 1.18 M → 681 k；三個定點 −58～−59 % |
| ES3.1 行動預覽（**封裝版**、即時 1080p、240 m/s）| GPU **59.9 ms（16.4 fps）**，p95 88 ms；同一封裝版 PC SM5（Medium 陰影）187.8 ms（5.2 fps）。300 m/s 62.7 ms。**兩種速度 0 次 WP 串流降級**、0 個 game thread > 50 ms 影格，`AddToWorld` p99 2.8–3.1 ms（PC 6.1 ms）|
| 記憶體 | 渲染側（GPU scene）樹 instance −42 %；CPU 側樹 instance 資料在 Win64 預覽中仍是 ~480 MB（Detail Mode 只「不註冊」）—— 手機 cook 剝除後按比例 **~265 MB**，再把 WP 載入範圍縮到 2.5 km（實測 346 MB × 0.55）**~190 MB**（§4.3）|
| 視覺 | 三個定點 + 7 個飛越點同視角 PC／行動對照（`same_view/`）：近景仍是立體濃密的 3D 林、中景連續林冠與樹種色、遠景山形與空氣透視都保留；行動版近景樹量是 PC 的 55 %，造林地樹幹比 PC 明顯 |
| 手機 30 fps | **無法判定**：沒有 Android／iOS 建置環境與實機。PC 內顯上的行動渲染器 16 fps 不能換算成手機 fps。需要的實機驗證見 §5 |

**最終問題：如何用手機負擔得起的成本，保留這片北台灣森林？**
不是讓手機畫更少的「同一片森林」，而是讓每一層距離由最便宜、又最能代表它的東西負責，且全部出自同一套資料：

- **近景（0–0.45 km 滿密度，到 1.5 km 漸稀）**：仍是真的 3D 紅楠／相思樹／柳杉，但只留 PR #50 消失順位最低的 **55 %** —— 也就是 PC 上本來就活得最遠的那些樹。樹冠略放大（+10 %），樹與樹之間的地面直接畫烘焙好的遊戲樹冠（不是林下土色），從空中看仍是濃密、立體的林冠。
- **中景（0.5–1.5 km）**：3D 樹在 1.5 km 前漸隱，交給 PR #49 的**烘焙樹冠貼圖 + 樹冠殼 WPO**（從 0.5 km 開始，PC 是 1.2 km），保留連續林冠、樹種色塊與稜線輪廓。
- **遠景（> 1.5 km）**：山形、地形皮膚、森林色塊與空氣透視 —— 與 PC 相同的 Landscape 材質，行動版只少了雙尺度樹冠法線（6 次取樣 → 3 次）。
- **陰影只給近景**（600 m、2 cascades、1024），遠處樹冠的明暗已經烘在貼圖裡。
- **同一個世界、同一批資產**：沒有第二套森林。差別只在 (1) 渲染器在編譯材質時選哪一組距離數字（`#if SHADING_PATH_MOBILE`），(2) 手機 device profile 的幾個 cvar，(3) 每個樹 HISM 依消失順位帶的 Detail Mode（手機 cook 直接剝掉 45 % 的樹）。

## 1. 第一階段：PR #52 `packaged_t020s.jpg` 的階梯狀山坡

### 1.1 結論：工程缺陷（cooked build 的 Landscape heightmap mip 串流），不是地形資料、不是 Landscape LOD、不是 World Partition。已修正。

| 檢查 | 結果 |
|---|---|
| 地形資料 | `build_region.py` 由 MOI 20 m DEM 以雙三次樣條內插到 10 m、uint16 量化 2 cm；資料本身沒有平台／階梯 |
| 是哪一格畫面 | `t020` = 第 3 個定點 `agl120_plantation`（柳杉造林地上空 140 m），不是飛越 |
| 編輯器 MRQ 同視角 | **平滑**（`terrain_diag/editor_mrq_plantation.jpg`）；關掉樹冠殼 WPO、把 Landscape LOD 細 8 倍、`r.Streaming.MipBias 5` 都一樣平滑 |
| PR #52 封裝版重跑同一段 | **重現**：第 3 定點約 11 個 dump 影格（~8 s）都是平台＋垂直面（`pr52_package_plantation_streaming.jpg`） |
| 同一封裝版 + `r.Streaming.FullyLoadUsedTextures 1` | **消失**（`pr52_package_plantation_fullyloadtextures.jpg`） |

原因：cooked build 的 Landscape heightmap 是串流貼圖（UE 5.8 用 `FLandscapeTextureStorageMipProvider` 在 cook 時另存 mip）。鏡頭切換到新定點後，heightmap 高解析 mip 還沒進來時，頂點著色器以 **point 取樣**讀到粗 mip，細網格上的頂點落在同一個粗 texel 上 → 平台；相鄰 texel 之間 → 垂直面（棕色是遮罩材質在垂直面上的拉伸）。編輯器的 heightmap 不走這條串流路徑，所以 MRQ 永遠看不到。dump 影格時只有 ~1.4 fps，讓「幾個影格內就會補上」的串流拖了 8 秒，這才被截到。

### 1.2 修正（`Config/DefaultDeviceProfiles.ini`，所有平台）
- `[GlobalDefaults DeviceProfile]` 的 `TEXTUREGROUP_Terrain_Heightmap` 加 `NumStreamedMips=0`：heightmap 不串流、整張常駐。這片 26.5 km Landscape 本來就是「不分區載入、永遠常駐」（`nf_build.py`），heightmap 含 mip ~20 MB，手機也負擔得起。
- 世界尺度的遮罩貼圖（`T_NF_Mask1/2`、`T_NF_Terrain`、`T_NF_Roofs`）設 `never_stream`：它們覆蓋整張地圖、永遠在畫面上，晚到時遠景會出現模糊色塊（同一張 `t020` 的棕色斑塊）。
- 驗證：新封裝版同一段 （`pkm_sm5_movie`，沒有任何串流覆寫）：切到第 3 定點後的**第一個** dump 影格就是平滑山坡（`terrain_diag/before_after_package_plantation.jpg`：上 = PR #52 封裝版、下 = 本版封裝版）。

沒有做大規模地形重建；地形資料、Landscape 設定、World Partition 都沒改。

## 2. 第二階段：Mobile Forest Profile 的做法

### 2.1 研究依據（UE 既有機制，不另寫森林系統）
| 需求 | UE 5.8 既有機制（本專案驗證過的引擎原始碼位置） |
|---|---|
| 依平台少畫一部分樹且**手機套件裡根本沒有** | 元件 `DetailMode` + device profile `r.DetailMode` → `PrimitiveComponent.cpp`：detail mode 高於平台設定的元件不建 render state；`r.CookOutUnusedDetailModeComponents=1` → `SceneComponent.cpp` cook 時直接剝掉 |
| 依渲染器選不同材質數字 | 材質 Custom HLSL 的 `SHADING_PATH_MOBILE`（ES3.1／Vulkan／Metal 行動路徑與 PC 的 ES3.1 預覽都會定義），同一個材質、同一個 MPC |
| 樹不送到 GPU 的距離 | `foliage.MaxEndCullDistance`（HISM end cull 上限）|
| 行動天空 | 行動渲染器不畫 SkyAtmosphere 全螢幕 pass（`SkyAtmosphereRendering.cpp`：「Mobile must use a skydome mesh with a sky material」）→ Is Sky 天空罩 |
| 行動陰影 | `r.Shadow.DistanceScale`、`r.Shadow.CSM.MaxMobileCascades`、`r.Shadow.MaxCSMResolution` |
| 有評估但**沒有採用** | `foliage.DensityScale`（引擎內建的隨機減量，但隨機丟棄會打亂 PR #50 的消失順位）；`foliage.MinLOD=1`（柳杉 LOD1 只剩 15 k 三角形中的 1.4 k，造林地露出整片樹幹，見 §3.2）；`wp.Runtime.OverrideRuntimeLoadingRange`（只存在於非 Shipping，只能拿來量測，見 §4.3） |

### 2.2 實作
| 部分 | 檔案 | 內容 |
|---|---|---|
| MPC 行動雙胞胎 | `nf_mobile_profile.py` (mpc) | `MPC_NF_Forest` 加 `NearFullM 450 m`、`ThinEndM 1.5 km`、`FadeWidthM 100 m`、`ThinGammaM 1.6`、`ShellStartM 0.5 km`、`ShellEndM 1.3 km`、`ClumpGainM 0.5`、`RankKeepM 0.55`、`CrownGainM 0.10`、`NearCanopyM 0.6`、`BarkAOM 0.45`。PC 數字（NearFull 1 km、ThinEnd 3.4 km、Shell 1.2–3 km）不變 |
| 樹材質 | `nf_mobile_profile.py` (trees) | 6 個 `M_NF_*` 樹材質的兩個 Custom 節點（像素保留遮罩、頂點 clump／消失塌縮）前面加 `#if SHADING_PATH_MOBILE` 改讀行動數字；順位重映射 `r' = r / RankKeepM`，讓留下的 55 % 仍分布在整段漸稀距離；近處樹冠 `+CrownGainM` |
| 樹的 Detail Mode | `nf_mobile_profile.py` (detail) | 17,351 個樹 HISM 依消失順位 band：0–0.55 → Low（2,121,823 棵）、0.55–0.78 → Medium（889,853）、0.78–1 → High（847,529）。PC（`r.DetailMode` 預設最高）全部照畫 |
| 樹皮遮蔽 | `nf_mobile_profile.py` (bark) | 行動渲染器沒有 SSAO；樹變稀後柳杉樹幹整片亮粉紅。3 個樹皮材質 base color 在行動路徑 × `BarkAOM 0.45` |
| Landscape | `nf_landscape_dl.py` `ACW_NF_DL_MOBILE=1` → `M_NF_LandscapeDL_R4` | 同一張圖、行動分支：樹冠殼／樹冠色改用 `ShellStartM/EndM`；近處林地 `max(shell, NearCanopyM)`（樹之間畫樹冠而不是林下土色）；樹冠法線單尺度（6 → 3 次取樣）；遮罩 never-stream |
| 天空罩 | `nf_mobile_sky.py` | `NF_SkyDome`（`SM_SkySphere` ~150 km）+ `M_NF_SkyDome`（unlit、opaque、Is Sky、`SkyAtmosphereViewLuminance` + 太陽盤）。兩種渲染器都用它當天空 —— 桌面渲染器一看到場景有 sky mesh 就停止自己的大氣天空，所以不能只在行動顯示；PC 畫面與加天空罩前**逐像素差 0.05/255**（`P1` vs `P3`） |
| 手機 device profile | `Config/DefaultDeviceProfiles.ini` `[Android]`／`[IOS]` | `r.DetailMode=0`、`r.CookOutUnusedDetailModeComponents=1`、`foliage.MaxEndCullDistance=165000`、`r.Shadow.DistanceScale=0.2`、`r.Shadow.CSM.MaxMobileCascades=2`、`r.Shadow.MaxCSMResolution=1024` |
| 預覽 = 手機同一份設定 | `tools/ntw/forest_world/mobile_cvars.ps1` | 讀 `[Android DeviceProfile]` 轉成 `-dpcvars=...` 給 PC 預覽（並檢查 iOS 區塊一致），預覽與手機設定不會分岔 |
| 封裝 | `DefaultEngine.ini` `+D3D12TargetedShaderFormats=PCD3D_ES31`、`tools/ntw/forest_world/package_win64.ps1` | Win64 封裝內同時有 SM5 與 ES3.1 shader，封裝版可直接跑 `-featureleveles31` |

量測：`run_nf_perf.ps1 -Frames 2150 -FixedFps 15 -ExtraArgs "-featureleveles31 $(mobile_cvars.ps1) -llm"` → `mobile_compare.py`；封裝版 `run_packaged.ps1 -ExtraArgs "-featureleveles31 $(mobile_cvars.ps1)"` → `pk_analyze.py`；同視角 `run_nf_mrq.ps1 -ExtraArgs @('-featureleveles31', ...)`（ES3.1 下 MRQ 可用）。

重建順序：`nf_mobile_profile.py`（mpc,trees 需 RHI；detail 用 `-nullrhi`；bark）→ `nf_landscape_dl.py`（`ACW_NF_LMAT_REV=4 ACW_NF_DL_MOBILE=1`）→ `nf_mobile_sky.py` → `nf_autoplay.py ACW_NF_AUTOPLAY=1` → `package_win64.ps1`。

## 3. 同視角比較（PC SM5 vs 行動 ES3.1 預覽）

### 3.1 定點（MRQ，1080p，同一序列影格；`same_view/`）
| 定點 | 對照圖 | 觀察 |
|---|---|---|
| `dl_layers_north`（432 m，遠眺大屯山系 8.6 km）| `dl_layers_north_pc_vs_mobile.jpg` | 山形、稜線、空氣透視、城鎮幾乎相同；行動版近處小山的林冠略深、樹的立體顆粒較少 |
| `agl200_qingtiangang`（擎天崗草原）| `agl200_qingtiangang_pc_vs_mobile.jpg` | 草原、闊葉林冠連續；行動版林冠顆粒稍平 |
| `agl120_plantation`（柳杉造林地 140 m）| `agl120_plantation_pc_vs_mobile.jpg` | 最難的畫面：PC 的造林地是密不透風的錐形樹冠；行動版仍連續，但樹幹較多可見、1.5 km 外改由貼圖林冠承接（交界在對面山谷可見）|
| 飛越 7 點（MRQ 逐格精確同視角，影格 450–3150）| `flight_f*_pc_vs_mobile.jpg`、`flight_sheet_pc_top_mobile_bottom.jpg` | 從飛行高度看，兩者差異主要在近景樹的顆粒感；森林連續性、樹種色塊、山形都保留 |
| 封裝版定點 | `packaged_pairs/t020s_pair.jpg` | 封裝版 PC（左）vs 封裝版 ES3.1 行動（右），同一定點 |

封裝版行動預覽影片：`mobile_packaged_every_frame.mp4`（每個 render 影格以 15 fps 播放，**不是即時速度**：`-dumpmovie` 時序列時鐘與 CSV 的牆鐘影格時間對不上，所以不做「即時節奏」版本；同理 PR #52 的 `runtime_packaged_realtime_pacing.mp4` 是以擷取時的牆鐘排的，不是序列時間）。

### 3.2 視覺迭代（不是調參搜尋，三次修正都有明確原因）
1. **天空全黑**（`agl200_qingtiangang_mobile_nosky_vs_skydome.jpg`）：行動渲染器不畫大氣天空 → 天空罩。黑天空同時讓即時天光擷取變黑，整片森林偏暗；修正後亮度回到 PC 水準。
2. **柳杉造林地一片樹幹**（`agl120_plantation_mobile_iter1_vs_final.jpg`）：`foliage.MinLOD=1` 把柳杉強制到 1.4 k 三角形的 LOD1 → 移除該 cvar；行動沒有 SSAO → 樹皮 × 0.45。
3. 其餘數字（55 %、1.5 km、0.5 km 殼起點）第一次就採用，沒有做參數搜尋。

## 4. 效能與記憶體

### 4.1 編輯器固定步長（PR #52 同一協定：`-game -benchmark -fps=15`、1080p、2150 影格、Medium 陰影；`ed_*`）
| 飛越（117 s，240 m/s）| PR #52 SM5 | 本版 SM5 | PR #52 ES3.1 | 本版 ES3.1 只有材質側 | **本版 ES3.1 完整行動 profile** |
|---|---:|---:|---:|---:|---:|
| GPU 中位（ms）| 282.5 | 286.6 | 168.2 | 151.7 | **67.2** |
| GPU p95（ms）| 383.9 | 390.2 | 255.4 | 235.3 | **92.1** |
| Basepass（ms）| 155.1 | 156.2 | 64.1 | 118.5* | **49.3** |
| draw calls | 2508 | 2510 | 1970 | 1976 | **750** |
| GPU scene instances 中位 / 最大 | 806 k / 1.18 M | 782 k / 1.18 M | 809 k / 1.18 M | 762 k / 1.18 M | **479 k / 681 k** |

| 定點 GPU（ms）| PR #52 ES3.1 | 本版 ES3.1 完整 | 變化 |
|---|---:|---:|---:|
| `dl_layers_north` | 106.6 | 44.6 | −58 % |
| `agl200_qingtiangang` | 154.3 | 65.2 | −58 % |
| `agl120_plantation` | 295.7 | 120.0 | −59 % |

\* 「只有材質側」的 Basepass 數字含有 PR #52 那次沒有的 CSM 陰影深度（12.6 ms，GPU 計時欄位分配不同）與天空罩；看 GPU 總時間即可。這一欄說明：光是行動距離數字（樹到 1.5 km 消失）只省 ~10 %；大頭來自 device profile 那一半 —— 不註冊 45 % 的樹、`MaxEndCullDistance` 讓 1.65 km 外的 HISM 根本不送、陰影只到 600 m。

### 4.2 封裝版即時（Win64 Development，1080p，`-llm`；`pkm_*`）
| 飛越 | PC SM5（Medium 陰影）`pkm_sm5_sq1` | ES3.1 行動 `pkm_es31` | ES3.1 行動 300 m/s `pkm_es31_300` | ES3.1 行動 + WP 2.5 km `pkm_es31_r25` |
|---|---:|---:|---:|---:|
| GPU 中位 / p95（ms）| 187.8 / 375.1 | **59.9 / 88.4** | 62.7 / 90.6 | 59.9 / 86.8 |
| fps 中位 | 5.2 | **16.4** | 15.7 | 16.3 |
| 穩定段 GPU（42 s 起）| 276.4 | 63.0 | 65.0 | 62.7 |
| game / render thread 中位（ms）| 5.3 / 192.3 | 4.1 / 61.2 | — | 3.9 / 61.2 |
| WP 串流降級（飛越中）| 0 | **0** | **0** | 0 |
| game thread > 50 ms 影格 | 0 | 0 | 0 | 0 |
| `AddToWorld` p99 / 最大（ms）| 6.1 / 9.1 | **2.8 / 6.4** | 3.1 | 2.6 / 4.3 |
| GPU scene instances 最大 | 1.18 M | 681 k | 681 k | **436 k** |
| 行程實體記憶體峰值 | 2.47 GB | 2.13 GB | 2.11 GB | 1.93 GB |

- PC SM5 187.8 ms vs PR #52 同設定 176 ms：+7 %，在 PR #50 記錄過的跨 session 漂移範圍內；同視角影像不變。
- LoadMap 0.84–1.70 s（PR #52 0.9 s），次間差異大，沒有看到穩定的回歸（heightmap 常駐多 ~20 MB 讀取）。
- 300 m/s 用 `slomo 1.25`（同 PR #52）。
- 行動預覽的 render thread ≈ GPU 時間是內顯同步等待，不是 CPU 瓶頸；game thread 4 ms。

### 4.3 記憶體
LLM 峰值（封裝版 Win64，MB）：

| 標籤 | PC SM5 | ES3.1 行動 | ES3.1 行動 + WP 2.5 km |
|---|---:|---:|---:|
| `Meshes/InstancedMesh`（樹的 instance 資料，CPU）| 478 | 482 | 346 |
| `Meshes/StaticMesh` | 153 | 86 | 56 |
| `Textures` | 146 | 139 | 137 |
| `RenderTargets` | 159 | 118 | 118 |

- Win64 預覽裡 `Meshes/InstancedMesh` 不會變小：Medium／High band 的 HISM 仍被載入，只是沒有 render state。**手機 cook 才會剝除**（`r.CookOutUnusedDetailModeComponents=1`，引擎在 cook 時對目標平台 device profile 判斷）。以 instance 數比例推估：載入範圍不變時 482 × 0.55 ≈ **265 MB**；載入範圍 2.5 km 時 346 × 0.55 ≈ **190 MB**（PC 480 MB）。這是推估，要在 Android cook 後以 `memreport`／LLM 實測確認。
- WP 載入範圍：行動版樹只畫到 1.65 km，但世界的 runtime grid 載入範圍仍是 PC 的 3.9 km。2.5 km 的效果是用 `wp.Runtime.OverrideRuntimeLoadingRange`（**只在非 Shipping 有效**）量的：GPU 不變、instances −36 %、instance 資料 −28 %、行程記憶體 −200 MB，串流仍 0 降級、`AddToWorld` p99 2.6 ms。正式做法是遊戲的 PlayerController 在行動平台把 World Partition streaming source 的 `LoadingRangeScale` 設成 ~0.65（一個屬性；本專案目前沒有遊戲碼，所以沒有做）。
- GPU scene instances 最大 −42 %（1.18 M → 681 k），2.5 km 時 −63 %（436 k）。

## 5. 要判定手機 30 fps 還缺什麼（實機驗證清單）
1. **建置環境**：Epic Launcher 加裝 Android 平台支援；Android Studio + SDK + **NDK r27c** + JDK 17；`Android_ASTC` cook。確認 (a) cook log 的 detail-mode 剝除（Medium／High tree HISM 不在套件裡），(b) 套件大小，(c) 材質在 Vulkan／GLES 編譯。iOS：Mac + Xcode + 開發者帳號。
2. **裝置**：至少一台中階 Android（Adreno 7xx／Mali-G7xx 級、6–8 GB RAM）、一台入門（4 GB）、一台 iPhone（A15 級）。
3. **量什麼**（同一條 240／300 m/s 航線 + 3 個定點，自動播放已在地圖裡）：
   - 10 分鐘持續 fps 與降頻（發熱後）—— 30 fps 的判準是**降頻後**的 p95 ≤ 33 ms，不是冷機中位數；
   - GPU 計時與 TBDR 計數器（Snapdragon Profiler／Mali Streamline／Xcode GPU）：遮罩葉片的 overdraw、帶寬；
   - 記憶體：LLM + 系統 PSS，目標 4 GB 機 < ~1.3 GB；
   - 串流：手機 CPU 上的 `AddToWorld`／AsyncLoading 尖峰（PC 2.8 ms，手機 CPU 預期 3–4 倍）；
   - PSO／shader 首次編譯卡頓（要做 PSO cache）。
4. **若中階機達不到 30 fps，依序可用的槓桿**（都在本版機制內，不用新系統）：解析度 70–80 %（`r.MobileContentScaleFactor`／screen percentage）→ 4x MSAA 換掉 TAA（葉片 alpha-to-coverage）→ `ThinEndM` 1.5 → 1.2 km → 樹 band 再細一級（把 rank 0.30–0.55 改 Medium、低階機 `r.DetailMode=0` 只留 30 %，`RankKeepM` 0.30）→ 陰影只留 1 cascade。
5. **WP 載入範圍**：在遊戲碼加行動版 streaming source `LoadingRangeScale`（§4.3）。

## 6. 限制
- 所有效能數字來自一台 UHD 770 內顯；ES3.1 預覽是在 PC GPU 上跑行動渲染路徑：沒有 TBDR、沒有行動 GPU 的頻寬／發熱限制、沒有 ASTC。只能當相對比較。
- Detail Mode 剝除與 `r.CookOutUnusedDetailModeComponents` 的**記憶體**效果要在 Android／iOS cook 才會實際發生；本機 Win64 封裝只能量到「不註冊」帶來的 GPU scene 與繪製減量，CPU 端的 instance 資料仍在（§4.3 以比例推估）。
- 單次量測；Development 組態。
- 行動版近景是 PC 的 55 % 樹量：從空中仍連續，但比 PC 疏，柳杉造林地最明顯（樹幹較多可見）；更低的貼地飛行沒有另外檢查。
- 鏡頭瞬移到 10 km 外的新定點後，前 ~3 個 dump 影格（`agl200_qingtiangang`）草原上有深色方塊，PC 與行動、修正前後都有；是 WP 格子在瞬移後才開始載入的過渡（連續飛行中沒有出現），不是地形問題，本輪沒有處理。
- PC 的 `r.DetailMode` 被 `sg.EffectsQuality` 連動（Low 0／Medium、High 1／Epic 3），會讓 PC 在中低特效時少掉 Medium／High 樹 band；`[Windows DeviceProfile] r.DetailMode=3` 把它固定住。驗證：同一封裝版 `sg.EffectsQuality 1` 與 Epic 在同一飛越時段的 instances 完全相同（最大 995,887、中位 203,844）。
- 重現第一階段時，PR #52 的封裝版被重跑兩次（`diag_t020_a/b`），輸出寫在 PR #52 worktree 的未追蹤 `Saved/NorthForest/gate/runs/`；PR #52 的內容與分支沒有改動。
- 舊工具 `nf_tier.py` 的 "mobile" 預設（PR #46）已被本版取代（它只改共用 MPC 的預設值，等於把 PC 一起改掉）。
