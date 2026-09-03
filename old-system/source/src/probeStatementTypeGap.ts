/**
 * src/probeStatementTypeGap.ts
 *
 * AI财务 · 探针18d —— statement/list 行数缺口根因定位：类型归类差异假设（只读，零写库）。
 *
 * 探针18c已排除"无排序分页丢行"：换排序行数分毫不变（5894/1194，确定性缺口）。
 * 新假设：缺的行被领星归在别的 transactionType 下（CSV实测存在type为空的行；
 * 枚举中还有"Other"）。同时实锤：19位数字id经JSON.parse精度丢失（id重复5439为假象），
 * 正式同步唯一键必须用字符串 transactionKey/uniqueNo，禁用数字id。
 *
 * 本探针（同账期 reportKey=10f51fc8cba79633，CN2601）：
 *   A. 按描述过滤不按类型：transactionDescriptions:["WFS Fulfillment fee"]（无transactionTypes）
 *      全量拉取 → 应=6801行/-$39,733.06（CSV基准）。首页顺带打印 data 层全部键名与 total 字段。
 *   B. 同法拉 ["Keep-it refund"] → 应=940行/-$3,558.46。
 *   C. transactionTypes:["Other"] 全量 → 按description分组，看缺失行是否藏在Other下。
 *   D. 汇总判读：A/B到位 → 根因=类型归类差异，正式同步按"仅reportKey过滤全量拉+自分类"设计；
 *      A/B仍偏少 → 把输出贴回继续查。
 *
 * 运行：npx ts-node src/probeStatementTypeGap.ts
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
  return `${anyE?.message ?? String(e)}${anyE?.data ? "  data=" + JSON.stringify(anyE.data).slice(0, 300) : ""}`;
}

async function pull(
  client: LingxingClient, storeId: string, extra: Record<string, unknown>, label: string, showDataKeys = false,
): Promise<Array<Record<string, unknown>>> {
  const rows: Array<Record<string, unknown>> = [];
  for (let page = 0; page < 60; page++) {
    try {
      const resp = await client.request<unknown>({
        method: "POST", path: STATEMENT_PATH,
        params: {
          sids: [storeId],
          searchType: 6, searchSingleValue: REPORT_KEY, searchExactly: true,
          offset: page * 200, length: 200,
          ...extra,
        },
        timeoutMs: 60000,
      });
      const data = (resp as { data?: unknown }).data;
      if (page === 0 && showDataKeys && data && typeof data === "object") {
        const d = data as Record<string, unknown>;
        console.log(`  [data层键名] ${Object.keys(d).join(", ")}${d.total !== undefined ? `  total=${d.total}` : ""}`);
      }
      const list = extractList(data);
      if (list.length === 0) break;
      rows.push(...list);
      if (list.length < 200) break;
      await sleep(350);
    } catch (e) {
      console.log(`  [${label}] page=${page} 失败: ${errInfo(e)}`);
      break;
    }
  }
  return rows;
}

function agg(rows: Array<Record<string, unknown>>): Map<string, { rows: number; amount: number }> {
  const m = new Map<string, { rows: number; amount: number }>();
  for (const r of rows) {
    const k = `${toStr(r.transactionType) || "(空)"} | ${toStr(r.transactionDescription)}`;
    if (!m.has(k)) m.set(k, { rows: 0, amount: 0 });
    const a = m.get(k)!;
    a.rows += 1; a.amount += toNum(r.amount);
  }
  return m;
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

  console.log(`=== A. 按描述过滤(无类型过滤): WFS Fulfillment fee（基准6801行/-$39733.06）===`);
  const a = await pull(client, storeId, { transactionDescriptions: ["WFS Fulfillment fee"] }, "A", true);
  for (const [k, v] of agg(a)) console.log(`  ${k.padEnd(44)} ${v.amount.toFixed(2).padEnd(13)} ${v.rows}行`);
  console.log(`  A合计: ${a.length}行 $${a.reduce((s, r) => s + toNum(r.amount), 0).toFixed(2)}  ${a.length === 6801 ? "✅=CSV基准行数" : "⚠️仍与6801有差"}`);
  await sleep(1000);

  console.log(`\n=== B. 按描述过滤: Keep-it refund（基准940行/-$3558.46）===`);
  const b = await pull(client, storeId, { transactionDescriptions: ["Keep-it refund"] }, "B");
  for (const [k, v] of agg(b)) console.log(`  ${k.padEnd(44)} ${v.amount.toFixed(2).padEnd(13)} ${v.rows}行`);
  console.log(`  B合计: ${b.length}行 $${b.reduce((s, r) => s + toNum(r.amount), 0).toFixed(2)}  ${b.length === 940 ? "✅=CSV基准行数" : "⚠️仍与940有差"}`);
  await sleep(1000);

  console.log(`\n=== C. transactionTypes:["Other"] 全量（看缺失行是否归在Other下）===`);
  const c = await pull(client, storeId, { transactionTypes: ["Other"] }, "C");
  console.log(`  C共 ${c.length} 行；按 类型|描述 分组:`);
  for (const [k, v] of [...agg(c).entries()].sort((x, y) => Math.abs(y[1].amount) - Math.abs(x[1].amount)).slice(0, 20)) {
    console.log(`  ${k.padEnd(44)} ${v.amount.toFixed(2).padEnd(13)} ${v.rows}行`);
  }

  console.log(`\n=== D. 判读 ===`);
  console.log(`  A/B行数到位 → 根因=类型归类差异；正式同步改为"仅按reportKey全量拉取(不按类型过滤)+落库后自分类"。`);
  console.log(`  唯一键规约（已实锤）：用字符串 transactionKey/uniqueNo，禁用数字id（19位超JS安全整数，JSON.parse精度丢失）。`);
  console.log("\n探针18d结束。");
}

main().catch((err) => { console.error("探针18d执行失败：", err); process.exit(1); });
