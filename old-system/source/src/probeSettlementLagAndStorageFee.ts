/**
 * src/probeSettlementLagAndStorageFee.ts
 *
 * AI财务·单品现金利润 · 探针14 —— 开工前最后两个待闭环项（只读，零写库，零改动生产）：
 *
 *   A) 结算数据滞后天数实测：模块要"逐日拉结算数据"（startDate=endDate=D 每天攒），
 *      需要知道 D 距今多少天内数据还不可得/不完整，即回补窗口设多长。
 *      方法：对 CN2601 逐日调结算利润msku接口（近16天，每天一个单日窗口），
 *      记录每天的 total行数 / salesAmount合计 / 各费用字段合计——最近的"有数据日"
 *      到今天的距离=最小滞后；行数金额随日期衰减的形态=完整性成熟曲线。
 *
 *   B) 零销量纯库存SKU的仓储费可得性：库存里压着但整月没卖一单的SKU，
 *      它的仓储费能不能从结算利润接口查到？（决定"纯仓储费吃利润"的行能不能算准）
 *      方法①：拉 CN2601 七月整窗(07-01~07-31)结算msku全量list（分页），
 *      统计 salesAmount=0 但 仓储/入仓费字段非零 的行数并打样例——存在即证明"可得"。
 *      方法②DB交叉：从 fact_sales_daily 找七月零销量、fact_inventory_daily 有WFS库存
 *      的 item（前10），逐个看其 msku 是否出现在结算窗口list里——直接回答
 *      "纯压库存的品在结算接口里到底有没有行"。
 *
 * 安全边界：只读 LingXing API（结算利润msku接口，与探针6同款）+ 只读 DB SELECT，
 *   零写库、零写RAW、零改动生产、不建表。
 *
 * 运行（生产机，由部署工程师执行）：
 *   npx ts-node src/probeSettlementLagAndStorageFee.ts
 *
 * 用法：把完整输出贴回来，重点看"一、逐日可得性表"和"三、DB交叉核对"。
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const SETTLEMENT_MSKU_PATH = "/basicOpen/multiplatform/profit/report/msku";
const WALMART_PLATFORM_CODE = "10008";
const LAG_DAYS_BACK = 16;
const JULY = { startDate: "2026-07-01", endDate: "2026-07-31" };
const PAGE_LEN = 200;
const MAX_PAGES = 15;

// 仓储/费用候选字段（探针2/6已见过的字段体系；逐个求和看哪个非零）
const STORAGE_FIELDS = ["platformWfsStorageAmount", "wfsWarehousFee", "wfsPrepServiceFee", "wfsShipmentFee"];

function toNum(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}
function toStr(v: unknown): string {
  return String(v ?? "").trim();
}
function chinaDateOffset(offsetDays: number): string {
  const d = new Date();
  d.setUTCHours(d.getUTCHours() + 8);
  d.setUTCDate(d.getUTCDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}
function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

async function fetchSettlementWindow(
  client: LingxingClient,
  storeId: string,
  startDate: string,
  endDate: string,
  maxPages: number,
): Promise<{ rows: Array<Record<string, unknown>>; total: number }> {
  const rows: Array<Record<string, unknown>> = [];
  let total = 0;
  for (let page = 0; page < maxPages; page++) {
    const resp = await client.request<{ total?: number; list?: Array<Record<string, unknown>> }>({
      method: "POST",
      path: SETTLEMENT_MSKU_PATH,
      params: {
        offset: page * PAGE_LEN,
        length: PAGE_LEN,
        platformCodeS: [WALMART_PLATFORM_CODE],
        sids: storeId,
        startDate,
        endDate,
      },
      timeoutMs: 30000,
    });
    const data = (resp as unknown as { data?: { total?: number; list?: Array<Record<string, unknown>> } }).data;
    const list = data?.list ?? [];
    total = data?.total ?? total;
    rows.push(...list);
    if (list.length < PAGE_LEN || (total > 0 && rows.length >= total)) break;
    await sleep(400);
  }
  return { rows, total };
}

async function main() {
  const db = await mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });

  const [storeRows] = await db.execute(
    `SELECT store_id, store_name FROM dim_store_config WHERE platform='walmart' AND store_name LIKE '%瑞盈龙盛%'`,
  );
  const stores = storeRows as Array<{ store_id: string; store_name: string }>;
  if (stores.length === 0) { console.log("没匹配到店铺，终止。"); await db.end(); return; }
  const storeId = stores[0].store_id;
  console.log(`目标店铺: store_id=${storeId} (${stores[0].store_name})\n`);

  const client = new LingxingClient(loadConfig());

  // ── 一、逐日可得性（滞后实测）──
  console.log(`=== 一、结算数据逐日可得性（近${LAG_DAYS_BACK}天，每天单日窗口，判定滞后/回补窗口）===\n`);
  console.log("日期(距今)".padEnd(18) + "total".padEnd(8) + "list行".padEnd(8) + "salesAmount$".padEnd(14) + STORAGE_FIELDS.map((f) => f.padEnd(24)).join(""));
  for (let back = LAG_DAYS_BACK; back >= 1; back--) {
    const d = chinaDateOffset(-back);
    try {
      const { rows, total } = await fetchSettlementWindow(client, storeId, d, d, 3);
      const sales = rows.reduce((a, r) => a + toNum(r.salesAmount), 0);
      const feeSums = STORAGE_FIELDS.map((f) => rows.reduce((a, r) => a + toNum(r[f]), 0));
      console.log(
        `${d}(-${String(back).padEnd(3)})`.padEnd(18) + String(total).padEnd(8) + String(rows.length).padEnd(8) +
        sales.toFixed(2).padEnd(14) + feeSums.map((v) => v.toFixed(2).padEnd(24)).join(""),
      );
    } catch (e) {
      console.log(`${d}(-${back})  [请求失败] ${e instanceof Error ? e.message : String(e)}`);
    }
    await sleep(600);
  }
  console.log(`\n[判读] 最近的非零日=最小滞后；行数/金额明显低于更早日期的天=数据未成熟，回补窗口应覆盖到金额稳定的天数。`);

  // ── 二、七月整窗：零销量但有费用的行 ──
  console.log(`\n=== 二、七月整窗(${JULY.startDate}~${JULY.endDate}) 零销量行审计 ===\n`);
  const { rows: julyRows, total: julyTotal } = await fetchSettlementWindow(client, storeId, JULY.startDate, JULY.endDate, MAX_PAGES);
  console.log(`整窗 total=${julyTotal}，实取 ${julyRows.length} 行${julyRows.length < julyTotal ? "（未取全，结论按已取样本）" : ""}`);
  if (julyRows.length > 0) {
    console.log(`\n首行全部字段名（供核对字段体系）:\n${Object.keys(julyRows[0]).sort().join(", ")}\n`);
  }
  const zeroSales = julyRows.filter((r) => toNum(r.salesAmount) === 0);
  const zeroSalesWithFee = zeroSales.filter((r) => STORAGE_FIELDS.some((f) => toNum(r[f]) !== 0));
  console.log(`salesAmount=0 的行: ${zeroSales.length} 条；其中仓储/WFS类费用字段非零的: ${zeroSalesWithFee.length} 条`);
  for (const r of zeroSalesWithFee.slice(0, 5)) {
    const fees = STORAGE_FIELDS.map((f) => `${f}=${toNum(r[f]).toFixed(2)}`).filter((s) => !s.endsWith("=0.00")).join(" ");
    console.log(`  样例: msku=${toStr(r.msku ?? r.sku)}  ${fees}`);
  }
  console.log(`[判读] 非零条数>0 → "零销量纯库存SKU的仓储费可从结算接口取到"成立（费用跟着结算事件走，不依赖销售）。`);

  // ── 三、DB交叉：七月零销量+有WFS库存的品，结算接口里有没有行 ──
  console.log(`\n=== 三、DB交叉核对：七月零销量但压WFS库存的品（前10），在结算七月整窗里是否有行 ===\n`);
  const [zeroSaleItems] = await db.execute(
    `SELECT i.item_id, MAX(i.msku) AS msku, ROUND(AVG(i.wfs_available_stock),0) AS avg_stock
       FROM fact_inventory_daily i
      WHERE i.store_id=? AND i.snapshot_date BETWEEN ? AND ? AND i.wfs_available_stock > 0
        AND NOT EXISTS (
          SELECT 1 FROM fact_sales_daily s
           WHERE s.store_id=i.store_id AND s.item_id=i.item_id
             AND s.stat_date BETWEEN ? AND ? AND s.sales_qty > 0)
      GROUP BY i.item_id ORDER BY avg_stock DESC LIMIT 10`,
    [storeId, JULY.startDate, JULY.endDate, JULY.startDate, JULY.endDate],
  );
  const zsItems = zeroSaleItems as Array<{ item_id: string; msku: string | null; avg_stock: unknown }>;
  if (zsItems.length === 0) {
    console.log("  [DB里没找到七月零销量+有WFS库存的品]");
  } else {
    const settleMskuMap = new Map<string, Record<string, unknown>>();
    for (const r of julyRows) {
      const k = toStr(r.msku ?? r.sku);
      if (k && !settleMskuMap.has(k)) settleMskuMap.set(k, r);
    }
    for (const it of zsItems) {
      const msku = toStr(it.msku);
      const hit = msku ? settleMskuMap.get(msku) : undefined;
      if (hit) {
        const fees = STORAGE_FIELDS.map((f) => `${f}=${toNum(hit[f]).toFixed(2)}`).filter((s) => !s.endsWith("=0.00")).join(" ") || "(各费用字段全0)";
        console.log(`  item=${it.item_id} msku=${msku} 均库存=${it.avg_stock} → 结算窗口有行: ${fees}`);
      } else {
        console.log(`  item=${it.item_id} msku=${msku || "(空)"} 均库存=${it.avg_stock} → [结算窗口无行]`);
      }
    }
    console.log(`\n[判读] 多数命中且费用非零 → 仓储费可得性闭环；多数无行 → 纯库存SKU仓储费需另找数据源（回报需求方）。`);
  }

  await db.end();
  console.log("\n探针14结束。");
}

main().catch((err) => {
  console.error("探针14执行失败：", err);
  process.exit(1);
});
