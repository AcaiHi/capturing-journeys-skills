---
name: capturing-journeys
description: >
  在前端系統完成後，依使用故事（USER_STORY）從頭走到尾，把每一步畫面拍成
  尺寸一致、資料寫實的截圖，並用 manifest 記錄每張圖依賴的程式碼、資料與
  重拍穩定性，之後可偵測哪些圖過時並局部重拍。每個畫面是一個可重跑的
  Playwright 測試。當使用者說「幫我把整個系統完整截圖」「依使用故事走一遍拍照」
  「系統做完了要拍畫面」「重拍截圖」「截圖過期了嗎」「改了元件哪些圖要重拍」
  「標註截圖」，或要為已完成的前端專案建立可長期維護的畫面記錄時使用。
---

# capturing-journeys

目標：系統完成後，沿著使用故事走完整個系統，產出 **尺寸一致、資料連貫、可局部重拍**
的截圖，以及記錄每張圖來歷的 manifest。

```
docs/ui-inventory/
├─ USER_STORY.md            使用故事（拍攝的起點，圖序由它決定）
├─ facts.json               畫面上出現的人名、日期、數量，單一來源
├─ manifest.json            每張圖的類型、穩定性、依賴、標註框
├─ inventory.md             由 manifest 產生的圖片清單（不手寫）
├─ playwright.config.ts     視窗大小 x 倍率 = 圖片尺寸
├─ states/
│  ├─ _shoot.ts             shoot()：拍整頁、記錄文字與標註框
│  ├─ _story.ts             讀 facts.json，定義各檢查點的資料狀態
│  ├─ _backend.ts           共用的後端 mock（需要時）
│  └─ <chapter>.spec.ts     每章一個檔，每個畫面一個 test()
└─ screens/<id>.png         截圖（另有 <id>.meta.json、<id>.annotated.png）
```

指令都在工作區根目錄執行，Playwright 一律加 `-c docs/ui-inventory`。
腳本：`python .claude/skills/capturing-journeys/scripts/stale.py <子命令>`，只需要 Python 3.9 以上的標準庫；
標註與差異比較另需 Pillow（`pip install pillow`）。

目錄：[拍攝](#拍攝複製這份-todo-清單並逐項勾選) · [重拍](#重拍複製這份-todo-清單) · [何時問使用者](#要停下來問使用者的時機) · [發現 app 問題](#發現-app-問題) · [注意事項](#注意事項) · [更多](#更多)

## 拍攝：複製這份 todo 清單並逐項勾選

```
拍攝進度：
- [ ] 1. 故事：讀或撰寫 USER_STORY.md
- [ ] 2. 清單：由故事導出圖清單，標類型與穩定性，等使用者確認
- [ ] 3. 環境：選資料來源與檢查點，把事實放進 facts.json
- [ ] 4. 拍攝：寫 spec 並拍攝（靜態圖或錄影）
- [ ] 5. 驗收：逐張看圖、連跑 3 次、查重複圖
- [ ] 6. 登錄：stale.py record、標註、stale.py inventory
- [ ] 7. 回報：列出警告、volatile 的圖、略過的圖
```

**1. 故事** — 沒有 `USER_STORY.md` 就先和使用者一起寫。每個要拍的畫面都要在故事裡被提到。寫法見 [reference/story.md](reference/story.md)。

**2. 清單** — 逐項列出 id、一句中文圖說、`kind`、`stability`，等使用者確認後才開始拍。
使用者已經預先確認清單，或明說這是非互動執行、不要停下來問時，視為已確認，把清單寫進回報再往下做。
清單階段就要判斷每張圖重拍後會不會變（演算法結果、LLM、時間、非同步），標 `volatile`，不要等重拍時才發現。
使用者確認後，把這份清單寫成 `manifest.json` 的 `screens`（`id`、`chapter`、`caption`、`kind`、`stability`、`entry`、`checkpoint`、`needs`…）；`inputs`、`textHash`、`boxes` 由 `record` 填。欄位定義與完整範例見 [reference/stale.md](reference/stale.md)。

**3. 環境** — 圖與圖要連貫，所以先決定資料來源：真實系統一次走完、有狀態 mock、或簡單 mock。
畫面上出現的人名、日期、數字只能從 `facts.json` 讀，不准寫死在 spec。
同時把 `playwright.config.ts` 調到能直接跑：確認 `baseURL`；要用本機 Chrome 就取消 `channel: 'chrome'` 的註解；沒有伺服器在跑就取消 `webServer` 的註解。細節見 [reference/environment.md](reference/environment.md)。

**4. 拍攝** — `states/_shoot.ts`、`_story.ts`、`_backend.ts` 已由 sync 建立，直接 import；spec 的寫法範本在 `.claude/skills/capturing-journeys/templates/state.spec.ts`。規則：
- 每個畫面一個 `test('<id>：<圖說>')`，`<id>` 為 kebab-case，全專案唯一，同時是檔名。
- 一律用 `shoot(page, '<id>')`，拍整個視窗，不拍 `fullPage` 或單一元素，所有圖才會是同樣尺寸。內容在畫面下方就先捲過去。
- 拍之前先斷言這個畫面獨有的東西（步驟標題、頁面標題），不要只檢查網址；頁面可能轉址，拍錯頁一樣會「通過」。
  斷言的名稱若同時是其他元素文字的一部分（側邊欄、頁首也含這幾個字），要加 `exact: true`，否則 strict mode 會報多重匹配。
- 定位順序：`getByRole` / `getByText` / `getByLabel`，其次 `getByTestId`，不用 CSS class。
  側邊欄的導覽即使沒有 `href` 也常帶 `role="link"`，用 `getByRole('link', { name: '…' })`；找不到再看 DOM 是否缺可及名稱。圖示按鈕沒有可及名稱時，可加 `aria-label`（見下方「發現 app 問題」）。
- 要標註的元素在 `shoot` 的 `marks` 傳入：key 是標籤（`A`、`B`…），值是該元素的 Locator。位置是拍攝當下從元素實際量出來的，不寫死座標，所以版面移動後重拍，框會跟著元素走。
- 拍不到的畫面（原生對話框、選檔視窗、跨網域 iframe）用 `test.skip('<id>：…')` 並註明原因，仍留在清單。
- 要看到「過程」的畫面（AI 逐步回覆、動畫）改用錄影，見 [reference/recording.md](reference/recording.md)。
- 派子代理平行拍攝時照 [reference/delegating.md](reference/delegating.md)。

指令：`npx playwright test -c docs/ui-inventory states/<chapter>.spec.ts --update-snapshots --retries=0`

**5. 驗收** —
- 逐張打開 PNG，確認是對的畫面、資料看起來真實。這是唯一能抓出拍錯頁或佔位資料的檢查。
- 不加 `--update-snapshots` 連跑 3 次，輸出出現 `flaky` 或間歇失敗代表少了等待，補等待，不靠重試。
  volatile 的圖在這種執行裡只跑守門斷言、不比對像素，所以連跑 3 次通過只代表守門斷言穩定，不代表畫面正確；它們是否正確只能靠人工看圖。重拍（`--update-snapshots`）時則會直接覆寫舊圖，不會失敗。
- `python .../stale.py dups` 找像素完全相同的圖，確認是否重複。
- 穩定化手法見 [reference/stability.md](reference/stability.md)。

**6. 登錄** — 依序執行 `stale.py record`（寫入依賴雜湊與標註框）、`stale.py annotate`（需要標註時，見 [reference/annotate.md](reference/annotate.md)）、`stale.py inventory`。

**7. 回報** — 列出新增的畫面、略過的畫面、所有警告，並**明確點出每一張 volatile 的圖**，提醒使用者它重拍後可能不同，需要人工確認。

## 重拍：複製這份 todo 清單

```
重拍進度：
- [ ] 1. 偵測：stale.py check，依章節看哪些圖過時及原因
- [ ] 2. 備份：stale.py backup（把現有 PNG 存到 .before/）
- [ ] 3. 重拍：先刪要重拍的 PNG，再 --update-snapshots --retries=0 重拍受影響的章節
- [ ] 4. 比較：stale.py compare，依差異比例排序
- [ ] 5. 看圖：自己打開差異大的圖與所有 volatile 的圖（Read），確認是對的畫面
- [ ] 6. 把關：不帶 --update-snapshots 整套跑一次，失敗的圖補進重拍範圍
- [ ] 7. 登錄：stale.py record、annotate、inventory
- [ ] 8. 回報：點名需要使用者過目的圖（volatile 與差異大的）
```

非互動執行只是不停下來問使用者，**不代表可以省略步驟**：第 5、6 步一樣要做，需要使用者確認的圖留在第 8 步的回報裡。

- 順序固定：先 `backup`，再刪要重拍的 PNG，最後重拍。刪的是 `docs/ui-inventory/screens/<id>.png`，只刪要重拍那幾張，`.meta.json` 與 `.annotated.png` 不用刪。每次 `backup` 都會清掉並覆蓋上一次的 `.before/`。`--update-snapshots` 不會覆蓋差異低於容許值的舊圖，圖會顯示成「已更新」但其實沒變。
- 單張重拍：刪該 PNG，`-g <id> --update-snapshots --retries=0`，再 record 與 annotate。
- 範圍：以 `check` 的輸出為起點，不憑印象縮小。`check` 列出超過一半的圖，或改的是頁首、側邊欄、全域樣式這類全站元素，就直接整套重拍，不逐章挑。
- `check` 是預測，不是保證：它看不到 spec 裡的斷言文字、全域樣式、不在 import 圖裡的資源。所以改完後另外整套跑一次 `npx playwright test -c docs/ui-inventory`（不加 `--update-snapshots`）當作把關；若出現「畫面文字與上次拍攝不同」，該圖就是過時，補進重拍範圍。
- `compare` 的差異比例只用來排序：`check` 列為過時的圖，即使差異很小（只改了幾個字）也要看，不能因為比例低就自動接受。
- 偵測原理與輸出判讀見 [reference/stale.md](reference/stale.md)。

## 要停下來問使用者的時機

- 圖清單完成時（第 2 步，確認後才拍）。
- 故事缺資訊：主角、單位、日期、要完成什麼。
- 啟動指令或 port 不明、資料來源要選真實系統還是 mock（尤其是沒有快照可還原時）。
- 想固定演算法的亂數種子或改 app 其他行為。
- 重拍完成後：volatile 的圖與差異大的圖請使用者過目。

## 發現 app 問題

- 畫面暴露 app 本身的 bug（錯誤訊息沒顯示、文字重疊、資料不一致）：照實拍，在 spec 加 `// BUG:` 註解，manifest 該筆填 `warn`，回報並**詢問使用者要不要修**。不擅自改 app 程式，也不讓 spec 去斷言你希望的行為。
- 唯一可直接做的 app 改動是不影響行為的定位輔助（例如給圖示按鈕加 `aria-label`）；做了就在回報裡逐條列出檔案與原因。

## 注意事項

- 看到 `A snapshot doesn't exist ... writing actual`：先刪了 PNG 再重拍就會出現，是正常的，不是錯誤。
- 看到 `[mock] 未處理: GET ...`：共用 mock 對沒有被登記的 API 回 404 並留下痕跡。該畫面本來就不需要那個請求（例如未登入時的 `/api/me`）就可以忽略；畫面不對時才回頭補 mock。
- 字型渲染隨作業系統不同：Windows 與 Linux 的圖不會一樣。一組圖盡量在同一台機器、同一套字型下拍完。
- Canvas、WebGL、影片會每次略有不同，用 `mask` 遮蓋。
- 改 spec 用 Edit 工具或整檔重寫，不要用腳本切字串，容易弄壞語法。
- `.claude/skills/capturing-journeys` 是指向本體的連結。所有指令都從工作區根目錄下，不要 `cd` 進這個連結再用 `../` 回去（會被解析到本體的真實路徑而跑偏）。
- 同一個 session 中途剛 sync 的 skill 不會被載入；這時直接讀 `.claude/skills/capturing-journeys/SKILL.md`，腳本路徑不變。

## 更多

- 故事與清單：[reference/story.md](reference/story.md)
- 資料來源、檢查點、mock：[reference/environment.md](reference/environment.md)
- 穩定性與拍前整理：[reference/stability.md](reference/stability.md)
- manifest 與過時偵測：[reference/stale.md](reference/stale.md)
- 錄影：[reference/recording.md](reference/recording.md)
- 標註：[reference/annotate.md](reference/annotate.md)
- 派子代理：[reference/delegating.md](reference/delegating.md)
