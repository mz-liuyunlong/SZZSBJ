/**
 * src/probeStatementPagination.ts
 *
 * AI财务 · 探针18c —— statement/list 分页稳定性验证（只读，零写库，零改动生产）。
 *
 * 背景（探针18）：
 *   payout/list 账期头完全可信（settlementCount=35525 与CSV行数一个不差，差额全0）；
 *   店铺级类目金额分毫不差；partnerItemId=MSKU形态实锤。
 *   但带品级的大类目行数系统性偏少（WFS Fulfillment fee 5751/6801、Keep-it 822/940、
 *   Return Refund 360/397、ReturnProc 94/103、SEM 12/13）——settlementCount证明领星数据是全的，
 *   高度怀疑：探针18分页未传 sortField，无稳定排序的分页跨页丢行。
 *
 * 本探针（同账期 reportKey=10f51fc8cba79633，CN2601）：
 *   A. Adjustment 全量重拉，带 sortField:"id" sortType:"1"(升序)：
 *      期望行数≈6953（CSV: Fulfillment 6801+RetProc 103+RetDisposal 43+Lost 2+Found 2+Damage 2）；
 *      按description分组行数/金额对CSV基准（Fulfillment应=-39733.06/6801行）。
 *      并做id去重计数（dup>0=分页重复；dup=0且行数到位=分页修复成立）。
 *   B. Refund 全量重拉同参数：期望1349行（940+397+12），Keep-it应=-3558.46。
 *   C. 若 sortField:"id" 报错，回退依次试 sortField:"transactionPostedTimestamp"、
 *      "transactionKey"，哪个能让行数到位用哪个。
 *
 * 安全边界：只读API+只查dim_store_config。运行：npx ts-node src/probeStatementPagination.ts
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const STATEMENT_PATH = "/basicOpen/multiplatformFinance/walmart/bill/statement/list";
const REPORT_KEY = "10f51fc8cba79633";
const SORT_CANDIDATES = ["id", "transactionPostedTimestamp", "transactionKey"];
const BENCH: Record<string, { rows: number; amount: number }> = {
  "Adjustment|WFS Fulfillment fee": { rows: 6801, amount: -39733.06 },
  "Adjustment|WFS Return Processing Fee": { rows: 103, amount: -821.90 },
  "Adjustment|WFS Returned Item Disposal Fee": { rows: 43, amount: -20.85 },
  "Adjustment|WFS LostInventory": { rows: 2, amount: 2694.96 },
  "Refund|Keep-it refund": { rows: 940, amount: -3558.46 },
  "Refund|Return Refund": { rows: 397, amount: -1633.89 },
  "Refund|Seller Initiated Returns": { rows: 12, amount: -60.08 },
};

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
  return `${anyE?.message ?? String(e)}${anyE?.data ? "  data=" + JSON.stringify(anyE.data).slice(0, 300) : ""}`;
}

async function pullType(
  client: LingxingClient, storeId: string, tType: string, sortField: string,
): Promise<{ rows: Array<Record<string, unknown>>; error?: string }> {
  const rows: Array<Record<string, unknown>> = [];
  for (let page = 0; page < 60; page++) {
    try {
      const resp = await client.request<unknown>({
        method: "POST", path: STATEMENT_PATH,
        params: {
          sids: [storeId], transactionTypes: [tType],
          searchType: 6, searchSingleValue: REPORT_KEY, searchExactly: true,
          sortField, sortType: "1",
          offset: page * 200, length: 200,
        },
        timeoutMs: 60000,
      });
      const list = extractList((resp as { data?: unknown }).data);
      if (list.length === 0) break;
      rows.push(...list);
      if (list.length < 200) break;
      await sleep(400);
    } catch (e) {
      return { rows, error: errInfo(e) };
    }
  }
  return { rows };
}

function report(tType: string, sortField: string, rows: Array<Record<string, unknown>>) {
  const ids = rows.map((r) => toStr(r.id));
  const dup = ids.length - new Set(ids).size;
  console.log(`\n【${tType} | sortField=${sortField}】总行数=${rows.length}  id重复=${dup}`);
  const byDesc = new Map<string, { rows: number; amount: number }>();
  for (const r of rows) {
    const k = `${tType}|${toStr(r.transactionDescription)}`;
    if (!byDesc.has(k)) byDesc.set(k, { rows: 0, amount: 0 });
    const a = byDesc.get(k)!;
    a.rows += 1; a.amount += toNum(r.amount);
  }
  for (const [k, a] of [...byDesc.entries()].sort((x, y) => Math.abs(y[1].amount) - Math.abs(x[1].amount))) {
    const b = BENCH[k];
    const mark = b
      ? (a.rows === b.rows && Math.abs(a.amount - b.amount) < 0.01 ? "  ✅=CSV基准" : `  ⚠️基准 ${b.rows}行/$${b.amount.toFixed(2)}`)
      : "";
    console.log(`  ${k.slice(0, 46).padEnd(48)} ${a.amount.toFixed(2).padEnd(13)} ${String(a.rows).padEnd(6)}${mark}`);
  }
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
  console.log(`基准: Adjustment应≈6953行 / Refund应=1349行（CSV实数）\n`);

  const client = new LingxingClient(loadConfig());

  for (const tType of ["Adjustment", "Refund"]) {
    let done = false;
    for (const sf of SORT_CANDIDATES) {
      const { rows, error } = await pullType(client, storeId, tType, sf);
      if (error && rows.length === 0) {
        console.log(`\n【${tType} | sortField=${sf}】请求失败: ${error}，试下一个排序字段`);
        await sleep(600);
        continue;
      }
      report(tType, sf, rows);
      if (error) console.log(`  （中途报错: ${error}，行数仅供参考）`);
      done = true;
      break; // 第一个可用排序字段的结果为准；行数是否到位由输出判读
    }
    if (!done) console.log(`\n【${tType}】所有排序字段均失败`);
    await sleep(1000);
  }

  console.log(`\n[判读] 行数与金额全部✅ → 分页丢行=排序问题已修复，statement/list数据保真100%，收入主线定稿自动化；`);
  console.log(`       仍偏少 → 需再查（offset语义/接口内部过滤），把本输出贴回。`);
  console.log("\n探针18c结束。");
}

main().catch((err) => { console.error("探针18c执行失败：", err); process.exit(1); });
