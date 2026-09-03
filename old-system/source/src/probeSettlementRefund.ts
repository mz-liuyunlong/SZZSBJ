/**
 * probeSettlementRefund.ts — 只读探测v2：Walmart结算退货行全貌（2026-08-13）
 * v1结论：transactionTypeS=[2] 返回 orderType="退货" 行；单行金额多为0 → 疑似一单拆多行。
 * v2目标（零写入）：
 *   ①拉近60天 type=[2] 全量（最多25页×200）
 *   ②每个金额/数量字段的 非零行数+求和 分布（找出钱和件数挂在哪些字段）
 *   ③挑2个 platformOrderNo 打印该单全部行（看拆行结构）
 *   ④按 settlementDate 月份统计行数/单数
 *   ⑤顺带试 transactionTypeS=[4]/[5]（是否还有其它类型）
 * 用法：npx ts-node src/probeSettlementRefund.ts （只打印，不写任何表）
 */
import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const API_PATH = "/basicOpen/multiplatform/profit/report/order";
const PAGE_LEN = 200;
const MAX_PAGES = 25;

function d(offsetDays: number): string {
  const t = new Date(Date.now() + 8 * 3600 * 1000 + offsetDays * 86400 * 1000);
  return t.toISOString().slice(0, 10);
}

async function pull(client: LingxingClient, types: number[], startDate: string, endDate: string, maxPages: number): Promise<Array<Record<string, unknown>>> {
  const out: Array<Record<string, unknown>> = [];
  let offset = 0;
  for (let p = 0; p < maxPages; p++) {
    const resp = await client.request<{ list?: Array<Record<string, unknown>> }>({
      method: "POST", path: API_PATH,
      params: { offset, length: PAGE_LEN, platformCodeS: ["10008"], transactionTypeS: types,
        currencyCode: "USD", searchDateType: "2", startDate, endDate },
      timeoutMs: 30000,
    });
    const list = resp?.data?.list ?? [];
    out.push(...list);
    if (list.length < PAGE_LEN) break;
    offset += PAGE_LEN;
    await new Promise((r) => setTimeout(r, 1200));
  }
  return out;
}

async function main(): Promise<void> {
  const cfg = loadConfig();
  const client = new LingxingClient(cfg);
  const startDate = d(-62), endDate = d(-2);
  console.log(`探测窗口 ${startDate}~${endDate}｜transactionTypeS=[2]（退货）`);
  const rows = await pull(client, [2], startDate, endDate, MAX_PAGES);
  console.log(`退货行合计 ${rows.length} 行`);

  const agg = new Map();
  for (const r of rows) {
    for (const [k, v] of Object.entries(r)) {
      const num = Number(v);
      if (!Number.isFinite(num) || num === 0) continue;
      if (["storeId", "productId", "rowIndex", "id"].includes(k)) continue;
      const a = agg.get(k) ?? { n: 0, sum: 0 };
      a.n += 1; a.sum += num; agg.set(k, a);
    }
  }
  console.log("\n== 非零数值字段分布（字段｜非零行数｜求和） ==");
  for (const [k, a] of [...agg.entries()].sort((x, y) => y[1].n - x[1].n)) {
    console.log(`${k}\t${a.n}\t${Math.round(a.sum * 100) / 100}`);
  }

  const byOrder = new Map();
  for (const r of rows) {
    const no = String(r.platformOrderNo ?? "");
    const arr = byOrder.get(no) ?? []; arr.push(r); byOrder.set(no, arr);
  }
  console.log(`\n退货单数（按platformOrderNo）: ${byOrder.size}`);
  let printed = 0;
  for (const [no, arr] of byOrder) {
    if (arr.length < 2 && printed === 0 && byOrder.size > 1) continue;
    console.log(`\n== 完整退货单 ${no}（${arr.length}行） ==`);
    for (const r of arr) {
      const nz = Object.entries(r).filter(([k, v]) => Number.isFinite(Number(v)) && Number(v) !== 0 && !["storeId", "productId", "rowIndex", "id"].includes(k))
        .map(([k, v]) => `${k}=${v}`).join(", ");
      console.log(`rowIndex=${r.rowIndex} msku=${r.msku} orderType=${r.orderType} settlementDate=${r.settlementDate} | 非零: ${nz || "(全零)"}`);
    }
    printed += 1;
    if (printed >= 2) break;
  }

  const byMonth = new Map();
  for (const r of rows) {
    const m = String(r.settlementDate ?? "").slice(0, 7);
    const a = byMonth.get(m) ?? { rows: 0, orders: new Set() };
    a.rows += 1; a.orders.add(String(r.platformOrderNo ?? "")); byMonth.set(m, a);
  }
  console.log("\n== 按结算月份量级 ==");
  for (const [m, a] of [...byMonth.entries()].sort()) console.log(`${m}\t${a.rows}行\t${a.orders.size}单`);

  for (const code of [4, 5]) {
    try {
      const r2 = await pull(client, [code], d(-16), endDate, 1);
      console.log(`\ntransactionTypeS=[${code}] → ${r2.length} 行${r2.length ? `｜orderType=${r2[0].orderType}` : ""}`);
    } catch (e) { console.log(`\ntransactionTypeS=[${code}] → 失败: ${e instanceof Error ? e.message : String(e)}`); }
    await new Promise((r) => setTimeout(r, 1200));
  }
  // ⑥ RAW 全费用字段清点（销售类型行，近5万行只读）：沃尔玛账单里到底有哪些费用
  console.log("\n== RAW(销售行) 全费用字段清点（最近5万行，字段｜非零行数｜求和） ==");
  const db = await mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1", port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "", password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
  try {
    const [rawRows] = await db.execute(
      `SELECT row_json FROM raw_lingxing_settlement_order ORDER BY id DESC LIMIT 50000`);
    const feeAgg = new Map();
    let scanned = 0;
    for (const rr of rawRows as Array<{ row_json: unknown }>) {
      const r = (typeof rr.row_json === "string" ? JSON.parse(rr.row_json) : rr.row_json) as Record<string, unknown>;
      scanned++;
      for (const [k, v] of Object.entries(r)) {
        const num = Number(v);
        if (!Number.isFinite(num) || num === 0) continue;
        if (["storeId", "productId", "rowIndex", "id", "cid", "bid", "mskuId", "version"].includes(k)) continue;
        const a = feeAgg.get(k) ?? { n: 0, sum: 0 };
        a.n += 1; a.sum += num; feeAgg.set(k, a);
      }
    }
    console.log(`扫描 ${scanned} 行`);
    for (const [k, a] of [...feeAgg.entries()].sort((x, y) => Math.abs(y[1].sum) - Math.abs(x[1].sum))) {
      console.log(`${k}\t${a.n}\t${Math.round(a.sum * 100) / 100}`);
    }
  } finally { await db.end().catch(() => undefined); }
  console.log("\nPROBE_DONE（零写入）");
}

main().catch((e) => { console.error("FATAL:", e instanceof Error ? e.message : String(e)); process.exit(1); });
