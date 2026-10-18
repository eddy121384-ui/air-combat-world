# B0 驗收記錄

使用者故事：Cloud Lab 的路線／鏡頭操作 → 純 CloudField 世界座標查詢 → 密度快取 → 依場景深度積分 → 雲內可見度降低、出雲恢復。全部資料在本機，沒有 API、帳號或環境變數依賴。

## 已驗證邊界

| 驗證 | 結果與證據 |
|---|---|
| 原有五項 regression | PASS：brake-trap、hud-attitude、flight-path、airbrake-throttle、power-strip；執行 `npm test`。 |
| 可重現與 seed | 兩種雲形各 5,000 點，與同 seed 完全一致；另一 seed 改變幾何及密度。 |
| 三維連續性 | X/Y/Z 各移動 0.5 m，最大密度差分別不超過 0.0071；包含雲底／頂與世界負座標。 |
| 時間、方向及高度 | 風平移查詢一致；前後積分一致；雲上方視線 T=1；同位置六方向局部密度相同。 |
| 穿雲 | 220 m/s、60 Hz 的數值路線，最大單幀密度差：積雲 0.01834、層積雲 0.02084；最大 T 差 0.01697。 |
| 顯示與遮蔽 | 接近／雲內／穿出由真 WebGL 畫面記錄。鏡頭轉開再回到同姿勢，framebuffer hash 完全一致；96 步邊界畫面掃描最大中央區域平均 RGB 差約 0.000164（歸一化 0–1）。 |
| 操作 | 實際 DOM 路線滑桿、播放／暫停、mouse drag、W 前進、風時間及 CDP touch drag 均通過。 |
| R2 browser smoke | 完整 `--scenario all` 通過，26 張 runtime 截圖，console/page/network errors=0。包含 7 組天空鏡頭、雙機型、受控擊墜、標題、對戰、鍵盤、觸控油門／AB／BRK、AI 觀戰、完整結算及 Enter 再戰。 |

數值原始資料：[field-validation.json](field-validation.json)。瀏覽器原始資料：[browser-validation.json](browser-validation.json)，包含 Chromium 版本、來源 SHA-256、世界位置、局部密度、T500、GPU timer 與真截圖。R2 完整報告：[r2-smoke.json](r2-smoke.json)；其 26 張完整解析度截圖保留於本機可再生目錄 `tools/out/cloud-b0-r2-smoke/`。

## 保留基準

`git diff 0db84b5 -- prototypes/ace-to-ace/assets prototypes/ace-to-ace/src/game prototypes/ace-to-ace/src/ai prototypes/ace-to-ace/src/sim prototypes/ace-to-ace/vendor prototypes/ace-to-ace/index.html prototypes/ace-to-ace/style.css` 為空。

兩個 R2 素材的工作樹 Git blob hash 與基準完全相同：

| 素材 | Git blob SHA-1 |
|---|---|
| sky-painting-r2.jpg | `77b28531cbaf7747cb3a021d566a6d230b7e0340` |
| cloud-paintings-r2.png | `22e7e45fc6807b3f3b66cbbe25793e7a4e0dd758` |

原 checkout 保持 `claude/vibrant-dirac-kmsuin`、`0db84b5953eaffd75c3256ad0579f3c098dd0147` 且 clean。B0 只在獨立 worktree `ace-cloud-engine-b0` 工作；不 merge main、不 force-push、不改 PR #35 的 Draft 狀態。

## CPU 成本

Windows、Node v22.23.1、Intel Core i7-12700。先暖機，每種工作負載 100,000 次查詢，5 輪；包含測試輸入組裝成本。這是 CPU 密度函式 benchmark，沒有 GPU 或 FPS 換算。

| 工作負載 | 中位數 μs/query | 5 輪範圍 μs/query |
|---|---:|---:|
| 雲內外混合點 | 0.638 | 0.490–0.713 |
| 雲核心點 | 1.258 | 1.217–1.499 |

GPU 合成成本與 CPU render submission 另見 [performance.md](performance.md)。快取一次建構成本、顯示解析度及 360 KiB 密度體積都在瀏覽器報告中記錄。數據是小型有界診斷，不是長時間壓力或真機測試。

## 限制

視覺 QA 為 Chromium SwiftShader 桌面與觸控尺寸模擬，未聲稱 iPhone／Safari 真機驗證。低解析快取、粗輪廓、固定積分步數、簡化明暗與有限雲域是已知限制。數值／畫面掃描覆蓋代表性路線，不能保證任意極端參數、任意速度或無限時間的行為。
