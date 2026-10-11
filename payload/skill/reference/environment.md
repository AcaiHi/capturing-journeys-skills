# 資料來源、檢查點與 mock

## 目錄
- 選資料來源
- facts.json：畫面事實的單一來源
- 檢查點
- _backend.ts：共用 mock
- 探查 app 的啟動行為
- 固定時鐘的副作用
- 啟動方式與瀏覽器
- 字型
- 登入

## 選資料來源

圖與圖之間的資料要連貫（前面登入 A，後面也要是 A）。依下表選：

| 情況 | 做法 | 重拍成本 |
|---|---|---|
| 流程長、圖與圖有關聯，系統能完整跑起來 | 真實系統一次走完 | 沒有快照可還原就得整條重跑 |
| 流程長，但要避開真實資料或系統不易啟動 | 有狀態 mock：全部資料由 `facts.json` 與 `_story.ts` 產生 | 低，可整章重拍 |
| 單張獨立畫面 | 簡單 `page.route(...).fulfill(...)` | 最低 |

- 真實系統想支援整章重拍，需要種子腳本或資料庫快照來還原檢查點；沒有的話，在 manifest 把這些圖標成同一條 chain，只能整條重拍。
- 畫面上的資料要寫實（真實的名稱、金額、日期，使用者的語言），不出現 test、foo、asdf、123。
- 敏感資料（人名等）要去識別化或遮蔽，遮完再拍。

mock 與真實系統的差異是最常見的錯誤來源，所以：
- mock 的欄位數、欄位名稱、錯誤訊息從後端的單一定義讀取，不在 mock 裡自己編。
- 編來的錯誤訊息會被當成真的出現在圖裡，務必與後端實際輸出一致。
- 故事裡的資料要符合後端的業務規則（不可能存在的狀態不要拍），寫完用程式碼規則核對一遍。

## facts.json：畫面事實的單一來源

`facts.json` 是扁平的 key/value，放所有會顯示在畫面上的事實：

```json
{ "persona.name": "林雅婷", "persona.unit": "內科病房", "date.today": "2026-03-02", "count.requests": 3 }
```

- spec 與 mock 都從這裡取值，不在 spec 裡寫死。
- 改人名、日期時，只改這一處；`stale.py check` 會找出所有 `needs` 這個 key 的圖。
- 每張圖在 manifest 的 `needs` 列出用到的 key。

## 檢查點

檢查點是一個命名的資料狀態（例如 `C2`：已登入、已有 3 筆申請）。

- 每章宣告從哪個檢查點開始；章與章之間不傳遞狀態，各章從自己的檢查點出發，所以重拍第 5 章不會受第 3 章影響。
- 章內可以有順序（先新增、再編輯），用同一個 test 或 `test.describe.serial` 處理。
- `manifest.json` 的 `checkpoints` 宣告每個檢查點提供哪些前提（`provides`）；`stale.py check` 用它核對圖的 `needs`。
- 有狀態 mock：`_story.ts` 的 `stateAt('C2')` 回傳該檢查點的資料。
- 真實系統：在章首執行還原腳本。例如把還原寫成一個指令（種子腳本，或還原資料庫快照 / docker volume），在該章 spec 的 `test.beforeAll` 呼叫：

  ```ts
  import { execSync } from 'node:child_process';
  test.beforeAll(() => { execSync('npm run seed -- --checkpoint C2', { cwd: '../..', stdio: 'inherit' }); });
  ```

  還原後記得重新登入（session 可能已失效）。沒有種子腳本或快照可用，就在 manifest 把這些圖設成同一個 `chain`（例如 `"chain": "flow-main"`），`check` 會在其中任一張過時時把整條列出，只能整條重拍；並告訴使用者這個代價。
- 演算法或 LLM 的結果想讓它固定：可以固定亂數種子、或把求解器的回應 mock 成固定資料，圖就能由 `volatile` 改標 `stable`。固定種子需要改 app，先問使用者；mock 回應則用有狀態 mock 即可。

## _backend.ts：共用 mock

app 啟動就要打後端時，用一份共用 mock，spec 只傳入覆寫：

- 跨網域 API：回應要帶 CORS 標頭，並回答 `OPTIONS`。
- 沒被攔截到的請求要有明確的預設（回 404 或記錄），不要讓它打到真實網路。
- 狀態有持久化的 app（例如 Zustand persist），用 `page.addInitScript` 預先寫入 localStorage，每個 test 開頭清空。
- 共用回應放哪一層：每頁都會打的請求（登入狀態、目前使用者、清單）寫在 `_story.ts` 的 `stateAt(...).api`（URL glob 對應 JSON），由 `installBackend` 統一註冊；只有某一張圖才需要的特殊回應，才在 spec 用 `overrides`。
- 範例資料檔放 `fixtures/`；ESM 專案沒有 `__dirname`，用 `new URL('../fixtures/x', import.meta.url)`。
- 編輯類操作要把修改合併回資料，不要整份覆蓋（否則附件之類的欄位會消失）。
- 一個 spec 需要特殊回應時，在 spec 內覆寫，不改共用 mock。

## 探查 app 的啟動行為

不熟的 app，先寫一支臨時的 `zz-probe.spec.ts`：記錄它發出的請求與 console 訊息、轉址與啟動時的探測請求（例如啟動時掃描檔案）。
弄清楚後刪掉，不留在專案裡。

## 固定時鐘的副作用

`page.clock.setFixedTime(...)` 讓時間固定，日期穩定；但計時器與動畫不會前進：
- toast 不會自動消失，`toBeHidden` 會逾時；需要它消失時改用 `page.clock.install` 加 `runFor`。
- 要模擬「處理需要時間」的畫面，由 mock 控制回覆節奏，不靠真實等待。

## 啟動方式與瀏覽器

- `baseURL` 要與專案實際的 port 相符；連不上就問使用者啟動指令與 port，不要猜。
- 專案規定不能跑 dev server 時，改用 build 加 preview：先 build，再讓 `webServer` 啟動 preview。忘了 build 會拍到舊畫面。
- 沒有安裝 Playwright 瀏覽器時，可在 config 的 `use` 加 `channel: 'chrome'` 使用本機 Chrome。

## 字型

不要依賴線上字型（Google Fonts 會切片載入，每次反鋸齒略有不同，也會造成版面位移）。
字型由前端打包，或由 mock 提供同一份本機檔案；字型載入完成再拍（`shoot()` 內已等 `document.fonts.ready`）。
避免路徑綁死某台機器（例如 `C:/Windows/Fonts`）。

## 登入

帳號密碼登入寫在 `beforeEach`；SSO 或 2FA 則手動登入一次，存成 `storageState` 重複使用。
