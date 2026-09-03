/**
 * clearanceCenterRoutes.ts - 清货中心（批②，2026-07-21 v2：其他渠道改SKU维度）
 *
 * 挂载：/api/clearance-center（adminServer，Basic Auth 保护区内）
 * 端点：
 *   GET  /list            自动行（清货期产品实时聚合）+ 手动行（其他渠道SKU台账）+ KPI
 *   GET  /product-lookup  按 sku 查 dim_product（预填 mskus/负责人）
 *   POST /manual-add      添加其他渠道清货（sku+channel 唯一；渠道 亚马逊/希音）
 *   POST /manual-update   更新台账（owner/platform_ref/manual_stock/remark/status）
 *
 * 展示口径（2026-07-21 需求方定稿）：
 *   列=SKU、平台ID；沃尔玛行平台ID=ItemID，亚马逊=ASIN，希音=平台SKC
 *   自动行库存=最新快照；手动行库存=manual_stock 人工维护，日销待批⑤亚马逊销量接入
 * 铁律：只读 DIM/FACT/EVENT + 只写人工台账与审计事件，不碰 dim_product
 */

import { Router, Request, Response } from "express";
import * as mysql from "mysql2/promise";
import { requireAuth, requirePermission, AuthedRequest } from "./authMiddleware";
import { getNotifyTenantToken, resolveActiveMembers, sendTextToTarget } from "./feishuNotify";

const router = Router();

const MANUAL_CHANNELS = new Set(["沃尔玛", "亚马逊", "希音", "TEMU", "TikTok"]); // 2026-07-21 沃尔玛(ItemID)；2026-07-24 加TEMU/TikTok（产品ID=平台商品ID）

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

function txt(v: unknown): string {
  return String(v ?? "").trim();
}

// ── 2026-07-23 本月清货目标（与月度规划同底座 biz_monthly_plan，indicator=清货）────
// 中国时区当月（YYYY-MM）；与月度规划 currentPlanMonth 同口径
function chinaPlanMonth(): string {
  return new Date(Date.now() + 8 * 3600 * 1000).toISOString().slice(0, 7);
}
// 当月起止（end 为下月1日，查询用 stat_date >= start AND stat_date < end）
function chinaMonthRange(month: string): { start: string; end: string } {
  const [y, m] = month.split("-").map(Number);
  const ny = m === 12 ? y + 1 : y;
  const nm = m === 12 ? 1 : m + 1;
  return { start: `${month}-01`, end: `${ny}-${String(nm).padStart(2, "0")}-01` };
}

/** 店铺名三层递补（与待认领/无动作同口径），整店无名保留ID */
async function fetchStoreNames(db: mysql.Connection): Promise<Map<string, string>> {
  const m = new Map<string, string>();
  const merge = (rows: unknown[]): void => {
    for (const r of rows as Array<{ store_id: unknown; store_name: unknown }>) {
      const id = txt(r.store_id);
      const name = txt(r.store_name);
      if (id && name && !m.has(id)) m.set(id, name);
    }
  };
  const [p] = await db.query<mysql.RowDataPacket[]>(
    `SELECT store_id, MAX(NULLIF(TRIM(store_name),'')) AS store_name
     FROM dim_product WHERE store_id IS NOT NULL AND store_id<>'' GROUP BY store_id`);
  merge(p);
  try {
    const [cfg] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, store_name FROM dim_store_config WHERE store_id IS NOT NULL AND store_id<>''`);
    merge(cfg);
  } catch { /* 兜底层失败忽略 */ }
  try {
    const [inv] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, MAX(NULLIF(TRIM(store_name),'')) AS store_name
       FROM fact_inventory_daily WHERE store_id IS NOT NULL AND store_id<>'' GROUP BY store_id`);
    merge(inv);
  } catch { /* 兜底层失败忽略 */ }
  return m;
}

async function auditClearanceCenter(
  db: mysql.Connection,
  args: { sku: string; field: string; oldValue: string; newValue: string; operator: string },
): Promise<void> {
  try {
    await db.query(
      `INSERT INTO biz_event
         (event_date, event_type, platform, store_id, item_id, msku, owner,
          title, reason, severity, status, source_table, source_key, detected_by, extra_json)
       VALUES (CURDATE(), 'clearance_manual_change', 'walmart', '', '', ?, '',
               ?, '', 'info', 'resolved', 'biz_clearance_other_channel', ?, 'admin_ui', CAST(? AS JSON))`,
      [args.sku,
       `${args.field}: ${args.oldValue || "(空)"} → ${args.newValue || "(空)"}`,
       `sku:${args.sku}:${args.field}:${Date.now()}`,
       JSON.stringify({ field: args.field, old: args.oldValue, new: args.newValue, operator: args.operator, at: new Date().toISOString() })],
    );
  } catch (e) {
    console.warn("[清货中心] 审计写入失败（不阻断业务）:", e instanceof Error ? e.message : String(e));
  }
}

interface ClearanceRow {
  row_type: "auto" | "manual";
  manual_id: number | null;
  approval_id?: number | null;   // 待审批行=event_clearance_approval.id；其余不设（页面审批用）
  sku: string;
  mskus: string;
  platform_ref: string;    // 沃尔玛=ItemID / 亚马逊=ASIN / 希音=平台SKC
  channel: string;         // 沃尔玛 / 亚马逊 / 希音
  store_id: string;
  store_name: string;      // 手动行=渠道名
  item_id: string;
  owner: string;
  entered_at: string;
  stock: number;
  inbound: number;
  daily7: number | null;   // 手动行暂无销量源（批⑤），null 显示—
  days_to_clear: number | null;
  remark: string;
  state: "待审批" | "清货中" | "清零待归档" | "其他渠道清货";
  row_key: string;          // 预计清货结束时间的存取键
  expect_end: string;       // 人工选择的预计清货结束时间（YYYY-MM-DD 或空）
  // ── 2026-07-23 本月清货目标 + 清货库存成本 ──
  month_target: number | null;      // 本月清货目标(件)，来自 biz_monthly_plan indicator=清货
  target_updated_by: string;        // 目标最近录入人（biz_monthly_plan.updated_by）
  target_updated_at: string;        // 目标最近更新（MM-DD）
  month_cleared: number | null;     // 本月已清(件) = 当月 fact_sales_daily 销量合计（item级，受T-2滞后影响）
  purchase_cost: number | null;     // 采购成本(¥)，dim_product_cost_config 最新生效
  first_mile_cost: number | null;   // 头程成本(¥)
  stock_cost: number | null;        // 清货库存成本(¥) = (采购+头程)×当前库存；缺成本且库存>0 时为 null
}

router.get("/list", async (req: Request, res: Response): Promise<void> => {
  const fStore = txt(req.query.store);
  const fOwner = txt(req.query.owner);
  const fState = txt(req.query.state);
  const db = await getDb();
  try {
    const storeNames = await fetchStoreNames(db);
    const [autoRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT p.platform, p.store_id,
              COALESCE(MAX(NULLIF(TRIM(p.store_name),'')),'') AS store_name,
              p.item_id,
              SUBSTRING(GROUP_CONCAT(DISTINCT NULLIF(TRIM(p.msku),'') SEPARATOR '/'),1,500) AS mskus,
              COALESCE(MAX(NULLIF(TRIM(p.sku),'')),'') AS sku,
              COALESCE(MAX(NULLIF(TRIM(p.owner),'')),'') AS owner
       FROM dim_product p
       LEFT JOIN dim_product_business_state bs
         ON bs.platform = p.platform AND bs.store_id = p.store_id AND bs.item_id = p.item_id
        AND COALESCE(bs.msku,'') = COALESCE(p.msku,'')
        AND bs.stat_date = (SELECT MAX(stat_date) FROM dim_product_business_state WHERE platform='walmart')
       WHERE p.platform = 'walmart'
         AND COALESCE(p.product_management_status,'active') <> 'archived'
         AND COALESCE(NULLIF(TRIM(p.manual_lifecycle_stage),''), bs.lifecycle_stage, bs.system_lifecycle_stage, '') = '清货期'
       GROUP BY p.platform, p.store_id, p.item_id`,
    );
    const [pendRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT id, platform, store_id, store_name, item_id, mskus, sku, owner,
              DATE_FORMAT(created_at,'%Y-%m-%d') AS entered_at
       FROM event_clearance_approval WHERE status = 'pending'`,
    );
    const [manualRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT id, sku, mskus, owner, channel, platform_ref, manual_stock, remark,
             monthly_target, target_month, target_updated_by,
             DATE_FORMAT(target_updated_at,'%m-%d') AS target_updated_at_s, monthly_cleared,
              DATE_FORMAT(created_at,'%Y-%m-%d') AS entered_at
       FROM biz_clearance_other_channel WHERE status = 'active'`,
    );
    const [enterRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, item_id, DATE_FORMAT(MAX(decided_at),'%Y-%m-%d') AS entered_at
       FROM event_clearance_approval WHERE status IN ('approved','legacy')
       GROUP BY store_id, item_id`,
    );
    const enterMap = new Map(enterRows.map((r) => [`${r.store_id}|${r.item_id}`, String(r.entered_at ?? "")]));
    const [invRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT inv.store_id, inv.item_id,
              SUM(COALESCE(inv.wfs_available_stock,0)) AS wfs,
              SUM(COALESCE(inv.inbound_stock,0)) AS inbound
       FROM fact_inventory_daily inv
       JOIN (SELECT store_id, item_id, msku, MAX(snapshot_date) AS d
             FROM fact_inventory_daily WHERE platform='walmart' GROUP BY store_id, item_id, msku) li
         ON li.store_id = inv.store_id AND li.item_id = inv.item_id AND li.msku = inv.msku
        AND inv.snapshot_date = li.d
       WHERE inv.platform='walmart'
       GROUP BY inv.store_id, inv.item_id`,
    );
    const invMap = new Map(invRows.map((r) => [`${r.store_id}|${r.item_id}`, { wfs: Number(r.wfs ?? 0), inbound: Number(r.inbound ?? 0) }]));
    const [dateRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT DISTINCT DATE_FORMAT(stat_date,'%Y-%m-%d') AS d FROM fact_sales_daily
       WHERE platform='walmart' ORDER BY d DESC LIMIT 7`,
    );
    const dates = dateRows.map((r) => String(r.d));
    const salesMap = new Map<string, number>();
    if (dates.length) {
      const [salesRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT store_id, item_id, SUM(COALESCE(sales_qty,0)) AS qty
         FROM fact_sales_daily
         WHERE platform='walmart' AND stat_date IN (${dates.map(() => "?").join(",")})
         GROUP BY store_id, item_id`,
        dates,
      );
      for (const r of salesRows) salesMap.set(`${r.store_id}|${r.item_id}`, Number(r.qty ?? 0));
    }
    const dayCount = Math.max(dates.length, 1);

    // 预计清货结束时间（人工）
    let expectMap = new Map<string, string>();
    try {
      const [expRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT row_key, DATE_FORMAT(expect_end,'%Y-%m-%d') AS d FROM biz_clearance_expect_date`,
      );
      expectMap = new Map(expRows.map((r) => [String(r.row_key), String(r.d)]));
    } catch { /* 表未建时忽略 */ }

    // ── 2026-07-23 本月清货目标（biz_monthly_plan indicator=清货，与月度规划同一条记录）──
    // 2026-08-03 月份筛选：?month=YYYY-MM，非法/空回退当月（chinaPlanMonth），默认口径不变
    const monthParam = txt(req.query.month);
    const planMonth = /^\d{4}-\d{2}$/.test(monthParam) ? monthParam : chinaPlanMonth();
    const mr = chinaMonthRange(planMonth);
    interface TargetInfo { target: number; updatedBy: string; updatedAt: string; }
    const targetMap = new Map<string, TargetInfo>();
    try {
      const [planRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT store_id, item_id, indicator1_type, indicator1_target,
                indicator2_type, indicator2_target,
                updated_by, DATE_FORMAT(updated_at,'%m-%d') AS updated_at
         FROM biz_monthly_plan
         WHERE plan_month = ? AND platform = 'walmart'`,
        [planMonth],
      );
      for (const r of planRows) {
        const t = String(r.indicator1_type ?? "") === "清货" ? r.indicator1_target
          : String(r.indicator2_type ?? "") === "清货" ? r.indicator2_target : null;
        if (t === null || t === undefined) continue;
        const key = `${r.store_id}|${r.item_id}`;
        if (!targetMap.has(key)) {
          targetMap.set(key, { target: Number(t), updatedBy: txt(r.updated_by), updatedAt: String(r.updated_at ?? "") });
        }
      }
    } catch (e) {
      console.warn("[清货中心] 月目标读取失败（降级为空）:", e instanceof Error ? e.message : String(e));
    }
    // 本月已清(件) = 当月销量合计（item级；T-2滞后为已知口径）
    const clearedMap = new Map<string, number>();
    try {
      const [mRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT store_id, item_id, SUM(COALESCE(sales_qty,0)) AS qty
         FROM fact_sales_daily
         WHERE platform='walmart' AND stat_date >= ? AND stat_date < ?
         GROUP BY store_id, item_id`,
        [mr.start, mr.end],
      );
      for (const r of mRows) clearedMap.set(`${r.store_id}|${r.item_id}`, Number(r.qty ?? 0));
    } catch (e) {
      console.warn("[清货中心] 当月销量读取失败（降级为空）:", e instanceof Error ? e.message : String(e));
    }
    // 2026-07-24 其他渠道本月已清 + 7日日销：读 fact_channel_clearance_sales_daily（按 平台|平台商品ID）
    const channelClearedMap = new Map<string, number>();
    const channelDaily7Map = new Map<string, number>();
    try {
      const [ccRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT platform, platform_ref, SUM(COALESCE(sales_qty, 0)) AS qty
           FROM fact_channel_clearance_sales_daily
          WHERE stat_date >= ? AND stat_date < ?
          GROUP BY platform, platform_ref`,
        [mr.start, mr.end],
      );
      for (const r of ccRows) channelClearedMap.set(`${r.platform}|${txt(r.platform_ref)}`, Number(r.qty ?? 0));
      const [d7Rows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT platform, platform_ref, SUM(COALESCE(sales_qty, 0)) AS qty
           FROM fact_channel_clearance_sales_daily
          WHERE stat_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY) AND stat_date < CURDATE()
          GROUP BY platform, platform_ref`,
      );
      for (const r of d7Rows) channelDaily7Map.set(`${r.platform}|${txt(r.platform_ref)}`, Math.round(Number(r.qty ?? 0) / 7 * 100) / 100);
    } catch (e) {
      console.warn("[清货中心] 其他渠道已清/日销读取失败（降级为空）:", e instanceof Error ? e.message : String(e));
    }
    // 清货库存成本：dim_product_cost_config 最新生效 (采购+头程)，产品管理同源；
    // 当前清货池全单MSKU，按 item 级取最新一条；多MSKU情况取该 item 最新生效行并注释留待细化
    interface CostInfo { purchase: number | null; firstMile: number | null; }
    const costMap = new Map<string, CostInfo>();
    const itemIds = [...new Set([...autoRows, ...pendRows].map((r) => txt((r as Record<string, unknown>).item_id)).filter(Boolean))];
    if (itemIds.length) {
      try {
        const [cRows] = await db.query<mysql.RowDataPacket[]>(
          `SELECT store_id, item_id, purchase_cost, first_mile_shipping_cost,
                  DATE_FORMAT(effective_date,'%Y-%m-%d') AS eff, id
           FROM dim_product_cost_config
           WHERE platform='walmart' AND item_id IN (${itemIds.map(() => "?").join(",")})
             AND (purchase_cost IS NOT NULL OR first_mile_shipping_cost IS NOT NULL)`,
          itemIds,
        );
        // JS 选优：优先 store_id 匹配行，再按 effective_date/id 最新
        const best = new Map<string, { score: number; eff: string; id: number; purchase: number | null; firstMile: number | null }>();
        for (const r of cRows) {
          const itemKeyAll = [`*|${r.item_id}`];
          if (txt(r.store_id)) itemKeyAll.push(`${r.store_id}|${r.item_id}`);
          for (const k of itemKeyAll) {
            const score = k.startsWith("*") ? 0 : 1;
            const cur = best.get(k);
            const cand = {
              score, eff: String(r.eff ?? ""), id: Number(r.id),
              purchase: r.purchase_cost === null ? null : Number(r.purchase_cost),
              firstMile: r.first_mile_shipping_cost === null ? null : Number(r.first_mile_shipping_cost),
            };
            if (!cur || cand.score > cur.score
              || (cand.score === cur.score && (cand.eff > cur.eff || (cand.eff === cur.eff && cand.id > cur.id)))) {
              best.set(k, cand);
            }
          }
        }
        for (const [k, v] of best) costMap.set(k, { purchase: v.purchase, firstMile: v.firstMile });
      } catch (e) {
        console.warn("[清货中心] 成本读取失败（降级为空）:", e instanceof Error ? e.message : String(e));
      }
    }

    const rows: ClearanceRow[] = [];
    const pushAuto = (base: Record<string, unknown>, state: ClearanceRow["state"], enteredAt: string, approvalId: number | null = null): void => {
      const key = `${base.store_id}|${base.item_id}`;
      const inv = invMap.get(key) ?? { wfs: 0, inbound: 0 };
      const daily7 = Math.round((salesMap.get(key) ?? 0) / dayCount * 100) / 100;
      const storeId = txt(base.store_id);
      const rowKey = `auto:${storeId}:${txt(base.item_id)}`;
      // 2026-07-23：月目标/已清/库存成本
      const tInfo = targetMap.get(key);
      const cost = costMap.get(key) ?? costMap.get(`*|${txt(base.item_id)}`) ?? null;
      const unitCost = cost && (cost.purchase !== null || cost.firstMile !== null)
        ? (cost.purchase ?? 0) + (cost.firstMile ?? 0)
        : null;
      const stockCost = inv.wfs <= 0 ? 0 : unitCost === null ? null : Math.round(unitCost * inv.wfs * 100) / 100;
      rows.push({
        row_key: rowKey,
        expect_end: expectMap.get(rowKey) ?? "",
        row_type: "auto",
        manual_id: null,
        approval_id: approvalId,
        sku: txt(base.sku) || "-",
        mskus: txt(base.mskus) || "-",
        platform_ref: txt(base.item_id),
        channel: "沃尔玛",
        store_id: storeId,
        store_name: txt(base.store_name) || storeNames.get(storeId) || storeId,
        item_id: txt(base.item_id),
        owner: txt(base.owner) || "-",
        entered_at: enteredAt,
        stock: inv.wfs,
        inbound: inv.inbound,
        daily7,
        days_to_clear: inv.wfs > 0 && daily7 > 0 ? Math.round(inv.wfs / daily7) : null,
        remark: "",
        state,
        month_target: tInfo ? tInfo.target : null,
        target_updated_by: tInfo ? tInfo.updatedBy : "",
        target_updated_at: tInfo ? tInfo.updatedAt : "",
        month_cleared: clearedMap.get(key) ?? 0,
        purchase_cost: cost ? cost.purchase : null,
        first_mile_cost: cost ? cost.firstMile : null,
        stock_cost: stockCost,
      });
    };

    const pendingSet = new Set(pendRows.map((r) => `${r.store_id}|${r.item_id}`));
    for (const r of pendRows) pushAuto(r, "待审批", `${r.entered_at} 申请`, Number(r.id));
    for (const r of autoRows) {
      if (pendingSet.has(`${r.store_id}|${r.item_id}`)) continue;
      const key = `${r.store_id}|${r.item_id}`;
      const inv = invMap.get(key) ?? { wfs: 0, inbound: 0 };
      pushAuto(r, inv.wfs <= 0 && inv.inbound <= 0 ? "清零待归档" : "清货中", enterMap.get(key) ?? "2026-07-31");
    }
    // 2026-07-24 其他渠道清货库存成本：按 SKU 取 dim_product_cost_config 最新生效（采购+头程），与沃尔玛同源
    const costBySkuMap = new Map<string, { purchase: number | null; firstMile: number | null }>();
    const manualSkuList = [...new Set(manualRows.map((mrx) => txt((mrx as Record<string, unknown>).sku)).filter(Boolean))];
    if (manualSkuList.length) {
      try {
        const [csRows] = await db.query<mysql.RowDataPacket[]>(
          `SELECT sku, purchase_cost, first_mile_shipping_cost, DATE_FORMAT(effective_date,'%Y-%m-%d') AS eff, id
             FROM dim_product_cost_config
            WHERE sku IN (${manualSkuList.map(() => "?").join(",")})
              AND (purchase_cost IS NOT NULL OR first_mile_shipping_cost IS NOT NULL)`,
          manualSkuList,
        );
        const bestSku = new Map<string, { eff: string; id: number; purchase: number | null; firstMile: number | null }>();
        for (const cr of csRows) {
          const k = txt(cr.sku);
          const cand = { eff: String(cr.eff ?? ""), id: Number(cr.id), purchase: cr.purchase_cost === null ? null : Number(cr.purchase_cost), firstMile: cr.first_mile_shipping_cost === null ? null : Number(cr.first_mile_shipping_cost) };
          const cur = bestSku.get(k);
          if (!cur || cand.eff > cur.eff || (cand.eff === cur.eff && cand.id > cur.id)) bestSku.set(k, cand);
        }
        for (const [k, v] of bestSku) costBySkuMap.set(k, { purchase: v.purchase, firstMile: v.firstMile });
      } catch (e) {
        console.warn("[清货中心] 其他渠道成本读取失败（降级为空）:", e instanceof Error ? e.message : String(e));
      }
    }
    for (const r of manualRows) {
      const rowKey = `manual:${txt(r.sku)}:${txt(r.channel)}`;
      const chPlat = txt(r.channel) === "亚马逊" ? "amazon" : txt(r.channel) === "希音" ? "shein" : txt(r.channel) === "TEMU" ? "temu" : txt(r.channel) === "TikTok" ? "tiktok" : "";
      const chRefKey = `${chPlat}|${txt(r.platform_ref)}`;
      const chDaily7 = chPlat ? (channelDaily7Map.get(chRefKey) ?? 0) : 0;
      const chStock = Number(r.manual_stock ?? 0);
      const chCost = costBySkuMap.get(txt(r.sku)) ?? null;
      const chUnit = chCost && (chCost.purchase !== null || chCost.firstMile !== null) ? (chCost.purchase ?? 0) + (chCost.firstMile ?? 0) : null;
      rows.push({
        row_key: rowKey,
        expect_end: expectMap.get(rowKey) ?? "",
        row_type: "manual",
        manual_id: Number(r.id),
        sku: txt(r.sku),
        mskus: txt(r.mskus) || "-",
        platform_ref: txt(r.platform_ref),
        channel: txt(r.channel),
        store_id: "",
        store_name: txt(r.channel),
        item_id: "",
        owner: txt(r.owner) || "-",
        entered_at: `${r.entered_at} 手动`,
        stock: chStock,
        inbound: 0,
        daily7: chPlat ? chDaily7 : null,
        days_to_clear: chPlat && chStock > 0 && chDaily7 > 0 ? Math.round(chStock / chDaily7) : null,
        remark: txt(r.remark),
        state: "其他渠道清货",
        month_target: txt(r.target_month) === planMonth && r.monthly_target !== null ? Number(r.monthly_target) : null,
        target_updated_by: txt(r.target_month) === planMonth ? txt(r.target_updated_by) : "",
        target_updated_at: txt(r.target_month) === planMonth ? txt(r.target_updated_at_s) : "",
        month_cleared: chPlat
          ? (channelClearedMap.get(chRefKey) ?? 0)
          : (txt(r.target_month) === planMonth && r.monthly_cleared !== null ? Number(r.monthly_cleared) : null),
        purchase_cost: chCost ? chCost.purchase : null,
        first_mile_cost: chCost ? chCost.firstMile : null,
        stock_cost: chStock <= 0 ? 0 : chUnit === null ? null : Math.round(chUnit * chStock * 100) / 100,
      });
    }

    // 2026-07-23：月目标/库存成本 KPI 口径 = 清货池（清货中+清零待归档），待审批未入池不计
    const poolRows = rows.filter((r) => r.state === "清货中" || r.state === "清零待归档");
    const targetRows = poolRows.filter((r) => r.month_target !== null);
    const kpi = {
      clearing: rows.filter((r) => r.state === "清货中").length,
      pending: rows.filter((r) => r.state === "待审批").length,
      cleared: rows.filter((r) => r.state === "清零待归档").length,
      other_channel: rows.filter((r) => r.state === "其他渠道清货").length,
      friday_due: rows.filter((r) => r.state === "清货中" && r.days_to_clear !== null && r.days_to_clear <= 60).length,
      month_target_total: targetRows.reduce((s, r) => s + (r.month_target ?? 0), 0),
      month_cleared_on_target: targetRows.reduce((s, r) => s + (r.month_cleared ?? 0), 0),
      no_target_count: poolRows.length - targetRows.length,
      stock_cost_total: Math.round(poolRows.reduce((s, r) => s + (r.stock_cost ?? 0), 0) * 100) / 100,
      cost_missing_count: poolRows.filter((r) => r.stock > 0 && r.stock_cost === null).length,
    };

    let out = rows;
    if (fStore) out = out.filter((r) => r.store_name === fStore || r.store_id === fStore);
    if (fOwner) out = out.filter((r) => r.owner === fOwner);
    if (fState) out = out.filter((r) => r.state === fState);
    out.sort((a, b) => a.state.localeCompare(b.state, "zh") || a.owner.localeCompare(b.owner, "zh") || a.sku.localeCompare(b.sku));

    // 2026-08-03 月份下拉：有清货计划数据的月 ∪ 当月 ∪ 所选月；倒序
    let availableMonths: string[] = [];
    try {
      const [amRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT DISTINCT plan_month FROM biz_monthly_plan
          WHERE platform='walmart' AND ('清货' IN (indicator1_type, indicator2_type))`,
      );
      availableMonths = amRows.map((r) => String(r.plan_month)).filter(Boolean);
    } catch (e) {
      console.warn('[清货中心] 月份列表读取失败（降级为空）:', e instanceof Error ? e.message : String(e));
    }
    availableMonths = [...new Set([chinaPlanMonth(), planMonth, ...availableMonths])].sort().reverse();
    // 2026-08-03 §1 同步时间：库存最新快照日
    let syncTime = '';
    try {
      const [stRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT DATE_FORMAT(MAX(snapshot_date),'%Y-%m-%d') AS t FROM fact_inventory_daily WHERE platform='walmart'`,
      );
      syncTime = String(stRows[0]?.t ?? '');
    } catch { /* 忽略 */ }

    res.json({
      ok: true,
      kpi,
      plan_month: planMonth,
      available_months: availableMonths,
      sync_time: syncTime,
      total: out.length,
      sales_dates: dates,
      stores: [...new Set(rows.filter((r) => r.row_type === "auto").map((r) => r.store_name).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh")),
      owners: [...new Set(rows.map((r) => r.owner).filter((o) => o && o !== "-"))].sort((a, b) => a.localeCompare(b, "zh")),
      rows: out,
    });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end().catch(() => {});
  }
});

// 2026-07-21 需求方：预计清货结束时间（人工选择，逐行维护）
router.post("/expect-date", async (req: Request, res: Response): Promise<void> => {
  const rowKey = txt(req.body?.row_key);
  const expectEnd = txt(req.body?.expect_end);
  const operator = txt((req as AuthedRequest).user?.username) || txt(req.body?.operator_name) || "admin_ui";
  if (!rowKey) { res.status(400).json({ error: "缺少 row_key" }); return; }
  if (expectEnd && !/^\d{4}-\d{2}-\d{2}$/.test(expectEnd)) {
    res.status(400).json({ error: "expect_end 格式须为 YYYY-MM-DD 或留空清除" });
    return;
  }
  const db = await getDb();
  try {
    if (expectEnd) {
      await db.query(
        `INSERT INTO biz_clearance_expect_date (row_key, expect_end, updated_by)
         VALUES (?, ?, ?)
         ON DUPLICATE KEY UPDATE expect_end = VALUES(expect_end), updated_by = VALUES(updated_by)`,
        [rowKey, expectEnd, operator],
      );
    } else {
      await db.query(`DELETE FROM biz_clearance_expect_date WHERE row_key = ?`, [rowKey]);
    }
    await auditClearanceCenter(db, {
      sku: rowKey, field: "expect_end", oldValue: "", newValue: expectEnd || "(清除)", operator,
    });
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end().catch(() => {});
  }
});

// 2026-07-21 需求方：添加表单负责人改下拉选择（在营产品负责人去重全集）
router.get("/owners", async (_req: Request, res: Response): Promise<void> => {
  const db = await getDb();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT DISTINCT TRIM(owner) AS owner FROM dim_product
       WHERE owner IS NOT NULL AND TRIM(owner) <> '' AND TRIM(owner) <> '未分配'
       ORDER BY owner`,
    );
    res.json({ ok: true, owners: rows.map((r) => String(r.owner)) });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end().catch(() => {});
  }
});

router.get("/product-lookup", async (req: Request, res: Response): Promise<void> => {
  const sku = txt(req.query.sku);
  if (!sku) { res.status(400).json({ error: "缺少 sku" }); return; }
  const db = await getDb();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT sku,
              SUBSTRING(GROUP_CONCAT(DISTINCT NULLIF(TRIM(msku),'') SEPARATOR '/'),1,500) AS mskus,
              COALESCE(MAX(NULLIF(TRIM(owner),'')),'') AS owner,
              COUNT(DISTINCT item_id) AS item_count
       FROM dim_product WHERE platform='walmart' AND sku = ?
       GROUP BY sku`,
      [sku],
    );
    res.json({ ok: true, matches: rows });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end().catch(() => {});
  }
});

router.post("/manual-add", async (req: Request, res: Response): Promise<void> => {
  const sku = txt(req.body?.sku);
  const owner = txt(req.body?.owner);
  const channel = txt(req.body?.channel);
  const platformRef = txt(req.body?.platform_ref);
  const manualStock = Number(req.body?.manual_stock ?? 0);
  const remark = txt(req.body?.remark);
  const operator = txt((req as AuthedRequest).user?.username) || txt(req.body?.operator_name) || "admin_ui";
  if (!sku || !owner || !channel || !platformRef) {
    res.status(400).json({ error: "sku / 负责人 / 渠道 / 平台识别号 必填" });
    return;
  }
  if (!MANUAL_CHANNELS.has(channel)) {
    res.status(400).json({ error: "渠道只允许：亚马逊 / 希音" });
    return;
  }
  if (!Number.isFinite(manualStock) || manualStock < 0) {
    res.status(400).json({ error: "库存数量必须为非负整数" });
    return;
  }
  const db = await getDb();
  try {
    const [prodRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT SUBSTRING(GROUP_CONCAT(DISTINCT NULLIF(TRIM(msku),'') SEPARATOR '/'),1,500) AS mskus
       FROM dim_product WHERE platform='walmart' AND sku = ?`,
      [sku],
    );
    const mskus = txt(prodRows[0]?.mskus);
    const [dupRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT id, status FROM biz_clearance_other_channel WHERE sku = ? AND channel = ? LIMIT 1`,
      [sku, channel],
    );
    if (dupRows.length && dupRows[0].status === "active") {
      res.status(409).json({ error: `该 SKU 已在「${channel}」清货台账中` });
      return;
    }
    if (dupRows.length) {
      await db.query(
        `UPDATE biz_clearance_other_channel
         SET status='active', owner=?, platform_ref=?, manual_stock=?, remark=?, added_by=?, mskus=?
         WHERE id=?`,
        [owner, platformRef, Math.round(manualStock), remark, operator, mskus, dupRows[0].id],
      );
    } else {
      await db.query(
        `INSERT INTO biz_clearance_other_channel
           (sku, mskus, owner, channel, platform_ref, manual_stock, status, added_by, remark)
         VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)`,
        [sku, mskus, owner, channel, platformRef, Math.round(manualStock), operator, remark],
      );
    }
    await auditClearanceCenter(db, {
      sku, field: "other_channel_add", oldValue: "", newValue: `${channel}/${platformRef}/库存${Math.round(manualStock)}`, operator,
    });
    res.json({ ok: true, product_found: !!mskus });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end().catch(() => {});
  }
});

router.post("/manual-update", async (req: Request, res: Response): Promise<void> => {
  const id = Number(req.body?.id ?? 0);
  const operator = txt((req as AuthedRequest).user?.username) || txt(req.body?.operator_name) || "admin_ui";
  const nextStatus = txt(req.body?.status);
  const owner = req.body?.owner === undefined ? null : txt(req.body?.owner);
  const platformRef = req.body?.platform_ref === undefined ? null : txt(req.body?.platform_ref);
  const manualStock = req.body?.manual_stock === undefined ? null : Number(req.body?.manual_stock);
  const remark = req.body?.remark === undefined ? null : txt(req.body?.remark);
  if (!id) { res.status(400).json({ error: "缺少 id" }); return; }
  if (nextStatus && !["active", "done", "removed"].includes(nextStatus)) {
    res.status(400).json({ error: "status 只允许 active/done/removed" });
    return;
  }
  if (owner !== null && !owner) { res.status(400).json({ error: "负责人不允许清空" }); return; }
  if (platformRef !== null && !platformRef) { res.status(400).json({ error: "平台识别号不允许清空" }); return; }
  if (manualStock !== null && (!Number.isFinite(manualStock) || manualStock < 0)) {
    res.status(400).json({ error: "库存数量必须为非负整数" });
    return;
  }
  const db = await getDb();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT sku, channel, status, manual_stock FROM biz_clearance_other_channel WHERE id=? LIMIT 1`, [id],
    );
    if (!rows.length) { res.status(404).json({ error: "台账行不存在" }); return; }
    const sets: string[] = [];
    const params: unknown[] = [];
    if (nextStatus) { sets.push("status=?"); params.push(nextStatus); }
    if (owner !== null) { sets.push("owner=?"); params.push(owner); }
    if (platformRef !== null) { sets.push("platform_ref=?"); params.push(platformRef); }
    if (manualStock !== null) { sets.push("manual_stock=?"); params.push(Math.round(manualStock)); }
    if (remark !== null) { sets.push("remark=?"); params.push(remark); }
    if (!sets.length) { res.status(400).json({ error: "没有可更新的字段" }); return; }
    params.push(id);
    await db.query(`UPDATE biz_clearance_other_channel SET ${sets.join(", ")} WHERE id=?`, params);
    await auditClearanceCenter(db, {
      sku: txt(rows[0].sku), field: "other_channel_update",
      oldValue: `${rows[0].status}/库存${rows[0].manual_stock}`,
      newValue: `${nextStatus || rows[0].status}/库存${manualStock ?? rows[0].manual_stock}`,
      operator,
    });
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end().catch(() => {});
  }
});

// ── 2026-07-23 本月清货目标录入（写月度规划同底座 biz_monthly_plan，indicator=清货≥件）──
// 槽位保护：已有清货指标→更新；否则写空槽；两槽被其他指标占满→409 不写。
// 绝不覆盖非清货指标、不改 target_sales_amount/target_gross_profit/deadline/note 等其他人工字段。
// 2026-07-23 批3c：核心逻辑抽为 applyMonthlyTarget，单条录入与批量导入共用同一套槽位保护。
async function applyMonthlyTarget(
  db: mysql.Connection,
  storeId: string, itemId: string, target: number, operator: string,
): Promise<{ ok: true; note: string } | { ok: false; status: number; error: string }> {
  const planMonth = chinaPlanMonth();
  // 同 item 可能存在多条不同 msku 的规划行（uk 含 msku）；优先取已带清货指标的行，其次最早的行
  const [planRows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT id, msku, owner, indicator1_type, indicator2_type
     FROM biz_monthly_plan
     WHERE plan_month = ? AND platform = 'walmart' AND store_id = ? AND item_id = ?
     ORDER BY id`,
    [planMonth, storeId, itemId],
  );
  const withClear = planRows.find((r) =>
    String(r.indicator1_type ?? "") === "清货" || String(r.indicator2_type ?? "") === "清货");
  const hit = withClear ?? planRows[0];
  if (hit) {
    const i1 = String(hit.indicator1_type ?? "");
    const i2 = String(hit.indicator2_type ?? "");
    let slotSql: string;
    if (i1 === "清货") slotSql = "indicator1_type = '清货', indicator1_target = ?";
    else if (i2 === "清货") slotSql = "indicator2_type = '清货', indicator2_target = ?";
    else if (!i1) slotSql = "indicator1_type = '清货', indicator1_target = ?";
    else if (!i2) slotSql = "indicator2_type = '清货', indicator2_target = ?";
    else {
      return { ok: false, status: 409, error: `该产品本月两个指标已被「${i1}/${i2}」占用，请先到月度规划调整后再录清货目标` };
    }
    // 写清货指标即视为有优化动作，normal_operation 置 0；不动其他人工字段
    await db.query(
      `UPDATE biz_monthly_plan SET ${slotSql}, normal_operation = 0, updated_by = ? WHERE id = ?`,
      [target, operator, hit.id],
    );
    return { ok: true, note: i1 === "清货" || i2 === "清货" ? "更新清货目标" : "写入空指标槽" };
  }
  // 新建行：owner/msku 取 dim_product，msku 用月度规划同口径聚合串（ORDER BY msku / 截120）
  const [dimRows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT COALESCE(MAX(NULLIF(TRIM(owner),'')),'') AS owner,
            COALESCE(SUBSTRING(GROUP_CONCAT(DISTINCT NULLIF(TRIM(msku),'') ORDER BY msku SEPARATOR '/'),1,120),'') AS mskus
     FROM dim_product
     WHERE platform = 'walmart' AND store_id = ? AND item_id = ?`,
    [storeId, itemId],
  );
  const dim = dimRows[0];
  if (!dim || (!txt(dim.owner) && !txt(dim.mskus))) {
    return { ok: false, status: 404, error: "产品不存在（dim_product 未命中）" };
  }
  await db.query(
    `INSERT INTO biz_monthly_plan
       (plan_month, platform, store_id, item_id, msku, owner,
        indicator1_type, indicator1_target, normal_operation, created_by, updated_by)
     VALUES (?, 'walmart', ?, ?, ?, ?, '清货', ?, 0, ?, ?)`,
    [planMonth, storeId, itemId, txt(dim.mskus), txt(dim.owner) || "未分配", target, operator, operator],
  );
  return { ok: true, note: "新建规划行" };
}

router.post("/monthly-target", requireAuth, async (req: Request, res: Response): Promise<void> => {
  // M5a（2026-08）：清货目标仅超管（林翔/陈佳聪）可写，运营只读（运营改到『目标管理』填报）
  if (!(req as AuthedRequest).user?.isSuperadmin) { res.status(403).json({ error: "仅超管可编辑清货目标（当前为 林翔 / 陈佳聪）；运营请到『目标管理』填报" }); return; }
  const storeId = txt(req.body?.store_id);
  const itemId = txt(req.body?.item_id);
  const operator = txt((req as AuthedRequest).user?.username) || txt(req.body?.operator_name) || "admin_ui";
  const targetRaw = Number(req.body?.target_qty);
  if (!storeId || !itemId) { res.status(400).json({ error: "缺少 store_id / item_id" }); return; }
  if (!Number.isFinite(targetRaw) || targetRaw < 1 || targetRaw > 99999999) {
    res.status(400).json({ error: "目标件数必须为 1~99999999 的数字" });
    return;
  }
  const target = Math.round(targetRaw);
  const planMonth = chinaPlanMonth();
  const db = await getDb();
  try {
    const r = await applyMonthlyTarget(db, storeId, itemId, target, operator);
    if (!r.ok) { res.status(r.status).json({ error: r.error }); return; }
    await auditClearanceCenter(db, {
      sku: `${storeId}|${itemId}`, field: "monthly_target",
      oldValue: r.note, newValue: `${planMonth} 清货目标=${target}件`, operator,
    });
    res.json({ ok: true, plan_month: planMonth, target });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end().catch(() => {});
  }
});

// ── 2026-07-23 批3c 批量导入（CSV → 前端解析 → JSON 行数组；单次≤1000行）──
// 导入=覆盖式 upsert：本月目标按 ItemID 匹配（复用 applyMonthlyTarget 槽位保护）；
// 其他渠道按 SKU+渠道 匹配，已存在覆盖更新，不存在新增。每次导入写 1 条汇总审计。
const IMPORT_MAX_ROWS = 1000;

// ── POST /clearance-center/template-xlsx  批量导入模板（xlsx；2026-07-24 拍板）──
// target：按负责人预填其清货产品清单（产品ID/店铺ID/店铺名称/负责人/本月目标件数/本月已清）。
// other：空白模板100行，负责人列预填所选负责人，负责人/渠道两列为单元格下拉（数据验证）。
router.post("/template-xlsx", async (req: Request, res: Response): Promise<void> => {
  try {
    const tplType = txt(req.body?.type);
    const owner = txt(req.body?.owner);
    if (!owner || (tplType !== "target" && tplType !== "other")) {
      res.status(400).json({ error: "type(target/other)/owner 必填" }); return;
    }
    const { Workbook } = await import("exceljs");
    const wb = new Workbook();
    let fname = "";
    if (tplType === "target") {
      const rows = Array.isArray(req.body?.rows) ? (req.body.rows as Array<Array<string | number | null>>) : [];
      if (rows.length === 0 || rows.length > 1000) { res.status(400).json({ error: "rows 数量需为 1~1000" }); return; }
      const ws = wb.addWorksheet("清货目标");
      ws.addRow(["渠道(勿改)", "产品ID(勿改)", "店铺ID(勿改)", "店铺/渠道名(参考)", "SKU(勿改)", "负责人(勿改)", "本月目标件数(必填)", "本月已清(其他渠道可填/沃尔玛参考)"]);
      ws.getRow(1).font = { bold: true };
      ws.views = [{ state: "frozen", ySplit: 1 }];
      [10, 16, 20, 22, 14, 12, 18, 20].forEach((w, i) => { ws.getColumn(i + 1).width = w; });
      for (const r of rows) ws.addRow((r ?? []).map((v) => (v === null || v === undefined ? "" : v)));
      fname = `清货目标导入模板_${owner}.xlsx`;
    } else {
      const ownersList = Array.isArray(req.body?.owners)
        ? (req.body.owners as unknown[]).map((o) => txt(o)).filter(Boolean) : [];
      const ws = wb.addWorksheet("其他渠道清货");
      ws.addRow(["产品SKU", "负责人", "渠道(沃尔玛/亚马逊/希音/TEMU/TikTok)", "产品ID(必填:沃尔玛ItemID/亚马逊ASIN/希音SKC/TEMU=SKU ID/TikTok商品ID)", "库存数量(选填)", "备注(选填)"]);
      ws.getRow(1).font = { bold: true };
      ws.views = [{ state: "frozen", ySplit: 1 }];
      [16, 12, 22, 26, 14, 20].forEach((w, i) => { ws.getColumn(i + 1).width = w; });
      const BLANK_ROWS = 100;
      for (let i = 0; i < BLANK_ROWS; i++) ws.addRow(["", owner, "", "", "", ""]);
      const ownerListStr = ownersList.join(",");
      const ownerFormula = ownerListStr && ownerListStr.length <= 250 ? `"${ownerListStr}"` : `"${owner}"`;
      for (let i = 2; i <= BLANK_ROWS + 1; i++) {
        ws.getCell(`B${i}`).dataValidation = { type: "list", allowBlank: true, formulae: [ownerFormula] };
        ws.getCell(`C${i}`).dataValidation = { type: "list", allowBlank: true, formulae: ['"沃尔玛,亚马逊,希音,TEMU,TikTok"'] };
      }
      fname = `其他渠道清货导入模板_${owner}.xlsx`;
    }
    const out = await wb.xlsx.writeBuffer();
    res.setHeader("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
    res.setHeader("Content-Disposition", `attachment; filename*=UTF-8''${encodeURIComponent(fname)}`);
    res.end(Buffer.isBuffer(out) ? out : Buffer.from(out as ArrayBuffer));
  } catch (e: unknown) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  }
});

// ── POST /clearance-center/parse-xlsx  解析导入的 xlsx → grid（前端沿用同一校验链）──
router.post("/parse-xlsx", async (req: Request, res: Response): Promise<void> => {
  try {
    const chunks: Buffer[] = [];
    let size = 0;
    let tooBig = false;
    await new Promise<void>((resolve, reject) => {
      req.on("data", (c: Buffer) => {
        size += c.length;
        if (size > 8 * 1024 * 1024) { tooBig = true; resolve(); return; }
        chunks.push(c);
      });
      req.on("end", () => resolve());
      req.on("error", (e) => reject(e));
    });
    if (tooBig) { res.status(400).json({ error: "文件超过 8MB" }); return; }
    const buf = Buffer.concat(chunks);
    if (buf.length < 4 || buf[0] !== 0x50 || buf[1] !== 0x4b) { res.status(400).json({ error: "不是有效的 xlsx 文件" }); return; }
    const { Workbook } = await import("exceljs");
    const wb = new Workbook();
    await wb.xlsx.load(buf as unknown as ArrayBuffer);
    const ws = wb.worksheets[0];
    if (!ws) { res.status(400).json({ error: "xlsx 中没有工作表" }); return; }
    if (ws.rowCount > 1001) { res.status(400).json({ error: "单次最多 1000 行" }); return; }
    const grid: string[][] = [];
    ws.eachRow({ includeEmpty: false }, (row) => {
      const arr: string[] = [];
      for (let i = 1; i <= 8; i++) arr.push(String(row.getCell(i).text ?? "").trim());
      if (arr.some((c) => c !== "")) grid.push(arr);
    });
    res.json({ grid });
  } catch (e: unknown) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  }
});

// ── POST /clearance-center/manual-target  手工渠道行 目标/已清（人工维护，2026-07-24 产品维度重构）──
router.post("/manual-target", async (req: Request, res: Response): Promise<void> => {
  const manualId = Number(req.body?.manual_id);
  const targetRaw = req.body?.target_qty === undefined || txt(req.body?.target_qty) === "" ? null : Number(req.body?.target_qty);
  const clearedRaw = req.body?.cleared_qty === undefined || txt(req.body?.cleared_qty) === "" ? null : Number(req.body?.cleared_qty);
  const operator = txt((req as AuthedRequest).user?.username) || txt(req.body?.operator_name) || "admin_ui";
  if (!Number.isFinite(manualId) || manualId <= 0) { res.status(400).json({ error: "manual_id 非法" }); return; }
  if (targetRaw === null && clearedRaw === null) { res.status(400).json({ error: "target_qty/cleared_qty 至少填一个" }); return; }
  if (targetRaw !== null && (!Number.isFinite(targetRaw) || targetRaw < 1 || targetRaw > 99999999)) {
    res.status(400).json({ error: "目标件数必须为1~99999999的数字" }); return;
  }
  if (clearedRaw !== null && (!Number.isFinite(clearedRaw) || clearedRaw < 0)) {
    res.status(400).json({ error: "已清件数须为非负数字" }); return;
  }
  const db = await getDb();
  try {
    const [r0] = await db.query<mysql.RowDataPacket[]>(
      `SELECT id FROM biz_clearance_other_channel WHERE id = ? AND status = 'active'`, [manualId]);
    if (!r0.length) { res.status(404).json({ error: "台账行不存在或已结束" }); return; }
    await db.query(
      `UPDATE biz_clearance_other_channel
          SET monthly_target = COALESCE(?, monthly_target), target_month = ?,
              target_updated_by = ?, target_updated_at = NOW(),
              monthly_cleared = COALESCE(?, monthly_cleared)
        WHERE id = ?`,
      [targetRaw === null ? null : Math.round(targetRaw), chinaPlanMonth(), operator,
       clearedRaw === null ? null : Math.round(clearedRaw), manualId],
    );
    res.json({ ok: true, plan_month: chinaPlanMonth() });
  } catch (e: unknown) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally {
    await db.end().catch(() => {});
  }
});

router.post("/import-monthly-target", requireAuth, async (req: Request, res: Response): Promise<void> => {
  // M5a（2026-08）：清货目标导入仅超管（林翔/陈佳聪）可写，运营只读
  if (!(req as AuthedRequest).user?.isSuperadmin) { res.status(403).json({ error: "仅超管可导入清货目标（当前为 林翔 / 陈佳聪）" }); return; }
  // 2026-07-24 需求方拍板：导入必须选负责人（复查校验）；模板按负责人生成含店铺ID可消除跨店歧义
  const importOwner = txt(req.body?.import_owner);
  const operator = txt((req as AuthedRequest).user?.username) || txt(req.body?.operator_name) || (importOwner ? `bulk:${importOwner}` : "admin_ui");
  const rows = Array.isArray(req.body?.rows) ? (req.body.rows as Array<Record<string, unknown>>) : [];
  if (!importOwner) { res.status(400).json({ error: "必须选择导入负责人（import_owner）" }); return; }
  if (!rows.length) { res.status(400).json({ error: "rows 为空" }); return; }
  if (rows.length > IMPORT_MAX_ROWS) { res.status(400).json({ error: `单次最多 ${IMPORT_MAX_ROWS} 行` }); return; }
  const db = await getDb();
  try {
    let success = 0;
    const errors: string[] = [];
    for (let i = 0; i < rows.length; i++) {
            const line = i + 2;
      const itemId = txt(rows[i].item_id);
      const rowOwner = txt(rows[i].owner);
      const rowStoreId = txt(rows[i].store_id);
      const rowChannel = txt(rows[i].channel) || "沃尔玛";
      const rowSku = txt(rows[i].sku);
      const clearedRaw = txt(rows[i].cleared_qty);
      const targetRaw = Number(rows[i].target_qty);
      if (!itemId) { errors.push(`第${line}行: 产品ID 为空`); continue; }
      // 2026-07-24 产品维度重构：亚马逊/希音渠道行 → 目标/已清写台账表（人工维护列）
      if (rowChannel !== "沃尔玛") {
        if (!rowSku) { errors.push(`第${line}行(${itemId}): 渠道行缺少 SKU`); continue; }
        if (rowOwner && rowOwner !== importOwner) {
          errors.push(`第${line}行(${itemId}): 行内负责人「${rowOwner}」与导入负责人「${importOwner}」不符`); continue;
        }
        if (!Number.isFinite(targetRaw) || targetRaw < 1 || targetRaw > 99999999) {
          errors.push(`第${line}行(${itemId}): 目标件数必须为1~99999999的数字`); continue;
        }
        const clearedVal = clearedRaw === "" ? null : Number(clearedRaw);
        if (clearedVal !== null && (!Number.isFinite(clearedVal) || clearedVal < 0)) {
          errors.push(`第${line}行(${itemId}): 已清件数须为非负数字或留空`); continue;
        }
        const [mRows] = await db.query<mysql.RowDataPacket[]>(
          `SELECT id, owner FROM biz_clearance_other_channel WHERE sku = ? AND channel = ? AND status = 'active' LIMIT 1`,
          [rowSku, rowChannel],
        );
        if (!mRows.length) { errors.push(`第${line}行(${itemId}): 台账无该 SKU+渠道 的在清记录`); continue; }
        if (txt(mRows[0].owner) && txt(mRows[0].owner) !== importOwner) {
          errors.push(`第${line}行(${itemId}): 该台账行负责人为「${txt(mRows[0].owner)}」，与导入负责人不符`); continue;
        }
        await db.query(
          `UPDATE biz_clearance_other_channel
              SET monthly_target = ?, target_month = ?, target_updated_by = ?, target_updated_at = NOW(),
                  monthly_cleared = COALESCE(?, monthly_cleared)
            WHERE id = ?`,
          [Math.round(targetRaw), chinaPlanMonth(), operator, clearedVal, mRows[0].id],
        );
        success++;
        continue;
      }
      if (rowOwner && rowOwner !== importOwner) {
        errors.push(`第${line}行(${itemId}): 行内负责人「${rowOwner}」与导入负责人「${importOwner}」不符`); continue;
      }
      if (!Number.isFinite(targetRaw) || targetRaw < 1 || targetRaw > 99999999) {
        errors.push(`第${line}行(${itemId}): 目标件数必须为1~99999999的数字`);
        continue;
      }
      const [stRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT store_id, COALESCE(MAX(NULLIF(TRIM(owner),'')),'') AS owner
           FROM dim_product
          WHERE platform='walmart' AND item_id = ?
            AND COALESCE(product_management_status,'active') <> 'archived'
          GROUP BY store_id`,
        [itemId],
      );
      if (!stRows.length) { errors.push(`第${line}行(${itemId}): 产品不存在或已归档`); continue; }
      let picked = stRows[0];
      if (rowStoreId) {
        const hitStore = stRows.find((s) => txt(s.store_id) === rowStoreId);
        if (!hitStore) { errors.push(`第${line}行(${itemId}): 店铺ID 与产品不匹配（勿改模板店铺ID列）`); continue; }
        picked = hitStore;
      } else if (stRows.length > 1) {
        errors.push(`第${line}行(${itemId}): 产品ID 跨店铺不唯一，请使用按负责人下载的模板（含店铺ID）`); continue;
      }
      const prodOwner = txt(picked.owner);
      if (prodOwner && prodOwner !== importOwner) {
        errors.push(`第${line}行(${itemId}): 该产品负责人为「${prodOwner}」，与导入负责人不符`); continue;
      }
      const r = await applyMonthlyTarget(db, txt(picked.store_id), itemId, Math.round(targetRaw), operator);
      if (r.ok) success++;
      else errors.push(`第${line}行(${itemId}): ${r.error}`);
    }
    await auditClearanceCenter(db, {
      sku: "batch_import", field: "monthly_target_import",
      oldValue: `${rows.length}行`, newValue: `成功${success}/失败${errors.length}`, operator,
    });
    res.json({ ok: true, total: rows.length, success, failed: errors.length, errors: errors.slice(0, 50) });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end().catch(() => {});
  }
});

router.post("/import-other-channel", async (req: Request, res: Response): Promise<void> => {
  // 2026-07-24 需求方拍板：导入必须选负责人，行内负责人必须与之一致（复查校验）
  const importOwner = txt(req.body?.import_owner);
  const operator = txt((req as AuthedRequest).user?.username) || txt(req.body?.operator_name) || (importOwner ? `bulk:${importOwner}` : "admin_ui");
  const rows = Array.isArray(req.body?.rows) ? (req.body.rows as Array<Record<string, unknown>>) : [];
  if (!importOwner) { res.status(400).json({ error: "必须选择导入负责人（import_owner）" }); return; }
  if (!rows.length) { res.status(400).json({ error: "rows 为空" }); return; }
  if (rows.length > IMPORT_MAX_ROWS) { res.status(400).json({ error: `单次最多 ${IMPORT_MAX_ROWS} 行` }); return; }
  const db = await getDb();
  try {
    let success = 0;
    const errors: string[] = [];
    for (let i = 0; i < rows.length; i++) {
      const line = i + 2;
      const sku = txt(rows[i].sku);
      const owner = txt(rows[i].owner);
      const channel = txt(rows[i].channel);
      const platformRef = txt(rows[i].platform_ref);
      const stockRaw = rows[i].manual_stock === undefined || txt(rows[i].manual_stock) === "" ? 0 : Number(rows[i].manual_stock);
      const remark = txt(rows[i].remark);
            if (!sku || !owner || !channel || !platformRef) {
        errors.push(`第${line}行(${sku || "?"}): SKU/负责人/渠道/产品ID 必填`);
        continue;
      }
      if (owner !== importOwner) {
        errors.push(`第${line}行(${sku}): 行内负责人「${owner}」与导入负责人「${importOwner}」不符`);
        continue;
      }
      if (!MANUAL_CHANNELS.has(channel)) { errors.push(`第${line}行(${sku}): 渠道只允许 沃尔玛/亚马逊/希音/TEMU/TikTok`); continue; }
      if (!Number.isFinite(stockRaw) || stockRaw < 0) { errors.push(`第${line}行(${sku}): 库存数量必须为非负整数`); continue; }
      const [prodRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT SUBSTRING(GROUP_CONCAT(DISTINCT NULLIF(TRIM(msku),'') SEPARATOR '/'),1,500) AS mskus
         FROM dim_product WHERE platform='walmart' AND sku = ?`,
        [sku],
      );
      const mskus = txt(prodRows[0]?.mskus);
      const [dupRows] = await db.query<mysql.RowDataPacket[]>(
        `SELECT id FROM biz_clearance_other_channel WHERE sku = ? AND channel = ? LIMIT 1`,
        [sku, channel],
      );
      if (dupRows.length) {
        // 导入语义=覆盖（与手动添加的 409 不同，导入以模板为准刷新台账行并激活）
        await db.query(
          `UPDATE biz_clearance_other_channel
           SET status='active', owner=?, platform_ref=?, manual_stock=?, remark=?, added_by=?, mskus=?
           WHERE id=?`,
          [owner, platformRef, Math.round(stockRaw), remark, operator, mskus, dupRows[0].id],
        );
      } else {
        await db.query(
          `INSERT INTO biz_clearance_other_channel
             (sku, mskus, owner, channel, platform_ref, manual_stock, status, added_by, remark)
           VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)`,
          [sku, mskus, owner, channel, platformRef, Math.round(stockRaw), operator, remark],
        );
      }
      success++;
    }
    await auditClearanceCenter(db, {
      sku: "batch_import", field: "other_channel_import",
      oldValue: `${rows.length}行`, newValue: `成功${success}/失败${errors.length}`, operator,
    });
    res.json({ ok: true, total: rows.length, success, failed: errors.length, errors: errors.slice(0, 50) });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end().catch(() => {});
  }
});

// ── 2026-07-25 清货审批：页面入口（复用飞书卡审批逻辑；鉴权 requirePermission("clearance_approval")，超管绕过）──
// 私信申请人（best-effort，失败只记日志）
function notifyClearanceApplicant(applicant: string, text: string): void {
  setImmediate(async () => {
    try {
      const { targets } = await resolveActiveMembers([applicant]);
      const t = targets.find((x) => x.label === applicant);
      if (!t) { console.log(`[清货审批] 申请人「${applicant}」花名册未命中，跳过私信`); return; }
      const token = await getNotifyTenantToken();
      await sendTextToTarget(token, t, text, true);
    } catch (e) {
      console.log(`[清货审批] 私信申请人失败（忽略）: ${e instanceof Error ? e.message : String(e)}`);
    }
  });
}
async function auditClearanceApproval(db: mysql.Connection, args: { storeId: string; itemId: string; newValue: string; operator: string }): Promise<void> {
  try {
    await db.query(
      `INSERT INTO biz_event
         (event_date, event_type, platform, store_id, item_id, msku, owner,
          title, reason, severity, status, source_table, source_key, detected_by, extra_json)
       VALUES (CURDATE(), 'clearance_approval_web', 'walmart', ?, ?, '', '',
               ?, '', 'info', 'resolved', 'event_clearance_approval', ?, ?, CAST(? AS JSON))`,
      [args.storeId, args.itemId, `清货申请页面审批: ${args.newValue}`,
       `${args.storeId}:${args.itemId}:approval:${Date.now()}`, args.operator,
       JSON.stringify({ result: args.newValue, operator: args.operator, at: new Date().toISOString() })],
    );
  } catch (e) {
    console.warn("[清货审批] 审计写入失败（不阻断）:", e instanceof Error ? e.message : String(e));
  }
}

// POST /approve {id} — 通过：产品进清货期 + 申请 approved + 私信申请人
router.post("/approve", requireAuth, requirePermission("clearance_approval"), async (req: Request, res: Response): Promise<void> => {
  const appId = Number(((req.body ?? {}) as Record<string, unknown>).id ?? 0);
  const approver = txt((req as AuthedRequest).user?.username) || "审批人";
  if (!appId) { res.status(400).json({ error: "缺少 id" }); return; }
  const db = await getDb();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT id, platform, store_id, store_name, item_id, mskus, applicant, status FROM event_clearance_approval WHERE id = ? LIMIT 1`, [appId]);
    const app = rows[0];
    if (!app) { res.status(404).json({ error: `申请 #${appId} 不存在` }); return; }
    if (String(app.status) !== "pending") { res.status(409).json({ error: `该申请已处理（当前 ${app.status}）` }); return; }
    const [msRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT MAX(stat_date) AS d FROM dim_product_business_state WHERE platform = ?`, [String(app.platform)]);
    const maxStat = msRows[0]?.d ?? null;
    await db.beginTransaction();
    try {
      await db.query(
        `UPDATE dim_product p
         LEFT JOIN dim_product_business_state bs
           ON bs.platform = p.platform AND bs.store_id = p.store_id AND bs.item_id = p.item_id
          AND COALESCE(bs.msku,'') = COALESCE(p.msku,'') AND bs.stat_date = ?
         SET p.manual_lifecycle_stage = '清货期', p.manual_lifecycle_by = ?, p.manual_lifecycle_at = NOW(),
             p.manual_lifecycle_system_snapshot = bs.system_lifecycle_stage, p.updated_at = NOW()
         WHERE p.platform = ? AND p.store_id = ? AND p.item_id = ?`,
        [maxStat, `${approver}(页面审批)`, String(app.platform), String(app.store_id), String(app.item_id)]);
      await db.query(
        `UPDATE event_clearance_approval SET status = 'approved', approver = ?, decided_at = NOW() WHERE id = ?`,
        [approver, appId]);
      await db.commit();
    } catch (e) { await db.rollback(); throw e; }
    await auditClearanceApproval(db, { storeId: String(app.store_id), itemId: String(app.item_id), newValue: "审批通过→清货期", operator: approver });
    notifyClearanceApplicant(String(app.applicant),
      `✅ 你提交的清货申请已通过审批：${String(app.store_name)} ｜ ItemID ${String(app.item_id)} ｜ ${String(app.mskus)}\n该产品已进入清货期。审批人：${approver}`);
    // M5b：提示审批人到清货中心设本月清货目标（仅超管可填）
    { const link = (process.env.BUSINESS_REPORT_BASE_URL || "http://42.193.254.170").replace(/\/+$/, "") + "/admin/#/clearance-center";
      notifyClearanceApplicant(approver, `📌 已通过清货：${String(app.store_name)} ｜ ItemID ${String(app.item_id)}。请到清货中心设置本月【清货目标数量】（仅超管可填）：\n${link}`); }
    res.json({ ok: true, id: appId, status: "approved" });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally { await db.end().catch(() => undefined); }
});

// POST /reject {id, reason?} — 驳回：申请 rejected + 私信申请人（理由可空）
router.post("/reject", requireAuth, requirePermission("clearance_approval"), async (req: Request, res: Response): Promise<void> => {
  const body = (req.body ?? {}) as Record<string, unknown>;
  const appId = Number(body.id ?? 0);
  const reason = txt(body.reason);
  const approver = txt((req as AuthedRequest).user?.username) || "审批人";
  if (!appId) { res.status(400).json({ error: "缺少 id" }); return; }
  const db = await getDb();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT id, store_id, store_name, item_id, mskus, applicant, status FROM event_clearance_approval WHERE id = ? LIMIT 1`, [appId]);
    const app = rows[0];
    if (!app) { res.status(404).json({ error: `申请 #${appId} 不存在` }); return; }
    if (String(app.status) !== "pending") { res.status(409).json({ error: `该申请已处理（当前 ${app.status}）` }); return; }
    await db.query(
      `UPDATE event_clearance_approval SET status = 'rejected', approver = ?, reject_reason = ?, decided_at = NOW() WHERE id = ?`,
      [approver, reason, appId]);
    await db.query("COMMIT");
    await auditClearanceApproval(db, { storeId: String(app.store_id), itemId: String(app.item_id), newValue: `驳回${reason ? "：" + reason : ""}`, operator: approver });
    notifyClearanceApplicant(String(app.applicant),
      `❌ 你提交的清货申请被驳回：${String(app.store_name)} ｜ ItemID ${String(app.item_id)} ｜ ${String(app.mskus)}\n${reason ? "理由：" + reason + "\n" : ""}产品生命周期维持原状。审批人：${approver}`);
    res.json({ ok: true, id: appId, status: "rejected" });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally { await db.end().catch(() => undefined); }
});

export default router;
