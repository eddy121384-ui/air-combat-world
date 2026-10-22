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

**v2 更新（§10、§11）**：impostor 從「A/B 區域常駐 217 萬棵」改為「全圖 386 萬棵、World Partition 距離串流」，常駐 impostor 實例資料最壞 97 MB（最密林區）、一般 10–65 MB、關閉 ≤ 1.4 MB；5–7 km 山形與農田黑點兩個問題以全域規則修正；最終 A/B v6 比 PR #57 High 便宜 10–16 %（森林）、比 Ultra 便宜 47–53 %，300 m/s 0 個遠景 pop。另做了可與 0.2.0 並存的 S11 測試 APK（含平板上自動 A/B 的 BENCH 按鈕）。

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

## 10. v2：手機整合準備（World Partition 距離串流、農田黑點、5–7 km 山形）

日期：2026-10-22（同一分支，PR #58 延續）。基準保留：PR #57 High／Ultra 與 PR #58 v5 都在同一個 A/B 工具裡（v5 = v5 參數跑在 v6 資料上；它原本 6.2–7 km 的部分以 PR #58 提交的 `ab5` 畫面為準）。

### 10a. 串流設計（全部是 UE 5.8 既有機制）

| 項目 | 做法 |
|---|---|
| 範圍 | 整張地圖 573 個 1 km tile、3,859,205 棵樹全部有 impostor，但**沒有常駐**：依距離串流 |
| Grid | 每個「遠處稀疏化 hash 段」一個 2D runtime grid：`FI_B0`／`FI_B1`（h < 0.40，2 km cell，6.8 km）、`FI_B2`（5.6 km）、`FI_B3`（4.6 km），`FI_ISO`（稀疏林／林緣／田間樹，3.6 km）。載入距離 = 該段最後可見距離 + 0.15 km 剔除餘量 + 0.5 km 串流預留（300 m/s 約 1.7 s） |
| Cell 對齊 | Grid 原點對齊樹 tile 格（54000, 0 cm），且 `bIs2D = true` |
| Actor | `AFarImpostorCell`（新增，一個 tile × 一個 hash 段，一個 ISM 元件）。**串流邊界 = tile 本身**（`GetStreamingBounds` override）；畫面剔除仍用真實邊界 |
| 開關 | 關閉 = 用 `wp.Runtime.OverrideRuntimeLoadingRange -grid=<名稱>` 把各 grid 載入距離設成 1 cm（只留攝影機所在的格子，約 1 MB）＋隱藏 |
| 參數 | `MPC_FI_Impostor`（v5／v6 同一份資料、執行中切換） |

離線尺寸工具 `tools/ntw/forest_world/fi_stream_budget.py` 用真實樹位置估算每種 grid 佈局的常駐量，實測與模型誤差 < 10 %。

### 10b. 過程中找到並修掉的問題（避免後續整合重踩）

| 問題 | 現象 | 修正 |
|---|---|---|
| 1 km tile 的 actor 邊界（含樹冠）> 1 km | World Partition 依 `ceil(log2(邊界/cell))` 把 actor 升到 2 km（再加上 3D grid 的高度）→ 提早約 0.6 km 載入，常駐量 ×2 | `AFarImpostorCell` 串流邊界 = tile；grid 改 2D、原點對齊 |
| Clone 出來的 partition 預設是 3D（`bIs2D=false`） | 地形起伏 1 km 也算進 cell 大小與距離 | `SetRuntimePartitionShape(…, bIs2D=true)` |
| 編輯器裡刪不掉已串流的舊 actor | v2a 的 328 個 actor 沒被刪，`ab7` 畫了兩層（**該輪數據作廢**） | 先用 descriptor `load_actors` 再刪；收據記錄刪除數 |
| MPC 重建產生新 GUID | 只重建 MPC 不重建材質 → 材質讀到 0 → impostor 全部消失（`ab9` **作廢**） | MPC 參數原地更新 |
| HUD／`r.ProfileGPU` 等 | 已在 v1 記錄 | — |

### 10c. 記憶體預算（實測常駐，CPU 實例資料 = 64 B 轉換 + 4 B × 3 custom float）

| 視角（最終 grid，`v2/stats_ab13.json` / `skyfl_ab13.log.txt`） | impostor 常駐 actor | impostor 常駐實例 | impostor 資料 | 3D 樹常駐（PR #57，所有設定相同） |
|---|---:|---:|---:|---:|
| forest_layers | 544 | 870 k | **63 MB** | 661 k / 43 MB |
| mid_ridge（最密的林區，最壞情況） | 632 | 1,342 k | **97 MB** | 814 k / 53 MB |
| basin_edge | 196 | 145 k | **11 MB** | 36 k / 2 MB |
| far_range | 338 | 533 k | **39 MB** | 294 k / 19 MB |
| 300 m/s 12 km 即時飛行（rt2） | — | — | **63–77 MB** | — |
| 關閉（FAR OFF） | 1–11 | ≤ 20 k | **≤ 1.4 MB** | — |

- **預算：impostor 實例資料最壞情況 ≤ 100 MB**（目前 97 MB，在最密的林區）；一般 10–65 MB。距離由 grid 載入範圍決定，與地圖大小無關（全圖 386 萬棵，常駐的最多 134 萬）。
- 迭代：常駐（v1，只有 A/B 區域）→ 兩層 grid（v2a）實測 115 MB（forest_layers，且有邊界升級問題）→ 修正後 4+1 個 band grid：63 MB（同一視角，−45 %）。離線模型（`fi_stream_budget.py`）的「理想值」（只載入可能看得見的樹）是 44 MB：剩下的差距是 World Partition 以整個圓盤載入 cell 的固有成本。
- 遠層（`FI_B0`／`FI_B1`）用 2 km cell：在 300 m/s 下載入事件減半（即時飛行中 WP「Slow」從 26 s 降到 17 s），代價約 +9 MB。
- 比較基準：3D 樹在 PR #57 的常駐實例資料（同一算法）是 19–53 MB；impostor 層大約是它的 1.5–2 倍。GPU scene 端另有每實例資料（約同量級，未單獨量測）。
- **PR #57 的發現（未修改，以保留基準）**：(1) Tree distance 列的 World Partition 載入距離用的是 `wp.Runtime.OverrideRuntimeSpatialHashLoadingRange -grid=0`（舊 SpatialHash 的索引式指令），這張地圖是 RuntimeHashSet，需要用名稱式的 `wp.Runtime.OverrideRuntimeLoadingRange -grid=MainGrid`：實測三種預設的 3D 樹常駐量完全相同（661,298），也就是該列在 World Partition 上沒有作用。(2) `MainGrid` 是 3D grid、1 km cell，而每個 1 km 樹 tile 的邊界 > 1 km，同樣會被升級到更大的 cell（3D 樹實際載入範圍大於 3.9 km）。修好這兩點，候選配置（3D 樹 2.2 km）還能再省下約 20–40 % 的 3D 樹常駐記憶體——建議另開 PR 處理。

### 10d. 兩個畫面問題的修正

**5–7 km 遠山輪廓被樹冠模糊**：根因是 v5 讓 impostor 一直畫到 7 km 並放大到 1.6 倍，蓋掉 PR #49 地形皮膚的稜線與溝谷明暗。v6：impostor 4.8→6.0 km 淡出（7 km 以外完全交回山形），放大上限 1.25，地形法線彎曲 2→5 km、最多 0.75。`v2/v2_crop_forest_layers.jpg`：上 PR #57 High、中 PR #58 v5、下 v6 —— 7 km 以外的山脊、溝谷明暗回來了，3–6 km 的樹冠立體感保留。

**農田散生樹黑點**：根因有三。(1) v5 讓田間樹以放大 1.6 倍的 impostor 畫到 7 km；(2) 全域亮度校正來自密林（樹冠互相遮蔭），單株樹太暗；(3) 遠處稀疏化在**稀疏林**裡只留下零星幾棵 → 一顆顆點。v6 規則：一棵樹若「Landscape 在它底下不畫森林」（`T_NF_Mask1` R < 0.5）**或**「周圍 250 m 內的樹 < 550 棵」（森林中位數 686 的約 80 %，全圖 17.4 % 的樹），就歸為稀疏林：impostor 不放大、亮度 ×1.3、在 2.8 km（＝ 3D 田間樹在 High 的範圍）淡出，並放在自己的短距 grid（`FI_ISO`，3.6 km）。`v2/v2_crop_far_range.jpg`：4–6 km 谷底恢復成 PR #57 的乾淨農田；2.2–2.8 km 的田間樹仍在、色調接近 3D 樹。全部是全域規則，沒有逐棵、逐區修改。

### 10e. A/B 結果（最終：`ab13`，ES3.1 預覽，2560×1600，UHD 770，同 session、兩個順序）

| 視角 | PR #57 High | PR #58 v5 | **v6** | PR #57 Ultra | v6 vs High | v6 vs Ultra | draw call High → v6 |
|---|---:|---:|---:|---:|---:|---:|---:|
| forest_layers | 142.4 | 127.4 | **125.0** | 239.1 | **−12 %** | **−48 %** | 2,052 → 2,076 |
| mid_ridge | 196.8 | 178.2 | **176.7** | 374.6 | **−10 %** | **−53 %** | 1,414 → 1,569 |
| basin_edge | 50.2 | 50.3 | **50.4** | 66.8 | ±0 % | −25 % | 927 → 1,008 |
| far_range | 87.3 | 73.5 | **73.3** | 138.7 | **−16 %** | **−47 %** | 1,792 → 1,852 |

（PR #58 v5 在這裡是 v5 參數跑在 v6 串流資料上；GPU ms。）

**高速飛行（300 m/s）**

| | PR #57 High | PR #58 v5 | **v6** |
|---|---:|---:|---:|
| 逐格鎖定 3.6 km（`fly3`）GPU 中位 / p95 / 最大 | 120.5 / 163.0 / 171.1 | 92.1 / 135.6 / 140.1 | **92.9 / 135.5 / 149.6** |
| 遠景帶 pop（> 3× 局部中位） | 0 | 0 | **0** |
| 遠景帶閃爍（逐格變化中位） | 5.63 | 5.83 | 5.83 |
| 即時 12 km（`rt2`，1280×800）frame 中位 / GPU 中位 | 33.8 / 72.3 ms | — | **34.8 / 60.0 ms** |
| 即時飛行中 impostor 常駐 | — | — | 63–77 MB |
| 即時飛行 WP 串流狀態 | 2 s「Slow」 | — | 17 s「Slow」、無「Critical」 |
| 即時飛行 frame p95（WP 載入卡頓） | 633 ms | — | 574 ms |

- 即時飛行中兩個配置都有約 0.6 s 的 World Partition 載入卡頓（PR #57 本身就有，這台主機 CPU 被 PID 13716 佔一核）；impostor 層讓 WP 在 300 m/s 下處於「Slow」較久，但沒有可量到的遠景 pop（兩者都偵測到 1 次）。**S11 上需要再看一次**（CPU 不同）。

**畫面**（`v2/triptych_<view>.jpg`：PR #57 High／PR #58 v5／v6／PR #57 Ultra，同一格）：
- forest_layers：7 km 以外的稜線與溝谷明暗回到 PR #57 水準（v5 是一片朦朧樹冠紋理）；2–6 km 樹冠立體感保留。
- far_range：4–6 km 谷底恢復乾淨農田（`v2/v2_crop_far_range.jpg`）。
- 遠景帶結構相似度（1/4 解析度亮度 SSIM，畫面 30–46 % 高度，各自對同 session 的 PR #57 High；`farlod_metrics.py`）——PR #58 v5（提交的 `ab5`）→ v6（`ab13`）：forest_layers 0.893 → **0.914**、far_range 0.877 → **0.906**、basin_edge 0.961 → **0.989**、mid_ridge 0.949 → 0.946。（同 session 的「v5」這裡不當基準：它跑在 v6 資料上，6.2 km 外與稀疏林已被新的 grid 截斷。）「農田暗點」自動計數太吵（PR #57 High 自己就有 261 個），不作證據，以裁切圖為準。
- mid_ridge、basin_edge：與 v5 幾乎相同（這兩個視角沒有上述兩個問題）。
- 作廢的兩輪：`ab7`（舊 actor 沒刪，兩層 impostor 疊畫）、`ab9`（MPC GUID 不符，impostor 全部消失）——數據不採用，原因見 10b。

## 11. S11 測試 APK（獨立安裝，不覆蓋 0.2.0）

| | |
|---|---|
| 檔案 | `SkyfrontFarLODTest-0.3.0-farlod-dev-arm64.apk`，1,201,993,474 bytes（1,146 MB），SHA-256 `4180cf5d…60730112`（`v2/apk_manifest.json`） |
| 位置 | `D:\Users\EDDY\SkyfrontBuilds\`（與 0.1.0、0.2.0 並列；0.2.0 未動） |
| Package | `com.skyfront.homeland.farlodtest` 0.3.0-farlod（versionCode 3），arm64-v8a，minSdk 29 / targetSdk 34，Vulkan，ASTC，Development |
| 簽章 | 與 0.1.0／0.2.0 同一個 debug 憑證；package name 不同 → **另外安裝，不會更新或覆蓋 0.2.0** |
| 建置 | BuildCookRun exit 0，14 分鐘；cook 2,551 個 package、0 error、1 warning；比 0.2.0 大 395 MB（全圖 impostor 資料） |
| 實機 | **未測**（這台主機沒有連接 S11） |

**與 0.2.0 的差別**：package name `com.skyfront.homeland.farlodtest`（0.2.0 是 `com.skyfront.homeland.freeflight`）→ 兩個 app 可以同時安裝、互不覆蓋；圖示名稱「Skyfront FarLOD Test」、版本 0.3.0-farlod。遊戲、飛行、PR #57 的圖形設定全部一樣；impostor 層**預設關閉**（與 0.2.0 相同的畫面）。

**新增兩個按鈕（GFX 面板標題列）**
- **FAR OFF / FAR ON**：遠景 impostor 層開關（v6 參數）。開啟後串流載入，約 1–3 s 內補齊。若要看候選配置：選 High，再把「Tree distance」往左一格（2.2 km），然後 FAR ON。
- **BENCH**：在平板上自動跑 A/B（約 8 分鐘，請勿觸碰）：4 個固定視角 × 5 個配置（Balanced、Balanced 3D 1.5 km + impostor、High、High 3D 2.2 km + impostor、Ultra），正反兩個順序。結束後畫面左側顯示 GPU ms 表與 forest_layers 的常駐記憶體（impostor／3D 樹／整個 process），同時寫入 app 的 `Saved/FarLodBench.txt`。跑完會恢復原本的設定。
- 診斷 overlay 多一行：`FAR IMPOSTORS ON/OFF: near / far 常駐實例 (MB)、3D trees (MB)`。

**S11 測試單（回報這些就夠）**
1. 安裝後開 DIAG，確認裝置 profile 與 RHI 行（預期 Android_Mali_G9xx_Vulkan / Vulkan）。
2. 按 BENCH，等它跑完，拍下結果表（5 個配置 × 4 個視角的 GPU ms ＋記憶體三行）。
3. High：FAR OFF 與「High + Tree distance 2.2 km + FAR ON」各自自由飛 2–3 分鐘（240–400 km/h），看 overlay 的 FPS／frame／GPU ms 與「last change」；注意遠處是否有樹突然出現或閃爍。
4. 10 分鐘溫度測試：High + 2.2 km + FAR ON 持續飛行，記 FPS 的變化。
5. 主觀：2–6 km 森林的立體感、7 km 以外山形、農田遠處有沒有黑點。

**不在這個 APK 裡**：PR #57 Tree distance 列對 World Partition 無效的修正（10c，保留基準）、城市 HLOD。

## 12. v2 結論與建議

| | |
|---|---|
| 串流 | 全圖 386 萬棵 impostor 用 5 個 2D World Partition grid 依距離載入；常駐最壞 97 MB（最密林區）、一般 10–65 MB、關閉 ≤ 1.4 MB；300 m/s 即時 12 km 無可量到的遠景 pop |
| 畫面 | 7 km 外山形恢復、4–6 km 農田恢復乾淨；2–6 km 樹冠立體感保留 |
| 成本 | v6 比 PR #57 High 便宜 10–16 %（森林）、比 Ultra 便宜 47–53 %；draw call 增加 ≤ 160 |
| 下一步 | (1) S11 上跑 BENCH（§11 測試單）；(2) 另開 PR 修 PR #57 Tree distance 列的 World Partition 指令與 `MainGrid` 邊界升級（10c），候選配置還能省 3D 樹記憶體；(3) 若 S11 上 WP 串流在 300 m/s 長時間「Slow」，把 `FI_B2`／`FI_B3` 也改 2 km cell（代價約 +10 MB）；(4) 城市 HLOD 原型 |

**PID 13716（只調查，未終止）**：仍存在。是 2026-10-16 17:50 一個舊 Claude Code session（`07d9068d…`）的背景指令：`Get-ChildItem -Path D:\out, …\air-combat-world\out\treegen, C:\Users\EDDY\out -Recurse -Filter "it1_front.png"`，跑超過 120 s 被移到背景後一直沒有結束。三個搜尋路徑現在都不存在，輸出檔是空的，但它持續佔用約一個 CPU 核心（5 s 內 4.95 CPU 秒，累計約 135 小時）。父程序是同一舊 session 的 `claude.exe`（PID 23816）。判斷：**無用的孤兒程序**，可以安全結束（`taskkill /PID 13716 /F`）；它會讓這台內顯的絕對效能數字在不同 session 間漂移。

**v2 重現**
```powershell
python tools/ntw/forest_world/fi_terrain_normal.py <run> unreal/TreeLookdev/Saved/NorthForest/fi_pack/3
python tools/ntw/forest_world/fi_forest_mask.py <run> unreal/TreeLookdev/Saved/NorthForest/fi_pack/3
python tools/ntw/forest_world/fi_stream_budget.py <run>                       # offline residency of grid layouts
$env:ACW_FI_PARTS='mpc,mat,actors'; $env:ACW_FI_CAMS='all'; tools\ntw\forest_world\run_nf.ps1 -Script fi_build.py -Name fi_build -Expect fi_build.report.json
$env:ACW_FI_GRIDS='FI_B0:200000:680000,FI_B1:200000:680000'; tools\ntw\forest_world\run_nf.ps1 -Script fi_grids.py -Name fi_grids -Expect fi_grids.report.json
tools\skyfront\run_farlod_ab.ps1 -Tag ab13 -Views 0,1,2,3                    # high / pr58_v5 / v6 / ultra, census in SKYFL lines
tools\skyfront\run_farlod_ab.ps1 -Tag rt2 -Fly -Realtime -FlySeconds 40 -FlyCfgs 0,2 -ResX 1280 -ResY 800
tools\skyfront\run_farlod_ab.ps1 -Tag fly3 -Fly -FlyCfgs 0,1,2 -ResX 1280 -ResY 800
python tools/skyfront/farlod_metrics.py unreal/TreeLookdev/Saved/Skyfront/ab13
# APK: move Plugins/XinyiLandscapeBridge out, then
tools\skyfront\package_android.ps1 -ArchiveName android_archive_farlod     # then move the plugin back
```

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
