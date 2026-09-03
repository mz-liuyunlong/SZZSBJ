/**
 * pmcFeeDetailRoutes.ts — 智能PMC·仓储费/入库运输 明细（2026-08-18 新增，隔离模块）
 * 挂载：/api/pmc/fee-detail（adminServer 全局登录门禁已覆盖 /api/*，登录即可读）
 * 只读：全部 SELECT，前端仅读 FACT/DIM 层（fact_wfs_storage_fee / fact_storage_fee_daily /
 *       fact_inbound_freight_alloc / fact_wfs_shipment_item / dim_product / dim_store / dim_store_config）。
 * 视图（仿沃尔玛 Seller Center）：
 *   - 仓储费   GET /storage/list?mode=bill(默认)                → 账单账期原行（与沃尔玛仓储报告一一对应）
 *              GET /storage/list?mode=custom&date_start&date_end → fact_storage_fee_daily 日摊按区间求和（任意日期金额准确）
 *   - 入库运输 GET /inbound/list?mode=bill(默认)                → 分摊原行
 *              GET /inbound/list?mode=custom&date_start&date_end → 账期与所选区间有交集的原行（一次性费用不按天拆分，需求方 2026-08-18 确认）
 * 关联：SKU/负责人=dim_product(店铺+商品ID+MSKU，兜底 店铺+商品ID)；入库GTIN=fact_wfs_shipment_item(shipment_id+MSKU)。
 */
import { Router, Request, Response } from "express";
import * as mysql from "mysql2/promise";

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
// §12：NULL(报告版式无此列)必须保留为 null 给前端显示"—"，不得吞成 0
const numN = (v: unknown): number | null => { if (v == null) return null; const n = Number(v); return Number.isFinite(n) ? n : null; };

/** 店铺名 + 产品(SKU/负责人)关联片段（复用全站口径：dim_store → dim_store_config → store_id 兜底） */
const STORE_NAME_EXPR = `COALESCE(NULLIF(ds.store_name,''), NULLIF(dc.store_name,''), f.store_id)`;
const STORE_JOINS = `
  LEFT JOIN dim_store ds ON ds.store_id = f.store_id
  LEFT JOIN dim_store_config dc ON dc.platform = 'walmart' AND dc.store_id = f.store_id AND dc.is_active = 1`;
const PRODUCT_JOIN_MSKU = (mskuCol: string): string => `
  LEFT JOIN (SELECT store_id, item_id, msku, MAX(NULLIF(TRIM(sku),'')) AS sku, MAX(NULLIF(TRIM(owner),'')) AS owner
             FROM dim_product WHERE platform = 'walmart' GROUP BY store_id, item_id, msku) p
    ON p.store_id = f.store_id AND p.item_id = f.item_id AND p.msku = ${mskuCol}
  LEFT JOIN (SELECT store_id, item_id, MAX(NULLIF(TRIM(sku),'')) AS sku, MAX(NULLIF(TRIM(owner),'')) AS owner
             FROM dim_product WHERE platform = 'walmart' GROUP BY store_id, item_id) p2
    ON p2.store_id = f.store_id AND p2.item_id = f.item_id`;

// ── GET /storage/list ────────────────────────────────────────────────────────
router.get("/storage/list", async (req: Request, res: Response): Promise<void> => {
  const mode = String(req.query.mode ?? "bill") === "custom" ? "custom" : "bill";
  const db = await getDb();
  try {
    const [syncRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT DATE_FORMAT(MAX(updated_at), '%Y-%m-%d %H:%i:%s') AS ts FROM fact_wfs_storage_fee`,
    );
    const [boundRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT DATE_FORMAT(MIN(fee_date),'%Y-%m-%d') AS min_d, DATE_FORMAT(MAX(fee_date),'%Y-%m-%d') AS max_d
       FROM fact_storage_fee_daily`,
    );
    const minDaily = String(boundRows[0]?.min_d ?? "");
    const maxDaily = String(boundRows[0]?.max_d ?? "");

    if (mode === "bill") {
      const [rows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT f.store_id, ${STORE_NAME_EXPR} AS store_name,
                f.sku AS msku, COALESCE(p.sku, p2.sku, '') AS sku, COALESCE(p.owner, p2.owner, '') AS owner,
                f.item_id, f.gtin,
                DATE_FORMAT(f.report_start,'%Y-%m-%d') AS report_start,
                DATE_FORMAT(f.report_end,'%Y-%m-%d') AS report_end,
                f.days_in_period, f.avg_units_standard, f.avg_units_longterm,
                f.original_amount, f.discount_savings, f.final_storage_fee, f.source_task_id,
                f.length_in, f.width_in, f.height_in, f.weight_lb,
                f.unit_fee_standard, f.unit_fee_peak, f.unit_fee_lt366, f.unit_fee_lt450,
                f.avg_units_peak, f.avg_units_lt366, f.avg_units_lt450
         FROM fact_wfs_storage_fee f ${STORE_JOINS} ${PRODUCT_JOIN_MSKU("f.sku")}
         ORDER BY f.report_start DESC, store_name, msku`,
      );
      res.json({
        mode, latest_sync_time: syncRows[0]?.ts ?? null, daily_min: minDaily, daily_max: maxDaily,
        rows: rows.map((r) => ({
          store_id: String(r.store_id), store_name: String(r.store_name), msku: String(r.msku),
          sku: String(r.sku), owner: String(r.owner), item_id: String(r.item_id), gtin: String(r.gtin),
          report_start: String(r.report_start), report_end: String(r.report_end),
          days_in_period: num(r.days_in_period), avg_units_standard: num(r.avg_units_standard),
          avg_units_longterm: num(r.avg_units_longterm), original_amount: num(r.original_amount),
          discount_savings: num(r.discount_savings), final_storage_fee: num(r.final_storage_fee),
          source_task_id: String(r.source_task_id),
          length_in: numN(r.length_in), width_in: numN(r.width_in),
          height_in: numN(r.height_in), weight_lb: numN(r.weight_lb),
          unit_fee_standard: numN(r.unit_fee_standard), unit_fee_peak: numN(r.unit_fee_peak),
          unit_fee_lt366: numN(r.unit_fee_lt366), unit_fee_lt450: numN(r.unit_fee_lt450),
          avg_units_peak: numN(r.avg_units_peak), avg_units_lt366: numN(r.avg_units_lt366),
          avg_units_lt450: numN(r.avg_units_lt450),
        })),
      });
      return;
    }

    // custom：日摊表按区间求和；缺省区间 = 日摊数据最近30天
    let dateStart = String(req.query.date_start ?? "");
    let dateEnd = String(req.query.date_end ?? "");
    if (!DATE_RE.test(dateEnd)) dateEnd = maxDaily;
    if (!DATE_RE.test(dateStart)) {
      const end = new Date(`${dateEnd}T00:00:00Z`);
      dateStart = Number.isFinite(end.getTime())
        ? new Date(end.getTime() - 29 * 86400000).toISOString().slice(0, 10)
        : minDaily;
    }
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT f.store_id, ${STORE_NAME_EXPR} AS store_name,
              f.msku, COALESCE(p.sku, p2.sku, '') AS sku, COALESCE(p.owner, p2.owner, '') AS owner,
              f.item_id, f.gtin, f.days_covered, f.storage_fee
       FROM (SELECT store_id, sku AS msku, MAX(NULLIF(TRIM(gtin),'')) AS gtin, MAX(NULLIF(TRIM(item_id),'')) AS item_id,
                    COUNT(DISTINCT fee_date) AS days_covered, SUM(storage_fee) AS storage_fee
             FROM fact_storage_fee_daily
             WHERE platform = 'walmart' AND fee_date >= ? AND fee_date <= ?
             GROUP BY store_id, sku) f
       ${STORE_JOINS} ${PRODUCT_JOIN_MSKU("f.msku")}
       ORDER BY store_name, f.msku`,
      [dateStart, dateEnd],
    );
    res.json({
      mode, latest_sync_time: syncRows[0]?.ts ?? null, daily_min: minDaily, daily_max: maxDaily,
      date_start: dateStart, date_end: dateEnd,
      rows: rows.map((r) => ({
        store_id: String(r.store_id), store_name: String(r.store_name), msku: String(r.msku),
        sku: String(r.sku), owner: String(r.owner), item_id: String(r.item_id ?? ""), gtin: String(r.gtin ?? ""),
        days_covered: num(r.days_covered), storage_fee: num(r.storage_fee),
      })),
    });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end();
  }
});

// ── GET /inbound/list ────────────────────────────────────────────────────────
router.get("/inbound/list", async (req: Request, res: Response): Promise<void> => {
  const mode = String(req.query.mode ?? "bill") === "custom" ? "custom" : "bill";
  const db = await getDb();
  try {
    const [syncRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT DATE_FORMAT(MAX(updated_at), '%Y-%m-%d %H:%i:%s') AS ts,
              DATE_FORMAT(MIN(report_start),'%Y-%m-%d') AS min_d, DATE_FORMAT(MAX(report_end),'%Y-%m-%d') AS max_d
       FROM fact_inbound_freight_alloc`,
    );
    const minD = String(syncRows[0]?.min_d ?? "");
    const maxD = String(syncRows[0]?.max_d ?? "");

    let where = "1=1";
    const params: string[] = [];
    let dateStart = "", dateEnd = "";
    if (mode === "custom") {
      dateStart = String(req.query.date_start ?? "");
      dateEnd = String(req.query.date_end ?? "");
      if (!DATE_RE.test(dateStart)) dateStart = minD;
      if (!DATE_RE.test(dateEnd)) dateEnd = maxD;
      // 账期与所选区间有交集（一次性费用不按天拆分）
      where = "f.report_start <= ? AND f.report_end >= ?";
      params.push(dateEnd, dateStart);
    }
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT f.store_id, ${STORE_NAME_EXPR} AS store_name,
              f.settlement_month,
              DATE_FORMAT(f.report_start,'%Y-%m-%d') AS report_start,
              DATE_FORMAT(f.report_end,'%Y-%m-%d') AS report_end,
              f.cargo_code, f.shipment_id, f.msku,
              COALESCE(p.sku, p2.sku, NULLIF(si.sku,''), '') AS sku,
              COALESCE(p.owner, p2.owner, '') AS owner,
              f.item_id, COALESCE(si.gtin, '') AS gtin,
              f.declare_num, f.freight_total, f.alloc_amount, f.alloc_basis, f.source_task_id
       FROM fact_inbound_freight_alloc f
       ${STORE_JOINS} ${PRODUCT_JOIN_MSKU("f.msku")}
       LEFT JOIN (SELECT shipment_id, msku, MAX(NULLIF(TRIM(gtin),'')) AS gtin, MAX(NULLIF(TRIM(sku),'')) AS sku
                  FROM fact_wfs_shipment_item GROUP BY shipment_id, msku) si
         ON si.shipment_id = f.shipment_id AND si.msku = f.msku
       WHERE ${where}
       ORDER BY f.settlement_month DESC, f.report_start DESC, store_name, f.cargo_code, f.msku`,
      params,
    );
    res.json({
      mode, latest_sync_time: syncRows[0]?.ts ?? null, period_min: minD, period_max: maxD,
      date_start: dateStart || undefined, date_end: dateEnd || undefined,
      rows: rows.map((r) => ({
        store_id: String(r.store_id), store_name: String(r.store_name),
        settlement_month: String(r.settlement_month),
        report_start: String(r.report_start), report_end: String(r.report_end),
        cargo_code: String(r.cargo_code), shipment_id: String(r.shipment_id),
        msku: String(r.msku), sku: String(r.sku), owner: String(r.owner),
        item_id: String(r.item_id), gtin: String(r.gtin),
        declare_num: num(r.declare_num), freight_total: num(r.freight_total),
        alloc_amount: num(r.alloc_amount), alloc_basis: String(r.alloc_basis),
        source_task_id: String(r.source_task_id),
      })),
    });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end();
  }
});

export default router;
