# North Taiwan Forest — Runtime Gate v1（封裝、載入、串流、連續高速飛行）

日期：2026-10-20 · 分支 `gate/ntw-forest-runtime`（自 PR #50 `perf/ntw-forest-distance-optimization` @ `7578b96`）· worktree `air-combat-world-ntwforest-gate`
主機：i7-12700 + **Intel UHD 770 內顯**、16 GB RAM、UE 5.8 安裝版。沒有新增森林功能、樹種或地圖範圍。**Draft，勿 merge。**

## 0. 結論

| 項目 | 結果 |
|---|---|
| Windows Cook／Package | **PASS**：BuildCookRun Development Win64、pak + IoStore，build → cook（815 packages）→ stage **18 min**，0 cook error、2 個無害 cvar 優先序 warning；staged 1.46 GB（內容 ucas 713 MB） |
| 封裝版實際啟動 | **PASS**：`TreeLookdev.exe` 直接進入 `L_NF_Yangmingshan`，**LoadMap 0.9 s**；地形（Landscape + 距離分層材質）、三種樹、建物、海面、World Partition 都在封裝版正常（`runtime_frames/`） |
| 240 m/s 連續飛越（117 s） | **串流 PASS**：飛越中 0 次 WP 串流降級、0 個 game thread > 50 ms 的影格；HISM 註冊成本 `AddToWorld` p99 **7.9 ms**（最大 11 ms）、AsyncLoading p99 4 ms |
| 300 m/s 連續飛越（`slomo 1.25`） | **串流 PASS**：同上，0 次降級，AddToWorld p99 5.8 ms |
| GPU（1080p，封裝版） | Epic 陰影（封裝預設）：飛越 GPU 中位 **397 ms（2.5 fps）**；Medium 陰影（`sg.ShadowQuality 1`）：**176 ms（5.6 fps）**，穩定飛行段 270 ms。差別幾乎全在 CSM 陰影深度（137 ms → 5 ms） |
| 記憶體 | 封裝版峰值 working set **2.0–2.6 GB**；LLM：`Meshes/InstancedMesh` ~480 MB（樹的 instance data）、StaticMesh 147 MB、Textures 140 MB、RenderTargets 156 MB；GPU scene 最多 **1.18 M instances** |
| 全域 velocity 設定 | **已改為逐元件**：17,351 個樹 HISM 設 `world_position_offset_writes_velocity=False`，移除 PR #50 的全專案 `r.Velocity.EnableVertexDeformation=0`；編輯器固定步長量測 282.6 ms（全域版 274.0 ms，誤差範圍內），velocity pass 1.3 ms |
| Android／iOS | **未能建置**（§5）：本機 UE 5.8 安裝版沒有 Android target platform（cook 只列出 Windows），沒有 Android SDK／NDK／JDK、沒有裝置；iOS 需要 Mac。以 ES3.1 行動渲染預覽在 PC 上檢查（§5.2） |

## 1. 開始前的資產保護

PR #50 worktree 未進版控的 UE 專案（Content 含 840 MB 外部 actor、Plugins、Config）與 `data/generated/ntw/forest_world`（地形 r16、遮罩、3.86 M 棵樹的 tile 資料、建物、林冠烘焙）打包到 **`C:\Users\EDDY\Backups\ntw-forest\20261020-pr50-7578b96\`**：
`TreeLookdev_project.tar.gz`（1.21 GB）、`forest_world_generated.tar.gz`（0.33 GB）、`manifest.json`（3,000 個檔案逐一 SHA-256 + 兩個封存檔的 SHA-256 + 來源 commit）。放在 C:（與所有 worktree 的 D: 分開）。資料本身也可由提交的腳本從官方 DEM／PR #39 土地覆蓋／Overture 重建（見 PR #46–#50 文件）。

## 2. 封裝（可重現指令）

UE 5.8 安裝版 + 本專案要點：
1. 專案啟用了非預設 plugin（Python、MRQ、GeometryScripting…），UAT 因此把它當成需要專案自己 target 的專案，`BuildCookRun` 一開始就找 `Binaries/Win64/TreeLookdevEditor.target` 而失敗。修正：`-unrealexe=<安裝版 UnrealEditor-Cmd.exe>` 讓 cook 用安裝版編輯器，`-build` 讓 UBT 連結專案的遊戲執行檔。
2. 專案內的 `XinyiLandscapeBridge`（只有 Editor module、預先編譯）在封裝時暫時移出專案資料夾（之後移回）；地圖裡只有標準 Landscape／HISM／Actor，不依賴它。
3. `GameDefaultMap` = `L_NF_Yangmingshan`；地圖內 `NF_PerfSequence` 自動播放（`nf_gate_prep.py`）。

```powershell
RunUAT.bat BuildCookRun -project=<...>\unreal\TreeLookdev\TreeLookdev.uproject -unrealexe="C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" `
  -noP4 -platform=Win64 -clientconfig=Development -build -cook -stage -pak -iostore -map=/Game/NorthForest/Maps/L_NF_Yangmingshan -unattended -utf8output
tools/ntw/forest_world/run_packaged.ps1 -Tag pk_sq1 -Frames 2400 -ExecCmds "r.VSync 0,sg.ShadowQuality 1"
python tools/ntw/forest_world/pk_analyze.py unreal/TreeLookdev/Saved/NorthForest/gate/runs <out.json> pk_sq1
```

## 3. 封裝版 Runtime 量測（即時、1080p、`-llm`、單次）

| 執行 | 速度 | 陰影 | 飛越 frame 中位 / p95 | GPU 中位 | 穩定段 GPU | fps | 飛越中串流降級 | AddToWorld p99 / max | GT > 50 ms 影格 | 峰值實體記憶體 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `pk_perf2` | 240 m/s | Epic（預設） | 400 / 684 ms | 397 ms | 458 ms | 2.5 | 0 | 7.9 / 11.3 ms | 0 | 2.50 GB |
| `pk_sq1` | 240 m/s | Medium | 178 / 367 ms | 176 ms | 270 ms | 5.6 | 0 | 5.9 / 9.5 ms | 0 | 2.39 GB |
| `pk_sq1_300` | 300 m/s | Medium | 176 / 370 ms | 173 ms | 270 ms | 5.7 | 0 | 5.8 / 9.5 ms | 0 | 2.37 GB |

參考（編輯器 `-game`、固定步長、Medium 陰影）：桌面渲染器 SM5 飛越 GPU 282.6 ms；**ES3.1 行動渲染預覽 168.3 ms**（p95 255.3）。

- **Editor vs 封裝**：之前 PR #46–#50 的編輯器 `-game` 數字是在編輯器套用的 **Medium 陰影**（1 cascade、1024、distance scale 0.7）下量的；封裝版預設 Epic（2048、light 設定的 4 cascades）。同為 Medium 陰影時封裝版飛越 GPU 176 ms，與編輯器同條件相符（編輯器即時 rt_final 同窗 287 ms，封裝版穩定段 270 ms）。**比較時必須固定 `sg.ShadowQuality`**。
- 森林的 3 km CSM 在這台內顯上要 ~130–150 ms；Medium（1 cascade）幾乎看不出差別（樹在 1–3 km 本來就主要靠林冠層），建議 PC 低階／行動預設 Medium 以下。
- 串流：WP 3.9 km 範圍 + PR #50 串流預算；240 與 300 m/s 飛越中皆 0 次降級（只有載入時的一次 Critical → Good，0.7 s）。
- HISM 註冊：17,351 個 HISM 分在 573 個 tile；每次 tile 進入 `AddToWorld` p99 6–8 ms、最大 11 ms，**沒有造成 game thread 尖峰**（GT 中位 3.8–7.8 ms）。cooked HISM 資料直接載入，不需要在執行時重建 cluster tree。

## 4. Runtime 飛越畫面

- `runtime_packaged_realtime_pacing.mp4`：**封裝版即時執行**，引擎自己輸出每一個 rendered frame（`-dumpmovie`），依每格實際耗時排成牆鐘時間影片。寫 PNG 讓這次執行降到 ~1.4 fps，所以畫面是真的 runtime 但比正常（5.6 fps）更斷續。
- `runtime_packaged_every_frame.mp4`：同一批 174 個 runtime 影格以 15 fps 連續播放（**不是即時**），方便看畫面內容。
- `runtime_frames/packaged_t*.jpg`：飛越中 8 個時間點的封裝版原始畫面。
- 嘗試過以 Windows 視窗擷取（ffmpeg gdigrab）錄即時畫面：擷取的是螢幕上該區域，當時遊戲視窗被使用者的其他視窗遮住，錄到的是**使用者的私人畫面**。檔案已立即刪除、未提交、未上傳，之後不再使用螢幕擷取。

## 5. 手機（Android／iOS）移植障礙

### 5.1 實際阻塞（本機驗證）
1. **UE 5.8 安裝版沒有 Android target platform**：`-run=cook -targetplatform=Android_ASTC` 立即失敗，`Available = { Windows, WindowsEditor, WindowsServer, WindowsClient }`（`cook_android_astc.log`）。需要在 Epic Launcher 的引擎選項加裝 Android 平台支援。
2. **沒有 Android 建置環境**：無 `ANDROID_HOME`／`NDKROOT`／`JAVA_HOME`、無 adb；UBT 的平台檢查回報 `Android INVALID r27c`（UE 5.8 期望 NDK r27c）。需要 Android Studio + SDK + NDK r27c + JDK 17，並在專案設定填路徑。
3. **沒有實機**：沒有 Android 裝置連線；**iOS 需要 Mac + Xcode + Apple 開發者帳號**，Windows 主機無法建置。
→ 依任務指示，未具備環境與裝置，**沒有做手機實機測試**。

### 5.2 在本機能驗證的部分：ES3.1 行動渲染預覽（`-featureleveles31`，D3D12 ES3_1）
- 所有森林材質（距離分層 Landscape、三樹種葉／樹皮含消失順位 custom data 與 WPO、建物、水）在行動 shader 路徑**編譯 0 錯誤**，整段飛越可執行。
- 同機同條件飛越 GPU：ES3.1 預覽 168 ms vs 桌面 SM5 283 ms。**這是 PC 內顯上的行動渲染器，不代表手機效能。**

### 5.3 內容層面的移植障礙（依量測推估）
| 項目 | 現況（Win64 封裝） | 手機風險 | 建議 |
|---|---|---|---|
| 樹的 instance 資料 | LLM `Meshes/InstancedMesh` ~480 MB、GPU scene 最多 1.18 M instances | 4–6 GB 手機的可用記憶體不足 | 行動檔：PR #46 的 mobile MPC 預設（滿密度 250 m、消失 1.1 km）＋ WP 範圍 ~1.5–2 km；必要時離線產生較稀的行動版 tile |
| 總記憶體 | 峰值 2.0–2.6 GB（Development） | 太高 | 先量 Shipping；降紋理、RenderTargets（TSR history 200 %）|
| Landscape 材質 | 12 samplers、446 PS 指令 | 接近 ES3.1 16 sampler 上限（Landscape 本身還要 heightmap 等）、像素成本高 | 用 Feature Level Switch 做行動版：拿掉林冠法線與雙尺度混合，只留巨觀色＋地形皮膚 |
| 遮罩葉片 | Masked + 像素 dither 淡出 | 行動 TBDR 的 alpha test／overdraw 很貴 | 行動檔縮短 3D 樹距離、LOD 提早、遠處交給地形林冠 |
| 陰影 | Epic 4 cascades 3 km ≈ 130 ms（內顯） | 行動 CSM 很貴 | 行動 1 cascade ≤ 1 km，或遠處樹不投影 |
| 串流 CPU | AddToWorld p99 6–8 ms（i7） | 手機 CPU 慢 3–4×，可能 20–30 ms 尖峰 | 降每格串流預算、減少每 tile 元件（行動版 band 數 4 → 2） |
| velocity | 已改逐元件 | 行動通常不開 TSR velocity，不影響 | — |
| 套件 | Win64 內容 713 MB（IoStore） | ASTC 量級相近 | Android 需 asset pack／OBB 規劃 |

### 5.4 下一步（依序）
1. 安裝 Android 平台支援 + Android Studio/SDK/NDK r27c/JDK 17，`Android_ASTC` cook → 看實際 shader／記憶體／套件大小。
2. 建行動檔（MPC mobile 預設、WP 範圍、陰影、Landscape 行動材質分支）並在一台中階 Android（Vulkan）實機量 FPS／溫度／記憶體。
3. iOS 需 Mac 建置機。

## 6. 限制

- 只有這台內顯的數字；封裝版即時 1080p 只有 2.5（Epic 陰影）–5.6 fps（Medium）。手機、獨顯 PC **NOT TESTED**。
- 單次量測；Development 組態（Shipping 會略快）；`-llm` 有少量 CPU 開銷。
- runtime 影片受擷取方式限制（§4）。
- `slomo 1.25` 用時間膨脹模擬 300 m/s（序列與串流同步加速），不是另一條航線。
