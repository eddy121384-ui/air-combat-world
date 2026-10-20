# North Taiwan Forest — Performance Recovery v1（保留 PR #49 畫面，降低森林成本）

日期：2026-10-20 · 分支 `perf/ntw-forest-distance-optimization`（自 PR #49 `feat/ntw-forest-distance-layer-lookdev-v1` @ `7d4058c`）· worktree `air-combat-world-ntwforest-perf`
同一張地圖、同一片陽明山、同一套 PR #49 地形材質／地形皮膚／遠山色彩／大氣；沒有新樹種、沒有改 Golden、沒有新的森林引擎。**Draft，勿 merge。**
主機：Intel UHD 770 內顯，1080p，未封裝 `-game`。**所有數字只代表這台內顯；手機與獨顯 PC NOT TESTED。**

## 0. 結論

| | PR #46 樹木配置* | PR #49 | **本輪** |
|---|---:|---:|---:|
| 飛越 GPU 中位（固定步長，內容完整） | 354.7 ms | 603.5 ms | **274.0 ms（−55 % vs #49，−23 % vs #46 配置）** |
| 飛越 GPU p95 | 490.9 ms | 868.8 ms | **376.6 ms** |
| MRQ 117 s 飛越 1080p 渲染時間 | — | 2,878 s | **1,503 s** |
| 240 m/s 即時飛越 WP 串流 | — | 後段 Slow→Critical（含阻塞載入） | **全程 Good**（僅航線起點從靜態鏡頭切換的恢復事件） |
| 畫面 | — | 基準 | 10 個同視角幾乎一致；2–3 km 稜線 3D 樹帶略稀（§4） |

\* 「PR #46 樹木配置」= PR #49 的地形／大氣不變，只把樹木距離、WPO 冠團、WP 範圍恢復成 PR #46（任務指定的關鍵 A/B）。
即時（UHD 770、內容實際有載入）飛越約 6 fps。手機與獨顯 PC **NOT TESTED**。

## 1. 量測方法（為什麼不用 PR #46 / #49 的即時數字比較）

- 先前的效能數字是即時播放：在這台內顯上 World Partition 串流跟不上 240 m/s，**沒載入的樹不花 GPU**，所以即時 GPU 中位數被「缺內容」低估（例：同一個最終配置，串流落後時 72 ms、串流正常時 120 ms）。
- 本輪 A/B 一律用**固定步長**（`-benchmark -fps=15`）：每個配置渲染完全相同的影格，引擎會等內容載入，量到的是「內容完整」時的真實成本。序列 = 3 個代表鏡頭（各 4 s）＋完整 117 s 英雄航線，CSV `GPUTime` 取飛越段 1,750 格的中位與 p95。
- `GPU/<pass>` 分項在重負載下會停止更新（PR #31 已記錄），只當參考；結論只用總 `GPUTime`。
- 串流另做即時執行，記錄 `LogWorldPartition: Streaming performance changed` 事件落在航線上的時間。
- 工具：`tools/ntw/forest_world/run_ab.ps1`（配置 → 固定步長量測）、`adapters/unreal/ntwforest/nf_perfcfg.py`（不重建地圖切換 MPC／WP 範圍／地形材質）、`ab_passes.py`、`streaming_events.py`。

## 2. 關鍵 A/B 與瓶頸分析（固定步長，飛越 GPU 中位）

| 標籤 | 配置 | GPU 中位 | p95 |
|---|---|---:|---:|
| `c49` | PR #49 原樣 | 603.5 | 868.8 |
| `c46t` | PR #46 樹木距離（450 m／2.4 km，無冠團，cull 2.6 km，WP 3.2 km），PR #49 地形 | 354.7 | 490.9 |
| `f_tail` | PR #49 但尾端 2.4 km（cull 2.6 km） | 362.7 | 490.3 |
| `f_land` | `c46t` + 舊地形材質（PR #46 R6） | 355.3 | 487.4 |
| `c49_vel0` | PR #49 + velocity 關 | 530.2 | 763.7 |
| `van_vel0` | + 消失樹頂點壓扁 | 525.7 | 745.8 |
| `..._ez1` / `..._lod15` | + EarlyZPass=1 / + LOD 距離 ×1.5 | 527.7 / 526.3 | 746.5 / 749.3 |
| `band` / `band_vel0` | + 依消失順位分段剔除（PR #49 曲線不變） | 402.4 / 349.3 | 520.8 / 460.8 |
| `t28` | + 尾端 2.8 km（否決：2–3 km 樹帶變薄） | 263.5 | 387.1 |
| `t34c` / `t34l` | 尾端 3.4 km + 保覆蓋加寬 / 線性冠團，WPO 邊界 12 m | 368.1 / 366.8 | 516.2 / 513.1 |
| **`t34l7`** | **尾端 3.4 km + 線性冠團 + WPO 邊界 7 m（採用）** | **274.0** | **376.6** |

另一個瓶頸在最後才找到：材質的 `max_world_position_offset_displacement` 會放大每棵樹的包圍盒，讓更多樹通過視錐與陰影 cascade 剔除。12 m → 7 m 省 ~93 ms（`t34l` → `t34l7`）；PR #49 的 9 m 也有部分同樣的成本（未單獨拆分）。保覆蓋加寬（`nf_trees_cover.py` cover 模式）反而更貴（加寬的存活樹把稀疏化省下的葉卡面積又加回去），未採用，保留為證據。

瓶頸依序：
1. **遠環的「已消失樹」仍被送進 GPU（最大）**：每棵樹的消失距離寫在材質裡，但 HISM 只能用一個距離剔除整個 component，所以 2.6→4.3 km 環裡 80–90 % 已溶解的樹仍全部送進頂點著色。PR #49 只把尾端從 2.4 延到 4 km，就多了 ~240 ms（`f_tail` 363 vs `c49` 604）。
2. **WPO 讓所有樹多畫一次（velocity pass）**：PR #49 樹材質加了 WPO，TSR 因此把每棵樹再畫進 velocity buffer；關掉 vertex-deformation velocity 省 ~70 ms（604 → 530；樹改進 depth prepass，所以不是全省）。
3. 不是瓶頸：近景 1 km 滿密度（`f_tail` 363 ≈ `c46t` 355）、新地形材質（`f_land` 355 = `c46t` 355）、EarlyZ 設定、LOD 距離（皆 ±2 ms）、頂點階段把消失樹壓扁（只省光柵化，總時間不變 → 代表是頂點／實例送出受限）。

## 3. 採用的修正（皆為既有 UE 機制）

1. **依消失順位分段剔除（rank-banded HISM culling）** `nf_trees_band.py`：每棵樹的消失順位 r 存成 per-instance custom data；材質（像素淡出與頂點 WPO）改讀這個 r；每個 tile 的樹依 r 分成 4 個 HISM，各自的 end cull = 該段最後一棵樹的消失距離 + 淡出寬 + 100 m。**畫面上每棵樹出現與消失的位置規則不變，只是不會再送出已經看不到的樹。**
2. **velocity**：`r.Velocity.EnableVertexDeformation=0`（專案 ini）。樹的 WPO 只隨距離緩慢變化，用相機運動重建的速度就足夠。
3. **尾端 4 → 3.4 km，冠團維持 PR #49 線性公式，WPO 包圍盒邊界 9 → 7 m** `nf_trees_cover.py`（`ACW_NF_CLUMP_MODE=linear`、`ACW_NF_MAXWPO_CM=700`）：3.4 km 以外原本只剩 ~5 % 的 3D 樹，交給 PR #49 的林冠層與林冠殼；7 m 足以容納冠團最大位移（~6 m）。WP 載入範圍 4.6 → 3.9 km。
4. **消失的樹在頂點階段壓到 pivot** `nf_trees_vanish.py`：零畫面變化，省光柵化（單獨看總時間沒變，保留因為無副作用且搭配分段剔除）。
5. **串流預算**（專案 ini `[ConsoleVariables]`）：`s.AsyncLoadingTimeLimit 15`、`s.LevelStreamingActorsUpdateTimeLimit 15`、元件註冊粒度 40、`wp.Runtime.MaxLoadingStreamingCells 8`。內顯上每格 100+ ms 時，預設的每格數毫秒預算撐不起 240 m/s 的 tile 進出。

沒有採用：降解析度、改 EarlyZ、LOD 偏移（量不到效益或傷畫質）；2.8 km 尾端版本（GPU 263 ms，但 2–3 km 稜線的 3D 樹帶明顯變薄，見 §4）。

## 4. 畫面（同視角 Before／After，原生 MRQ 1080p）

- `docs/evidence/ntw/forest_world_perf/before_after/ba_*.jpg`：PR #49 的 10 個鏡頭，左 = PR #49 提交的截圖，右 = 本輪。`ba_all.jpg` 總表。
- `mid_band_crop_*`：2–3 km 帶的原始像素裁切。`mid_band_crop_layers_north_PR49_top_vs_t28_REJECTED_bottom.jpg` 是被否決的 2.8 km 版本（稜線 3D 樹帶變薄）；`..._vs_final_bottom.jpg` 是採用版本（樹帶與稜線鋸齒恢復，左側稜線略稀於 PR #49）。
- 飛越：`fly_optimized_1080p.mp4`（同航線 117 s，原生 MRQ）、`fly_before_after_side_by_side.mp4`（左 PR #49、右本輪），`stills/flight_f*.jpg`；`flight_temporal_check.json`：3,518 個影格轉換 0 個跳變尖峰。

## 5. 串流（即時，240 m/s，同航線）

| 執行 | 設定 | 飛越串流 | 即時 fps 中位 |
|---|---|---|---:|
| `rt_band` | 分段剔除、WP 4.6 km、預設串流預算 | Slow → Critical → **Immediate（阻塞）** 反覆 | 7.7（內容缺） |
| `rt_t28` | WP 3.4 km、預設預算 | 同上 | 13.2（內容缺） |
| `rt_t28_stream` | + 串流預算 | 一次 1.5 s Slow 後恢復 | 8.2 |
| **`rt_final`** | 採用配置（WP 3.9 km + 串流預算） | **全程 Good** | 6.0 |

`streaming_*.json` 有每個事件的時間。即時 fps 會因為「樹沒載入」而虛高，所以只拿來判斷串流，不拿來比 GPU。

## 6. 限制

- 只量 UHD 770；手機（行動渲染器、ASTC、ES3.1）與獨顯 PC **NOT TESTED**。行動檔需重新決定尾端與串流預算。
- 固定步長與即時數字不可直接比較（§1）；即時 fps 在這台內顯上仍只有個位數到十幾。
- 分段剔除讓 HISM 元件數 4,454 → 17,351；串流預算因此必須提高。封裝版（cooked）的載入成本未量。
- 遠處冠團加寬是頂點位移，不是 impostor／HLOD。
- 單次量測、單一主機；先前經驗同主機跨 session 漂移數 ms。

## 7. 重現（UE stage 依序；`tools/ntw/forest_world/run_nf.ps1`）

```text
nf_sequence.py   ACW_NF_VIEWS=views_perf.json ACW_NF_SEQ_SUFFIX=_P ACW_NF_STILLS_TOO=1 ACW_NF_PERF_HOLD_S=4   # 3 stills + flight perf sequence
nf_trees_vanish.py                                                                                   # vanish collapse (vertex)
nf_perfcfg.py    ACW_NF_CFG={"mpc":{"NearFull":100000,"ThinEnd":340000,"FadeWidth":15000,"ThinGamma":2.2,"ShellStart":120000,"ShellEnd":300000,"ClumpGain":0.7},"wp_range_cm":390000}
nf_trees_band.py                                                                                     # rank custom data + 4 cull bands from the MPC curve
nf_trees_cover.py ACW_NF_CLUMP_MODE=linear ACW_NF_MAXWPO_CM=700
unreal/TreeLookdev/Config/DefaultEngine.ini: r.Velocity.EnableVertexDeformation=0 + [ConsoleVariables] streaming budget
A/B: run_ab.ps1 -Plan ab_plan_*.json ; ab_passes.py ; streaming_events.py <run> 3 4
```
