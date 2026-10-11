---
name: capturing-journeys-build
description: >
  把 capturing-journeys skill 一個指令裝進目前的前端專案，或修復壞掉的連結：建立
  .claude/skills/capturing-journeys 連結（Windows 用 junction），並建立
  docs/ui-inventory/ 骨架。當使用者說「/capturing-journeys-build sync」「把
  capturing-journeys 裝進這個專案」「sync capturing-journeys」，或專案的
  .claude/skills/capturing-journeys 不存在或失效時使用。本 skill 只負責安裝，不負責拍攝。
---

# capturing-journeys-build

`capturing-journeys` 的本體只放在 `payload/skill/`（刻意不是 skill 目錄，所以不會在沒有
選用它的專案裡被觸發）。每個工作區用目錄連結指向它，並各自擁有 `docs/ui-inventory/`。

## `sync`

在**前端專案根目錄**（`package.json` 所在）執行，並把輸出轉述給使用者：

```
python "~/.claude/skills/capturing-journeys-build/scripts/build.py" sync --workspace .
```

可重複執行，既有檔案不覆蓋，只刷新規則區塊。它會：

1. 建立或修復 `.claude/skills/capturing-journeys` 連結；真實資料夾會先移到 `.bak-<日期>`。
2. 建立 `docs/ui-inventory/`：`playwright.config.ts`、`manifest.json`、`facts.json`、`USER_STORY.md`、`states/_shoot.ts`、`states/_story.ts`、`states/_backend.ts`、`.gitignore`。
   `{name}` 依序取 `package.json` 的 name、git 根目錄名；`baseURL` 依 vite 設定或框架預設偵測。
3. 在 `CLAUDE.md` 與 `AGENTS.md`（有哪個用哪個，都沒有就建立 `CLAUDE.md`）寫入規則區塊，標記為 `<!-- capturing-journeys:begin/end -->`；標記外的文字不動。
   工作區在 git 根目錄的子資料夾時，也會在根目錄的 `CLAUDE.md` 補一段指向它的指標。
4. 檢查連結是否被 `.gitignore` 排除（Windows 上 git 會透過 junction 把內容一起 commit），並檢查是否缺 `@playwright/test`。

第一次 sync 之後，告訴使用者：

- 缺 Playwright 時：`npm i -D @playwright/test`；不想下載瀏覽器就在 config 加 `channel: 'chrome'`。
- 確認 `docs/ui-inventory/playwright.config.ts` 的 `baseURL`、`locale`、`timezoneId`。
- 警告連結沒被忽略時，把輸出提示的那一行加進 `.gitignore`。
- 新裝的 skill 要**開一個新的 session** 才會載入；舊 session 可以直接讀 `.claude/skills/capturing-journeys/SKILL.md`。

## 修改本體

只改 `payload/skill/`，所有已連結的工作區立即生效。改了 `templates/agent-block.md` 的話，各專案要重新 `sync` 才會刷新規則區塊。
