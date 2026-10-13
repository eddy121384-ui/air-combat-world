# 北台灣白模 Phase 2B — Runtime Gate（UE 5.8 隔離場景）

日期：2026-10-13 · 分支：`feat/ntw-phase2b-runtime-gate`（自 PR #23 `feat/ntw-phase2b-north-core-terrain` @ `b20d454` 建立）
回應：Sophira Review #5496569016（PR #23，CONDITIONAL PASS offline only）。
環境：Windows 11、i7-12700、**Intel UHD Graphics 770 內顯**、15.6 GB RAM；venv `acw-ntw`；UE 5.8（只用隔離臨時專案
`D:/Users/EDDY/UEIsolated/NTWRuntimeGate`）。
**未修改**：信義 25 個已接受 GLB、信義 Landscape R16、正式 Unreal 專案 / 場景、`worlds/battlefields/north_core_v1.json`（112 km 設定）。
未生成全北台灣，未 Merge 任何 PR。

標記：**MEASURED** = 引擎或腳本實測；**ESTIMATE** = 推算；**NOT TESTED** = 本輪未做，不宣稱通過。
所有 Runtime 數字都來自 UE 5.8 PIE 實際執行（`UnrealEditor.exe`、D3D12），**不是**資產匯入成功的代用指標。

---

## 0. 結論（Gate 判定）

| 項目 | 結果 |
|---|---|
| UE 隔離 Runtime 場景 | World Partition 關卡：50 個地形 chunk Actor（真實 5 級 LOD chain）+ 接受的信義 Landscape（631² R16，以量測仿射作為 Actor transform）+ stitch v2 / v1 + 25 個信義建築 tile。PIE 實際執行，兩次 session 共 ~13 分鐘 |
| 地形碰撞（66,446 條垂直 trace） | 網格誤差 **≤ 0.2 mm**、Landscape 誤差 **≤ 2.5 mm**（對應引擎實測的四邊形對角線 A）、錯誤 Actor **0**、接縫連續性 **≤ 2.9 mm**。**FAIL（僅限正好落在邊界線上的射線）**：26 條恰好落在信義 Landscape / stitch 共用邊界線上的射線兩者都沒打到；**偏離邊界 ≥ 0.5 mm 的 9,600 條全部命中** → 縫寬 < 0.5 mm 的零寬度重合邊界退化，非可見破洞（§3.3，附修正建議） |
| Actor 座標精度 | **PASS**：50 chunk / 2 stitch / 25 建築 PIE 位置誤差 **0.0 cm**；Landscape 四角 vs 仿射 ≤ **0.0001 cm**；距原點 156 km 的探針讀回 0.0 cm、trace 打頂面誤差 0.0 cm |
| 不同 LOD 組合（507 張 SceneCapture） | **FAIL（如實保留）**。信義接縫本身：stitch v2 + 「信義邊界 Landscape component 強制 LOD0」+「stitch LOD = 相鄰 chunk LOD」在所有組合下**接縫裂縫 0**；但剩下 53 px 裂縫位於 **Landscape 內部**、強制 LOD0 的邊界環與較粗內部 component 的交界（不是接縫）。stitch LOD ≠ chunk LOD 時 hole 側出現大面積破洞（最大 24 萬 px）；Landscape LOD ≥ 1 且無策略時 v2 接縫最大 866 px；v1（舊 decimated stitch）在 stitch LOD ≥ 2 時即使有策略仍有接縫裂縫 |
| Review 指出的 Xinyi 不同 LOD stitch 偏差 | **已消除（離線 + 引擎）**：stitch v2 每個 LOD 都保留信義 2,520 個全解析度邊界頂點，`ring_vs_full_res` 偏差 LOD1–4 由 0.94 / 4.28 / 7.78 / 19.73 m → **0.0 m**；引擎 v2 vs v1 比較見 §4 |
| 300 m/s 飛越串流（1.6 km cell / 8 km 載入範圍） | **PASS（桌機 PIE，2 個 Cell）**：150/300/600/800 m AGL 四次飛行 + 低畫質 + 擷取飛行，前方 0/0.5/1/2/4/6 km **地形存在率 100 %**；loaded chunk 28→50→28 平滑變化；記憶體變化 < 62 MB。frame time p50 ~56 ms 為內顯 GPU-bound，**不代表手機** |
| 失敗證據：模板預設網格（252 m / 768 m） | **重現失敗**：PIE 起始時中心只載入 4/50 chunk；300 m/s 時前方 1 km 地形存在率 87 %、2 km 僅 **54 %**、4 km 22 %，第 15 m 就出現第一個缺地形；截圖可見只有永遠載入的信義 Landscape 浮在空中 |
| 建築 shard 嚴格模式碎片 | 嚴格預設不變（`FRAGMENT_POLICY` / `QUANT_FALLBACK` 都預設 **OFF**）。全台北 374,238 個 WFS part 掃描：嚴格模式只擋 **10 個**（1 個 4.6e-6 m² 碎片 + 9 棟真實建築）；候選 float32 格點吸附 fallback 以寬度 / 面積 / 中庭核心門檻把 10/10 解掉（9 棟建模、1 碎片入帳），0 FAIL；信義 11,128 part **0** 觸發 → 信義建置位元不變（構造保證）。**候選政策，需審核 + 回歸後才可進生產** |
| 整個相鄰 8 km Cell shard 測試（混合 WFS / Overture、跨台北 / 新北） | **機制 PASS**：435/435 tile 逐位元相同、0 重複、0 孤兒、信義 ID 0、剔除邊界式載入 0 漏載（Cell 矩形式載入 12–16 處漏載 → FAIL）。**生產 FAIL**：1 個退化來源 part（面積 0 m²、mesh 階段失敗）、跨提供者重疊 4 組 131 m²、Cell A 11.76 km² 來源 BLOCKED（§7.3） |
| 112 / 120 / 128×112 km 比較 | 只比較、**未修改 112 km 設定**。兩個擴展方案新增面積 **100 % 為海**、0 新陸地 Cell、0 建築、0 地形三角形；128×112 西擴讓西側海域 2,606.6 → 3,758.6 km²（+44 %）、核心西海岸最小縱深 14.6 → 30.6 km；東側核心縱深三案皆 0 km（限制已標註） |
| 手機效能 / packaged build / HLOD | **NOT TESTED** |

---

## 1. Git 與範圍

- 分支自 `origin/feat/ntw-phase2b-north-core-terrain`（PR #23 HEAD `b20d454`）建立，Draft PR base 為該分支。
- 主 checkout（目前在別的任務分支）只做**唯讀**存取：信義接受的 Landscape 合約 / GLB。
- 大型產物全部不進 git：UE 臨時專案、PIE 原始擷取（570 張 / 327 MB）、shard GLB、地形 GLB。提交的是精簡 JSON（`data/ntw/runtime/`、`data/ntw/terrain/`、`data/ntw/battlefield/`）與縮圖證據（`docs/evidence/ntw/runtime/`，約 4 MB）。

## 2. UE 5.8 隔離 Runtime 場景（`tools/ntw/ue_gate/`）

| 階段 | 腳本 | 內容 |
|---|---|---|
| 輸入 | `prepare_gate_inputs.py` | trace 點與**期望高度**（Landscape 內 = 接受的 R16；外 = 實際出貨網格的垂直射線）、13 個接縫攝影機、5 個高度攝影機、4 條沿地形包絡（±1.2 km 最大值）+ AGL 的飛行路徑、11,200 條微偏移 trace |
| 建置 | `ue_gate_build.py`（`UnrealEditor-Cmd`） | OpenWorld 模板 → 刪除樣本地形；WP runtime grid 設為 1.6 km / 8 km；匯入 50 chunk × 5 LOD 並組成真實 LOD chain（螢幕尺寸由 Phase 2B 量測切換距離換算）、complex-as-simple 碰撞；信義 Landscape 以 bridge `ALandscape::Import` 建立，Actor transform = 位置 + yaw −0.23925° + 非等向 XY scale（397.04 / 394.86 cm）；25 建築 tile；洋紅色 unlit 偵測平面（地下 200 m、恰為兩 Cell 範圍）；精度探針；**actor 普查失敗即中止** |
| Runtime | `ue_gate_runtime.py`（`UnrealEditor.exe` PIE） | 碰撞 trace、Actor 精度、LOD 矩陣、高度序列、300 m/s 飛行、模板網格失敗證據 |
| 執行器 | `run_gate.py` | 外部 psutil 每 0.25 s 取樣編輯器 RSS / private bytes；逾時強制結束 |
| 分析 | `analyse_runtime.py` | 產生 `data/ntw/runtime/runtime_gate_result.json` 與證據圖 |

隔離外掛（不在 repo）：`XinyiLandscapeBridge` 的隔離副本加上 `UNtwGateLibrary`（反射設定 WP runtime grid、讀取 runtime cell 狀態、`IsAllStreamingCompleted`、編輯器背景節流開關——這些 UE 5.8 Python 都沒有暴露）。

### 2.1 Gate 過程中抓到並修正的問題（失敗證據，全部保留在本節）

1. **WP 外部 Actor 殘留**：重建關卡時舊建置的 `__ExternalActors__` 沒被清掉，每個 Actor 重複兩份 → 第一輪 LOD 擷取全部「看起來一樣」。修正：建置前清除、建置後 actor 普查不符即 FAIL。
2. **LOD chain 材質槽**：`SetLodFromStaticMesh` 帶入每個 LOD 自己的 glTF 預設材質槽 → 強制 LOD2 的 chunk **完全看不見**、stitch LOD2 全黑。引擎讀回每個 LOD 的頂點 / 法線都正確，問題在材質槽。修正：每個 LOD section 重新指向槽 0，建置時驗證。
3. **`r.ForceLOD` 會連 Landscape 一起強制**（`LandscapeRender.cpp` `GetViewLodOverride`）→ 無法表達「Landscape 與網格不同 LOD」。改用逐 component `SetForcedLOD` 與逐 mesh `SetForcedLodModel`。
4. **串流完成的假陽性**：teleport 後數幀內 `IsAllStreamingCompleted` 會在 0 個 cell 載入時回 true → 改為「≥ 1 s 且連續 15 幀完成」。
5. **洋紅偵測被霧 / 大氣染色**：真實破洞在有霧時呈紫藍色，計數為 0 → 裂縫擷取關閉 Fog / Atmosphere / VolumetricFog / Cloud。
6. 模板網格 session 第一次因「嚴格 actor 普查」中止（768 m 範圍只載入 4/50 chunk，本身就是證據）→ 該 session 改為只記錄；建築 tile 串流出去後留在 trace 忽略清單會造成無效物件 → 飛行時只忽略玩家 pawn（建築本來就無碰撞）。
7. 編輯器結束時偶發 `0xC0000005`（log 已寫完「Exiting」之後），不影響結果。

## 3. 地形碰撞（MEASURED，Visibility channel、simple collision）

### 3.1 trace 集合與結果

| 集合 | trace 數 | 未命中 | 錯誤 Actor | 網格 dz 最大 | Landscape dz 最大 |
|---|---:|---:|---:|---:|---:|
| 信義南 / 東 / 北 / 西邊（每 2 m，偏移 −2 / −0.5 / −0.05 / +0.05 / +0.5 / +2 m） | 4 × 7,494 | 0 | 0 | 0.2 mm | 2.5 mm |
| 四角（±3 m、0.25 m 格點） | 4 × 625 | 26（全在邊界線上） | 0 | 0.1 mm | 1.8 mm |
| Cell 接縫 N 2,768,000（±5 cm） | 7,990 | 0 | 0 | 0.1 mm | — |
| Chunk 接縫 E 305,600（穿過信義）/ N 2,763,200 | 15,990 / 7,990 | 0 | 0 | 0.1 mm | 0.1 mm |
| 官方 DEM 節點（chunk 頂點） | 1,785 | 0 | 0 | 0.0 mm | — |

- 引擎 Landscape 碰撞的四邊形切分為對角線 A：以 A 三角化計算期望值時最大誤差 2.5 mm；用 B 會是 171 mm；用雙線性為 86 mm（因此期望值用 A）。
- **期望值修正（全部在看過完整 run 後決定，已揭露，引擎資料未改）**：(a) 角落格點中 100 個正好在邊界線上的點改為「兩者皆可」；(b) DEM 節點抽樣原本抽到 107 個 skirt 頂點（低 2 m）與 108 個信義洞內孤立頂點，排除後只檢查頂面節點；(c) 穿過信義的 chunk 接縫點期望為 Landscape。

### 3.2 接縫連續性

±5 cm 的原始高度差在南邊陡坡最大 0.26 m——那是**坡度**（南緣坡度達 ~2:1），不是斷差。連續性改用兩種與坡度無關的量測（評估方式在 run 後改變，已揭露；門檻 0.10 m 未變）：

| 接縫 | 相隔 1 mm（±0.5 mm）高度差 最大 | ±5 cm 殘差（各自減去自己的期望面）最大 |
|---|---:|---:|
| 信義南 / 東 / 北 / 西 | 2.9 / 2.7 / 0.2 / 0.9 mm | 2.6 / 2.4 / 0.2 / 0.2 mm |
| Cell 接縫 / 兩條 Chunk 接縫 | — | 0.1 mm |

### 3.3 邊界線退化（26 條未命中）

微偏移測試（每邊 400 個樣本 × 7 個偏移）：

| 偏移 | 南 | 東 | 北 | 西 |
|---|---|---|---|---|
| −5 / −1 / −0.5 mm | 全部 Landscape | 全部 Landscape | 全部 Landscape | 全部 Landscape |
| **0（正好在線上）** | 174 未命中 | 184 未命中 | 204 未命中 | 0 未命中 |
| +0.5 / +1 / +5 mm | 全部 stitch | 全部 stitch | 全部 stitch | 全部 stitch |

結論：**不存在 ≥ 0.5 mm 的縫**；正好落在 Landscape heightfield 邊界與 stitch 邊界重合線上的射線（量測為零的集合）可能兩者都不算。飛機的 sweep / capsule 碰撞不會穿過零寬度線，但以生產門檻（0 未命中）判定仍為 **FAIL**。建議修正（下一輪）：給 stitch 一圈只用於碰撞、向 Landscape 內延伸 5–10 cm 的重疊 flange（或讓 Landscape 碰撞延伸半格），消除重合邊界；修正後重跑本 trace 集合。

## 4. 不同 LOD 組合與裂縫（MEASURED，`lod_matrix.json` 507 張）

設定：13 支接縫攝影機（四邊 250 m / 900 m、四角、Cell 接縫）× 12 種組合（Landscape LOD L、stitch LOD T、chunk LOD C；`auto` = 引擎自動選擇）× stitch v2 / v1 × 策略「無」/「信義邊界 16 個 Landscape component 強制 LOD0（border0）」。洋紅像素 = 看穿表面打到地下 200 m 的偵測平面。每張有裂縫的圖最多取 120 個裂縫像素，反投影到 LOD0 參考面分類位置。

| stitch / 策略 | 代表組合 | 裂縫 px（13 攝影機合計） | 位置分類 |
|---|---|---:|---|
| v2 / 無 | `auto`（引擎真實選擇） | 1 | 信義接縫 |
| v2 / border0 | `auto` | 1 | Landscape component 邊界 |
| v2 / 無 | L0_T0_C0、L0_T2_C0、L0_T2_C2 | 0 | — |
| v2 / 無 | L1 / L2 / L3_T0_C0 | 50 / 151 / 866 | 信義接縫 |
| v2 / border0 | L1 / L2 / L3_T0_C0 | 1 / 9 / 23 | **Landscape component 邊界**（0 接縫） |
| v2 / border0 | L2_T2_C2 / L3_T3_C3 / L3_T4_C4 | 3 / 12 / 4 | Landscape component 邊界 |
| v2 / 無 | **L0_T0_C2 / L0_T0_C4**（stitch ≠ chunk） | **767,799 / 2,043,984** | stitch hole 側、chunk 接縫 |
| v1 / 無 | L0_T2_C0 / L0_T2_C2 | 144 / 86 | 信義接縫（v1 decimated 邊） |
| v1 / border0 | L3_T3_C3 / L3_T4_C4 | 264 / 481 | 信義接縫（策略也救不了 v1） |

判讀：
1. **stitch v2 解決了 Review 的 LOD 偏差**：Landscape 邊界為 LOD0 時，任何 stitch LOD 都 0 裂縫；v1 在 stitch LOD ≥ 2 就裂。
2. Landscape 本身降 LOD 會讓它的邊界頂點離開 stitch 的全解析度邊 → 必須讓信義邊界 component 維持 LOD0（border0）。
3. border0 用 `ForcedLOD` 實作時，會在 Landscape **內部**、邊界環與較粗內部 component 交界產生小裂縫（強制 LOD 跳過 Landscape 的鄰居 LOD 漸變）→ 正式政策不能用硬性 ForcedLOD；下一輪測 `LODBias` / LOD 分佈設定讓邊界環在可視距離內自然維持 LOD0。
4. **stitch 與 chunk 的 LOD 必須鎖定**：stitch 是獨立 Actor，引擎依自己的 bounds 選 LOD，與相鄰 chunk 不同時 hole 側出現大面積破洞。正式方案：把 stitch 併入其所在 chunk 的 LOD chain（共用 LOD 選擇），或 stitch 的 hole 側每個 LOD 都對齊最粗 chunk LOD 並加 skirt。
5. 因此本項 Gate 為 **FAIL**，下一輪修正後重跑同一個矩陣。

證據：`docs/evidence/ntw/runtime/lod_matrix_*.png`（每支攝影機 8 種組合）、`crack_*.png`（裂縫放大）、`seam_debug_colour_views.png`（stitch 著紅色，看得出接縫位置）。

## 5. Actor 座標精度（MEASURED）

- 50 chunk、2 stitch、25 建築：PIE 世界中 `GetActorLocation` 與 EPSG:3826 → UE cm 期望值的差 **0.0 cm**（double，LWC）。
- 信義 Landscape：位置 / yaw / scale 與建置值一致；四角經 Actor transform 後與仿射映射的 ENU 四角差 ≤ **0.0001 cm**。
- 精度探針（10 m 方塊、永遠載入）：近原點 (37.37, −61.61, 12345.67) cm 與 ~156 km 外 (11,000,000.37, −11,000,000.61, 12345.67) cm 讀回誤差 0.0 cm；從上方以小數座標 trace 頂面，誤差 0.0 cm。
- 「執行中移動 0.01 cm」不適用：StaticMeshActor 為 Static mobility，引擎拒絕移動（記錄為 not applicable）。

## 6. 300 m/s 飛越串流（MEASURED，桌機 PIE）

路徑：E 305.2 → 307.4 km、N 2,760.4 → 2,775.6 km（15.36 km，穿過 Cell 接縫與信義區），以真實經過時間 300 m/s 移動 pawn（串流來源），每幀記錄 dt、loaded chunk Actor、runtime cell 狀態、串流完成、前方 0/0.5/1/2/4/6 km 地面 trace。

| 飛行 | 幀數 | dt p50 / p99 / max (ms) | >100 ms | chunk Actor | 前方 1 / 2 / 4 km 地形存在 | RSS 變化 |
|---|---:|---|---:|---|---|---:|
| 1.6 km / 8 km，150 m AGL | 908 | 56.6 / 62.3 / 125.7 | 1 | 28–50 | 100 / 100 / 100 % | −7 MB |
| 同，300 m | 918 | 56.0 / 61.0 / 121.3 | 1 | 28–50 | 100 / 100 / 100 % | −4 MB |
| 同，600 m | 919 | 55.9 / 61.8 / 119.9 | 1 | 28–50 | 100 / 100 / 100 % | −62 MB |
| 同，800 m | 927 | 55.4 / 59.8 / 122.8 | 1 | 28–50 | 100 / 100 / 100 % | +3 MB |
| 同，300 m，scalability 0 | 1,963 | 27.0 / 31.4 / 97.4 | 0 | 28–50 | 100 / 100 / 100 % | +20 MB |
| **模板 252 m / 768 m**，300 m | 957 | 53.1 / 66.7 / 129.3 | 1 | **2–9** | **87 / 54 / 22 %** | +8 MB |
| 模板，150 m | 947 | 53.7 / 65.4 / 138.8 | 1 | 2–9 | 88 / 54 / 22 % | +2 MB |
| 模板，300 m，scalability 0 | 2,068 | 24.6 / 30.8 / 105.9 | 1 | 2–9 | 88 / 54 / 22 % | +16 MB |

- 編輯器程序 RSS ~4.1–4.4 GB（整個 UE 編輯器，不是遊戲記憶體預算）。
- frame time 由 UHD 770 內顯 GPU 主導（scalability 0 減半）；每次飛行約一個 ~120 ms 尖峰，位置不固定。**這不是手機數據，也不是 packaged build**；30 FPS 手機目標維持未驗證。
- 擷取飛行（每秒一張，GPU 回讀造成停頓，該幀不計入統計）：`flight_configured_agl300_captured.png` vs `flight_template_default_grid_agl300_captured.png`。

## 7. 建築 shard：嚴格模式碎片（Review P0 #2）

### 7.1 母體掃描（`tools/ntw/fragment_scan.py` → `data/ntw/terrain/fragment_scan.json`）

全台北 WFS 373,532 筆 / 374,238 個 part 跑接受的 repair + `prepare_footprint`：

| 結果 | 數量 |
|---|---:|
| 嚴格 footprint 階段失敗 | **10**（1 個非最大碎片：4.6e-6 m²、平均寬 7.6e-7 m；9 個最大塊 = 真實建築 13–990 m²） |
| 原始來源拒絕（另行入帳） | 24 |
| 信義已接受 ENU 來源 11,128 part | **0 失敗** |

9 棟：`tp_building_height.125625 / 167294 / 171665 / 179103 / 286126 / 301157 / 353579 / 360929 / 361019`（失敗原因：5 個 quantized invalid / collapsed、4 個 courtyard not preserved、1 個 point contact）。

### 7.2 候選政策：float32 格點吸附 fallback（`tools/ntw/quantization_fallback.py`，預設 OFF）

只有在**接受的路徑已失敗**時才執行：
1. tile-local 以 GEOS `set_precision` 吸附到 2⁻¹³ m（≈0.12 mm）格點（|x| < 1024 m 時 float32 可精確表示）；
2. 來源保真門檻（對**原始** part，不放寬任何既有門檻）：被移除 / 新增的區域內縮 1 格後面積必須為 0（寬度 < 2 格）；|ΔA| 與對稱差 ≤ 周長 × 格 + π 格²；原始中庭內縮 2 格後的核心必須仍為空；
3. 吸附後的 footprint 再跑**未改動**的 `prepare_footprint`、mesher 與嚴格網格門檻（float64 / float32 / GLB 回讀）。

`tools/ntw/fallback_eval.py` 結果：10/10 → 9 建模、1 碎片入帳（id + 面積）、**0 FAIL**。最大面積變化 2.6e-3 m²（283.9 m² 建築）。說明：
- 第一版用 Hausdorff 當門檻擋下 5 棟，原因是零寬度的數位化「髮絲」（長達 3.7 m、面積為 0）——因此改為寬度門檻；Hausdorff 仍記錄。
- 中庭數「4 → 1」等情況：被吸附消失的是寬度 < 0.5 mm 的退化洞（核心檢查保證真正的中庭仍為空）；point-contact 洞變成凹口，空區域不變。
- 只會改動「原本就失敗」的 part → 已接受的建置（例如全信義 0 失敗）啟用後**位元不變**（構造保證，§7.1 證明觸發集合）。
- `build_pilot.py` 新增 `QUANT_FALLBACK = {"enabled": False}`，報告列出每個套用案例；`FRAGMENT_POLICY` 仍預設 OFF。**啟用於正式生產前需審核 + locked representative / full-Xinyi 回歸**（AGENTS.md）。

### 7.3 整個相鄰 8 km Cell shard 測試（`tools/ntw/building_cell_shard_test.py`）

兩個**完整** 8 km Cell，以未改動的接受幾何堆疊獨立建置與聯合建置（`data/ntw/terrain/building_cell_shard_test.json`）：
A = C+0038+0345（E 304–312 km / N 2,760–2,768 km）、B = C+0038+0346（N 2,768–2,776 km，含信義，其 WFS ID 以 L3 抑制）、joint = 兩者。
提供者擁有權：source part 頂點平均質心在 TW-TPE（Overture divisions 本地快取）內 → 台北 WFS；外 → Overture（2026-09-23.1 快取）；非擁有者的副本**入帳為 excluded**，不靜默丟棄。`FRAGMENT_POLICY` OFF、候選 `QUANT_FALLBACK` ON。

| 項目 | A | B | joint |
|---|---:|---:|---:|
| source part（含兩提供者） | 56,018 | — | 219,465 |
| 輸出 part | 43,000 | 116,567 | 159,567（WFS 156,617 / Overture-OSM 1,051 / Overture-zenodo 1,899） |
| 嚴格 Gate | **FAIL（1）** | PASS | **FAIL（1）** |
| tile | 194 | 241 | 435 |
| 三角形 | 1,593,336 | 4,992,296 | 6,585,632 |
| GLB | 51.9 MB | 153.7 MB | 205.6 MB |
| 建置時間 | 909 s | 3,310 s | 4,209 s |

**嚴格 FAIL 的原因（新發現，如實保留）**：`tp_building_height.307096` 第 1 個 part 是**退化來源輪廓**——85 個頂點、自相交、來源面積 **0.0 m²**；GEOS `make_valid` 把它碎成 23 個合計約 0.003 m² 的微小碎片，其中 2 個通過 footprint 門檻卻在 **mesh 階段**失敗（`zero_area_triangles:2`、`extrude_geos_polygon requires a valid area-bearing Polygon`）。
- §7.1 的全市掃描只涵蓋 footprint 階段，所以沒抓到這一類；候選 fallback 也只處理 footprint 階段 → 正確地沒有介入。
- 兩個 Cell 共 15.9 萬個輸出 part 中只有這 1 個 mesh 階段失敗。
- 建議（下一輪、需審核的**全域**規則，不是逐棟例外）：repair 結果「全部碎片都低於序列化解析度、且來源面積為 0」時以 `source_rejected: repaired_to_sub_resolution_fragments` 入帳；並把全市掃描延伸到 mesh 階段。

因為 A / joint 嚴格失敗時依規定不寫出 GLB，shard 機制改以**明確的診斷旗標** `DIAGNOSTIC_WRITE_ON_FAILURE`（預設 OFF、報告中標示、Gate 結果仍為 FAIL）寫出其餘通過的 tile 來量測：

| shard 機制 | 結果 |
|---|---|
| 聯合 vs 獨立 tile | 435 / 435 **逐位元相同**；tile 集合相同 |
| 擁有權 | 兩個 Cell 都輸出的 part **0**；獨立聯集 = 聯合；聯合內重複 0 |
| 孤兒 | A / B / joint 皆 **0** |
| 信義 | 信義 WFS ID 輸出 **0**；聯合抑制 11,136 part |
| 嚴格失敗集合（fallback 介入處） | 7 個 part：6 棟建模 + 1 碎片入帳（皆屬 §7.1 的 10 個） |
| 剔除邊界 overhang（實測） | A：西 68.2 m、北 20.0 m、東 9.6 m（72 個 component 越界）；B：南 36.9 m、北 8.1 m（63 個） |
| 載入情境（相機 50 m 格點 154,401 點） | 以 8 km **Cell 矩形**決定載入：V = 1.5 km 有 12 個位置、V = 3 km 有 16 個位置「看得到但所屬 shard 未載入」→ **FAIL**；以**實測剔除邊界**決定載入：0 → PASS。規則：shard 載入判斷必須用剔除邊界（Cell + overhang），不能用 Cell 矩形 |
| 跨台北 / 新北界線的重複建築 | 界線 200 m 帶內 WFS 2,684 / Overture 406 個 part；**4 組重疊（131.2 m²）**：一個 Overture 輪廓（質心在新北、447 m²）覆蓋 4 棟台北 WFS 建築 → 以質心擁有權不足以避免跨提供者重複，下一輪需要「非擁有者輪廓與擁有者重疊即抑制」的全域規則 |
| 來源缺口 | A 有 **11.76 km²**（台北市外、Overture 快取範圍外：新店 / 深坑一帶）**BLOCKED**——不是空地；本輪不新增下載 |

結論：shard 機制（擁有權、位元相同、無孤兒、信義抑制、剔除式載入）在整個 Cell 尺度 **PASS**；正式生產 Gate **FAIL**（1 個退化來源 part、跨提供者重疊 4 組、A 有 11.76 km² 來源缺口）。嚴格預設未降低。

## 8. 戰場尺寸比較（MEASURED，`tools/ntw/battlefield_compare.py`，未改 112 km 設定）

| 方案 | 範圍 EPSG:3826 | 西側縱深 最小 / 中位 | 北側 最小 | 西側海域 | 前線海域（核心西海岸 0–50 km） | 新增面積 |
|---|---|---|---:|---:|---:|---|
| **112 × 112（已提出）** | E 224,000–336,000 / N 2,728,000–2,840,000 | 14.6 / 29.4 km | 41 km | 2,606.6 km² | 6,669.5 km² | — |
| 120 × 120 | E 216,000–336,000 / N 2,728,000–2,848,000 | 22.6 / 37.4 km | 49 km | 3,182.6 km² | 7,633.4 km² | +1,856 km²（100 % 海） |
| 128 × 112 西擴 | E 208,000–336,000 / N 2,728,000–2,840,000 | 30.6 / 45.4 km | 41 km | 3,758.6 km² | 7,842.6 km² | +1,792 km²（100 % 海） |

- 反登陸任務空間：三案海岸線 263.1 km、平坦低海岸代理（內陸 1 km 平均 DTM < 20 m）187.4 km、Overture 海灘 63 處**完全相同**——擴展只增加外海縱深（接敵 / 艦隊待命 / 低空進場空間），不增加登陸地點。
- 額外地形製作成本：**0** 新陸地 Cell、0 建築、0 LOD0 地形三角形（生產區若跟著擴大也一樣）；只需水面與遠景。
- 限制：三案東側核心縱深皆 **0 km**（東北角海岸基隆 → 三貂角離開方框，無東側海面緩衝）。
- 建議：維持 112 km 為生產網格；若需要反登陸 / 海上打擊任務，128×112 西擴可作為**任務變體**（成本只有海面），最終尺寸需遊戲性審查後決定。圖：`docs/evidence/ntw/battlefield/north_core_v1_compare.png`。

## 9. Review P1 項目狀態

- **P1 5 LOD 模型是代理**：本輪改用引擎實際 LOD 選擇（`auto` 列）、強制組合與 300 m/s 飛行驗證；坡度 / 剪影 / pumping 的量化指標仍待下一輪（本輪只有擷取圖與裂縫計數）。
- **P1 6 資料與範圍**：官方圖幅來源保留；DTM 缺口仍 BLOCKED；224 km 為**包絡**不是生產承諾；Overture 快取範圍外的新北 11.76 km² 在 Cell A 標記為 BLOCKED（§7.3），本輪不新增下載；海岸線裁切驗證仍為海岸生產前的 Gate；80 萬棟可飛行建築**不等於** 80 萬個 runtime Actor（本輪 25 個 500 m tile Actor 承載全信義）。

## 10. NOT TESTED / 下一 Gate

1. 碰撞重疊 flange（或 Landscape 碰撞延伸）後重跑 §3.3 微偏移與邊界線 trace。
2. Landscape 邊界 LOD：以 `LODBias` / LOD 分佈取代硬性 `ForcedLOD`，重跑 §4 矩陣（目標 0 px）。
3. stitch 併入 chunk LOD chain（或 hole 側對齊最粗 LOD + skirt），重跑 stitch ≠ chunk 組合。
4. 手機（iPhone 11 Pro 級）packaged build：frame time、記憶體、串流；HLOD；cook。
5. 補齊 Cell A 新北部分的 Overture 來源後重跑 §7.3。
6. 全域規則候選（需審核）：退化來源（面積 0、repair 只剩次解析度碎片）入帳為 source_rejected；非擁有者輪廓與擁有者重疊即抑制；全市掃描延伸到 mesh 階段。

## 11. 重現

```bash
python tools/ntw/build_terrain_cells.py --cells C+0038+0346 C+0038+0345 --identity-nodes --out data/generated/ntw/terrain/joint_ue_local
python tools/ntw/build_terrain_cells.py --cells C+0038+0346 C+0038+0345 --identity-nodes --stitch-edge decimated --out data/generated/ntw/terrain/joint_ue_local_v1
python tools/ntw/ue_gate/prepare_gate_inputs.py
python tools/ntw/ue_gate/run_gate.py build
python tools/ntw/ue_gate/run_gate.py runtime --mode full
python tools/ntw/ue_gate/run_gate.py runtime --mode followup
python tools/ntw/ue_gate/analyse_runtime.py
python tools/ntw/fragment_scan.py && python tools/ntw/fallback_eval.py
python tools/ntw/building_cell_shard_test.py
python tools/ntw/battlefield_compare.py
python -m pytest tests/test_ntw_phase2b.py tests/test_ntw_runtime_gate.py
```
