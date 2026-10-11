// 畫面事實與檢查點。所有會顯示在畫面上的人名、日期、數字都從 facts.json 讀，spec 與 mock 不寫死。
import fs from 'node:fs';
import path from 'node:path';

// 用 fs 讀 JSON：JSON import 在 CJS 與 ESM 專案的寫法不同（ESM 需要 import attribute），容易直接壞掉。
// 執行時工作目錄通常是專案根目錄（npx playwright test -c docs/ui-inventory），在 docs/ui-inventory 內執行也找得到。
function loadFacts(): Record<string, string | number> {
  const candidates = ['docs/ui-inventory/facts.json', 'facts.json'].map((p) => path.resolve(process.cwd(), p));
  const file = candidates.find((p) => fs.existsSync(p));
  if (!file) throw new Error(`找不到 facts.json，已找過：${candidates.join('、')}`);
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

export const F = loadFacts();

/** 固定時間：與 facts.json 的 date.today 一致。 */
export const NOW = new Date(`${F['date.today'] ?? '2026-01-01'}T09:00:00+08:00`);

export type Checkpoint = 'C0' | 'C1' | 'C2';

/**
 * 有狀態 mock：每個檢查點回傳該時間點整個系統的資料。
 * `api` 是「URL glob -> 回應 JSON」，由 installBackend 統一註冊；每頁都會打的請求（登入狀態、目前使用者、清單）寫在這裡，
 * 只有某一張圖才需要的特殊回應，才在 spec 裡用 overrides 覆寫。
 * 改人名、數量時，只改 facts.json。檢查點提供了哪些前提，要同步宣告在 manifest.json 的 checkpoints。
 * 用真實系統時，這裡改成呼叫還原腳本（種子資料或資料庫快照）。
 */
export function stateAt(cp: Checkpoint) {
  const user = { name: String(F['persona.name'] ?? '使用者'), unit: String(F['unit.name'] ?? '') };
  const api: Record<string, unknown> = {};

  if (cp === 'C0') return { user, api }; // 未登入：/api/me 沒有被 mock，會走 installBackend 的 404 預設

  api['**/api/me'] = user; // C1 起：已登入
  // api['**/api/requests'] = [{ id: 1, nurse: String(F['request.1.nurse']), day: String(F['request.1.day']) }];
  if (cp === 'C1') return { user, api };

  // C2：已有完整資料
  return { user, api };
}
