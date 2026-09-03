/**
 * src/probeAdFeeMskuReconcile.ts
 *
 * 单品现金利润模块 · 探针6 —— 核对"广告费"到底该用哪个数据源（只读，零写库，零改动生产）。
 *
 * 背景：
 *   用户上传了店铺 CN2601-瑞盈龙盛(刘云龙) 的真实沃尔玛对账单CSV（旧版付款报告格式）+ 3张
 *   Walmart Connect 官方广告发票（Sponsored Product Receipt）。核对发现两件事：
 *   1) 对账单CSV里"Walmart Product Advertising"/"SEM Marketing"这两类费用行，Partner Item Id
 *      （即MSKU/ItemID对应列）全部为空——沃尔玛官方账单本身不按item维度出广告费，只按结算周期
 *      给一笔总费用。已用3张真实发票核对到分毫不差：
 *        2026-07-10~07-15 对账单扣费 -6607.08  ↔ 发票78430539 Total $6607.08
 *        2026-07-16~07-22 对账单扣费 -6977.20  ↔ 发票78597070 Total $6977.20
 *        2026-07-22~07-23 对账单扣费  -846.32  ↔ 发票78597073 Total  $846.32
 *   2) 但发票本身是有"广告活动(campaign)"级别明细的，且这个账号的广告活动命名习惯是
 *      "SKU前缀-广告类型-日期(campaignId)"（如 YC00032-自动4.07、JJ8056 词组-4.17），
 *      跟同一账号真实SKU前缀吻合，理论上可以按活动名解析出SKU维度。
 *   3) 代码里发现本来就已经有一张按 item_id/msku 维度落地的真实广告花费表
 *      fact_ads_keyword_daily（stat_date+store_id+item_id+msku+keyword 维度，ad_spend字段），
 *      来源分两路：source_type='lingxing_keyword'（人工广告经领星API自动同步）+
 *      source_type='walmart_auto_csv'（自动广告经沃尔玛后台CSV人工导入）。这张表存在的意义
 *      本身就说明"手动广告用领星API能拿到真实item维度花费，自动广告领星API拿不到只能靠CSV导入"——
 *      跟"广告费是否按ItemID维度算"这个问题直接相关。
 *
 *   本探针要验证的问题：领星结算报表 /basicOpen/multiplatform/profit/report/msku 返回的
 *   platformAdvertisingFee/semMarketingFee/advertisementAmount 这几个字段，按MSKU汇总后的
 *   总和，跟"真实发票总额"、"fact_ads_keyword_daily真实同步总和"这两个基准比，差多少——
 *   如果差异很大且不随窗口稳定，就实锤结算报表的广告费字段是估算/摊派值，不是真实账单，
 *   "单品现金利润"模块的广告费子项应该改用 fact_ads_keyword_daily，不能用结算报表原样字段。
 *
 * 本探针做的事：
 *   1) 从生产DB dim_store_config 按"瑞盈龙盛/CN2601/刘云龙"模糊匹配，找出真实 store_id。
 *   2) 对3个真实发票覆盖的窗口，各查一次结算利润msku接口（取全部list，不只totalSum），
 *      按MSKU汇总 platformAdvertisingFee+semMarketingFee+advertisementAmount，打印合计。
 *   3) 对同样3个窗口，查 fact_ads_keyword_daily，按 source_type 分组 SUM(ad_spend)，
 *      并给出去重后的MSKU�covered数量，打印合计。
 *   4) 每个窗口打印三方对照：真实发票总额 | 结算报表广告字段合计 | fact_ads_keyword_daily合计，
 *      并计算与真实发票的绝对差值和比例，供人工判断结算报表字段的可信度。
 *
 * 安全边界：
 *   - 只读 LingXing API + 只读 DB SELECT，零写库、零改动生产、不建表。
 *
 * 运行（生产机，由部署工程师执行）：
 *   npx ts-node src/probeAdFeeMskuReconcile.ts
 *
 * 用法：把完整输出贴回来，重点看每个窗口的三方对照表。
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const SETTLEMENT_MSKU_PATH = "/basicOpen/multiplatform/profit/report/msku";
const WALMART_PLATFORM_CODE = "10008";

// 真实发票基准（来自用户上传的3张 Walmart Connect Sponsored Product 发票，人工核对到分毫不差）
const INVOICE_WINDOWS: Array<{ label: string; startDate: string; endDate: string; realInvoiceTotal: number; invoiceNo: string }> = [
  { label: "窗口1", startDate: "2026-07-10", endDate: "2026-07-15", realInvoiceTotal: 6607.08, invoiceNo: "78430539" },
  { label: "窗口2", startDate: "2026-07-16", endDate: "2026-07-22", realInvoiceTotal: 6977.20, invoiceNo: "78597070" },
  { label: "窗口3", startDate: "2026-07-22", endDate: "2026-07-23", realInvoiceTotal: 846.32, invoiceNo: "78597073" },
];

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function toNum(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

async function main() {
  const db = await mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });

  const [allStores] = await db.execute(
    `SELECT store_id, store_name FROM dim_store_config WHERE platform = 'walmart'`,
  );
  const stores = allStores as Array<{ store_id: string; store_name: string }>;
  const keywords = ["瑞盈龙盛", "CN2601", "刘云龙"];
  const matched = stores.filter((s) => keywords.some((kw) => (s.store_name || "").includes(kw)));
  console.log(`按关键字 [${keywords.join(", ")}] 匹配到 ${matched.length} 个店铺：`);
  for (const s of matched) console.log(`  store_id=${s.store_id}  store_name=${s.store_name}`);

  if (matched.length === 0) {
    console.log("\n没匹配到店铺，把上面 dim_store_config 全量列表贴回来人工指认。全量列表：");
    for (const s of stores) console.log(`  store_id=${s.store_id}  store_name=${s.store_name}`);
    await db.end();
    return;
  }
  const store = matched[0];
  if (matched.length > 1) {
    console.log(`\n匹配到不止一个，本探针默认取第一个 store_id=${store.store_id} (${store.store_name})，如不对请重新指定。`);
  }

  const cfg = loadConfig();
  const client = new LingxingClient(cfg);

  console.log(`\n目标店铺: store_id=${store.store_id} (${store.store_name})\n`);

  for (const w of INVOICE_WINDOWS) {
    console.log(`\n########## ${w.label}: ${w.startDate} ~ ${w.endDate} (对照发票 ${w.invoiceNo}, 真实总额 $${w.realInvoiceTotal}) ##########`);

    // ── A. 结算利润msku接口：按MSKU汇总广告相关字段 ──
    let settlementAdFeeSum = 0;
    let settlementRowCount = 0;
    let settlementMskuSet = new Set<string>();
    try {
      const resp = await client.request<{ total?: number; list?: Array<Record<string, unknown>> }>({
        method: "POST",
        path: SETTLEMENT_MSKU_PATH,
        params: {
          offset: 0,
          length: 200,
          platformCodeS: [WALMART_PLATFORM_CODE],
          sids: store.store_id,
          startDate: w.startDate,
          endDate: w.endDate,
        },
        timeoutMs: 30000,
      });
      const data = (resp as unknown as { data?: { total?: number; list?: Array<Record<string, unknown>> } }).data;
      const list = data?.list ?? [];
      settlementRowCount = data?.total ?? list.length;
      if (settlementRowCount > list.length) {
        console.log(`  [注意] 接口total=${settlementRowCount}，本次只取了length=200，可能未取全，合计仅供参考。`);
      }
      for (const row of list) {
        const msku = String(row.msku ?? row.sku ?? "");
        if (msku) settlementMskuSet.add(msku);
        settlementAdFeeSum +=
          toNum(row.platformAdvertisingFee) + toNum(row.semMarketingFee) + toNum(row.advertisementAmount);
      }
      console.log(`  A) 结算报表list条数=${list.length}（total=${settlementRowCount}），覆盖MSKU数=${settlementMskuSet.size}`);
      console.log(`     platformAdvertisingFee+semMarketingFee+advertisementAmount 合计 = ${settlementAdFeeSum.toFixed(2)}`);
    } catch (err) {
      console.log(`  A) 结算报表请求失败: ${err instanceof Error ? err.message : String(err)}`);
    }
    await sleep(400);

    // ── B. fact_ads_keyword_daily：真实按MSKU/ItemID广告花费 ──
    const [adRows] = await db.execute(
      `SELECT source_type, SUM(ad_spend) AS spend_sum, COUNT(*) AS row_cnt,
              COUNT(DISTINCT COALESCE(NULLIF(msku,''), item_id)) AS msku_cnt
         FROM fact_ads_keyword_daily
        WHERE platform = 'walmart' AND store_id = ? AND stat_date BETWEEN ? AND ?
        GROUP BY source_type`,
      [store.store_id, w.startDate, w.endDate],
    );
    const adRowsTyped = adRows as Array<{ source_type: string; spend_sum: string | null; row_cnt: number; msku_cnt: number }>;
    let factAdSpendSum = 0;
    console.log(`  B) fact_ads_keyword_daily 按source_type分组:`);
    if (adRowsTyped.length === 0) {
      console.log(`     [无数据] 该窗口在 fact_ads_keyword_daily 里没有任何行`);
    }
    for (const r of adRowsTyped) {
      const spend = toNum(r.spend_sum);
      factAdSpendSum += spend;
      console.log(`     source_type=${r.source_type}: spend=${spend.toFixed(2)}, 行数=${r.row_cnt}, 覆盖MSKU/ItemID数=${r.msku_cnt}`);
    }
    console.log(`     合计 = ${factAdSpendSum.toFixed(2)}`);

    // ── 三方对照 ──
    const diffSettlement = settlementAdFeeSum - (-w.realInvoiceTotal); // 结算报表字段是负数口径，真实发票是扣费金额(正数标注)，统一按"扣费额的绝对值"比较见下方百分比
    const settlementAbs = Math.abs(settlementAdFeeSum);
    const factAbs = Math.abs(factAdSpendSum);
    const settlementPct = w.realInvoiceTotal > 0 ? ((settlementAbs / w.realInvoiceTotal) * 100).toFixed(1) : "-";
    const factPct = w.realInvoiceTotal > 0 ? ((factAbs / w.realInvoiceTotal) * 100).toFixed(1) : "-";
    console.log(`\n  ── 三方对照 (${w.label}) ──`);
    console.log(`     真实发票总额(基准)         : $${w.realInvoiceTotal.toFixed(2)}`);
    console.log(`     结算报表广告字段合计(绝对值): $${settlementAbs.toFixed(2)}  (占真实发票 ${settlementPct}%)`);
    console.log(`     fact_ads_keyword_daily合计  : $${factAbs.toFixed(2)}  (占真实发票 ${factPct}%)`);
  }

  await db.end();
  console.log(`\n探针6结束。`);
}

main().catch((err) => {
  console.error("探针6执行失败：", err);
  process.exit(1);
});
