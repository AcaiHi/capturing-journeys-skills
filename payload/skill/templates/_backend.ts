// 共用的後端 mock 骨架。app 啟動就要打後端時使用；spec 只傳入覆寫，不改這個檔。
import type { Page, Route } from '@playwright/test';
import { stateAt, type Checkpoint } from './_story';

export type Handler = (route: Route, state: ReturnType<typeof stateAt>) => Promise<void> | void;

const CORS = {
  'access-control-allow-origin': '*',
  'access-control-allow-headers': '*',
  'access-control-allow-methods': '*',
};

export interface BackendOptions {
  checkpoint: Checkpoint;
  /** 這個 spec 專用的覆寫，key 為 URL 的 glob，例如 '**\/api/cart'。 */
  overrides?: Record<string, Handler>;
  /** 預先寫入 localStorage 的值（有 persist 的狀態庫）。 */
  storage?: Record<string, unknown>;
}

export async function installBackend(page: Page, opts: BackendOptions) {
  const state = stateAt(opts.checkpoint);

  // 持久化的狀態先預植；每個 test 都是新的 page，所以不會殘留上一個 test 的內容。
  if (opts.storage) {
    await page.addInitScript((entries) => {
      for (const [k, v] of Object.entries(entries)) localStorage.setItem(k, JSON.stringify(v));
    }, opts.storage);
  }

  // 沒被攔截到的 API 請求：回 404 並留下痕跡，不要讓它打到真實網路。
  await page.route('**/api/**', async (route) => {
    if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers: CORS });
    console.warn(`[mock] 未處理: ${route.request().method()} ${route.request().url()}`);
    return route.fulfill({ status: 404, headers: CORS, json: { error: 'unmocked' } });
  });

  // 檢查點的共用回應（_story.ts 的 stateAt(...).api）：URL glob -> JSON。欄位與錯誤訊息要與後端實際一致，不要自己編。
  for (const [glob, json] of Object.entries(state.api)) {
    await page.route(glob, (route) =>
      route.request().method() === 'OPTIONS'
        ? route.fulfill({ status: 204, headers: CORS })
        : route.fulfill({ headers: CORS, json }),
    );
  }

  // 這個 spec 的覆寫（後註冊的先匹配）。
  for (const [glob, handler] of Object.entries(opts.overrides ?? {})) {
    await page.route(glob, async (route) => {
      if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers: CORS });
      return handler(route, state);
    });
  }
  return state;
}
