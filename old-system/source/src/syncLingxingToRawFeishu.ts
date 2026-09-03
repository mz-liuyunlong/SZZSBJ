/**
 * syncLingxingToRawFeishu.ts
 *
 * 从领星 FACT 表读取数据，计算利润指标，写入 raw_feishu_table
 * 替代飞书数据源，使 #/feishu-raw-sales-data 显示领星实时数据。
 *
 * 写入的 3 个 sheet：
 *   <REDACTED_FEISHU_SHEET_ID>  当日数据       —— 指定日期，每次全量覆盖
 *   <REDACTED_FEISHU_SHEET_ID>  每日销售明细    —— 指定日期追加（同日期先删再写，保留其他日期）
 *   <REDACTED_FEISHU_SHEET_ID>  近期利润与广告  —— 近7天/近5天聚合，每次全量覆盖
 *
 * 下游迁移（脱离飞书 <REDACTED_FEISHU_SHEET_ID>，产品管理 V1.2 之后）：
 * 负责人改读 dim_product.owner，WFS配送费改读 dim_product_cost_config.delivery_fee，
 * 不再 JOIN raw_feishu_table(sheet_id='<REDACTED_FEISHU_SHEET_ID>') 的旧飞书镜像数据。
 *
 * 用法：
 *   npx ts-node src/syncLingxingToRawFeishu.ts [YYYY-MM-DD] [--only=all|detail]
 *   不传日期默认昨天
 *
 * 计算规则（与飞书公式一致）：
 *   汇率       = 6.6（写死）
 *   佣金率     = CN2501/CN2502 → 15%，其余 → 12%
 *   悦斯CS规则 = CN2502 且 MSKU 以 CS 开头 → WFS$4, 采购¥200, 头程¥1（写死）
 *   毛利润     = 销售额 - 广告 - WFS×销量 - 佣金 - (采购+头程)×销量 / 汇率
 *   毛利率     = 毛利润 / 销售额
 *   广告占比   = 广告 / 销售额
 */

import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";

// ── 常量 ──────────────────────────────────────────────────────────────────────

const SPREADSHEET_TOKEN = "<REDACTED_FEISHU_SPREADSHEET_TOKEN>";

const SHEETS = {
  daily:  { id: "<REDACTED_FEISHU_SHEET_ID>", name: "当日数据" },
  detail: { id: "<REDACTED_FEISHU_SHEET_ID>", name: "每日销售明细" },
  recent: { id: "<REDACTED_FEISHU_SHEET_ID>", name: "近期利润与广告" },
} as const;

const EXCHANGE_RATE = 6.6;
const YUESI_CS_WFS_FEE      = 4;    // $
const YUESI_CS_PURCHASE_COST = 200; // ¥
const YUESI_CS_FIRST_MILE    = 1;   // ¥

// ── 工具 ──────────────────────────────────────────────────────────────────────

function makeHash(...parts: string[]): string {
  return crypto.createHash("md5").update(parts.join("|")).digest("hex").slice(0, 64);
}

function yesterday(): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return d.toISOString().slice(0, 10);
}

/** <REDACTED_FEISHU_SHEET_ID> 专用：把日期转成不冲突的 row_index 基数（INT 安全范围）
 *  原理：距 1970-01-01 的天数 × 1000（每日最多 1000 条）
 *  2026-06-23 ≈ 20629 天 → base = 20,629,001（远低于 INT MAX 2,147,483,647）
 */
function dateToRowBase(date: string): number {
  // 2026-08-18 批B-9容量扩位：×1000→×10000（listing增长后单日已超1000行，×1000会溢出到邻日编码区间；
  // 全系统读方/删除方均按 row_json"日期" 工作，本编码仅写方内部防冲突用；INT上限内安全至公元2557年）
  const dayNum = Math.floor(new Date(date + "T00:00:00Z").getTime() / 86400000);
  return dayNum * 10000 + 1;
}

function addDays(date: string, days: number): string {
  const d = new Date(date + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host:     process.env.DB_HOST     ?? "127.0.0.1",
    port:     Number(process.env.DB_PORT ?? 3306),
    user:     process.env.DB_USER     ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME     ?? "walmart_ai_data",
  });
}

// ── 业务规则 ──────────────────────────────────────────────────────────────────

function getCommissionRate(storeName: string): number {
  return (storeName.includes("CN2501") || storeName.includes("CN2502")) ? 0.15 : 0.12;
}

function isYuesiCs(storeName: string, msku: string): boolean {
  return storeName.includes("CN2502") && msku.toUpperCase().startsWith("CS");
}

interface CalcInput {
  store_name:   string;
  msku:         string;
  sales_qty:    number;
  sales_amount: number;
  ad_spend:     number;
  delivery_fee: number;
  purchase_cost: number;
  first_mile:   number;
}

interface CalcResult {
  commission_rate: number;
  wfs_fee:         number;
  purchase_cost:   number;
  first_mile:      number;
  gross_profit:    number;
  gross_margin:    number;
  ad_ratio:        number;
}

function calcMetrics(r: CalcInput): CalcResult {
  const commRate = getCommissionRate(r.store_name);
  let wfsFee       = r.delivery_fee;
  let purchaseCost = r.purchase_cost;
  let firstMile    = r.first_mile;

  if (isYuesiCs(r.store_name, r.msku)) {
    wfsFee       = YUESI_CS_WFS_FEE;
    purchaseCost = YUESI_CS_PURCHASE_COST;
    firstMile    = YUESI_CS_FIRST_MILE;
  }

  const commission = r.sales_amount * commRate;
  const gp =
    r.sales_amount
    - r.ad_spend
    - wfsFee * r.sales_qty
    - commission
    - (purchaseCost + firstMile) * r.sales_qty / EXCHANGE_RATE;

  return {
    commission_rate: commRate,
    wfs_fee:         wfsFee,
    purchase_cost:   purchaseCost,
    first_mile:      firstMile,
    gross_profit:    Math.round(gp * 100) / 100,
    gross_margin:    r.sales_amount > 0 ? Math.round(gp / r.sales_amount * 10000) / 10000 : 0,
    ad_ratio:        r.sales_amount > 0 ? Math.round(r.ad_spend / r.sales_amount * 10000) / 10000 : 0,
  };
}

// 格式化：整数百分比（与飞书一致，如 "15%"）
function pct(n: number): string { return Math.round(n * 100) + "%"; }
// 格式化：保留2位小数
function n2(n: number): string  { return n.toFixed(2); }

function costJoinSql(mskuExpr: string): string {
  return `
  LEFT JOIN (
    SELECT c.store_id,
           c.item_id,
           c.msku,
           MAX(c.purchase_cost) AS purchase_cost,
           MAX(c.first_mile_shipping_cost) AS first_mile_shipping_cost
    FROM dim_product_cost_config c
    WHERE c.platform = 'walmart'
      AND c.status = 'active'
      AND c.source_system = 'lingxing_api'
      AND c.purchase_cost IS NOT NULL
      AND c.first_mile_shipping_cost IS NOT NULL
      AND COALESCE(c.store_id, '') != ''
      AND COALESCE(c.item_id, '') != ''
      AND COALESCE(c.msku, '') != ''
      AND NOT EXISTS (
        SELECT 1
        FROM dim_product_cost_config newer
        WHERE newer.platform = 'walmart'
          AND newer.status = 'active'
          AND newer.source_system = 'lingxing_api'
          AND newer.purchase_cost IS NOT NULL
          AND newer.first_mile_shipping_cost IS NOT NULL
          AND newer.store_id = c.store_id
          AND newer.item_id = c.item_id
          AND newer.msku = c.msku
          AND (
            newer.effective_date > c.effective_date
            OR (newer.effective_date = c.effective_date AND newer.updated_at > c.updated_at)
            OR (newer.effective_date = c.effective_date AND newer.updated_at = c.updated_at AND newer.id > c.id)
          )
      )
    GROUP BY c.store_id, c.item_id, c.msku
  ) dpc_store
    ON dpc_store.store_id = base.store_id
   AND dpc_store.item_id = base.item_id
   AND dpc_store.msku = ${mskuExpr}
  LEFT JOIN (
    SELECT c.item_id,
           c.msku,
           MAX(c.purchase_cost) AS purchase_cost,
           MAX(c.first_mile_shipping_cost) AS first_mile_shipping_cost
    FROM dim_product_cost_config c
    WHERE c.platform = 'walmart'
      AND c.status = 'active'
      AND c.source_system = 'lingxing_api'
      AND c.purchase_cost IS NOT NULL
      AND c.first_mile_shipping_cost IS NOT NULL
      AND COALESCE(c.item_id, '') != ''
      AND COALESCE(c.msku, '') != ''
      AND NOT EXISTS (
        SELECT 1
        FROM dim_product_cost_config newer
        WHERE newer.platform = 'walmart'
          AND newer.status = 'active'
          AND newer.source_system = 'lingxing_api'
          AND newer.purchase_cost IS NOT NULL
          AND newer.first_mile_shipping_cost IS NOT NULL
          AND newer.item_id = c.item_id
          AND newer.msku = c.msku
          AND (
            newer.effective_date > c.effective_date
            OR (newer.effective_date = c.effective_date AND newer.updated_at > c.updated_at)
            OR (newer.effective_date = c.effective_date AND newer.updated_at = c.updated_at AND newer.id > c.id)
          )
      )
    GROUP BY c.item_id, c.msku
  ) dpc_item
    ON dpc_item.item_id = base.item_id
   AND dpc_item.msku = ${mskuExpr}
`;
}

// 下游迁移（脱离飞书 <REDACTED_FEISHU_SHEET_ID>）：WFS配送费改读 dim_product_cost_config.delivery_fee，
// 取"该字段自己的最新非空值"（不按整行 effective_date 决定，避免和 purchase_cost/first_mile 互相干扰），
// 逻辑与产品管理页面 GET /product-management 的读取口径一致。不再读 raw_feishu_table(sheet_id='<REDACTED_FEISHU_SHEET_ID>')。
function deliveryFeeJoinSql(mskuExpr: string): string {
  return `
  LEFT JOIN (
    SELECT c.store_id, c.item_id, c.msku, c.delivery_fee
    FROM dim_product_cost_config c
    WHERE c.platform = 'walmart'
      AND c.status = 'active'
      AND c.delivery_fee IS NOT NULL
      AND COALESCE(c.store_id, '') != ''
      AND COALESCE(c.item_id, '') != ''
      AND COALESCE(c.msku, '') != ''
      AND NOT EXISTS (
        SELECT 1
        FROM dim_product_cost_config newer
        WHERE newer.platform = 'walmart'
          AND newer.status = 'active'
          AND newer.delivery_fee IS NOT NULL
          AND newer.store_id = c.store_id
          AND newer.item_id = c.item_id
          AND newer.msku = c.msku
          AND (
            newer.effective_date > c.effective_date
            OR (newer.effective_date = c.effective_date AND newer.updated_at > c.updated_at)
            OR (newer.effective_date = c.effective_date AND newer.updated_at = c.updated_at AND newer.id > c.id)
          )
      )
  ) dfee_store
    ON dfee_store.store_id = base.store_id
   AND dfee_store.item_id = base.item_id
   AND dfee_store.msku = ${mskuExpr}
  LEFT JOIN (
    SELECT c.item_id, c.msku, c.delivery_fee
    FROM dim_product_cost_config c
    WHERE c.platform = 'walmart'
      AND c.status = 'active'
      AND c.delivery_fee IS NOT NULL
      AND COALESCE(c.item_id, '') != ''
      AND COALESCE(c.msku, '') != ''
      AND NOT EXISTS (
        SELECT 1
        FROM dim_product_cost_config newer
        WHERE newer.platform = 'walmart'
          AND newer.status = 'active'
          AND newer.delivery_fee IS NOT NULL
          AND newer.item_id = c.item_id
          AND newer.msku = c.msku
          AND (
            newer.effective_date > c.effective_date
            OR (newer.effective_date = c.effective_date AND newer.updated_at > c.updated_at)
            OR (newer.effective_date = c.effective_date AND newer.updated_at = c.updated_at AND newer.id > c.id)
          )
      )
  ) dfee_item
    ON dfee_item.item_id = base.item_id
   AND dfee_item.msku = ${mskuExpr}
  LEFT JOIN dim_product_wfs_fee_auto dfa
    ON dfa.platform = 'walmart'
   AND dfa.store_id = base.store_id
   AND dfa.msku = ${mskuExpr}
   AND dfa.fee IS NOT NULL
`;
}
// 2026-07-20 口径统一：WFS费改为 自动(dfa) > 人工store > 人工item > 0，
// 与 syncOrderProfitDaily 完全一致；CS测品不在自动表内，calcMetrics 的 CS 硬覆盖不受影响。

// ── 写入 raw_feishu_table ─────────────────────────────────────────────────────

async function insertRows(
  db: mysql.Connection,
  sheetId: string,
  sheetName: string,
  jsonRows: Record<string, string>[],
  baseRowIndex: number,
): Promise<number> {
  if (jsonRows.length === 0) return 0;

  const pulledAt   = new Date();
  const extraJson  = JSON.stringify({ source: "lingxing" });
  let   inserted   = 0;

  // 批量 INSERT（每批 200 行）
  const BATCH = 200;
  for (let start = 0; start < jsonRows.length; start += BATCH) {
    const batch  = jsonRows.slice(start, start + BATCH);
    const values: (string | number | Date)[] = [];
    const placeholders: string[] = [];

    for (let i = 0; i < batch.length; i++) {
      const rowIndex   = baseRowIndex + start + i;
      const rowJsonStr = JSON.stringify(batch[i]);
      const rawHash    = makeHash(SPREADSHEET_TOKEN, sheetId, String(rowIndex), rowJsonStr);

      placeholders.push("('lingxing', ?, ?, ?, ?, ?, ?, ?, ?)");
      values.push(
        SPREADSHEET_TOKEN, sheetId, sheetName,
        rowIndex, rowJsonStr, rawHash, pulledAt, extraJson,
      );
    }

    await db.query(
      `INSERT INTO raw_feishu_table
         (source_system, spreadsheet_token, sheet_id, sheet_name,
          row_index, row_json, raw_hash, pulled_at, extra_json)
       VALUES ${placeholders.join(", ")}`,
      values,
    );
    inserted += batch.length;
  }

  return inserted;
}

// ── 主 SQL（当日明细：有销售 OR 有广告花费 OR 有WFS库存的商品都写入）────────

// 6 个 ? 参数全部传同一个 targetDate
const DAILY_DETAIL_SQL = `
  SELECT
    COALESCE(f.store_name, a.store_name, inv2.store_name, '')  AS store_name,
    base.item_id,
    COALESCE(NULLIF(f.msku, ''), NULLIF(a.msku, ''), NULLIF(inv.msku, ''),
             NULLIF(dp.msku, ''), '')                         AS msku,
    COALESCE(f.sku, inv.sku, dp.sku, '')                       AS sku,
    COALESCE(dp.product_name, dp.item_name, '')                AS product_name,
    COALESCE(dp.owner, '')                                     AS owner,
    COALESCE(f.sales_qty, 0)                                   AS sales_qty,
    ROUND(COALESCE(f.sales_amount, 0), 2)                      AS sales_amount,
    ROUND(COALESCE(a.ad_spend, 0), 2)                          AS ad_spend,
    COALESCE(dfa.fee, dfee_store.delivery_fee, dfee_item.delivery_fee, 0) AS delivery_fee,
    COALESCE(dpc_store.purchase_cost, dpc_item.purchase_cost, 0) AS purchase_cost,
    COALESCE(dpc_store.first_mile_shipping_cost, dpc_item.first_mile_shipping_cost, 0) AS first_mile,
    COALESCE(inv.wfs_available_stock, 0)                       AS wfs_stock
  FROM (
    SELECT store_id, item_id FROM fact_sales_daily
      WHERE stat_date = ? AND platform = 'walmart'
    UNION
    SELECT store_id, item_id FROM fact_ads_product_daily
      WHERE stat_date = ? AND platform = 'walmart'
    UNION
    SELECT store_id, item_id FROM fact_inventory_daily
      WHERE snapshot_date = ? AND platform = 'walmart' AND wfs_available_stock > 0
  ) base
  LEFT JOIN fact_sales_daily f
    ON  f.item_id   = base.item_id
    AND f.store_id  = base.store_id
    AND f.stat_date = ?
    AND f.platform  = 'walmart'
  LEFT JOIN (
    SELECT store_id, item_id,
           MAX(store_name) AS store_name,
           MAX(msku)       AS msku,
           ROUND(SUM(ad_spend), 2) AS ad_spend
    FROM   fact_ads_product_daily
    WHERE  platform = 'walmart' AND stat_date = ?
    GROUP  BY store_id, item_id
  ) a
    ON  a.item_id  = base.item_id
    AND a.store_id = base.store_id
  LEFT JOIN fact_inventory_daily inv
    ON  inv.item_id       = base.item_id
    AND inv.store_id      = base.store_id
    AND inv.snapshot_date = ?
    AND inv.platform      = 'walmart'
  LEFT JOIN (
    SELECT store_id, item_id, MAX(store_name) AS store_name
    FROM   fact_inventory_daily
    WHERE  platform = 'walmart' AND snapshot_date = ?
    GROUP  BY store_id, item_id
  ) inv2
    ON  inv2.item_id  = base.item_id
    AND inv2.store_id = base.store_id
  LEFT JOIN dim_product dp
    ON  dp.item_id  = base.item_id
    AND dp.store_id = base.store_id
    AND dp.platform = 'walmart'
  ${costJoinSql("COALESCE(NULLIF(f.msku, ''), NULLIF(a.msku, ''), NULLIF(inv.msku, ''), NULLIF(dp.msku, ''), '')")}
  ${deliveryFeeJoinSql("COALESCE(NULLIF(f.msku, ''), NULLIF(a.msku, ''), NULLIF(inv.msku, ''), NULLIF(dp.msku, ''), '')")}
  ORDER BY COALESCE(f.sales_amount, 0) DESC
`;

// ── sheet: <REDACTED_FEISHU_SHEET_ID> / <REDACTED_FEISHU_SHEET_ID> ───────────────────────────────────────────────────

async function syncDetailSheet(
  db: mysql.Connection,
  sheet: { id: string; name: string },
  targetDate: string,
  clearAll: boolean,   // true=<REDACTED_FEISHU_SHEET_ID>（全量覆盖），false=<REDACTED_FEISHU_SHEET_ID>（按日期覆盖）
): Promise<number> {
  // 2026-07-31 #1-3修复：删除下移到有数据后、与INSERT同事务;先查数据

  // 2. 查数据（7 个 ? 全部传 targetDate）
  const [rawRows] = await db.query<mysql.RowDataPacket[]>(DAILY_DETAIL_SQL, Array(7).fill(targetDate));

  // 3. 转换成飞书格式 row_json（字段顺序与飞书一致）
  const jsonRows = (rawRows as mysql.RowDataPacket[]).map(r => {
    const m = calcMetrics({
      store_name:   String(r.store_name),
      msku:         String(r.msku),
      sales_qty:    Number(r.sales_qty),
      sales_amount: Number(r.sales_amount),
      ad_spend:     Number(r.ad_spend),
      delivery_fee: Number(r.delivery_fee),
      purchase_cost: Number(r.purchase_cost),
      first_mile:   Number(r.first_mile),
    });
    return {
      "SKU":             String(r.sku),
      "MSKU":            String(r.msku),
      "品名":            String(r.product_name),
      "备注":            "",
      "店铺":            String(r.store_name),
      "日期":            targetDate,
      "汇率":            String(EXCHANGE_RATE),
      "商品ID":          String(r.item_id),
      "毛利率":          pct(m.gross_margin),
      "负责人":          String(r.owner),
      "今日销量":        String(r.sales_qty),
      "广告占比":        pct(m.ad_ratio),
      "WFS可售库存":     String(r.wfs_stock),
      "店铺佣金率":      pct(m.commission_rate),
      "毛利润（$）":     n2(m.gross_profit),
      "头程成本(￥)":    n2(m.first_mile),
      "采购成本(￥)":    n2(m.purchase_cost),
      "WFS配送费（$）":  n2(m.wfs_fee),
      "广告花费（$）":   n2(Number(r.ad_spend)),
      "今日销售额（$）": n2(Number(r.sales_amount)),
    };
  });

  // 4. <REDACTED_FEISHU_SHEET_ID> 用日期编码的 row_index 避免与其他日期冲突
  //    <REDACTED_FEISHU_SHEET_ID> 从 2 开始（模拟飞书行号：第1行=表头，数据从2开始）
  const base = clearAll ? 2 : dateToRowBase(targetDate);

  if (jsonRows.length === 0) return 0;   // 2026-07-31 #1-3：源为空不删,保留存量
  await db.beginTransaction();
  try {
    if (clearAll) {
      await db.query(
        `DELETE FROM raw_feishu_table WHERE spreadsheet_token = ? AND sheet_id = ?`,
        [SPREADSHEET_TOKEN, sheet.id],
      );
    } else {
      await db.query(
        `DELETE FROM raw_feishu_table
         WHERE spreadsheet_token = ? AND sheet_id = ?
           AND JSON_UNQUOTE(JSON_EXTRACT(row_json, '$."日期"')) = ?`,
        [SPREADSHEET_TOKEN, sheet.id, targetDate],
      );
    }
    const inserted = await insertRows(db, sheet.id, sheet.name, jsonRows, base);
    await db.commit();
    return inserted;
  } catch (e) {
    await db.rollback();
    throw e;
  }
}

// ── sheet: <REDACTED_FEISHU_SHEET_ID>（近期利润与广告）────────────────────────────────────────────

async function syncRecentSheet(
  db: mysql.Connection,
  targetDate: string,
): Promise<number> {
  const sheet      = SHEETS.recent;
  const date7Start = addDays(targetDate, -6); // 近7天：含目标日在内往前6天
  const date5Start = addDays(targetDate, -4); // 近5天：含目标日在内往前4天

  // 2026-07-31 #1-3修复：删除下移到有数据后、与INSERT同事务;先查数据

  // 2. 查近7天每日明细（有销售 OR 有广告 OR 有WFS库存都纳入）
  const [rawRows] = await db.query<mysql.RowDataPacket[]>(`
    SELECT
      base.store_id,
      COALESCE(f.store_name, a.store_name, inv2.store_name, '') AS store_name,
      base.item_id,
      COALESCE(NULLIF(f.msku, ''), NULLIF(a.msku, ''), NULLIF(inv2.msku, ''),
               NULLIF(dp.msku, ''), '')                       AS msku,
      COALESCE(f.sku, inv2.sku, dp.sku, '')                     AS sku,
      COALESCE(dp.product_name, dp.item_name, '')               AS product_name,
      COALESCE(dp.owner, '')                                    AS owner,
      COALESCE(dfa.fee, dfee_store.delivery_fee, dfee_item.delivery_fee, 0) AS delivery_fee,
      COALESCE(dpc_store.purchase_cost, dpc_item.purchase_cost, 0) AS purchase_cost,
      COALESCE(dpc_store.first_mile_shipping_cost, dpc_item.first_mile_shipping_cost, 0) AS first_mile,
      DATE_FORMAT(base.stat_date, '%Y-%m-%d')                   AS stat_date,
      COALESCE(f.sales_qty, 0)                                  AS sales_qty,
      ROUND(COALESCE(f.sales_amount, 0), 2)                     AS sales_amount,
      ROUND(COALESCE(a.ad_spend, 0), 2)                         AS ad_spend
    FROM (
      SELECT store_id, item_id, stat_date FROM fact_sales_daily
        WHERE stat_date >= ? AND stat_date <= ? AND platform = 'walmart'
      UNION
      SELECT store_id, item_id, stat_date FROM fact_ads_product_daily
        WHERE stat_date >= ? AND stat_date <= ? AND platform = 'walmart'
      UNION
      SELECT store_id, item_id, snapshot_date AS stat_date FROM fact_inventory_daily
        WHERE snapshot_date >= ? AND snapshot_date <= ? AND platform = 'walmart'
          AND wfs_available_stock > 0
    ) base
    LEFT JOIN fact_sales_daily f
      ON  f.item_id   = base.item_id
      AND f.store_id  = base.store_id
      AND f.stat_date = base.stat_date
      AND f.platform  = 'walmart'
    LEFT JOIN (
      SELECT store_id, item_id, stat_date,
             MAX(store_name) AS store_name,
             MAX(msku)       AS msku,
             ROUND(SUM(ad_spend), 2) AS ad_spend
      FROM   fact_ads_product_daily
      WHERE  platform = 'walmart'
      GROUP  BY store_id, item_id, stat_date
    ) a
      ON  a.item_id   = base.item_id
      AND a.store_id  = base.store_id
      AND a.stat_date = base.stat_date
    LEFT JOIN (
      SELECT store_id, item_id, snapshot_date, MAX(store_name) AS store_name,
             MAX(msku) AS msku, MAX(sku) AS sku
      FROM   fact_inventory_daily
      WHERE  platform = 'walmart'
      GROUP  BY store_id, item_id, snapshot_date
    ) inv2
      ON  inv2.item_id       = base.item_id
      AND inv2.store_id      = base.store_id
      AND inv2.snapshot_date = base.stat_date
    LEFT JOIN dim_product dp
      ON  dp.item_id  = base.item_id
      AND dp.store_id = base.store_id
      AND dp.platform = 'walmart'
    ${costJoinSql("COALESCE(NULLIF(f.msku, ''), NULLIF(a.msku, ''), NULLIF(inv2.msku, ''), NULLIF(dp.msku, ''), '')")}
    ${deliveryFeeJoinSql("COALESCE(NULLIF(f.msku, ''), NULLIF(a.msku, ''), NULLIF(inv2.msku, ''), NULLIF(dp.msku, ''), '')")}
    ORDER BY base.item_id, base.store_id, base.stat_date DESC
  `, [date7Start, targetDate, date7Start, targetDate, date7Start, targetDate]);

  // 3. 按 (item_id, store_id) 聚合近7天 / 近5天
  interface Agg {
    store_name:   string;
    item_id:      string;
    msku:         string;
    sku:          string;
    product_name: string;
    owner:        string;
    delivery_fee: number;
    purchase_cost: number;
    first_mile:   number;
    d7: { qty: number; sales: number; ad: number };
    d5: { qty: number; sales: number; ad: number };
  }

  const map = new Map<string, Agg>();

  for (const r of rawRows as mysql.RowDataPacket[]) {
    const key = `${String(r.item_id)}___${String(r.store_id)}`;
    if (!map.has(key)) {
      map.set(key, {
        store_name:   String(r.store_name),
        item_id:      String(r.item_id),
        msku:         String(r.msku),
        sku:          String(r.sku),
        product_name: String(r.product_name),
        owner:        String(r.owner),
        delivery_fee: Number(r.delivery_fee),
        purchase_cost: Number(r.purchase_cost),
        first_mile:   Number(r.first_mile),
        d7: { qty: 0, sales: 0, ad: 0 },
        d5: { qty: 0, sales: 0, ad: 0 },
      });
    }
    const item    = map.get(key)!;
    const qty     = Number(r.sales_qty);
    const sales   = Number(r.sales_amount);
    const adSpend = Number(r.ad_spend);
    const date    = String(r.stat_date);

    // 近7天累计（所有行都在7天窗口内）
    item.d7.qty   += qty;
    item.d7.sales += sales;
    item.d7.ad    += adSpend;

    // 近5天：仅日期 >= date5Start 的行
    if (date >= date5Start) {
      item.d5.qty   += qty;
      item.d5.sales += sales;
      item.d5.ad    += adSpend;
    }
  }

  // 4. 计算各周期利润并构建 row_json
  function calcPeriod(
    totalSales: number, totalQty: number, totalAd: number,
    wfsFee: number, purchaseCost: number, firstMile: number, commRate: number,
  ): { gp: number; gm: number; ar: number } {
    const commission = totalSales * commRate;
    const gp = totalSales
      - totalAd
      - wfsFee * totalQty
      - commission
      - (purchaseCost + firstMile) * totalQty / EXCHANGE_RATE;
    return {
      gp: Math.round(gp * 100) / 100,
      gm: totalSales > 0 ? Math.round(gp / totalSales * 10000) / 10000 : 0,
      ar: totalSales > 0 ? Math.round(totalAd / totalSales * 10000) / 10000 : 0,
    };
  }

  const jsonRows: Record<string, string>[] = [];

  for (const item of map.values()) {
    const commRate = getCommissionRate(item.store_name);
    let wfsFee       = item.delivery_fee;
    let purchaseCost = item.purchase_cost;
    let firstMile    = item.first_mile;
    if (isYuesiCs(item.store_name, item.msku)) {
      wfsFee       = YUESI_CS_WFS_FEE;
      purchaseCost = YUESI_CS_PURCHASE_COST;
      firstMile    = YUESI_CS_FIRST_MILE;
    }

    const r7 = calcPeriod(item.d7.sales, item.d7.qty, item.d7.ad, wfsFee, purchaseCost, firstMile, commRate);
    const r5 = calcPeriod(item.d5.sales, item.d5.qty, item.d5.ad, wfsFee, purchaseCost, firstMile, commRate);

    // 字段顺序与飞书原始数据一致
    jsonRows.push({
      "SKU":           item.sku,
      "MSKU":          item.msku,
      "品名":          item.product_name,
      "店铺":          item.store_name,
      "商品ID":        item.item_id,
      "负责人":        item.owner,
      "近7天销量":     String(item.d7.qty),
      "近5天销量":     String(item.d5.qty),
      "近7天广告费":   n2(item.d7.ad),
      "近7天毛利润":   n2(r7.gp),
      "近7天毛利率":   pct(r7.gm),
      "近7天销售额":   n2(item.d7.sales),
      "近5天广告费":   n2(item.d5.ad),
      "近5天毛利润":   n2(r5.gp),
      "近5天毛利率":   pct(r5.gm),
      "近5天销售额":   n2(item.d5.sales),
      "近7天广告占比": pct(r7.ar),
      "近5天广告占比": pct(r5.ar),
    });
  }

  // 按近5天销售额降序排列
  jsonRows.sort((a, b) => Number(b["近5天销售额"]) - Number(a["近5天销售额"]));

  if (jsonRows.length === 0) return 0;   // 2026-07-31 #1-3：源为空不删,保留存量
  await db.beginTransaction();
  try {
    await db.query(
      `DELETE FROM raw_feishu_table WHERE spreadsheet_token = ? AND sheet_id = ?`,
      [SPREADSHEET_TOKEN, sheet.id],
    );
    const inserted = await insertRows(db, sheet.id, sheet.name, jsonRows, 2);
    await db.commit();
    return inserted;
  } catch (e) {
    await db.rollback();
    throw e;
  }
}

// ── 主入口 ────────────────────────────────────────────────────────────────────

type SyncOnly = "all" | "detail";

function parseArgs(): { targetDate: string; only: SyncOnly } {
  let targetDate = "";
  let only: SyncOnly = "all";

  for (const arg of process.argv.slice(2)) {
    const value = arg.trim();
    if (!value) continue;
    if (value.startsWith("--only=")) {
      const mode = value.slice("--only=".length);
      if (mode !== "all" && mode !== "detail") {
        throw new Error("参数 --only 只支持 all 或 detail");
      }
      only = mode;
      continue;
    }
    if (value.startsWith("--")) {
      throw new Error(`未知参数: ${value}`);
    }
    if (!targetDate) {
      targetDate = value;
      continue;
    }
    throw new Error(`多余参数: ${value}`);
  }

  return { targetDate: targetDate || yesterday(), only };
}

async function main(): Promise<void> {
  let parsed: { targetDate: string; only: SyncOnly };
  try {
    parsed = parseArgs();
  } catch (err) {
    console.error("❌ 参数错误:", err instanceof Error ? err.message : String(err));
    console.error("   用法: npx ts-node src/syncLingxingToRawFeishu.ts [YYYY-MM-DD] [--only=all|detail]");
    process.exit(1);
  }

  const { targetDate, only } = parsed;

  if (!/^\d{4}-\d{2}-\d{2}$/.test(targetDate)) {
    console.error("❌ 日期格式错误，应为 YYYY-MM-DD");
    console.error("   用法: npx ts-node src/syncLingxingToRawFeishu.ts [YYYY-MM-DD] [--only=all|detail]");
    process.exit(1);
  }

  console.log(`\n[syncLingxingToRawFeishu] 开始同步，目标日期: ${targetDate}`);
  console.log(`  同步范围: ${only === "detail" ? "仅每日销售明细" : "全部 raw sheet"}`);
  const startAt = Date.now();

  const db = await getDb();
  try {
    let n1 = 0;
    let n3 = 0;

    if (only === "all") {
      // <REDACTED_FEISHU_SHEET_ID>: 当日数据（全量覆盖）
      process.stdout.write(`  → ${SHEETS.daily.name} (${SHEETS.daily.id}) ... `);
      n1 = await syncDetailSheet(db, SHEETS.daily, targetDate, true);
      console.log(`✓ ${n1} 行`);
    }

    // <REDACTED_FEISHU_SHEET_ID>: 每日销售明细（按日期覆盖）
    process.stdout.write(`  → ${SHEETS.detail.name} (${SHEETS.detail.id}) ... `);
    const n2 = await syncDetailSheet(db, SHEETS.detail, targetDate, false);
    console.log(`✓ ${n2} 行`);

    if (only === "all") {
      // <REDACTED_FEISHU_SHEET_ID>: 近期利润与广告（近7/5天聚合，全量覆盖）
      process.stdout.write(`  → ${SHEETS.recent.name} (${SHEETS.recent.id}) ... `);
      n3 = await syncRecentSheet(db, targetDate);
      console.log(`✓ ${n3} 行`);
    }

    const elapsed = ((Date.now() - startAt) / 1000).toFixed(1);
    console.log(`\n[syncLingxingToRawFeishu] 完成 ✅  耗时 ${elapsed}s`);
    console.log(`  当日数据: ${n1} 行 | 每日销售明细: ${n2} 行 | 近期利润: ${n3} 行`);
  } catch (err) {
    console.error("\n[syncLingxingToRawFeishu] ❌ 错误:", err);
    process.exit(1);
  } finally {
    await db.end();
  }
}

main();
