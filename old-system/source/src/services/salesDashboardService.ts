/**
 * salesDashboardService.ts
 *
 * 产品负责人经营看板（销售驾驶舱）聚合服务 —— 只读，不写任何表。
 *
 * 数据来源（全部现有表，无结构变更）：
 *   fact_sales_daily / fact_ads_product_daily / fact_inventory_daily
 *   dim_product / dim_product_owner / dim_product_cost_config / fact_profit_daily(仅 platform_fee 参考)
 *
 * 口径（详见 docs/销售驾驶舱_v1_口径决议补充.md）：
 *   - 销售额 = sales_amount，不扣退款；refund_amount 单独展示
 *   - 负责人：dim_product_owner(status=active, 按 platform+item_id) → 兜底 dim_product.owner → 未分配
 *   - 采购/头程成本：仅 source_system='lingxing_api'，每字段分别取非空最新 effective_date，不回退飞书
 *   - WFS配送费：dim_product_cost_config.delivery_fee（feishu_item_owner 来源），单独取
 *   - 成本匹配键：store_id+item_id+msku → 回退 item_id+msku，禁止只按 item_id
 *   - 广告：item 级聚合(ad_spend/total_sales/orders)，不分摊到 msku 行
 *   - 毛利(负责人/公司级) = 销售额 − 采购×qty/汇率 − 头程×qty/汇率 − WFS费×qty − 佣金 − 广告费
 *     msku 明细行毛利不含广告费（gross_profit_ex_ad）
 *   - 佣金：沿用现有生产规则（店铺佣金率），platform_fee 仅作参考字段返回
 *   - 悦斯CS 写死成本规则与现有 lingxingDailyMetricsService 保持一致
 *   - 库存：取 ≤date_to 最新 snapshot_date 快照，不跨天求和
 *   - 库存天数 = available_stock / 近N天日均销量，N = min(60, 实际有数据天数)
 *   - 异常范围：筛选期内有销售或有广告花费的商品；null=未配置，0=配置为0，均算异常但区分显示
 */

import * as mysql from "mysql2/promise";

// ── 可配置常量（环境变量优先，默认值与现有 lingxingDailyMetricsService 一致） ──

const EXCHANGE_RATE = Number(process.env.LX_EXCHANGE_RATE ?? 6.6);
const DEFAULT_COMMISSION_RATE = Number(process.env.LX_COMMISSION_RATE_DEFAULT ?? 0.12);
const SPECIAL_COMMISSION_RATE = Number(process.env.LX_COMMISSION_RATE_SPECIAL ?? 0.15);

const YUESI_CS_WFS_FEE = 4;
const YUESI_CS_PURCHASE_COST = 200;
const YUESI_CS_FIRST_MILE = 1;

function getCommissionRate(storeName: string): number {
  if (storeName.includes("CN2501-掌上便捷") || storeName.includes("CN2502-悦斯电子")) {
    return SPECIAL_COMMISSION_RATE;
  }
  return DEFAULT_COMMISSION_RATE;
}

function isYuesiCs(storeName: string, msku: string): boolean {
  return storeName.includes("CN2502-悦斯电子") && msku.toUpperCase().startsWith("CS");
}

// ── 异常类型 ──────────────────────────────────────────────────────────────────

export const EXCEPTION_LABELS: Record<string, string> = {
  sales_no_sku: "有销售但SKU为空",
  ad_no_sku: "有广告花费但SKU为空",
  missing_purchase_cost: "缺采购成本",
  missing_first_mile_cost: "缺头程成本",
  missing_delivery_fee: "缺WFS配送费",
  ad_no_sales: "广告花费>0但销售额=0",
};

const UNASSIGNED = "未分配";

// ── 类型 ──────────────────────────────────────────────────────────────────────

export interface DashboardParams {
  date_from?: string;
  date_to?: string;
  store_id?: string;
  owner?: string;          // 负责人名，或 "未分配"
  keyword?: string;        // item_id / msku / sku / 产品名 / 负责人
  exception_type?: string; // 仅 owner-products 下钻用
}

interface ProductRow {
  store_id: string;
  store_name: string;
  item_id: string;
  msku: string;
  sku: string;
  product_name: string;
  owner: string;
  owner_source: "owner_table" | "product_table" | "";
  sales_qty: number;
  order_count: number;
  sales_amount: number;
  refund_amount: number;
  delivery_fee: number | null;
  purchase_cost: number | null;
  first_mile_shipping_cost: number | null;
  cost_source: "lingxing_api" | "yuesi_cs_fixed" | "";
  commission_rate: number;
  commission: number;
  platform_fee_ref: number | null;
  gross_profit_ex_ad: number;   // 明细行毛利（不含广告费，广告不分摊）
  available_stock: number;
  wfs_available_stock: number;
  stock_days: number | null;
  exceptions: string[];
}

interface ItemAdRow {
  store_id: string;
  store_name: string;
  item_id: string;
  owner: string;
  owner_source: string;
  sku_known: string;         // 该 item 下已知的任一非空 sku（用于 ad_no_sku 判断展示）
  ad_spend: number;
  ad_sales: number;          // fact_ads_product_daily.total_sales
  ad_orders: number;
  item_sales_amount: number; // 该 item 全部 msku 销售额（TACOS 用）
  acos: number | null;
  tacos: number | null;
  exceptions: string[];
}

export interface OwnerRankingRow {
  owner: string;
  product_total: number;
  product_with_sales: number;
  sales_amount: number;
  order_count: number;
  refund_amount: number;
  ad_spend: number;
  ad_sales: number;
  acos: number | null;
  tacos: number | null;
  gross_profit: number;
  gross_margin: number | null;
  wfs_stock: number;
  stock_days: number | null;
  exception_count: number;
}

export interface ExceptionSummaryRow {
  owner: string;
  code: string;
  label: string;
  product_count: number;
  null_count: number;   // 未配置
  zero_count: number;   // 配置为0
  affected_sales: number;
  affected_ad_spend: number;
}

// ── DB ────────────────────────────────────────────────────────────────────────

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
}

type Row = mysql.RowDataPacket;

// ── 核心数据装配 ──────────────────────────────────────────────────────────────

interface CoreData {
  dateFrom: string;
  dateTo: string;
  latestSalesDate: string | null;
  snapshotDate: string | null;
  avgWindowDays: number;
  platformFeeAvailable: boolean;
  productRows: ProductRow[];   // msku 级（有销售的行）
  itemAdRows: ItemAdRow[];     // item 级广告（含无销售纯广告 item）
  invRows: { store_id: string; item_id: string; msku: string; available: number; wfs: number }[];
  avg60: Map<string, number>;  // store|item|msku → 日均销量
  ownerOf: (itemId: string) => { owner: string; source: "owner_table" | "product_table" | "" };
  ownerProductTotal: Map<string, number>; // 负责人 → 全量 active 商品数（item 去重）
}

const keyFull = (s: string, i: string, m: string) => `${s}|${i}|${m}`;
const keyIM = (i: string, m: string) => `${i}|${m}`;

export async function loadCoreData(params: DashboardParams): Promise<CoreData> {
  const db = await getDb();
  try {
    // 0) 最新有数据日期（默认日期用，不默认今天/昨天）
    const [latestRows] = await db.query<Row[]>(
      "SELECT DATE_FORMAT(MAX(stat_date), '%Y-%m-%d') AS d FROM fact_sales_daily WHERE platform='walmart'",
    );
    const latestSalesDate: string | null = latestRows[0]?.d ?? null;

    const dateFrom = params.date_from?.trim() || latestSalesDate || "";
    const dateTo = params.date_to?.trim() || latestSalesDate || "";
    if (!dateFrom || !dateTo) {
      return {
        dateFrom, dateTo, latestSalesDate, snapshotDate: null, avgWindowDays: 0,
        platformFeeAvailable: false, productRows: [], itemAdRows: [], invRows: [],
        avg60: new Map(), ownerOf: () => ({ owner: UNASSIGNED, source: "" }), ownerProductTotal: new Map(),
      };
    }

    const storeCond = params.store_id ? " AND f.store_id = ?" : "";
    const storeParam = params.store_id ? [params.store_id] : [];

    // 1) 销售聚合（msku 级）
    const [salesRows] = await db.query<Row[]>(
      `SELECT f.store_id, f.store_name, f.item_id, f.msku,
              MAX(COALESCE(f.sku,'')) AS sku,
              SUM(f.sales_qty) AS sales_qty,
              SUM(f.order_count) AS order_count,
              ROUND(SUM(f.sales_amount),2) AS sales_amount,
              ROUND(SUM(COALESCE(f.refund_amount,0)),2) AS refund_amount
       FROM fact_sales_daily f
       WHERE f.platform='walmart' AND f.stat_date BETWEEN ? AND ?${storeCond}
       GROUP BY f.store_id, f.store_name, f.item_id, f.msku`,
      [dateFrom, dateTo, ...storeParam],
    );

    // 2) 广告聚合（item 级；广告表无 sku、msku 大量为空，按口径不分摊）
    const [adsRows] = await db.query<Row[]>(
      `SELECT f.store_id, f.store_name, f.item_id,
              ROUND(SUM(f.ad_spend),2) AS ad_spend,
              ROUND(SUM(COALESCE(f.total_sales,0)),2) AS ad_sales,
              SUM(COALESCE(f.orders,0)) AS ad_orders
       FROM fact_ads_product_daily f
       WHERE f.platform='walmart' AND f.stat_date BETWEEN ? AND ?${storeCond}
       GROUP BY f.store_id, f.store_name, f.item_id`,
      [dateFrom, dateTo, ...storeParam],
    );

    // 3) 库存快照：取 ≤ date_to 的最新 snapshot_date（不跨天求和）
    const [snapRows] = await db.query<Row[]>(
      `SELECT DATE_FORMAT(MAX(snapshot_date), '%Y-%m-%d') AS d
       FROM fact_inventory_daily WHERE platform='walmart' AND snapshot_date <= ?`,
      [dateTo],
    );
    const snapshotDate: string | null = snapRows[0]?.d ?? null;
    let invRows: CoreData["invRows"] = [];
    if (snapshotDate) {
      const [inv] = await db.query<Row[]>(
        `SELECT f.store_id, f.item_id, f.msku,
                COALESCE(f.available_stock,0) AS available,
                COALESCE(f.wfs_available_stock,0) AS wfs
         FROM fact_inventory_daily f
         WHERE f.platform='walmart' AND f.snapshot_date = ?${storeCond}`,
        [snapshotDate, ...storeParam],
      );
      invRows = (inv as Row[]).map((r) => ({
        store_id: String(r.store_id), item_id: String(r.item_id), msku: String(r.msku ?? ""),
        available: Number(r.available), wfs: Number(r.wfs),
      }));
    }

    // 4) dim_product：产品名/SKU 兜底/负责人兜底/全量商品数
    const [dimRows] = await db.query<Row[]>(
      `SELECT store_id, item_id, msku, COALESCE(sku,'') AS sku,
              COALESCE(product_name,'') AS product_name,
              COALESCE(owner,'') AS owner, COALESCE(status,'') AS status
       FROM dim_product WHERE platform='walmart'`,
    );

    // 5) dim_product_owner：active，按 item_id，取最新 effective_date
    const [ownerRows] = await db.query<Row[]>(
      `SELECT item_id, owner_name
       FROM dim_product_owner
       WHERE platform='walmart' AND status='active'
       ORDER BY effective_date DESC, id DESC`,
    );

    // 6) 成本：采购/头程仅 lingxing_api；每字段分别取非空最新（禁止单一 MAX(effective_date) 同取三项）
    const [lxCostRows] = await db.query<Row[]>(
      `SELECT store_id, item_id, msku, purchase_cost, first_mile_shipping_cost
       FROM dim_product_cost_config
       WHERE platform='walmart' AND status='active' AND source_system='lingxing_api'
       ORDER BY effective_date DESC, id DESC`,
    );
    // 7) WFS 配送费：单独取（feishu_item_owner 来源），非空最新
    const [dfRows] = await db.query<Row[]>(
      `SELECT store_id, item_id, msku, delivery_fee
       FROM dim_product_cost_config
       WHERE platform='walmart' AND status='active' AND delivery_fee IS NOT NULL
       ORDER BY effective_date DESC, id DESC`,
    );

    // 8) 近60天日均销量窗口
    const [minRows] = await db.query<Row[]>(
      "SELECT DATE_FORMAT(MIN(stat_date), '%Y-%m-%d') AS d FROM fact_sales_daily WHERE platform='walmart'",
    );
    const minDate: string | null = minRows[0]?.d ?? null;
    let avgWindowDays = 0;
    if (minDate) {
      const spanDays = Math.floor((Date.parse(dateTo) - Date.parse(minDate)) / 86400000) + 1;
      avgWindowDays = Math.max(1, Math.min(60, spanDays));
    }
    const windowFrom = new Date(Date.parse(dateTo) - (avgWindowDays - 1) * 86400000)
      .toISOString().slice(0, 10);
    const [qty60Rows] = await db.query<Row[]>(
      `SELECT f.store_id, f.item_id, f.msku, SUM(f.sales_qty) AS qty
       FROM fact_sales_daily f
       WHERE f.platform='walmart' AND f.stat_date BETWEEN ? AND ?${storeCond}
       GROUP BY f.store_id, f.item_id, f.msku`,
      [windowFrom, dateTo, ...storeParam],
    );

    // 9) platform_fee 参考（fact_profit_daily 字段偏旧，仅参考不做主口径）
    // fact_profit_daily 字段偏旧，仅取 platform_fee 参考；表异常时降级为空，不影响主口径
    let pfRows: Row[] = [];
    try {
      const [pf] = await db.query<Row[]>(
        `SELECT f.store_id, f.item_id, f.msku, ROUND(SUM(COALESCE(f.platform_fee,0)),2) AS pf
         FROM fact_profit_daily f
         WHERE f.platform='walmart' AND f.stat_date BETWEEN ? AND ?${storeCond}
         GROUP BY f.store_id, f.item_id, f.msku`,
        [dateFrom, dateTo, ...storeParam],
      );
      pfRows = pf as Row[];
    } catch { /* platform_fee 参考数据不可用时忽略 */ }

    // ── 构建映射 ──────────────────────────────────────────────────────────────

    // 负责人：owner_table 优先（首见即最新 effective_date），兜底 dim_product.owner
    const ownerTableMap = new Map<string, string>();
    for (const r of ownerRows as Row[]) {
      const id = String(r.item_id);
      if (!ownerTableMap.has(id) && String(r.owner_name ?? "").trim()) {
        ownerTableMap.set(id, String(r.owner_name).trim());
      }
    }
    const dimOwnerMap = new Map<string, string>();
    const dimByFull = new Map<string, { sku: string; product_name: string }>();
    const dimSkuByItem = new Map<string, string>();
    const dimActiveItemsByOwnerKey = new Map<string, string>(); // item_id → 已解析负责人（全量商品数用）
    for (const r of dimRows as Row[]) {
      const id = String(r.item_id);
      const o = String(r.owner ?? "").trim();
      if (o && !dimOwnerMap.has(id)) dimOwnerMap.set(id, o);
      dimByFull.set(keyFull(String(r.store_id), id, String(r.msku ?? "")), {
        sku: String(r.sku ?? ""), product_name: String(r.product_name ?? ""),
      });
      if (String(r.sku ?? "").trim() && !dimSkuByItem.has(id)) dimSkuByItem.set(id, String(r.sku).trim());
    }
    const ownerOf = (itemId: string): { owner: string; source: "owner_table" | "product_table" | "" } => {
      const a = ownerTableMap.get(itemId);
      if (a) return { owner: a, source: "owner_table" };
      const b = dimOwnerMap.get(itemId);
      if (b) return { owner: b, source: "product_table" };
      return { owner: UNASSIGNED, source: "" };
    };

    // 全量 active 商品数（item 去重）
    for (const r of dimRows as Row[]) {
      const st = String(r.status ?? "").toLowerCase();
      if (st && st !== "active") continue;
      const id = String(r.item_id);
      if (!dimActiveItemsByOwnerKey.has(id)) dimActiveItemsByOwnerKey.set(id, ownerOf(id).owner);
    }
    const ownerProductTotal = new Map<string, number>();
    for (const [, o] of dimActiveItemsByOwnerKey) {
      ownerProductTotal.set(o, (ownerProductTotal.get(o) ?? 0) + 1);
    }

    // 成本映射：首见即最新；记录 0 值（0=配置为0，也算异常但有记录）
    const mkCostMaps = () => ({ full: new Map<string, number>(), im: new Map<string, number>() });
    const purchase = mkCostMaps(); const firstMile = mkCostMaps(); const delivery = mkCostMaps();
    const setCost = (maps: { full: Map<string, number>; im: Map<string, number> }, r: Row, v: unknown) => {
      if (v === null || v === undefined) return;
      const fk = keyFull(String(r.store_id ?? ""), String(r.item_id), String(r.msku ?? ""));
      const ik = keyIM(String(r.item_id), String(r.msku ?? ""));
      if (!maps.full.has(fk)) maps.full.set(fk, Number(v));
      if (!maps.im.has(ik)) maps.im.set(ik, Number(v));
    };
    for (const r of lxCostRows as Row[]) {
      setCost(purchase, r, r.purchase_cost);
      setCost(firstMile, r, r.first_mile_shipping_cost);
    }
    for (const r of dfRows as Row[]) setCost(delivery, r, r.delivery_fee);
    const lookupCost = (
      maps: { full: Map<string, number>; im: Map<string, number> },
      storeId: string, itemId: string, msku: string,
    ): number | null => {
      const f = maps.full.get(keyFull(storeId, itemId, msku));
      if (f !== undefined) return f;
      const i = maps.im.get(keyIM(itemId, msku));
      if (i !== undefined) return i;
      return null; // 未配置（禁止只按 item_id 匹配）
    };

    // 日均销量
    const avg60 = new Map<string, number>();
    for (const r of qty60Rows as Row[]) {
      avg60.set(
        keyFull(String(r.store_id), String(r.item_id), String(r.msku ?? "")),
        avgWindowDays > 0 ? Number(r.qty) / avgWindowDays : 0,
      );
    }

    // platform_fee 参考
    const pfMap = new Map<string, number>();
    for (const r of pfRows) {
      pfMap.set(keyFull(String(r.store_id), String(r.item_id), String(r.msku ?? "")), Number(r.pf));
    }
    const platformFeeAvailable = pfMap.size > 0;

    // 库存映射
    const invByFull = new Map<string, { available: number; wfs: number }>();
    for (const r of invRows) invByFull.set(keyFull(r.store_id, r.item_id, r.msku), { available: r.available, wfs: r.wfs });

    // ── 产品行（msku 级） ─────────────────────────────────────────────────────
    const productRows: ProductRow[] = [];
    const itemSalesAmount = new Map<string, number>(); // store|item → 销售额合计
    const itemHasSku = new Map<string, boolean>();

    for (const r of salesRows as Row[]) {
      const storeId = String(r.store_id); const storeName = String(r.store_name ?? "");
      const itemId = String(r.item_id); const msku = String(r.msku ?? "");
      const dim = dimByFull.get(keyFull(storeId, itemId, msku));
      const sku = (String(r.sku ?? "").trim() || dim?.sku || "").trim();
      const own = ownerOf(itemId);
      const salesAmount = Number(r.sales_amount ?? 0);
      const salesQty = Number(r.sales_qty ?? 0);
      const orderCount = Number(r.order_count ?? 0);

      let pc = lookupCost(purchase, storeId, itemId, msku);
      let fm = lookupCost(firstMile, storeId, itemId, msku);
      let df = lookupCost(delivery, storeId, itemId, msku);
      let costSource: ProductRow["cost_source"] = pc !== null || fm !== null ? "lingxing_api" : "";
      if (isYuesiCs(storeName, msku)) {
        pc = YUESI_CS_PURCHASE_COST; fm = YUESI_CS_FIRST_MILE; df = YUESI_CS_WFS_FEE;
        costSource = "yuesi_cs_fixed";
      }

      const rate = getCommissionRate(storeName);
      const commission = salesAmount * rate;
      const grossExAd =
        salesAmount -
        commission -
        (df ?? 0) * salesQty -
        (((pc ?? 0) + (fm ?? 0)) * salesQty) / EXCHANGE_RATE;

      const inv = invByFull.get(keyFull(storeId, itemId, msku));
      const avg = avg60.get(keyFull(storeId, itemId, msku)) ?? 0;
      const stockDays = inv && avg > 0 ? Math.round((inv.available / avg) * 10) / 10 : null;

      const exceptions: string[] = [];
      if ((salesAmount > 0 || orderCount > 0) && !sku) exceptions.push("sales_no_sku");
      if (pc === null || pc === 0) exceptions.push("missing_purchase_cost");
      if (fm === null || fm === 0) exceptions.push("missing_first_mile_cost");
      if (df === null || df === 0) exceptions.push("missing_delivery_fee");

      productRows.push({
        store_id: storeId, store_name: storeName, item_id: itemId, msku, sku,
        product_name: dim?.product_name ?? "",
        owner: own.owner, owner_source: own.source,
        sales_qty: salesQty, order_count: orderCount,
        sales_amount: salesAmount, refund_amount: Number(r.refund_amount ?? 0),
        delivery_fee: df, purchase_cost: pc, first_mile_shipping_cost: fm,
        cost_source: costSource,
        commission_rate: rate,
        commission: Math.round(commission * 100) / 100,
        platform_fee_ref: pfMap.get(keyFull(storeId, itemId, msku)) ?? null,
        gross_profit_ex_ad: Math.round(grossExAd * 100) / 100,
        available_stock: inv?.available ?? 0,
        wfs_available_stock: inv?.wfs ?? 0,
        stock_days: stockDays,
        exceptions,
      });

      const ik = `${storeId}|${itemId}`;
      itemSalesAmount.set(ik, (itemSalesAmount.get(ik) ?? 0) + salesAmount);
      if (sku) itemHasSku.set(ik, true);
    }

    // ── item 级广告行（含纯广告无销售 item） ──────────────────────────────────
    const itemAdRows: ItemAdRow[] = [];
    for (const r of adsRows as Row[]) {
      const storeId = String(r.store_id); const itemId = String(r.item_id);
      const ik = `${storeId}|${itemId}`;
      const adSpend = Number(r.ad_spend ?? 0);
      const adSales = Number(r.ad_sales ?? 0);
      const salesAmt = itemSalesAmount.get(ik) ?? 0;
      const own = ownerOf(itemId);
      const skuKnown = itemHasSku.get(ik) ? "" : (dimSkuByItem.get(itemId) ?? "");
      const hasSku = Boolean(itemHasSku.get(ik) || dimSkuByItem.get(itemId));

      const exceptions: string[] = [];
      if (adSpend > 0 && !hasSku) exceptions.push("ad_no_sku");
      if (adSpend > 0 && salesAmt === 0) exceptions.push("ad_no_sales");

      itemAdRows.push({
        store_id: storeId, store_name: String(r.store_name ?? ""), item_id: itemId,
        owner: own.owner, owner_source: own.source,
        sku_known: skuKnown,
        ad_spend: adSpend, ad_sales: adSales, ad_orders: Number(r.ad_orders ?? 0),
        item_sales_amount: Math.round(salesAmt * 100) / 100,
        acos: adSales > 0 ? Math.round((adSpend / adSales) * 10000) / 10000 : null,
        tacos: salesAmt > 0 ? Math.round((adSpend / salesAmt) * 10000) / 10000 : null,
        exceptions,
      });
    }

    return {
      dateFrom, dateTo, latestSalesDate, snapshotDate, avgWindowDays,
      platformFeeAvailable, productRows, itemAdRows, invRows, avg60, ownerOf, ownerProductTotal,
    };
  } finally {
    await db.end();
  }
}

// ── 筛选 ──────────────────────────────────────────────────────────────────────

function kwMatch(kw: string, ...fields: string[]): boolean {
  const k = kw.toLowerCase();
  return fields.some((f) => f && f.toLowerCase().includes(k));
}

function applyFilters(core: CoreData, params: DashboardParams): {
  productRows: ProductRow[]; itemAdRows: ItemAdRow[];
  invRows: CoreData["invRows"];
} {
  let { productRows, itemAdRows, invRows } = core;
  const owner = params.owner?.trim();
  const kw = params.keyword?.trim();

  if (owner) {
    productRows = productRows.filter((r) => r.owner === owner);
    itemAdRows = itemAdRows.filter((r) => r.owner === owner);
    invRows = invRows.filter((r) => core.ownerOf(r.item_id).owner === owner);
  }
  if (kw) {
    productRows = productRows.filter((r) => kwMatch(kw, r.item_id, r.msku, r.sku, r.product_name, r.owner));
    itemAdRows = itemAdRows.filter((r) => kwMatch(kw, r.item_id, r.sku_known, r.owner));
    invRows = invRows.filter((r) => kwMatch(kw, r.item_id, r.msku));
  }
  return { productRows, itemAdRows, invRows };
}

// ── 看板主接口数据 ────────────────────────────────────────────────────────────

export async function buildDashboard(params: DashboardParams) {
  const core = await loadCoreData(params);
  const { productRows, itemAdRows, invRows } = applyFilters(core, params);

  // 负责人聚合
  interface Acc {
    sales: number; orders: number; qty: number; refund: number;
    grossExAd: number; adSpend: number; adSales: number;
    itemsWithSales: Set<string>; exceptionItems: Set<string>;
    available: number; wfs: number; avgQty: number;
  }
  const accs = new Map<string, Acc>();
  const acc = (o: string): Acc => {
    let a = accs.get(o);
    if (!a) {
      a = { sales: 0, orders: 0, qty: 0, refund: 0, grossExAd: 0, adSpend: 0, adSales: 0,
            itemsWithSales: new Set(), exceptionItems: new Set(), available: 0, wfs: 0, avgQty: 0 };
      accs.set(o, a);
    }
    return a;
  };

  for (const r of productRows) {
    const a = acc(r.owner);
    a.sales += r.sales_amount; a.orders += r.order_count; a.qty += r.sales_qty; a.refund += r.refund_amount;
    a.grossExAd += r.gross_profit_ex_ad;
    if (r.sales_qty > 0) a.itemsWithSales.add(`${r.store_id}|${r.item_id}`);
    if (r.exceptions.length > 0) a.exceptionItems.add(`${r.store_id}|${r.item_id}`);
  }
  for (const r of itemAdRows) {
    const a = acc(r.owner);
    a.adSpend += r.ad_spend; a.adSales += r.ad_sales;
    if (r.exceptions.length > 0) a.exceptionItems.add(`${r.store_id}|${r.item_id}`);
  }
  for (const r of invRows) {
    const o = core.ownerOf(r.item_id).owner;
    if (params.owner && o !== params.owner) continue;
    const a = acc(o);
    a.available += r.available; a.wfs += r.wfs;
    a.avgQty += core.avg60.get(`${r.store_id}|${r.item_id}|${r.msku}`) ?? 0;
  }

  const ownerRanking: OwnerRankingRow[] = [...accs.entries()].map(([owner, a]) => {
    const gross = a.grossExAd - a.adSpend;
    return {
      owner,
      product_total: core.ownerProductTotal.get(owner) ?? 0,
      product_with_sales: a.itemsWithSales.size,
      sales_amount: r2(a.sales), order_count: a.orders, refund_amount: r2(a.refund),
      ad_spend: r2(a.adSpend), ad_sales: r2(a.adSales),
      acos: a.adSales > 0 ? r4(a.adSpend / a.adSales) : null,
      tacos: a.sales > 0 ? r4(a.adSpend / a.sales) : null,
      gross_profit: r2(gross),
      gross_margin: a.sales > 0 ? r4(gross / a.sales) : null,
      wfs_stock: a.wfs,
      stock_days: a.avgQty > 0 ? Math.round((a.available / a.avgQty) * 10) / 10 : null,
      exception_count: a.exceptionItems.size,
    };
  }).sort((x, y) => y.sales_amount - x.sales_amount);

  // 公司卡片 = 负责人排行合计（保证两者一致）
  const sum = (f: (r: OwnerRankingRow) => number) => r2(ownerRanking.reduce((s, r) => s + f(r), 0));
  const totalSales = sum((r) => r.sales_amount);
  const totalAdSpend = sum((r) => r.ad_spend);
  const totalAdSales = sum((r) => r.ad_sales);
  const totalGross = sum((r) => r.gross_profit);
  const wfsItemSet = new Set(invRows.filter((r) => r.wfs > 0).map((r) => `${r.store_id}|${r.item_id}`));
  const exceptionItemTotal = ownerRanking.reduce((s, r) => s + r.exception_count, 0);

  const cards = {
    sales_amount: totalSales,
    order_count: ownerRanking.reduce((s, r) => s + r.order_count, 0),
    gross_profit: totalGross,
    gross_margin: totalSales > 0 ? r4(totalGross / totalSales) : null,
    ad_spend: totalAdSpend,
    ad_sales: totalAdSales,
    acos: totalAdSales > 0 ? r4(totalAdSpend / totalAdSales) : null,
    tacos: totalSales > 0 ? r4(totalAdSpend / totalSales) : null,
    wfs_item_count: wfsItemSet.size,
    exception_item_count: exceptionItemTotal,
  };

  // 异常汇总（负责人 × 类型；null/0 区分）
  const exMap = new Map<string, ExceptionSummaryRow>();
  const exAcc = (owner: string, code: string): ExceptionSummaryRow => {
    const k = `${owner}|${code}`;
    let e = exMap.get(k);
    if (!e) {
      e = { owner, code, label: EXCEPTION_LABELS[code] ?? code,
            product_count: 0, null_count: 0, zero_count: 0, affected_sales: 0, affected_ad_spend: 0 };
      exMap.set(k, e);
    }
    return e;
  };
  for (const r of productRows) {
    for (const code of r.exceptions) {
      const e = exAcc(r.owner, code);
      e.product_count += 1;
      e.affected_sales = r2(e.affected_sales + r.sales_amount);
      if (code === "missing_purchase_cost") (r.purchase_cost === null ? e.null_count++ : e.zero_count++);
      if (code === "missing_first_mile_cost") (r.first_mile_shipping_cost === null ? e.null_count++ : e.zero_count++);
      if (code === "missing_delivery_fee") (r.delivery_fee === null ? e.null_count++ : e.zero_count++);
    }
  }
  for (const r of itemAdRows) {
    for (const code of r.exceptions) {
      const e = exAcc(r.owner, code);
      e.product_count += 1;
      e.affected_ad_spend = r2(e.affected_ad_spend + r.ad_spend);
      e.affected_sales = r2(e.affected_sales + r.item_sales_amount);
    }
  }
  const exceptions = [...exMap.values()].sort(
    (a, b) => a.owner.localeCompare(b.owner) || a.code.localeCompare(b.code),
  );

  return {
    meta: {
      date_from: core.dateFrom,
      date_to: core.dateTo,
      latest_sales_date: core.latestSalesDate,
      inventory_snapshot_date: core.snapshotDate,
      avg_window_days: core.avgWindowDays,
      exchange_rate: EXCHANGE_RATE,
      commission_note: `佣金按店铺规则估算（默认${DEFAULT_COMMISSION_RATE * 100}%，掌上便捷/悦斯电子${SPECIAL_COMMISSION_RATE * 100}%）；platform_fee 仅作参考字段`,
      platform_fee_available: core.platformFeeAvailable,
      stock_note: "库存天数暂按 available_stock / 近N天日均销量计算；在途/已采购库存后续接入后再纳入",
      ad_note: "广告为 ItemID 级数据，不分摊到 MSKU 明细行；明细行毛利未扣广告费，负责人/公司级毛利已扣",
    },
    cards,
    ownerRanking,
    exceptions,
  };
}

// ── 负责人下钻产品明细 ────────────────────────────────────────────────────────

export async function buildOwnerProducts(params: DashboardParams) {
  const core = await loadCoreData(params);
  let { productRows, itemAdRows } = applyFilters(core, params);

  const ex = params.exception_type?.trim();
  if (ex) {
    productRows = productRows.filter((r) => r.exceptions.includes(ex));
    itemAdRows = itemAdRows.filter((r) => r.exceptions.includes(ex));
  }

  productRows = [...productRows].sort((a, b) => b.sales_amount - a.sales_amount);
  itemAdRows = [...itemAdRows].sort((a, b) => b.ad_spend - a.ad_spend);

  return {
    meta: {
      date_from: core.dateFrom, date_to: core.dateTo,
      inventory_snapshot_date: core.snapshotDate,
      avg_window_days: core.avgWindowDays,
      owner: params.owner ?? "",
      exception_type: ex ?? "",
    },
    rows: productRows,
    ad_item_rows: itemAdRows,
  };
}

// ══════════════════════════════════════════════════════════════════════════════
// v2：趋势与环比对比（隔离新增，不改动 v1 代码路径）
// 口径完全复用 v1：对比与排名变化直接调用 buildDashboard 聚合，
// 保证"本期负责人合计 = 公司本期指标"天然成立。
// ══════════════════════════════════════════════════════════════════════════════

export interface TrendsParams extends DashboardParams {
  compare_from?: string;   // 上期起（可选，缺省=紧邻的等长上一周期；"本月"由前端传上月同期）
  compare_to?: string;     // 上期止
}

export interface TrendPoint {
  stat_date: string;
  sales_amount: number;
  order_count: number;
  ad_spend: number;
  ad_sales: number;
  gross_profit: number;
  gross_margin: number | null;
  acos: number | null;
  tacos: number | null;
}

export interface ComparisonMetric {
  key: string;
  label: string;
  ratio: boolean;              // true=比例类（毛利率/ACOS/TACOS），变化按百分点
  current: number | null;
  previous: number | null;
  change: number | null;       // 数值差；比例类为百分点差（0.019 = +1.9pct）
  change_pct: number | null;   // 金额/数量类的变化百分比；比例类为 null
}

export interface OwnerChangeRow {
  owner: string;
  sales_current: number; sales_previous: number; sales_change: number; sales_change_pct: number | null;
  gross_current: number; gross_previous: number; gross_change: number;
  margin_current: number | null; margin_previous: number | null; margin_change: number | null;
  tacos_current: number | null; tacos_previous: number | null; tacos_change: number | null;
  exception_count: number;
}

function addDays(iso: string, days: number): string {
  return new Date(Date.parse(iso) + days * 86400000).toISOString().slice(0, 10);
}

// ── 维度/成本映射（trends 专用，独立加载，不复用 loadCoreData 以免影响 v1） ──────

interface DimCostMaps {
  ownerOf: (itemId: string) => { owner: string; source: string };
  dimByFull: Map<string, { sku: string; product_name: string }>;
  dimSkuByItem: Map<string, string>;
  lookupPurchase: (s: string, i: string, m: string) => number | null;
  lookupFirstMile: (s: string, i: string, m: string) => number | null;
  lookupDelivery: (s: string, i: string, m: string) => number | null;
}

async function loadDimCostMaps(db: mysql.Connection): Promise<DimCostMaps> {
  const [dimRows] = await db.query<Row[]>(
    `SELECT store_id, item_id, msku, COALESCE(sku,'') AS sku,
            COALESCE(product_name,'') AS product_name, COALESCE(owner,'') AS owner
     FROM dim_product WHERE platform='walmart'`,
  );
  const [ownerRows] = await db.query<Row[]>(
    `SELECT item_id, owner_name FROM dim_product_owner
     WHERE platform='walmart' AND status='active'
     ORDER BY effective_date DESC, id DESC`,
  );
  const [lxCostRows] = await db.query<Row[]>(
    `SELECT store_id, item_id, msku, purchase_cost, first_mile_shipping_cost
     FROM dim_product_cost_config
     WHERE platform='walmart' AND status='active' AND source_system='lingxing_api'
     ORDER BY effective_date DESC, id DESC`,
  );
  const [dfRows] = await db.query<Row[]>(
    `SELECT store_id, item_id, msku, delivery_fee
     FROM dim_product_cost_config
     WHERE platform='walmart' AND status='active' AND delivery_fee IS NOT NULL
     ORDER BY effective_date DESC, id DESC`,
  );

  const ownerTableMap = new Map<string, string>();
  for (const r of ownerRows as Row[]) {
    const id = String(r.item_id);
    if (!ownerTableMap.has(id) && String(r.owner_name ?? "").trim()) {
      ownerTableMap.set(id, String(r.owner_name).trim());
    }
  }
  const dimOwnerMap = new Map<string, string>();
  const dimByFull = new Map<string, { sku: string; product_name: string }>();
  const dimSkuByItem = new Map<string, string>();
  for (const r of dimRows as Row[]) {
    const id = String(r.item_id);
    const o = String(r.owner ?? "").trim();
    if (o && !dimOwnerMap.has(id)) dimOwnerMap.set(id, o);
    dimByFull.set(keyFull(String(r.store_id), id, String(r.msku ?? "")), {
      sku: String(r.sku ?? ""), product_name: String(r.product_name ?? ""),
    });
    if (String(r.sku ?? "").trim() && !dimSkuByItem.has(id)) dimSkuByItem.set(id, String(r.sku).trim());
  }
  const ownerOf = (itemId: string) => {
    const a = ownerTableMap.get(itemId);
    if (a) return { owner: a, source: "owner_table" };
    const b = dimOwnerMap.get(itemId);
    if (b) return { owner: b, source: "product_table" };
    return { owner: UNASSIGNED, source: "" };
  };

  const mk = () => ({ full: new Map<string, number>(), im: new Map<string, number>() });
  const purchase = mk(); const firstMile = mk(); const delivery = mk();
  const set = (maps: ReturnType<typeof mk>, r: Row, v: unknown) => {
    if (v === null || v === undefined) return;
    const fk = keyFull(String(r.store_id ?? ""), String(r.item_id), String(r.msku ?? ""));
    const ik = keyIM(String(r.item_id), String(r.msku ?? ""));
    if (!maps.full.has(fk)) maps.full.set(fk, Number(v));
    if (!maps.im.has(ik)) maps.im.set(ik, Number(v));
  };
  for (const r of lxCostRows as Row[]) { set(purchase, r, r.purchase_cost); set(firstMile, r, r.first_mile_shipping_cost); }
  for (const r of dfRows as Row[]) set(delivery, r, r.delivery_fee);
  const look = (maps: ReturnType<typeof mk>) => (s: string, i: string, m: string): number | null => {
    const f = maps.full.get(keyFull(s, i, m));
    if (f !== undefined) return f;
    const im = maps.im.get(keyIM(i, m));
    if (im !== undefined) return im;
    return null;
  };
  return {
    ownerOf, dimByFull, dimSkuByItem,
    lookupPurchase: look(purchase), lookupFirstMile: look(firstMile), lookupDelivery: look(delivery),
  };
}

// ── 按日趋势 ──────────────────────────────────────────────────────────────────

async function loadDailyTrend(
  db: mysql.Connection, maps: DimCostMaps, params: TrendsParams,
  dateFrom: string, dateTo: string,
): Promise<TrendPoint[]> {
  const storeCond = params.store_id ? " AND f.store_id = ?" : "";
  const storeParam = params.store_id ? [params.store_id] : [];

  const [salesDaily] = await db.query<Row[]>(
    `SELECT DATE_FORMAT(f.stat_date,'%Y-%m-%d') AS d, f.store_id, f.store_name, f.item_id, f.msku,
            MAX(COALESCE(f.sku,'')) AS sku,
            SUM(f.sales_qty) AS qty, SUM(f.order_count) AS orders,
            ROUND(SUM(f.sales_amount),2) AS amount
     FROM fact_sales_daily f
     WHERE f.platform='walmart' AND f.stat_date BETWEEN ? AND ?${storeCond}
     GROUP BY d, f.store_id, f.store_name, f.item_id, f.msku`,
    [dateFrom, dateTo, ...storeParam],
  );
  const [adsDaily] = await db.query<Row[]>(
    `SELECT DATE_FORMAT(f.stat_date,'%Y-%m-%d') AS d, f.store_id, f.item_id,
            ROUND(SUM(f.ad_spend),2) AS spend,
            ROUND(SUM(COALESCE(f.total_sales,0)),2) AS ad_sales
     FROM fact_ads_product_daily f
     WHERE f.platform='walmart' AND f.stat_date BETWEEN ? AND ?${storeCond}
     GROUP BY d, f.store_id, f.item_id`,
    [dateFrom, dateTo, ...storeParam],
  );

  const owner = params.owner?.trim();
  const kw = params.keyword?.trim();

  interface DayAcc { sales: number; orders: number; grossExAd: number; spend: number; adSales: number; }
  const byDate = new Map<string, DayAcc>();
  const day = (d: string): DayAcc => {
    let a = byDate.get(d);
    if (!a) { a = { sales: 0, orders: 0, grossExAd: 0, spend: 0, adSales: 0 }; byDate.set(d, a); }
    return a;
  };

  for (const r of salesDaily as Row[]) {
    const storeId = String(r.store_id); const storeName = String(r.store_name ?? "");
    const itemId = String(r.item_id); const msku = String(r.msku ?? "");
    const own = maps.ownerOf(itemId);
    if (owner && own.owner !== owner) continue;
    if (kw) {
      const dim = maps.dimByFull.get(keyFull(storeId, itemId, msku));
      const sku = String(r.sku ?? "").trim() || dim?.sku || "";
      if (!kwMatch(kw, itemId, msku, sku, dim?.product_name ?? "", own.owner)) continue;
    }
    const amount = Number(r.amount ?? 0);
    const qty = Number(r.qty ?? 0);

    let pc = maps.lookupPurchase(storeId, itemId, msku);
    let fm = maps.lookupFirstMile(storeId, itemId, msku);
    let df = maps.lookupDelivery(storeId, itemId, msku);
    if (isYuesiCs(storeName, msku)) { pc = YUESI_CS_PURCHASE_COST; fm = YUESI_CS_FIRST_MILE; df = YUESI_CS_WFS_FEE; }
    const commission = amount * getCommissionRate(storeName);
    const grossExAd = amount - commission - (df ?? 0) * qty - (((pc ?? 0) + (fm ?? 0)) * qty) / EXCHANGE_RATE;

    const a = day(String(r.d));
    a.sales += amount; a.orders += Number(r.orders ?? 0); a.grossExAd += grossExAd;
  }

  for (const r of adsDaily as Row[]) {
    const itemId = String(r.item_id);
    const own = maps.ownerOf(itemId);
    if (owner && own.owner !== owner) continue;
    if (kw && !kwMatch(kw, itemId, maps.dimSkuByItem.get(itemId) ?? "", own.owner)) continue;
    const a = day(String(r.d));
    a.spend += Number(r.spend ?? 0); a.adSales += Number(r.ad_sales ?? 0);
  }

  return [...byDate.entries()].sort((x, y) => x[0].localeCompare(y[0])).map(([d, a]) => {
    const gross = a.grossExAd - a.spend;
    return {
      stat_date: d,
      sales_amount: r2(a.sales), order_count: a.orders,
      ad_spend: r2(a.spend), ad_sales: r2(a.adSales),
      gross_profit: r2(gross),
      gross_margin: a.sales > 0 ? r4(gross / a.sales) : null,
      acos: a.adSales > 0 ? r4(a.spend / a.adSales) : null,
      tacos: a.sales > 0 ? r4(a.spend / a.sales) : null,
    };
  });
}

// ── 环比对比 ──────────────────────────────────────────────────────────────────

const COMPARISON_DEFS: { key: string; label: string; ratio: boolean }[] = [
  { key: "sales_amount", label: "销售额", ratio: false },
  { key: "order_count", label: "订单量", ratio: false },
  { key: "ad_spend", label: "广告花费", ratio: false },
  { key: "ad_sales", label: "广告销售额", ratio: false },
  { key: "gross_profit", label: "毛利额", ratio: false },
  { key: "gross_margin", label: "毛利率", ratio: true },
  { key: "acos", label: "ACOS", ratio: true },
  { key: "tacos", label: "TACOS", ratio: true },
];

function mkComparison(
  cur: Record<string, number | null>, prev: Record<string, number | null>,
): ComparisonMetric[] {
  return COMPARISON_DEFS.map(({ key, label, ratio }) => {
    const c = cur[key] ?? null;
    const p = prev[key] ?? null;
    let change: number | null = null;
    let changePct: number | null = null;
    if (c !== null && p !== null) {
      change = ratio ? r4(c - p) : r2(c - p);
      if (!ratio) changePct = p !== 0 ? r4((c - p) / Math.abs(p)) : null;
    }
    return { key, label, ratio, current: c, previous: p, change, change_pct: changePct };
  });
}

// ── 主入口 ────────────────────────────────────────────────────────────────────

export async function buildTrends(params: TrendsParams) {
  // 1) 日期解析（默认最新有数据日；上期默认紧邻等长周期，可由参数覆盖）
  const db = await getDb();
  let dateFrom = ""; let dateTo = ""; let latest: string | null = null;
  let companyTrend: TrendPoint[] = [];
  let ownerTrend: TrendPoint[] = [];
  let compareFrom = ""; let compareTo = "";
  try {
    const [latestRows] = await db.query<Row[]>(
      "SELECT DATE_FORMAT(MAX(stat_date), '%Y-%m-%d') AS d FROM fact_sales_daily WHERE platform='walmart'",
    );
    latest = latestRows[0]?.d ?? null;
    dateFrom = params.date_from?.trim() || latest || "";
    dateTo = params.date_to?.trim() || latest || "";
    if (!dateFrom || !dateTo) {
      return {
        dateRange: { date_from: dateFrom, date_to: dateTo, compare_from: "", compare_to: "" },
        companyTrend: [], ownerTrend: [], comparison: { metrics: [] }, ownerRankingChanges: [],
      };
    }
    const days = Math.max(1, Math.floor((Date.parse(dateTo) - Date.parse(dateFrom)) / 86400000) + 1);
    compareTo = params.compare_to?.trim() || addDays(dateFrom, -1);
    compareFrom = params.compare_from?.trim() || addDays(compareTo, -(days - 1));

    // 2) 按日趋势（当前范围；owner 参数存在时即为负责人趋势）
    const maps = await loadDimCostMaps(db);
    companyTrend = await loadDailyTrend(db, maps, params, dateFrom, dateTo);
    ownerTrend = params.owner?.trim() ? companyTrend : [];
  } finally {
    await db.end();
  }

  // 3) 本期/上期整体对比 + 负责人排名变化：直接复用 v1 buildDashboard，口径一致
  const base = {
    store_id: params.store_id, owner: params.owner, keyword: params.keyword,
  };
  const cur = await buildDashboard({ ...base, date_from: dateFrom, date_to: dateTo });
  const prev = await buildDashboard({ ...base, date_from: compareFrom, date_to: compareTo });

  const comparison = {
    metrics: mkComparison(
      cur.cards as unknown as Record<string, number | null>,
      prev.cards as unknown as Record<string, number | null>,
    ),
  };

  const prevByOwner = new Map(prev.ownerRanking.map((r) => [r.owner, r]));
  const curByOwner = new Map(cur.ownerRanking.map((r) => [r.owner, r]));
  const allOwners = new Set([...curByOwner.keys(), ...prevByOwner.keys()]);
  const ownerRankingChanges: OwnerChangeRow[] = [...allOwners].map((o) => {
    const c = curByOwner.get(o);
    const p = prevByOwner.get(o);
    const salesC = c?.sales_amount ?? 0; const salesP = p?.sales_amount ?? 0;
    const grossC = c?.gross_profit ?? 0; const grossP = p?.gross_profit ?? 0;
    const marginC = c?.gross_margin ?? null; const marginP = p?.gross_margin ?? null;
    const tacosC = c?.tacos ?? null; const tacosP = p?.tacos ?? null;
    return {
      owner: o,
      sales_current: salesC, sales_previous: salesP,
      sales_change: r2(salesC - salesP),
      sales_change_pct: salesP !== 0 ? r4((salesC - salesP) / Math.abs(salesP)) : null,
      gross_current: grossC, gross_previous: grossP, gross_change: r2(grossC - grossP),
      margin_current: marginC, margin_previous: marginP,
      margin_change: marginC !== null && marginP !== null ? r4(marginC - marginP) : null,
      tacos_current: tacosC, tacos_previous: tacosP,
      tacos_change: tacosC !== null && tacosP !== null ? r4(tacosC - tacosP) : null,
      exception_count: c?.exception_count ?? 0,
    };
  }).sort((a, b) => b.sales_change - a.sales_change);

  return {
    dateRange: {
      date_from: dateFrom, date_to: dateTo,
      compare_from: compareFrom, compare_to: compareTo,
      latest_sales_date: latest,
    },
    companyTrend,
    ownerTrend,
    comparison,
    ownerRankingChanges,
  };
}

// ── 工具 ──────────────────────────────────────────────────────────────────────

function r2(n: number): number { return Math.round(n * 100) / 100; }
function r4(n: number): number { return Math.round(n * 10000) / 10000; }
