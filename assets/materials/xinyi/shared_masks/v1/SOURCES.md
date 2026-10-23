# 來源與使用條件

本批為專案原創／AI 輔助的灰階控制圖，沒有下載照片、掃描材質、Fab／商店貼圖或第三方建築影像。來源與衍生檔的 SHA-256 分別記在 `inputs.json`、`manifest.json`；原圖保留，不以處理後貼圖冒充原始生成結果。

| 來源 | 出處與版本 | 使用條件／紀錄 |
|---|---|---|
| A1 風化、A2 補漆 A、A3 雨痕 | PR #14 @ `6c2feb1611a3d07436c8222c3b67246a9b1ad8cd`，`../../imagegen/batch1/` 的 B1、B2 r2、B3 原圖及候選圖 | 沿用原有 AI 來源紀錄，不聲稱為 CC0 或照片掃描。原 prompt、生成日期、原圖 hash 與處理步驟在該目錄 `manifest.json`；本輪不改任何舊檔。 |
| R1–R4 屋頂四張來源 | `sources/roof_macro_sheet.png`，2026-10-23 原生 `image_gen.imagegen` 輸出，1254×1254 RGB | **一次生成、四個面板**，不是四次獨立生成。未提供參考圖；prompt 在 `generation.json`。沒有模型 ID／seed 回傳，以 null 記錄。四個 627px 面板各內縮 2px，623px 來源裁切後縮至 512px，沒有放大假裝高解析度。 |
| A4 補漆 B | `sources/facade_repair_b.svg`，本輪為專案繪製的原創向量遮罩 | 32m 座標的階梯狀補抹、橫帶修補與跨邊界補片；沒有噪聲生成或外部圖像。原始 SVG 可編輯；PNG 由產生腳本光柵化。依專案擁有者的資產管理／散布政策使用，未另行宣告第三方開放授權。 |
| `planes/`、`textures/`、`authoring/`、`review/` | 上述來源的可重現處理、打包與示意圖 | 沿用各來源的使用條件；衍生處理不會自動產生 CC0／獨占著作權保證。預覽中的窗格是腳本繪製的說明圖，不是照片或新建築幾何。 |

AI 圖像屬 OpenAI 生成輸出，使用依適用的提供者服務條款處理；它不是附帶 stock／CC 授權的下載素材。條款參照：[Terms of Use](https://openai.com/policies/terms-of-use/)、[Business Terms](https://openai.com/policies/business-terms/)。這些連結不是本輪已查證的合約版本或訓練資料授權證明；未獨立認證輸出獨特性／權利排他性。

離線工具依賴 Pillow、NumPy，固定版本列於根目錄 `requirements-xinyi-material-masks.txt`，沒有把函式庫或字型檔打包進遊戲。預覽使用 Pillow 內附預設字型，不下載照片或字型。
