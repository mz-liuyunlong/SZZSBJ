/**
 * adsFeeReportRoutes.ts — 广告系统·广告费用报表（2026-08-19 新增，隔离只读模块）
 * 挂载：/api/finance/ads-fee（复用 /api/finance 既有 nginx 代理与全局登录门禁，登录即可读；
 *       注册在 aiFinanceRoutes 之前，更具体先挂——参照 /api/hr/attendance 先例）
 * 只读：全部 SELECT，前端仅读 FACT/DIM 层（fact_ads_product_daily / dim_product / dim_store / dim_store_config）。
 * 背景（2026-08-19 需求方拍板）：财务每月下载站内广告(SP/SB/SV)费用明细，粒度=店铺-ITEMID-MSKU-SKU；
 *   SEM 财务另用「SEM广告数据」页（campaign级已可到ITEMID），本页排除 campaign_type='sem'。
 *   数据权威性：fact_ads_product_daily 非sem合计已与 Walmart Connect 发票逐张 $0.01 对平
 *   （2026-08-19 全量对账，见 TASK_CHANGE_LOG；尾部1~2天T+2滞后除外）。
 * 视图：
 *   GET /list?granularity=month(默认)                    → 区间汇总：店铺+ITEMID+MSKU+广告类型 一行
 *   GET /list?granularity=day                            → 按天明细：另带 stat_date 列
 *   两种视图均接受 date_start/date_end（缺省=数据最新日所在月的1日~数据最新日）。
 *   口径：仅含区间内花费合计>0 的行（零花费行为展示噪音，不入报表）。
 */
import { Router, Request, Response } from "express";
import * as mysql from "mysql2/promise";
import { adjustedAdsFactSql } from "./adsItemSpendAlloc";

const router = Router();

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const num = (v: unknown): number => { const n = Number(v); return Number.isFinite(n) ? n : 0; };

/** 店铺名 + 产品(SKU/负责人)关联片段（与 pmcFeeDetailRoutes 同口径） */
const STORE_NAME_EXPR = `COALESCE(NULLIF(ds.store_name,''), NULLIF(dc.store_name,''), f.store_id)`;
const STORE_JOINS = `
  LEFT JOIN dim_store ds ON ds.store_id = f.store_id
  LEFT JOIN dim_store_config dc ON dc.platform = 'walmart' AND dc.store_id = f.store_id AND dc.is_active = 1`;
const PRODUCT_JOIN = `
  LEFT JOIN (SELECT store_id, item_id, msku, MAX(NULLIF(TRIM(sku),'')) AS sku, MAX(NULLIF(TRIM(owner),'')) AS owner
             FROM dim_product WHERE platform = 'walmart' GROUP BY store_id, item_id, msku) p
    ON p.store_id = f.store_id AND p.item_id = f.item_id AND p.msku = f.msku
  LEFT JOIN (SELECT store_id, item_id, MAX(NULLIF(TRIM(sku),'')) AS sku, MAX(NULLIF(TRIM(owner),'')) AS owner,
                    MAX(NULLIF(TRIM(msku),'')) AS msku
             FROM dim_product WHERE platform = 'walmart' GROUP BY store_id, item_id) p2
    ON p2.store_id = f.store_id AND p2.item_id = f.item_id`;
// （2026-08-19 SEM纳入报表后不再排除sem；保留注释备忘：账单扣费bill分支读发票头表，天然不含SEM）

// ── GET /list ────────────────────────────────────────────────────────────────
router.get("/list", async (req: Request, res: Response): Promise<void> => {
  const gq = String(req.query.granularity ?? "month");
  const granularity = gq === "day" ? "day" : gq === "bill" ? "bill" : "month";
  const db = await getDb();
  try {
    // 账单视图（2026-08-19 需求方追加，对标仓储费页账单视图）：发票账期原行，
    // 一行=一张Connect发票；扣款方式(Seller Center/Credit Card/Invoice待扣款)在此视图体现（发票级属性）。
    if (granularity === "bill") {
      const [metaB] = await db.query<mysql.RowDataPacket[]>(
        `SELECT DATE_FORMAT(MAX(updated_at), '%Y-%m-%d %H:%i:%s') AS ts,
                DATE_FORMAT(MIN(period_start),'%Y-%m-%d') AS min_d, DATE_FORMAT(MAX(period_end),'%Y-%m-%d') AS max_d
         FROM fact_onsite_ads_invoice_head`,
      );
      const [rowsB] = await db.query<mysql.RowDataPacket[]>(
        `SELECT h.store_id,
                COALESCE(NULLIF(h.store_name,''), NULLIF(ds.store_name,''), NULLIF(dc.store_name,''), h.store_id) AS store_name,
                h.invoice_number,
                DATE_FORMAT(h.period_start,'%Y-%m-%d') AS period_start,
                DATE_FORMAT(h.period_end,'%Y-%m-%d') AS period_end,
                DATE_FORMAT(h.invoice_date,'%Y-%m-%d') AS invoice_date,
                DATE_FORMAT(h.charge_date,'%Y-%m-%d') AS charge_date,
                h.line_count, h.total_ad_spend, h.total_credits_applied, h.total_charged,
                h.payment_method, h.source_task_id
           FROM fact_onsite_ads_invoice_head h
           LEFT JOIN dim_store ds ON ds.store_id = h.store_id
           LEFT JOIN dim_store_config dc ON dc.platform = 'walmart' AND dc.store_id = h.store_id AND dc.is_active = 1
          ORDER BY h.period_start DESC, store_name, h.invoice_number`,
      );
      res.json({
        granularity, latest_sync_time: metaB[0]?.ts ?? null,
        data_min: String(metaB[0]?.min_d ?? ""), data_max: String(metaB[0]?.max_d ?? ""),
        rows: rowsB.map((r) => ({
          store_id: String(r.store_id), store_name: String(r.store_name),
          invoice_number: String(r.invoice_number),
          period_start: String(r.period_start ?? ""), period_end: String(r.period_end ?? ""),
          invoice_date: r.invoice_date == null ? null : String(r.invoice_date),
          charge_date: r.charge_date == null ? null : String(r.charge_date),
          line_count: num(r.line_count), ad_spend: num(r.total_ad_spend),
          credits_applied: num(r.total_credits_applied), total_charged: num(r.total_charged),
          payment_method: String(r.payment_method ?? ""), source_task_id: String(r.source_task_id ?? ""),
        })),
      });
      return;
    }
    // 2026-08-19 需求方拍板：SEM纳入本报表（sem行现已自带item_id/msku，近30天覆盖率100%实证）；
    // 账单扣费页(bill分支)不含SEM——SEM走店铺账单结算，无Connect发票。
    const [metaRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT DATE_FORMAT(MAX(updated_at), '%Y-%m-%d %H:%i:%s') AS ts,
              DATE_FORMAT(MIN(stat_date),'%Y-%m-%d') AS min_d, DATE_FORMAT(MAX(stat_date),'%Y-%m-%d') AS max_d
       FROM fact_ads_product_daily WHERE platform='walmart'`,
    );
    const minD = String(metaRows[0]?.min_d ?? "");
    const maxD = String(metaRows[0]?.max_d ?? "");

    let dateStart = String(req.query.date_start ?? "");
    let dateEnd = String(req.query.date_end ?? "");
    if (!DATE_RE.test(dateEnd)) dateEnd = maxD;
    if (!DATE_RE.test(dateStart)) dateStart = dateEnd ? `${dateEnd.slice(0, 8)}01` : minD;

    const dayCols = granularity === "day" ? `DATE_FORMAT(f.stat_date,'%Y-%m-%d') AS stat_date,` : "";
    const innerDay = granularity === "day" ? `stat_date,` : "";
    const innerDayGroup = granularity === "day" ? `, stat_date` : "";
    // 2026-08-25 需求方拍板：按品广告费统一口径——SV无商品ID行(占位1001类)的钱按广告组回归商品，
    // 页面不再出现占位行。统一分摊逻辑见 adsItemSpendAlloc.ts（一处计算多处读取）。
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT f.store_id, ${STORE_NAME_EXPR} AS store_name,
              f.item_id, COALESCE(NULLIF(f.msku,''), p2.msku, '') AS msku,
              COALESCE(p.sku, p2.sku, '') AS sku, COALESCE(p.owner, p2.owner, '') AS owner,
              f.ad_type, ${dayCols} f.days_covered, f.ad_spend
       FROM (SELECT store_id, item_id, msku, ${innerDay}
                    COALESCE(NULLIF(TRIM(campaign_type),''),'unknown') AS ad_type,
                    COUNT(DISTINCT stat_date) AS days_covered,
                    ROUND(SUM(ad_spend),2) AS ad_spend
             FROM ${adjustedAdsFactSql()} base
             WHERE base.platform='walmart' AND base.stat_date >= ? AND base.stat_date <= ?
             GROUP BY store_id, item_id, msku, COALESCE(NULLIF(TRIM(campaign_type),''),'unknown')${innerDayGroup}
             HAVING SUM(ad_spend) > 0) f
       ${STORE_JOINS} ${PRODUCT_JOIN}
       ORDER BY store_name, f.ad_spend DESC`,
      [dateStart, dateEnd],
    );
    res.json({
      granularity, latest_sync_time: metaRows[0]?.ts ?? null, data_min: minD, data_max: maxD,
      date_start: dateStart, date_end: dateEnd,
      rows: rows.map((r) => ({
        store_id: String(r.store_id), store_name: String(r.store_name),
        item_id: String(r.item_id ?? ""), msku: String(r.msku ?? ""),
        sku: String(r.sku), owner: String(r.owner),
        ad_type: String(r.ad_type),
        ...(granularity === "day" ? { stat_date: String(r.stat_date) } : {}),
        days_covered: num(r.days_covered), ad_spend: num(r.ad_spend),
      })),
    });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end();
  }
});

export default router;
