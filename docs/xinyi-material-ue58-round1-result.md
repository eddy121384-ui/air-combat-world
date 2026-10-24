# 信義區建築遮罩：Windows UE 5.8 首輪實機 A/B

2026-10-24：完成 **7 組同鏡位 A/B、14 張原始 UE PNG**，另保留第一張基準測試圖。場景已在隔離環境恢復；美術驗收仍待審。本輪沒有完整 Cook、城市幾何／地形重建或 PR merge，也沒有手機效能驗證。

審圖入口：[三張手機用左右 A/B JPEG 與三組 1:1 無損細節裁切](evidence/xinyi-material-ue58-round1/review/README.md)。左為 Baseline、右為 New Materials，兩側全幅同為 40% 顯示比例；JPEG 分別約 189／147／302 KB。細節裁切保留原始像素、不縮放、不強化。這次預覽整理沒有啟動 UE 或修改材質，全部 14 張 A/B 原始 PNG 與首張基準 PNG 均逐位元組不變；[來源、座標及核對紀錄](evidence/xinyi-material-ue58-round1/review/manifest.json)可供重查。

執行環境是 Windows 本機 UE **5.8.0 / CL 55116800**、D3D12、Intel UHD Graphics 770（驅動 31.0.101.4502）。隔離 worktree 位於 `C:\Users\EDDY\Desktop\M1A2\xinyi-material-ue58-round1`，分支 `test/xinyi-shared-masks-ue58-round1`，以視覺分支 `ede7960d8ec05b2aa521b1e4c65b5bbd667c456d` 為基礎。

**原始 D 槽專案確實可恢復。** 只讀調查 `D:\Users\EDDY\Documents\GitHub\air-combat-world` 後，確認 `Content/XinyiV2` 有 32 個檔案，包含 Contract、WP 地圖與 25 個 Runtime Tile meshes；`__ExternalActors__` 有 32 個 WP 外部 Actor 檔案。正式 `Content/XinyiLook` 目錄已缺失，`__ExternalObjects__` 不存在。`Saved/XinyiLook` 約 832 MiB，仍有 Look GLB、樹木／屋頂配置與舊 PASS receipts；`Saved/XinyiHostGates` 亦保留先前的 streaming／collision／source-immutability 紀錄。舊 PASS 只作歷史證據，本輪另外啟動 UE 檢查複本：成功載入 25 個 Runtime Tiles 和 25 個 Landscape components，未存檔；該 NullRHI 依賴檢查沒有產生截圖。

恢復採用 **243 個既有輸入的實體複本（228.58 MiB）**，不使用 hardlink 或 junction。缺少的 8 張衍生 PNG 為 ground／ground-light／campus、sign／shop／storefront-plan、far-city、wall-ad；只補回資料貼圖，GLB、地形、樹木與屋頂配置保持原始位元組。sign、shop、storefront-plan、wall-ad 的 PNG SHA-256 與舊紀錄完全一致；其餘四張沒有可供比對的歷史 PNG hash，已記錄本輪輸出 hash。依賴只安裝在本輪 `.capture-python`，不改全域 Python。

之後沿用 `xinyi_look_build_assets.py`、`xinyi_look_build_level.py`，從現有 GLB 重建缺少的衍生 UE 資產與 Look 地圖；沒有執行 `build_all.py`、建築 extrusion／triangulation 或地形生成。`PASS_LOOK_ASSETS`、`PASS_LOOK_LEVEL` 及新程序 reopen/capture 均通過。正式幾何、樹木來源和原始 CC 工作檔沒有改寫。測試後，D 槽原始檔及其隔離輸入複本共 243 筆 SHA-256 全部一致；D 槽恢復前後剩餘均為 47,430,725,632 bytes（約 44.17 GiB），產物寫入 C 槽。

PR #62 固定在 `b0e00f2256bfe67ba76798d73450fa3c5412930f`，其 PR #14 基底為 `6c2feb1611a3d07436c8222c3b67246a9b1ad8cd`。本分支只抽取兩張 512² packed PNG 與來源條件，沒有整批引入這兩個 PR 的修改。[輸入與通道雜湊](../assets/materials/xinyi/ue58_round1/source.json)及[來源條件](../assets/materials/xinyi/ue58_round1/PR62_SOURCES.md)均保留。

測試材質限定於 `/Game/XinyiMaterialAB`。兩張 Texture 已回讀核對 **sRGB OFF、TC_MASKS、compression_no_alpha=False、Wrap U/V、Simple Average mips**；RGBA 四通道均有非定值資料，Alpha 用作第四個控制通道。正式 HLSL 檔與 baseline `M_XinyiCity` 不改寫。32 m 尺度、每棟位移／U 鏡像、`V=-height` 的雨痕方向及華廈 0.6 權重只在獨立材質實驗中接入；每類表面一次完整 RGBA SampleGrad。只對 25 個 Look tiles 作暫時 component override，未儲存地圖；英雄建築、地形、樹木、學校及屋頂設備保留 baseline 路徑。

截圖後端完全沿用 `SceneCapture2D → RTF_RGBA8 → SCS_FINAL_COLOR_LDR → export_render_target`。A/B 均為 **1920×1080、白天、無雲、sg.*=2、ScreenPercentage=100、MotionBlur=0、RayTracing=0**。相機、實際 console 值、Look 地圖 hash 與 baseline 材質 hash 全部逐項相等。原始 harness 對唯讀 `r.RayTracing` 的設定會留下訊息，但兩輪回讀值都是 0。原始 PNG 只做逐位元組複製，沒有離線補畫、增強或用預覽圖代替實機圖。

請以 1:1 開啟原圖切換比較；兩個立面鏡位距離約 7.5 m，用來檢查表面，不代表飛行距離。最初被屋頂擋住／落在陰影的鏡位已在材質比較前調整，最終 A/B 使用同一份固定相機 JSON。

| 對象 | Baseline | New Materials |
|---|---|---|
| 老公寓 `tp_building_height.269873` | [老公寓 Baseline 原始 PNG](evidence/xinyi-material-ue58-round1/captures/baseline/walkup__day.png) | [老公寓 New Materials 原始 PNG](evidence/xinyi-material-ue58-round1/captures/candidate/walkup__day.png) |
| 華廈 `tp_building_height.270894` | [華廈 Baseline 原始 PNG](evidence/xinyi-material-ue58-round1/captures/baseline/huaxia__day.png) | [華廈 New Materials 原始 PNG](evidence/xinyi-material-ue58-round1/captures/candidate/huaxia__day.png) |
| 吳興屋頂，沿用既有鏡位 | [屋頂 Baseline 原始 PNG](evidence/xinyi-material-ue58-round1/captures/baseline/wuxing_roofs__day.png) | [屋頂 New Materials 原始 PNG](evidence/xinyi-material-ue58-round1/captures/candidate/wuxing_roofs__day.png) |

近景立面增加柔和的濕斑、修補明暗與粗糙度變化，窗格及招牌輪廓保留；改善幅度克制，尚不能把本輪稱為顯著整體畫質提升。吳興廣角場景以學校和設備為主，受本次遮罩影響的區域有限，遠景屋頂收益偏弱。兩張立面圖的平均 RGB 絕對差約 1.34／1.19（0–255），屋頂廣角約 0.084；這些數字只證明影像有改變，不是美術評分。

補拍的五個屋頂鏡位位於 east -12、-6、0、+6、+12 m，覆蓋 24 m。[四張位移圖及完整配對](evidence/xinyi-material-ue58-round1/captures/)保留原始相機設定。這些抽樣圖未見明顯新增接縫，但不足以排除 32 m 圖章感。立面雨痕按重力方向接入，未旋轉 90° 或鏡像 V；目前對比偏弱，沒有以定向診斷圖逐牆確認。**五張移位靜幀不是連續飛行影片，不能據此宣稱無閃爍。**

| Windows 同鏡位時間代理，每組 40 次 | Baseline median（P10–P90） | New median（P10–P90） | 差異 |
|---|---:|---:|---:|
| 老公寓 | 62.54 ms（60.98–65.32） | 62.84 ms（61.15–65.72） | +0.30 ms / +0.48% |
| 吳興屋頂 | 65.84 ms（64.41–70.17） | 67.15 ms（65.53–71.13） | +1.31 ms / +1.99% |

方法為一次 `capture_scene` 加一次 1-pixel readback 強制 GPU 同步的 wall time，包含 CPU、提交及 readback 固定成本；只有一輪最終 A/B，區間重疊，不作統計顯著、實際遊戲 FPS 或純 GPU 成本結論。桌面材質編譯器回報 pixel instructions **4410 → 4515（+105，約 +2.38%）**，samplers **4 → 6**，vertex instructions 仍為 146。Custom node 內的取樣不會可靠反映在 editor 的 `num_pixel_texture_samples` 欄位，不能把其 0 解讀成沒有 texture fetch。

保留了兩項失敗紀錄：第一次貼圖恢復在套件尚未完成安裝時啟動，輸入未變；第一次候選材質雖已編譯／存檔，但關閉 editor 時發生 `Object is not packaged: ModeManagerInteractiveToolsContext None`，exit 3。改用既有資產腳本的自動退出方式後，只重試一次，完整階段 exit 0；後續新程序載入與候選截圖亦 exit 0。[失敗 receipt](evidence/xinyi-material-ue58-round1/receipts/candidate-build-shutdown-failure.json)、[UE log 摘錄](evidence/xinyi-material-ue58-round1/logs/)與最終正常 receipt 均保留，沒有把初次失敗當作 PASS。

本輪未驗證 ASTC、手機 GPU／顯存／發熱、完整 Cook、打包遊戲、150／300／600／800 m 固定距離組、暮色及連續移動閃爍。下一步先由美術決定濕斑／修補強度與 32 m 重複是否可接受，再補固定距離與連續移動，最後於真機測 ASTC 和成本；仍不宜直接替換正式材質。

[完整量測與相同條件核對](evidence/xinyi-material-ue58-round1/summary.json) · [原始輸入不變驗證](evidence/xinyi-material-ue58-round1/receipts/source-immutability.json) · [本機 worktree／磁碟／程序快照](evidence/xinyi-material-ue58-round1/receipts/host-before-candidate-capture.json) · [第一張真實 UE 基準圖](evidence/xinyi-material-ue58-round1/captures/baseline-smoke.png)

本機回放使用 `tools/lookdev/run_xinyi_material_round1.ps1`。保有目前衍生資產時，只需依序執行 `-Stage baseline` 與 `-Stage candidate` 即可重拍，避免重新匯入。從空的同名隔離 worktree 恢復時，先以 `stage_xinyi_capture_inputs.ps1` 複製原始輸入，再設定 `.capture-python` 依賴路徑並執行 `restore_xinyi_look_textures.py`；接著依序執行 `assets → level → smoke`，通過真正基準截圖後才執行 `extract_pr62_material_inputs.py`，最後執行 `baseline → candidate-build → candidate`。`verify_xinyi_capture_sources.ps1` 和 `collect_xinyi_material_round1.py` 負責最後核對及原始截圖收集。這些工具刻意限制為本輪 C 槽隔離目錄，不能指向 CC 原始專案執行寫入階段。

離線恢復版本固定於 `requirements-xinyi-material-capture.txt`；可用 Python 的 `-m pip install --only-binary=:all: --target .capture-python -r requirements-xinyi-material-capture.txt` 安裝至隔離目錄，並將 `PYTHONPATH` 指向該目錄。Unreal 截圖本身使用 UE 內建 Python，不依賴這些離線套件。
