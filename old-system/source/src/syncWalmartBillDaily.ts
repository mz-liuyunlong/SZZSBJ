/**
 * syncWalmartBillDaily.ts
 *
 * AI财务 · 收入主线正式同步（一期首条脚本）——领星Walmart账单双接口 → 账期周期表 + 周期×MSKU×类目事实表。
 *
 * 设计依据：docs/AI财务_单品现金利润_数据与计算逻辑定稿_v1.md（v1.5+探针18~18h终稿）
 *   1) payout/list  → upsert fact_reconciliation_period（登记账期头；只更新 total_payable/payment_date/
 *      report_key/currency，**绝不触碰人工列** period_status/confirmed_by/confirmed_at/remark）。
 *   2) statement/list → **必须按 startDate/endDate（入账日期）拉取**（探针18h：该路径100%完整；
 *      searchType=6账期ID过滤不可靠，禁用）。逐日拉取、RAW留痕（raw_lingxing_api）。
 *   3) 归桶：postedDate∈[period_start, period_end) 归入账期；PaymentSummary汇总行不入类目聚合。
 *      **只聚合"整期天数全部拉齐"的账期**（部分天数聚合会写坏周期粒度数据）。
 *   4) 守恒自检：每个聚合账期 Σ(类目金额) vs total_payable，偏差>max(1%,$50) →
 *      写 event_finance_sentinel_alert（equation='revenue'，只增）。
 *   5) 唯一键规约：FACT聚合粒度=(store,period,msku,fee_category)；禁用 uniqueNo（报告级同值）
 *      与数字id（19位精度丢失）；transactionKey仅留档RAW。
 *
 * 写入范围（严格限定）：fact_reconciliation_period / fact_reconciliation_item /
 *   fact_ad_credit_detail（2026-08-11新增：返还/赔付类行级留档，AI财务·返还明细页数据源）/
 *   fact_commission_saving（2026-08-11新增：佣金折扣聚合，激励中心口径，信息指标不进守恒）/
 *   event_finance_sentinel_alert / raw_lingxing_api / sync_task_log —— 全部为AI财务新表或既有留痕表，
 *   不触碰任何现有业务表；本脚本不挂cron（挂cron需需求方单独批准）。
 *
 * 用法（生产）：
 *   npx ts-node src/syncWalmartBillDaily.ts                                    # 默认全店铺,近20天窗口
 *   npx ts-node src/syncWalmartBillDaily.ts --store=110687423514268160 --startDate=2026-07-11 --endDate=2026-07-25
 *   npx ts-node src/syncWalmartBillDaily.ts --days=45                          # 全店铺,近45天
 * 环境变量：DB_* / 领星凭据（loadConfig），全部读.env。
 */

import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const PAYOUT_PATH = "/basicOpen/multiplatformFinance/walmart/bill/payout/list";
const STATEMENT_PATH = "/basicOpen/multiplatformFinance/walmart/bill/statement/list";
const TASK_NAME = "walmart_bill_daily_sync";
const PAGE_SIZE = 200;
const MAX_PAGES_PER_DAY = 60;
const PAYOUT_LOOKBACK_DAYS = 150;
const DELAY_PAGE_MS = 350;
const DELAY_DAY_MS = 600;
const DELAY_STORE_MS = 2000;

// 类目映射（transactionType|transactionDescription → fee_category；未命中→other，desc留档extra维度）
const CATEGORY_MAP: Record<string, string> = {
  "Sale|Purchase": "sale",
  "Refund|Keep-it refund": "refund_keepit",
  "Refund|Return Refund": "refund_return",
  "Refund|Seller Initiated Returns": "refund_seller_initiated",
  "Adjustment|WFS Fulfillment fee": "wfs_fulfillment",
  "Adjustment|WFS LostInventory": "lost_inventory",
  "Adjustment|WFS FoundInventory": "found_inventory",
  "Adjustment|WFS DamageInWarehouse": "damage_warehouse",
  "Adjustment|WFS Return Processing Fee": "return_processing",
  "Adjustment|WFS Returned Item Disposal Fee": "returned_item_disposal",
  "Service Fee|Walmart Product Advertising": "ad_platform",
  "Service Fee|WFS InboundTransportationFee": "inbound_transport",
  "Service Fee|WFS InventoryRemovalOrder": "removal",
  "Service Fee|WFS StorageFee": "storage",
  "Service Fee|Review Accelerator": "review_accelerator",
  "Service Fee|WFS PrepServiceFee": "prep_service",
  "Campaigns|SEM Marketing": "sem",
  "Other|WFS RC_InventoryDisposalFee": "rc_inventory_disposal",
  // 2026-08-11 需求方批准新增（CN2602对账单实证；此前落 other:* 杂项桶，存量已由 sql/044 迁移）
  "Service Fee|Walmart Product Advertising Credits": "ad_credit",
  "Adjustment|WFS Refund": "wfs_refund",
  // 2026-08-12 批2 需求方批准正式命名（盘点实锤 tType=Other）
  "Other|WFS DiscountAdjustment": "wfs_discount_adjustment",
};

// 返还/赔付行级留档（AI财务「返还明细」页面数据源）：
//   ① 已知返还类目白名单（不论正负，found_inventory冲回为负也留档）；
//   ② 自发现规则（2026-08-11需求方要求"没体现的返还项目要体现出来"）：
//      非Sale/Refund/PaymentSummary的行金额>0 = 沃尔玛向我们返钱，未知类型也一律留档，
//      类目自动带 other:* 标签浮出，供需求方后续正式命名归类。
const CREDIT_DETAIL_CATEGORIES = new Set(["ad_credit", "wfs_refund", "lost_inventory", "found_inventory"]);
const NON_CREDIT_TYPES = new Set(["Sale", "Refund", "PaymentSummary"]);
// 2026-08-12 批2：自发现slug的正式命名（transactionType未实锤的类目走slug级改名，避免臆测组合键；
//   历史行由 sql/050 一次性迁移，此表保证新导入直接落正式名）
const OTHER_SLUG_RENAME: Record<string, string> = {
  "other:wfs_discountadjustment": "wfs_discount_adjustment",
  "other:wfs_inventorytransferfee": "inventory_transfer",
  "other:wfs_charge": "wfs_charge_misc",
};
function categoryOf(tType: string, desc: string): string {
  const hit = CATEGORY_MAP[`${tType}|${desc}`];
  if (hit) return hit;
  const slug = "other:" + (desc || tType || "unknown").toLowerCase().replace(/[^a-z0-9]+/g, "_").slice(0, 40);
  return OTHER_SLUG_RENAME[slug] ?? slug;
}

function getArg(name: string, def = ""): string {
  const p = `--${name}=`;
  const a = process.argv.find((x) => x.startsWith(p));
  return a ? a.slice(p.length) : def;
}
function chinaDate(offsetDays = 0): string {
  const d = new Date();
  d.setUTCHours(d.getUTCHours() + 8);
  d.setUTCDate(d.getUTCDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}
function addDays(dateStr: string, n: number): string {
  const d = new Date(dateStr + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
function toNum(v: unknown): number { const n = Number(v); return Number.isFinite(n) ? n : 0; }
function toStr(v: unknown): string { return String(v ?? "").trim(); }
function sleep(ms: number): Promise<void> { return new Promise((r) => setTimeout(r, ms)); }
function extractList(data: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(data)) return data as Array<Record<string, unknown>>;
  const d = data as { list?: unknown } | null;
  if (Array.isArray(d?.list)) return d!.list as Array<Record<string, unknown>>;
  return [];
}

async function saveRawPage(
  db: mysql.Connection, path: string, params: Record<string, unknown>, response: unknown, dataDate: string,
): Promise<void> {
  const rawJson = JSON.stringify(response);
  const rawHash = crypto.createHash("md5").update(rawJson).digest("hex").slice(0, 64);
  await db.query(
    `INSERT IGNORE INTO raw_lingxing_api
       (api_path, request_method, request_params_json, response_json, response_code, is_success, data_date, raw_hash)
     VALUES (?, 'POST', ?, ?, '0', 1, ?, ?)`,
    [path, JSON.stringify(params), rawJson, dataDate, rawHash],
  );
}

interface Period { reportKey: string; start: string; end: string; totalPayable: number; paymentDate: string; currency: string }

async function syncPayoutPeriods(
  client: LingxingClient, db: mysql.Connection, storeId: string,
): Promise<Period[]> {
  const params = {
    sids: [storeId], startDate: chinaDate(-PAYOUT_LOOKBACK_DAYS), endDate: chinaDate(0), offset: 0, length: 200,
  };
  const resp = await client.request<unknown>({ method: "POST", path: PAYOUT_PATH, params, timeoutMs: 60000 });
  await saveRawPage(db, PAYOUT_PATH, params, (resp as { data?: unknown }).data, chinaDate(0));
  const list = extractList((resp as { data?: unknown }).data);
  const periods: Period[] = [];
  for (const r of list) {
    const p: Period = {
      reportKey: toStr(r.reportKey),
      start: toStr(r.periodStartDate).slice(0, 10),
      end: toStr(r.periodEndDate).slice(0, 10),
      totalPayable: toNum(r.totalPayable),
      paymentDate: toStr(r.transactionPostedTimestamp).slice(0, 10),
      currency: toStr(r.currency) || "USD",
    };
    if (!p.start || !p.end) continue;
    periods.push(p);
    // upsert：绝不触碰人工列（period_status/confirmed_by/confirmed_at/remark）
    await db.query(
      `INSERT INTO fact_reconciliation_period
         (platform, store_id, period_start, period_end, payment_date, report_key, total_payable, currency_code, import_task_id)
       VALUES ('walmart', ?, ?, ?, ?, ?, ?, ?, ?)
       ON DUPLICATE KEY UPDATE
         payment_date = VALUES(payment_date),
         report_key   = VALUES(report_key),
         total_payable= VALUES(total_payable),
         currency_code= VALUES(currency_code)`,
      [storeId, p.start, p.end, p.paymentDate || null, p.reportKey, p.totalPayable, p.currency, TASK_NAME],
    );
  }
  return periods;
}

async function pullStatementDay(
  client: LingxingClient, db: mysql.Connection, storeId: string, day: string,
): Promise<Array<Record<string, unknown>>> {
  const rows: Array<Record<string, unknown>> = [];
  for (let page = 0; page < MAX_PAGES_PER_DAY; page++) {
    const params = { sids: [storeId], startDate: day, endDate: day, offset: page * PAGE_SIZE, length: PAGE_SIZE };
    let resp: unknown = null;
    let lastErr: unknown = null;
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        resp = await client.request<unknown>({ method: "POST", path: STATEMENT_PATH, params, timeoutMs: 60000 });
        lastErr = null;
        break;
      } catch (e) { lastErr = e; await sleep(2000 * (attempt + 1)); }
    }
    if (lastErr) throw lastErr;
    const data = (resp as { data?: unknown }).data;
    await saveRawPage(db, STATEMENT_PATH, params, data, day);
    const list = extractList(data);
    if (list.length === 0) break;
    rows.push(...list);
    if (list.length < PAGE_SIZE) break;
    await sleep(DELAY_PAGE_MS);
  }
  return rows;
}

interface AggRow { msku: string; gtin: string; category: string; amount: number; cnt: number }

function aggregate(rows: Array<Record<string, unknown>>): Map<string, AggRow> {
  const m = new Map<string, AggRow>();
  for (const r of rows) {
    const tType = toStr(r.transactionType);
    if (tType === "PaymentSummary") continue; // 汇总行不入类目
    const desc = toStr(r.transactionDescription);
    const category = categoryOf(tType, desc);
    const msku = toStr(r.partnerItemId); // 实测=MSKU形态；店铺级行为空串
    const key = `${msku}|${category}`;
    if (!m.has(key)) m.set(key, { msku, gtin: toStr(r.partnerGtin), category, amount: 0, cnt: 0 });
    const a = m.get(key)!;
    a.amount += toNum(r.amount);
    a.cnt += 1;
    if (!a.gtin) a.gtin = toStr(r.partnerGtin);
  }
  return m;
}

async function main() {
  const storeFilter = getArg("store");
  const daysArg = Number(getArg("days", "20"));
  const startArg = getArg("startDate");
  const endArg = getArg("endDate");
  const winStart = startArg || chinaDate(-(Number.isFinite(daysArg) && daysArg > 0 ? daysArg : 20));
  const winEnd = endArg || chinaDate(0);

  console.log("═".repeat(60));
  console.log(`  Walmart账单同步  窗口 ${winStart} → ${winEnd}${storeFilter ? `  store=${storeFilter}` : "  (全店铺)"}`);
  console.log("═".repeat(60));

  const db = await mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1", port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "", password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
  const client = new LingxingClient(loadConfig());

  const [storeRows] = await db.execute(
    `SELECT store_id, store_name FROM dim_store_config WHERE platform='walmart'${storeFilter ? " AND store_id = ?" : ""}`,
    storeFilter ? [storeFilter] : [],
  );
  const stores = storeRows as Array<{ store_id: string; store_name: string }>;
  console.log(`店铺数: ${stores.length}\n`);

  let periodsAgg = 0, itemsUpserted = 0, alerts = 0, errors = 0;

  for (const store of stores) {
    console.log(`──── ${store.store_name} (${store.store_id}) ────`);
    try {
      // 1) 账期头
      const periods = await syncPayoutPeriods(client, db, store.store_id);
      console.log(`  账期登记/刷新 ${periods.length} 个`);

      // (store,msku)→item_id 唯一命中映射
      const [dimRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT msku, MAX(item_id) AS item_id FROM dim_product
          WHERE platform='walmart' AND store_id=? AND COALESCE(msku,'')<>''
          GROUP BY msku HAVING COUNT(DISTINCT item_id)=1`,
        [store.store_id],
      );
      const itemMap = new Map<string, string>();
      for (const r of dimRows) itemMap.set(String(r.msku), String(r.item_id));

      // 2) 选择"与窗口相交且整期可拉齐"的账期，逐期整期拉取
      const targets = periods.filter((p) => p.start <= winEnd && p.end >= winStart);
      for (const p of targets) {
        const dayRows: Array<Record<string, unknown>> = [];
        // 归桶=postedDate∈[start,end)：拉 [start, end-1]；另拉end当日仅用于PaymentSummary核对(不入聚合)
        let ok = true;
        for (let d = p.start; d < p.end; d = addDays(d, 1)) {
          try {
            const rows = await pullStatementDay(client, db, store.store_id, d);
            for (const r of rows) (r as Record<string, unknown>).__pullDay = d; // 行级留档需要入账日
            dayRows.push(...rows);
          } catch (e) {
            ok = false;
            errors++;
            console.log(`  ⚠️ ${p.start}~${p.end} 拉取 ${d} 失败，跳过该账期聚合（下次运行重试）: ${e instanceof Error ? e.message : String(e)}`);
            break;
          }
          await sleep(DELAY_DAY_MS);
        }
        if (!ok) continue;
        if (dayRows.length === 0) { console.log(`  账期 ${p.start}~${p.end}: 明细0行（可能未结算），跳过`); continue; }

        const aggMap = aggregate(dayRows);
        let periodSum = 0;
        for (const a of aggMap.values()) periodSum += a.amount;

        // 3) upsert items（整期聚合值覆盖）
        for (const a of aggMap.values()) {
          await db.query(
            `INSERT INTO fact_reconciliation_item
               (platform, store_id, period_start, period_end, item_id, gtin, msku, fee_category, amount, txn_count, currency_code, source_task_id)
             VALUES ('walmart', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
             ON DUPLICATE KEY UPDATE
               item_id=VALUES(item_id), gtin=VALUES(gtin), amount=VALUES(amount),
               txn_count=VALUES(txn_count), currency_code=VALUES(currency_code), source_task_id=VALUES(source_task_id)`,
            [store.store_id, p.start, p.end, itemMap.get(a.msku) ?? "", a.gtin, a.msku, a.category,
             a.amount, a.cnt, p.currency, TASK_NAME],
          );
          itemsUpserted++;
        }
        periodsAgg++;

        // 3.5) 返还/赔付类行级留档（2026-08-11新增；仅新表fact_ad_credit_detail，不影响原聚合）
        //      白名单类目 + 自发现（费用/调整类正数行=返钱，未知类型也留档，other:*标签浮出）
        for (const r of dayRows) {
          const tType = toStr(r.transactionType);
          if (tType === "PaymentSummary") continue;
          const desc = toStr(r.transactionDescription);
          const cat = categoryOf(tType, desc);
          const amtVal = toNum(r.amount);
          const capture = CREDIT_DETAIL_CATEGORIES.has(cat)
            || (amtVal > 0 && !NON_CREDIT_TYPES.has(tType));
          if (!capture) continue;
          const srcRef = toStr(r.transactionKey)
            || crypto.createHash("md5").update(JSON.stringify(r)).digest("hex").slice(0, 32);
          await db.query(
            `INSERT INTO fact_ad_credit_detail
               (platform, store_id, posted_date, period_start, period_end, fee_category,
                transaction_type, transaction_desc, amount, currency_code, campaign_id,
                source_ref, source_system, source_task_id)
             VALUES ('walmart', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'lingxing_api', ?)
             ON DUPLICATE KEY UPDATE
               posted_date=VALUES(posted_date), period_start=VALUES(period_start), period_end=VALUES(period_end),
               fee_category=VALUES(fee_category), amount=VALUES(amount), source_task_id=VALUES(source_task_id)`,
            [store.store_id, toStr(r.__pullDay), p.start, p.end, cat, tType, desc,
             amtVal, p.currency, toStr(r.campaignId ?? ""), srcRef, TASK_NAME],
          );
        }

        // 3.6) 佣金折扣聚合（2026-08-11探针20定案；仅新表fact_commission_saving，信息指标不进守恒）
        //      口径=Sale行commissionSaving按(msku×激励计划)聚合——与激励中心You've saved同口径
        //      （CN2601对数差0.019%实证）；Refund行不计（页面口径为销售侧）。
        const commAgg = new Map<string, { msku: string; program: string; amount: number; cnt: number }>();
        for (const r of dayRows) {
          if (toStr(r.transactionType) !== "Sale") continue;
          const saving = toNum(r.commissionSaving);
          if (saving === 0) continue;
          const msku = toStr(r.partnerItemId);
          const program = toStr(r.commissionIncentiveProgram);
          const key = `${msku}|${program}`;
          if (!commAgg.has(key)) commAgg.set(key, { msku, program, amount: 0, cnt: 0 });
          const c = commAgg.get(key)!;
          c.amount += saving;
          c.cnt += 1;
        }
        for (const c of commAgg.values()) {
          await db.query(
            `INSERT INTO fact_commission_saving
               (platform, store_id, period_start, period_end, msku, item_id, incentive_program,
                saving_amount, txn_count, currency_code, source_task_id)
             VALUES ('walmart', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
             ON DUPLICATE KEY UPDATE
               item_id=VALUES(item_id), saving_amount=VALUES(saving_amount),
               txn_count=VALUES(txn_count), source_task_id=VALUES(source_task_id)`,
            [store.store_id, p.start, p.end, c.msku, itemMap.get(c.msku) ?? "", c.program,
             c.amount, c.cnt, p.currency, TASK_NAME],
          );
        }

        // 4) 守恒自检
        const diff = periodSum - p.totalPayable;
        const pct = p.totalPayable !== 0 ? Math.abs(diff / p.totalPayable) * 100 : 0;
        const hit = Math.abs(diff) > Math.max(50, Math.abs(p.totalPayable) * 0.01) ? 1 : 0;
        await db.query(
          `INSERT INTO event_finance_sentinel_alert
             (equation, store_id, period_month, expected_total, actual_total, diff_amount, diff_pct, threshold_hit, detail_json)
           VALUES ('revenue', ?, ?, ?, ?, ?, ?, ?, ?)`,
          [store.store_id, p.start.slice(0, 7), p.totalPayable, periodSum, diff, pct, hit,
           JSON.stringify({ period_start: p.start, period_end: p.end, report_key: p.reportKey, rows: dayRows.length, categories: aggMap.size })],
        );
        if (hit) alerts++;
        console.log(`  账期 ${p.start}~${p.end}: 明细${dayRows.length}行 → ${aggMap.size}个(msku×类目) Σ=$${periodSum.toFixed(2)} vs 应付$${p.totalPayable.toFixed(2)} 差$${diff.toFixed(2)}(${pct.toFixed(2)}%) ${hit ? "🚨超阈值" : "✅守恒"}`);
      }
    } catch (e) {
      errors++;
      console.log(`  ⚠️ 店铺级失败: ${e instanceof Error ? e.message : String(e)}`);
    }
    await sleep(DELAY_STORE_MS);
  }

  await db.query(
    `INSERT INTO sync_task_log
       (task_name, source_system, target_table, status, inserted_count, updated_count, failed_count, finished_at, error_message)
     VALUES (?, 'lingxing_api', 'fact_reconciliation_period,fact_reconciliation_item', ?, ?, ?, ?, NOW(), ?)`,
    [TASK_NAME, errors > 0 ? "failed" : "success", periodsAgg, itemsUpserted, errors, alerts > 0 ? `${alerts}个账期守恒超阈值` : null],
  );
  await db.end();
  console.log(`\n完成：聚合账期=${periodsAgg}  明细upsert=${itemsUpserted}  守恒报警=${alerts}  错误=${errors}`);
}

main().catch((err) => { console.error("同步失败：", err); process.exit(1); });
