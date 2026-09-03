/**
 * src/probeWalmartBillApis.ts
 *
 * AI财务 · 探针18 —— 领星「Walmart回款明细列表 + 结算账单列表」双接口定型验证
 * （只读，零写库，零改动生产）。
 *
 * 背景（需求方2026-08-11提供两份API文档）：
 *   payout/list  = 账单周期头（reportKey账期ID/周期起止/totalPayable/settlementCount/差额）
 *   statement/list = 交易级明细（字段与沃尔玛对账单CSV逐一对应，searchType=6可按账期ID过滤）
 *   若数据保真，收入核算主线自动化（CSV人工导入降级为备用+核查）。
 *
 * 真实基准（需求方上传的结算日2026-07-28对账单CSV，35,525行实测）：
 *   全表净额=$34,548.88（=该账期应付额）；各类目：Sale/Purchase $110,856.30、
 *   WFS Fulfillment fee -$39,733.06、Walmart Product Advertising -$14,430.60(3行)、
 *   WFS InboundTransportationFee -$7,238.91、WFS InventoryRemovalOrder -$6,639.50、
 *   WFS StorageFee -$3,922.52、Keep-it refund -$3,558.46(940行)、WFS LostInventory +$2,694.96、
 *   Return Refund -$1,633.89、WFS Return Processing Fee -$821.90、Review Accelerator -$420.00、
 *   SEM Marketing -$342.91。
 *
 * 本探针做的事（CN2601）：
 *   一、payout/list 拉 2026-05-01~今天 全部账期：逐行打印 reportKey/周期/totalPayable/
 *       结算条数/差额；自动锁定 |totalPayable-34548.88|<1 的账期（=CSV那期）。
 *   二、statement/list 按该 reportKey（searchType=6）分交易类型拉取：
 *       Service Fee / Adjustment / Refund / Campaigns / Misc Adjustment / Dispute 全量
 *       （每类分页上限40页×200，超限如实标注），Sale 只拉第1页看形态（2.7万行不全拉）。
 *       按 transactionType+transactionDescription 聚合 sum(amount)/行数/partnerItemId非空数，
 *       与CSV基准逐类对比。
 *   三、partnerItemId 取值形态实锤：打印样例值（数字13位=ItemID？字符串=MSKU？）——
 *       文档标注"MSKU"与CSV的Partner Item Id(ItemID数字)冲突，以真实返回为准。
 *   四、自守恒：Σ(已拉类目) 与 totalPayable−(Sale+税净额估计)的关系如实打印，供人工判读。
 *
 * 安全边界：只读 LingXing API + 只查 dim_store_config，零写库零改生产。
 * 运行：npx ts-node src/probeWalmartBillApis.ts
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const PAYOUT_PATH = "/basicOpen/multiplatformFinance/walmart/bill/payout/list";
const STATEMENT_PATH = "/basicOpen/multiplatformFinance/walmart/bill/statement/list";
const CSV_TOTAL = 34548.88;
const CSV_BENCH: Array<[string, number]> = [
  ["Sale/Purchase", 110856.30], ["WFS Fulfillment fee", -39733.06],
  ["Walmart Product Advertising", -14430.60], ["WFS InboundTransportationFee", -7238.91],
  ["WFS InventoryRemovalOrder", -6639.50], ["WFS StorageFee", -3922.52],
  ["Keep-it refund", -3558.46], ["WFS LostInventory", 2694.96],
  ["Return Refund", -1633.89], ["WFS Return Processing Fee", -821.90],
  ["Review Accelerator", -420.00], ["SEM Marketing", -342.91],
];
const FULL_TYPES = ["Service Fee", "Adjustment", "Refund", "Campaigns", "Misc Adjustment", "Dispute", "Customer Fee"];

function toNum(v: unknown): number { const n = Number(v); return Number.isFinite(n) ? n : 0; }
function toStr(v: unknown): string { return String(v ?? "").trim(); }
function sleep(ms: number): Promise<void> { return new Promise((r) => setTimeout(r, ms)); }
function todayChina(): string { const d = new Date(); d.setUTCHours(d.getUTCHours() + 8); return d.toISOString().slice(0, 10); }
function extractList(data: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(data)) return data as Array<Record<string, unknown>>;
  const d = data as { list?: unknown } | null;
  if (Array.isArray(d?.list)) return d!.list as Array<Record<string, unknown>>;
  return [];
}
function errInfo(e: unknown): string {
  const anyE = e as { message?: string; data?: unknown };
  return `${anyE?.message ?? String(e)}${anyE?.data ? "  data=" + JSON.stringify(anyE.data).slice(0, 350) : ""}`;
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
  console.log(`目标店铺: ${stores[0].store_name} store_id=${storeId}  今天=${todayChina()}\n`);

  const client = new LingxingClient(loadConfig());

  // ── 一、payout/list 账期列表 ──
  console.log(`=== 一、回款明细列表 payout/list（2026-05-01~今天）===\n`);
  let targetReportKey = "";
  try {
    const resp = await client.request<unknown>({
      method: "POST", path: PAYOUT_PATH,
      params: { sids: [storeId], startDate: "2026-05-01", endDate: todayChina(), offset: 0, length: 200 },
      timeoutMs: 60000,
    });
    const list = extractList((resp as { data?: unknown }).data);
    console.log(`返回 ${list.length} 个账期：`);
    console.log("reportKey".padEnd(28) + "周期".padEnd(26) + "totalPayable$".padEnd(15) + "结算条数".padEnd(10) + "差额".padEnd(10) + "结算时间");
    for (const r of list) {
      const tp = toNum(r.totalPayable);
      console.log(
        toStr(r.reportKey).padEnd(28) + (toStr(r.periodStartDate).slice(0, 10) + "~" + toStr(r.periodEndDate).slice(0, 10)).padEnd(26) +
        tp.toFixed(2).padEnd(15) + toStr(r.settlementCount).padEnd(10) + toStr(r.settlementDifference).padEnd(10) + toStr(r.transactionPostedTimestamp).slice(0, 10),
      );
      if (Math.abs(tp - CSV_TOTAL) < 1 && !targetReportKey) targetReportKey = toStr(r.reportKey);
    }
    if (list.length > 0) {
      console.log(`\n首行原始JSON:\n${JSON.stringify(list[0])}`);
    }
    console.log(`\n锁定CSV对应账期(|totalPayable-${CSV_TOTAL}|<1): ${targetReportKey || "[未命中，请人工从上表指认reportKey后告知代码AI]"}`);
  } catch (e) { console.log(`payout/list失败: ${errInfo(e)}`); }
  await sleep(1000);

  if (!targetReportKey) { console.log("\n无法自动锁定账期，探针18结束（把第一节输出贴回人工指认）。"); return; }

  // ── 二、statement/list 分类型拉取 ──
  console.log(`\n=== 二、结算账单列表 statement/list（reportKey=${targetReportKey}，分交易类型全量）===\n`);
  const agg = new Map<string, { amount: number; rows: number; itemNonEmpty: number; itemSamples: Set<string> }>();
  let pulledTotal = 0;
  for (const t of FULL_TYPES) {
    let typeRows = 0;
    let truncated = false;
    for (let page = 0; page < 40; page++) {
      try {
        const resp = await client.request<unknown>({
          method: "POST", path: STATEMENT_PATH,
          params: {
            sids: [storeId], transactionTypes: [t],
            searchType: 6, searchSingleValue: targetReportKey, searchExactly: true,
            offset: page * 200, length: 200,
          },
          timeoutMs: 60000,
        });
        const list = extractList((resp as { data?: unknown }).data);
        if (list.length === 0) break;
        typeRows += list.length;
        for (const r of list) {
          const key = `${t} | ${toStr(r.transactionDescription)}`;
          if (!agg.has(key)) agg.set(key, { amount: 0, rows: 0, itemNonEmpty: 0, itemSamples: new Set() });
          const a = agg.get(key)!;
          const amt = toNum(r.amount);
          a.amount += amt; a.rows += 1; pulledTotal += amt;
          const pid = toStr(r.partnerItemId);
          if (pid) { a.itemNonEmpty += 1; if (a.itemSamples.size < 3) a.itemSamples.add(pid); }
        }
        if (list.length < 200) break;
        if (page === 39) truncated = true;
        await sleep(400);
      } catch (e) { console.log(`  [${t}] page=${page} 失败: ${errInfo(e)}`); break; }
    }
    console.log(`  类型[${t}] 共拉 ${typeRows} 行${truncated ? "（达40页上限，未取全，合计仅供参考）" : ""}`);
    await sleep(600);
  }

  // Sale 只看形态
  console.log(`\n  类型[Sale] 仅拉第1页看形态（全量2.7万行不拉）:`);
  try {
    const resp = await client.request<unknown>({
      method: "POST", path: STATEMENT_PATH,
      params: { sids: [storeId], transactionTypes: ["Sale"], searchType: 6, searchSingleValue: targetReportKey, searchExactly: true, offset: 0, length: 5 },
      timeoutMs: 60000,
    });
    const list = extractList((resp as { data?: unknown }).data);
    for (const r of list.slice(0, 2)) console.log(`  Sale样例: ${JSON.stringify(r).slice(0, 600)}`);
    const pids = list.map((r) => toStr(r.partnerItemId)).filter(Boolean);
    console.log(`  Sale行 partnerItemId 样例: ${pids.join(", ")}  ← 数字13位=ItemID / 字母数字混合=MSKU（实锤文档标注）`);
  } catch (e) { console.log(`  Sale形态查询失败: ${errInfo(e)}`); }

  // ── 三、类目对比 ──
  console.log(`\n=== 三、逐类目对比（API聚合 vs CSV基准）===\n`);
  console.log("API类目(type|description)".padEnd(52) + "API$".padEnd(14) + "行数".padEnd(7) + "有ItemId".padEnd(9) + "ItemId样例");
  for (const [k, a] of [...agg.entries()].sort((x, y) => Math.abs(y[1].amount) - Math.abs(x[1].amount))) {
    console.log(k.slice(0, 50).padEnd(52) + a.amount.toFixed(2).padEnd(14) + String(a.rows).padEnd(7) + `${a.itemNonEmpty}/${a.rows}`.padEnd(9) + [...a.itemSamples].join(","));
  }
  console.log(`\nCSV基准（供逐行对照）:`);
  for (const [n, v] of CSV_BENCH) console.log(`  ${n.padEnd(36)} ${v.toFixed(2)}`);
  console.log(`\n已拉类目净额合计=$${pulledTotal.toFixed(2)}（不含Sale/税，CSV基准对应部分≈$${(CSV_TOTAL - 110856.30 - 7984.25 - 1.98 + 7887.72 + 96.53 - 131.82 - 1894.63 + 1894.63).toFixed(2)}量级，人工判读）`);
  console.log(`账期totalPayable基准=$${CSV_TOTAL}`);
  console.log("\n探针18结束。");
}

main().catch((err) => { console.error("探针18执行失败：", err); process.exit(1); });
