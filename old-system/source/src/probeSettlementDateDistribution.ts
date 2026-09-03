/**
 * src/probeSettlementDateDistribution.ts
 *
 * AI财务·单品现金利润 · 探针14b —— 结算数据的"结算日期分布/批次形态/真实滞后"量化
 * （只读，零写库，零改动生产）。
 *
 * 背景（探针14结论）：
 *   近16天单日窗口全部返回0，但七月整窗能拿到158行 → 结算数据按批次入账、滞后可能2~3周；
 *   接口返回字段里有 settlementDate/dateMonth/shipmentDate，本探针把各月窗口的行
 *   按 settlementDate 分布摆出来，直接量化：①结算批次的入账节奏（是不是每周几批）；
 *   ②当前最新一笔结算日期距今几天=真实滞后；③模块"滚动窗口每日重拉"的窗口该设多长。
 *   另外验证一个关键假设：startDate/endDate 参数是否就是按 settlementDate 过滤
 *   （用分布里真实存在的某个结算日再发一次单日查询，非零即证实）。
 *
 * 本探针做的事（对 CN2601）：
 *   1) 分别拉 2026-06-01~06-30、2026-07-01~07-31、2026-08-01~08-31 三个整窗（分页取全），
 *      每窗按 settlementDate 分组打印：行数 / salesAmount合计 / wfsShipmentFee合计。
 *   2) 打印全局最大 settlementDate 距今天数 = 真实最小滞后。
 *   3) 取七月分布里行数最多的那个 settlementDate，用 startDate=endDate=该日 再查一次，
 *      看返回行数是否≈分布里的行数（验证参数=按结算日过滤）。
 *   4) 顺带打印2条样例行的 settlementDate/dateMonth/shipmentDate/deliveryDate 原值，
 *      供人工确认字段语义。
 *
 * 安全边界：只读 LingXing API + 无DB写入（只查 dim_store_config），零改动生产。
 *
 * 运行（生产机，由部署工程师执行）：
 *   npx ts-node src/probeSettlementDateDistribution.ts
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const SETTLEMENT_MSKU_PATH = "/basicOpen/multiplatform/profit/report/msku";
const WALMART_PLATFORM_CODE = "10008";
const PAGE_LEN = 200;
const MAX_PAGES = 15;
const WINDOWS = [
  { label: "6月窗", startDate: "2026-06-01", endDate: "2026-06-30" },
  { label: "7月窗", startDate: "2026-07-01", endDate: "2026-07-31" },
  { label: "8月窗", startDate: "2026-08-01", endDate: "2026-08-31" },
];

function toNum(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}
function toStr(v: unknown): string {
  return String(v ?? "").trim();
}
function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
function todayChina(): string {
  const d = new Date();
  d.setUTCHours(d.getUTCHours() + 8);
  return d.toISOString().slice(0, 10);
}

async function fetchWindow(
  client: LingxingClient,
  storeId: string,
  startDate: string,
  endDate: string,
): Promise<Array<Record<string, unknown>>> {
  const rows: Array<Record<string, unknown>> = [];
  for (let page = 0; page < MAX_PAGES; page++) {
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
    const data = (resp as unknown as { data?: { list?: Array<Record<string, unknown>> } }).data;
    const list = data?.list ?? [];
    rows.push(...list);
    if (list.length < PAGE_LEN) break;
    await sleep(400);
  }
  return rows;
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
  await db.end();
  if (stores.length === 0) { console.log("没匹配到店铺，终止。"); return; }
  const storeId = stores[0].store_id;
  console.log(`目标店铺: store_id=${storeId} (${stores[0].store_name})  今天(中国)=${todayChina()}\n`);

  const client = new LingxingClient(loadConfig());
  let globalMaxDate = "";
  let julyBestDate = "";
  let julyBestCnt = 0;
  let sampled = false;

  for (const w of WINDOWS) {
    console.log(`=== ${w.label} ${w.startDate}~${w.endDate} 按 settlementDate 分布 ===\n`);
    const rows = await fetchWindow(client, storeId, w.startDate, w.endDate);
    console.log(`实取 ${rows.length} 行`);
    if (rows.length === 0) { console.log(""); await sleep(800); continue; }

    if (!sampled) {
      sampled = true;
      console.log(`\n样例行日期字段原值（2条）:`);
      for (const r of rows.slice(0, 2)) {
        console.log(`  msku=${toStr(r.msku)}  settlementDate=${toStr(r.settlementDate)}  dateMonth=${toStr(r.dateMonth)}  shipmentDate=${toStr(r.shipmentDate)}  deliveryDate=${toStr(r.deliveryDate)}  orderType=${toStr(r.orderType)}`);
      }
    }

    const byDate = new Map<string, { cnt: number; sales: number; wfsShip: number }>();
    for (const r of rows) {
      const d = toStr(r.settlementDate).slice(0, 10) || "(空)";
      if (!byDate.has(d)) byDate.set(d, { cnt: 0, sales: 0, wfsShip: 0 });
      const b = byDate.get(d)!;
      b.cnt += 1;
      b.sales += toNum(r.salesAmount);
      b.wfsShip += toNum(r.wfsShipmentFee);
    }
    console.log(`\nsettlementDate`.padEnd(15) + "行数".padEnd(7) + "salesAmount$".padEnd(14) + "wfsShipmentFee$");
    for (const [d, b] of [...byDate.entries()].sort((a, b2) => a[0].localeCompare(b2[0]))) {
      console.log(d.padEnd(15) + String(b.cnt).padEnd(7) + b.sales.toFixed(2).padEnd(14) + b.wfsShip.toFixed(2));
      if (d !== "(空)" && d > globalMaxDate) globalMaxDate = d;
      if (w.label === "7月窗" && d !== "(空)" && b.cnt > julyBestCnt) { julyBestCnt = b.cnt; julyBestDate = d; }
    }
    console.log("");
    await sleep(800);
  }

  if (globalMaxDate) {
    const today = new Date(todayChina() + "T00:00:00Z").getTime();
    const maxD = new Date(globalMaxDate + "T00:00:00Z").getTime();
    const lagDays = Math.round((today - maxD) / 86400000);
    console.log(`=== 全局最新 settlementDate = ${globalMaxDate}，距今 ${lagDays} 天 = 当前真实最小滞后 ===\n`);
  } else {
    console.log(`=== 三个窗口均无 settlementDate 数据，无法量化滞后 ===\n`);
  }

  if (julyBestDate) {
    console.log(`=== 验证 startDate/endDate 是否按 settlementDate 过滤：单日查 ${julyBestDate}（七月分布里行数最多日，应≈${julyBestCnt}行）===\n`);
    const rows = await fetchWindow(client, storeId, julyBestDate, julyBestDate);
    console.log(`单日返回 ${rows.length} 行（分布内该日 ${julyBestCnt} 行）→ ${rows.length > 0 ? "参数=按结算日期过滤，假设成立" : "单日查询无数据，参数语义与假设不符，需人工再核"}`);
  }

  console.log("\n探针14b结束。");
}

main().catch((err) => {
  console.error("探针14b执行失败：", err);
  process.exit(1);
});
