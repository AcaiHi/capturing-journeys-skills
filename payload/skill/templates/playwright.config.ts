// capturing-journeys — 專案 {name} 的畫面截圖
// 執行：npx playwright test -c docs/ui-inventory
import { defineConfig, devices } from '@playwright/test';

// 每張圖的尺寸都是 VIEWPORT x SCALE（預設 1280x800 x 2 = 2560x1600）。只改這兩個常數。
const VIEWPORT = { width: 1280, height: 800 };
const SCALE = 2; // 2 = 印刷與 PDF 清楚；1 = 檔案較小

// baseURL 已依專案偵測為 {baseURL}，請確認是否為實際的 port。
const BASE_URL = process.env.SCREENS_BASE_URL ?? '{baseURL}';

export default defineConfig({
  testDir: './states',
  snapshotPathTemplate: '{testDir}/../screens/{arg}{ext}',
  // 拍攝一律不重試：出現 flaky 代表 spec 少了等待，要補等待而不是靠重試。
  retries: 0,
  outputDir: './test-results',
  reporter: [['list'], ['html', { outputFolder: './report', open: 'never' }]],
  use: {
    baseURL: BASE_URL,
    // 固定語系與時區，日期在任何機器上顯示一致；請設成使用者所在地區。
    locale: 'zh-TW',
    timezoneId: 'Asia/Taipei',
    // 沒有安裝 Playwright 瀏覽器時，取消下一行註解使用本機 Chrome：
    // channel: 'chrome',
  },
  expect: {
    // 容許誤差刻意設得很小：太寬會讓只改幾個字的畫面偵測不到。
    // 畫面文字另由 shoot() 的文字雜湊把關。
    toHaveScreenshot: { animations: 'disabled', caret: 'hide', scale: 'device', maxDiffPixels: 20 },
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: VIEWPORT, deviceScaleFactor: SCALE } },
  ],
  // 讓 Playwright 自己啟動伺服器（已在跑的會沿用）。擇一，取消註解：
  // 開發伺服器：
  // webServer: { command: 'npm run dev', url: BASE_URL, reuseExistingServer: true, cwd: '../..' },
  // 專案不允許用 dev server 時，先 build 再 preview（忘了 build 會拍到舊畫面）：
  // webServer: { command: 'npm run build && npm run preview', url: BASE_URL, reuseExistingServer: true, cwd: '../..', timeout: 180_000 },
});
