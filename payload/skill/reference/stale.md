# manifest 與過時偵測

## 目錄
- manifest 結構
- 每張圖的欄位
- 依賴怎麼算
- stale.py 子命令
- 判讀 check 的輸出
- 把關：差異比較

## manifest 結構

`docs/ui-inventory/manifest.json`：

```json
{
  "version": 1,
  "checkpoints": { "C0": { "provides": ["登入"] }, "C2": { "provides": ["申請R1存在"] } },
  "screens": [ { "id": "030-solver-result", "...": "..." } ]
}
```

`checkpoints` 宣告每個檢查點提供哪些前提。`screens` 的順序就是圖序。一筆完整的圖長這樣（`inputs`、`textHash`、`boxes`、`recordedAt` 由 `record` 填，其餘自己寫）：

```json
{
  "id": "030-solver-result", "chapter": 2, "caption": "求解完成後的結果", "kind": "main",
  "desc": "按下開始求解後，系統列出違規格數與被調整的人員。",
  "capture": "still", "stability": "volatile", "volatileBy": ["solver"],
  "checkpoint": "C2", "entry": "src/pages/Schedule.tsx",
  "needs": ["登入", "persona.name", "申請R1存在"], "makes": ["班表已求解"],
  "derivedFrom": [], "warn": "違規格數與下一章引用的數字需在重拍後核對"
}
```

`needs` 可以是 `facts.json` 的 key、檢查點 `provides` 裡的項目，或同一章前面某張圖的 `makes`。
實務寫法：每個檢查點的 `provides` 列出該章圖會 `needs` 的**非事實**前提（例如 `"登入"`、`"申請存在"`），事實類的需求直接寫 `facts.json` 的 key。`check` 會逐條核對，找不到來源就回報「前提無來源」。

## 每張圖的欄位

| 欄位 | 填寫者 | 說明 |
|---|---|---|
| `id`、`chapter`、`caption` | 你 | 識別、章號、一句中文圖說 |
| `kind` | 你 | `main` 主圖、`sub` 子圖、`extra` 只拍不放、`manual` 需手動截圖、`setup` 只為準備狀態 |
| `parent` | 你 | 子圖指向的主圖 id |
| `capture` | 你 | `still` 或 `recording` |
| `stability`、`volatileBy` | 你 | 見 [stability.md](stability.md) |
| `checkpoint` | 你 | 這章從哪個檢查點開始 |
| `needs`、`makes` | 你 | 需要的 / 產生的事實；`needs` 可為 `facts.json` 的 key、檢查點 `provides` 的項目，或前面某張圖的 `makes` |
| `entry` | 你 | 這張圖所屬頁面的入口檔（例如 `src/pages/Schedule.tsx`），用來展開相依檔案 |
| `chain` | 你 | 同一個值的圖只能整條重拍（真實系統沒有快照可還原時使用）；其中一張過時，整條都會被列出 |
| `derivedFrom` | 你 | 這張圖的說明引用了哪些圖的結果（id 陣列）；來源圖過時時，這張也會被列出，提醒重新核對說明 |
| `story` | 你 | 對應 USER_STORY 哪一段（章節標題或錨點） |
| `desc` | 你 | 一兩句說明這個畫面讓使用者看到什麼、為什麼；`inventory` 會放在圖下方 |
| `chapterTitle` | 你 | 章名，填在該章任一筆即可；`inventory` 用作章標題 |
| `manualReason` | 你 | `kind: manual` 的圖無法自動截圖的原因 |
| `warn` | 你 | 疑似 bug 或待確認的問題，沒有就省略 |
| `inputs` | `record` | 依賴的檔案、事實、環境的雜湊 |
| `textHash`、`boxes` | `record` | 來自 `screens/<id>.meta.json` 的畫面文字雜湊與標註框 |

新增或修改圖時，你只改「你」填的欄位；`record` 會填其餘欄位。`makes`、`needs`、`derivedFrom`、`warn` 沒有內容時可以省略，不必寫空陣列。
子代理的草稿是一個 JSON 陣列，每筆就是上面的一張圖（只含「你」填的欄位）；`checkpoints` 只寫在主 manifest，不放在草稿裡。

## 依賴怎麼算

`record` 對每張圖記錄三類輸入的雜湊：

1. **程式碼**：截圖拍的是「app 外殼加頁面」，所以依賴有兩個方向：
   - 往下：從 `entry` 沿 import 展開所有相依的原始檔與樣式（略過 `node_modules`）。型別匯入（`import type`）編譯後會消失，不算依賴。
   - 往上：所有直接或間接 import `entry` 的檔案（`App`、版型、`main`）也算，連同它們帶進來的共用外殼（例如側邊欄、全域樣式）。外殼的相依檔案若是**別張圖的入口**（別的頁面）就排除，所以改別頁不會讓這張圖過時；尚未有圖的頁面則還算在外殼裡，等它有了圖、入口被登錄，就會自動排除。
   這個範圍偏保守：共用的版型、元件或全域樣式一改，所有受影響的圖都會被列出，這是想要的結果；實際有沒有變，交給 `compare` 驗證。
2. **事實**：`needs` 中屬於 `facts.json` 的 key，各記錄其值的雜湊。
3. **環境**：`playwright.config.ts`、`@playwright/test` 版本，以及共用的 `states/_backend.ts`、`_story.ts`、`_shoot.ts`。共用 mock 或拍攝輔助一改，所有圖都會被列出。

**畫面文字**不在 `check` 裡：`shoot()` 在拍攝時比對 `textHash`，文字與上次不同就讓該 test 失敗（訊息「畫面文字與上次拍攝不同」）。所以整套跑一次不帶 `--update-snapshots`，失敗的圖就是過時。volatile 的圖不做這項比對。

路徑別名（例如 `@/` 對應 `src/`）從 `tsconfig.json` 的 `paths` 讀；讀不到時用 `--alias @=src` 指定。
沒有 `entry` 的圖只會因為事實與環境變動而被列出，`check` 會提醒補上。

## stale.py 子命令

在工作區根目錄執行：`python .claude/skills/capturing-journeys/scripts/stale.py <子命令>`

| 子命令 | 作用 |
|---|---|
| `record` | 拍完後執行：合併 `screens/*.meta.json`，重算 `inputs`，寫入 manifest |
| `check` | 比對目前雜湊與記錄，依章節列出過時的圖與原因；同時核對 `needs` 有沒有來源 |
| `merge` | 把 `docs/ui-inventory/_parts/*.manifest.json`（子代理各自寫的草稿）合併進 manifest：id 已存在的略過，新的依章號排序；合併後再 `record` |
| `inventory` | 由 manifest 產生 `inventory.md` |
| `dups` | 找出像素完全相同的 PNG |
| `backup` | 把現有 `screens/*.png` 複製到 `.before/`，重拍前使用 |
| `compare` | 比較 `.before/` 與目前的 PNG，依差異比例由大到小列出 |
| `annotate` | 依 manifest 的 `boxes` 產生 `screens/<id>.annotated.png` |

常用選項：`--ui docs/ui-inventory`（預設）、`--root .`（原始碼根）、`--alias @=src`、`--chapter <n>`。

## 判讀 check 的輸出

每筆輸出含原因：

- `檔案變更: <路徑>`：相依的原始檔變了，圖可能受影響。
- `事實變更: <key>`：`facts.json` 的值變了。
- `環境變更`：config、Playwright 版本或共用的 `_backend/_story/_shoot` 變了，全部圖都會列出。
- `前提無來源: <need>`：這張圖需要的前提，既不在 `facts.json`、檢查點，也不是前面圖產生的；補上來源，或確認該圖的前提寫對了。
- `沒有 entry`：補上入口檔，否則程式碼變更偵測不到。
- `同一 chain 的圖過時`：真實系統沒有快照可還原，整條只能一起重拍。
- `引用的圖過時`：這張圖的說明引用了過時圖的結果，重拍後要重新核對說明裡的數字或文字。
- `volatile`：另外標出，重拍後須人工過目。

`check` 是預測，列出的是**可能**受影響的圖。它的盲區：spec 裡斷言的文字、全域樣式、不在 import 圖裡的資源（圖片、字型檔）、後端回應的改變。所以改完後仍要整套跑一次不帶 `--update-snapshots` 的檢查把關，失敗的圖補進重拍範圍。

## 把關：差異比較

重拍前 `backup`，重拍後 `compare`：
差異比例只用來**排序**，不單獨決定接受：
- `check` 沒列為過時、差異又接近 0 的圖，視為沒變。
- `check` 列為過時的圖，即使差異很小（改幾個字的差異本來就小）也要看過。
- 差異大的、以及所有 volatile 的圖，請使用者逐張看。volatile 的差異偏大是正常的，不代表回歸。
- 差異出現在預期以外的圖，當成可能的回歸回報，不要直接接受。
