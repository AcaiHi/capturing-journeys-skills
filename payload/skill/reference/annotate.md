# 標註

標註圖另存為 `screens/<id>.annotated.png`，**原圖不改**。框的位置來自拍攝時記錄的元素位置，版面移動後重拍，框會自動跟著元素走。

## 流程

1. spec 在 `shoot` 傳入要標註的元素，key 為標籤字母或編號：

   ```ts
   await shoot(page, '030-solver-result', {
     marks: { A: page.getByRole('button', { name: '開始求解' }), B: page.getByText('違規格數') },
   });
   ```

2. `stale.py record` 把 `screens/<id>.meta.json` 的元素位置合併進 manifest 的 `boxes`。
3. `stale.py annotate` 依 `boxes` 產生標註圖。只重做部分圖時加 `--ids a,b`。

沒有 Pillow 時先 `pip install pillow`。

## 樣式預設

- 框線要粗（2560 寬的圖約 7px），標籤字要大（約 23px、粗體）。
- 不用紅色。預設色序：藍紫 `#4C3BCF`、橘 `#E8801A`、藍 `#2A7DE1`、深紫 `#5B2A86`、洋紅 `#C2185B`、暗金 `#B8860B`。
- 同一個字母在整份文件裡固定一種顏色。
- 專案要改樣式，在 `docs/ui-inventory/annotate.style.json` 覆寫：`{"width": 7, "font": 23, "colors": ["#4C3BCF", ...]}`。
  `width` 與 `font` 的單位是**圖片像素**（以預設 2560 寬為基準），不隨倍率自動縮放。

## 注意

- 元素位置是 CSS 像素；`annotate` 會乘上 `deviceScaleFactor` 對到圖片像素，倍率由 config 讀取。
- 標籤放在框的左上角外側；超出圖片邊界時改放內側。
- 產出後打開幾張檢查框有沒有對到元素、有沒有遮住重要內容。
