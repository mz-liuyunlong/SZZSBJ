/**
 * pmcRoutes.ts - AI智能PMC（批④，2026-07-21 需求方定稿）
 * 挂载：/api/pmc（adminServer，Basic Auth 保护区内）
 * GET /list：在营产品 × 最新库存/在途 × 近7日日销 × 未完结采购(按SKU) ×
 *            全部未完结货件 × 70天补货建议（清货期无建议）× 风险分层
 * 只读模块，不写任何表
 */

import { Router, Request, Response } from "express";
import * as mysql from "mysql2/promise";
import { replenishSuggestion, riskLevel } from "./notifyRules/pmcRule";

const router = Router();
const TARGET_DAYS = Number(process.env.PMC_TARGET_DAYS ?? 70);
// 2026-07-21 需求方：虚拟产品剔除（XY2007 等），CSV 可扩展
const EXCLUDE_SKUS = new Set(
  (process.env.PMC_EXCLUDE_SKUS ?? "XY2007").split(",").map((s) => s.trim()).filter(Boolean),
);

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
    dateStrings: true,
  });
}
function txt(v: unknown): string { return String(v ?? "").trim(); }

router.get("/list", async (req: Request, res: Response): Promise<void> => {
  const fStore = txt(req.query.store);
  const fOwner = txt(req.query.owner);
  const fRisk = txt(req.query.risk);
  const db = await getDb();
  try {
    // 店铺名三层兜底
    const nameMap = new Map<string, string>();
    const mergeNames = (rows: mysql.RowDataPacket[]): void => {
      for (const r of rows) {
        const id = txt(r.store_id); const nm = txt(r.store_name);
        if (id && nm && !nameMap.has(id)) nameMap.set(id, nm);
      }
    };
    const [n1] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, MAX(NULLIF(TRIM(store_name),'')) AS store_name FROM dim_product
       WHERE store_id IS NOT NULL AND store_id<>'' GROUP BY store_id`);
    mergeNames(n1);
    try {
      const [n2] = await db.query<mysql.RowDataPacket[]>(
        `SELECT store_id, store_name FROM dim_store_config WHERE store_id IS NOT NULL AND store_id<>''`);
      mergeNames(n2);
    } catch { /* 忽略 */ }

    // 在营 item（含清货期标记）
    const [items] = await db.query<mysql.RowDataPacket[]>(
      `SELECT p.store_id,
              COALESCE(MAX(NULLIF(TRIM(p.store_name),'')),'') AS store_name,
              p.item_id,
              SUBSTRING(GROUP_CONCAT(DISTINCT NULLIF(TRIM(p.msku),'') SEPARATOR '/'),1,500) AS mskus,
              COALESCE(MAX(NULLIF(TRIM(p.sku),'')),'') AS sku,
              COALESCE(MAX(NULLIF(TRIM(p.owner),'')),'') AS owner,
              MAX(CASE WHEN COALESCE(NULLIF(TRIM(p.manual_lifecycle_stage),''), bs.lifecycle_stage, bs.system_lifecycle_stage, '') = '清货期'
                       THEN 1 ELSE 0 END) AS is_clearance
       FROM dim_product p
       LEFT JOIN dim_product_business_state bs
         ON bs.platform = p.platform AND bs.store_id = p.store_id AND bs.item_id = p.item_id
        AND COALESCE(bs.msku,'') = COALESCE(p.msku,'')
        AND bs.stat_date = (SELECT MAX(stat_date) FROM dim_product_business_state WHERE platform='walmart')
       WHERE p.platform='walmart'
         AND COALESCE(p.product_management_status,'active') = 'active'
         AND p.item_id IS NOT NULL AND p.item_id <> ''
       GROUP BY p.store_id, p.item_id`,
    );
    // 库存/在途
    const [inv] = await db.query<mysql.RowDataPacket[]>(
      `SELECT inv.store_id, inv.item_id,
              SUM(COALESCE(inv.wfs_available_stock,0)) AS wfs,
              SUM(COALESCE(inv.inbound_stock,0)) AS inbound
       FROM fact_inventory_daily inv
       JOIN (SELECT store_id, item_id, msku, MAX(snapshot_date) AS d FROM fact_inventory_daily
             WHERE platform='walmart' GROUP BY store_id, item_id, msku) li
         ON li.store_id=inv.store_id AND li.item_id=inv.item_id AND li.msku=inv.msku AND inv.snapshot_date=li.d
       WHERE inv.platform='walmart' GROUP BY inv.store_id, inv.item_id`,
    );
    const invMap = new Map(inv.map((r) => [`${r.store_id}|${r.item_id}`, { wfs: Number(r.wfs ?? 0), inbound: Number(r.inbound ?? 0) }]));
    // 近7数据日销量
    const [dateRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT DISTINCT DATE_FORMAT(stat_date,'%Y-%m-%d') AS d FROM fact_sales_daily
       WHERE platform='walmart' ORDER BY d DESC LIMIT 7`);
    const dates = dateRows.map((r) => String(r.d));
    const salesMap = new Map<string, number>();
    if (dates.length) {
      const [sr] = await db.query<mysql.RowDataPacket[]>(
        `SELECT store_id, item_id, SUM(COALESCE(sales_qty,0)) AS qty FROM fact_sales_daily
         WHERE platform='walmart' AND stat_date IN (${dates.map(() => "?").join(",")})
         GROUP BY store_id, item_id`, dates);
      for (const r of sr) salesMap.set(`${r.store_id}|${r.item_id}`, Number(r.qty ?? 0));
    }
    const dayCount = Math.max(dates.length, 1);
    // 采购中口径（2026-07-21 需求方定稿）：
    //   采购中 = A 未到货采购 Σ(quantity_receive=待收量；未作废；预计到货不早于90天前防陈年脏单) —— 2026-08-03 修正:领星 quantity_receive 实为待收量,原"计划-已收"口径反了(全部到货单反被全额计入)
    //          + B 本地仓库存（采购到货入本地仓、尚未创建货件扣减的部分）
    //   创建货件扣本地仓后 → 计入"在途"（fact_inventory_daily.inbound_stock），不再算采购中
    const poMap = new Map<string, { qty: number; nearest: string }>();
    try {
      const [po] = await db.query<mysql.RowDataPacket[]>(
        `SELECT i.sku,
                SUM(COALESCE(i.quantity_receive,0)) AS open_qty,
                MIN(NULLIF(TRIM(i.expect_arrive_time),'')) AS nearest
         FROM fact_purchase_order_item i
         JOIN fact_purchase_order o ON o.order_sn = i.order_sn
         WHERE o.status_text NOT LIKE '%作废%'
           AND (NULLIF(TRIM(i.expect_arrive_time),'') IS NULL
                OR i.expect_arrive_time >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 90 DAY), '%Y-%m-%d'))
         GROUP BY i.sku`);
      for (const r of po) poMap.set(txt(r.sku), { qty: Number(r.open_qty ?? 0), nearest: txt(r.nearest) });
    } catch { /* 采购表未建时忽略 */ }
    const localMap = new Map<string, number>();
    try {
      const [loc] = await db.query<mysql.RowDataPacket[]>(
        `SELECT sku, qty FROM fact_local_inventory_daily
         WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM fact_local_inventory_daily)`);
      for (const r of loc) localMap.set(txt(r.sku), Number(r.qty ?? 0));
    } catch { /* 本地仓表未建/未同步时忽略 */ }
    // 全部未完结货件（按 item 汇总多条）
    const shipMap = new Map<string, Array<{ id: string; status: string; received: number; declared: number }>>();
    try {
      const [ships] = await db.query<mysql.RowDataPacket[]>(
        `SELECT s.store_id, s.shipment_id, COALESCE(NULLIF(TRIM(s.status_name),''), s.status) AS status_name,
                si.msku, SUM(COALESCE(si.declare_num,0)) AS declared, SUM(COALESCE(si.received_num,0)) AS received
         FROM fact_wfs_shipment s
         JOIN fact_wfs_shipment_item si
           ON si.platform=s.platform AND si.store_id=s.store_id AND si.shipment_id=s.shipment_id
         WHERE s.platform='walmart'
           AND s.to_closed_time IS NULL
           AND s.to_cancelled_time IS NULL
         GROUP BY s.store_id, s.shipment_id, si.msku`);
      const [mskuRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT store_id, msku, item_id FROM dim_product
         WHERE platform='walmart' AND msku IS NOT NULL AND TRIM(msku)<>''`);
      const itemByMsku = new Map(mskuRows.map((r) => [`${r.store_id}|${txt(r.msku)}`, txt(r.item_id)]));
      for (const r of ships) {
        const itemId = itemByMsku.get(`${r.store_id}|${txt(r.msku)}`);
        if (!itemId) continue;
        const key = `${r.store_id}|${itemId}`;
        if (!shipMap.has(key)) shipMap.set(key, []);
        const arr = shipMap.get(key)!;
        const existing = arr.find((x) => x.id === txt(r.shipment_id));
        if (existing) {
          existing.received += Number(r.received ?? 0);
          existing.declared += Number(r.declared ?? 0);
        } else {
          arr.push({ id: txt(r.shipment_id), status: txt(r.status_name), received: Number(r.received ?? 0), declared: Number(r.declared ?? 0) });
        }
      }
    } catch (e) {
      // 2026-07-21 教训：此前静默吞掉 DATETIME='' 比较错误导致在途恒0难排查——必须留日志
      console.warn("[PMC] 货件在途查询失败（在途按0处理）:", e instanceof Error ? e.message : String(e));
    }

    const rows = items
      .filter((r) => !EXCLUDE_SKUS.has(txt(r.sku)))
      .map((r) => {
      const key = `${r.store_id}|${r.item_id}`;
      const iv = invMap.get(key) ?? { wfs: 0, inbound: 0 };
      const daily7 = Math.round((salesMap.get(key) ?? 0) / dayCount * 100) / 100;
      const sku = txt(r.sku);
      // 2026-07-21 在途口径修复：fact_inventory_daily.inbound_stock 上游未建设（恒0），
      // 改由未完结货件推导 Σ(申报-已收)；与需求方流程"创建货件→在途"一致
      const shipList = shipMap.get(key) ?? [];
      const inboundDerived = shipList.reduce((a, sp) => a + Math.max(sp.declared - sp.received, 0), 0);
      const inbound = Math.max(inboundDerived, iv.inbound);
      const po = poMap.get(sku) ?? { qty: 0, nearest: "" };
      const localQty = localMap.get(sku) ?? 0;
      const procurement = po.qty + localQty;
      const isClearance = Number(r.is_clearance ?? 0) === 1;
      const sug = replenishSuggestion({
        stock: iv.wfs, inbound, purchased: procurement, daily7, isClearance, targetDays: TARGET_DAYS,
      });
      return {
        store_id: txt(r.store_id),
        store_name: txt(r.store_name) || nameMap.get(txt(r.store_id)) || txt(r.store_id),
        item_id: txt(r.item_id),
        mskus: txt(r.mskus) || "-",
        sku: sku || "-",
        owner: txt(r.owner) || "-",
        stock: iv.wfs,
        inbound,
        procurement,
        procurement_po: po.qty,
        procurement_local: localQty,
        purchase_nearest: po.nearest,
        daily7,
        days_to_sell: sug.daysToSell,
        shipments: shipList,
        suggestion: isClearance ? "" : sug.label,
        suggestion_qty: sug.qty,
        risk: riskLevel(iv.wfs, daily7, isClearance),
      };
    });

    // 采购中总量按 SKU 去重（同 SKU 多变体行共享同一采购量，逐行累加会重复计数）
    const skuSeen = new Set<string>();
    let procurementTotal = 0;
    for (const r of rows) {
      if (r.procurement > 0 && !skuSeen.has(r.sku)) {
        skuSeen.add(r.sku);
        procurementTotal += r.procurement;
      }
    }
    const kpi = {
      total: rows.length,
      out_of_stock: rows.filter((r) => r.risk === "已断货").length,
      within7: rows.filter((r) => r.risk === "≤7天").length,
      need_replenish: rows.filter((r) => r.suggestion_qty > 0).length,
      inbound_total: rows.reduce((a, r) => a + r.inbound, 0),
      procurement_total: procurementTotal,
    };

    let out = rows;
    if (fStore) out = out.filter((r) => r.store_name === fStore || r.store_id === fStore);
    if (fOwner) out = out.filter((r) => r.owner === fOwner);
    if (fRisk) out = out.filter((r) => r.risk === fRisk);
    const riskOrder: Record<string, number> = { "已断货": 0, "≤7天": 1, "≤14天": 2, "健康": 3, "无动销": 4, "积压": 5, "清货中": 6, "无库存": 7 };
    out.sort((a, b) => (riskOrder[a.risk] ?? 9) - (riskOrder[b.risk] ?? 9) || b.daily7 - a.daily7);

    res.json({
      ok: true,
      kpi,
      target_days: TARGET_DAYS,
      sales_dates: dates,
      purchase_synced: poMap.size > 0 || localMap.size > 0,
      stores: [...new Set(rows.map((r) => r.store_name).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh")),
      owners: [...new Set(rows.map((r) => r.owner).filter((o) => o && o !== "-"))].sort((a, b) => a.localeCompare(b, "zh")),
      risks: ["已断货", "≤7天", "≤14天", "健康", "无动销", "积压", "清货中"],
      total: out.length,
      rows: out,
    });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end().catch(() => {});
  }
});

export default router;
