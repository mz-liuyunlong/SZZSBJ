import "dotenv/config";
import * as mysql from "mysql2/promise";
import { sendCardToTarget, sendTextToTarget, getNotifyTenantToken, getTestChatId, resolveActiveMembers, type NotifyTarget } from "./feishuNotify";

const CS_ALERT_SUPERVISORS = (process.env.CS_ALERT_SUPERVISORS ?? "林翔,陈佳聪").split(",").map((s) => s.trim()).filter(Boolean);
const CS_ALERT_PENALTY_POINTS = 5;
// 绩效稽核收件人：凡发生扣绩效，均需通知（标准规则 2026-07-24：所有绩效扣分都发送给黄少如稽核留档）
const CS_ALERT_PENALTY_NOTIFY = (process.env.CS_ALERT_PENALTY_NOTIFY ?? "黄少如").split(",").map((s) => s.trim()).filter(Boolean);

interface CardBundle { title: string; card: Record<string, unknown>; fallbackText: string; }

// ============================================================================
// csTestAlertNotify.ts — CS测品异常预警（2026-07-24）
// 触发：测品天数>20 且 累计销量>11 且 未结束(test_end_date NULL)。工作日 17:00 检测。
// 阶段1（本文件当前范围）：--detect 逐字复刻 cs-test-analysis 生产查询 → 套触发条件
//   → 打印异常清单；加 --execute 才 upsert biz_cs_test_alert（只落库；不发卡、不扣分、不改 reason/status）。
// 阶段2+（后续）：--notify/--send 发飞书卡、绩效扣分、消警——本文件预留，暂未实现。
// 查询口径与参数序完全对齐 feishuRawSalesRoutes.ts 生产（[Q1]/[Q2] 实证）。
// ============================================================================

const CS_TEST_HISTORICAL_END_DATE = "2026-06-27";
const CS_TEST_AD_START_DATE = "2026-06-01";

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
}

// 数据可用日（≈生产 businessAvailableDate）：取 CS 销售/库存事实表最新数据日，自洽不依赖外部函数。
async function resolveAvailDate(db: mysql.Connection): Promise<string> {
  const [rows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT DATE_FORMAT(GREATEST(
        COALESCE((SELECT MAX(stat_date) FROM fact_sales_daily WHERE platform='walmart' AND msku LIKE 'CS%'), '2000-01-01'),
        COALESCE((SELECT MAX(snapshot_date) FROM fact_inventory_daily WHERE platform='walmart' AND msku LIKE 'CS%'), '2000-01-01')
      ), '%Y-%m-%d') AS avail`,
  );
  return String(rows[0]?.avail ?? "");
}

async function resolveProductNameExpr(db: mysql.Connection): Promise<string> {
  try {
    const [columnRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
       WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'dim_product'
         AND COLUMN_NAME IN ('product_name', 'item_name')`,
    );
    const cols = new Set(columnRows.map((r) => String(r.COLUMN_NAME)));
    return cols.has("item_name") ? "COALESCE(product_name, item_name, '')" : "COALESCE(product_name, '')";
  } catch {
    return "COALESCE(product_name, '')";
  }
}

interface AlertRow {
  store_id: string;
  item_id: string;
  msku: string;
  owner: string;
  first_ad_date: string | null;
  test_days: number;
  total_sales_qty: number;
}

// 逐字复刻 feishuRawSalesRoutes.ts 的 aggregateSql（[Q1]）；baseWhere 固定 '1=1'（检测不带页面筛选）。
function buildAggregateSql(productNameExpr: string): string {
  const baseWhere = "1=1";
  return `
    SELECT
      base.store_id,
      base.store_name,
      base.item_id,
      base.msku,
      base.sku,
      base.product_name,
      COALESCE(NULLIF(owner_map.owner, ''), NULLIF(base.owner, ''), '') AS owner,
      first_ad.first_ad_date AS first_ad_date,
      CASE
          WHEN first_ad.first_ad_date IS NULL THEN NULL
          WHEN COALESCE(inv.latest_non_wfs_stock, 0) > 0 THEN NULL
          WHEN inv.last_gt0_date IS NOT NULL AND DATE_ADD(inv.last_gt0_date, INTERVAL 1 DAY) >= first_ad.first_ad_date THEN DATE_FORMAT(DATE_ADD(inv.last_gt0_date, INTERVAL 1 DAY), '%Y-%m-%d')
          WHEN first_ad.first_ad_date <= '${CS_TEST_HISTORICAL_END_DATE}' THEN '${CS_TEST_HISTORICAL_END_DATE}'
          WHEN first_ad.first_ad_date <= '2026-07-21' THEN '2026-07-21'
          WHEN first_ad.last_ad_date IS NOT NULL THEN DATE_FORMAT(first_ad.last_ad_date, '%Y-%m-%d')
          ELSE NULL
        END AS test_end_date,
      CASE
          WHEN first_ad.first_ad_date IS NULL THEN 0
          WHEN COALESCE(inv.latest_non_wfs_stock, 0) <= 0 AND inv.last_gt0_date IS NOT NULL AND DATE_ADD(inv.last_gt0_date, INTERVAL 1 DAY) >= first_ad.first_ad_date THEN DATEDIFF(DATE_ADD(inv.last_gt0_date, INTERVAL 1 DAY), first_ad.first_ad_date) + 1
          WHEN COALESCE(inv.latest_non_wfs_stock, 0) <= 0 AND first_ad.first_ad_date <= '${CS_TEST_HISTORICAL_END_DATE}' THEN DATEDIFF('${CS_TEST_HISTORICAL_END_DATE}', first_ad.first_ad_date) + 1
          WHEN COALESCE(inv.latest_non_wfs_stock, 0) <= 0 AND first_ad.first_ad_date <= '2026-07-21' THEN DATEDIFF('2026-07-21', first_ad.first_ad_date) + 1
          WHEN COALESCE(inv.latest_non_wfs_stock, 0) <= 0 AND first_ad.last_ad_date IS NOT NULL THEN DATEDIFF(first_ad.last_ad_date, first_ad.first_ad_date) + 1
          WHEN COALESCE(inv.latest_non_wfs_stock, 0) <= 0 THEN NULL
          ELSE DATEDIFF(?, first_ad.first_ad_date) + 1
        END AS test_days,
      COALESCE(inv.latest_non_wfs_stock, 0) AS latest_non_wfs_stock,
      COALESCE(s.sales_days, 0) AS sales_days,
      COALESCE(s.total_sales_qty, 0) AS total_sales_qty,
      ROUND(CASE
          WHEN first_ad.first_ad_date IS NULL THEN 0
          WHEN COALESCE(inv.latest_non_wfs_stock, 0) <= 0 AND inv.last_gt0_date IS NOT NULL AND DATE_ADD(inv.last_gt0_date, INTERVAL 1 DAY) >= first_ad.first_ad_date THEN COALESCE(s.total_sales_qty, 0) / NULLIF(DATEDIFF(DATE_ADD(inv.last_gt0_date, INTERVAL 1 DAY), first_ad.first_ad_date) + 1, 0)
          WHEN COALESCE(inv.latest_non_wfs_stock, 0) <= 0 AND first_ad.first_ad_date <= '${CS_TEST_HISTORICAL_END_DATE}' THEN COALESCE(s.total_sales_qty, 0) / NULLIF(DATEDIFF('${CS_TEST_HISTORICAL_END_DATE}', first_ad.first_ad_date) + 1, 0)
          WHEN COALESCE(inv.latest_non_wfs_stock, 0) <= 0 AND first_ad.first_ad_date <= '2026-07-21' THEN COALESCE(s.total_sales_qty, 0) / NULLIF(DATEDIFF('2026-07-21', first_ad.first_ad_date) + 1, 0)
          WHEN COALESCE(inv.latest_non_wfs_stock, 0) <= 0 AND first_ad.last_ad_date IS NOT NULL THEN COALESCE(s.total_sales_qty, 0) / NULLIF(DATEDIFF(first_ad.last_ad_date, first_ad.first_ad_date) + 1, 0)
          WHEN COALESCE(inv.latest_non_wfs_stock, 0) <= 0 THEN NULL
          ELSE COALESCE(s.total_sales_qty, 0) / NULLIF(DATEDIFF(?, first_ad.first_ad_date) + 1, 0)
        END, 2) AS avg_daily_sales_qty,
      COALESCE(s.total_orders, 0) AS total_orders,
      ROUND(COALESCE(s.total_sales_amount, 0), 2) AS total_sales_amount
    FROM (
      SELECT
        platform,
        store_id,
        SUBSTRING_INDEX(GROUP_CONCAT(NULLIF(store_name, '') ORDER BY source_priority ASC, source_date DESC SEPARATOR '|||'), '|||', 1) AS store_name,
        item_id,
        msku,
        SUBSTRING_INDEX(GROUP_CONCAT(NULLIF(sku, '') ORDER BY source_priority ASC, source_date DESC SEPARATOR '|||'), '|||', 1) AS sku,
        SUBSTRING_INDEX(GROUP_CONCAT(NULLIF(product_name, '') ORDER BY source_priority ASC, source_date DESC SEPARATOR '|||'), '|||', 1) AS product_name,
        SUBSTRING_INDEX(GROUP_CONCAT(NULLIF(owner, '') ORDER BY source_priority ASC, source_date DESC SEPARATOR '|||'), '|||', 1) AS owner,
        SUBSTRING_INDEX(GROUP_CONCAT(NULLIF(launch_date, '') ORDER BY source_priority ASC, source_date DESC SEPARATOR '|||'), '|||', 1) AS launch_date
      FROM (
        SELECT
          1 AS source_priority,
          updated_at AS source_date,
          platform,
          store_id,
          store_name,
          item_id,
          msku,
          sku,
          ${productNameExpr} AS product_name,
          owner,
          DATE_FORMAT(launch_date, '%Y-%m-%d') AS launch_date
        FROM dim_product
        WHERE platform = 'walmart' AND msku LIKE 'CS%'
        UNION ALL
        SELECT
          2 AS source_priority,
          stat_date AS source_date,
          platform,
          store_id,
          store_name,
          item_id,
          msku,
          sku,
          '' AS product_name,
          '' AS owner,
          '' AS launch_date
        FROM fact_sales_daily
        WHERE platform = 'walmart' AND msku LIKE 'CS%' AND stat_date >= ? AND stat_date <= ?
        UNION ALL
        SELECT
          3 AS source_priority,
          snapshot_date AS source_date,
          platform,
          store_id,
          store_name,
          item_id,
          msku,
          sku,
          '' AS product_name,
          '' AS owner,
          '' AS launch_date
        FROM fact_inventory_daily
        WHERE platform = 'walmart' AND msku LIKE 'CS%' AND snapshot_date >= ? AND snapshot_date <= ?
      ) base_raw
      GROUP BY platform, store_id, item_id, msku
    ) base
    LEFT JOIN (
      SELECT
        item_id,
        SUBSTRING_INDEX(GROUP_CONCAT(NULLIF(owner_name, '') ORDER BY effective_date DESC, updated_at DESC SEPARATOR '|||'), '|||', 1) AS owner
      FROM dim_product_owner
      WHERE platform = 'walmart' AND status = 'active'
      GROUP BY item_id
    ) owner_map
      ON owner_map.item_id = base.item_id
    LEFT JOIN (
      SELECT store_id, item_id, MIN(stat_date) AS first_ad_date, MAX(stat_date) AS last_ad_date
      FROM fact_ads_product_daily
      WHERE platform = 'walmart' AND ad_spend > 0
      GROUP BY store_id, item_id
    ) first_ad
      ON first_ad.store_id = base.store_id AND first_ad.item_id = base.item_id
    LEFT JOIN (
      SELECT
        store_id,
        item_id,
        MIN(stat_date) AS first_ad_date,
        COUNT(*) AS ad_record_count,
        SUM(impressions) AS impressions,
        SUM(clicks) AS clicks,
        SUM(ad_spend) AS total_ad_spend,
        SUM(orders) AS ad_orders,
        SUM(total_sales) AS ad_sales
      FROM fact_ads_product_daily
      WHERE platform = 'walmart' AND stat_date >= ? AND stat_date <= ?
      GROUP BY store_id, item_id
    ) ad
      ON ad.store_id = base.store_id AND ad.item_id = base.item_id
    LEFT JOIN (
      SELECT
        store_id,
        item_id,
        msku,
        COUNT(DISTINCT CASE WHEN sales_qty > 0 THEN stat_date END) AS sales_days,
        SUM(sales_qty) AS total_sales_qty,
        SUM(COALESCE(NULLIF(order_count, 0), sales_qty)) AS total_orders,
        SUM(sales_amount) AS total_sales_amount
      FROM fact_sales_daily
      WHERE platform = 'walmart' AND IFNULL(?, '') IS NOT NULL AND IFNULL(?, '') IS NOT NULL /* 全历史口径；占位仅保参数序 */
      GROUP BY store_id, item_id, msku
    ) s
      ON s.store_id = base.store_id AND s.item_id = base.item_id AND COALESCE(s.msku, '') = COALESCE(base.msku, '')
    LEFT JOIN (
      SELECT
        i.store_id,
        i.item_id,
        i.msku,
        SUBSTRING_INDEX(GROUP_CONCAT(GREATEST(COALESCE(i.non_wfs_available_stock, 0), 0) ORDER BY i.snapshot_date DESC SEPARATOR ','), ',', 1) AS latest_non_wfs_stock,
        MAX(i.snapshot_date) AS latest_inventory_date,
        MAX(CASE WHEN GREATEST(COALESCE(i.non_wfs_available_stock, 0), 0) > 0 THEN i.snapshot_date END) AS last_gt0_date,
        MIN(CASE
          WHEN fa.first_ad_date IS NOT NULL
           AND i.snapshot_date >= fa.first_ad_date
           AND GREATEST(COALESCE(i.non_wfs_available_stock, 0), 0) <= 0
          THEN i.snapshot_date
        END) AS stock_out_date
      FROM fact_inventory_daily i
      LEFT JOIN (
        SELECT store_id, item_id, MIN(stat_date) AS first_ad_date
        FROM fact_ads_product_daily
        WHERE platform = 'walmart' AND ad_spend > 0
        GROUP BY store_id, item_id
      ) fa ON fa.store_id = i.store_id AND fa.item_id = i.item_id
      WHERE i.platform = 'walmart' AND IFNULL(?, '') IS NOT NULL AND IFNULL(?, '') IS NOT NULL /* 全历史口径；占位仅保参数序 */
      GROUP BY i.store_id, i.item_id, i.msku
    ) inv
      ON inv.store_id = base.store_id AND inv.item_id = base.item_id AND COALESCE(inv.msku, '') = COALESCE(base.msku, '')
    WHERE ${baseWhere}
      AND first_ad.first_ad_date IS NOT NULL
      AND first_ad.first_ad_date >= '${CS_TEST_AD_START_DATE}'
  `;
}

async function detect(db: mysql.Connection): Promise<AlertRow[]> {
  const avail = await resolveAvailDate(db);
  const productNameExpr = await resolveProductNameExpr(db);
  const aggregateSql = buildAggregateSql(productNameExpr);
  // 参数序完全对齐生产 [Q2]：12 个日期占位，dateStart=dateEnd=avail（单日窗，base 由 dim_product 分支兜底全量）
  const params: string[] = [
    avail, avail,       // test_days / avg DATEDIFF 兜底
    avail, avail,       // base fact_sales_daily
    avail, avail,       // base fact_inventory_daily
    avail, avail,       // ad 窗口
    avail, avail,       // s 销售窗口（IFNULL 中性化）
    avail, avail,       // inv 库存窗口（IFNULL 中性化）
  ];
  // 漏斗诊断：全量CS → 各触发条件 → 交集，验证口径与页面一致、清单条数由来
  const [funnelRows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT COUNT(*) AS total,
            SUM(CASE WHEN agg.test_days > 20 THEN 1 ELSE 0 END) AS d_days,
            SUM(CASE WHEN agg.total_sales_qty > 11 THEN 1 ELSE 0 END) AS d_sales,
            SUM(CASE WHEN agg.test_end_date IS NULL THEN 1 ELSE 0 END) AS d_open,
            SUM(CASE WHEN (agg.test_days > 20 OR agg.total_sales_qty > 11) AND agg.test_end_date IS NULL THEN 1 ELSE 0 END) AS d_all
       FROM (${aggregateSql}) agg`,
    params,
  );
  const f = funnelRows[0] ?? {};
  console.log(`[漏斗] 全量CS测品=${Number(f.total ?? 0)} ｜ 测品>20天=${Number(f.d_days ?? 0)} ｜ 累计销量>11=${Number(f.d_sales ?? 0)} ｜ 未结束=${Number(f.d_open ?? 0)} ｜ 三条件交集=${Number(f.d_all ?? 0)}`);
  const [rows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT agg.store_id, agg.item_id, agg.msku, agg.owner,
            DATE_FORMAT(agg.first_ad_date, '%Y-%m-%d') AS first_ad_date,
            agg.test_days, agg.total_sales_qty
       FROM (${aggregateSql}) agg
      WHERE (agg.test_days > 20 OR agg.total_sales_qty > 11) AND agg.test_end_date IS NULL
      ORDER BY agg.test_days DESC`,
    params,
  );
  console.log(`[detect] 数据可用日=${avail}；异常清单（测品>20天 或 累计销量>11，且 未结束）共 ${rows.length} 条：`);
  const out: AlertRow[] = [];
  for (const r of rows) {
    const row: AlertRow = {
      store_id: String(r.store_id ?? ""),
      item_id: String(r.item_id ?? ""),
      msku: String(r.msku ?? ""),
      owner: String(r.owner ?? ""),
      first_ad_date: r.first_ad_date ? String(r.first_ad_date).slice(0, 10) : null,
      test_days: Number(r.test_days ?? 0),
      total_sales_qty: Number(r.total_sales_qty ?? 0),
    };
    out.push(row);
    console.log(`  ${row.msku} | ItemID ${row.item_id} | ${row.owner || "(无负责人)"} | 测品${row.test_days}天 | 累计销量${row.total_sales_qty} | 首广${row.first_ad_date ?? "-"}`);
  }
  return out;
}

async function upsertAlerts(db: mysql.Connection, rows: AlertRow[]): Promise<number> {
  let n = 0;
  for (const r of rows) {
    if (!r.owner) { console.log(`  [跳过落库] ${r.msku} 无负责人，暂不建预警行`); continue; }
    const [res] = await db.query<mysql.ResultSetHeader>(
      `INSERT INTO biz_cs_test_alert
         (platform, store_id, item_id, msku, owner_name, test_days_snapshot, sales_qty_snapshot, first_ad_date_snapshot, first_alert_date, status)
       VALUES ('walmart', ?, ?, ?, ?, ?, ?, ?, CURDATE(), 'open')
       ON DUPLICATE KEY UPDATE
         owner_name = VALUES(owner_name),
         test_days_snapshot = VALUES(test_days_snapshot),
         sales_qty_snapshot = VALUES(sales_qty_snapshot),
         first_ad_date_snapshot = VALUES(first_ad_date_snapshot),
         updated_at = NOW()`,
      [r.store_id, r.item_id, r.msku, r.owner, r.test_days, r.total_sales_qty, r.first_ad_date],
    );
    n += res.affectedRows > 0 ? 1 : 0;
  }
  return n;
}

// ── 阶段2 探针：飞书 2.0 表单输入卡（form+input+submit）——验证飞书是否接受/渲染输入框 ──
function buildOwnerAlertInputCard(a: {
  id: number; msku: string; item_id: string; owner_name: string;
  test_days: number; sales_qty: number; first_ad: string;
}, testMode: boolean): CardBundle {
  const title = `${testMode ? "【测试】" : ""}⚠️ CS测品异常预警 · ${a.msku}`;
  const bodyMd =
    `**负责人：${a.owner_name}**\n` +
    `产品 **${a.msku}** ｜ ItemID ${a.item_id}\n` +
    `测品 **${a.test_days} 天**、累计销量 **${a.sales_qty} 件**，仍未结束测品（未转稳定期/未清货），属异常。\n` +
    `首广 ${a.first_ad}。请填写原因（不少于 15 字）后提交。\n` +
    `<font color="red">**⚠ 绩效规则**：须【当天】填写原因（≥15字）。未填写：从第 2 次提醒起，每个工作日累计扣 **5 分**，直至填写原因或测品结束。</font>`;
  const card = {
    schema: "2.0",
    config: { wide_screen_mode: true },
    header: { template: "orange", title: { tag: "plain_text", content: title } },
    body: {
      elements: [
        { tag: "markdown", content: bodyMd },
        {
          tag: "form",
          name: "csAlertForm",
          elements: [
            {
              tag: "input",
              name: "reason",
              label: { tag: "plain_text", content: "预警原因（≥15字）" },
              placeholder: { tag: "plain_text", content: "为什么测品超期仍未结束？后续处理动作是……" },
              max_length: 500,
            },
            {
              tag: "button",
              text: { tag: "plain_text", content: "提交原因" },
              type: "primary",
              action_type: "form_submit",
              name: "submitReason",
              value: { biz: "cs_test_alert", id: a.id, ...(testMode ? { test: 1 } : {}) },
            },
          ],
        },
      ],
    },
  };
  const fb = `${title}\n${a.owner_name}｜${a.msku} 测品${a.test_days}天/销量${a.sales_qty}件 未结束，请当天填写原因（≥15字）。绩效规则：未填从第2次提醒起每工作日累计扣5分，直至填写或测品结束。`;
  return { title, card, fallbackText: fb };
}

async function cardProbe(db: mysql.Connection): Promise<void> {
  const [rows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT id, msku, item_id, owner_name, test_days_snapshot, sales_qty_snapshot,
            DATE_FORMAT(first_ad_date_snapshot,'%Y-%m-%d') AS first_ad
       FROM biz_cs_test_alert WHERE status = 'open' ORDER BY id LIMIT 1`,
  );
  if (!rows.length) { console.log("[card-probe] biz_cs_test_alert 无 open 行，先跑 --detect --execute"); return; }
  const r = rows[0];
  const bundle = buildOwnerAlertInputCard({
    id: Number(r.id), msku: String(r.msku), item_id: String(r.item_id), owner_name: String(r.owner_name),
    test_days: Number(r.test_days_snapshot ?? 0), sales_qty: Number(r.sales_qty_snapshot ?? 0),
    first_ad: String(r.first_ad ?? "-"),
  }, true);
  const testChat = getTestChatId();
  if (!testChat) { console.log("[card-probe] 测试群未配置（getTestChatId 空）"); return; }
  const target: NotifyTarget = { type: "chat", label: "测试群(CS预警探针)", id: testChat };
  console.log(`[card-probe] 真实发送 2.0 表单输入卡 → 测试群，产品=${r.msku}`);
  // 第4参=doSend：true 才真发（现有清货卡同款）；探针目标本身就是测试群，不会二次镜像
  const res = await sendCardToTarget(target, bundle.card, bundle.fallbackText, true);
  console.log(`[card-probe] 飞书发送结果：ok=${res.ok}${res.error ? ` error=${res.error}` : ""} retry=${res.retryCount}`);
  console.log(`[card-probe] 若 ok=true 请到测试群看：输入框能否渲染；若 ok=false 上面的 error 即飞书拒绝原因（据此判定改 1.0 兜底或修 2.0 结构）`);
}

// ── 主管汇总卡（1.0，只读；列出当日各异常品 谁已填/未填）──
function buildSupervisorSummaryCard(
  rows: Array<{ msku: string; owner_name: string; test_days_snapshot: number; sales_qty_snapshot: number; status: string; penalty_count: number }>,
  dateStr: string, testMode: boolean,
): { card: Record<string, unknown>; fallbackText: string } {
  const title = `${testMode ? "【测试】" : ""}📋 CS测品异常预警·汇总 ｜ ${dateStr}（${rows.length} 个产品）`;
  const lines = rows.map((r, i) => {
    const state = r.status === "resolved" ? "✅ 已填原因" : (r.penalty_count > 0 ? `⚠ 待填（已累计扣${r.penalty_count * CS_ALERT_PENALTY_POINTS}分）` : "⚠ 待填");
    return `${i + 1}. **${r.msku}** ｜ ${r.owner_name} ｜ ${r.test_days_snapshot}天/${r.sales_qty_snapshot}件 ｜ ${state}`;
  });
  const content = lines.length ? lines.join("\n") : "（今日无异常产品）";
  const card = {
    config: { wide_screen_mode: true },
    header: { template: "orange", title: { tag: "plain_text", content: title } },
    elements: [
      { tag: "div", text: { tag: "lark_md", content: "以下 CS 测品产品**超20天 或 销量超11件，且仍未结束**，需负责人当天填写原因：" } },
      { tag: "div", text: { tag: "lark_md", content } },
      { tag: "note", elements: [{ tag: "lark_md", content: "绩效规则：负责人未填原因，从第2次提醒起每工作日累计扣5分，直至填写或测品结束。" }] },
    ],
  };
  const fb = `${title}\n${content}`;
  return { card, fallbackText: fb };
}

// ── 每日通知：给 open 预警发负责人卡 + 递增次数 + 第2次起未填累计扣5分 + 主管汇总卡 ──
async function notify(db: mysql.Connection, isTest: boolean): Promise<void> {
  const dateStr = await (async () => {
    const [d] = await db.query<mysql.RowDataPacket[]>("SELECT DATE_FORMAT(CURDATE(),'%Y-%m-%d') AS d");
    return String(d[0]?.d ?? "");
  })();
  const [rows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT id, store_id, item_id, msku, owner_name, test_days_snapshot, sales_qty_snapshot,
            DATE_FORMAT(first_ad_date_snapshot,'%Y-%m-%d') AS first_ad,
            DATE_FORMAT(last_sent_date,'%Y-%m-%d') AS last_sent_date, send_count, penalty_count, status
       FROM biz_cs_test_alert WHERE status = 'open' ORDER BY id`,
  );
  console.log(`[notify] ${isTest ? "测试模式(发测试群)" : "正式发送"}：open 预警 ${rows.length} 条（当日 ${dateStr}）`);
  const testChat = getTestChatId();
  let sent = 0, penalized = 0, skipped = 0, skippedToday = 0;
  const penaltyEvents: Array<{ owner: string; msku: string; item_id: string; points: number; sendCount: number }> = [];
  for (const r of rows) {
    const id = Number(r.id);
    const owner = String(r.owner_name ?? "");
    // 同日护栏：今天已发过就整行跳过，防同一自然日重复递增 send_count / 重复扣分
    // （正式 cron 每工作日一次；同日重试或手动补跑不重复计分。跨工作日累计不受影响。）
    const lastSent = r.last_sent_date ? String(r.last_sent_date).slice(0, 10) : null;
    if (lastSent === dateStr) {
      console.log(`  [今日已发] ${r.msku} last_sent_date=${lastSent}，本自然日已处理，跳过（不重复递增/扣分）`);
      skippedToday++;
      continue;
    }
    const bundle = buildOwnerAlertInputCard({
      id, msku: String(r.msku), item_id: String(r.item_id), owner_name: owner,
      test_days: Number(r.test_days_snapshot ?? 0), sales_qty: Number(r.sales_qty_snapshot ?? 0), first_ad: String(r.first_ad ?? "-"),
    }, isTest);
    let target: NotifyTarget | null = null;
    if (isTest) {
      if (!testChat) { console.log("  [跳过] 测试群未配置"); skipped++; continue; }
      target = { type: "chat", label: `测试群(CS-${owner})`, id: testChat };
    } else {
      const { targets, warnings } = await resolveActiveMembers([owner]);
      for (const w of warnings) console.log(`  [花名册] ${w}`);
      target = targets.find((t) => t.label === owner) ?? null;
      if (!target) { console.log(`  [跳过] ${owner} 花名册未命中，${r.msku} 本次不发`); skipped++; continue; }
    }
    const sr = await sendCardToTarget(target, bundle.card, bundle.fallbackText, true);
    if (!sr.ok) { console.log(`  [失败] ${r.msku} → ${owner}：${sr.error ?? ""}`); skipped++; continue; }
    sent++;
    const newCount = Number(r.send_count ?? 0) + 1;
    await db.query(
      `UPDATE biz_cs_test_alert SET send_count = ?, last_sent_date = CURDATE(),
              first_alert_date = COALESCE(first_alert_date, CURDATE()) WHERE id = ?`,
      [newCount, id],
    );
    // 扣分累计：第2次发送起、且仍未填原因，每次发送再扣5分（ref_event_id 编码 (id,发送次)防重跑）
    if (newCount >= 2) {
      // 2026-07-29 修复：测试/正式独立 ref 命名空间，避免测试扣分行占坑挡住正式 INSERT IGNORE（uq_perf_ref 撞键静默吞真实扣分）
      const refEventId = (isTest ? 3000000000 : 2000000000) + id * 10000 + newCount;
      // 测试模式(--test-send)扣分行加测试标记：created_by=..._TEST + note前缀【测试】，便于事后按 created_by 批量筛除、不污染真人绩效核算
      const dedCreatedBy = isTest ? "csTestAlertNotify_TEST" : "csTestAlertNotify";
      const dedNote = `${isTest ? "【测试】" : ""}测品超20天或销量超11未结束且第${newCount}次提醒未填原因`;
      const [pr] = await db.query<mysql.ResultSetHeader>(
        `INSERT IGNORE INTO biz_perf_deduction
           (deduction_date, owner_name, points, entry_type, biz_type, platform, store_id, item_id, msku, ref_event_id, note, created_by)
         VALUES (CURDATE(), ?, ?, 'deduct', 'cs_test_alert', 'walmart', ?, ?, ?, ?, ?, ?)`,
        [owner, CS_ALERT_PENALTY_POINTS, String(r.store_id ?? ""), String(r.item_id ?? ""), String(r.msku ?? ""),
         refEventId, dedNote, dedCreatedBy],
      );
      if (pr.affectedRows > 0) {
        await db.query(`UPDATE biz_cs_test_alert SET penalty_count = penalty_count + 1 WHERE id = ?`, [id]);
        penalized++;
        penaltyEvents.push({ owner, msku: String(r.msku ?? ""), item_id: String(r.item_id ?? ""), points: CS_ALERT_PENALTY_POINTS, sendCount: newCount });
        console.log(`  [扣分] ${owner} ${r.msku} 第${newCount}次未填 → 扣${CS_ALERT_PENALTY_POINTS}分`);
      }
    }
    await db.query("COMMIT");
  }
  // 绩效稽核：本次新增的所有扣分逐条汇总，发送给黄少如（人事HR）——标准规则：所有绩效扣分都通知黄少如稽核留档
  if (penaltyEvents.length > 0) {
    const totalPts = penaltyEvents.reduce((sum, e) => sum + e.points, 0);
    const lines = penaltyEvents.map(
      (e, i) => `${i + 1}. ${e.owner}｜${e.msku}（ItemID ${e.item_id}）｜第${e.sendCount}次未填原因 → 扣${e.points}分`,
    );
    const auditText =
      `${isTest ? "【测试】" : ""}🧾 CS测品异常预警 · 绩效扣分明细（${dateStr}）\n` +
      `本次新增扣分 ${penaltyEvents.length} 笔、合计 ${totalPts} 分。明细：\n${lines.join("\n")}\n` +
      `规则：测品超20天或销量超11未结束，从第2次提醒起每工作日未填原因累计扣5分。扣分明细已落 biz_perf_deduction 台账。`;
    try {
      const token = await getNotifyTenantToken();
      if (isTest) {
        if (testChat) await sendTextToTarget(token, { type: "chat", label: "测试群(绩效稽核)", id: testChat }, auditText, true);
      } else {
        const { targets, warnings } = await resolveActiveMembers(CS_ALERT_PENALTY_NOTIFY);
        for (const w of warnings) console.log(`  [花名册-绩效稽核] ${w}`);
        if (!targets.length) console.log(`  [绩效稽核] ${CS_ALERT_PENALTY_NOTIFY.join("/")} 花名册未命中，扣分通知未发出（扣分已入库）`);
        for (const t of targets) await sendTextToTarget(token, t, auditText, true);
      }
      console.log(`  [绩效稽核] 扣分明细已发送 → ${isTest ? "测试群" : CS_ALERT_PENALTY_NOTIFY.join("/")}（${penaltyEvents.length}笔/${totalPts}分）`);
    } catch (ae) {
      console.warn(`  [绩效稽核] 发送扣分明细失败（扣分已入库，不影响台账）：${ae instanceof Error ? ae.message : String(ae)}`);
    }
  }
  // 同日护栏：本次无任何新发送/扣分（多为同一自然日重复运行，open 行均被同日护栏拦截）→ 完全空跑，不重发汇总卡
  if (sent === 0 && penalized === 0) {
    console.log(`[notify] 本次无新发送/扣分（同日护栏拦截 ${skippedToday} 条），跳过主管汇总卡，视为同日空跑。`);
    console.log(`SUMMARY_JSON ${JSON.stringify({ mode: isTest ? "test" : "real", open: rows.length, sent, penalized, skipped, skippedToday })}`);
    return;
  }
  // 主管汇总卡
  const [sumRows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT msku, owner_name, test_days_snapshot, sales_qty_snapshot, status, penalty_count
       FROM biz_cs_test_alert WHERE status IN ('open','resolved') AND last_sent_date = CURDATE() ORDER BY status, id`,
  );
  const summary = buildSupervisorSummaryCard(
    sumRows.map((r) => ({
      msku: String(r.msku), owner_name: String(r.owner_name), test_days_snapshot: Number(r.test_days_snapshot ?? 0),
      sales_qty_snapshot: Number(r.sales_qty_snapshot ?? 0), status: String(r.status), penalty_count: Number(r.penalty_count ?? 0),
    })), dateStr, isTest,
  );
  if (isTest) {
    if (testChat) await sendCardToTarget({ type: "chat", label: "测试群(CS汇总)", id: testChat }, summary.card, summary.fallbackText, true);
  } else {
    const { targets, warnings } = await resolveActiveMembers(CS_ALERT_SUPERVISORS);
    for (const w of warnings) console.log(`  [花名册-主管] ${w}`);
    for (const t of targets) await sendCardToTarget(t, summary.card, summary.fallbackText, true);
  }
  console.log(`[notify] 完成：发卡=${sent} 扣分=${penalized} 跳过=${skipped} 今日已发跳过=${skippedToday}；汇总卡→${isTest ? "测试群" : CS_ALERT_SUPERVISORS.join("/")}`);
  console.log(`SUMMARY_JSON ${JSON.stringify({ mode: isTest ? "test" : "real", open: rows.length, sent, penalized, skipped, skippedToday })}`);
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const doDetect = args.includes("--detect");
  const doCardProbe = args.includes("--card-probe");
  const doNotify = args.includes("--notify");
  const testSend = args.includes("--test-send");
  const execute = args.includes("--execute");
  if (!doDetect && !doCardProbe && !doNotify) {
    console.log("用法: npx ts-node src/csTestAlertNotify.ts --detect [--execute] | --card-probe | --notify [--test-send|--send]");
    console.log("  --detect            跑异常清单并打印（DRY-RUN，不写库）");
    console.log("  --detect --execute  额外 upsert biz_cs_test_alert（只落库；不发卡、不扣分、不改 reason/status）");
    console.log("  --card-probe        发一张 2.0 表单输入卡到测试群（探针）");
    console.log("  --notify --test-send  给 open 预警发负责人卡+主管汇总卡到【测试群】，并按规则递增次数/累计扣分");
    console.log("  --notify --send       正式：负责人卡发本人、汇总卡发林翔/陈佳聪");
    process.exit(2);
  }
  const db = await getDb();
  try {
    if (doCardProbe) {
      await cardProbe(db);
      return;
    }
    if (doNotify) {
      const realSend = args.includes("--send");
      if (!testSend && !realSend) { console.log("[notify] 需 --test-send（测试群）或 --send（正式）"); return; }
      if (testSend && realSend) { console.log("[错误] --test-send 与 --send 不可同用"); return; }
      await notify(db, !realSend);
      return;
    }
    const rows = await detect(db);
    if (execute) {
      const n = await upsertAlerts(db, rows);
      await db.query("COMMIT"); // 防生产 MySQL autocommit=0：显式提交，避免 end() 断开被隐式回滚
      const [dbg] = await db.query<mysql.RowDataPacket[]>(
        "SELECT DATABASE() AS db, (SELECT COUNT(*) FROM biz_cs_test_alert) AS cnt",
      );
      console.log(`[execute] 已 upsert biz_cs_test_alert 影响行 ${n}（仅落库/更新快照；reason/status 不动）`);
      console.log(`[execute] 写入库=${String(dbg[0]?.db ?? "")} ｜ biz_cs_test_alert 当前行数=${Number(dbg[0]?.cnt ?? 0)}`);
    } else {
      console.log("[dry-run] 未写库。加 --execute 才落库。");
    }
    console.log(`SUMMARY_JSON ${JSON.stringify({ mode: execute ? "execute" : "dry-run", availDetected: rows.length })}`);
  } finally {
    await db.end();
  }
}

main().catch((e) => {
  console.error(`FATAL: ${e instanceof Error ? e.stack || e.message : String(e)}`);
  process.exit(1);
});
