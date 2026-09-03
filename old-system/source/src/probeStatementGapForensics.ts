/**
 * src/probeStatementGapForensics.ts
 *
 * AI财务 · 探针18f —— statement/list 缺行法证定位（只读，零写库，零改动生产）。
 *
 * 已排除：分页策略(18c)、类型/描述过滤(18d)、无过滤全量(18e仍30156/35525)、
 * Key+AmountType去重(本地CSV验证无重复可丢)。缺口~15%按天均匀分布。
 * 本探针三件事：
 *   A. 首页打印 data.totalCount / data.totalSum 的真实值（领星自己认多少）+ 3行样例的
 *      uniqueNo/transactionKey/deleteFlag/currency 原值。
 *   B. 去掉 sids 过滤同查首页 totalCount 对比（排除店铺归属过滤嫌疑）。
 *   C. Refund 类型全量（约6页，行数已知稳定1194）：Keep-it refund 按 postedDate 分布
 *      （行数+金额，对照CSV分布已在手），并完整打印 2026-07-13 当天全部 Keep-it 行的
 *      customerOrderNo|line|amount 清单（CSV当天90行，API预计约79行，回来本地逐行diff）。
 *
 * 运行：npx ts-node src/probeStatementGapForensics.ts
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const STATEMENT_PATH = "/basicOpen/multiplatformFinance/walmart/bill/statement/list";
const REPORT_KEY = "10f51fc8cba79633";

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
  console.log(`目标店铺: ${stores[0].store_name}  reportKey=${REPORT_KEY}\n`);
  const client = new LingxingClient(loadConfig());

  // A. totalCount/totalSum + 样例
  console.log(`=== A. 首页 totalCount/totalSum 真实值（带sids）===`);
  try {
    const resp = await client.request<unknown>({
      method: "POST", path: STATEMENT_PATH,
      params: { sids: [storeId], searchType: 6, searchSingleValue: REPORT_KEY, searchExactly: true, offset: 0, length: 5 },
      timeoutMs: 60000,
    });
    const d = (resp as { data?: Record<string, unknown> }).data ?? {};
    console.log(`  totalCount = ${JSON.stringify(d.totalCount)}`);
    console.log(`  totalSum   = ${JSON.stringify(d.totalSum)}`);
    for (const r of extractList(d).slice(0, 3)) {
      console.log(`  样例: uniqueNo=${JSON.stringify(r.uniqueNo)} transactionKey=${JSON.stringify(toStr(r.transactionKey).slice(0, 60))} deleteFlag=${JSON.stringify(r.deleteFlag)} currency=${toStr(r.currency)} posted=${toStr(r.transactionPostedTimestamp)}`);
    }
  } catch (e) { console.log(`  失败: ${errInfo(e)}`); }
  await sleep(800);

  console.log(`\n=== B. 去掉sids过滤的首页 totalCount 对比 ===`);
  try {
    const resp = await client.request<unknown>({
      method: "POST", path: STATEMENT_PATH,
      params: { searchType: 6, searchSingleValue: REPORT_KEY, searchExactly: true, offset: 0, length: 1 },
      timeoutMs: 60000,
    });
    const d = (resp as { data?: Record<string, unknown> }).data ?? {};
    console.log(`  totalCount(无sids) = ${JSON.stringify(d.totalCount)}  totalSum = ${JSON.stringify(d.totalSum)}`);
  } catch (e) { console.log(`  失败: ${errInfo(e)}`); }
  await sleep(800);

  // C. Refund全量 → Keep-it 按天分布 + 07-13全清单
  console.log(`\n=== C. Refund全量：Keep-it refund 按天分布 + 2026-07-13全清单 ===`);
  const rows: Array<Record<string, unknown>> = [];
  for (let page = 0; page < 10; page++) {
    try {
      const resp = await client.request<unknown>({
        method: "POST", path: STATEMENT_PATH,
        params: { sids: [storeId], transactionTypes: ["Refund"], searchType: 6, searchSingleValue: REPORT_KEY, searchExactly: true, offset: page * 200, length: 200 },
        timeoutMs: 60000,
      });
      const list = extractList((resp as { data?: unknown }).data);
      if (list.length === 0) break;
      rows.push(...list);
      if (list.length < 200) break;
      await sleep(400);
    } catch (e) { console.log(`  page=${page} 失败: ${errInfo(e)}`); break; }
  }
  const keepIt = rows.filter((r) => toStr(r.transactionDescription) === "Keep-it refund");
  console.log(`  Refund总行=${rows.length}，Keep-it行=${keepIt.length}（CSV基准940）`);
  const byDate = new Map<string, { rows: number; amount: number }>();
  for (const r of keepIt) {
    const dte = toStr(r.transactionPostedTimestamp).slice(0, 10);
    if (!byDate.has(dte)) byDate.set(dte, { rows: 0, amount: 0 });
    const b = byDate.get(dte)!; b.rows += 1; b.amount += toNum(r.amount);
  }
  console.log(`  按天分布（CSV基准: 07-11=64 07-12=54 07-13=90 07-14=75 07-15=90 07-16=74 07-17=70 07-18=52 07-19=75 07-20=51 07-21=62 07-22=72 07-23=60 07-24=51）:`);
  for (const [k, v] of [...byDate.entries()].sort()) console.log(`    ${k}  ${v.rows}行  ${v.amount.toFixed(2)}`);
  console.log(`\n  2026-07-13 当天 Keep-it 全清单（customerOrderNo|line|amount，供本地与CSV逐行diff）:`);
  for (const r of keepIt.filter((r) => toStr(r.transactionPostedTimestamp).startsWith("2026-07-13"))) {
    console.log(`    ${toStr(r.customerOrderNo)}|${toStr(r.customerOrderLineNo)}|${toNum(r.amount).toFixed(2)}`);
  }

  console.log("\n探针18f结束。");
}

main().catch((err) => { console.error("探针18f执行失败：", err); process.exit(1); });
