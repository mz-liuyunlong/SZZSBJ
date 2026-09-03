/**
 * pmcInventoryRoutes.ts - 智能PMC · 库存一览表（2026-08-02，隔离新模块，只读）
 * 挂载：/api/pmc/inventory（adminServer，Basic Auth 保护区内；挂 /api/pmc/ 下复用现有 nginx 代理）
 * GET /overview：ITEMID→MSKU×店铺 库存四桶 + 库存数量（本期不含成本/货值）
 *   - 本地仓库/已采购 = SKU级共享池，按近30天销量分摊到 ITEMID（1:1直归；全0均摊）
 *   - 在途/WFS/非WFS = MSKU×店铺级，直接摊到子行
 *   - 库存数量 = 已采购 + 本地仓库 + 在途 + WFS在库；非WFS 独立展示
 *   口径见 context/DATABASE_MAP「库存一览表 · 四桶数据源与库存数量公式」。只读，不写任何表。
 */
import { Router, Request, Response } from "express";
import * as mysql from "mysql2/promise";

const router = Router();
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
function num(v: unknown): number { const n = Number(v); return Number.isFinite(n) ? n : 0; }

interface Child { store_id: string; store_name: string; msku: string; in_transit: number; wfs: number; non_wfs: number; }
interface Group {
  item_id: string; sku: string; owner: string; is_clearance: number;
  alloc_local: number; alloc_po: number;
  in_transit_sum: number; wfs_sum: number; non_wfs_sum: number; inv_qty: number;
  children: Child[];
}

router.get("/overview", async (req: Request, res: Response): Promise<void> => {
  const fStore = txt(req.query.store);
  const fOwner = txt(req.query.owner);
  const fKw = txt(req.query.kw).toLowerCase();
  const db = await getDb();
  try {
    // 店铺名三层兜底（同现网 PMC）：store_id → 名称
    const nameMap = new Map<string, string>();
    const mergeNames = (rows: mysql.RowDataPacket[]): void => {
      for (const r of rows) { const id = txt(r.store_id); const nm = txt(r.store_name); if (id && nm && !nameMap.has(id)) nameMap.set(id, nm); }
    };
    const [n1] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, MAX(NULLIF(TRIM(store_name),'')) AS store_name FROM dim_product WHERE store_id IS NOT NULL AND store_id<>'' GROUP BY store_id`);
    mergeNames(n1);
    try {
      const [n2] = await db.query<mysql.RowDataPacket[]>(
        `SELECT store_id, store_name FROM dim_store_config WHERE store_id IS NOT NULL AND store_id<>''`);
      mergeNames(n2);
    } catch { /* dim_store_config 缺失时忽略 */ }
    // 1) 在营 listing 明细（store×item×msku），排除 CS测品/虚拟品，带清货期标记
    const [listings] = await db.query<mysql.RowDataPacket[]>(
      `SELECT p.store_id,
              COALESCE(NULLIF(TRIM(p.store_name),''),'') AS store_name,
              p.item_id,
              COALESCE(NULLIF(TRIM(p.msku),''),'') AS msku,
              COALESCE(NULLIF(TRIM(p.sku),''),'') AS sku,
              COALESCE(NULLIF(TRIM(p.owner),''),'') AS owner,
              CASE WHEN COALESCE(NULLIF(TRIM(p.manual_lifecycle_stage),''), bs.lifecycle_stage, bs.system_lifecycle_stage,'')='清货期'
                   THEN 1 ELSE 0 END AS is_clearance
       FROM dim_product p
       LEFT JOIN dim_product_business_state bs
         ON bs.platform=p.platform AND bs.store_id=p.store_id AND bs.item_id=p.item_id
        AND COALESCE(bs.msku,'')=COALESCE(p.msku,'')
        AND bs.stat_date=(SELECT MAX(stat_date) FROM dim_product_business_state WHERE platform='walmart')
       WHERE p.platform='walmart'
         AND COALESCE(p.product_management_status,'active')='active'
         AND p.item_id IS NOT NULL AND p.item_id<>''
         AND p.msku IS NOT NULL AND TRIM(p.msku)<>''
         AND p.msku NOT LIKE 'CS%'`);

    // 2) 最新库存快照：WFS / 非WFS（store×item×msku）
    const [inv] = await db.query<mysql.RowDataPacket[]>(
      `SELECT inv.store_id, inv.item_id, inv.msku,
              COALESCE(inv.wfs_available_stock,0) AS wfs,
              COALESCE(inv.non_wfs_available_stock,0) AS non_wfs
       FROM fact_inventory_daily inv
       JOIN (SELECT store_id,item_id,msku,MAX(snapshot_date) AS d FROM fact_inventory_daily
             WHERE platform='walmart' GROUP BY store_id,item_id,msku) li
         ON li.store_id=inv.store_id AND li.item_id=inv.item_id AND li.msku=inv.msku AND li.d=inv.snapshot_date
       WHERE inv.platform='walmart'`);
    const invMap = new Map<string, { wfs: number; non_wfs: number }>();
    for (const r of inv) invMap.set(`${txt(r.store_id)}|${txt(r.item_id)}|${txt(r.msku)}`, { wfs: num(r.wfs), non_wfs: num(r.non_wfs) });

    // 3) 在途（未完结货件 Σ max(已发货-签收,0)，2026-08-12需求方定稿：取已发货数不取申报量——
    //    幽灵货件(状态已发货但发货数=0)申报量曾虚增在途12.3%，改用发货数后天然归零，部分发货也按实际发出算）
    const transitMap = new Map<string, number>();
    try {
      const [tr] = await db.query<mysql.RowDataPacket[]>(
        `SELECT s.store_id, si.msku,
                SUM(GREATEST(COALESCE(si.shipments_num,0)-COALESCE(si.received_num,0),0)) AS in_transit
         FROM fact_wfs_shipment s
         JOIN fact_wfs_shipment_item si
           ON si.platform=s.platform AND si.store_id=s.store_id AND si.shipment_id=s.shipment_id
         WHERE s.platform='walmart' AND s.to_closed_time IS NULL AND s.to_cancelled_time IS NULL
         GROUP BY s.store_id, si.msku`);
      for (const r of tr) transitMap.set(`${txt(r.store_id)}|${txt(r.msku)}`, num(r.in_transit));
    } catch { /* 货件表未建时忽略 */ }

    // 4) 本地仓库存池（按SKU，最新快照）
    const localMap = new Map<string, number>();
    try {
      const [loc] = await db.query<mysql.RowDataPacket[]>(
        `SELECT sku, SUM(COALESCE(qty,0)) AS qty FROM fact_local_inventory_daily
         WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM fact_local_inventory_daily) GROUP BY sku`);
      for (const r of loc) localMap.set(txt(r.sku), num(r.qty));
    } catch { /* 本地仓表未建/未同步时忽略 */ }

    // 5) 采购在途池（按SKU）。领星 quantity_receive 实为"待收/未到货量"(全部到货单=0、未到货单=全额)，故采购在途=SUM(quantity_receive)，排作废+90天防陈年脏单。2026-08-03 核对领星修正(原 计划-已收 口径反了)
    const poMap = new Map<string, number>();
    try {
      const [po] = await db.query<mysql.RowDataPacket[]>(
        `SELECT i.sku, SUM(COALESCE(i.quantity_receive,0)) AS open_qty
         FROM fact_purchase_order_item i
         JOIN fact_purchase_order o ON o.order_sn=i.order_sn
         WHERE o.status_text NOT LIKE '%作废%'
           AND (NULLIF(TRIM(i.expect_arrive_time),'') IS NULL
                OR i.expect_arrive_time >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 90 DAY), '%Y-%m-%d'))
         GROUP BY i.sku`);
      for (const r of po) poMap.set(txt(r.sku), num(r.open_qty));
    } catch { /* 采购表未建时忽略 */ }

    // 6) 近30天销量（按 item_id），用于 SKU池分摊权重
    const sales30 = new Map<string, number>();
    try {
      const [sl] = await db.query<mysql.RowDataPacket[]>(
        `SELECT item_id, SUM(COALESCE(sales_qty,0)) AS qty FROM fact_sales_daily
         WHERE platform='walmart'
           AND stat_date >= DATE_SUB((SELECT MAX(stat_date) FROM fact_sales_daily WHERE platform='walmart'), INTERVAL 29 DAY)
         GROUP BY item_id`);
      for (const r of sl) sales30.set(txt(r.item_id), num(r.qty));
    } catch { /* 销量表异常时忽略（分摊退化为均摊） */ }

    // ---- 组装：先按 item_id 建组与子行 ----
    const groups = new Map<string, Group>();
    const storeNameSet = new Set<string>();
    const skuItems = new Map<string, Set<string>>(); // sku → item_id 集合（用于分摊）
    for (const r of listings) {
      const sku = txt(r.sku);
      if (EXCLUDE_SKUS.has(sku)) continue;
      const itemId = txt(r.item_id);
      const storeId = txt(r.store_id);
      const msku = txt(r.msku);
      if (sku) {
        if (!skuItems.has(sku)) skuItems.set(sku, new Set());
        skuItems.get(sku)!.add(itemId);
      }
      if (!groups.has(itemId)) {
        groups.set(itemId, {
          item_id: itemId, sku, owner: txt(r.owner), is_clearance: num(r.is_clearance),
          alloc_local: 0, alloc_po: 0, in_transit_sum: 0, wfs_sum: 0, non_wfs_sum: 0, inv_qty: 0, children: [],
        });
      }
      const g = groups.get(itemId)!;
      if (!g.owner && txt(r.owner)) g.owner = txt(r.owner);
      if (num(r.is_clearance) === 1) g.is_clearance = 1;
      const iv = invMap.get(`${storeId}|${itemId}|${msku}`) ?? { wfs: 0, non_wfs: 0 };
      const transit = transitMap.get(`${storeId}|${msku}`) ?? 0;
      const storeName = nameMap.get(storeId) || txt(r.store_name);
      if (storeName) storeNameSet.add(storeName);
      g.children.push({ store_id: storeId, store_name: storeName, msku, in_transit: transit, wfs: iv.wfs, non_wfs: iv.non_wfs });
      g.in_transit_sum += transit;
      g.wfs_sum += iv.wfs;
      g.non_wfs_sum += iv.non_wfs;
    }

    // ---- SKU池（本地仓/采购）按近30天销量分摊到各 item_id ----
    const allocPool = (poolMap: Map<string, number>, pick: (g: Group, v: number) => void): void => {
      for (const [sku, items] of skuItems.entries()) {
        const pool = poolMap.get(sku) ?? 0;
        if (!pool) continue;
        const ids = Array.from(items);
        const weights = ids.map((id) => sales30.get(id) ?? 0);
        const wsum = weights.reduce((a, b) => a + b, 0);
        let assigned = 0;
        ids.forEach((id, idx) => {
          const g = groups.get(id);
          if (!g) return;
          const share = wsum > 0 ? pool * (weights[idx] / wsum) : pool / ids.length;
          const v = idx === ids.length - 1 ? pool - assigned : Math.round(share); // 末位吸收取整余差
          assigned += (idx === ids.length - 1) ? 0 : Math.round(share);
          pick(g, Math.max(v, 0));
        });
      }
    };
    allocPool(localMap, (g, v) => { g.alloc_local += v; });
    allocPool(poMap, (g, v) => { g.alloc_po += v; });

    // ---- 库存数量 + 过滤 ----
    let out = Array.from(groups.values());
    for (const g of out) g.inv_qty = g.alloc_local + g.alloc_po + g.in_transit_sum + g.wfs_sum;
    if (fStore) out = out.filter((g) => g.children.some((c) => c.store_name === fStore));
    if (fOwner) out = out.filter((g) => g.owner === fOwner);
    if (fKw) out = out.filter((g) =>
      g.item_id.toLowerCase().includes(fKw) || g.sku.toLowerCase().includes(fKw) ||
      g.children.some((c) => c.msku.toLowerCase().includes(fKw)));
    out.sort((a, b) => b.inv_qty - a.inv_qty);

    // 筛选选项 + KPI
    const stores = Array.from(storeNameSet).filter(Boolean).sort();
    const owners = Array.from(new Set(listings.map((r) => txt(r.owner)).filter(Boolean))).sort();
    const kpi = {
      item_count: out.length,
      listing_rows: out.reduce((a, g) => a + g.children.length, 0),
      inv_qty_total: out.reduce((a, g) => a + g.inv_qty, 0),
      wfs_total: out.reduce((a, g) => a + g.wfs_sum, 0),
      non_wfs_total: out.reduce((a, g) => a + g.non_wfs_sum, 0),
      in_transit_total: out.reduce((a, g) => a + g.in_transit_sum, 0),
    };

    res.json({ ok: true, groups: out, stores, owners, kpi });
  } catch (e) {
    res.status(500).json({ ok: false, error: e instanceof Error ? e.message : String(e) });
  } finally {
    await db.end().catch(() => {});
  }
});

export default router;
