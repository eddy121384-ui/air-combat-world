# Ace to Ace — original NPR assets

`cloud-atlas.png`：1024 × 512 RGBA，四格各 512 × 256。低雲、雲塔與不對稱雲冠，
以奶油色亮面、珍珠灰中間調及藍紫色陰影組成，含輕微筆觸與透明邊緣。

來源是本原型的 [`tools/generate-lookdev-clouds.py`](../../tools/generate-lookdev-clouds.py)，
由固定種子的橢圓距離場、分階色塊與程序噪聲產生。沒有使用外部圖片、網路下載、
使用者參考圖的像素，或第三方美術素材；沒有外部圖像授權依賴。

重新產生（只有作者工具需要 Python、NumPy 與 Pillow；遊戲不需要）：

```sh
python tools/generate-lookdev-clouds.py
```

本次生成環境：Python 3.12.14、NumPy 2.3.5、Pillow 12.3.0。
PNG 約 185 KiB；RGBA 解碼加完整 mip chain 約 2.67 MiB。
四格均留透明邊，避免 mipmap 採到相鄰雲形；透明 texel 保留淡灰 RGB 以減少黑邊。
僅供 Ace to Ace 小型風格實驗使用，並不定義 Skyfront Homeland 主專案美術方向。
