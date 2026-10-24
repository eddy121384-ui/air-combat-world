# 老公寓 Exemplar 269873：第一輪 UE 5.8 美術試作

**結果：部分改善，尚未完整達成 150–300 m 的遠距辨識目標。** 50 m 的外推鐵窗、窗沿投影與冷氣機層次明顯；150 m 仍可分辨較厚的框架與生活設備；300 m 在全幅圖中差異偏弱。已完成第一版與一次針對性修正後停止，不把局部放大圖當成遠距成功證明。建議先審定這棟的 300 m 主次層次與舊平面細節殘留，再決定第二棟華廈，暫不擴散到全區。

2026-10-24；在原 C 槽 `xinyi-material-ue58-round1` worktree，從 PR #68 的 `a6b0d3536ac00e12214e78665750c9994518dd44` 原地建立 `feat/xinyi-walkup-exemplar-269873`。沒有新 worktree、D 槽場景複製、城市幾何生成、Cook 或 merge。Windows UE 5.8.0 / CL 55116800、D3D12、Intel UHD 770（31.0.101.4502）。

[手機審圖與三個距離的原圖](evidence/xinyi-walkup-exemplar-269873/README.md) · [完整資料與量測](evidence/xinyi-walkup-exemplar-269873/summary.json) · [來源不變驗證](evidence/xinyi-walkup-exemplar-269873/source-immutability.json)

## 研究與取捨

都市更新處「村落之聲」的[撫遠街步登公寓整備紀錄](https://www.villagetaipei.net/Post?PId=15333)說明四至五層步登公寓與外推鐵窗／陽台的生活使用；[信義區老屋案例](https://www.villagetaipei.net/Post?PId=15361)有整備前被鐵窗封閉的陽台照片。這些是現地整備案例，並非目標棟的實測紀錄。

另直接觀察 Alfred Twu 2018 年拍攝的[台北公寓實景原作](https://commons.wikimedia.org/wiki/File:Taipei-apartments-with-rooftop-additions.jpg)（作者自攝、CC0；[本 PR 縮小參考圖](evidence/xinyi-walkup-exemplar-269873/reference-alfred-twu-2018-cc0.jpg)）。照片中的窗籠、外推窗面與冷氣箱體有不同深度，遠看形成框架、平台及陰影節奏。未把照片貼到模型，也未宣稱它是 269873 的實況。此試作是類型美術概念，不是目標地址的寫實復原。

原版 `M_XinyiCity` 已有窗型、鐵窗與冷氣的程序化繪製，但大多落在同一牆面，缺少視差與自投影；細線遠距又會被濾成平均色。原版屋頂已有設備，本輪不再疊加屋頂物件。只選兩項改善：

1. **立體窗框／外推鐵窗**：依既有 bay 與 floor 節奏生成窗框、窗台、頂蓋、主欄杆與側向回折。不是新增房間或改建築本體。
2. **冷氣機與支架**：沿同一樓層／窗邊規則安排箱體、簡化散熱格柵及支架，打破平面白色方塊感。

本輪實際是 12 個開窗模組、5 組外推鐵窗、7 組冷氣；沒有新增陽台房間、屋頂加蓋、管線、招牌、植栽或其他功能。

## 單棟與來源保護

目標 `tp_building_height.269873` 為 4 層、15.95 m 高，surveyed ground 9.45 m，來源仍為已保留的 EPSG:3826 資料。從既有 Look GLB 的 `-001_-001` tile 讀取這棟的 UV／normal／payload 與兩面臨街牆；不用重新 extrusion 或 triangulation。綁定的 97 個原始頂點只讀，未搬移、刪改或重建。

所有新增內容在 `/Game/XinyiExemplar/Walkup269873`。Actor 只在截圖時暫時生成，關閉／不生成即可回到 Before；不存地圖、不新增碰撞。原 footprint、本體位置、接受的 tile、地形、森林、樹木與其他建築材質都不改寫。窗籠最大外推 0.82 m，屬附掛構件包絡，不改地面 footprint。現有店招佔至 1.72 個樓層，模組只設在其上的兩層，避免遮住店面。

254 筆 #68 凍結檔案（包含既有 182 個 UE 場景／依賴檔）逐 SHA-256 不變；D 槽原始輸入與 C 槽複本各 243 筆均一致。其餘 40 個 investigation 檔案未修改。所有 #68 原始 PNG、預覽與報告保留；#68 分支仍固定在 `a6b0d35`，不因本次新分支提交而移動。

## 一次修正與實際畫面

R1 新增 3,744 triangles，已有明顯深度，但全綠色 backing 抹掉原窗面差異，顯得像整批換新窗；CPU 採 packed seed / 255，原 shader 卻採 / 256 + 0.00123，使部分窗型／冷氣選擇不齊。細鐵條也缺乏遠距主次。

唯一的 R2 修正為：對齊 shader seed、移除新玻璃 backing，保留原版玻璃／窗簾色彩；鐵窗外推 0.52 → 0.82 m，主條厚度 0.035 → 0.055 m，間距 0.25 → 0.34 m，並壓低過乾淨的框色。沒有加第三種功能。幾何降為 **2,940 triangles（比 R1 少 804 / 21.5%）**。兩版 GLB、規則摘要、原始 UE 圖與 [修正紀錄](evidence/xinyi-walkup-exemplar-269873/iteration-plan.json)皆保留。

| 距離 | 全幅 A/B JPEG | 原像素立面裁切 | 原始 UE Before / After |
|---|---|---|---|
| 50 m | [全幅](evidence/xinyi-walkup-exemplar-269873/review/050m-full-ab.jpg) | [細節](evidence/xinyi-walkup-exemplar-269873/review/050m-detail-ab.jpg) | [Before](evidence/xinyi-walkup-exemplar-269873/captures/before/distance_050m__day.png) / [R2](evidence/xinyi-walkup-exemplar-269873/captures/r2/distance_050m__day.png) |
| 150 m | [全幅](evidence/xinyi-walkup-exemplar-269873/review/150m-full-ab.jpg) | [細節](evidence/xinyi-walkup-exemplar-269873/review/150m-detail-ab.jpg) | [Before](evidence/xinyi-walkup-exemplar-269873/captures/before/distance_150m__day.png) / [R2](evidence/xinyi-walkup-exemplar-269873/captures/r2/distance_150m__day.png) |
| 300 m | [全幅](evidence/xinyi-walkup-exemplar-269873/review/300m-full-ab.jpg) | [細節](evidence/xinyi-walkup-exemplar-269873/review/300m-detail-ab.jpg) | [Before](evidence/xinyi-walkup-exemplar-269873/captures/before/distance_300m__day.png) / [R2](evidence/xinyi-walkup-exemplar-269873/captures/r2/distance_300m__day.png) |

相機至同一立面觀察點的實際直線距離為 50／150／300 m，**全部使用同一 50° 水平 FOV**、35° 俯視方向；沒有以遠距窄 FOV 偽裝近距。每個 Before／R1／R2 的相機 JSON、實際畫質 console 值、基準地圖與基準材質 hash 均相同。1920×1080、白天、無雲、sg.*=2、ScreenPercentage=100、MotionBlur=0、RayTracing=0，沿用原有 day preset 的 manual exposure。實機程序均正常 exit 0，reopen check 均通過，未存地圖。

原圖是 `SceneCapture2D → RTF_RGBA8 → FINAL_COLOR_LDR → export_render_target` 的 byte-exact 副本。共保存 Before、R1、R2 各 3 張 **9 張 UE PNG**。全幅 JPEG 左右同為 40%，另提供左右同座標、不縮放的立面裁切 JPEG，兩者均無調色／銳化。JPEG 有損壓縮，細節以原圖為準；裁切沒有增加遠距資訊。獨立 UE 程序仍有少量全畫面像素差異，不能宣稱改變像素全部侷限單棟，也不能以影像差值當辨識度評分；來源／其他資產不變由檔案 hash 證明。

## 成本

| 項目 | R2 新增成本 |
|---|---|
| UE render-data triangles，LOD0 回讀 | **2,940** |
| StaticMesh / Actor / material section | 各 **1**；只在 After 暫時加入 |
| Draw submissions | 每個可見 raster pass 約 +1；depth／shadow passes 另外增加。這是由 section 數推算，**未量測全場景 RHI Draw Calls** |
| 新增 image textures | **0**；以 UV 儲存構件顏色 |
| 材質 compiler statistics | pixel **267**、vertex **144** instructions；samplers **3**、pixel texture samples **0**（引擎回報） |
| LOD / Nanite / collision | 僅 LOD0；Nanite OFF；碰撞 OFF；投影 ON |

這是一個獨立材質 draw，267 不能與原城市 shader 指令數相減當成效能節省。所有距離都保留 LOD0，未完成遠距 LOD 與全區批次合併／instancing；單棟 +1 section 不能直接證明擴大到上千棟仍合算。

| Windows 同步 SceneCapture wall-time，每姿勢 40 次 | Before median（P10–P90） | R2 median（P10–P90） | median 差 |
|---|---:|---:|---:|
| 50 m | 62.80（60.35–67.33）ms | 61.07（59.52–64.33）ms | -1.73 ms |
| 150 m | 61.85（59.91–64.94）ms | 61.25（59.81–64.86）ms | -0.60 ms |
| 300 m | 65.05（63.24–68.35）ms | 64.68（63.05–68.71）ms | -0.37 ms |

沿用既有 capture_scene + 1-pixel readback 強制 GPU 同步方法，包含 CPU、提交與 readback 固定成本；只有一輪，時間區間重疊，負差值不能當成新增幾何會加速。**沒有測得可信的時間成本差異**，也沒有純 GPU timestamp、遊戲 FPS、手機效能／ASTC／發熱結論。

## 未解決與下一步

- 300 m 的全幅辨識提升仍不足以明確通過成功標準；細格柵與冷氣會收斂成少量像素。應先讓美術判斷窗籠的粗輪廓是否值得保留，再決定是否調整遠距表達，而非繼續堆細節。
- 原 shader 的平面鐵窗／冷氣仍在，少數位置有雙層線條或平面殘留；本輪只讀疊加，不冒險改共享城市材質來消除它們。
- 尚未測連續移動閃爍、反向／夜間／背光、其他高度與多棟批次成本。深度及 bay grammar 可重用，但下一棟仍須顯式綁定來源，不是已完成全區自動套用。
- **暫緩直接開始第二棟華廈。** 先審定此棟 150／300 m 的收益，再安排有針對性的遠距／批次方案；本次不再追加第三版。

## 回放與驗證

桌面 Python 使用既有環境；不安裝新套件。`generate.py --revision r1|r2` 只產生新的獨立套件 GLB 與 manifest；`run.ps1 -Stage import -Variant r1|r2` 只匯入 Exemplar 命名空間。現有 receipts 存在時拒絕覆蓋，已存在的 mesh 不需重匯。

在同一個 worktree 重拍時，用 `run.ps1 -Stage capture -Variant before -CaptureRun review01` 及 `-Variant r2 -CaptureRun review01`，另存到 `Saved/XinyiExemplar/Walkup269873/runs/review01/`；兩輪用相同名稱且不同 variant。`collect.py` 是本輪封存工具，新 run 不自動覆寫已提交證據。不要重跑 #68 的 runner／collector／preview builder。

本輪四項離線 QA 通過：GLB 三角面非退化／normal 朝向、單棟／店招範圍、三個距離與 A/B 配對、9 張原圖與 JPEG hash／容量；PowerShell parsing 及 `git diff --check` 通過。`verify_protected.py` 核對 #68 的凍結清單與兩處來源。小型 UE 材質／mesh snapshot、兩版生成來源及所有 receipt 隨本 PR 提交，正式 182 個本機基底資產不整批納入。

[QA 與提交範圍核對](evidence/xinyi-walkup-exemplar-269873/verification.json) · [兩版 GLB 獨立重產的相同雜湊](evidence/xinyi-walkup-exemplar-269873/determinism.json)
