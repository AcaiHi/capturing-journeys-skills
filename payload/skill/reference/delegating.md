# 派子代理拍攝

畫面多時可以平行派子代理。規則：

## 派工時必須交代

- 要使用 `capturing-journeys` skill，並給 SKILL.md 與 reference 的路徑；子代理不得沿用其他專案的舊截圖腳本。
- 已確認的圖清單（負責哪幾張 id）與 `facts.json` 的位置。**事實由主代理先定好、寫進 `facts.json` 再派工**，子代理只讀不改（多個子代理同時改同一個檔會互相覆蓋）。
- 每個子代理另外寫自己的 manifest 草稿（例如 `docs/ui-inventory/_parts/<名稱>.manifest.json`，一個陣列），由主代理合併進 `manifest.json`，子代理不直接改 `manifest.json`，也不執行 `record`、`inventory`、`annotate`。
- 開發伺服器由主代理先啟動，子代理共用，不各自啟動（同時啟動同一個 port 會互相衝突）。
- 啟動方式：baseURL、是否要先 build、API 是否跨網域、persist 的 key。
- 可不可以改 app 程式（預設不可，只允許不影響行為的定位輔助，並要回報）。
- 可不可以安裝套件。
- 輸出位置：每個子代理有自己的輸出資料夾與自己的 spec 檔，需要特殊回應就在自己的 spec 內覆寫，**不直接修改共用的 `_backend.ts`**。

## 子代理的回報

只回報路徑與一行摘要：拍了哪些圖、略過哪些、有哪些警告、有哪些 volatile。不要貼內容。

## 主代理收回後

- 合併各子代理的成果：圖、`<id>.meta.json`、manifest 草稿。
- 至少抽看每個子代理的圖，**所有有警告與 volatile 的圖都要看**。
- 執行 `stale.py dups`、連跑 3 次、`record`、`inventory`。
- 子代理的 spec 若各自重複寫了同樣的 mock 設定，整併回共用 mock。
- 子代理專用的資料（例如只有某一章才用到的 `/api/nurses`）先留在它自己 spec 的 `overrides`，因為它不能改共用的 `_story.ts`；全部收回後，由主代理決定哪些要搬進 `_story.ts` 的 `stateAt(...).api`。

## 提醒

- 子代理的 prompt 要寫出規則本身（拍整頁、先斷言再拍、事實來自 facts.json、先刪 PNG 再重拍），不要只說「照 skill 做」，因為子代理可能讀不到剛裝好的 skill。
- 拍攝到一半，若使用者決定整個介面要重做，先停下來，已拍的圖封存到 `screens/_archive/`，不要直接刪。
