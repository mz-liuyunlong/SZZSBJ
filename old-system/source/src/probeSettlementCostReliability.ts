/**
 * src/probeSettlementCostReliability.ts
 *
 * 单品现金利润模块 · 探针2 —— 拉取"结算利润"接口的真实数据做校验（只读，零写库，零改动生产）。
 *
 * 背景（2026-07-31 用户补充的领星帮助中心文档《多平台-结算利润（新）》+ 用户确认）：
 *   结算利润接口（/basicOpen/multiplatform/profit/report/sku、/msku）返回的
 *   purchaseAmount（采购成本）/ transportationAmount（头程费用）/ otherAmount（其他成本），
 *   取值逻辑取决于领星账号"业务配置-多平台-数据配置"里的"成本取值方式"：
 *     - 计价方法：优先取【销售出库单】的真实成本，没有出库单才退回固定值（产品管理-采购成本/头程费用）
 *     - 固定值：不管有没有出库单，一律取产品管理里配置的固定采购成本/头程费用
 *   用户已确认：生产账号用的是【计价方法】——也就是说 purchaseAmount/transportationAmount
 *   本身就是领星已经核算完的真实成本，可以暂时作为单品现金利润"成本侧"的数据路径，
 *   不必再另建采购单+发货单的真实成本归集链路（探针1摸出来的那条路先搁置，不是不需要，是"暂时"不需要）。
 *   本探针的验证①（横向对比 dim_product_cost_config 配置均价）仍然保留，作为一次性 sanity check——
 *   如果实测下来隐含单位成本大面积等于配置均价，说明这个账号的"计价方法"在很多SKU上其实退回到了
 *   固定值兜底（比如缺销售出库单数据），需要在设计表结构前提前发现，而不是等上线后才发现口径不对。
 *
 * v2 修订说明（首版探针1轮跑出来两个窗口都是0条，问题排查后修订）：
 *   1) v1 用 lag=7/window=7 的窄近期窗口，且完全不传 sids/currencyCode。已知能跑通生产的
 *      syncWfsFeeFromSettlement.ts 用的是 SETTLE_LAG_DAYS=2、WINDOW_DAYS=60 的宽窗口，且是
 *      按已知真实 msku 逐个 searchField=msku 精确查询，不是"裸查全平台"。v1 两者都没照做，
 *      不能确定 0 条是"真的没数据"还是"参数缺了必要的范围限定"。
 *   2) v2 改为先在生产 DB 里查真实数据：dim_store_config 拿 platform='walmart' 的真实 store_id，
 *      raw_lingxing_settlement_order 拿最近确实同步到过的真实 msku 样本——这些都是已经在生产
 *      跑通的东西，不是猜的。
 *   3) v2 先跑一轮诊断：对同一个宽日期窗口（T+2 结算延迟、60天），依次尝试"裸查/带
 *      currencyCode/带sids/带sids+currencyCode/按真实msku精确查询"这几种参数组合，每种都打印
 *      返回条数，找到第一个能返回非空数据的组合，再用这个组合去跑正式的窗口A/B横向纵向对比。
 *      如果所有组合都是0条，会如实打出来，不臆造数据。
 *
 * v3 修订说明（v2实测：dim_store_config查到10个真实店铺，但取样msku那步SQL报错，脚本中途退出，
 *   没跑到真正的LingXing接口调用）：
 *   v2版 `SELECT DISTINCT msku_query FROM raw_lingxing_settlement_order ORDER BY capture_batch DESC`
 *   在生产MySQL严格模式下报 ER_FIELD_IN_ORDER_NOT_SELECT（DISTINCT下ORDER BY列必须在SELECT列表里）。
 *   v3改成 `GROUP BY msku_query ORDER BY MAX(capture_batch) DESC` 取代 DISTINCT，逻辑不变，纯语法修复。
 *
 * 验证①（横向）：结算利润里 purchaseAmount/salesNum（隐含单位采购成本）
 *                是否等于 dim_product_cost_config 里同一 msku 的 purchase_cost？
 *                - 基本相等 → 极可能是固定值模式（配置均价），不可直接当真实成本用。
 *                - 明显不等 → 极可能是计价方法模式（真实出库成本），可以考虑直接复用。
 * 验证②（纵向）：同一个 msku，两个不重叠时间窗口，隐含单位采购成本是否随时间变化。
 *                - 固定值配置均价通常不随时间变 → 两窗口应几乎一致。
 *                - 真实出库成本会随批次波动 → 两窗口大概率不同。
 *
 * 安全边界：
 *   - 只读 LingXing API：/basicOpen/multiplatform/profit/report/msku 是查询接口，
 *     LingxingClient.assertReadOnlyPath 兜底拦截任何写类路径，本探针未触碰任何写接口。
 *   - 数据库只做 SELECT（dim_store_config / raw_lingxing_settlement_order / dim_product_cost_config），
 *     零 INSERT/UPDATE/DELETE，不落新 RAW 表、不建表、不改任何现有脚本。
 *
 * 运行（生产机，由部署工程师执行，需要真实 .env 网络/凭证 + 生产 DB 连接）：
 *   npx ts-node src/probeSettlementCostReliability.ts                  # 默认：诊断 + T+2/60天双窗口对比
 *   npx ts-node src/probeSettlementCostReliability.ts --limit=100      # 多看一些msku
 *   npx ts-node src/probeSettlementCostReliability.ts --window-days=30 # 正式对比窗口天数（默认30/30）
 *
 * 用法：把完整输出贴回来（尤其是"诊断"那一段每个参数组合的返回条数，以及最后的汇总结论）。
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const SETTLEMENT_MSKU_PATH = "/basicOpen/multiplatform/profit/report/msku";
const WALMART_PLATFORM_CODE = "10008";

function getArg(name: string, fallback: string): string {
  const prefix = `--${name}=`;
  const arg = process.argv.find((a) => a.startsWith(prefix));
  return arg ? arg.slice(prefix.length) : fallback;
}

function shanghaiDate(offsetDays = 0): string {
  const d = new Date(Date.now() + 8 * 3600 * 1000);
  d.setUTCDate(d.getUTCDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

interface SettlementMskuRow {
  storeId?: string | number;
  storeName?: string;
  msku?: string;
  localSku?: string;
  currencyCode?: string;
  salesNum?: number;
  salesAmount?: number;
  purchaseAmount?: number;
  transportationAmount?: number;
  otherAmount?: number;
  tailAmount?: number;
  grossProfit?: number;
  [k: string]: unknown;
}

interface SettlementMskuResponse {
  data?: {
    totalSum?: SettlementMskuRow;
    list?: SettlementMskuRow[];
  };
  total?: number;
}

async function callSettlement(
  client: LingxingClient,
  params: Record<string, unknown>,
): Promise<SettlementMskuRow[]> {
  const resp = await client.request<SettlementMskuResponse["data"]>({
    method: "POST",
    path: SETTLEMENT_MSKU_PATH,
    params,
    timeoutMs: 30000,
  });
  return (resp as unknown as SettlementMskuResponse).data?.list ?? [];
}

async function main() {
  const limit = Number(getArg("limit", "50"));
  const windowDays = Number(getArg("window-days", "30"));

  const cfg = loadConfig();
  const client = new LingxingClient(cfg);

  const db = await mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });

  // 1) 先从生产 DB 拿真实 store_id（dim_store_config，syncWfsFeeFromSettlement.ts 已验证可用的同一张表）
  const [storeRows] = await db.execute(
    `SELECT store_id, store_name FROM dim_store_config WHERE platform = 'walmart'`,
  );
  const storeIds = (storeRows as Array<{ store_id: string }>).map((r) => String(r.store_id)).filter(Boolean);
  console.log(`dim_store_config 查到 walmart 店铺 ${storeIds.length} 个：${storeIds.join(",") || "(空)"}`);

  // 2) 再从生产 DB 拿真实已同步过的 msku 样本（raw_lingxing_settlement_order，同一张表已证明生产在写）
  //    v3修订：v2版 SELECT DISTINCT ... ORDER BY capture_batch 在生产 MySQL 严格模式下报
  //    ER_FIELD_IN_ORDER_NOT_SELECT（DISTINCT 下 ORDER BY 列必须在 SELECT 列表里），改成 GROUP BY + MAX 取代 DISTINCT。
  const [mskuRows] = await db.execute(
    `SELECT msku_query, MAX(capture_batch) AS latest_batch
     FROM raw_lingxing_settlement_order
     GROUP BY msku_query
     ORDER BY latest_batch DESC
     LIMIT 10`,
  );
  const sampleMskus = (mskuRows as Array<{ msku_query: string }>).map((r) => r.msku_query).filter(Boolean);
  console.log(`raw_lingxing_settlement_order 查到真实 msku 样本 ${sampleMskus.length} 个：${sampleMskus.join(", ") || "(空，说明该表也没数据，可能是全新环境或表名/口径已变)"}`);

  // 3) 诊断：宽日期窗口（T+2结算延迟，60天）下依次尝试几种参数组合，找出第一个非空的
  const diagEnd = shanghaiDate(-2);
  const diagStart = shanghaiDate(-2 - 60 + 1);
  console.log(`\n=== 诊断：宽窗口(结算日期) ${diagStart}~${diagEnd}，依次尝试参数组合 ===`);

  type Variant = { label: string; params: Record<string, unknown> };
  const variants: Variant[] = [
    {
      label: "裸查(仅platformCodeS+日期)",
      params: { offset: 0, length: 50, platformCodeS: [WALMART_PLATFORM_CODE], startDate: diagStart, endDate: diagEnd },
    },
    {
      label: "+currencyCode=USD",
      params: { offset: 0, length: 50, platformCodeS: [WALMART_PLATFORM_CODE], currencyCode: "USD", startDate: diagStart, endDate: diagEnd },
    },
  ];
  if (storeIds.length > 0) {
    variants.push({
      label: "+sids(真实店铺范围)",
      params: { offset: 0, length: 50, platformCodeS: [WALMART_PLATFORM_CODE], sids: storeIds.join(","), startDate: diagStart, endDate: diagEnd },
    });
    variants.push({
      label: "+sids+currencyCode=USD",
      params: { offset: 0, length: 50, platformCodeS: [WALMART_PLATFORM_CODE], sids: storeIds.join(","), currencyCode: "USD", startDate: diagStart, endDate: diagEnd },
    });
  }
  for (const msku of sampleMskus.slice(0, 3)) {
    variants.push({
      label: `按真实msku精确查询(searchField=msku,value=${msku})`,
      params: {
        offset: 0,
        length: 50,
        platformCodeS: [WALMART_PLATFORM_CODE],
        ...(storeIds.length ? { sids: storeIds.join(",") } : {}),
        searchField: "msku",
        searchValue: msku,
        startDate: diagStart,
        endDate: diagEnd,
      },
    });
  }

  let winningParams: Record<string, unknown> | null = null;
  for (const v of variants) {
    let list: SettlementMskuRow[] = [];
    let errMsg = "";
    try {
      list = await callSettlement(client, v.params);
    } catch (err) {
      errMsg = err instanceof Error ? err.message : String(err);
    }
    console.log(`变体[${v.label}] → 返回 ${list.length} 条${errMsg ? `｜报错: ${errMsg}` : ""}`);
    if (list.length > 0 && !winningParams) {
      winningParams = { ...v.params };
      delete winningParams.offset;
      delete winningParams.length;
      delete winningParams.startDate;
      delete winningParams.endDate;
      delete winningParams.searchField;
      delete winningParams.searchValue;
      console.log(`  → 命中！样例记录: ${JSON.stringify(list[0]).slice(0, 500)}`);
    }
    await sleep(300);
  }

  if (!winningParams) {
    console.log(
      "\n所有参数组合在近60天宽窗口下都是0条。说明不是参数问题，而是这个领星账号在" +
        "/basicOpen/multiplatform/profit/report/msku 这个接口上确实没有可查询到的结算数据" +
        "（可能：该接口权限未开通给当前 access_token / 该账号走的是另一套账单口径 / 需要联系领星侧确认）。" +
        "后面的窗口A/B正式对比会照样跑，但预期也会是0条——如果真是0条，不必再等对比结果，" +
        "直接把这段诊断输出反馈回来即可，不需要跑完整个脚本。",
    );
  } else {
    console.log(`\n诊断命中的参数组合（后续窗口A/B对比将复用）：${JSON.stringify(winningParams)}`);
  }

  // 4) 正式对比：用诊断命中的参数组合（若诊断全失败则退回裸查，如实展示0条），拉两个不重叠窗口
  const lag = 2;
  const bEnd = shanghaiDate(-lag);
  const bStart = shanghaiDate(-lag - windowDays + 1);
  const aEnd = shanghaiDate(-lag - windowDays);
  const aStart = shanghaiDate(-lag - windowDays * 2 + 1);

  const baseParams = winningParams ?? { platformCodeS: [WALMART_PLATFORM_CODE] };

  console.log(`\n探针2正式对比 | 窗口A(结算日期) ${aStart}~${aEnd} | 窗口B(结算日期) ${bStart}~${bEnd} | limit=${limit}`);

  async function fetchWindow(startDate: string, endDate: string): Promise<SettlementMskuRow[]> {
    const rows: SettlementMskuRow[] = [];
    let offset = 0;
    const length = 200;
    for (;;) {
      const list = await callSettlement(client, { ...baseParams, offset, length, startDate, endDate });
      rows.push(...list);
      if (list.length < length || rows.length >= limit) break;
      offset += length;
      await sleep(300);
    }
    return rows.slice(0, limit);
  }

  console.log("\n=== 拉取窗口A ===");
  const rowsA = await fetchWindow(aStart, aEnd);
  console.log(`窗口A返回 ${rowsA.length} 条 msku 记录`);

  console.log("\n=== 拉取窗口B ===");
  const rowsB = await fetchWindow(bStart, bEnd);
  console.log(`窗口B返回 ${rowsB.length} 条 msku 记录`);

  const byMskuA = new Map<string, SettlementMskuRow>();
  for (const r of rowsA) if (r.msku) byMskuA.set(String(r.msku), r);
  const byMskuB = new Map<string, SettlementMskuRow>();
  for (const r of rowsB) if (r.msku) byMskuB.set(String(r.msku), r);

  const mskuSet = new Set<string>([...byMskuA.keys(), ...byMskuB.keys()]);
  console.log(`\n合并去重后共 ${mskuSet.size} 个 msku`);

  // 5) 查询 dim_product_cost_config 里的配置均价（固定值）用于横向比对
  const mskuList = [...mskuSet];
  const configByMsku = new Map<string, { purchase_cost: number | null; first_mile_shipping_cost: number | null }>();
  if (mskuList.length > 0) {
    const placeholders = mskuList.map(() => "?").join(",");
    const [rows] = await db.execute(
      `SELECT msku, purchase_cost, first_mile_shipping_cost, effective_date, updated_at
       FROM dim_product_cost_config
       WHERE platform = 'walmart'
         AND status = 'active'
         AND source_system = 'lingxing_api'
         AND msku IN (${placeholders})
       ORDER BY effective_date DESC, updated_at DESC`,
      mskuList,
    );
    for (const r of rows as Array<{
      msku: string;
      purchase_cost: string | number | null;
      first_mile_shipping_cost: string | number | null;
    }>) {
      if (!configByMsku.has(r.msku)) {
        configByMsku.set(r.msku, {
          purchase_cost: r.purchase_cost === null ? null : Number(r.purchase_cost),
          first_mile_shipping_cost: r.first_mile_shipping_cost === null ? null : Number(r.first_mile_shipping_cost),
        });
      }
    }
  }
  await db.end();
  console.log(`dim_product_cost_config 命中配置成本的 msku 数：${configByMsku.size}`);

  console.log("\n=== 逐个 msku 对比（验证①横向 vs 配置均价，验证②纵向窗口A/B是否随时间变化） ===");
  console.log(
    [
      "msku", "A_销量", "A_采购成本", "A_隐含单位采购成本",
      "B_销量", "B_采购成本", "B_隐含单位采购成本",
      "配置purchase_cost",
      "A_头程成本", "A_隐含单位头程", "B_头程成本", "B_隐含单位头程", "配置first_mile_cost",
      "初步判断",
    ].join("\t"),
  );

  let matchConfigCount = 0;
  let diffFromConfigCount = 0;
  let stableAcrossWindowCount = 0;
  let varyAcrossWindowCount = 0;
  let noDataCount = 0;

  for (const msku of mskuList) {
    const a = byMskuA.get(msku);
    const b = byMskuB.get(msku);
    const cfg2 = configByMsku.get(msku);

    const aSalesNum = a?.salesNum ?? 0;
    const bSalesNum = b?.salesNum ?? 0;
    const aUnitPurchase = a && aSalesNum > 0 ? (a.purchaseAmount ?? 0) / aSalesNum : null;
    const bUnitPurchase = b && bSalesNum > 0 ? (b.purchaseAmount ?? 0) / bSalesNum : null;
    const aUnitTransport = a && aSalesNum > 0 ? (a.transportationAmount ?? 0) / aSalesNum : null;
    const bUnitTransport = b && bSalesNum > 0 ? (b.transportationAmount ?? 0) / bSalesNum : null;

    let verdict = "数据不足";
    if (aUnitPurchase === null && bUnitPurchase === null) {
      noDataCount += 1;
    } else {
      const cfgPurchase = cfg2?.purchase_cost ?? null;
      const closeToConfig = (v: number | null) =>
        v !== null && cfgPurchase !== null && Math.abs(v - cfgPurchase) < 0.01 * Math.max(1, cfgPurchase);
      const configMatch = closeToConfig(aUnitPurchase) || closeToConfig(bUnitPurchase);
      const bothPresent = aUnitPurchase !== null && bUnitPurchase !== null;
      const windowStable = bothPresent && Math.abs((aUnitPurchase as number) - (bUnitPurchase as number)) < 0.01 * Math.max(1, aUnitPurchase as number);

      if (configMatch) {
        matchConfigCount += 1;
        verdict = "≈配置均价(疑似固定值模式)";
      } else if (cfgPurchase !== null) {
        diffFromConfigCount += 1;
        verdict = "≠配置均价(疑似真实成本)";
      }
      if (bothPresent) {
        if (windowStable) {
          stableAcrossWindowCount += 1;
        } else {
          varyAcrossWindowCount += 1;
          if (verdict === "数据不足") verdict = "窗口间波动(疑似真实成本)";
        }
      }
    }

    console.log(
      [
        msku, aSalesNum, a?.purchaseAmount ?? "", aUnitPurchase !== null ? aUnitPurchase.toFixed(4) : "",
        bSalesNum, b?.purchaseAmount ?? "", bUnitPurchase !== null ? bUnitPurchase.toFixed(4) : "",
        cfg2?.purchase_cost ?? "",
        a?.transportationAmount ?? "", aUnitTransport !== null ? aUnitTransport.toFixed(4) : "",
        b?.transportationAmount ?? "", bUnitTransport !== null ? bUnitTransport.toFixed(4) : "",
        cfg2?.first_mile_shipping_cost ?? "",
        verdict,
      ].join("\t"),
    );
  }

  console.log("\n=== 汇总 ===");
  console.log(`msku 总数：${mskuList.length}`);
  console.log(`隐含单位采购成本 ≈ dim_product_cost_config 配置均价：${matchConfigCount}`);
  console.log(`隐含单位采购成本 ≠ 配置均价：${diffFromConfigCount}`);
  console.log(`窗口A/B 隐含单位采购成本几乎不变：${stableAcrossWindowCount}`);
  console.log(`窗口A/B 隐含单位采购成本有变化：${varyAcrossWindowCount}`);
  console.log(`两个窗口都没有销量数据的 msku：${noDataCount}`);
  console.log(
    "\n结论提示：如果「≈配置均价」和「几乎不变」占绝大多数 → 生产账号大概率是固定值模式，" +
      "结算利润接口的成本字段不能直接当真实现金成本用，需要走探针1摸清楚的采购单+发货单真实成本链路。\n" +
      "如果「≠配置均价」和「有变化」占绝大多数 → 大概率是计价方法模式，结算利润接口的成本字段本身就是真实成本，" +
      "可以大幅简化架构，直接复用。",
  );
}

main().catch((err) => {
  console.error("探针2执行失败：", err);
  process.exit(1);
});
