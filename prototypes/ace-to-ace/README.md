# Ace to Ace — 1v1 arcade air-combat AI lab (browser prototype)

Skyfront Homeland 的第一個可玩入口（Issue #34）。一片海、一片天、F-16V 對 J-16。
主要目標是驗證「飛行員 AI 本身好不好玩」，不是擬真度。
目前進行僅限本網頁原型的 [anime film 2D-look / NPR LookDev 第二輪小型風格實驗](docs/anime-film-lookdev-r2.md)，
不代表 Skyfront Homeland / Unreal 主專案的正式美術方向。

- **背景美術 + 3D 空戰的視覺實驗**：原創天空畫、少量大型雲畫片、天空反射海面、柔和冷暖受光與極淡細色線；機型輪廓可辨識但非精確建模。
- **街機空戰**：能量制飛行模型（轉彎速率在角速度峰值、拉 G 掉速、爬升換高度），簡化的飛彈 / 機砲 / 熱焰彈。
- **AI 完全本機**：傳統遊戲 AI（狀態評估 + 戰術模式 + 機動控制器），runtime 無 LLM、無網路。
- 與 `unreal/`、`cities/`、`tools/`（城市管線）完全隔離；本目錄不依賴也不修改它們。

![title](docs/screens/title-iphone.jpg)

## 啟動

不需要建置步驟（three.js r180 已 vendored 在 `vendor/`）。任何靜態伺服器即可：

```bash
cd prototypes/ace-to-ace
python3 -m http.server 8080        # 或 npx serve .
# 桌面：http://localhost:8080
# iPhone：同一個 Wi-Fi 下開 http://<電腦的區網 IP>:8080 （Safari，橫向）
```

URL 參數（開發用）：
- `?mode=arcade|tactical&control=assisted|expert`：預選飛行物理與操控方式（仍停在標題畫面，不自動出擊）。
- `?autostart=1`：直接出擊；`?mode=pvai`（舊網址，直接出擊，物理沿用已儲存設定或 `?feel`）；`?mode=aivai`（直接觀戰）。
- `?feel=A|B`：歷史 A/B 測試用的舊飛行積分器（僅供回歸比較，不在選單中）。
- `?debug`（AI 狀態面板）、`?skill=rookie|veteran|ace`、`?seed=N`（可重現的開局）、`?autopilot=chaser`（自動駕駛玩家機，煙霧測試用）。

## 操作

| | 觸控（iPhone，橫向） | 鍵盤 |
|---|---|---|
| 轉彎 / 俯仰 | 左半螢幕浮動搖桿 | 方向鍵 |
| 油門 | 右側動力條上下滑動（放手保留，預設 72%） | 固定巡航 72% |
| 後燃器 | 動力條頂端 `AB`（切換） | `W`（按住） |
| 減速板 | 動力條底端 `BRK`（按住，不取消油門或 AB） | `S` |
| 飛彈 / 機砲 | `MSL` / `GUN`（按住） | `Space` / `Shift` 或 `F` |
| 熱焰彈 | `FLR` | `Q` |
| 看向敵機 | `LOOK`（按住） | `E` |
| AI 狀態面板 | `AI` | `Tab` / `` ` `` |
| 暫停 / 再戰 | `II` / 結算畫面按鈕 | `Esc` / `Enter` |

**飛行設定（四種組合）**：標題畫面或暫停選單的「⚙ 飛行設定」選擇 **Arcade / Tactical 物理** × **Assisted / Expert 操控**，
預設 **Arcade × Expert**。物理對玩家與 AI 完全相同；操控方式只改變搖桿如何被解讀，不改變飛機性能。詳見
[`docs/dual-flight-modes.md`](docs/dual-flight-modes.md) 與 [`docs/flight-feel-polish.md`](docs/flight-feel-polish.md)。

**Expert（預設）**：左右＝滾轉、上下＝俯仰，必須先滾轉再拉桿才能轉彎；沒有自動改平。
**Assisted**：搖桿左右＝要求轉彎，飛控自動解出水平轉彎所需坡度並協調拉桿；搖桿回中自動改平；
置中時上下就是純俯仰（翻筋斗、俯衝都還是你的）。Assisted **不會**自動開後燃器、不會提供額外 G 或推力；油門、AB、BRK 全由玩家控制。
iPhone 上虛擬搖桿是**彈簧回中**：手指放開，搖桿指令與搖桿圖示回到中立，下一次觸碰從中立開始。回中的是**指令**，不是飛機：Expert 放手後停止滾轉、保持當下坡度（不自動改平）；Assisted 由飛控協助改平。油門位置、AB 切換、BRK 按住各自獨立，不受搖桿放手影響；切到背景、失去焦點或觸控被系統取消時，搖桿與 BRK／GUN 會釋放，不留幽靈輸入。

**HUD 姿態參考（AC7 LookDev v2）**：依 AC7 實際駕駛艙 HUD 截圖，使用細薄的左右開口導框、頂部航向刻度帶、中央小型 **W 形 Waterline／Whiskey Mark**（機頭方向）和可隨坡度旋轉的每 5° 俯仰梯（向下為虛線）；去除前版完整方框與 HDG／PITCH／BANK 大字組，速度／高度改成綠色小箭頭框。保留第三人稱下讀取姿態的能力，不動觸控、操控、物理與 AI。不新增按鈕。 既有小圓機頭準星現已改為 W，不會兩個機頭符號重疊；近距機砲 lead pipper 原樣保留。現在 W 與飛行路徑標記（Flight Path Marker／FPM，帶翅膀的小圓圈）**同時顯示**：W 從機頭方向投影，FPM 從飛機實際速度向量（即位移方向）投影。高速平飛會重合；拉 G、拉升、改變航向時會出現幾度的偏差。為此在玩家和 AI **共用的**簡化飛行模型加入短暫的速度方向慣性響應（舊版 0.09 秒；Arcade／Tactical 各自設定）：這會輕微改變實際航跡／飛彈攔截幾何，但**不改搖桿、最大 G、推力、阻力或武器機制**；這是街機近似，不是完整 AoA／側滑 CFD 模擬。

**俯仰方向**：在「⚙ 飛行設定」切換（預設搖桿式：上推＝俯衝）；暫停中只改俯仰方向會立即套用到本局、不重開。

## 王牌飛行學院（Ace Flight Academy）

標題畫面「飛行學院 ACADEMY」：10 堂 1–3 分鐘的可玩短課，由教官 KITE 以無線電引導——
天空與地平線、飛機如何轉彎、動力控制、G 力的代價、能量交易、危險飛行狀態、空戰追蹤、武器控制、防守與反擊，
最後是對 VETERAN AI 的 **ACE QUALIFICATION** 畢業考（S／A／B 評等）。每課都判讀真實模擬狀態，失敗時依你的實際數據
說明原因（例如「平均 9.6G，速度從 751 被燒掉了」），飛行中也會依你的實際動作即時提醒（例如「你在瞄它本身——瞄橘圈」）。
重試跳過開場白；後段失敗可「從此段重試」（最高 A，S 需一次飛完）。畢業時依你的飛法授予 TAC NAME。
支援全部四種飛行／操控組合，進度只存在本機 localStorage。
自由對戰不需要先完成學院。課程設計、真實航空／遊戲模型／遊戲規則的區分與驗收數據見
[`docs/academy-curriculum.md`](docs/academy-curriculum.md)。QA 連結：`?lesson=L05`（簡報）、`?lesson=L05&autostart=1`（直接出擊）。

## 規則（為街機節奏調整，非真實性能）

- HP 100；飛彈 50–75 傷害（兩發必死）、機砲 4/發；熱焰彈 2 組，25 秒回充 1 組。
- 飛彈 12 枚、左右掛架各 5 秒裝填；鎖定需目標在機頭 30° 內 0.85 秒；最小射程約 450 m。
- 飛彈有自動駕駛延遲：**在約 2–3 秒前用最大 G 側向急轉**可以甩掉；太晚或速度太低會被追上。
- 5 分鐘時限：依剩餘 HP 判定；同分則「Sudden Death」（下一次命中定勝負，再 60 秒仍無則平手）。
- 戰區半徑 12 km、升限 10 km；出界 12 秒判負。墜海即損失。
- 難度只改「AI 飛行員的品質」，飛機、物理、武器完全相同；另依街機慣例，ROOKIE 時玩家受到的傷害 ×0.75。

## 架構

```
src/sim/   飛行模型、武器、規則、射控輔助（純 JS，無 three.js，Node 可跑）
src/ai/    飛行員 AI、無線電台詞、測試用 bot（含 human proxy）
src/game/  three.js 渲染、模型、HUD、輸入、音效、主迴圈
tools/     aivai.mjs（無頭 AI 對戰與校準）、browser-check.mjs（Playwright 實機畫面檢查）、model-viewer.html
```

AI 輸出與玩家完全相同的控制量（俯仰 / 滾轉 / 方向舵 / 油門 / 武器），經過同一個 `stepAircraft()`；
它不能做出玩家做不到的機動。模擬以 60 Hz 固定步長、種子化亂數執行，AI vs AI 可完全重現。
決策層（`ai/`）與飛行 / 武器規則（`sim/`）及渲染輸入（`game/`）分離，未來移植到 Unreal 時可以照搬設計與參數。

## 飛行員 AI

`src/ai/pilot.js`，分四層：

1. **感知**：看到的是 0.26–0.6 秒前的對手（依難度）再做航位推算；用 RWR/MAWS 規則得知被鎖定與來襲飛彈。
   不讀取玩家輸入。
2. **態勢評估**：距離、ATA（我的機頭對它）、aspect（我是否在它六點）、它對我的 ATA、接近率、
   比能量差（高度 + 速度²/2g）、飛彈威脅（含「這枚飛彈還追得到我嗎」的動能判斷）。
3. **戰術模式**（優先序 + 最短停留 + 兩票遲滯，避免抖動）：
   - `ENGAGE` 遠距佈局：偏置接近準備 lead turn、能量不足時爬升、搶高度優勢；對頭時會先開一發「逼迫彈」。
   - `ATTACK` 追擊：遠距 lead pursuit、近距機砲提前量追蹤（含前饋控制）、接近率過高改 lag + high yo-yo、
     能量不足 low yo-yo / 卸載加速。
   - `DEFEND` 被咬：向攻擊者急轉、近距減速板逼對手衝過頭再反咬、機砲範圍內 jink、能量大時拉垂直。
   - `EVADE` 飛彈：遠時 beam / crank、2–3 秒內最後急轉、依難度時機放熱焰彈；有鎖定時「回敬一發」。
   - `EXTEND` 脫離重整：卸載、後燃、俯衝加速，拉開後**一定回頭**再接戰（有時間上限與冷卻）。
4. **機動控制器**：把「想往哪個方向飛、用多少 G」轉成升力向量控制（先滾轉、再拉、重力補償、
   G 受限時保留重力補償、目標角速度前饋），輸出與玩家相同的搖桿量。

**防無限繞圈**：偵測 12 秒內雙方持續高 G 迴轉、沒有任何傷害進展、角度優勢沒變化，或「領先角度但從未把機頭對上」
→ 啟動破局：高 yo-yo（爬出迴圈平面再翻轉俯衝到提前點）、剪刀反轉、或脫離重整後重新對頭。45 秒內連續失敗就升級為重整。

**防避戰**：`aggression` 會隨「很久沒開火」「距離太遠」上升；高時不再脫離、降低開火門檻、會打牽制彈；
被命中時暫時變謹慎。重整只能是重整：有時間上限、回頭條件，且被對手機頭指著時會中止。

**讀你的習慣**：AI 觀察自己的飛彈接近你時你有沒有在閃（高 G 或熱焰彈），更新「閃避指數」，調整它的開火門檻；
結算畫面會告訴你它對你的判讀。

**讓玩家看得懂**：戰術轉換會觸發攔截到的敵方無線電（預寫台詞，有冷卻）；`AI` 面板顯示模式、機動名稱、
決策理由、ATA / aspect / 能量差 / Pk / 侵略性與最近的決策紀錄。

**難度**：ROOKIE / VETERAN / ACE 只改反應時間、G 使用率、瞄準誤差、射擊紀律、閃避時機，
以及「會不會用進階戰術」的機率（逼迫彈、回敬、lag / yo-yo、破局選擇、減速反咬、飛彈動能判斷）。

## 測試

```bash
node tools/aivai.mjs --suite --n 100 --write docs/aivai-report.json   # 無頭對戰與校準（約數分鐘）
node tools/aivai.mjs --n 40 --blue human --red veteran --verbose        # 單一組合 + 決策紀錄
node tools/browser-check.mjs                                             # Chromium 實際啟動遊戲並截圖
node tools/browser-check.mjs --scenario lookdev                           # 固定追機 / 側傾 / 近雲 / 海面 / 俯衝 / 雙機型
node tools/browser-check.mjs --scenario settings                          # 四模式設定選單：選擇/取消/儲存/重整/暫停切換/再戰
node tools/browser-check.mjs --scenario modes                             # 四種組合的 iPhone 尺寸觸控操作 + 兩套物理各一場完整 1v1
node tools/probe-flight-feel.mjs                                          # 四種組合的手感量測（滾轉停止、轉彎、能量、追蹤）
node tools/aivai.mjs --n 40 --blue human --red veteran --feel tactical --control expert   # human proxy 走 Expert 操控
node tools/test-academy.mjs                                               # 學院 10 課 × 4 模式 + 錯誤示範的因果失敗
node tools/browser-check.mjs --scenario academy                           # 學院選單→出擊→失敗→重試→通關→進度保存
```

- **AI vs AI**：同一套 AI 對打（正面開局 / 隨機幾何 / 交換機型）、ACE vs ROOKIE 技術梯度、
  直飛靶機與最大 G 繞圈靶機（必須擊落）、兩種壓迫型追擊 bot。統計勝率、時間、飛彈命中率、
  **繞圈秒數**（雙方 >3G、200–2500 m、20 秒無開火）、**>5 km 避戰秒數**、最長無開火時間、先開火者勝率、擊墜機會窗。
- **Human proxy**：走真正的玩家輸入路徑（`PlayerController` + ASSIST），只用 HUD 可見資訊（目標框方向、鎖定、
  SHOOT 提示、MISSILE 警告），有反應延遲、拇指漂移（OU 雜訊）與常見習慣。它是玩家模型，不是玩家。
- **瀏覽器**：桌面 1280×720 與 iPhone 13 mini 尺寸（812×375、觸控事件）各跑一次：標題、自動駕駛對戰、
  鍵盤操作、觸控搖桿與按鈕、AI 觀戰、擊墜鏡頭、結算與 `Enter` 再戰；收集 console 錯誤與 draw call 數。

最新結果見 [`docs/aivai-report.json`](docs/aivai-report.json) 與 PR 說明。

## Brake Trap（減速誘敵實驗）

- J-16 被較快的玩家近距離咬尾、對方正快速逼近時，較有經驗的 AI 可能短暫減速並偏轉，嘗試讓玩家衝過頭；不是隨機表演。
- 只有 AI 感知到敵機真正穿越**開始減速時的原機頭平面**，才進入反追並播放成功台詞。若敵機沒有衝過頭，只算一次失敗的耗能嘗試。
- 每次短暫減速不超過 1.8 秒，至少間隔 18 秒，遇到來襲飛彈或失去安全條件就退出；完全使用現有物理系統，不瞬移、不強制鏡頭。
- 遊戲畫面顯示「J-16 減速！」；確認對手衝過頭才顯示「J-16 反咬！」；結算顯示嘗試與確認次數。
- `node tools/test-brake-trap.mjs` 可檢查啟動幾何條件、成功判定、逾時、冷卻、飛彈優先與技能差異。
- **限制：**此測試驗證決策與事件條件，不能取代 AI vs AI 回歸、真實 iPhone 操作與玩家是否感到驚喜的遊玩測試。
