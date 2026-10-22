# Skyfront Homeland — 行動裝置遠景渲染研究 v1（森林 Impostor 原型）

日期：2026-10-22 · 分支 `research/mobile-far-lod-v1`（自 PR #57 `feat/graphics-settings-v1` @ `4956584`）· worktree `air-combat-world-farlod`
**Draft，勿 merge。** 沒有重做 Golden、沒有擴張地圖、沒有重建森林（3D 樹、地形、材質都是 PR #57 原樣），沒有改 Android APK。
主機：Intel UHD 770 內顯。標記：**[PC]** = 這台主機實測（ES3.1 行動渲染器預覽或 SM5）；**[code]** = 引擎原始碼 / 設定；
**[文獻]** = 業界公開資料；**[推論]** = 我們自己的工程推論；**[S11]** = 等 Galaxy Tab S11 實機。**不宣稱任何 S11 幀率。**

## 0. 結論（先看這裡）

| 問題 | 答案 |
|---|---|
| 有業界依據的方案？ | **Octahedral tree impostor**：《鳴潮》行動版的中遠景樹就是 impostor，UE 5.8 也隨附 Brucks 的 ImpostorBaker [文獻]。原型用同一套方法，自己寫烘焙與 shader，以便控制交接。 |
| 比 PR #57 好看嗎？ | **2–5 km 明顯較好 [PC]**：稜線與城鎮上方的山坡從平面貼圖變成一顆顆有明暗的樹冠，天際線有樹冠鋸齒。**5–7 km 有一點缺點**：最銳利的山脊明暗略被樹冠紋理柔化。與 Ultra 相比，中遠景樹冠接近，但少了 Ultra 1.5 km 陰影帶來的近景對比（陰影是另一個設定，不屬於本方案）。 |
| 成本有競爭力嗎？ | 候選配置（High 預設，但 3D 樹只到 2.2 km，2.2–7 km 交給 impostor）在同一 session、交錯兩個順序量測 [PC]：森林三個視角 **比 PR #57 High 便宜 5–14 %**，**比 Ultra 便宜 46–52 %**；盆地城市邊緣視角貴 6 %。Draw call 多 128–320 個（+6～+35 %，第一版 HISM 時是 +4,000）。300 m/s 飛行：GPU 中位 **−23 %**、p95 **−17 %**，**0 個遠景跳變**。 |
| 高速移動、LOD 交接？ | 每棵樹在自己原本的消失距離被同一棵樹的 impostor 用**互補 dither** 接手，沒有距離環；360 格 300 m/s 飛行的遠景帶 **0 個 pop**，閃爍（逐格變化中位）只多 3 %。 |
| 值得進入大規模整合嗎？ | **值得，但先做三件事**（§7）：S11 實機量測（行動 GPU 的 masked／instance 成本與 PC 不同）、impostor 用 World Partition 分近遠兩層串流以控制記憶體、城市遠景另做 HLOD。 |
| 淘汰什麼？ | HISM 版 impostor（draw call ×3、多出 velocity／occlusion 成本）、球形卡片、到 10 km 的全密度 impostor（蓋掉山形）、把 3D 樹延到 3.4 km 的 Ultra 做法在行動版的地位（同畫面貴一倍）。 |

**所有效能數字都是 Intel UHD 770 + ES3.1 行動渲染器預覽，只代表相對成本；沒有任何 S11 幀率宣稱。**

## 2. 原型做了什麼（皆在既有 PR #57 世界上，不改 3D 樹／地形／材質）

1. **烘焙** `adapters/unreal/ntwforest/fi_bake.py`：4 種樹形 × 10 個色調變體，用遊戲本身的網格（**LOD3**＝1.5 km 外實際畫出的團簇卡片）與世界材質，正交 SceneCapture 從半八面體 16×16 個方向拍 BaseColor／法線／深度（256 px 拍、4× 超取樣降到 64 px）。4,608 張，48–71 s。第一版用 LOD0 拍時，相思與柳杉的細葉卡在 128 px 下消失（覆蓋率 8 %），改 LOD3 才正確（`bake/fi_sheet.png`）。
2. **打包** `tools/ntw/forest_world/fi_pack.py`：每個變體一張 1024² atlas（BC：sRGB 色＋覆蓋率；ND：物件空間法線＋深度），透明處顏色擴張避免 mip 黑邊。匯入成兩個 **Texture2DArray**（10 層），一個材質、一個元件畫所有樹種（《鳴潮》以 Texture Array 合批的做法）。
3. **材質** `M_FI_Impostor`（`fi_build.py`）：頂點階段在半八面體上選最近 3 個視角＋重心權重、卡片朝向相機、卡片→各視角 UV 投影；像素階段 3 視角混合、法線轉世界。四個關鍵規則：
   - **交接**：讀與 3D 樹相同的 MPC 曲線與消失順位 r，像素 dither 與 3D 樹**完全互補**，所以每棵樹在 PR #57 原本讓它消失的地方被換掉（PC 曲線／行動版 twin 曲線都對應）。
   - **遠處稀疏化**（我們的推論）：超過 3 km 只保留 (3 km/D)² 的樹、存活者放大 min(D/3 km, 1.6)；5.5→7 km 整層 dither 淡出，7 km 外交回 PR #49 的地形皮膚／巨觀林色（「遠景看山形」）。
   - **山形保留**：每棵樹存一個 30 m 平滑的地形法線（`fi_terrain_normal.py`，DEM 方向檢查中位誤差 1 m），impostor 法線隨距離往地形法線彎（2→6 km，最多 0.6）。
   - **卡片貼合輪廓**：卡片依視角仰角用樹的水平半徑 × 投影高度，而不是包圍球（柳杉卡片窄 57 %）。這是 ImpostorBaker「per-frame cutout mesh」的同一個想法。
4. **實例** `fi_build.py actors`：A/B 區域（4 個鏡頭 + 飛行段的視錐內 7.5 km）254 個 1 km tile 的 **2,168,177 棵樹**，同一份樹位置／旋轉／縮放／消失順位，2 km 一格共 79 個 actor、395 個 **ISM** 元件（依稀疏化 hash 分 5 段，各自剔除距離）。不做空間載入，以 tag `FarImpostor` 在記憶體中開關。
5. **量測工具**：`FreeFlightFarLodTest.cpp`（`-fffarlodtest`／`-fffarlodfly`），`tools/skyfront/run_farlod_ab.ps1`、`farlod_report.py`、`farlod_profile.py`（ProfileGPU 分 pass）、`farlod_fly.py`（逐格時間檢查）。

## 3. 同位置／同相機／同光照 A/B（ES3.1 行動預覽，2560×1600，UHD 770）

同一個 session 內即時切換、**正反兩個順序**各量一次（每格 4 s，等串流與 shader 編完）。Impostor 層用記憶體開關，地圖完全相同。

| 配置 | 說明 |
|---|---|
| `high`／`ultra` | PR #57 原樣（對照） |
| `high_fi`／`ultra_fi` | 同上 ＋ impostor 接在該預設 3D 樹消失之後 |
| **`high_t22_fi`（候選）** | High，但 3D 樹距離降一級（2.2 km）＋ impostor 2.2–7 km |

**GPU 中位 ms（最終版 `ab/stats.json`，兩次平均）**

| 視角 | High | High+FI | **候選** | Ultra | 候選 vs High | 候選 vs Ultra | Draw call High → 候選 |
|---|---:|---:|---:|---:|---:|---:|---:|
| forest_layers（8.6 km 森林層次） | 143.8 | 154.3 | **127.5** | 240.2 | **−11 %** | **−47 %** | 2,052 → 2,180 |
| mid_ridge（7.4 km 中央稜線） | 300.6 | 314.9 | **285.8** | 595.2 | **−5 %** | **−52 %** | 1,412 → 1,564 |
| basin_edge（盆地城市邊緣） | 77.4 | 83.7 | 81.8 | 102.7 | +6 % | −20 % | 926 → 1,246 |
| far_range（逆光遠山 10.7 km） | 138.9 | 156.1 | **120.2** | 220.9 | **−13 %** | **−46 %** | 1,792 → 2,042 |

- 最終 session 的**絕對值**比前幾輪高（mid_ridge High 300 vs 197 ms，內容未變）：這台機器上有一個從 10/16 起執行、已累積約 134 CPU 小時的孤兒 PowerShell 背景程序（PID 13716，別的 Claude session 留下的），內顯和 CPU 共用功耗。因此只引用**同 session 交錯**的相對差；前三輪（`stats_iter*.json`）的相對差一致：候選 vs High −6～−9 %（森林）、+12 %（盆地）；vs Ultra −41～−53 %。
- 只加 impostor 不降 3D 距離（`high_fi`）：+6～+17 ms。impostor 層本身不是免費的；省下來的是 3D 樹 2.2–3.0 km 那段的頂點／實例成本。

**ProfileGPU 分 pass（`ab/profile_gpu.json`）與迭代：**

| 版本 | impostor 層成本（forest_layers） | 多出的 draw call | 原因 / 修正 |
|---|---:|---:|---|
| v1 HISM | +24.4 ms | +4,045 | HISM 每元件約 13 個 batch ＋ 每元件約 8 個 occlusion query；WPO 讓所有 impostor 進 **velocity pass**（+8.6 ms） |
| v2 **ISM** + `world_position_offset_writes_velocity=False` | **+12.7 ms** | **+311** | GPU scene 剔除，每元件每 pass 一個 draw；velocity／occlusion 成本消失 |
| v3 地形法線 | +13.3 | +313 | 畫面修正，成本不變 |
| v5 貼合卡片、7 km 結束 | +10.5 | +280 | masked 面積少；柳杉人工林不再爆 |

剩下的 impostor 成本主要在 BasePass（masked 像素）、GPU instance culling（`BuildRenderingCommandsDeferred` ＋ shadow view 的剔除各 1.5–3.7 ms，因為原型區有 217 萬實例常駐）。

**畫面證據**（`docs/evidence/skyfront/far_lod_research_v1/ab/`）：
- `triptych_<view>.jpg`：上 PR #57 Ultra、中 PR #57 High、下候選，同一格畫面。
- `crop_<view>_high_vs_high_t22_fi.jpg`、`crop_<view>_ultra_vs_high_t22_fi.jpg`：遠景帶原生像素裁切。
- `diff_<view>_high_vs_high_t22_fi.png`：|差| ×4，看出改變全部落在 2 km 外的林區。
- `ab_<view>.jpg`：所有配置對。

**亮度校正**：impostor 是用基色＋法線重新打光，第一版比同位置 3D 樹亮 13–17 %、偏黃。用 forest_layers 2.2–3.4 km 帶（Ultra 3D 樹 vs 同一批樹的 impostor）量出一個**全域**線性 tint（0.66, 0.69, 0.86），之後各視角 impostor 與被取代者的亮度差在 −12 %～+8 %（盆地視角 −22 %，因為 impostor 蓋住的是亮的開闊地而不是樹）。沒有逐棵、逐區調整。

## 4. 高速飛行（300 m/s，逐格鎖定同一路徑，1280×800，360 格）

`flight/fly_300mps_high_vs_high_t22_fi.mp4`（左 High、右候選），`fly_temporal_*.json`，`skyflfly_*.log.txt`。

| | High | 候選（球形卡片 v4） | **候選（貼合卡片 v5）** |
|---|---:|---:|---:|
| GPU 中位 | 119.7 | 110.1 | **92.4 (−23 %)** |
| GPU p95 | 165.7 | 224.1 | **137.9 (−17 %)** |
| GPU 最大 | 208.4 | 341.8 | **145.6** |
| 遠景帶 pop（> 3× 局部中位） | 0 | 0 | **0** |
| 遠景帶逐格變化中位（閃爍） | 5.65 | 5.84 | 5.83（+3 %） |

- v4 的 p95 尖峰來自柳杉人工林（6 m 間距）在掠射角下，大量幾乎全透明的球形卡片疊在一起（`plantation_spike_frame312_sphere_cards.jpg`）。改成貼合卡片後尖峰消失，這也是本輪最重要的成本修正。
- Impostor 轉向：3 視角混合，視角間 11°；飛行中沒有可量到的視角切換跳變。卡片朝向相機但陰影不投射（行動版陰影最遠 1.5 km，impostor 從 2.2 km 起，所以《鳴潮》提到的「Billboard 陰影跟著相機轉」問題在這個距離不出現）。

## 5. 記憶體

| 項目 | 數值 | 標記 |
|---|---|---|
| Impostor 貼圖：2 個 Texture2DArray，1024² × 10 層 | PC（BC7）約 2 × 14 MB；行動 ASTC 6×6 約 2 × 6 MB | [推論，依格式計算] |
| 原型區實例：2,168,177 棵 × (轉換 64 B + 3 floats) | CPU 約 165 MB，GPU scene 約同量級 | [推論] |
| 對照：PR #57 全部 3D 樹帶 | 約 482 MB 實例資料（PR #55 估計） | [code] |
| 候選把 3D 樹 WP 載入範圍 3.2 → 2.8 km | 載入的 3D 樹面積 −23 % | [code] |

原型為了 A/B 方便讓 impostor 常駐，**不是行動版的形態**。行動版建議：World Partition 兩層 impostor grid：近層 0–4 km 存全部樹（約 27 萬棵），遠層 4–7 km 只存稀疏化後會留下的 45 %（約 26 萬棵），合計約 53 萬實例、約 40 MB CPU [推論]。Editor `-game` 的程序記憶體讀數受編輯器影響，不作證據。

## 6. 哪些值得擴大、哪些淘汰

| 方案 | 判定 | 理由 |
|---|---|---|
| Octahedral impostor 2.2–7 km，接在 PR #57 的逐棵消失之後 | **擴大** | 森林視角比 High 便宜、比 Ultra 便宜一半；2–5 km 樹冠立體感明顯提升；0 pop |
| 互補 dither 交接（同一棵樹、同一 MPC 曲線） | **擴大** | 無距離環、無額外 LOD 狀態；所有預設自動對應 |
| ISM + 關 WPO velocity | **擴大** | 相對 HISM 成本減半、draw call 從 +4,000 變 +300 |
| 貼合輪廓的卡片 | **擴大** | 柳杉人工林 p95 −38 %；下一步可換成 ImpostorBaker 的多邊形 cutout |
| 地形法線彎曲 | 保留，效果小 | 稍微回復遠山明暗；真正保住山形的是 7 km 收尾 |
| HISM 版 impostor | 淘汰 | draw call ×3、velocity／occlusion 開銷 |
| 包圍球卡片 | 淘汰 | 人工林掠射角 p95 尖峰 |
| Impostor 一直畫到 10 km、全密度 | 淘汰 | 蓋掉 PR #49 的山形與地形皮膚，遠山變平、偏藍 |
| 只加 impostor 但不降 3D 樹距離 | 不建議當預設 | 畫面加分但每個視角多 6–17 ms |
| 《鳴潮》近景 Billboard 樹（取代插片樹） | 未做 | 需重做樹資產（本輪範圍外）；適合下一輪處理 0–2 km 的頂點成本 |
| 城市遠景 HLOD（Merged／Simplified） | 未做原型 | 盆地視角 543 個城鎮元件；Epic 的 HLOD／Proxy LOD 是有依據的方向，留給下一輪 |

## 7. 限制與 S11 待驗證

1. **[S11]** 沒有實機數字。Mali-G925 的 fragment pre-pass 對 `discard`（masked）draw 是 late-Z，可能比 PC 預覽更貴（Arm 文件）；impostor 的 3 視角 6 次取樣、600 指令的頂點 shader 在行動 GPU 上的比例也不同。必須在 S11 量：候選 vs Balanced／High 的 GPU ms、溫度、記憶體。
2. **[S11]** 行動版 Vulkan 是否走 GPU scene instance culling（ISM 的優勢前提）需要在裝置上確認；若否，ISM 會把所有實例送進頂點階段。
3. 頂點 shader 偏重（SM5 統計 686 指令）：每個 impostor 只有 4 個頂點，但實例很多。可再省：把 3 個視角的基底改成查表、或在遠處改單視角。
4. 5–7 km 的山脊明暗略被柔化；7 km 以外仍是 PR #49 的地形皮膚，天際線沒有樹冠鋸齒（10 km 版本有，但蓋掉山形）。
5. far_range 的農田上的散生樹（真實資料）在 4–7 km 變成深色小點，有點雜訊感；可用「林分密度 < 門檻的格子不出遠層 impostor」處理。
6. 原型區只有 4 個鏡頭＋一段飛行的視錐；整張地圖還沒建。Impostor 不投射陰影、不參與碰撞。
7. 背景負載：見 §3（PID 13716 孤兒程序）；相對數字為同 session 交錯，絕對值不可跨 session 比較。

## 8. 下一階段建議（若進入整合）

1. S11 量測包：一個帶 `-fffarlodtest` 相同邏輯的 Android 開發 APK（**不動現有 0.2.0 APK**），量候選 vs Balanced／High。
2. World Partition 兩層 impostor grid（近層全部、遠層稀疏），取代常駐。
3. 圖形設定新增一列「遠景森林」：Off／On；High／Ultra 改用「3D 2.2 km + impostor」，Balanced 評估「3D 1.5 km + impostor」。
4. 城市：盆地城鎮 HLOD（Merged Mesh + 材質烘焙）原型，同一套 A/B 工具。
5. 近景：評估《鳴潮》式 Billboard 樹冠（30–40 % 面數）取代 0–2 km 的插片 LOD。

## 9. 重現

```powershell
# worktree air-combat-world-farlod; ACW_NF_RUN 指向 forest_world/v1 資料（本輪讀 air-combat-world-gfx 的那份，唯讀）
$env:ACW_NF_RUN='...\air-combat-world-gfx\data\generated\ntw\forest_world\v1'
$env:ACW_FI_REV='3'; tools\ntw\forest_world\run_nf.ps1 -Script fi_bake.py -Name fi_bake3 -Expect fi_bake.report.json
python tools/ntw/forest_world/fi_pack.py unreal/TreeLookdev/Saved/NorthForest/fi_bake/3 unreal/TreeLookdev/Saved/NorthForest/fi_pack/3 64
python tools/ntw/forest_world/fi_terrain_normal.py $env:ACW_NF_RUN unreal/TreeLookdev/Saved/NorthForest/fi_pack/3
$env:ACW_FI_PACK_REV='3'; $env:ACW_FI_PARTS='tex,mesh,mat,actors'; tools\ntw\forest_world\run_nf.ps1 -Script fi_build.py -Name fi_build -Expect fi_build.report.json
# Build.bat TreeLookdevEditor Win64 Development（FreeFlightFarLodTest.cpp）
tools\skyfront\run_farlod_ab.ps1 -Tag ab5 -Views 0,1,2,3 -Profile
python tools/skyfront/farlod_report.py unreal/TreeLookdev/Saved/Skyfront/ab5 <out>
python tools/skyfront/farlod_profile.py unreal/TreeLookdev/Saved/Skyfront/ab5 high high_fi 6
tools\skyfront\run_farlod_ab.ps1 -Tag fly2 -Fly -FlyCfgs 0,2 -ResX 1280 -ResY 800
python tools/skyfront/farlod_fly.py unreal/TreeLookdev/Saved/Skyfront/fly2 <out> high high_t22_fi
```
UE 內容（`/Game/FarLOD`、地圖中的 `FI_Imp_*` actor）與 PR #57 的其他內容一樣不進 git（`unreal/TreeLookdev/Content/` 被忽略），由上面的腳本重建。

## 1. 文獻：業界已公開證實的做法 vs 我們的推論

### 1a. 已公開證實 [文獻]

| 主題 | 來源 | 內容（摘要） |
|---|---|---|
| 《鳴潮》樹木分層 | Unreal Engine 官方開發者訪談（Kuro）；UFSH2023 王宏波〈《鳴潮》基於虛幻引擎 4 的多平台效果和性能優化實踐〉 | PC／主機：近景 3D 模型樹、中景 Billboard 樹、遠景 Impostor 樹。**行動版：近景 Billboard、中景與遠景都用 Impostor。** |
| 《鳴潮》Billboard 樹 | 同上（CSDN 對 UFSH2023 的整理） | 把插片樹的每個葉團換成朝向相機的面片，只要約 30–40 % 的面片數就能還原插片樹外觀；缺點是陰影跟相機轉，解法是陰影 pass 讓面片朝向光源。 |
| 《鳴潮》Impostor 樹 | 同上 | 一圈相機離線拍攝物件、記錄材質資訊，執行時取最接近當前視角的拍攝結果合成；擴充 UE 的 Texture Array 成「動態 Texture Array」並配合動態載入／卸載，讓遠處樹可以批次繪製。 |
| Octahedral impostor | Ryan Brucks（Epic）的 octahedral impostor 方法；UE 5.8 隨引擎附帶的 `Plugins/Experimental/ImpostorBaker`（本機已確認存在） | 在（半）八面體上取 N×N 個視角烘焙成一張 atlas，執行時用最接近的 3 個視角混合；據公開資料用於 Fortnite 的樹木 LOD。 |
| World Partition HLOD | Epic 官方文件〈World Partition – HLOD〉 | Layer 類型：**Instancing**（換成最低 LOD 的 ISM，文件明說適合「impostor 類的樹與植被」）、Merged Mesh、Simplified Mesh（合併＋減面＋材質烘焙）、Approximated Mesh。Layer 可串成多級。 |
| HLOD／Proxy 對行動版的意義 | Epic tech blog（UE 4.20 Proxy LOD tool；2019 mobile VR 環境） | 合併成 proxy 網格以減少 draw call 與材質數；Proxy LOD 工具被描述為 Fortnite 行動版上市所必需。 |
| Mali 的 masked／discard 成本 | Arm〈Immortalis-G925: the fragment prepass〉、〈Hidden surface removal in Mali GPUs〉 | Tab S11 的 GPU（Immortalis-G925）有 fragment pre-pass；使用 `discard` 的 draw 是 late-Z：pre-pass 要先跑部分 fragment shader，主 pass 再跑一次，可能**增加**總工作量。建議：discard 前的計算要簡單、vertex 位置計算要簡單、不透明物件不需要再排序。 |
| 行動 GPU 與 alpha test | Arm／Unity 行動端最佳實務 | alpha test（cutout）會關掉 GPU 的一些隱藏面剔除優化；過度繪製要用 Arm Mobile Studio 在實機量。 |

### 1b. 我們的工程推論 [推論]（不是業界公開數據，需實驗驗證）

1. **森林的 1.5–8 km 是 impostor 的主場**：PR #50／#57 已量到 3D 樹在遠處是「頂點／實例送出受限」（LOD3 每棵 ~600–850 頂點），而 impostor 每棵 4 頂點；這是本輪原型要證明的。
2. **交接不做距離環**：PR #46 起每棵 3D 樹已有自己的消失距離 T(r) 與逐像素 dither；impostor 用「同一棵樹、互補的 dither」接手，理論上不會出現 LOD 環。
3. **遠處固定螢幕密度的稀疏化**：超過 S 後只保留 (S/D)² 的樹並放大 D/S 倍，螢幕上每個 impostor 大小與密度不變，實例數只隨 log(距離) 成長。
4. **城市遠景用 HLOD（Merged／Simplified）而不是 impostor**：建築是規則量體，合併網格＋烘焙材質對 draw call 的效果最直接；本輪只做森林原型，城市只記錄 draw call 現況。

## 參考資料

- Unreal Engine developer interview, *Exploring the post-apocalyptic charm of ASG open worlds in Wuthering Waves*: https://www.unrealengine.com/developer-interviews/exploring-the-post-apocalyptic-charm-of-asg-open-worlds-in-wuthering-waves
- UFSH2023〈《鳴潮》基於虛幻引擎4的多平台效果和性能優化實踐〉王宏波（庫洛）：https://www.bilibili.com/video/BV1BK411v7FY/ ；文字整理：https://blog.csdn.net/ruanjian_gc/article/details/139875635
- 第三方逆向分析（推測成分高，只作參考）：https://zhuanlan.zhihu.com/p/1891431033540416679
- Epic, *World Partition – Hierarchical Level of Detail*: https://dev.epicgames.com/documentation/en-us/unreal-engine/world-partition---hierarchical-level-of-detail-in-unreal-engine
- Epic tech blog, *An in-depth look at Unreal Engine 4.20's Proxy LOD tool*: https://www.unrealengine.com/tech-blog/an-in-depth-look-at-unreal-engine-4-20-s-proxy-lod-tool
- Epic tech blog, *Pushing the boundaries of mobile VR with stunning environments*: https://www.unrealengine.com/tech-blog/pushing-the-boundaries-of-mobile-vr-with-stunning-environments
- 80.lv, *Impostor Baker for UE4*（Brucks octahedral impostors）: https://80.lv/articles/impostor-baker-for-ue4/
- Arm, *Immortalis-G925: the fragment prepass*: https://developer.arm.com/community/arm-community-blogs/b/mobile-graphics-and-gaming-blog/posts/immortalis-g925-the-fragment-prepass
- Arm, *Hidden surface removal methods in Mali GPUs*: https://developer.arm.com/community/arm-community-blogs/b/mobile-graphics-and-gaming-blog/posts/hidden-surface-graphics-removal-methods-in-mali-gpus
