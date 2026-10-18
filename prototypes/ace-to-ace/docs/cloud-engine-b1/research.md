# B1 渲染研究與取捨

日期：2026-10-19。空間基準為 B0 `a75ea74fcadcf73464c9aea42164dcb96b57509a`；[B0 物理研究](../cloud-engine-b0/research.md)與 `cloud-field.js` 保持原樣。B1 不增加氣象、力學、AI 感知或武器規則。

## 美術方向

參考 [京都動畫《劇場版 紫羅蘭永恆花園》官方網站](https://violet-evergarden.jp/?lang=ja)及[新海誠作品官方入口](https://www.shinkaiworks.com/)所呈現的背景美術品質，並對照專案已接受的 R2 實際畫面。以下是本次的美術判讀與設計取向，並非對製作團隊技法的事實斷言：先讀出大塊不對稱雲牆與平坦雲底，再看到細碎筆觸；亮面保留暖象牙色，暗部用藍紫而非灰黑；逆光邊緣節制，遠處降低反差。雲海需要連續長脊與空隙，不能只排列同樣大小的圓球。

原創 atlas 依 B0 所需的側面、頂面、底面和近景霧筆觸生成。沒有複製上述作品的圖像；[素材來源及 prompts](../../assets/cloud-b1/README.md)另列。生成素材及最小渲染器仍未達到電影最終美術品質。

## 最小技術比較

| 方法 | 手機成本與空間問題 | B1 決定 |
|---|---|---|
| 多方向交叉透明片 | 素材直接、頂點少；交線、側看薄片與透明重疊明顯 | 不使用交叉平面 |
| 多層固定透明切片 | 真實深度與視差；任何方向都需多層，排序與 fill-rate 難控制 | 暫不使用大量切片 |
| 密度等值殼＋投影材質 | 幾何有體積；低細節時仍像球堆，alpha 投影容易出現拼貼縫 | 實際試作並淘汰 |
| 世界錨定的分層 impostor＋淺浮雕深度 | 一次 instancing、少三角形；可用複雜手繪輪廓，任意視角外形是近似 | 選用；27 個 B0 lobe 錨點，54 三角形 |
| 遠景 billboard LOD | 便宜但近處容易露出平面 | 同一配置的次要層在 4.5–7.5 km 漸退，九個主層保留 |
| 近景密度霧 | 補足穿入厚度；稀疏視線採樣會模糊細縫 | 9 條視線、4 距離段、每段 3 點，共 108 次 CPU 查詢 |

[Three.js 透明度說明](https://threejs.org/manual/pages/transparency.html)描述了物件排序與相交透明表面的限制。[Material 文件](https://threejs.org/docs/pages/Material.html)提供 alpha hash 與 MSAA alpha-to-coverage；前者會帶雜訊，本原型選擇後者，搭配 depth test/write，讓重疊雲片用覆蓋率與深度解決，而非依每張片排序。現有 WebGL2 renderer 的 offscreen target 使用 4 samples，畫面經深度感知的單一霧 pass 合成。需真機確認 Safari 的 MSAA/depth resolve 行為；這不是完整體積半透明。

Apple 的[行動圖形效能指南（封存）](https://developer.apple.com/library/archive/documentation/3DDrawing/Conceptual/OpenGLES_ProgrammingGuide/Performance/Performance.html)強調裝置實測、簡化光照與減少不必要工作。本次只採這些一般設計原則；該文件已退役，不能當成現代 Safari 效能保證。

## 空間契約與設計化近似

- 位置、尺寸、seed、雲底／頂取自同一 B0 field；所有 anchor 不受鏡頭改變。風以 `wind × time` 平流，CPU 霧採樣亦使用同一時間。Y 向上、公尺、海面 0 不變。
- 片的朝向面對觀察點，但中心固定在世界；側／頂／底 atlas 隨仰角平滑混合。片上依筆觸亮度與大形狀計算淺浮雕深度，讓相交與遮蔽具深度差；這不等於精確的 B0 等密度表面。
- 距離片中心 650–100 m 漸退，避免眼睛跨過近片時硬切；近景霧由連續 B0 density 驅動。固定 3×3 視線、0–80–250–700–1800 m 四段積分，利用場景深度限制有效長度。這是視線積分的粗近似，T500 讀數仍直接來自原始場。
- 世界太陽方向調整暖亮面、藍紫陰影、背光邊與雲底暗部；距離增加空氣透視。素材已含光影，動態 tint 不能完整重新打光。無多重散射、光線追蹤或 B1 全螢幕 96-step ray marching。
- 霧筆觸採世界座標三向投影，避免水平飛行時 XZ 投影拉成直條。只是設計化色彩變化，沒有新增密度或改物理。

## 下一步

先在 iPhone 13 mini Safari 測半解析度、4× MSAA、深度 resolve、記憶體與十分鐘持續飛行。再增加少量真正互相對應的方位 atlas，減少同一側面圖的重複；以一致的 painter-authored 深度／法線提高重打光與側向視差。霧可改成較細但仍有上限的視線網格，依鏡頭密度調整採樣距離，避免細縫被抹平。通過這些檢查後，才評估預設關閉的正式遊戲接線。
