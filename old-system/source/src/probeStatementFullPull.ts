/**
 * src/probeStatementFullPull.ts
 *
 * AI财务 · 探针18e —— statement/list 无过滤全量拉取终局验证（只读，零写库，零改动生产）。
 *
 * 背景：探针18/18c/18d已证：账期头(payout)完全可信；按类型/描述过滤路径服务端不稳定
 * （确定性缺行+深分页500），不可依赖。本探针测正式同步将采用的方式：
 * **仅按 reportKey（searchType=6）无任何类型过滤，顺序分页拉整账期**。
 *
 * 三重守恒判定（全过=收入主线定稿）：
 *   ① 总行数 = settlementCount = 35,525（payout头与CSV双重印证值）
 *   ② 总净额 = totalPayable = $34,548.88
 *   ③ 逐类目(type|description) 金额/行数 = CSV基准（含Sale|Purchase $110,856.30/27,198行）
 * 另：每页失败重试3次(退避2s)；每20页打进度；首页打印data层键名+total；
 *     按 amountType 聚合前15供 fee_category 映射设计参考。
 *
 * 运行：npx ts-node src/probeStatementFullPull.ts   （约180次调用，预计2~4分钟）
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const STATEMENT_PATH = "/basicOpen/multiplatformFinance/walmart/bill/statement/list";
const REPORT_KEY = "10f51fc8cba79633";
const EXPECT_ROWS = 35525;
const EXPECT_TOTAL = 34548.88;
const CSV_BENCH: Array<[string, number, number]> = [
  ["Sale | Purchase", 110856.30, 27198],
  ["Adjustment | WFS Fulfillment fee", -39733.06, 6801],
  ["Service Fee | Walmart Product Advertising", -14430.60, 3],
  ["Service Fee | WFS InboundTransportationFee", -7238.91, 2],
  ["Service Fee | WFS InventoryRemovalOrder", -6639.50, 1],
  ["Service Fee | WFS StorageFee", -3922.52, 2],
  ["Refund | Keep-it refund", -3558.46, 940],
  ["Adjustment | WFS LostInventory", 2694.96, 2],
  ["Refund | Return Refund", -1633.89, 397],
  ["Adjustment | WFS Return Processing Fee", -821.90, 103],
  ["Service Fee | Review Accelerator", -420.00, 2],
  ["Campaigns | SEM Marketing", -342.91, 13],
  ["Adjustment | WFS FoundInventory", -170.33, 2],
  ["Refund | Seller Initiated Returns", -60.08, 12],
  ["Adjustment | WFS DamageInWarehouse", 49.08, 2],
  ["Other | WFS RC_InventoryDisposalFee", -22.05, 1],
  ["Adjustment | WFS Returned Item Disposal Fee", -20.85, 43],
  ["Service Fee | WFS PrepServiceFee", -36.40, 1],
];

function toNum(v: unknown): number { const n = Number(v); return Number.isFinite(n) ? n : 0; }
function toStr(v: unknown): string { return String(v ?? "").trim(); }
function sleep(ms: number): Promise<void> { return new Promise((r) => setTimeout(r, ms)); }
function extractList(data: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(data)) return data as Array<Record<string, unknown>>;
  const d = data as { list?: unknown } | null;
  if (Array.isArray(d?.list)) return d!.list as Array<Record<string, unknown>>;
  return [];
}
function errInfo(e: unknown): string {
  const anyE = e as { message?: string; data?: unknown };
  return `${anyE?.message ?? String(e)}${anyE?.data ? "  data=" + JSON.stringify(anyE.data).slice(0, 250) : ""}`;
}

async function main() {
  const db = await mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1", port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "", password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
  const [storeRows] = await db.execute(
    `SELECT store_id, store_name FROM dim_store_config WHERE platform='walmart' AND store_name LIKE '%瑞盈龙盛%'`,
  );
  await db.end();
  const stores = storeRows as Array<{ store_id: string; store_name: string }>;
  if (stores.length === 0) { console.log("没匹配到店铺，终止。"); return; }
  const storeId = stores[0].store_id;
  console.log(`目标店铺: ${stores[0].store_name}  reportKey=${REPORT_KEY}`);
  console.log(`判定: 行数=${EXPECT_ROWS} / 净额=$${EXPECT_TOTAL} / 逐类目=CSV基准\n`);

  const client = new LingxingClient(loadConfig());

  const byCat = new Map<string, { rows: number; amount: number }>();
  const byAmountType = new Map<string, { rows: number; amount: number }>();
  const keySet = new Set<string>();
  let totalRows = 0, totalAmount = 0, pagesFailed = 0;

  for (let page = 0; page < 220; page++) {
    let list: Array<Record<string, unknown>> | null = null;
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const resp = await client.request<unknown>({
          method: "POST", path: STATEMENT_PATH,
          params: {
            sids: [storeId], searchType: 6, searchSingleValue: REPORT_KEY, searchExactly: true,
            offset: page * 200, length: 200,
          },
          timeoutMs: 60000,
        });
        const data = (resp as { data?: unknown }).data;
        if (page === 0 && data && typeof data === "object") {
          const d = data as Record<string, unknown>;
          console.log(`[data层键名] ${Object.keys(d).join(", ")}${d.total !== undefined ? `  total=${d.total}` : ""}`);
        }
        list = extractList(data);
        break;
      } catch (e) {
        console.log(`  page=${page} attempt=${attempt + 1} 失败: ${errInfo(e)}`);
        await sleep(2000 * (attempt + 1));
      }
    }
    if (list === null) { pagesFailed++; console.log(`  page=${page} 三次重试均失败，中止（已拉${totalRows}行）`); break; }
    if (list.length === 0) break;
    for (const r of list) {
      totalRows += 1;
      const amt = toNum(r.amount);
      totalAmount += amt;
      const cat = `${toStr(r.transactionType) || "(空)"} | ${toStr(r.transactionDescription)}`;
      if (!byCat.has(cat)) byCat.set(cat, { rows: 0, amount: 0 });
      const c = byCat.get(cat)!; c.rows += 1; c.amount += amt;
      const at = toStr(r.amountType) || "(空)";
      if (!byAmountType.has(at)) byAmountType.set(at, { rows: 0, amount: 0 });
      const a = byAmountType.get(at)!; a.rows += 1; a.amount += amt;
      const uk = toStr(r.uniqueNo) || toStr(r.transactionKey);
      if (uk) keySet.add(uk);
    }
    if ((page + 1) % 20 === 0) console.log(`  ...已拉 ${page + 1} 页 / ${totalRows} 行`);
    if (list.length < 200) break;
    await sleep(350);
  }

  console.log(`\n=== 守恒判定 ===`);
  console.log(`① 总行数 = ${totalRows}  (期望${EXPECT_ROWS})  ${totalRows === EXPECT_ROWS ? "✅" : "⚠️差" + (EXPECT_ROWS - totalRows)}`);
  console.log(`② 总净额 = $${totalAmount.toFixed(2)}  (期望$${EXPECT_TOTAL})  ${Math.abs(totalAmount - EXPECT_TOTAL) < 0.01 ? "✅" : "⚠️差$" + (EXPECT_TOTAL - totalAmount).toFixed(2)}`);
  console.log(`   uniqueNo/transactionKey 去重数 = ${keySet.size}（与总行数差=${totalRows - keySet.size}，0=可作唯一键）`);
  console.log(`   失败页数 = ${pagesFailed}`);

  console.log(`\n=== ③ 逐类目对比 ===`);
  console.log("类目".padEnd(48) + "API$".padEnd(14) + "API行数".padEnd(9) + "判定");
  for (const [name, bAmt, bRows] of CSV_BENCH) {
    const v = byCat.get(name);
    if (!v) { console.log(name.padEnd(48) + "-".padEnd(14) + "-".padEnd(9) + "⚠️API无此类目"); continue; }
    const ok = v.rows === bRows && Math.abs(v.amount - bAmt) < 0.01;
    console.log(name.padEnd(48) + v.amount.toFixed(2).padEnd(14) + String(v.rows).padEnd(9) + (ok ? "✅" : `⚠️基准${bRows}行/$${bAmt.toFixed(2)}`));
  }
  console.log(`\nAPI侧多出的类目（CSV基准表未列的）:`);
  const benchNames = new Set(CSV_BENCH.map((b) => b[0]));
  for (const [k, v] of [...byCat.entries()].sort((x, y) => Math.abs(y[1].amount) - Math.abs(x[1].amount))) {
    if (!benchNames.has(k)) console.log(`  ${k.padEnd(46)} ${v.amount.toFixed(2).padEnd(13)} ${v.rows}行`);
  }

  console.log(`\n=== 按 amountType 聚合前15（fee_category映射设计参考）===`);
  for (const [k, v] of [...byAmountType.entries()].sort((x, y) => Math.abs(y[1].amount) - Math.abs(x[1].amount)).slice(0, 15)) {
    console.log(`  ${k.padEnd(40)} ${v.amount.toFixed(2).padEnd(13)} ${v.rows}行`);
  }

  console.log(`\n[判读] ①②③全✅ → 收入主线定稿："payout登记账期头 + statement按reportKey无过滤全量拉+落库后自分类"；`);
  console.log(`       ①差固定行数且②差额=特定类目 → 看"API无此类目/多出类目"定位；深分页崩 → 看失败页位置。`);
  console.log("\n探针18e结束。");
}

main().catch((err) => { console.error("探针18e执行失败：", err); process.exit(1); });
