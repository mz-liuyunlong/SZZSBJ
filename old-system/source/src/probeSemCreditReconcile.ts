/**
 * probeSemCreditReconcile.ts — 探针19：SEM返还(AD_CREDIT)是否同时出现在店铺账单(statement)中
 *
 * 背景（2026-08-11 需求方追问）：SEM账单历史CSV里有两笔 AD_CREDIT 返还
 *   ① $50  "Pro Seller Instant Credit"     Billing 2026-08-05
 *   ② $500 "Spend to get reimbursement"    Billing 2026-08-08
 * 若 statement 的 sem 类目已是净额（扣费−返还），或返还另有正数行，则报表层再按CSV冲减一次=重复计算。
 * 本探针拉 statement/list（按入账日期，探针18h验证的100%完整路径）2026-08-01~2026-08-11，
 * 找出：sem类目逐日金额、|amount|∈{50,500}的行、type/desc含sem/credit/reimburs/advertis的行。
 *
 * ★ 零写入：不写任何表（不留RAW）；只调只读接口 + SELECT。
 *
 * 用法：npx ts-node src/probeSemCreditReconcile.ts [--startDate=2026-08-01] [--endDate=2026-08-11] [--store=SID]
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

// SEM账单CSV基准（发票日=扣费入账预期日；花费日≈发票日-2）
const CSV_REF: Record<string, string> = {
  "2026-08-01": "DEBIT $36.91", "2026-08-02": "DEBIT $43.04", "2026-08-03": "DEBIT $43.29",
  "2026-08-04": "DEBIT $54.33", "2026-08-05": "DEBIT $35.16 + AD_CREDIT $50",
  "2026-08-06": "DEBIT $29.45", "2026-08-07": "DEBIT $31.18",
  "2026-08-08": "DEBIT $55.16 + AD_CREDIT $500", "2026-08-09": "DEBIT $48.10",
  "2026-08-10": "DEBIT $291.71", "2026-08-11": "DEBIT $304.43",
};

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
  const startDate = getArg("startDate", "2026-08-01");
  const endDate = getArg("endDate", "2026-08-11");
  const storeFilter = getArg("store");

  console.log("═".repeat(70));
  console.log(`  探针19：statement里的SEM扣款与疑似返还  ${startDate} → ${endDate}`);
  console.log("═".repeat(70));

  const db = await mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1", port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "", password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data", dateStrings: true,
  });
  const client = new LingxingClient(loadConfig());

  // 参照1：已入库的sem类目账期聚合
  const [semAgg] = await db.execute(
    `SELECT store_id, period_start, period_end, SUM(amount) AS amt, SUM(txn_count) AS cnt
       FROM fact_reconciliation_item WHERE fee_category='sem'
      GROUP BY store_id, period_start, period_end ORDER BY period_start`,
  );
  console.log("\n【参照】fact_reconciliation_item 已入库sem类目（账期级）：");
  for (const r of semAgg as Array<Record<string, unknown>>) {
    console.log(`  ${r.store_id}  ${r.period_start}~${r.period_end}  $${Number(r.amt).toFixed(2)}  (${r.cnt}笔)`);
  }

  const [storeRows] = await db.execute(
    `SELECT store_id, store_name FROM dim_store_config WHERE platform='walmart'${storeFilter ? " AND store_id=?" : ""}`,
    storeFilter ? [storeFilter] : [],
  );
  const stores = storeRows as Array<{ store_id: string; store_name: string }>;
  console.log(`\n店铺数: ${stores.length}`);

  const RE_SUSPECT = /sem|advertis|credit|reimburs|campaign/i;

  for (const store of stores) {
    console.log(`\n──── ${store.store_name} (${store.store_id}) ────`);
    const semDaily: Record<string, { amt: number; cnt: number }> = {};
    const suspects: Array<Record<string, unknown>> = [];
    const amountHits: Array<Record<string, unknown>> = [];
    const combos: Record<string, { amt: number; cnt: number }> = {};
    let total = 0;

    for (let d = startDate; d <= endDate; d = addDays(d, 1)) {
      const rows = await pullDay(client, store.store_id, d);
      total += rows.length;
      for (const r of rows) {
        const tType = toStr(r.transactionType);
        const desc = toStr(r.transactionDescription);
        const combo = `${tType}|${desc}`;
        const amt = toNum(r.amount);
        if (tType !== "PaymentSummary") {
          if (!combos[combo]) combos[combo] = { amt: 0, cnt: 0 };
          combos[combo].amt += amt; combos[combo].cnt += 1;
        }
        if (combo === "Campaigns|SEM Marketing") {
          if (!semDaily[d]) semDaily[d] = { amt: 0, cnt: 0 };
          semDaily[d].amt += amt; semDaily[d].cnt += 1;
        } else if (RE_SUSPECT.test(combo)) {
          suspects.push({ day: d, ...r });
        }
        if (Math.abs(Math.abs(amt) - 50) < 0.01 || Math.abs(Math.abs(amt) - 500) < 0.01) {
          amountHits.push({ day: d, ...r });
        }
      }
      await sleep(DELAY_DAY_MS);
    }

    if (total === 0) { console.log("  （该窗口无statement明细，可能账期未结算）"); await sleep(DELAY_STORE_MS); continue; }
    console.log(`  明细总行数: ${total}`);

    const semDays = Object.keys(semDaily).sort();
    if (semDays.length) {
      console.log("  ◆ sem类目(Campaigns|SEM Marketing)逐日：");
      for (const d of semDays) {
        console.log(`    ${d}  $${semDaily[d].amt.toFixed(2)}  (${semDaily[d].cnt}笔)   CSV基准: ${CSV_REF[d] ?? "-"}`);
      }
      const semSum = semDays.reduce((s, d) => s + semDaily[d].amt, 0);
      console.log(`    窗口合计: $${semSum.toFixed(2)}`);
    } else {
      console.log("  ◆ 窗口内无sem类目行");
    }

    if (suspects.length) {
      console.log(`  ◆ 疑似SEM/返还相关行(非sem类目, 关键词命中) ${suspects.length} 条：`);
      for (const s of suspects.slice(0, 20)) {
        console.log(`    ${JSON.stringify(s).slice(0, 400)}`);
      }
    }
    if (amountHits.length) {
      console.log(`  ◆ |金额|=50或500的行 ${amountHits.length} 条（找返还的关键证据）：`);
      for (const s of amountHits.slice(0, 20)) {
        console.log(`    ${JSON.stringify(s).slice(0, 500)}`);
      }
    } else {
      console.log("  ◆ 无|金额|=50/500的行");
    }

    const comboKeys = Object.keys(combos).sort();
    console.log(`  ◆ 窗口内全部 type|desc 组合（${comboKeys.length}种）：`);
    for (const k of comboKeys) {
      console.log(`    ${k}  $${combos[k].amt.toFixed(2)}  (${combos[k].cnt}笔)`);
    }
    await sleep(DELAY_STORE_MS);
  }

  await db.end();
  console.log("\n探针19完成。");
}

main().catch((err) => { console.error("探针失败：", err); process.exit(1); });
