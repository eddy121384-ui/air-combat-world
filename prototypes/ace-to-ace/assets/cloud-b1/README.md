# B1 原創雲素材

兩張原始 atlas 均於 2026-10-19 依此專案需求使用內建 OpenAI `image_gen` 創作，沒有輸入、擷取或複製電影畫格、角色或第三方背景。素材供本專案的原型與衍生壓縮版本使用；此來源紀錄不主張 AI 輸出的排他著作權，也不額外附加第三方圖庫授權。

| 原始檔（1254²） | 遊戲檔（1024²） | 用途／來源 |
|---|---|---|
| [cloud-materials-b1.png](source/cloud-materials-b1.png) | [cloud-materials-b1.webp](cloud-materials-b1.webp) | RGB 滿版四視角筆觸；[完整 prompt 與生成紀錄](source/material-generation.json) |
| [cloud-silhouettes-b1.png](source/cloud-silhouettes-b1.png) | [cloud-silhouettes-b1.webp](cloud-silhouettes-b1.webp) | RGBA 側面、頂面、雲底、逆光側面；[完整 prompt](source/cloud-silhouettes-b1.prompt.txt) |

兩張都是原創生成素材，並非人手逐筆繪製。四格依左上、右上、左下、右下排列。WebGL 的 V 軸方向已在 shader 的 tile 選擇中處理。

`python tools/pack-cloud-b1.py` 使用 Pillow 重建壓縮版，不需要新的遊戲依賴。每格 496²，加 8 px guard band；剪影另有 40 px 透明邊緣衰減，避免原始 wisps 越界及 mip 串色。這是縮放、atlas packing 與 alpha 邊界處理，沒有重繪 R2 天空。深層 mip 仍可能混入鄰格，遠景 LOD 會減少細節層。

原始生成未完全遵守透明 gutter，部分邊緣有偏藍的半透明細絲；壓縮版處理了邊界，但尚非最終美術交付。最初滿版材質 prompt 提到 shell，該方案經 runtime 比較被淘汰；目前僅將此材質用於三向局部霧筆觸。

R2 的 `assets/lookdev/sky-painting-r2.jpg`、`cloud-paintings-r2.png` 完全保留；B1 素材與其分開存放。
