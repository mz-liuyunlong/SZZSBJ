/**
 * probeCommissionSaving.ts — 探针20：statement销售行的佣金折扣字段确认 + 激励中心对数
 *
 * 背景（2026-08-11 需求方）：卖家中心「激励中心」按品显示佣金折扣（如基准15%→实收3.75%，
 *   每件省$2.25），账期07-11~07-25某店合计You've saved=$12,950.71/6,808件。
 *   沃尔玛对账单CSV有 Commission Rate / Base Commission Rate / Original Commission /
 *   Commission Incentive Program / Commission Saving 五字段——需确认领星API statement行同样携带
 *   （CSV有≠API有，探针17教训），并按店铺Σ出07-11~07-25的佣金节省与激励中心页面对数。
 *
 * ★ 零写入：不写任何表；只调只读接口。
 *
 * 用法：npx ts-node src/probeCommissionSaving.ts [--startDate=2026-07-11] [--endDate=2026-07-25] [--store=SID]
 *   （区间语义=postedDate∈[startDate,endDate)，与账期归桶一致）
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const STATEMENT_PATH = "/basicOpen/multiplatformFinance/walmart/bill/statement/list";
const PAGE_SIZE = 200;
const MAX_PAGES_PER_DAY = 60;
const DELAY_PAGE_MS = 350;
const DELAY_DAY_MS = 500;
const DELAY_STORE_MS = 1500;

function getArg(name: string, def = ""): string {
  const p = `--${name}=`;
  const a = process.argv.find((x) => x.startsWith(p));
  return a ? a.slice(p.length) : def;
}
function addDays(dateStr: string, n: number): string {
  const d = new Date(dateStr + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
function toNum(v: unknown): number {
  if (typeof v === "number") return Number.isFinite(v) ? v : 0;
  const n = Number(String(v ?? "").replace(/,/g, ""));
  return Number.isFinite(n) ? n : 0;
}
function toStr(v: unknown): string { return String(v ?? "").trim(); }
function sleep(ms: number): Promise<void> { return new Promise((r) => setTimeout(r, ms)); }
function extractList(data: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(data)) return data as Array<Record<string, unknown>>;
  const d = data as { list?: unknown; data?: unknown } | null;
  if (Array.isArray(d?.list)) return d!.list as Array<Record<string, unknown>>;
  if (Array.isArray(d?.data)) return d!.data as Array<Record<string, unknown>>;
  return [];
}

async function pullDay(client: LingxingClient, storeId: string, day: string): Promise<Array<Record<string, unknown>>> {
  const rows: Array<Record<string, unknown>> = [];
  for (let page = 0; page < MAX_PAGES_PER_DAY; page++) {
    const params = { sids: [storeId], startDate: day, endDate: day, offset: page * PAGE_SIZE, length: PAGE_SIZE };
    let resp: unknown = null;
    let lastErr: unknown = null;
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        resp = await client.request<unknown>({ method: "POST", path: STATEMENT_PATH, params, timeoutMs: 60000 });
        lastErr = null;
        break;
      } catch (e) { lastErr = e; await sleep(2000 * (attempt + 1)); }
    }
    if (lastErr) { console.log(`    ⚠️ ${day} 拉取失败: ${lastErr instanceof Error ? lastErr.message : String(lastErr)}`); break; }
    const list = extractList((resp as { data?: unknown }).data);
    if (list.length === 0) break;
    rows.push(...list);
    if (list.length < PAGE_SIZE) break;
    await sleep(DELAY_PAGE_MS);
  }
  return rows;
}

async function main() {
  const startDate = getArg("startDate", "2026-07-11");
  const endDate = getArg("endDate", "2026-07-25");
  const storeFilter = getArg("store");

  console.log("═".repeat(70));
  console.log(`  探针20：佣金折扣字段确认+激励中心对数  postedDate∈[${startDate}, ${endDate})`);
  console.log("═".repeat(70));

  const db = await mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1", port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "", password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data", dateStrings: true,
  });
  const client = new LingxingClient(loadConfig());

  const [storeRows] = await db.execute(
    `SELECT store_id, store_name FROM dim_store_config WHERE platform='walmart'${storeFilter ? " AND store_id=?" : ""}`,
    storeFilter ? [storeFilter] : [],
  );
  const stores = storeRows as Array<{ store_id: string; store_name: string }>;
  console.log(`店铺数: ${stores.length}`);

  let fieldPrinted = false;
  const RE_COMM = /commis|incentive|saving/i;

  for (const store of stores) {
    console.log(`\n──── ${store.store_name} (${store.store_id}) ────`);
    let saleRows = 0, saleUnits = 0;
    const sums: Record<string, number> = {};
    const programs: Record<string, { amt: number; cnt: number }> = {};
    let commKeys: string[] = [];
    let sampleRow: Record<string, unknown> | null = null;

    for (let d = startDate; d < endDate; d = addDays(d, 1)) {
      const rows = await pullDay(client, store.store_id, d);
      for (const r of rows) {
        if (toStr(r.transactionType) !== "Sale") continue;
        saleRows++;
        saleUnits += toNum(r.shipQty);
        if (commKeys.length === 0) {
          commKeys = Object.keys(r).filter((k) => RE_COMM.test(k));
          sampleRow = r;
        }
        for (const k of commKeys) {
          const v = r[k];
          if (v == null || v === "") continue;
          const n = Number(String(v).replace(/,/g, "").replace("%", ""));
          if (Number.isFinite(n)) sums[k] = (sums[k] ?? 0) + n;
        }
        // 激励计划维度（字段名探测式：任何含incentive的字符串字段）
        for (const k of commKeys) {
          if (!/incentive|program/i.test(k)) continue;
          const prog = toStr(r[k]);
          if (!prog) continue;
          const savingKey = commKeys.find((x) => /saving/i.test(x) && !/rate|program/i.test(x));
          const amt = savingKey ? toNum(r[savingKey]) : 0;
          if (!programs[prog]) programs[prog] = { amt: 0, cnt: 0 };
          programs[prog].amt += amt; programs[prog].cnt += 1;
        }
      }
      await sleep(DELAY_DAY_MS);
    }

    if (saleRows === 0) { console.log("  （窗口内无Sale行，可能账期未结算）"); await sleep(DELAY_STORE_MS); continue; }
    if (!fieldPrinted && sampleRow) {
      fieldPrinted = true;
      console.log("  ◆ Sale行全部字段名（首店首行，供核对）：");
      console.log("    " + Object.keys(sampleRow).join(", "));
      console.log("  ◆ 佣金相关字段样本值：");
      for (const k of commKeys) console.log(`    ${k} = ${JSON.stringify(sampleRow[k])}`);
    }
    console.log(`  Sale行=${saleRows}  shipQty合计=${saleUnits}`);
    console.log("  ◆ 佣金相关字段窗口Σ（金额类才有意义，比率类Σ仅供识别用）：");
    for (const [k, v] of Object.entries(sums)) console.log(`    Σ${k} = ${v.toFixed(2)}`);
    if (Object.keys(programs).length) {
      console.log("  ◆ 按激励计划分组（saving金额Σ/行数）：");
      for (const [p, v] of Object.entries(programs)) console.log(`    ${p}: $${v.amt.toFixed(2)} (${v.cnt}行)`);
    }
    await sleep(DELAY_STORE_MS);
  }

  await db.end();
  console.log("\n探针20完成。对数方法：把各店铺Σsaving类字段与卖家中心「激励中心」同账期You've saved对照。");
}

main().catch((err) => { console.error("探针失败：", err); process.exit(1); });
