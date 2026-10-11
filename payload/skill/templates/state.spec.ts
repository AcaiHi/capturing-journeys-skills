// 範本：一章一個檔，每個畫面一個 test()，每個 test 從章首的檢查點出發。
import { test, expect } from '@playwright/test';
import { F, NOW } from './_story';
import { installBackend } from './_backend';
import { shoot } from './_shoot';

test.describe('第 2 章：排班', () => {
  test.beforeEach(async ({ page }) => {
    // 固定時間；注意計時器與 toast 不會前進（見 reference/environment.md）。
    await page.clock.setFixedTime(NOW);
  });

  test('020-schedule-empty：尚未建立班表', async ({ page }) => {
    await installBackend(page, { checkpoint: 'C1' });
    await page.goto('/schedule');
    // 守門：斷言這個畫面獨有的東西，轉址或拍錯頁時才會失敗。
    // 名稱會是別處文字的一部分時（側邊欄的「護理排班系統」也含「排班」），加 exact: true，否則 strict mode 會報多重匹配。
    await expect(page.getByRole('heading', { name: '排班', exact: true })).toBeVisible();
    await expect(page.getByText(String(F['persona.name']))).toBeVisible();
    await shoot(page, '020-schedule-empty', {
      marks: { A: page.getByRole('button', { name: '新增班表' }) },
    });
  });

  test('030-solver-result：求解完成後的結果', async ({ page }) => {
    await installBackend(page, { checkpoint: 'C2' });
    await page.goto('/schedule');
    await page.getByRole('button', { name: '開始求解' }).click();
    await expect(page.getByText('求解完成')).toBeVisible();
    // 內容每次不固定：volatile，不做文字雜湊比對；manifest 也要標 volatile。
    await shoot(page, '030-solver-result', { volatile: true });
  });

  // Playwright 拍不到的畫面：保留在清單，說明原因，manifest 標 kind: manual。
  test.skip('040-native-confirm：瀏覽器原生確認對話框', async () => {
    // manual: 原生 dialog
  });
});
