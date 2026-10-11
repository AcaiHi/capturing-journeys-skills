# 錄影

靜態截圖看不出「過程」（AI 逐步回覆、處理中的動畫）時，改用 Playwright 錄影。manifest 該筆填 `capture: "recording"`。

## 先決條件

Playwright 的錄影需要它自己的 ffmpeg，**即使 config 用的是 `channel: 'chrome'`（本機 Chrome）也一樣**。沒裝會直接失敗，訊息會叫你執行：

```
npx playwright install ffmpeg
```

只下載 ffmpeg 這一個元件（約 2 MB），不是整套瀏覽器。

## 錄影

在 spec 檔案頂端指定，**一定要寫明 size**：

```ts
test.use({ video: { mode: 'on', size: { width: 1280, height: 800 } } });
```

- 不寫 size 時，錄影會被縮成 800x500（長邊上限 800），細節看不清楚。
- size 要和 config 的視窗大小（`VIEWPORT`）一致，否則畫面會被裁切或縮放。
- 錄影檔在 `docs/ui-inventory/test-results/<測試名稱>/video.webm`，每次執行會被清掉，要保留就自己複製出去。
- 內建錄影是 25fps、尺寸為 CSS 像素大小（1280x800）；要更高解析度或更高幀率，得自己逐格截圖組合，這裡沒有現成做法。

## mock 要模擬耗時

mock 回覆太快，處理步驟會一閃而過、來不及顯示。讓 mock 在回覆前等一下，過程才看得見：

```ts
'**/api/solve': async (route) => {
  await new Promise((resolve) => setTimeout(resolve, 1500));
  await route.fulfill({ json: { violations: 0, adjusted: ['王志豪'] } });
},
```

固定時鐘（`page.clock.setFixedTime`）不影響這段 `setTimeout`，因為它跑在 Node 端，不是頁面裡。

## 後製

- 反問、回答、套用這類互動拆成幾段時，接起來要像一段連續的流程，中間有斷點會像沒回答就換了一句話。整段一次錄。
- 錄下來的檔案關鍵影格很少；倍速播放或剪接時會一直跳格，有些工具還會報 `No frame found`。重新編碼成每一格都是關鍵影格：

  ```
  <ffmpeg> -i video.webm -c:v libvpx-vp9 -g 1 -b:v 2M out.webm
  ```

  可用的 ffmpeg 就是剛裝的那個：`%LOCALAPPDATA%\ms-playwright\ffmpeg-<版本>\ffmpeg-win64.exe`（macOS / Linux 在 `~/.cache/ms-playwright/` 底下）。
  它是精簡版，只有 `libvpx-vp9`，沒有 `libvpx`、`libx264`；需要其他編碼器請另外安裝完整的 ffmpeg。
- 重新編碼這步寫成腳本，不要每次手動做。

## 穩定性

錄影的內容幾乎都是 volatile（`llm`、`async`），重拍後一定請使用者人工看過，並依實際內容核對任何引用其文字或數字的說明。
