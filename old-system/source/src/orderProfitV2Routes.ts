/**
 * orderProfitV2Routes.ts — 订单利润V2 一次查询路由（批3a上线，2026-08-18 整改批B修订）
 * 挂载：/api/profit-v2（adminServer 全局 authMiddleware 之内）；nginx location /api/profit-v2/ 已放行。
 *
 * GET /order-profit?from=YYYY-MM-DD&to=YYYY-MM-DD&store_id=
 *   一次请求返回：KPI合计 + 全部聚合行（前端分页/排序/筛选）+ 店铺级未归属广告桶。
 *
 * 口径（需求方拍板链 2026-08-14~18，整改批B新增/修订处标▲）：
 *   行键=店铺+MSKU；销售额=fact_profit_daily.sales_amount(saleStat原口径守P7恒等)。
 *   ▲CS测品(msku LIKE 'CS%')整行剔除：行/合计/KPI/广告分摊全不含（CS广告不入未归属桶，单独计数回报）。
 *   ▲送样单剔除（2026-08-19需求方拍板）：折扣RAW中|折扣|≥商品金额-0.01 的整单判定为送样/0元单，
 *     其销售额与销量从本页整单剔除（不计入正式订单）；小额折扣（沃尔玛补贴/满减，领星数据方向存疑）一律不采用，
 *     促销折扣列与净销售额列已下线。副作用（已拍板接受）：V2销售额低于P7三表恒等基准，差额=送样单金额；
 *     剔除仅覆盖折扣RAW窗口（订单列表接口31天上限），更早送样单无法识别，历史仍含虚增。
 *   广告费=fact_ads_product_daily全类型(SP手动/自动+SB+SV+SEM)；item级按MSKU销售额份额分摊；
 *     未归属→店铺桶（计入合计，SEM命名治理修源头）。
 *   WFS配送费=extra_json.wfs_fee_usd(单件)×销量；佣金=销售额×(CN2501/CN2502→15%,其余12%)。
 *   ▲采购成本/头程成本拆两列：各=extra_json单件CNY×销量÷汇率6.6（**当日快照历史成本**，
 *     非成本配置表当前价，故与产品管理页现价可能不同——2026-08-19需求方确认按历史成本口径）。
 *   ▲单价三列（2026-08-19新增，6位小数，不随币种换算）：采购单价¥/头程单价¥=extra_json当日单件价；
 *     仓储费单价$=fact_wfs_storage_fee.unit_fee_standard（该店该SKU最新账期的标准单价日费）。
 *   退货费用=fact_refund_daily(售后申请日=美西站点时间)；仓储费=fact_storage_fee_daily(账期日摊)。
 *   订单利润=净销售额−广告−WFS配送费−佣金−采购成本−头程成本−退款额−仓储费。
 *   ▲ROI=订单利润×汇率6.6÷(采购成本+头程成本CNY×销量)（需求方公式，分母≤0记null）。
 *   ▲WFS可售库存=fact_inventory_daily最新快照.wfs_available_stock（与每日销售明细同字段同源）。
 *   ▲成本状态（Beta同口径）：销量>0时按单件成本≤0记"缺采购成本/缺头程成本/缺WFS配送费"，否则"完整"。
 *   ▲负责人/商品ID兜底：dim_product(店铺+MSKU)优先；未命中且该MSKU全库唯一归属时用唯一命中。
 *   退货率30天=以to为锚近30天退货件÷销量（行级+合计同口径）。毛利润(旧)=gross_profit原样留对账。
 * 铁律：全程只读SELECT；密钥走环境变量。
 */
import { Router, Request, Response } from "express";
import * as mysql from "mysql2/promise";
import { adjustedAdsFactSql } from "./adsItemSpendAlloc";

const router = Router();
const EXCHANGE_RATE = 6.6; // 与 syncOrderProfitDaily.ts 同参（口径源头，改需同改）
const commissionRate = (storeName: string): number =>
  (storeName.includes("CN2501") || storeName.includes("CN2502")) ? 0.15 : 0.12;
const r2 = (v: number): number => Math.round(v * 100) / 100;
const CS = "AND msku NOT LIKE 'CS%'";
// 早期CS测品人工剔除名单（MSKU不以CS开头但实为CS测品，需求方2026-08-19点名）
// 后续如增多可迁至配置表；此处以ItemID为准（跨店同ItemID一并剔除）
const MANUAL_EXCLUDE_ITEMS = new Set<string>([
  "20090164596",  // YC00141-1A 早期CS测品，已作废（2026-08-19需求方点名）
  "20706361834",  // YS00001-1A 已作废归CS（2026-08-19需求方指令）
]);

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
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

interface RowAcc {
  store_id: string; store_name: string; item_id: string; msku: string; owner: string; sku: string;
  sales: number; qty: number; excluded_sales: number; excluded_qty: number; excluded_orders: number;
  pc_unit: number; fl_unit: number; storage_unit: number; wfs_unit: number;
  ad: number; wfs: number; commission: number; pc_cny: number; fl_cny: number;
  refund_qty: number; refund_amount: number; storage: number; gross_profit_old: number;
  refund_qty_30d: number; qty_30d: number; wfs_stock: number;
}

router.get("/order-profit", async (req: Request, res: Response) => {
  const db = await getDb();
  try {
    const storeFilter = String(req.query.store_id ?? "").trim();
    const [mx] = await db.execute(`SELECT DATE_FORMAT(MAX(stat_date),'%Y-%m-%d') d FROM fact_profit_daily WHERE platform='walmart'`);
    const latest = String((mx as Array<Record<string, unknown>>)[0]?.d ?? "");
    let from = String(req.query.from ?? "").trim() || latest;
    let to = String(req.query.to ?? "").trim() || latest;
    if (!DATE_RE.test(from) || !DATE_RE.test(to)) { res.status(400).json({ error: "from/to 格式须为 YYYY-MM-DD" }); return; }
    if (from > to) [from, to] = [to, from];
    const win30Start = new Date(Date.parse(`${to}T00:00:00Z`) - 29 * 86400000).toISOString().slice(0, 10);
    const sf = storeFilter ? " AND store_id = ? " : " ";
    const sfArgs = storeFilter ? [storeFilter] : [];

    const rows = new Map<string, RowAcc>();
    const rowOf = (storeId: string, msku: string): RowAcc => {
      const k = `${storeId}||${msku}`;
      let r = rows.get(k);
      if (!r) {
        r = { store_id: storeId, store_name: "", item_id: "", msku, owner: "", sku: "",
          sales: 0, qty: 0, excluded_sales: 0, excluded_qty: 0, excluded_orders: 0,
          pc_unit: 0, fl_unit: 0, storage_unit: 0, wfs_unit: 0, ad: 0, wfs: 0, commission: 0, pc_cny: 0, fl_cny: 0,
          refund_qty: 0, refund_amount: 0, storage: 0, gross_profit_old: 0,
          refund_qty_30d: 0, qty_30d: 0, wfs_stock: 0 };
        rows.set(k, r);
      }
      return r;
    };

    // ── 1) 利润FACT基座（CS剔除；采购/头程CNY分列）──
    // ── 2026-08-21 送样成本剔除修复 ──────────────────────────────────────────
    // 三项随销量线性的成本改用「逐日净销量」= GREATEST(当日销量 − 当日送样件数, 0)。
    // 为什么必须逐日、不能用「窗口净销量 × 单价」：本页成本口径是**历史快照价**（每天用当天的配置价），
    //   用最新单价乘窗口净销量会破坏该口径（页面帮助文明写「历史报表用当时成本才对得上当时利润」）。
    // 为什么加表别名 f：加 JOIN 后 msku / store_id 不再唯一，必须限定，否则 ERROR 1052 ambiguous。
    // 为什么不改共享常量 CS / sf：它们是未限定写法且被本文件其它 5 处查询复用，故**只在本查询内**用限定版。
    // 已知残留（与 saleStat 归因错配同源，已另立待办）：当窗口内某天送样件数 > 当日销量时，
    //   逐日扣会比「窗口净销量」多扣几件。31 天样本中仅 3 个 店×MSKU 组合命中，见 probeSampleOrderAnomalyDetail。
    const CS_F = "AND f.msku NOT LIKE 'CS%'";
    const sfF = storeFilter ? " AND f.store_id = ? " : " ";
    const NET_QTY = "GREATEST(CAST(JSON_UNQUOTE(JSON_EXTRACT(f.extra_json,'$.sales_qty')) AS DECIMAL(12,2)) - COALESCE(s.sqty,0), 0)";
    const [baseRows] = await db.execute(
      `SELECT f.store_id, f.msku, MAX(f.store_name) sname,
              SUBSTRING_INDEX(GROUP_CONCAT(f.item_id ORDER BY f.stat_date DESC), ',', 1) item_id,
              SUM(f.sales_amount) sales, SUM(f.gross_profit) gp,
              SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(f.extra_json,'$.sales_qty')) AS DECIMAL(12,2))) qty,
              SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(f.extra_json,'$.wfs_fee_usd')) AS DECIMAL(12,4)) * ${NET_QTY}) wfs,
              SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(f.extra_json,'$.purchase_cost_cny')) AS DECIMAL(12,2)) * ${NET_QTY}) pc_cny,
              SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(f.extra_json,'$.first_leg_cost_cny')) AS DECIMAL(12,2)) * ${NET_QTY}) fl_cny,
              CAST(SUBSTRING_INDEX(GROUP_CONCAT(JSON_UNQUOTE(JSON_EXTRACT(f.extra_json,'$.purchase_cost_cny')) ORDER BY f.stat_date DESC), ',', 1) AS DECIMAL(12,6)) pc_unit,
              CAST(SUBSTRING_INDEX(GROUP_CONCAT(JSON_UNQUOTE(JSON_EXTRACT(f.extra_json,'$.first_leg_cost_cny')) ORDER BY f.stat_date DESC), ',', 1) AS DECIMAL(12,6)) fl_unit,
              CAST(SUBSTRING_INDEX(GROUP_CONCAT(JSON_UNQUOTE(JSON_EXTRACT(f.extra_json,'$.wfs_fee_usd')) ORDER BY f.stat_date DESC), ',', 1) AS DECIMAL(12,6)) wfs_unit
       FROM fact_profit_daily f
       LEFT JOIN (
         SELECT purchase_date pd, store_id, msku, SUM(quantity) sqty
           FROM raw_mp_order_discount
          WHERE order_status <> 7 AND ABS(discount_amount) >= item_price_amount - 0.01
            AND purchase_date BETWEEN ? AND ? AND msku NOT LIKE 'CS%'
          GROUP BY pd, store_id, msku
       ) s ON s.pd = f.stat_date AND s.store_id = f.store_id AND s.msku = f.msku
       WHERE f.platform='walmart' AND f.stat_date BETWEEN ? AND ? ${CS_F}${sfF}
       GROUP BY f.store_id, f.msku`, [from, to, from, to, ...sfArgs]);
    for (const b of baseRows as Array<Record<string, unknown>>) {
      const r = rowOf(String(b.store_id), String(b.msku));
      r.store_name = String(b.sname ?? "");
      r.item_id = String(b.item_id ?? "");
      r.sales = Number(b.sales ?? 0);
      r.qty = Number(b.qty ?? 0);
      r.wfs = Number(b.wfs ?? 0);
      r.pc_cny = Number(b.pc_cny ?? 0);
      r.fl_cny = Number(b.fl_cny ?? 0);
      r.pc_unit = Number(b.pc_unit ?? 0);
      r.fl_unit = Number(b.fl_unit ?? 0);
      r.wfs_unit = Number(b.wfs_unit ?? 0);
      r.commission = r.sales * commissionRate(r.store_name);
      r.gross_profit_old = Number(b.gp ?? 0);
    }

    // ── 2) 送样单剔除（全额折扣=送样/0元单，整单不计入正式订单；2026-08-19拍板）──
    //    源=raw_mp_order_discount（订单列表接口，31天窗）；判定 |折扣| >= 商品金额-0.01；
    //    店铺id经历史精度修复后与FACT一致；日界=purchase_date（美西日，与销售额同源）。
    const [sampleRows] = await db.execute(
      `SELECT store_id, msku, COUNT(DISTINCT platform_order_no) orders,
              SUM(quantity) qty, ROUND(SUM(item_price_amount),2) amt
       FROM raw_mp_order_discount
       WHERE order_status <> 7 AND ABS(discount_amount) >= item_price_amount - 0.01
         AND purchase_date BETWEEN ? AND ? AND msku NOT LIKE 'CS%'${sf}
       GROUP BY store_id, msku`, [from, to, ...sfArgs]);
    for (const d of sampleRows as Array<Record<string, unknown>>) {
      const r = rowOf(String(d.store_id), String(d.msku));
      r.excluded_orders = Number(d.orders ?? 0);
      r.excluded_qty = Number(d.qty ?? 0);
      r.excluded_sales = Number(d.amt ?? 0);
    }

    // ── 3) 退货（范围内+30天窗一次取回，CS剔除）──
    const [refRows] = await db.execute(
      `SELECT store_id, msku,
              SUM(CASE WHEN refund_date BETWEEN ? AND ? THEN refund_qty ELSE 0 END) q,
              SUM(CASE WHEN refund_date BETWEEN ? AND ? THEN refund_amount ELSE 0 END) amt,
              SUM(CASE WHEN refund_date BETWEEN ? AND ? THEN refund_qty ELSE 0 END) q30
       FROM fact_refund_daily WHERE platform='walmart' AND refund_date BETWEEN LEAST(?, ?) AND ? ${CS}${sf}
       GROUP BY store_id, msku HAVING q > 0 OR q30 > 0 OR amt <> 0`,
      [from, to, from, to, win30Start, to, win30Start, from, to, ...sfArgs]);
    for (const d of refRows as Array<Record<string, unknown>>) {
      const r = rowOf(String(d.store_id), String(d.msku));
      r.refund_qty = Number(d.q ?? 0); r.refund_amount = Number(d.amt ?? 0);
      r.refund_qty_30d = Number(d.q30 ?? 0);
    }

    // ── 4) 仓储费日摊（CS剔除；表列名=sku）──
    const [stoRows] = await db.execute(
      `SELECT store_id, sku msku, SUM(storage_fee) amt
       FROM fact_storage_fee_daily WHERE platform='walmart' AND fee_date BETWEEN ? AND ? AND sku NOT LIKE 'CS%'${sf}
       GROUP BY store_id, sku`, [from, to, ...sfArgs]);
    for (const d of stoRows as Array<Record<string, unknown>>) {
      rowOf(String(d.store_id), String(d.msku)).storage = Number(d.amt ?? 0);
    }
    // 仓储费单价：该店该SKU最新账期的标准单价日费（$/件/天，6位小数，与仓储费页同源字段）
    const [stoUnitRows] = await db.execute(
      `SELECT f.store_id, f.sku msku, f.unit_fee_standard u
       FROM fact_wfs_storage_fee f
       JOIN (SELECT store_id, sku, MAX(report_start) ms FROM fact_wfs_storage_fee
             WHERE platform='walmart' GROUP BY store_id, sku) m
         ON m.store_id=f.store_id AND m.sku=f.sku AND m.ms=f.report_start
       WHERE f.platform='walmart' AND f.unit_fee_standard IS NOT NULL`);
    for (const d of stoUnitRows as Array<Record<string, unknown>>) {
      const r = rows.get(`${d.store_id}||${d.msku}`);
      if (r) r.storage_unit = Number(d.u ?? 0);
    }

    // ── 5) 广告费（权威表全类型；CS广告整体剔除不入桶）──
    // 2026-08-25 需求方拍板：按品广告费含SV无商品ID行(占位1001类)分摊——统一口径见 adsItemSpendAlloc.ts
    const [adRows] = await db.execute(
      `SELECT store_id, item_id, MAX(store_name) sname, SUM(ad_spend) ad
       FROM ${adjustedAdsFactSql()} fa WHERE fa.platform='walmart' AND fa.stat_date BETWEEN ? AND ?${sf}
       GROUP BY store_id, item_id`, [from, to, ...sfArgs]);
    const itemIndex = new Map<string, RowAcc[]>();
    for (const r of rows.values()) {
      if (!r.item_id) continue;
      const k = `${r.store_id}||${r.item_id}`;
      const arr = itemIndex.get(k) ?? [];
      arr.push(r); itemIndex.set(k, arr);
    }
    const unresolvedAds: Array<{ store_id: string; item_id: string; ad: number }> = [];
    const storeAdBucket = new Map<string, { store_id: string; store_name: string; ad: number; items: number }>();
    let csAdDropped = 0;
    for (const a of adRows as Array<Record<string, unknown>>) {
      const storeId = String(a.store_id), itemId = String(a.item_id ?? "").trim();
      const ad = Number(a.ad ?? 0);
      if (ad === 0) continue;
      const targets = itemIndex.get(`${storeId}||${itemId}`);
      if (targets && targets.length > 0) {
        const salesSum = targets.reduce((s, t) => s + t.sales, 0);
        for (const t of targets) t.ad += salesSum > 0 ? ad * (t.sales / salesSum) : ad / targets.length;
      } else if (itemId) {
        unresolvedAds.push({ store_id: storeId, item_id: itemId, ad });
      } else {
        const b = storeAdBucket.get(storeId) ?? { store_id: storeId, store_name: String(a.sname ?? ""), ad: 0, items: 0 };
        b.ad += ad; b.items += 1; storeAdBucket.set(storeId, b);
      }
    }
    if (unresolvedAds.length > 0) {
      const conds = unresolvedAds.map(() => "(store_id=? AND item_id=?)").join(" OR ");
      const args: string[] = [];
      for (const u of unresolvedAds) args.push(u.store_id, u.item_id);
      const [dpRows] = await db.execute(
        `SELECT store_id, item_id, msku FROM dim_product
         WHERE platform='walmart' AND (${conds}) GROUP BY store_id, item_id, msku`, args);
      const dpIdx = new Map<string, string[]>();
      for (const d of dpRows as Array<Record<string, unknown>>) {
        const k = `${d.store_id}||${d.item_id}`;
        const arr = dpIdx.get(k) ?? [];
        arr.push(String(d.msku)); dpIdx.set(k, arr);
      }
      for (const u of unresolvedAds) {
        const all = dpIdx.get(`${u.store_id}||${u.item_id}`) ?? [];
        const nonCs = all.filter((m) => !m.toUpperCase().startsWith("CS"));
        if (all.length > 0 && nonCs.length === 0) { csAdDropped = r2(csAdDropped + u.ad); continue; } // CS广告整体剔除
        if (nonCs.length > 0) {
          const per = u.ad / nonCs.length;
          for (const m of nonCs) {
            const r = rowOf(u.store_id, m);
            if (!r.item_id) r.item_id = u.item_id;
            r.ad += per;
          }
        } else {
          const b = storeAdBucket.get(u.store_id) ?? { store_id: u.store_id, store_name: "", ad: 0, items: 0 };
          b.ad += u.ad; b.items += 1; storeAdBucket.set(u.store_id, b);
        }
      }
    }

    // ── 6) 30天销量 + WFS可售库存(最新快照) + 负责人/店名补齐 ──
    const [qty30Rows] = await db.execute(
      `SELECT store_id, msku,
              SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(extra_json,'$.sales_qty')) AS DECIMAL(12,2))) q
       FROM fact_profit_daily WHERE platform='walmart' AND stat_date BETWEEN ? AND ? ${CS}${sf}
       GROUP BY store_id, msku`, [win30Start, to, ...sfArgs]);
    const qty30Map = new Map<string, number>();
    for (const d of qty30Rows as Array<Record<string, unknown>>) {
      qty30Map.set(`${d.store_id}||${d.msku}`, Number(d.q ?? 0));
    }
    for (const [k, r] of rows) r.qty_30d = qty30Map.get(k) ?? 0;

    const [invRows] = await db.execute(
      `SELECT store_id, msku, SUM(COALESCE(wfs_available_stock,0)) wfs
       FROM fact_inventory_daily
       WHERE platform='walmart' AND snapshot_date=(SELECT MAX(snapshot_date) FROM fact_inventory_daily WHERE platform='walmart')
         ${CS}${sf}
       GROUP BY store_id, msku`, [...sfArgs]);
    const [invMeta] = await db.execute(`SELECT DATE_FORMAT(MAX(snapshot_date),'%Y-%m-%d') d FROM fact_inventory_daily WHERE platform='walmart'`);
    const invDate = String((invMeta as Array<Record<string, unknown>>)[0]?.d ?? "");
    for (const d of invRows as Array<Record<string, unknown>>) {
      const r = rows.get(`${d.store_id}||${d.msku}`);
      if (r) r.wfs_stock = Number(d.wfs ?? 0);
    }

    const [ownRows] = await db.execute(
      `SELECT store_id, msku, MAX(COALESCE(owner,'')) owner, MAX(COALESCE(item_id,'')) item_id, MAX(COALESCE(sku,'')) sku
       FROM dim_product WHERE platform='walmart' GROUP BY store_id, msku`);
    const ownMap = new Map<string, { owner: string; item_id: string; sku: string }>();
    const mskuGlobal = new Map<string, { owners: Set<string>; items: Set<string>; stores: Set<string> }>();
    for (const d of ownRows as Array<Record<string, unknown>>) {
      const st = String(d.store_id), mk = String(d.msku);
      ownMap.set(`${st}||${mk}`, { owner: String(d.owner ?? ""), item_id: String(d.item_id ?? ""), sku: String(d.sku ?? "") });
      const g = mskuGlobal.get(mk) ?? { owners: new Set(), items: new Set(), stores: new Set() };
      if (String(d.owner ?? "")) g.owners.add(String(d.owner));
      if (String(d.item_id ?? "")) g.items.add(String(d.item_id));
      g.stores.add(st); mskuGlobal.set(mk, g);
    }
    const [stoNameRows] = await db.execute(`SELECT store_id, MAX(store_name) sname FROM dim_store WHERE platform='walmart' GROUP BY store_id`);
    const stoNameMap = new Map<string, string>();
    for (const d of stoNameRows as Array<Record<string, unknown>>) stoNameMap.set(String(d.store_id), String(d.sname ?? ""));
    for (const r of rows.values()) {
      const o = ownMap.get(`${r.store_id}||${r.msku}`);
      if (o) { if (!r.owner) r.owner = o.owner; if (!r.item_id) r.item_id = o.item_id; if (!r.sku) r.sku = o.sku; }
      if (!r.owner || !r.item_id) { // ▲msku全库唯一兜底
        const g = mskuGlobal.get(r.msku);
        if (g) {
          if (!r.owner && g.owners.size === 1) r.owner = Array.from(g.owners)[0];
          if (!r.item_id && g.items.size === 1) r.item_id = Array.from(g.items)[0];
        }
      }
      if (!r.store_name) r.store_name = stoNameMap.get(r.store_id) ?? r.store_id;
      if (r.commission === 0 && r.sales > 0) r.commission = r.sales * commissionRate(r.store_name);
    }
    for (const b of storeAdBucket.values()) { if (!b.store_name) b.store_name = stoNameMap.get(b.store_id) ?? b.store_id; }

    // ── 7) 出参（先剔除人工名单：早期CS测品）──
    for (const [k, r] of Array.from(rows.entries())) {
      if (MANUAL_EXCLUDE_ITEMS.has(r.item_id)) rows.delete(k);
    }
    const out = Array.from(rows.values()).map((r) => {
      // 送样单整单剔除：销售额与销量按剔除后口径（不足则归零，防负）
      const netSales = Math.max(0, r.sales - r.excluded_sales);
      const qtyNet = Math.max(0, r.qty - r.excluded_qty);
      const pc = r.pc_cny / EXCHANGE_RATE, fl = r.fl_cny / EXCHANGE_RATE;
      // 佣金基数=剔除送样后的销售额（送样单0元成交，平台不收佣金）
      const commission = netSales * commissionRate(r.store_name);
      const orderProfit = netSales - r.ad - r.wfs - commission - pc - fl - r.refund_amount - r.storage;
      const denomCny = r.pc_cny + r.fl_cny;
      const missing: string[] = [];
      if (r.qty > 0) {
        if (r.pc_cny <= 0) missing.push("缺采购成本");
        if (r.fl_cny <= 0) missing.push("缺头程成本");
        if (r.wfs <= 0) missing.push("缺WFS配送费");
      }
      return {
        store_id: r.store_id, store_name: r.store_name, owner: r.owner, item_id: r.item_id, msku: r.msku, sku: r.sku,
        sales: r2(netSales), qty: Math.round(qtyNet),
        excluded_sales: r2(r.excluded_sales), excluded_orders: r.excluded_orders, excluded_qty: Math.round(r.excluded_qty),
        refund_qty: Math.round(r.refund_qty), refund_amount: r2(r.refund_amount),
        refund_rate_30d: r.qty_30d > 0 ? Math.round((r.refund_qty_30d / r.qty_30d) * 10000) / 10000 : null,
        refund_qty_30d: Math.round(r.refund_qty_30d), qty_30d: Math.round(r.qty_30d),
        ad: r2(r.ad), wfs: r2(r.wfs), commission: r2(commission),
        purchase_cost: r2(pc), first_leg: r2(fl), storage: r2(r.storage),
        pc_unit: Math.round(r.pc_unit * 1e6) / 1e6, fl_unit: Math.round(r.fl_unit * 1e6) / 1e6,
        wfs_unit: Math.round(r.wfs_unit * 100) / 100,
        storage_unit: Math.round(r.storage_unit * 1e6) / 1e6,
        wfs_stock: Math.round(r.wfs_stock),
        gross_profit_old: r2(r.gross_profit_old),
        order_profit: r2(orderProfit),
        profit_rate: netSales > 0 ? Math.round((orderProfit / netSales) * 10000) / 10000 : null,
        roi: denomCny > 0 ? Math.round((orderProfit * EXCHANGE_RATE / denomCny) * 100) / 100 : null,
        cost_status: r.qty > 0 ? (missing.length ? missing.join("/") : "完整") : "-",
      };
    });
    const sum = (f: (x: typeof out[number]) => number): number => r2(out.reduce((s, x) => s + f(x), 0));
    const bucketAd = r2(Array.from(storeAdBucket.values()).reduce((s, b) => s + b.ad, 0));
    const totQty30 = out.reduce((s, x) => s + x.qty_30d, 0);
    const totRef30 = out.reduce((s, x) => s + x.refund_qty_30d, 0);
    res.json({
      from, to, latest_biz_date: latest, win30_start: win30Start, inv_snapshot_date: invDate,
      kpi: {
        sales: sum((x) => x.sales),
        excluded_sales: sum((x) => x.excluded_sales),
        excluded_orders: out.reduce((a, x) => a + x.excluded_orders, 0),
        order_profit: r2(sum((x) => x.order_profit) - bucketAd),
        refund_amount: sum((x) => x.refund_amount),
        refund_rate_30d: totQty30 > 0 ? Math.round((totRef30 / totQty30) * 10000) / 10000 : null,
        refund_qty_30d_total: totRef30, qty_30d_total: totQty30,
        ad_total: r2(sum((x) => x.ad) + bucketAd), ad_unattributed: bucketAd,
        cs_ad_dropped: csAdDropped, row_cnt: out.length,
      },
      rows: out,
      store_ad_buckets: Array.from(storeAdBucket.values()).map((b) => ({ ...b, ad: r2(b.ad) })),
      caliber_note: "订单利润=销售额−广告费(SP+SB+SV+SEM权威表)−WFS配送费−佣金−采购成本−头程成本−退款额−仓储费日摊；ROI=订单利润×6.6÷(采购+头程CNY)；CS测品整行剔除；送样单(全额折扣)整单剔除不计入销售额与销量，故本页销售额低于saleStat恒等基准，差额=送样单金额；成本为当日快照历史价；毛利润列为旧口径仅供对账",
    });
  } catch (e) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally {
    await db.end();
  }
});

export default router;
