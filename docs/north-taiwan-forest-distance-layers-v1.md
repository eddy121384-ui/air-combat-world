# North Taiwan Forest — Distance-Layer LookDev v1（近景看森林，遠景看山形）

日期：2026-10-20 · 分支 `feat/ntw-forest-distance-layer-lookdev-v1`（自 PR #46 `feat/ntw-forest-integration-v1` @ `81669a3`）· worktree `air-combat-world-ntwforest-dl`
同一張地圖、同一片陽明山／大屯火山群（26.46 km 見方），**沒有新增樹種、沒有新的試驗場、沒有改 Golden 或 Xinyi**。主機 Intel UHD 770，UE 5.8。**Draft，勿 merge。**

## 0. 結論

| 距離 | 規則（任務） | 現在的做法 | 結果 |
|---|---|---|---|
| 0–1.5 km | 明確樹感：林冠團塊、樹種色差、稜線鋸齒、林緣 | 3D 樹**滿密度到 1.0 km**（PR #46：450 m），之後逐棵隨機消失 | 近景、稜線鋸齒、柳杉／闊葉色差都由 3D 樹構成 |
| 1.5–4 km | 單棵樹 → 林冠群塊，仍有覆蓋感 | 稀疏長尾到 4 km（γ 2.2）；存活的遠處樹以 WPO **水平加寬成冠團**（最多 1.7×，高度 1.25×）；地表林冠層 + 冠團尺度圖層；林冠殼 1.2→3 km | 2–4 km 稜線上仍有 3D 冠團與柳杉林塊輪廓，背後林冠層接手（`diagnostic/layers_north_mid_band_B0_vs_A3.png`） |
| 4–8 km | 森林色塊、草坡、裸地、地形明暗 | 林冠貼圖淡出（3.5→6 km），換成**巨觀林色**：依實際種下樹種比例（柳杉深藍綠、相思橄欖、闊葉）＋林分色調斑塊＋30 m 斑駁；草坡稜線金黃、谷地偏綠；陡峭開放坡露土 | 不再是細碎顆粒；色塊與明暗由地形與土地覆蓋決定 |
| 7–10 km+ | 主要讀成山形、稜線、谷地、空氣透視 | 巨觀色 → 山形調色（降飽和）＋**地形皮膚**全強度：稜線暖亮、谷地冷暗、D8 匯流溝紋、開闊度 AO；高度霧 1.5 km 後才開始、偏藍 | 遠山讀成大屯山群的山形與溝谷，不再是「長了毛的灰山」 |

**最大的單一改善（找到根因）**：PR #46 遠景（尤其逆光）看起來灰白光禿，不是霧也不是樹不夠——關掉高度霧的診斷渲染幾乎一樣（`diagnostic/backlit_fog_off_A2_vs_X1.jpg`）。真正原因是 Landscape **specular 0.18**：植被反照率很低（~0.02），掠射角的 Fresnel 天空反射蓋過了漫射，整片山變灰紫色。改成陸地 0.02、水面 0.5 後，逆光遠山立刻變成深綠山形、金山平原變回綠色農田（`diagnostic/backlit_spec018_A2_vs_spec002_X3.jpg`）。樹葉 specular 也同理由 0.18 → 0.10（只改世界用的 MI_NF，M_TL 原件未動）。

## 1. 做了什麼（皆重用 PR #46 管線）

1. **地形皮膚圖** `tools/ntw/forest_world/terrain_skin.py`（離線 18 s，與 Landscape 同一份量化高程）：`T_NF_Terrain` 2048²，R = 50/200/600 m 多尺度地形位置（稜線／谷地），G = 20 m D8 匯流累積（log，只取溝道：火山錐放射狀溝谷網），B = 坡度，A = 300 m 尺度開闊度。預覽 `terrain_skin_preview.jpg`。
2. **距離分層 Landscape 材質** `adapters/unreal/ntwforest/nf_landscape_dl.py` → `M_NF_LandscapeDL_R3`：四個距離帶（材質參數 FA0/FA1/FB0/FB1/SK0/SK1，可用 MI 調）、地形皮膚隨距離加強、遠處關掉林冠法線、陸地 specular 0.02。PR #46 的 `M_NF_Landscape_R6` 保留，作為 before。
3. **樹木分層** `nf_trees_dl.py`：MPC 預設改為 dl（滿密度 1 km、消失 4 km、γ 2.2、殼 1.2–3 km、ClumpGain 0.7）；六個 M_NF 樹材質加冠團 WPO（`LocalPosition × (g, g, 0.35g)` 轉世界，`max_world_position_offset_displacement` 9 m）；4,454 個 HISM end cull 2.6 → 4.3 km；WP 載入距離 3.2 → 4.6 km。
4. **大氣**：高度霧 1.5 km 後才開始、密度 0.0025、falloff 0.05、偏藍內散射；SkyAtmosphere Mie 0.0022 / 異向性 0.6（減少逆光白霧）。
5. **評估鏡頭** `dl_views.py`：PR #46 的 6 個鏡頭 + 4 個新的距離分層鏡頭（每張都跨 0–10 km）。

## 2. 前後對照（原生 MRQ 1080p，`docs/evidence/ntw/forest_world_dl/`）

- `before_after/ba_*.jpg`：10 個鏡頭，左 = PR #46 狀態（同一張地圖在改動前渲染），右 = 本輪；`ba_all.jpg` 總表。
- 重點看：`ba_08_dl_far_range`（逆光遠山：灰白 → 深綠山形＋空氣透視）、`ba_07_dl_layers_north`（同一畫面 0–10 km 四層）、`ba_04_agl200_qingtiangang`（草原金黃稜線、遠稜山形）、`ba_10_dl_datun_west`。
- `stills/01–10_*.jpg`：本輪原生截圖。
- 飛越影片：見 §3。

## 3. 飛越影片

- **`fly_distance_layers_1080p.mp4`**：與 PR #46 同一條航線、同一速度（117 s、28 km、240 m/s、離地 105–358 m），正常速度，原生 MRQ 1080p30（standalone `-game` 固定步長，48 min 渲染）。
- **`fly_before_after_side_by_side.mp4`**：左 PR #46、右本輪，同步並排（各 960×540）。
- `stills/flight_f*.jpg`：8 張飛越影格。`flight_temporal_check.json`：3,518 個影格轉換、**0 個全畫面跳變尖峰**（>3× 局部中位），延長到 4 km 的樹沒有造成可量到的跳變。

## 4. 效能（基本摘要；UHD 770、1080p、即時、未封裝、單次）

| | PR #46 PC 檔 | 本輪（dl 預設） |
|---|---:|---:|
| 飛越 GPU 中位 | 108.9 ms | **206.2 ms** |
| 飛越 frame p95 | 326 ms | 581 ms |
| 峰值 working set | 1.9 GB | 2.0 GB |
| iGPU 本地記憶體（飛越中位） | 0.79 GB | 0.86 GB |
| 240 m/s 即時飛越中的 WP 串流降級 | 無 | **有**：飛越約 37 s 起 Slow、48 s 起 Critical |

- 成本翻倍來自規則本身：3D 樹滿密度從 450 m 拉到 1 km、尾端從 2.4 km 拉到 4 km，載入範圍 3.2 → 4.6 km。地形材質多了 1 張圖、幾個運算，在無 HISM 基線（PR #46：33 ms）之上影響很小（未單獨量測）。
- 串流降級：這台內顯上每格 ~200 ms，240 m/s 即時飛行時 4.6 km 範圍的 tile 來不及載入。MRQ 固定步長渲染不受影響（影片 0 跳變）。
- 靜態鏡頭在這次只有 12–139 個影格、時間對齊靠推算，數字不可靠，不列出比較（原始資料在 `perf_uhd770_dl.json`）。
- **行動檔沒有重量**：PR #46 的 mobile MPC 預設（250 m / 1.1 km）仍可用，但它會把 1.5–4 km 帶交還給林冠層，等於行動版是「近景樹感較短」的版本；手機／獨顯 **NOT TESTED**。

## 5. 迭代紀錄

| 版本 | 改了什麼 | 看到什麼 |
|---|---|---|
| B0 | PR #46 狀態，新 10 鏡頭 | 逆光遠山灰白、遠景細碎顆粒、金山平原像沙漠 |
| A1 | 距離分層材質 + 地形皮膚 + 樹木分層 + 霧 1.5 km 起 | 遠山有山形與溝谷，但偏灰平；3,000 m 視角霧太重 |
| A2 | 巨觀林色加深加飽和、林分斑塊、皮膚加強、Mie 降低 | 改善有限，逆光仍灰白 → 做診斷 |
| X1 | 診斷：關高度霧 | 幾乎沒差 → 不是霧 |
| X3 | 陸地 specular 0.18 → 0.02 | 逆光遠山立刻變深綠山形 → 根因 |
| A3 | + 樹葉 specular 0.10 | 採用 |

## 6. 仍有的限制

- 只有陽明山一帶；區外無遠景地形（地平線外只有海）。
- 4–8 km 帶的林色斑塊來自雜訊與樹種比例，不是實測林分；柳杉／相思分布仍是 PR #46 的美術規則。
- 地形皮膚以 10 m 地形為準，20 m DEM 之下的微地形（岩壁、步道切面）不存在；溝紋在 4 km 內被樹蓋住，主要在遠景起作用。
- 冠團加寬是頂點位移，貼近地面的視角（< 50 m）不會出現（加寬只在 1 km 外開始）；陰影跟著加寬。
- **效能**：近景樹延伸到 1 km、尾端到 4 km，這台內顯上飛越 GPU 由 109 ms 變 206 ms，且即時 240 m/s 時 WP 串流跟不上（§4）。下一步：中距離（1.5–4 km）改用真正的 impostor／HLOD 冠團而不是加寬的 3D 樹、載入範圍分 grid（樹 2.5 km / 地形常駐）、封裝後在獨顯 PC 與手機實測。手機／獨顯 PC **NOT TESTED**。

## 7. 重現

```powershell
python tools/ntw/forest_world/terrain_skin.py data/generated/ntw/forest_world/v1
python tools/ntw/forest_world/dl_views.py data/generated/ntw/forest_world/v1
# UE (run_nf.ps1; env vars in the calling shell):
nf_sequence.py  ACW_NF_VIEWS=views_dl.json ACW_NF_SEQ_SUFFIX=_DL ACW_NF_STILLS_TOO=1      # 10 stills + flight + perf sequences
nf_trees_dl.py                                                                              # MPC dl preset, clump WPO, re-cull, WP range
nf_landscape_dl.py ACW_NF_LMAT_REV=3 (+ fog / atmosphere: ACW_NF_FOG_DENSITY=0.0025 ACW_NF_FOG_FALLOFF=0.05 ACW_NF_FOG_START_CM=150000
                   ACW_NF_FOG_COLOR=0.42,0.54,0.70 ACW_NF_ATM_MIE=0.0022 ACW_NF_ATM_MIE_ANISO=0.6 — applied in rev 2, persisted)
nf_leaf_spec.py ACW_NF_LEAF_SPEC=0.10
nf_autoplay.py ACW_NF_AUTOPLAY=0 ; nf_mrq_configs.py ACW_NF_MRQ_ONLY=LS_NF_Stills_DL|LS_NF_Flight_DL ; run_nf_mrq.ps1
python tools/ntw/forest_world/ba_sheet.py <before frames> <after frames> data/generated/ntw/forest_world/v1/views_dl.json <out>
```
Before 圖是同一張地圖在任何改動前（PR #46 狀態）以同一組 10 鏡頭渲染的（`nf_stills_dl_B0`）。
- 天氣、雲、季節、灌木地被未做（依任務範圍）。
