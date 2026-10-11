// shoot()：拍整個視窗，並把畫面文字雜湊與標註框寫進 screens/<id>.meta.json。
// stale.py record 會把 meta 合併進 manifest.json。
import { expect, test, type Locator, type Page } from '@playwright/test';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

export interface ShootOptions {
  /** 要標註的元素，key 為標籤（A、B、C… 或 1、2…）；位置會記成 CSS 像素。 */
  marks?: Record<string, Locator>;
  /** 內容重拍後本來就會變（演算法、LLM…）：不做文字雜湊比對。要與 manifest 的 stability 一致。 */
  volatile?: boolean;
}

/** 拍前整理：字型載入完成、清掉 hover 與 focus。 */
export async function settle(page: Page) {
  await page.evaluate(() => (document as any).fonts?.ready);
  await page.mouse.move(0, 0);
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur?.());
}

/** 內容在內層捲動容器時，捲那個容器並預留 16px，標題才不會被裁切。 */
export async function scrollInto(page: Page, locator: Locator, margin = 16) {
  await locator.evaluate((el, m) => {
    let p: HTMLElement | null = el.parentElement;
    while (p && p.scrollHeight <= p.clientHeight) p = p.parentElement;
    const box = el.getBoundingClientRect();
    if (p) p.scrollTop += box.top - p.getBoundingClientRect().top - m;
    else window.scrollBy(0, box.top - m);
  }, margin);
}

export async function shoot(page: Page, id: string, opts: ShootOptions = {}) {
  await settle(page);
  const info = test.info();
  const screens = path.resolve(info.project.testDir, '..', 'screens');
  const metaFile = path.join(screens, `${id}.meta.json`);
  // Playwright 預設是 'missing'（只補沒有的圖），不算更新；只有 all / changed 才是在重拍。
  const mode = info.config.updateSnapshots;
  const updating = mode === 'all' || mode === 'changed';

  const text = await page.evaluate(() => document.body.innerText.replace(/\s+/g, ' ').trim());
  const textHash = createHash('sha1').update(text).digest('hex').slice(0, 16);

  if (!updating && !opts.volatile && fs.existsSync(metaFile)) {
    const prev = JSON.parse(fs.readFileSync(metaFile, 'utf8'));
    expect(textHash, `${id}：畫面文字與上次拍攝不同（即使像素差異在容許值內），這張圖可能已過時`).toBe(prev.textHash);
  }

  // volatile 的圖內容每次不固定：不帶 --update-snapshots 時只跑守門斷言、不比對像素，
  // 這樣連跑 3 次與整套檢查才不會必然失敗；是否正確靠人工看圖。
  // 圖還不存在時一定要拍，不然 volatile 的圖永遠不會有第一張。
  if (updating || !opts.volatile || !fs.existsSync(path.join(screens, `${id}.png`))) {
    await expect(page).toHaveScreenshot(`${id}.png`);
  }

  if (updating || !fs.existsSync(metaFile)) {
    const boxes: Record<string, { x: number; y: number; width: number; height: number }> = {};
    for (const [key, loc] of Object.entries(opts.marks ?? {})) {
      const b = await loc.boundingBox();
      if (!b) throw new Error(`${id}：標註元素 ${key} 找不到或不可見`);
      boxes[key] = { x: b.x, y: b.y, width: b.width, height: b.height };
    }
    fs.mkdirSync(screens, { recursive: true });
    fs.writeFileSync(metaFile, JSON.stringify({ id, textHash, boxes }, null, 2));
  }
}
