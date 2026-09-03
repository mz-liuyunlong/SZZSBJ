/**
 * src/probeStatementWindow.ts
 *
 * AI财务 · 探针18h —— statement/list "滚动保留窗口"假设验证（只读，零写库，零改动生产）。
 *
 * 证据链：当前账期(07-11~07-25)在领星侧现存最早行=posted 07-13、缺07-11/12两整天；
 * 上一账期(06-27~07-11)整体totalCount=0。今天2026-08-11，30天前≈07-12——
 * 假设：statement明细仅保留 postedDate 在近~30天内的行（滚动窗口，历史出窗即清）。
 *
 * 三个日期区间查询（sids+startDate/endDate，不用reportKey）：
 *   T1. 2026-06-25 ~ 2026-07-12 → 假设成立应 totalCount=0（全部出窗）
 *   T2. 2026-07-12 ~ 2026-07-14 → 应只有 07-13/07-14 的行
 *   T3. 2026-07-26 ~ 2026-08-10 → 未结算新周期的行是否已在库（决定每日拉取可行性）
 * 每个区间打印 totalCount、totalSum.amount、前5行的 postedDate/type/description。
 *
 * 工程结论（无论窗口精确天数）：statement明细=易逝数据 → 正式同步必须每日拉近N天增量
 * 沉淀到自家RAW/FACT；超窗历史回补只能走CSV导入（需求方自行解决的通道）。
 *
 * 运行：npx ts-node src/probeStatementWindow.ts
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const STATEMENT_PATH = "/basicOpen/multiplatformFinance/walmart/bill/statement/list";
const TESTS: Array<{ label: string; startDate: string; endDate: string; expect: string }> = [
  { label: "T1 出窗历史", startDate: "2026-06-25", endDate: "2026-07-12", expect: "假设成立应totalCount=0" },
  { label: "T2 窗口边缘", startDate: "2026-07-12", endDate: "2026-07-14", expect: "应只有07-13/07-14行" },
  { label: "T3 未结算新周期", startDate: "2026-07-26", endDate: "2026-08-10", expect: "有行=每日增量拉取可行" },
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
  console.log(`目标店铺: ${stores[0].store_name}  今天(参照)=2026-08-11，30天前≈2026-07-12\n`);
  const client = new LingxingClient(loadConfig());

  for (const t of TESTS) {
    console.log(`=== ${t.label} ${t.startDate}~${t.endDate}（${t.expect}）===`);
    try {
      const resp = await client.request<unknown>({
        method: "POST", path: STATEMENT_PATH,
        params: { sids: [storeId], startDate: t.startDate, endDate: t.endDate, offset: 0, length: 5 },
        timeoutMs: 60000,
      });
      const d = (resp as { data?: Record<string, unknown> }).data ?? {};
      const ts = d.totalSum as Record<string, unknown> | undefined;
      console.log(`  totalCount = ${JSON.stringify(d.totalCount)}  totalSum.amount = ${JSON.stringify(ts?.amount)}`);
      const list = extractList(d);
      for (const r of list.slice(0, 5)) {
        console.log(`  行: posted=${toStr(r.transactionPostedTimestamp).slice(0, 10)}  ${toStr(r.transactionType)}|${toStr(r.transactionDescription).slice(0, 30)}  $${toNum(r.amount).toFixed(2)}  order=${toStr(r.customerOrderNo)}`);
      }
    } catch (e) { console.log(`  失败: ${errInfo(e)}`); }
    console.log("");
    await sleep(900);
  }

  console.log(`[判读] T1=0 且 T2只有07-13/14 → 滚动窗口实锤（易逝数据，正式同步=每日增量沉淀，历史回补走CSV）；`);
  console.log(`       T3有行 → 未结算周期数据实时可拉，每日同步设计成立；T3无行 → 明细仅在结算后出现，同步改为账期结算触发式。`);
  console.log("\n探针18h结束。");
}

main().catch((err) => { console.error("探针18h执行失败：", err); process.exit(1); });
