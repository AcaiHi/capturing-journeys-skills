## 畫面截圖（capturing-journeys）

本專案在 `docs/ui-inventory/` 以使用故事為主線記錄每個畫面：每張圖是一個可重跑的
Playwright 測試，`manifest.json` 記錄每張圖的依賴與重拍穩定性。

- 要拍整個系統、重拍、或標註時，使用 `capturing-journeys` skill；其他 agent 請讀
  `.claude/skills/capturing-journeys/SKILL.md` 並照做。
- 修改使用者看得到的畫面（元件、版型、樣式、文案）之後，收尾前執行
  `python .claude/skills/capturing-journeys/scripts/stale.py check`，把可能過時的圖與原因回報給使用者。
  **只回報，不要自動重拍或覆蓋舊圖**；是否重拍由使用者決定。
- 重拍之後，凡標為 `volatile` 的圖（結果每次可能不同），**提醒使用者人工確認**，
  並提醒引用這些圖數字或文字的說明要依新畫面重新核對。
