# 動畫驗證與交付判斷

## 動態觀察

所有比較共用 B0 field／seed、相機位置、方向與 time=0；風另由操作測試檢查。R2 天空同一份素材。source hash 與每幀 pose／density 見 `final/report.json`。原 B1 與 Animfix 是各自原 shader，不用 B2 的畫面冒充控制組。

| 場景 | B2 的改善 | 仍存在的問題 |
|---|---|---|
| 接近雲牆 | 固定殼按透視增大，有明確前後關係；不改 top／side 圖 | 輪廓偏硬，插畫塊面像塗在實體上 |
| 側面掠過 | 表面視差與固定世界筆觸；沒有海報追鏡頭 | 原路線後半會擦入雲區，需搭配純外側補充片判讀 |
| 雲底爬升至雲頂 | 同一封閉物體的底部、側壁、屋頂；不換圖 | 平底／塔頂刻面有時像浮島或岩塊 |
| 上方雲海 | 固定幾何遮蔽、多團深度與大塊受光 | 群組輪廓重複感、遠景細節密度不如 B1 |
| 擦過雲邊 | 局部表面逐漸被密度霧遮蔽，整團不按中心淡出 | 稀疏霧會把邊緣塗寬；極近表面仍有 coverage 量化 |
| 進雲 | 霧一直存在；修正 hull depth 引起的透射重設 | 中景塊面進入密區後仍會失去較多細節 |
| 雲內前飛 | 冷暖三維 pigment 提供淡結構，戰機按真實場景深度遮蔽 | 仍有接近均勻灰霧的區段，未達有詩意的內部明暗 |
| 穿出雲 | 霧與表面隨世界位置恢復；沒有模式開關 | 連續穿雲第183–188幀仍可見較大的殼面／斜切邊滑出，尚不夠自然；不是完全解決消失感 |
| 90°／180° 繞行 | 眼睛真的移動；同一固定殼、底部／肩部與筆觸可追蹤 | 有硬殼、貼畫岩塊感；光照、透視與投影 mip 仍會自然改變畫面 |

高位轉向避免鄰雲擋住目標，沒有移動雲。低視角由側掠／爬升覆蓋。額外純外側側掠把眼睛放在場邊界外，持續看向同一前緣雲團，並核對每幀 eye density 為零；用來區分正常入雲遮蔽與 billboard 破綻。

`motion/` 對全部主比較 JPEG 計算相鄰低解析度 RGB 差，輸出每場景的 12 時刻密集表與最大變化附近六個**相鄰**幀。差值只定位需檢查位置，不是品質分數：低反差或細節消失也會降低差值。不能以它宣稱美術比 B1 好。

主比較2,700幀、外側側掠270幀、無剪接穿雲720幀，合計3,690幀均作相鄰差檢查；手動查看各場景密集表與重點相鄰幀。完整穿雲 B2 最大平均 RGB delta 約0.0404，位於第186幀出雲位置，仍可見上述硬切面問題。入雲120幀、220m/s、60Hz的另一次局部檢查為0.00413，不能用入雲數字代替全部路線品質。

局部霧另以72條實際 GPU T 讀值比原 B0 的900m／10m步距積分，平均絕對誤差0.0472、最大0.6543；最大出現在側掠畫面右側空隙（reference T=0.8583、B2 T=0.2039），是**過度遮蔽**。此診斷沒有設「準確體積重建通過」門檻；它保留了低成本3×3方向插值的明顯不足，不能把 JSON 的功能 passed 當成物理精度通過。

## 自動驗證紀錄

| 檢查 | 結果／證據 |
|---|---|
| 既有五項 regression | PASS：brake trap、HUD attitude、flight path、airbrake/throttle、mobile power strip |
| B0 CloudField | PASS；[b0-field/field-validation.json](b0-field/field-validation.json)，seed／風／連續性／視線積分 |
| B1 layout／fog | PASS；[b1-layout/layout-validation.json](b1-layout/layout-validation.json) |
| B2 雲殼 | PASS；[hull-validation.json](hull-validation.json)，同 seed bytes 完全一致、不同 seed 改變、兩雲形封閉邊／不一致繞序均0、有限且單位法線、正體積；頂點與三角形中心均在 B0 正密度內 |
| 十場三模式動態 | PASS；[final/report.json](final/report.json)，2,700幀，每幀位置／方向／density／field一致；飛行中無 geometry/cache 重建 |
| 外側側掠 | PASS；[side-review/report.json](side-review/report.json)，270幀，眼睛始終在零密度區，三模式 pose 一致 |
| 無剪接穿雲 | PASS；[traverse-review/report.json](traverse-review/report.json)，720幀，首尾零密度、中途>0.5；逐幀位移一致、沒有瞬移／剪接 |
| 相鄰幀 QA | 完成3,690幀；[主比較](motion/report.json)、[外側](motion-side-review/report.json)、[穿雲](motion-traverse-review/report.json)；數值不是美術分數 |
| 入雲連續性 | PASS；[performance/report.json](performance/report.json)，120幀／60Hz／220m/s，中心RGB delta最大0.00413，build counter不變 |
| 局部霧 GPU 診斷 | 72條實際 T 讀值，平均誤差0.0472、最大0.6543；只確認有限範圍與管線可運行，**未通過精確體積重建判斷** |
| Lab 操作 | PASS；[controls.json](controls.json)，WASD／環視／風／路線／進度／動畫按鈕／模式切換／觸控 |
| B0 保留模式 | PASS；[b0-controls.json](b0-controls.json)，同一 Lab 空間與操作 smoke；略過重複 GPU benchmark |
| R2 正式遊戲 smoke | PASS；[r2-smoke.json](r2-smoke.json)，27張實際畫面、觸控 power strip／FOX2／AI對戰／結果／Enter重賽，errors=[] |
| Console／shader／資產 | 三輪動畫、兩模式操作、R2 smoke 均無錯誤，WebGL programs runnable |
| 影片比較頁 | PASS；[gallery-smoke.json](gallery-smoke.json)，39段 metadata／時長、同步播放及前進一格；[頁面實際截圖](gallery-runtime.jpg)。Range請求實測206、0–31 bytes回32 bytes |

控制與 R2 的完整 PNG 截圖是可重現的忽略輸出 `tools/out/b2-controls/`、`b2-debug-controls/`、`b2-r2-smoke/`；此處提交 JSON，雲系統的實際 JPG／WebM 另完整提交。B0 操作工具的 baseline 欄沿用歷史祖先0db84b5；其中 source hash 指向本輪 Lab，分支起點仍是9963292。

## 限制與整合評估

固定幾何、筆觸和深度關係解決了 B1 表示法中的視角重建問題；四區間局部霧避免 Animfix 的 32 點逐像素密度積分。這是有價值的 B2 空間／成本實驗，**不是全部美術目標通過**。

尤其不能把較硬的塊面自動稱為動畫電影手繪雲。表面仍有岩塊／覆雪硬殼感、近距面片、投影材質縮放與群組造型重複；密霧內筆觸仍不足。粗網格是雕刻 scalar 的分片線性近似，scalar residual 不是物理 density error；頂點與三角形中心在 B0 正密度內，不代表每個像素都精確重建 B0 邊界。

稀疏方向霧可能在切線／小空隙產生過度遮蔽或漏遮蔽。opaque depth prepass 使用靜態網格深度，若未來加入新的 vertex deformation，需要另行對齊，不能直接移植到正式遊戲。同步建殼的暫停、手機 GPU／Safari、熱負載均未解決。

因此保留於 Cloud Lab，**不建議接入正式 Ace to Ace**。正式 R2 的天空素材、背景構圖、HUD、搖桿、油門、AB／BRK、AI、武器與飛行物理不變；Unreal 不變。#35／#41／#42／#44 保持 Draft，不 merge、不 force-push。
