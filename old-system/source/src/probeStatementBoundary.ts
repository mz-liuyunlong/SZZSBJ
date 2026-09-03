/**
 * src/probeStatementBoundary.ts
 *
 * AI财务 · 探针18g —— 账期边界归属一锤定音（只读，零写库，零改动生产）。
 *
 * 探针18f+本地diff已锁定：当前账期(10f51fc8cba79633, 07-11~07-25)在领星侧缺的正好是
 * 07-11/07-12两天全部交易（总缺5369行=CSV那两天2558+2811一行不差；Keep-it缺118=64+54；
 * Fulfillment缺1050=496+554；Sale缺4154=1983+2171——全部精确吻合）。
 * 假设：领星把07-11/07-12入账的交易归到了上一个账期 reportKey=d21ce341dba4f65a
 * （2026-06-27~2026-07-11，totalPayable=$15,433.66，settlementCount=43,803）名下。
 *
 * 本探针（约8次调用）：
 *   A. 上一账期 Refund 全量（预计≤2000行）：Keep-it 按 postedDate 分布——重点看
 *      2026-07-11/07-12 是否各有≥64/54行；并打印这两天全部行 orderNo|line|amount。
 *      与CSV指纹样本比对（嵌入8条：200015218062327|3|-20.00等，命中=实锤归属边界差异）。
 *   B. 上一账期首页 totalCount/totalSum：totalCount 是否≈43,803+boundary（自身账期头两天
 *      06-27/06-28应同理归到更早账期——若totalCount≠settlementCount同样差头两天，规律通吃）。
 *
 * 判定：A命中 → 钱没丢，领星按自己口径把账期首2天归上一期；正式同步设计=
 *   连续拉多个账期后按 postedDate∈[periodStart,periodEnd) 重新归桶到沃尔玛账期，
 *   守恒等式即可闭环，领星API可作核算主源（CSV导入为核查）。
 *
 * 运行：npx ts-node src/probeStatementBoundary.ts
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const STATEMENT_PATH = "/basicOpen/multiplatformFinance/walmart/bill/statement/list";
const PREV_KEY = "d21ce341dba4f65a"; // 2026-06-27 ~ 2026-07-11
const CSV_FP = [
  "200015218062327|3|-20.00", "200015218062327|3|-1.76", "200015218062327|3|1.76", "200015218062327|3|0.75",
  "200015130430773|1|-17.89", "200015130430773|1|-1.56", "200015130430773|1|1.56", "200015130430773|1|0.67",
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
  console.log(`目标店铺: ${stores[0].store_name}  上一账期 reportKey=${PREV_KEY}（06-27~07-11）\n`);
  const client = new LingxingClient(loadConfig());

  // B. 上一账期 totalCount
  console.log(`=== B. 上一账期首页 totalCount/totalSum（settlementCount基准=43,803）===`);
  try {
    const resp = await client.request<unknown>({
      method: "POST", path: STATEMENT_PATH,
      params: { sids: [storeId], searchType: 6, searchSingleValue: PREV_KEY, searchExactly: true, offset: 0, length: 1 },
      timeoutMs: 60000,
    });
    const d = (resp as { data?: Record<string, unknown> }).data ?? {};
    console.log(`  totalCount = ${JSON.stringify(d.totalCount)}  totalSum.amount = ${JSON.stringify((d.totalSum as Record<string, unknown> | undefined)?.amount)}`);
  } catch (e) { console.log(`  失败: ${errInfo(e)}`); }
  await sleep(800);

  // A. 上一账期 Refund 全量 → Keep-it 分布 + 07-11/12 清单
  console.log(`\n=== A. 上一账期 Refund 全量：Keep-it 按天分布 + 07-11/07-12 清单与CSV指纹比对 ===`);
  const rows: Array<Record<string, unknown>> = [];
  for (let page = 0; page < 15; page++) {
    try {
      const resp = await client.request<unknown>({
        method: "POST", path: STATEMENT_PATH,
        params: { sids: [storeId], transactionTypes: ["Refund"], searchType: 6, searchSingleValue: PREV_KEY, searchExactly: true, offset: page * 200, length: 200 },
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
  console.log(`  Refund总行=${rows.length}，Keep-it行=${keepIt.length}`);
  const byDate = new Map<string, number>();
  for (const r of keepIt) {
    const dte = toStr(r.transactionPostedTimestamp).slice(0, 10);
    byDate.set(dte, (byDate.get(dte) ?? 0) + 1);
  }
  console.log(`  按天分布:`);
  for (const [k, v] of [...byDate.entries()].sort()) console.log(`    ${k}  ${v}行`);

  const boundary = keepIt.filter((r) => {
    const dte = toStr(r.transactionPostedTimestamp).slice(0, 10);
    return dte === "2026-07-11" || dte === "2026-07-12";
  });
  console.log(`\n  07-11/07-12 的 Keep-it 行数=${boundary.length}（CSV当前账期那两天=118）`);
  const apiSet = new Set(boundary.map((r) => `${toStr(r.customerOrderNo)}|${toStr(r.customerOrderLineNo)}|${toNum(r.amount).toFixed(2)}`));
  let hit = 0;
  for (const fp of CSV_FP) if (apiSet.has(fp)) hit++;
  console.log(`  CSV指纹8条命中=${hit}/8  ${hit >= 7 ? "✅实锤：头两天交易归在上一账期，钱没丢，是账期归属口径差异" : "⚠️未命中，把下方清单贴回继续查"}`);
  console.log(`  07-11/07-12 清单（前60行 orderNo|line|amount|date）:`);
  for (const r of boundary.slice(0, 60)) {
    console.log(`    ${toStr(r.customerOrderNo)}|${toStr(r.customerOrderLineNo)}|${toNum(r.amount).toFixed(2)}|${toStr(r.transactionPostedTimestamp).slice(0, 10)}`);
  }

  console.log(`\n[判读] 指纹命中 → 正式同步设计：连续拉账期后按 postedDate∈[periodStart,periodEnd) 重新归桶，`);
  console.log(`       守恒即闭环，领星API可作核算主源、CSV导入为核查通道。`);
  console.log("\n探针18g结束。");
}

main().catch((err) => { console.error("探针18g执行失败：", err); process.exit(1); });
