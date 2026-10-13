# 北台灣白模 Phase 2B-C — Seam Collision & LOD Runtime Closure

日期：2026-10-13 · 分支：`feat/ntw-phase2b-seam-lod-closure`（自 PR #25 HEAD `f25d260`，PR base = `feat/ntw-phase2b-runtime-gate`）
回應：Sophira Review #5501430227（PR #25）。範圍：**同一個隔離的兩 Cell UE 5.8 場景**（`D:/Users/EDDY/UEIsolated/NTWRuntimeGate`）。
**未做**：全北台灣、任何新的生產 fallback 啟用、正式信義區修改、正式 UE 專案修改、Merge。建築資料缺口維持 BLOCKED。
硬體：i7-12700 + Intel UHD 770 內顯（桌機 PIE，**不是手機**）。所有 Runtime 數字為 UE 5.8 PIE 實測。

標記：**MEASURED** 引擎實測 / **NOT TESTED** 未測 / **PROPOSED** 提案未套用。

---

## 0. 結論（Gate 判定）

| 項目 | 結果 |
|---|---|
| ① 信義 Landscape/Stitch 交界碰撞（查詢） | **PASS（加僅碰撞 flange）**：主 trace 66,445 條 **0 未命中**（基線 26）、微偏移 11,200 條中**正好在邊界線上的 1,600 條 0 未命中**（基線 **562**）、高速 sweep 7,920 條 **0 未命中**（基線 1）、錯誤 Actor 0、網格誤差 ≤ 0.2 mm、Landscape ≤ 2.5 mm、接縫連續 ≤ 3.3 mm。5 cm 與 10 cm flange 結果相同 |
| ①b 動態物理（10 cm 球） | **FAIL（如實保留）**：控制點（邊界內外各 1 m）0 穿透；100 m/s 無 CCD 時**到處**穿透（含控制點 28/28 = 一般穿隧，與接縫無關），開 CCD 後 0 穿透。正好落在邊界線上的 3 m 掉落：無 flange 2/28（east@0.10、south@0.55，兩輪相同），加 flange 後 east@0.10 消失，**south@0.55 仍 1/28（兩輪）**，根因未找到（§3.5） |
| ② Stitch 與 Chunk LOD 一致性 | **PASS**：改為**所有 LOD 共用同一個洞**（對齊最粗 LOD 320 m 格），stitch LOD k = 該 LOD 格網裁到信義邊、洞邊兩側加 skirt。**全部 25 種 stitch×chunk 強制 LOD 組合 0 裂縫 px**（PR #25：最大 204 萬 px） |
| ②b Chunk 與 Chunk 混合 LOD（新發現） | **PASS（修正後）**：棋盤式 LOD 0/2 原本 679 px（每塊 skirt 只覆蓋自己 LOD 誤差；較細一側邊緣較高時無人覆蓋）→ skirt 改為「本塊與 8 鄰塊最粗 LOD 誤差 ×2 + 0.5 m」後 **0 px**（4 種棋盤組合） |
| ③ Landscape 邊界 / 內部 component LOD | **FAIL（大幅改善，殘留極少）**：硬性 ForcedLOD 仍在內部 component 交界留 8 px；`SetLODBias` **無效**（與不設定完全相同）；改用 Landscape **LOD 分佈**（`LOD0DistributionSetting`/`LODDistributionSetting` ×16/×64）後 13 支接縫攝影機 0 px、自動 LOD dolly（6 路徑 × 30 步）由 32 px → 5 px、300 m/s 裂縫模式飛行 3 → 0 px（×64）。殘留 5 px 為 2–3 km 外陡坡上的單像素針孔，×16 與 ×64 相同 → **非 Landscape LOD 造成**（兩個獨立網格共邊的光柵化漏點），加 render apron（v6）後 dolly ×16/×64 由 5 → **1 px**（180 張中 1 個像素，東南角）、300 m/s 裂縫模式飛行 ×16/×64 **0 px**；嚴格 0 px 門檻下仍判 FAIL |
| ④ 建築 float32 fallback | **不批准進生產**（維持 OFF）。10 個修復前後幾何逐一檢查並分類，提出可審核限制：AUTO 4 / EXCEPTION 6 / REJECT 0（§5）。3.72 m = 外凸零寬髮絲；0.2745 m = 向內零寬切縫；「中庭數變化」= 中庭仍為空、但在零寬捏點彼此相連或連到外部（拓撲變化） |
| 退化來源 / 跨提供者重疊 | **不建立全域刪除政策**；各寫一份 case 文件（PROPOSED，未套用，§5.3） |
| P1：乾淨的端到端 runner | **PASS**：configured 場景完整 session `COMPLETED`、編輯器 exit code **0**（`runtime_closure`） |
| 效能（僅記錄） | 桌機 iGPU：LOD 分佈 ×16/×64 使 frame p50 約 +1.5–2 ms（55.7 → 57.6 ms）；串流 configured grid 不變。**手機 NOT TESTED** |

---

## 1. 這輪的引擎場景

| 項目 | 內容 |
|---|---|
| 地形 run | `joint_ue_local_v3`（固定洞）→ `v4`（+ 鄰塊 skirt）→ `v5`（+ 信義邊 skirt 20 m）→ `v6`（+ render apron）；碰撞網格四版相同 |
| 碰撞 | 每個 chunk 與 stitch 使用**只含地表**的 complex collision mesh（`*_col.glb` → `ComplexCollisionMesh`）；skirt 永遠不參與碰撞 |
| Flange | `xinyi_flange_w10/w05.glb`：信義邊兩側各 10 / 5 cm，**精確**取自引擎 Landscape 三角化（對角線 A）與 stitch LOD0 三角形並裁到帶狀區域；隱藏、只碰撞。離線驗證 24,000 點：覆蓋 100 %、高度誤差 ≤ 0.29 mm |
| 物理探針 | 28 顆 10 cm 球（Movable），每批重設速度；邊界線上 / 內 1 m / 外 1 m；3 m 自由落下與 30 m + 100 m/s；CCD 關 / 開；兩輪交錯順序 |
| 執行（全部 `COMPLETED`、編輯器 exit 0） | `runtime_closure`（v3 完整 configured；其中碰撞 / 物理已被下列取代）、`runtime_physics_c3`（**最終碰撞配置**：v5 + 精確 flange）、`runtime_physics`（乾淨計時）、`runtime_probe_points`、`runtime_closure_lod_v4/v5/v6`（v5/v6 使用與 v4 相同期望面的 inputs，runner 標籤顯示 v4；關卡依 `build_v5f` / `build_v6`） |

### 1.1 本輪過程中發現並修正的問題（保留為證據）
1. **第一版 flange 是直線帶**（3.97 m 邊頂點之間線性內插）：查詢 0 未命中但打到 flange 時高度誤差 0.15–0.18 m（> 5 cm 門檻）→ 改為精確裁切（≤ 0.3 mm）。
2. **物理測試的狀態殘留**：第一輪未重設速度，前一批 −100 m/s 的速度帶到下一批 → 數字混亂；修正後加入控制點與兩輪交錯。
3. **skirt 參與碰撞**：skirt 是單面垂直牆，被假設為球被推入 Landscape 的原因 → 改用只含地表的碰撞網格（south@0.55 仍穿透，證明不是主因，但 skirt 不碰撞本身是正確的生產做法）。
4. **同時跑離線 CPU 工作污染了計時**（p50 90–100 ms）→ 另開乾淨計時 session（55–58 ms）。
5. **裂縫偵測的兩種假陽性**：dolly 相機到測試區外時看見地形外緣底下的偵測平面；飛行時 8 km 載入範圍外的 Cell 未載入、看見平面 → 分析中各自分類排除（`under_test_area_edge`、`beyond_loading_range`），**不算裂縫也不隱藏**，數字都保留在 JSON。後者是本 pilot 沒有 HLOD / 遠景的真實限制。

## 2. ② Stitch 與 Chunk 的 LOD 一致性（MEASURED）

PR #25 的洞是「每個 LOD 各自挖」（`outline.buffer(s)`），所以 stitch LOD ≠ chunk LOD 時兩者覆蓋的面積不同 → 面積型破洞，skirt 無法補。

修正（`build_terrain_cells.py --stitch-hole fixed`，預設仍為舊行為）：
- 固定洞 = 與信義外框（外擴 20 m）相交的 320 m 格之聯集：E 305,280–308,160 / N 2,768,320–2,771,200（8.29 km²，環帶寬 98–363 m）。
- chunk：中心點落在洞內的三角形移除（每個 LOD 同一個洞）。
- stitch LOD k：洞內的 LOD-k 格網減去信義區；離開信義邊的完整格保留 chunk 對角線，被信義邊穿過的格合成一條帶、用 GEOS CDT 三角化，**頂點只有格點與 2,520 個信義邊頂點**（不產生新頂點）。
- 洞邊兩側（stitch 與 chunk）雙面 skirt，深度 = 2 × 任一 LOD 洞邊折線相對 20 m 節點的最大偏差 + 0.5 m = **145 m**（LOD4 在象山側偏差 72 m）。
- 離線 QA（`data/ntw/terrain/stitch_v3_qa.json`）：每個 LOD 2,520/2,520 信義邊頂點與線段、高度誤差 0、其他頂點都等於 chunk 頂點、五個 LOD 的 stitch 足跡**完全相同**（對稱差 0 m²）。

引擎（13 支接縫攝影機 × 25 種強制組合，Landscape 全 LOD0 以隔離此接縫）：**0 px / 325 張**。圖：`docs/evidence/ntw/runtime_closure/v6_stitch_x_chunk_{corner_SE,edge_south_250m}.png`；棋盤：`v3_chunk_checkerboard.png`（679 px）vs `v6_chunk_checkerboard.png`（0 px）。

### 2.1 Chunk 與 Chunk（新發現）
棋盤式強制 LOD（相鄰 chunk 差 2 級）在 v3 出現 679 px（LOD 0/2）與 73 px（0/4）。原因：每塊 skirt = 2 × 自己這個 LOD 的誤差；較細那塊的邊緣比較粗的鄰塊高時，細塊自己的 skirt（最小 2 m）不夠深。修正（`--neighbour-skirts`）：skirt = 2 × max(本塊與 8 鄰塊在最粗 LOD 的誤差) + 0.5 m（中位 190 m、最大 243 m；垂直、在地表下、不碰撞）→ **0 px**。

## 3. ① 交界碰撞（MEASURED，最終配置 `runtime_physics_c3`）

### 3.1 兩組數字都列出（依 Review 要求）
| 測試 | 無 flange（基線） | 5 cm flange | 10 cm flange |
|---|---:|---:|---:|
| 主 trace 66,445 條：未命中 | **26**（全在邊界線上） | 0 | 0 |
| 微偏移 11,200 條：**正好在線上的 1,600 條**未命中 | **562** | 0 | 0 |
| 微偏移：偏離 ≥ 0.5 mm 的 9,600 條未命中 | 0 | 0 | 0 |
| 高速 sweep 7,920 條（線 / 0.05 m / 0.5 m 球，5 / 10 m 每幀）未命中 | 1 | 0 | 0 |
| 錯誤 Actor | 0 | 0 | 0 |
| 打到 flange 時高度誤差（網格） | — | ≤ 0.3 mm | ≤ 0.2 mm |
| 接縫連續（1 mm 間距 / 斜率無關殘差） | 2.7 mm | 3.3 mm | 3.3 mm |

sweep 起點一定在精確地表之上、終點一定在其下，穿越點正好落在信義邊界線上（四邊 40 點 × 4 方向 + 四角 8 方向；陡 / 擦地兩種剖面；300 m/s 在 30 / 60 fps）。

### 3.2 重疊碰撞的副作用
flange 與 Landscape / stitch 在 ±w 內是重疊（共面到 0.3 mm）的碰撞面。查詢會打到任一個（F 6,212 / L 13,161 / S3 16,102 等），高度一致；物理控制點在三種配置下都 0 穿透。建議生產用 **5 cm**（重疊面積減半，查詢結果相同）。

### 3.3 100 m/s 與 CCD
無 CCD：邊界 18/28、內 1 m 28/28、外 1 m 28/28 穿透 → **一般穿隧**（10 cm 球每物理步移動數公尺），與接縫無關。開 CCD：三組 **0/28**。生產規則：高速小物體（彈頭、碎片、墜毀判定）必須開 CCD 或用 sweep。

### 3.4 3 m 掉落（靜置）
控制點 0 穿透（兩輪、三種配置）。邊界線上：無 flange 2/28（east@0.10、south@0.55）→ flange 後 1/28（south@0.55，兩輪都在）。

### 3.5 south@0.55 的調查（未解決）
- 球先停在比地表高約 0.20 m 處，接著往信義內側（西北）滾動，於邊界內約 0.26 m 處逐漸沉入 Landscape。
- 同一沿邊位置、內 1 m 的控制球正常停住；skirt 已不參與碰撞；精確 flange 在該點的垂直 trace 打到 F、高度 14.789 m（正確）；水平 trace 在 2–30 cm 高度只碰到正常地表坡（約 15 %），**沒有凸出物**。
- 結論：根因未定位（懷疑 Landscape heightfield 最外列與重疊碰撞面在動態接觸上的交互）。物理 Gate **FAIL**，列為下一輪 P0。

## 4. ③ Landscape 邊界 / 內部 component LOD（MEASURED）

| 政策 | 13 接縫攝影機（自動 LOD） | 自動 LOD dolly（6 × 30 張，排除測試區外假陽性） | 300 m/s 裂縫模式飛行 |
|---|---:|---:|---:|
| none | 0 | 32 px（信義接縫） | 3–4 px |
| border0（硬性 ForcedLOD 0） | 0 | 8 px（Landscape **內部 component 交界**） | — |
| bias（`SetLODBias -5`） | 0 | 37 px（= none，**無效果**） | 10 px |
| dist4 / dist16 | 0 | 5 / 5 px | 2 px（×16） |
| dist64 | 0 | 5 px | **0 px** |
| none + render apron（v6） | 0 | 8 px | 2 px |
| dist16 + render apron（v6） | 0 | **1 px**（東南角，2–3 km） | **0 px** |
| dist64 + render apron（v6） | 0 | **1 px**（同一點） | **0 px** |

- dist16 與 dist64 殘留相同（2–3 km 外陡坡上的單像素針孔）→ 不是 Landscape LOD；推測為兩個獨立網格共用邊（頂點非 bit-identical）造成的光柵化漏點。render apron：信義邊兩側各 0.5 m 的精確地表、下沉 2 cm、不碰撞（`xinyi_apron_w50.glb`）。
- 建議政策（PROPOSED）：信義 Landscape 的 `LOD0DistributionSetting` / `LODDistributionSetting` 提高（等同本測試的 ×16 以上），不用硬性 ForcedLOD、不用 LODBias；代價（桌機 iGPU）約 +1.5–2 ms。手機 NOT TESTED。
- 圖（提交子集）：`v6_dolly_auto_lod_cracks.png`（v3/v4/v5 圖表亦保留）、`v6_landscape_policy_auto.png`、`v6_dolly_south.png`、`v6_flight_configured_{none,dist64}_agl300_crackcap.png`、`v3_landscape_policy_auto.png`（bias 無效證據）。

## 5. ④ 建築：fallback 前後幾何審查（不批准進生產）

`tools/ntw/fallback_review.py` → `data/ntw/terrain/fallback_review.json`、`docs/evidence/ntw/buildings/fallback_before_after.png`。

### 5.1 分類方式
- 改變區域依**突出距離**（離剩餘輪廓多遠）分類：`edge_shift_sliver`（≤ 2 格 = 0.24 mm，邊只是平移不到一個量化格，長度再長也不改變外形）、`zero_width_spike`（突出更遠但沒有寬度 = 數位化髮絲）、`material`（有寬度）。
- 另列「遠離吸附後輪廓的來源頂點」：在外 = 外凸髮絲、在內 = 向內切縫。
- 中庭命運：自己仍是洞 / 在零寬捏點與其他洞相連 / 在零寬捏點連到外部 / 被填滿。

### 5.2 結果（PROPOSED 限制：髮絲 ≤ 0.10 m、Hausdorff ≤ 0.10 m、中庭拓撲不變才 AUTO；填滿 ≥ 0.5 m 內切圓的中庭或改變 > 0.01 m² 實體區域 → REJECT；其餘為具名 EXCEPTION 需審核簽核）

| 建築 | 面積 m² | Hausdorff | 主要變化 | 中庭 | 判定 |
|---|---:|---:|---|---|---|
| 125625 | 445 | 0.0001 | 邊平移 | 1 個退化洞（0 m²）在捏點開向外部 | AUTO |
| 167294 | 17 | 0.019 | 19 mm 外凸髮絲 | — | AUTO |
| 171665 | 284 | 0.0001 | 邊平移 | 2 個中庭在捏點相連 | EXCEPTION |
| 179103 | 991 | **0.2745** | **向內零寬切縫 0.27 m** | 3 個中庭不變 | EXCEPTION |
| 211054 | 0.000005 | — | 非最大碎片吸附後消失（入帳） | — | AUTO |
| 286126 | 320 | 0.0001 | 邊平移 | 2 個中庭在捏點相連 | EXCEPTION |
| 301157 | 137 | **3.7235** | **外凸零寬髮絲 3.72 m**（移除） | — | EXCEPTION |
| 353579 | 13 | 0.0007 | 0.7 mm 髮絲 | — | AUTO |
| 360929 | 586 | **1.5262** | 外凸髮絲 1.53 m | **4 個中庭在捏點相連成 1 個環** | EXCEPTION |
| 361019 | 407 | 0.0001 | 邊平移 | 3 個中庭在捏點相連 | EXCEPTION |

所有中庭都仍為**空**（沒有被填滿），但「中庭數」在拓撲上改變（捏點相連）；髮絲 / 切縫面積 ≈ 0。這 6 個 EXCEPTION 必須個別審核；在 locked representative / full-Xinyi **實際**回歸跑過之前不考慮任何 opt-in。

### 5.3 Case 文件（PROPOSED，未套用）
- `tp_building_height.307096` 第 1 個 part：85 頂點、自相交、shoelace 面積 0.0028 m²、範圍 1.04 × 1.59 m；`make_valid` 碎成 23 塊共 0.0029 m²（最大 0.0005 m²）；緊貼第 0 個 part（真正的建築，正常輸出）。提案：**僅此 ID** 以 `degenerate_zero_area_outline` 入帳拒絕，或請資料方確認；**不**建立 `source_area==0` 全域規則。（更正：PR #25 文件寫「來源面積 0.0 m²」是兩位小數四捨五入，實為 0.0028 m²。）
- Overture `548d8e29…`（447.3 m²，質心在新北）與 4 棟台北 WFS（共 131.5 m²）重疊 131.2 m²；Overture 在 WFS 之外還有 **316.2 m²** 合法覆蓋（其中 91.8 m² 位於台北界內）。選項：A 保留兩者（重複 131 m²）/ B 以擁有者 WFS 裁切 Overture（保留 316 m²，需裁切 + 嚴格重驗證路徑）/ C 抑制 Overture（失去 316 m²）。提案：此對採 B（目視確認後），**不**做全面抑制。
- Cell A 11.76 km² Overture 快取缺口：維持 BLOCKED。

## 6. NOT TESTED / 下一 Gate
1. 物理：south@0.55 根因（Landscape 最外列 heightfield × 重疊碰撞的動態接觸）；更多邊界點、不同半徑。
2. 殘留針孔（v6：dolly 1 px）：讓 stitch 信義邊頂點與 Landscape 邊界頂點在引擎中 bit-identical（同一 transform 計算），或把 apron 下沉量 / 寬度做參數掃描；接受門檻（例如「≤ 1 px / 180 張」）需審查決定，本輪不自行放寬。
3. 正式生產前：Landscape LOD 分佈屬性落到信義 Landscape、手機 packaged build 計時、HLOD / 遠景（8 km 外目前無地形）。
4. fallback：locked representative / full-Xinyi 實際回歸；6 個 EXCEPTION 個別審核。

## 7. 重現
```bash
python tools/ntw/build_terrain_cells.py --cells C+0038+0346 C+0038+0345 --identity-nodes --stitch-hole fixed --collision-meshes --out data/generated/ntw/terrain/joint_ue_local_v3
python tools/ntw/build_terrain_cells.py --cells C+0038+0346 C+0038+0345 --identity-nodes --stitch-hole fixed --collision-meshes --neighbour-skirts --stitch-skirt-m 20 --out data/generated/ntw/terrain/joint_ue_local_v5
python tools/ntw/ue_gate/build_collision_flange.py --run joint_ue_local_v5 --apron
python tools/ntw/terrain_qa.py --stitch-run joint_ue_local_v3 --out data/ntw/terrain/stitch_v3_qa.json
python tools/ntw/ue_gate/run_gate.py build --terrain-run joint_ue_local_v5 --v1-run none --tag _v5f
python tools/ntw/ue_gate/run_gate.py runtime --mode physics --tag _c3 --inputs gate_inputs_v3p.json
python tools/ntw/ue_gate/run_gate.py runtime --mode closure_lod --tag _v6 --inputs gate_inputs_v4.json
python tools/ntw/ue_gate/analyse_closure.py
python tools/ntw/fallback_review.py
python -m pytest tests/test_ntw_seam_lod_closure.py tests/test_ntw_runtime_gate.py tests/test_ntw_phase2b.py
```
（`ACW_GATE_TERRAIN_RUN_NAME` 選擇 `prepare_gate_inputs.py` 的期望面所用的 run；`ACW_GATE_LAND_POLICIES` 選擇 closure_lod 的 Landscape 政策。）
