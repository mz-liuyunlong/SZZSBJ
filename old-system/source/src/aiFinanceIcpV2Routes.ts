/**
 * aiFinanceIcpV2Routes.ts — AI财务 · 单品现金利润 v2（按「店铺 + ITEMID」出数）批13 第一批
 * 挂载：/api/finance（adminServer，与 aiFinanceRoutes 同前缀、不同路径；全局 authMiddleware）
 *
 * GET /item-cash-profit-v2?from=YYYY-MM&to=YYYY-MM&store_id=&scope=clean|all&family=yc200|all
 *
 * 为什么新建文件而不改 aiFinanceRoutes.ts：
 *   铁律「新功能隔离开发、最小改动旧页面」。旧接口 /item-cash-profit 与旧页面**一行不改**，
 *   验收第3条「旧接口返回体逐字节一致」由构造保证，零回归风险。
 *
 * 与 v1 的唯一差异 = 聚合键：v1 = store||本地SKU（经 fact_inventory_daily 的 msku→sku 唯一命中映射）；
 *   v2 = store||item_id。七条成本源里五条本就带 item_id（recon/广告/仓储100%/入库100%/头程），
 *   v2 直接取用，**删掉映射层而非新增映射层**（v1 那张映射表 HAVING COUNT(DISTINCT sku)=1，
 *   多命中直接丢弃，是"未映射"行的来源之一）。真正需分摊的只有采购与期初池两条 SKU 级来源。
 *
 * 口径与 v1 完全一致，未作任何改动：
 *   切点 2026-05-01；期初=WFS快照×一刀价、按月FIFO防双算；切点前采购/头程现金不计（一刀切）；
 *   虚拟SKU(XY2007/DC001/QH888)整行豁免；汇率取归属月「上一个月」领星 my_rate、退 rate_org；
 *   店铺级类目(SEM/测评/赔付/其他/未映射广告/未归属采购)不摊到品；哨兵比总量、与聚合键无关。
 *
 * scope：
 *   clean（默认）= 只出「1店1item」的可直归 item（该本地SKU 全库只对应唯一 (店铺,ITEMID)），
 *     采购份额恒 100%、零分摊争议；被排除的 item 不丢弃，汇总进 excluded 桶，总量不失真。
 *   all = 全部 item（需分摊的按发货量份额拆，第二批用）。
 * family：yc200 = 本地SKU 匹配 ^YC[0-9]+ 且数字部分>=200（需求方口径：YC00200 之后基本都是新品）；all = 不限。
 *
 * 铁律：全程只读（仅 SELECT）；不写任何表、不碰人工备注列；连接从环境变量读，禁止硬编码密钥。
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
    dateStrings: true,
  });
}

// ── 常量：与 v1 逐字一致，禁止在此调整口径 ──
const CUTOFF = "2026-05-01";
const CUTOFF_M = "2026-05";
const EXCLUDED = new Set(["storage", "inbound_transport", "ad_platform"]); // 专管道替代，只进哨兵
const COMP = new Set(["lost_inventory", "found_inventory", "damage_warehouse", "wfs_refund",
  "ad_credit", "wfs_discount_adjustment", "inventory_transfer"]);
const VIRTUAL = new Set(["XY2007", "DC001", "QH888"]);

const r2 = (v: number): number => Math.round(v * 100) / 100;
function prevMonth(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 2, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}
function monthsOf(from: string, to: string): string[] {
  const out: string[] = [];
  const [fy, fm] = from.split("-").map(Number);
  const [ty, tm] = to.split("-").map(Number);
  let cur = new Date(Date.UTC(fy, fm - 1, 1));
  const last = new Date(Date.UTC(ty, tm - 1, 1));
  while (cur <= last && out.length < 24) {
    out.push(`${cur.getUTCFullYear()}-${String(cur.getUTCMonth() + 1).padStart(2, "0")}`);
    cur = new Date(Date.UTC(cur.getUTCFullYear(), cur.getUTCMonth() + 1, 1));
  }
  return out;
}
// 本地SKU 是否属「YC00200 及之后」（需求方口径）
function isYc200(sku: string): boolean {
  const m = /^YC0*(\d+)/.exec(sku);
  return m ? Number(m[1]) >= 200 : false;
}

interface Cell { c: number; u: number } // c=CNY u=USD 双币
interface V2Row {
  store_id: string; store_name: string; item_id: string;
  skus: string[]; mskus: string[];
  sale: Cell; refund: Cell; comp: Cell; wfs_fee: Cell; other_item: Cell;
  ads: Cell; storage: Cell; inbound: Cell;
  purchase: Cell; firstmile: Cell; opening_cost: Cell;
  sold_qty: number; opening_used_qty: number;
  revenue: Cell; expense: Cell; profit: Cell;
  is_clean: boolean;
}
interface StoreRow {
  store_id: string; store_name: string;
  sem: Cell; review: Cell; comp: Cell; other: Cell;
  ads_unmapped: Cell; purchase_unmapped: Cell; unmapped_cnt: number;
}

router.get("/item-cash-profit-v2", async (req: Request, res: Response): Promise<void> => {
  const q = (req.query ?? {}) as Record<string, unknown>;
  const nowM = new Date().toISOString().slice(0, 7);
  let from = String(q.from ?? CUTOFF_M).trim() || CUTOFF_M;
  let to = String(q.to ?? nowM).trim() || nowM;
  if (!/^\d{4}-\d{2}$/.test(from)) from = CUTOFF_M;
  if (!/^\d{4}-\d{2}$/.test(to)) to = nowM;
  if (from < CUTOFF_M) from = CUTOFF_M;
  if (to < from) to = from;
  const storeFilter = String(q.store_id ?? "").trim();
  const scope = String(q.scope ?? "clean").trim() === "all" ? "all" : "clean";
  const family = String(q.family ?? "all").trim() === "yc200" ? "yc200" : "all";
  const months = monthsOf(from, to);

  const db = await getDb();
  try {
    // ── ① 汇率：归属月取「上一个月」my_rate，退 rate_org（与 v1 同源）──
    const [fxRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT rate_month, my_rate, rate_org FROM fact_lingxing_fx_rate WHERE currency_code='USD'`);
    const fxRaw = new Map<string, { my: number; org: number }>();
    for (const r of fxRows) fxRaw.set(String(r.rate_month), { my: Number(r.my_rate) || 0, org: Number(r.rate_org) || 0 });
    const rateOf = (m: string): number => {
      const p = fxRaw.get(prevMonth(m));
      return p ? (p.my > 0 ? p.my : p.org) : 0;
    };
    const fxMissing: string[] = [];
    const zc = (): Cell => ({ c: 0, u: 0 });
    const cellAdd = (cell: Cell, m: string, amt: number, cur: "USD" | "CNY"): void => {
      const rate = rateOf(m);
      if (cur === "USD") { cell.u += amt; if (rate > 0) cell.c += amt * rate; else if (!fxMissing.includes(m)) fxMissing.push(m); }
      else { cell.c += amt; if (rate > 0) cell.u += amt / rate; else if (!fxMissing.includes(m)) fxMissing.push(m); }
    };

    // ── ② 店铺白名单 + 领星 storeId 数字精度损坏就近修复（与 v1 同逻辑）──
    const [stRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, store_name FROM dim_store WHERE platform='walmart'`);
    const storeNames = new Map<string, string>();
    for (const r of stRows) storeNames.set(String(r.store_id), String(r.store_name));
    const validArr = Array.from(storeNames.keys());
    const fixCache = new Map<string, string | null>();
    const closeId = (a: string, b: string): boolean => {
      if (a.length !== b.length || a.length < 5) return false;
      if (a.slice(0, -4) !== b.slice(0, -4)) return false;
      return Math.abs(Number(a.slice(-4)) - Number(b.slice(-4))) <= 16;
    };
    const normStore = (id: string): string | null => {
      if (!id) return null;
      if (storeNames.has(id)) return id;
      if (fixCache.has(id)) return fixCache.get(id) ?? null;
      let hit: string | null = null;
      for (const v of validArr) { if (closeId(v, id)) { hit = v; break; } }
      fixCache.set(id, hit); return hit;
    };

    // ── ③ dim_product：(店,item) 的 sku/msku 归属 + sku→(店,item) 反向 + 可直归判定 ──
    const [dpRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, COALESCE(sku,'') AS sku, COALESCE(msku,'') AS msku, item_id
         FROM dim_product WHERE platform='walmart' AND COALESCE(item_id,'')<>''`);
    const itemSkus = new Map<string, Set<string>>();   // store||item → skus
    const itemMskus = new Map<string, Set<string>>();  // store||item → mskus
    const skuPairs = new Map<string, Set<string>>();   // sku → Set(store||item)
    const mskuToItem = new Map<string, string | null>(); // store||msku → item（歧义置 null）
    for (const r of dpRows) {
      const st = String(r.store_id), it = String(r.item_id);
      const sku = String(r.sku), msku = String(r.msku);
      const ik = `${st}||${it}`;
      if (!itemSkus.has(ik)) itemSkus.set(ik, new Set());
      if (!itemMskus.has(ik)) itemMskus.set(ik, new Set());
      if (sku) itemSkus.get(ik)!.add(sku);
      if (msku) itemMskus.get(ik)!.add(msku);
      if (sku) {
        if (!skuPairs.has(sku)) skuPairs.set(sku, new Set());
        skuPairs.get(sku)!.add(ik);
      }
      if (msku) {
        const mk = `${st}||${msku}`;
        if (!mskuToItem.has(mk)) mskuToItem.set(mk, it);
        else if (mskuToItem.get(mk) !== it) mskuToItem.set(mk, null);
      }
    }
    // 可直归 = 该本地SKU 全库只对应唯一 (店铺,ITEMID)
    const cleanPairs = new Set<string>();
    for (const [, pairs] of skuPairs.entries()) {
      if (pairs.size === 1) for (const p of pairs) cleanPairs.add(p);
    }
    const itemIsVirtual = (ik: string): boolean => {
      const s = itemSkus.get(ik);
      if (!s || s.size === 0) return false;
      for (const x of s) if (!VIRTUAL.has(x)) return false;
      return true; // 全部为虚拟SKU 才豁免
    };
    const itemInFamily = (ik: string): boolean => {
      if (family === "all") return true;
      const s = itemSkus.get(ik);
      if (!s) return false;
      for (const x of s) if (isYc200(x)) return true;
      return false;
    };
    // 本行是否纳入 rows（scope=clean 时只要可直归）
    const inScope = (ik: string): boolean => {
      if (itemIsVirtual(ik)) return false;
      if (!itemInFamily(ik)) return false;
      return scope === "all" ? true : cleanPairs.has(ik);
    };

    // ── ④ 行容器：种子行（保证空壳 item 也出行，行数可硬校验）──
    const rows = new Map<string, V2Row>();
    const excluded = { rows: 0, revenue: zc(), expense: zc(), profit: zc() }; // 落在范围外 item 的量，不丢弃
    const mkRow = (store: string, item: string): V2Row => ({
      store_id: store, store_name: storeNames.get(store) ?? store, item_id: item,
      skus: Array.from(itemSkus.get(`${store}||${item}`) ?? []).slice(0, 12),
      mskus: Array.from(itemMskus.get(`${store}||${item}`) ?? []).slice(0, 12),
      sale: zc(), refund: zc(), comp: zc(), wfs_fee: zc(), other_item: zc(),
      ads: zc(), storage: zc(), inbound: zc(), purchase: zc(), firstmile: zc(), opening_cost: zc(),
      sold_qty: 0, opening_used_qty: 0, revenue: zc(), expense: zc(), profit: zc(),
      is_clean: cleanPairs.has(`${store}||${item}`),
    });
    for (const ik of itemSkus.keys()) {
      const [st, it] = ik.split("||");
      if (storeFilter && st !== storeFilter) continue;
      if (!inScope(ik)) continue;
      rows.set(ik, mkRow(st, it));
    }
    // 取行：范围内落行；范围外仅计入 excluded 汇总（保证总量不失真）
    const outOfScope = new Map<string, { rev: number; exp: number }>();
    const rowOf = (store: string, item: string): V2Row | null => {
      const ik = `${store}||${item}`;
      const hit = rows.get(ik);
      if (hit) return hit;
      if (storeFilter && store !== storeFilter) return null;
      if (itemIsVirtual(ik)) return null;               // 虚拟SKU 整行豁免
      if (scope === "all" && itemInFamily(ik)) {        // all 口径下 dim_product 查无的 item 也补行
        const nr = mkRow(store, item); rows.set(ik, nr); return nr;
      }
      if (!outOfScope.has(ik)) outOfScope.set(ik, { rev: 0, exp: 0 });
      return null;
    };
    const noteExcluded = (store: string, item: string, amt: number, kind: "rev" | "exp"): void => {
      const ik = `${store}||${item}`;
      if (!outOfScope.has(ik)) outOfScope.set(ik, { rev: 0, exp: 0 });
      const b = outOfScope.get(ik)!;
      if (kind === "rev") b.rev += amt; else b.exp += amt;
    };

    const storeRows = new Map<string, StoreRow>();
    const sRowOf = (store: string): StoreRow => {
      let r = storeRows.get(store);
      if (!r) {
        r = { store_id: store, store_name: storeNames.get(store) ?? store,
          sem: zc(), review: zc(), comp: zc(), other: zc(),
          ads_unmapped: zc(), purchase_unmapped: zc(), unmapped_cnt: 0 };
        storeRows.set(store, r);
      }
      return r;
    };

    const storeCond = storeFilter ? " AND store_id=? " : " ";
    const sf = (base: unknown[]): unknown[] => storeFilter ? [...base, storeFilter] : base;

    // ── ⑤ 回款 recon（USD）：**直接用 item_id**；为空时退 (店,msku) 唯一映射；仍为空进店铺级 ──
    const [recon] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, COALESCE(item_id,'') AS item_id, COALESCE(msku,'') AS msku, fee_category,
              DATE_FORMAT(period_end,'%Y-%m') AS m, ROUND(SUM(amount),4) AS amt
         FROM fact_reconciliation_item
        WHERE DATE_FORMAT(period_end,'%Y-%m') BETWEEN ? AND ? ${storeCond}
        GROUP BY store_id, item_id, msku, fee_category, m`, sf([from, to]));
    const pipeSent = { storage: 0, inbound: 0, ad: 0 };
    let reconAll = 0;
    for (const r of recon) {
      const store = String(r.store_id), cat = String(r.fee_category), m = String(r.m), amt = Number(r.amt) || 0;
      reconAll = r2(reconAll + amt);
      if (EXCLUDED.has(cat)) {
        if (cat === "storage") pipeSent.storage += amt;
        else if (cat === "inbound_transport") pipeSent.inbound += amt;
        else pipeSent.ad += amt;
        continue;
      }
      if (cat === "sem") { cellAdd(sRowOf(store).sem, m, amt, "USD"); continue; }
      if (cat === "review_accelerator") { cellAdd(sRowOf(store).review, m, amt, "USD"); continue; }
      let item = String(r.item_id);
      if (!item) {
        const msku = String(r.msku);
        if (msku) item = mskuToItem.get(`${store}||${msku}`) ?? "";
      }
      if (!item) { // 无品：赔付返还单列，其余进店铺级其他（与 v1 一致）
        const sr = sRowOf(store);
        if (COMP.has(cat)) cellAdd(sr.comp, m, amt, "USD"); else cellAdd(sr.other, m, amt, "USD");
        if (String(r.msku)) sr.unmapped_cnt += 1;
        continue;
      }
      const row = rowOf(store, item);
      if (!row) { noteExcluded(store, item, amt, cat === "sale" || cat.startsWith("refund_") || COMP.has(cat) ? "rev" : "exp"); continue; }
      if (cat === "sale") cellAdd(row.sale, m, amt, "USD");
      else if (cat.startsWith("refund_")) cellAdd(row.refund, m, amt, "USD");
      else if (COMP.has(cat)) cellAdd(row.comp, m, amt, "USD");
      else if (cat === "wfs_fulfillment") cellAdd(row.wfs_fee, m, amt, "USD");
      else cellAdd(row.other_item, m, amt, "USD");
    }

    // ── ⑥ 广告（USD）：直接用 item_id，空则退 (店,msku) ──
    const [ads] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, COALESCE(item_id,'') AS item_id, COALESCE(msku,'') AS msku,
              DATE_FORMAT(stat_date,'%Y-%m') AS m, ROUND(SUM(ad_spend),4) AS amt
         FROM fact_ads_product_daily
        WHERE platform='walmart' AND DATE_FORMAT(stat_date,'%Y-%m') BETWEEN ? AND ? ${storeCond}
        GROUP BY store_id, item_id, msku, m`, sf([from, to]));
    let adsPipeTotal = 0;
    for (const r of ads) {
      const store = String(r.store_id), m = String(r.m), amt = Number(r.amt) || 0;
      adsPipeTotal += amt;
      let item = String(r.item_id);
      if (!item) { const msku = String(r.msku); if (msku) item = mskuToItem.get(`${store}||${msku}`) ?? ""; }
      if (!item) { cellAdd(sRowOf(store).ads_unmapped, m, -amt, "USD"); continue; }
      const row = rowOf(store, item);
      if (!row) { noteExcluded(store, item, amt, "exp"); continue; }
      cellAdd(row.ads, m, amt, "USD");
    }

    // ── ⑦ 仓储费（USD；item_id 100% 填充）──
    const [stor] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, COALESCE(item_id,'') AS item_id, COALESCE(sku,'') AS msku,
              DATE_FORMAT(report_start,'%Y-%m') AS m, ROUND(SUM(final_storage_fee),4) AS amt
         FROM fact_wfs_storage_fee
        WHERE DATE_FORMAT(report_start,'%Y-%m') BETWEEN ? AND ? ${storeCond}
        GROUP BY store_id, item_id, msku, m`, sf([from, to]));
    let storPipeTotal = 0;
    for (const r of stor) {
      const store = String(r.store_id), m = String(r.m), amt = Number(r.amt) || 0;
      storPipeTotal += amt;
      let item = String(r.item_id);
      if (!item) { const msku = String(r.msku); if (msku) item = mskuToItem.get(`${store}||${msku}`) ?? ""; }
      if (!item) { cellAdd(sRowOf(store).other, m, -amt, "USD"); continue; }
      const row = rowOf(store, item);
      if (!row) { noteExcluded(store, item, amt, "exp"); continue; }
      cellAdd(row.storage, m, amt, "USD");
    }

    // ── ⑧ 入库运输分摊（USD；item_id 100% 填充）──
    const [inb] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, COALESCE(item_id,'') AS item_id, COALESCE(msku,'') AS msku,
              DATE_FORMAT(report_start,'%Y-%m') AS m, ROUND(SUM(alloc_amount),4) AS amt
         FROM fact_inbound_freight_alloc
        WHERE DATE_FORMAT(report_start,'%Y-%m') BETWEEN ? AND ? ${storeCond}
        GROUP BY store_id, item_id, msku, m`, sf([from, to]));
    let inbPipeTotal = 0;
    for (const r of inb) {
      const store = String(r.store_id), m = String(r.m), amt = Number(r.amt) || 0;
      inbPipeTotal += amt;
      let item = String(r.item_id);
      if (!item) { const msku = String(r.msku); if (msku) item = mskuToItem.get(`${store}||${msku}`) ?? ""; }
      if (!item) { cellAdd(sRowOf(store).other, m, -amt, "USD"); continue; }
      const row = rowOf(store, item);
      if (!row) { noteExcluded(store, item, amt, "exp"); continue; }
      cellAdd(row.inbound, m, amt, "USD");
    }

    // ── ⑨ 头程现金（CNY；cash_date≥切点、matched、非预估、单据非作废；带 item_id）──
    const [fm] = await db.query<mysql.RowDataPacket[]>(
      `SELECT l.store_id, COALESCE(l.item_id,'') AS item_id, COALESCE(l.msku,'') AS msku,
              DATE_FORMAT(l.cash_date,'%Y-%m') AS m,
              ROUND(SUM(l.per_first_let_cost * l.delivery_num),4) AS amt
         FROM fact_shipping_first_let l
         JOIN fact_shipping_order o ON o.platform=l.platform AND o.shipping_code=l.shipping_code
        WHERE l.match_status='matched' AND l.store_id<>'' AND l.value_source<>'预估费用'
          AND o.shipping_status<>'已作废' AND l.cash_date >= ?
          AND DATE_FORMAT(l.cash_date,'%Y-%m') BETWEEN ? AND ? ${storeFilter ? " AND l.store_id=? " : " "}
        GROUP BY l.store_id, l.item_id, l.msku, m`,
      storeFilter ? [CUTOFF, from, to, storeFilter] : [CUTOFF, from, to]);
    for (const r of fm) {
      const store = String(r.store_id), m = String(r.m), amt = Number(r.amt) || 0;
      let item = String(r.item_id);
      if (!item) { const msku = String(r.msku); if (msku) item = mskuToItem.get(`${store}||${msku}`) ?? ""; }
      if (!item) { cellAdd(sRowOf(store).other, m, -amt, "CNY"); continue; }
      const row = rowOf(store, item);
      if (!row) { noteExcluded(store, item, amt, "exp"); continue; }
      cellAdd(row.firstmile, m, amt, "CNY");
    }

    // ── ⑩ 发货量份额表：sku → (店||item) → 发货量（采购拆分依据；需求方定：一律按实际发货量，禁用销量估算）──
    const [shipRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, COALESCE(sku,'') AS sku, COALESCE(item_id,'') AS item_id, SUM(delivery_num) AS qty
         FROM fact_shipping_first_let
        WHERE match_status='matched' AND store_id<>'' AND COALESCE(item_id,'')<>''
        GROUP BY store_id, sku, item_id`);
    const shipBySku = new Map<string, Map<string, number>>(); // sku → (store||item) → qty
    for (const r of shipRows) {
      const st = normStore(String(r.store_id)); if (!st) continue;
      const sku = String(r.sku), it = String(r.item_id), qy = Number(r.qty) || 0;
      if (!sku || !it || qy <= 0) continue;
      if (!shipBySku.has(sku)) shipBySku.set(sku, new Map());
      const mm = shipBySku.get(sku)!;
      const k = `${st}||${it}`;
      mm.set(k, (mm.get(k) ?? 0) + qy);
    }

    // ── ⑪ 采购现金（CNY；仅切点后、非作废）──
    // 归属（需求方 2026-08-14 拍板，不设日期切点、逐行判断）：
    //   A. sid 有效 → 归该店；店内该 sku 单 item 直落，多 item 按发货量份额拆
    //   B. sid=0/无效 → 按发货单 sku→(店,item) 发货量份额拆
    //   C. 均不可得 → 店铺级「未归属采购」，不摊到品、不判为缺陷（含 sid=8345 等查无店铺者）
    const [pur] = await db.query<mysql.RowDataPacket[]>(
      `SELECT i.sid AS store_id, COALESCE(i.sku,'') AS sku, DATE_FORMAT(c.order_time,'%Y-%m') AS m,
              ROUND(SUM(i.amount),4) AS amt
         FROM fact_purchase_cash_item i JOIN fact_purchase_cash c ON c.order_sn=i.order_sn
        WHERE c.order_time >= ? AND DATE_FORMAT(c.order_time,'%Y-%m') BETWEEN ? AND ?
          AND c.status_text <> '已作废'
        GROUP BY i.sid, i.sku, m`, [CUTOFF, from, to]);
    let purchaseUnattr = 0;
    for (const r of pur) {
      const sku = String(r.sku), m = String(r.m), amt = Number(r.amt) || 0;
      if (!sku || VIRTUAL.has(sku)) continue;
      const sid = normStore(String(r.store_id));
      const all = shipBySku.get(sku) ?? new Map<string, number>();
      // 候选份额：A 类只取该店的子项；B 类取全部
      const cand = new Map<string, number>();
      for (const [k, qy] of all.entries()) {
        if (sid && !k.startsWith(`${sid}||`)) continue;
        cand.set(k, qy);
      }
      if (cand.size === 0) {
        // A 类但该店无发货记录 → 仍可按 dim_product 唯一 item 直落（1店1item 的常见情形）
        if (sid) {
          const only: string[] = [];
          for (const p of skuPairs.get(sku) ?? []) if (p.startsWith(`${sid}||`)) only.push(p);
          if (only.length === 1) cand.set(only[0], 1);
        }
      }
      if (cand.size === 0) { // C 类
        if (storeFilter) continue;
        purchaseUnattr = r2(purchaseUnattr + amt);
        continue;
      }
      let tot = 0; for (const v of cand.values()) tot += v;
      const entries = Array.from(cand.entries());
      let allocated = 0;
      for (let i = 0; i < entries.length; i++) {
        const [k, qy] = entries[i];
        const isLast = i === entries.length - 1;
        const part = isLast ? r2(amt - allocated) : r2(amt * qy / tot);
        allocated = r2(allocated + part);
        if (part === 0) continue;
        const [st2, it2] = k.split("||");
        if (storeFilter && st2 !== storeFilter) continue;
        const row = rowOf(st2, it2);
        if (!row) { noteExcluded(st2, it2, part, "exp"); continue; }
        cellAdd(row.purchase, m, part, "CNY");
      }
    }

    // ── ⑫ 销量 + 期初池 FIFO 消耗（CNY）──
    // 期初池为 SKU 级；消耗按该 SKU 各 (店,item) 的结算销量份额摊。
    // 实证：YC00200+ 的 211 个 SKU 100% 不在期初池 → clean+yc200 口径下本列恒为 0；
    // FIFO 推进逻辑仍原样保留（老品第二批要用），池照常推进、只有选中区间才计成本。
    const [openRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT sku, snap_qty_0501, opening_unit_cost FROM biz_finance_opening_cost WHERE cutoff_date=?`, [CUTOFF]);
    const pool = new Map<string, { qty: number; unit: number }>();
    let openingValue = 0;
    for (const r of openRows) {
      const qy = Number(r.snap_qty_0501) || 0, un = Number(r.opening_unit_cost) || 0;
      pool.set(String(r.sku), { qty: qy, unit: un });
      openingValue = r2(openingValue + qy * un);
    }
    const [salesRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, settlement_month AS m, COALESCE(msku,'') AS msku,
              JSON_UNQUOTE(JSON_EXTRACT(extra_json,'$.localSku')) AS sku, SUM(sales_num) AS qty
         FROM fact_settlement_msku_monthly
        WHERE settlement_month BETWEEN ? AND ?
        GROUP BY store_id, m, msku, sku`, [CUTOFF_M, to]);
    const salesBySkuM = new Map<string, number>();        // sku||m → qty
    const salesByItem = new Map<string, number>();        // sku||m||store||item → qty
    for (const r of salesRows) {
      const sku = String(r.sku ?? ""); if (!sku || VIRTUAL.has(sku)) continue;
      const store = normStore(String(r.store_id)); if (!store) continue;
      const msku = String(r.msku);
      const item = msku ? (mskuToItem.get(`${store}||${msku}`) ?? "") : "";
      if (!item) continue; // 无法定位 item 的销量不参与 item 级摊派（金额不丢：期初池按 SKU 推进）
      const qy = Number(r.qty) || 0;
      const km = `${sku}||${String(r.m)}`;
      salesBySkuM.set(km, (salesBySkuM.get(km) ?? 0) + qy);
      const ki = `${km}||${store}||${item}`;
      salesByItem.set(ki, (salesByItem.get(ki) ?? 0) + qy);
    }
    let consumedValueAll = 0;
    for (const m of monthsOf(CUTOFF_M, to)) {
      for (const [sku, p] of pool.entries()) {
        if (p.qty <= 0) continue;
        const sold = salesBySkuM.get(`${sku}||${m}`) ?? 0;
        if (sold <= 0) continue;
        const consume = Math.min(p.qty, sold);
        p.qty -= consume;
        consumedValueAll = r2(consumedValueAll + consume * p.unit);
        if (m < from || m > to) continue; // 池照常推进，只有选中区间才计成本
        const shares: Array<{ k: string; q: number }> = [];
        const pref = `${sku}||${m}||`;
        for (const [k2, q2] of salesByItem.entries()) {
          if (k2.startsWith(pref)) shares.push({ k: k2.slice(pref.length), q: Number(q2) });
        }
        let allocated = 0;
        for (let i = 0; i < shares.length; i++) {
          const isLast = i === shares.length - 1;
          const cq = isLast ? consume - allocated : Math.round(consume * shares[i].q / sold);
          allocated += cq;
          if (cq <= 0) continue;
          const [st2, it2] = shares[i].k.split("||");
          if (storeFilter && st2 !== storeFilter) continue;
          const row = rowOf(st2, it2);
          if (!row) { noteExcluded(st2, it2, cq * p.unit, "exp"); continue; }
          row.opening_used_qty += cq;
          cellAdd(row.opening_cost, m, cq * p.unit, "CNY");
        }
      }
    }
    let poolRemainQty = 0, poolRemainValue = 0;
    for (const p of pool.values()) { poolRemainQty += p.qty; poolRemainValue = r2(poolRemainValue + p.qty * p.unit); }

    // 区间销量落行（展示列）
    for (const [k, qy] of salesByItem.entries()) {
      const parts = k.split("||"); // sku, m, store, item
      const m = parts[1], st2 = parts[2], it2 = parts[3];
      if (m < from || m > to) continue;
      if (storeFilter && st2 !== storeFilter) continue;
      const row = rowOf(st2, it2);
      if (row) row.sold_qty += Number(qy);
    }

    // ── ⑬ 汇总列（口径与 v1 逐字一致）──
    const fin = (c0: Cell): Cell => ({ c: r2(c0.c), u: r2(c0.u) });
    const outRows: V2Row[] = [];
    for (const r of rows.values()) {
      const rev: Cell = { c: r.sale.c + r.refund.c + r.comp.c, u: r.sale.u + r.refund.u + r.comp.u };
      const exp: Cell = {
        c: -r.wfs_fee.c - r.other_item.c + r.ads.c + r.storage.c + r.inbound.c + r.purchase.c + r.firstmile.c + r.opening_cost.c,
        u: -r.wfs_fee.u - r.other_item.u + r.ads.u + r.storage.u + r.inbound.u + r.purchase.u + r.firstmile.u + r.opening_cost.u,
      };
      r.revenue = fin(rev); r.expense = fin(exp);
      r.profit = { c: r2(rev.c - exp.c), u: r2(rev.u - exp.u) };
      (["sale", "refund", "comp", "wfs_fee", "other_item", "ads", "storage", "inbound",
        "purchase", "firstmile", "opening_cost"] as const).forEach((f) => { r[f] = fin(r[f]); });
      outRows.push(r);
    }
    outRows.sort((a, b) => b.profit.c - a.profit.c);
    for (const b of outOfScope.values()) { excluded.rows += 1; excluded.revenue.c += b.rev; excluded.expense.c += b.exp; }
    excluded.revenue = fin(excluded.revenue); excluded.expense = fin(excluded.expense);
    excluded.profit = { c: r2(excluded.revenue.c - excluded.expense.c), u: 0 };

    // ── ⑭ 惠州仓资产 KPI（与 v1 一致）──
    const [[hz]] = await db.query<mysql.RowDataPacket[]>(
      `SELECT ROUND(SUM(stock_cost),2) AS v, SUM(balance_num) AS q FROM fact_lingxing_batch
        WHERE wh_name='惠州仓库' AND balance_num>0`) as unknown as [mysql.RowDataPacket[]];

    // ── ⑮ 哨兵（比总量，与聚合键无关；数值应与 v1 完全一致）──
    const [[tp]] = await db.query<mysql.RowDataPacket[]>(
      `SELECT ROUND(SUM(total_payable),2) AS v FROM fact_reconciliation_period
        WHERE DATE_FORMAT(period_end,'%Y-%m') BETWEEN ? AND ? ${storeCond}`, sf([from, to])) as unknown as [mysql.RowDataPacket[]];
    const sentinels = [
      { name: "回款完整性", expect: Number(tp?.v ?? 0), actual: r2(reconAll), note: "Σ对账明细 = Σ账期Total Payable（USD）" },
      { name: "广告管道vs账单", expect: r2(-pipeSent.ad), actual: r2(adsPipeTotal), note: "fact_ads_product_daily vs recon ad_platform（USD；SEM单列不含）" },
      { name: "仓储管道vs账单", expect: r2(-pipeSent.storage), actual: r2(storPipeTotal), note: "仓储报告导入 vs recon storage（USD；账期起日对齐）" },
      { name: "入库运输管道vs账单", expect: r2(-pipeSent.inbound), actual: r2(inbPipeTotal), note: "分摊表 vs recon inbound_transport（USD）" },
      { name: "期初恒等", expect: r2(openingValue), actual: r2(consumedValueAll + poolRemainValue), note: "全时段累计消耗额 + 池余量 = 期初（FIFO 真实核算）" },
    ].map((x) => ({ ...x, diff: r2(x.actual - x.expect), ok: Math.abs(x.actual - x.expect) <= Math.max(50, Math.abs(x.expect) * 0.02) }));

    res.json({
      from, to, cutoff: CUTOFF, months, scope, family,
      kpi: {
        opening_value: r2(openingValue),
        pool_remain_qty: poolRemainQty, pool_remain_value: r2(poolRemainValue),
        huizhou_value: Number(hz?.v ?? 0), huizhou_qty: Number(hz?.q ?? 0),
        profit_cny: r2(outRows.reduce((x, r) => x + r.profit.c, 0)),
        profit_usd: r2(outRows.reduce((x, r) => x + r.profit.u, 0)),
        row_cnt: outRows.length,
        clean_cnt: outRows.filter((r) => r.is_clean).length,
      },
      rows: outRows,
      store_rows: [
        ...Array.from(storeRows.values()).map((r0) => ({
          ...r0, store_name: storeNames.get(r0.store_id) ?? r0.store_id,
          sem: fin(r0.sem), review: fin(r0.review), comp: fin(r0.comp),
          other: fin(r0.other), ads_unmapped: fin(r0.ads_unmapped), purchase_unmapped: fin(r0.purchase_unmapped),
        })),
        ...(purchaseUnattr !== 0 && !storeFilter ? [{
          store_id: "__UNATTR_PURCHASE__", store_name: "（未归属采购·待发货单补全店铺）",
          sem: zc(), review: zc(), comp: zc(), other: zc(), ads_unmapped: zc(),
          purchase_unmapped: { c: r2(purchaseUnattr), u: rateOf(to) > 0 ? r2(purchaseUnattr / rateOf(to)) : 0 },
          unmapped_cnt: 0,
        }] : []),
      ],
      excluded, // scope 之外 item 的汇总（不丢弃，用于核总量）
      sentinels, fx_missing: fxMissing,
      excluded_note: "海外仓/Miami虚拟库存/XY2007/DC001/QH888 整行豁免；切点前采购头程现金不计（一刀切）；" +
        "佣金已含在回款销售净额（沃尔玛结算口径），不单列避免双算；" +
        "scope=clean 仅出「1店1item」可直归 item，其余汇总在 excluded（第二批接分摊逻辑）",
    });
  } catch (e) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally { await db.end().catch(() => undefined); }
});

export default router;
