/**
 * salesDetailV2Routes.ts — 每日销售明细 V2（2026-08-19 批C-1）
 * 挂载：/api/sales-detail-v2（adminServer 全局 authMiddleware 之内）
 *
 * GET /list  逐日明细（服务端分页/排序/筛选）；GET /summary 合计行 + 元信息
 *
 * 为什么新建：旧「每日销售明细」直查 raw_feishu_table(<REDACTED_FEISHU_SHEET_ID>)，违反分层铁律（前端禁直查RAW）。
 *   V2 全部读 FACT 层，并补齐订单利润V2那套新数据链。旧页并行对账，后续与旧Beta一同下线。
 *
 * 行粒度：业务日 × 店铺 × MSKU（逐日一行，同品多日多行）。
 * 口径（与订单利润V2一致，逐日化）：
 *   销售额/销量=fact_profit_daily当日值，扣当日送样单（全额折扣单，raw_mp_order_discount）；
 *   退货=fact_refund_daily当日；广告=fact_ads_product_daily当日全类型(SP+SB+SV+SEM)按MSKU销售额份额分摊；
 *   WFS配送费/佣金/采购/头程=当日快照单价×当日销量（佣金=当日销售额×费率）；仓储=fact_storage_fee_daily当日日摊；
 *   ▲WFS可售库存=当日历史快照（与旧明细页一致，不同于订单利润V2的"最新值"）；
 *   ▲退货率30天=以查询结束日为锚的品级滚动值（同品各行相同，与订单利润V2一致）；
 *   ▲运营日志=biz_product_operation_log 当日 log_content（空=运营无动作）；
 *   CS测品与人工作废名单剔除；成本为当日历史快照价。
 * 窗口：默认7天/上限31天；**锁定单品时（关键词精确命中单一MSKU或商品ID）放开至一年**。
 * 铁律：全程只读；密钥走环境变量。
 */
import { Router, Request, Response } from "express";
import * as mysql from "mysql2/promise";

const router = Router();
const EXCHANGE_RATE = 6.6;
const MANUAL_EXCLUDE_ITEMS = new Set<string>(["20090164596", "20706361834"]); // 与 orderProfitV2Routes 同步维护
const commissionRate = (storeName: string): number =>
  (storeName.includes("CN2501") || storeName.includes("CN2502")) ? 0.15 : 0.12;
const r2 = (v: number): number => Math.round(v * 100) / 100;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const MAX_DAYS_DEFAULT = 31;
const MAX_DAYS_SINGLE_ITEM = 366;

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

interface Ctx {
  from: string; to: string; latest: string; days: number;
  singleItem: boolean; kwType: string; kw: string;
  stores: string[]; owners: string[];
  stockState: string; costState: string;
  gmMin: number | null; gmMax: number | null; adMin: number | null; adMax: number | null;
}

function parseNum(v: unknown): number | null {
  const n = parseFloat(String(v ?? ""));
  return Number.isFinite(n) ? n : null;
}
function parseList(v: unknown): string[] {
  const s = String(v ?? "").trim();
  return s ? s.split(",").map((x) => x.trim()).filter(Boolean) : [];
}

/** 解析查询上下文（含窗口校验：锁定单品放宽至一年） */
async function buildCtx(db: mysql.Connection, req: Request): Promise<{ ctx?: Ctx; error?: string }> {
  // 2026-08-22 第六单：latest 取「利润表」与「fast 兜底表」的较大值。
  //   利润链路滞后到 T-3、fast 表已到 T-1；只看利润表则页面默认永远看不到最近两天。
  //   前端 anchorDate() 用的就是这个值，快捷「近N天」自动覆盖到 T-1，**前端无需改动**。
  const [mx] = await db.execute(
    `SELECT DATE_FORMAT(GREATEST(
              COALESCE((SELECT MAX(stat_date) FROM fact_profit_daily WHERE platform='walmart'), '1970-01-01'),
              COALESCE((SELECT MAX(stat_date) FROM fact_sales_fast_daily WHERE platform='walmart'), '1970-01-01')
            ), '%Y-%m-%d') d`);
  const latest = String((mx as Array<Record<string, unknown>>)[0]?.d ?? "");
  let to = String(req.query.to ?? "").trim() || latest;
  let from = String(req.query.from ?? "").trim() ||
    new Date(Date.parse(`${to}T00:00:00Z`) - 6 * 86400000).toISOString().slice(0, 10);
  if (!DATE_RE.test(from) || !DATE_RE.test(to)) return { error: "from/to 格式须为 YYYY-MM-DD" };
  if (from > to) [from, to] = [to, from];
  const days = Math.round((Date.parse(to) - Date.parse(from)) / 86400000) + 1;

  const kwType = String(req.query.kw_type ?? "keyword").trim();
  const kw = String(req.query.kw ?? "").trim();
  // 锁定单品判定：按 MSKU 或 商品ID 搜索，且该关键词在 dim_product 中命中唯一 MSKU
  let singleItem = false;
  if (kw && (kwType === "msku" || kwType === "item_id")) {
    const col = kwType === "msku" ? "msku" : "item_id";
    const [hit] = await db.execute(
      `SELECT COUNT(DISTINCT msku) c FROM dim_product WHERE platform='walmart' AND ${col} LIKE ?`, [`%${kw}%`]);
    singleItem = Number((hit as Array<Record<string, unknown>>)[0]?.c ?? 0) === 1;
  }
  const maxDays = singleItem ? MAX_DAYS_SINGLE_ITEM : MAX_DAYS_DEFAULT;
  if (days > maxDays) {
    return { error: singleItem
      ? `单品查询最长一年（当前 ${days} 天）`
      : `日期范围最长 ${MAX_DAYS_DEFAULT} 天（当前 ${days} 天）；按 MSKU 或商品ID 锁定单品后可查一年` };
  }
  return { ctx: {
    from, to, latest, days, singleItem, kwType, kw,
    stores: parseList(req.query.stores), owners: parseList(req.query.owners),
    stockState: String(req.query.stock_state ?? "").trim(),
    costState: String(req.query.cost_state ?? "").trim(),
    gmMin: parseNum(req.query.gm_min), gmMax: parseNum(req.query.gm_max),
    adMin: parseNum(req.query.ad_min), adMax: parseNum(req.query.ad_max),
  } };
}

interface DetailRow {
  stat_date: string; store_id: string; store_name: string; owner: string;
  item_id: string; msku: string; sku: string; product_name: string;
  qty: number; sales: number; excluded_sales: number;
  refund_qty: number; refund_amount: number; refund_rate_30d: number | null;
  ad: number; wfs: number; commission: number; purchase_cost: number; first_leg: number; storage: number;
  pc_unit: number; fl_unit: number; storage_unit: number; wfs_unit: number;
  wfs_stock: number; gross_profit_old: number; order_profit: number;
  profit_rate: number | null; roi: number | null; ad_ratio: number | null;
  cost_status: string; ops_log: string; sys_ops_log: string; sys_ops_red: string;
  is_fast: boolean;   // true = T-1 兜底行（fact_sales_fast_daily 建出），只有销量/销售额/库存
}

/** 核心取数：一次拉窗口内全部逐日行（后续在内存做筛选/排序/分页；窗口已限幅，行数可控） */
async function fetchRows(db: mysql.Connection, ctx: Ctx): Promise<DetailRow[]> {
  const { from, to } = ctx;
  const win30Start = new Date(Date.parse(`${to}T00:00:00Z`) - 29 * 86400000).toISOString().slice(0, 10);

  // 1) 利润FACT基座（逐日）
  const [baseRows] = await db.execute(
    `SELECT DATE_FORMAT(f.stat_date,'%Y-%m-%d') d, f.store_id, f.msku, f.item_id,
            COALESCE(f.store_name,'') store_name, f.sales_amount sales, f.gross_profit gp,
            CAST(JSON_UNQUOTE(JSON_EXTRACT(f.extra_json,'$.sales_qty')) AS DECIMAL(12,2)) qty,
            CAST(JSON_UNQUOTE(JSON_EXTRACT(f.extra_json,'$.wfs_fee_usd')) AS DECIMAL(12,4)) wfs_unit,
            CAST(JSON_UNQUOTE(JSON_EXTRACT(f.extra_json,'$.purchase_cost_cny')) AS DECIMAL(12,4)) pc_unit,
            CAST(JSON_UNQUOTE(JSON_EXTRACT(f.extra_json,'$.first_leg_cost_cny')) AS DECIMAL(12,4)) fl_unit
     FROM fact_profit_daily f
     WHERE f.platform='walmart' AND f.stat_date BETWEEN ? AND ? AND f.msku NOT LIKE 'CS%'`, [from, to]);

  const rows = new Map<string, DetailRow>();
  const key = (d: string, s: string, m: string): string => `${d}|${s}|${m}`;
  for (const b of baseRows as Array<Record<string, unknown>>) {
    const itemId = String(b.item_id ?? "");
    if (MANUAL_EXCLUDE_ITEMS.has(itemId)) continue;
    const storeName = String(b.store_name ?? "");
    const qty = Number(b.qty ?? 0), sales = Number(b.sales ?? 0);
    const pcU = Number(b.pc_unit ?? 0), flU = Number(b.fl_unit ?? 0);
    rows.set(key(String(b.d), String(b.store_id), String(b.msku)), {
      stat_date: String(b.d), store_id: String(b.store_id), store_name: storeName, owner: "",
      item_id: itemId, msku: String(b.msku), sku: "", product_name: "",
      qty, sales, excluded_sales: 0,
      refund_qty: 0, refund_amount: 0, refund_rate_30d: null,
      // 2026-08-21 送样成本剔除修复：此处的 qty **仍含送样单**（§2 才剔除），
      // 故三项随销量线性的成本一律置 0，改到 §11 收尾用净销量统一计算。**禁止在建行时算成本。**
      ad: 0, wfs: 0, commission: 0,
      purchase_cost: 0, first_leg: 0, storage: 0,
      pc_unit: pcU, fl_unit: flU, storage_unit: 0, wfs_unit: Number(b.wfs_unit ?? 0),
      wfs_stock: 0, gross_profit_old: Number(b.gp ?? 0), order_profit: 0,
      profit_rate: null, roi: null, ad_ratio: null, cost_status: "-", ops_log: "",
      sys_ops_log: "", sys_ops_red: "", is_fast: false,
    });
  }

  // 1.5) T-1 兜底基座（2026-08-22 第六单）
  //   利润链路（fact_profit_daily）滞后到 T-3，最近两天没有任何行 ⇒ 页面看不到昨天。
  //   此处用 fact_sales_fast_daily（订单接口现算，已到 T-1）补出这些日期的行。
  //   **只补「利润表当日一行都没有」的日期 —— 按日判断，不按全局。**
  //   某日利润表已有部分行则不补：两套口径混在同一天里，比缺数更糟。
  //   兜底行只带销量/销售额；库存由 §7 按 snapshot_date 逐日 join 自动带上；
  //   送样单由 §2 按 (日,店,MSKU) 自动扣减（fast 的 sales_amount 是折前含送样，正好对上）；
  //   成本与利润在 §11 一律清掉，cost_status 记「−」。
  const profitDates = new Set<string>();
  for (const r of rows.values()) profitDates.add(r.stat_date);
  const [fastBase] = await db.execute(
    `SELECT DATE_FORMAT(stat_date,'%Y-%m-%d') d, store_id, msku, item_id,
            sales_qty qty, sales_amount amt
     FROM fact_sales_fast_daily
     WHERE platform='walmart' AND stat_date BETWEEN ? AND ? AND msku NOT LIKE 'CS%'`, [from, to]);
  let fastAdded = 0;
  for (const f of fastBase as Array<Record<string, unknown>>) {
    const d = String(f.d);
    if (profitDates.has(d)) continue;
    const itemId = String(f.item_id ?? "");
    if (MANUAL_EXCLUDE_ITEMS.has(itemId)) continue;
    const k = key(d, String(f.store_id), String(f.msku));
    if (rows.has(k)) continue;
    rows.set(k, {
      stat_date: d, store_id: String(f.store_id), store_name: "", owner: "",
      item_id: itemId, msku: String(f.msku), sku: "", product_name: "",
      qty: Number(f.qty ?? 0), sales: Number(f.amt ?? 0), excluded_sales: 0,
      refund_qty: 0, refund_amount: 0, refund_rate_30d: null,
      ad: 0, wfs: 0, commission: 0,
      purchase_cost: 0, first_leg: 0, storage: 0,
      pc_unit: 0, fl_unit: 0, storage_unit: 0, wfs_unit: 0,
      wfs_stock: 0, gross_profit_old: 0, order_profit: 0,
      profit_rate: null, roi: null, ad_ratio: null, cost_status: "-", ops_log: "",
      sys_ops_log: "", sys_ops_red: "", is_fast: true,
    });
    fastAdded += 1;
  }
  if (fastAdded > 0) console.log(`[salesDetailV2] T-1兜底行 ${fastAdded} 条（窗口 ${from}~${to}）`);

  // 2) 送样单（当日全额折扣单）
  const [smp] = await db.execute(
    `SELECT DATE_FORMAT(purchase_date,'%Y-%m-%d') d, store_id, msku,
            SUM(quantity) qty, ROUND(SUM(item_price_amount),2) amt
     FROM raw_mp_order_discount
     WHERE order_status <> 7 AND ABS(discount_amount) >= item_price_amount - 0.01
       AND purchase_date BETWEEN ? AND ? AND msku NOT LIKE 'CS%'
     GROUP BY d, store_id, msku`, [from, to]);
  for (const s of smp as Array<Record<string, unknown>>) {
    const r = rows.get(key(String(s.d), String(s.store_id), String(s.msku)));
    if (!r) continue;
    r.excluded_sales = Number(s.amt ?? 0);
    r.sales = Math.max(0, r.sales - r.excluded_sales);
    r.qty = Math.max(0, r.qty - Number(s.qty ?? 0));
  }

  // 3) 退货（当日）
  const [ref] = await db.execute(
    `SELECT DATE_FORMAT(refund_date,'%Y-%m-%d') d, store_id, msku, SUM(refund_qty) q, SUM(refund_amount) amt
     FROM fact_refund_daily WHERE platform='walmart' AND refund_date BETWEEN ? AND ? AND msku NOT LIKE 'CS%'
     GROUP BY d, store_id, msku`, [from, to]);
  for (const x of ref as Array<Record<string, unknown>>) {
    const k = key(String(x.d), String(x.store_id), String(x.msku));
    const r = rows.get(k);
    if (r) { r.refund_qty = Number(x.q ?? 0); r.refund_amount = Number(x.amt ?? 0); }
  }

  // 4) 仓储费日摊（当日）
  const [sto] = await db.execute(
    `SELECT DATE_FORMAT(fee_date,'%Y-%m-%d') d, store_id, sku msku, SUM(storage_fee) amt
     FROM fact_storage_fee_daily WHERE platform='walmart' AND fee_date BETWEEN ? AND ? AND sku NOT LIKE 'CS%'
     GROUP BY d, store_id, sku`, [from, to]);
  for (const x of sto as Array<Record<string, unknown>>) {
    const r = rows.get(key(String(x.d), String(x.store_id), String(x.msku)));
    if (r) r.storage = Number(x.amt ?? 0);
  }

  // 5) 广告（当日 item 级 → 按当日该店该item各MSKU销售额份额分摊）
  const [ads] = await db.execute(
    `SELECT DATE_FORMAT(stat_date,'%Y-%m-%d') d, store_id, item_id, SUM(ad_spend) ad
     FROM fact_ads_product_daily WHERE platform='walmart' AND stat_date BETWEEN ? AND ?
     GROUP BY d, store_id, item_id`, [from, to]);
  const byItemDay = new Map<string, DetailRow[]>();
  for (const r of rows.values()) {
    if (!r.item_id) continue;
    const k = `${r.stat_date}|${r.store_id}|${r.item_id}`;
    const arr = byItemDay.get(k) ?? [];
    arr.push(r); byItemDay.set(k, arr);
  }
  for (const a of ads as Array<Record<string, unknown>>) {
    const ad = Number(a.ad ?? 0);
    if (ad === 0) continue;
    const targets = byItemDay.get(`${a.d}|${a.store_id}|${a.item_id}`);
    if (!targets || targets.length === 0) continue; // 无对应明细行（CS/已剔除/无当日行）→ 不摊
    const salesSum = targets.reduce((s, t) => s + t.sales, 0);
    for (const t of targets) t.ad += salesSum > 0 ? ad * (t.sales / salesSum) : ad / targets.length;
  }

  // 6) 退货率30天（品级，锚点=to；同品各行相同）
  const [q30] = await db.execute(
    `SELECT store_id, msku, SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(extra_json,'$.sales_qty')) AS DECIMAL(12,2))) q
     FROM fact_profit_daily WHERE platform='walmart' AND stat_date BETWEEN ? AND ? AND msku NOT LIKE 'CS%'
     GROUP BY store_id, msku`, [win30Start, to]);
  const q30Map = new Map<string, number>();
  for (const x of q30 as Array<Record<string, unknown>>) q30Map.set(`${x.store_id}|${x.msku}`, Number(x.q ?? 0));
  const [r30] = await db.execute(
    `SELECT store_id, msku, SUM(refund_qty) q FROM fact_refund_daily
     WHERE platform='walmart' AND refund_date BETWEEN ? AND ? AND msku NOT LIKE 'CS%'
     GROUP BY store_id, msku`, [win30Start, to]);
  const r30Map = new Map<string, number>();
  for (const x of r30 as Array<Record<string, unknown>>) r30Map.set(`${x.store_id}|${x.msku}`, Number(x.q ?? 0));

  // 7) 当日库存快照（逐日，与旧明细页一致）
  const [inv] = await db.execute(
    `SELECT DATE_FORMAT(snapshot_date,'%Y-%m-%d') d, store_id, msku, SUM(COALESCE(wfs_available_stock,0)) wfs
     FROM fact_inventory_daily WHERE platform='walmart' AND snapshot_date BETWEEN ? AND ? AND msku NOT LIKE 'CS%'
     GROUP BY d, store_id, msku`, [from, to]);
  for (const x of inv as Array<Record<string, unknown>>) {
    const r = rows.get(key(String(x.d), String(x.store_id), String(x.msku)));
    if (r) r.wfs_stock = Number(x.wfs ?? 0);
  }

  // 8) 仓储单价（最新账期）
  const [stoUnit] = await db.execute(
    `SELECT f.store_id, f.sku msku, f.unit_fee_standard u FROM fact_wfs_storage_fee f
     JOIN (SELECT store_id, sku, MAX(report_start) ms FROM fact_wfs_storage_fee
           WHERE platform='walmart' GROUP BY store_id, sku) m
       ON m.store_id=f.store_id AND m.sku=f.sku AND m.ms=f.report_start
     WHERE f.platform='walmart' AND f.unit_fee_standard IS NOT NULL`);
  const stoUnitMap = new Map<string, number>();
  for (const x of stoUnit as Array<Record<string, unknown>>) stoUnitMap.set(`${x.store_id}|${x.msku}`, Number(x.u ?? 0));

  // 9) 产品档案（负责人/SKU/品名）+ 店铺名
  const [dp] = await db.execute(
    `SELECT store_id, msku, MAX(COALESCE(owner,'')) owner, MAX(COALESCE(sku,'')) sku,
            MAX(COALESCE(product_name, item_name, '')) pname, MAX(COALESCE(item_id,'')) item_id
     FROM dim_product WHERE platform='walmart' GROUP BY store_id, msku`);
  const dpMap = new Map<string, { owner: string; sku: string; pname: string; item_id: string }>();
  for (const x of dp as Array<Record<string, unknown>>) {
    dpMap.set(`${x.store_id}|${x.msku}`, {
      owner: String(x.owner ?? ""), sku: String(x.sku ?? ""),
      pname: String(x.pname ?? ""), item_id: String(x.item_id ?? ""),
    });
  }
  const [st] = await db.execute(`SELECT store_id, MAX(store_name) n FROM dim_store WHERE platform='walmart' GROUP BY store_id`);
  const stMap = new Map<string, string>();
  for (const x of st as Array<Record<string, unknown>>) stMap.set(String(x.store_id), String(x.n ?? ""));

  // 10) 运营日志（当日）
  const [logs] = await db.execute(
    `SELECT DATE_FORMAT(log_date,'%Y-%m-%d') d, store_id, msku, COALESCE(log_content,'') c
     FROM biz_product_operation_log WHERE log_date BETWEEN ? AND ?`, [from, to]);
  for (const x of logs as Array<Record<string, unknown>>) {
    const r = rows.get(key(String(x.d), String(x.store_id), String(x.msku)));
    if (r) r.ops_log = String(x.c ?? "").trim();
  }

  // 10.1) 系统运营日志（2026-08-22 第四单）：event_ops_action_log 当日差分事件。
  //   V2 行粒度=日期+店铺+MSKU（无 item_id），同 MSKU 下多个 item 的事件在此合并。
  //   highlight=1 单独进 sys_ops_red，前端红色加粗。只读 EVENT 层，不写任何表。
  //   2026-08-24 第八单：按需求方定稿格式重排——日期一行/类型分组/广告组二级分组/中文状态/换行
  //   （规范原文 _deploy_tmp/audit/20260823_系统运营日志_展示格式规范.md；弹窗已是 pre-wrap，换行直接生效）。
  const [sysEvs] = await db.execute(
    `SELECT DATE_FORMAT(event_date,'%Y-%m-%d') d, store_id, msku,
            action_type, object_type, object_name, old_value, new_value,
            ad_group_name, match_type, log_content, highlight
       FROM event_ops_action_log
      WHERE platform='walmart' AND event_date BETWEEN ? AND ?
      ORDER BY highlight DESC, id`, [from, to]);
  const SYS_ST_CN: Record<string, string> = { live: "进行中", paused: "暂停", completed: "结束", proposal: "待审核",
    enabled: "启用", disabled: "禁用", scheduled: "已计划", rescheduled: "重新计划" };
  const SYS_MT_CN: Record<string, string> = { exact: "精准", broad: "广泛", phrase: "词组" };
  const sysStCn = (v: unknown): string => SYS_ST_CN[String(v ?? "").toLowerCase()] ?? (String(v ?? "") || "空");
  const sysMt = (v: unknown): string => { const c = SYS_MT_CN[String(v ?? "").toLowerCase()]; return c ? `（${c}）` : ""; };
  const sysStripDate = (v: unknown): string => String(v ?? "").trim().replace(/^\d{4}-\d{2}-\d{2}\s*/, "");
  /** 一个 (日期,店,MSKU) 键内的事件 → 定稿格式多行文本（R1 日期一行 / R3 类型分组 / R5 广告组行 / R8 中文状态） */
  const formatSysOps = (evs: Array<Record<string, unknown>>): string => {
    if (evs.length === 0) return "";
    const date = String(evs[0].d ?? "");
    const priceLines: string[] = [];
    const adTopLines: string[] = [];
    const kwByGroup = new Map<string, string[]>();
    for (const e of evs) {
      const at = String(e.action_type ?? ""), name = String(e.object_name ?? "");
      const ov = String(e.old_value ?? ""), nv = String(e.new_value ?? "");
      if (at === "price_change") { priceLines.push(sysStripDate(e.log_content)); continue; }
      if (String(e.object_type) === "keyword") {
        const g = String(e.ad_group_name ?? "") || "(未知广告组)";
        const arr = kwByGroup.get(g) ?? [];
        if (at === "keyword_add") arr.push(`新增关键词：${name}${sysMt(e.match_type)}`);
        else if (at === "ad_bid_change") arr.push(`${name}${sysMt(e.match_type)}：${ov} ${Number(nv) > Number(ov) ? "上调至" : "降至"} ${nv}`);
        else arr.push(`${name}${sysMt(e.match_type)}：${sysStCn(ov)} 改为 ${sysStCn(nv)}`);
        kwByGroup.set(g, arr);
        continue;
      }
      if (at === "campaign_add") adTopLines.push(`新增广告活动：${name}`);
      else if (at === "group_add") adTopLines.push(`新增广告组：${name}`);
      else if (at === "ad_budget_change") adTopLines.push(`${name}：预算 ${ov} ${Number(nv) > Number(ov) ? "上调至" : "下调至"} ${nv}`);
      else if (at === "ad_strategy_change") adTopLines.push(`${name}：竞价策略 ${ov || "空"} 改为 ${nv}`);
      else adTopLines.push(`${name}：${sysStCn(ov)} 改为 ${sysStCn(nv)}`);
    }
    const out: string[] = [date];
    out.push(...priceLines);
    if (adTopLines.length || kwByGroup.size) {
      out.push("广告日志");
      out.push(...adTopLines);
      for (const [g, lines] of kwByGroup) { out.push(`广告组：${g}`); out.push(...lines); }
    }
    return out.join("\n");
  };
  const sysEvByKey = new Map<string, Array<Record<string, unknown>>>();
  for (const x of sysEvs as Array<Record<string, unknown>>) {
    const k = key(String(x.d), String(x.store_id), String(x.msku));
    const arr = sysEvByKey.get(k) ?? [];
    arr.push(x);
    sysEvByKey.set(k, arr);
  }
  for (const [k, arr] of sysEvByKey) {
    const r = rows.get(k);
    if (!r) continue;
    const red = arr.filter((e) => Number(e.highlight) === 1);
    const normal = arr.filter((e) => Number(e.highlight) !== 1);
    if (red.length) r.sys_ops_red = red.map((e) => sysStripDate(e.log_content)).filter(Boolean).join("\n");
    const txt = formatSysOps(normal);
    if (txt) r.sys_ops_log = txt;
  }

  // 11) 收尾计算
  for (const r of rows.values()) {
    const d = dpMap.get(`${r.store_id}|${r.msku}`);
    if (d) { r.owner = d.owner; r.sku = d.sku; r.product_name = d.pname; if (!r.item_id) r.item_id = d.item_id; }
    if (!r.store_name) r.store_name = stMap.get(r.store_id) ?? r.store_id;
    r.storage_unit = stoUnitMap.get(`${r.store_id}|${r.msku}`) ?? 0;
    // ── 2026-08-21 送样成本剔除修复（需求方报障：YC00263 08-14 销量0 却背 采购2.47+头程0.82）──
    // 此刻 r.qty 已是**剔除送样后的净销量**（§2 已扣），三项随销量线性的成本必须用它算。
    // 修复前在建行时按**含送样**的 qty 算死，送样单的采购/头程/WFS 仍进订单利润；
    // 实测 31 天窗口低估利润 $4726.89（采购1787.31 + 头程706.33 + WFS2233.26，见 probeSampleOrderCostLeak）。
    // 需求方 2026-08-21 定：送样成本从运营端订单利润**彻底移除，不进任何其它口径**（财务报表另说）。
    // ⚠️ 位置要求：必须在下方 cost_status 判定**之前**——那里读 r.wfs <= 0。
    r.wfs           = r.wfs_unit * r.qty;
    r.purchase_cost = r.pc_unit  * r.qty / EXCHANGE_RATE;
    r.first_leg     = r.fl_unit  * r.qty / EXCHANGE_RATE;
    r.commission = r.sales * commissionRate(r.store_name);
    const q = q30Map.get(`${r.store_id}|${r.msku}`) ?? 0;
    const rq = r30Map.get(`${r.store_id}|${r.msku}`) ?? 0;
    r.refund_rate_30d = q > 0 ? Math.round((rq / q) * 10000) / 10000 : null;
    r.order_profit = r.sales - r.ad - r.wfs - r.commission - r.purchase_cost - r.first_leg - r.refund_amount - r.storage;
    r.profit_rate = r.sales > 0 ? Math.round((r.order_profit / r.sales) * 10000) / 10000 : null;
    r.ad_ratio = r.sales > 0 ? Math.round((r.ad / r.sales) * 10000) / 10000 : null;
    const denom = (r.pc_unit + r.fl_unit) * r.qty;
    r.roi = denom > 0 ? Math.round((r.order_profit * EXCHANGE_RATE / denom) * 100) / 100 : null;
    const missing: string[] = [];
    if (r.qty > 0) {
      if (r.pc_unit <= 0) missing.push("缺采购成本");
      if (r.fl_unit <= 0) missing.push("缺头程成本");
      if (r.wfs <= 0) missing.push("缺WFS配送费");
    }
    r.cost_status = r.qty > 0 ? (missing.length ? missing.join("/") : "完整") : "-";
    // 2026-08-22 第六单：兜底行没有成本与利润基础数据，上面算出来的不是真实值——
    //   commission 会算成「销售额×费率」的估算、order_profit 会算成「销售额减掉几项」，
    //   cost_status 会显示「缺采购成本/缺头程成本/缺WFS配送费」，但那不是缺失、是还没算。
    //   这几项一律清掉，成本状态改显示「−」，等权威数据到位后重算。
    //   **退款额与仓储费不清**——那两项若当日真有数据就是真实值，清掉等于隐瞒。
    if (r.is_fast) {
      r.commission = 0;
      r.order_profit = 0;
      r.profit_rate = null; r.roi = null; r.ad_ratio = null;
      r.cost_status = "-";
    }
    // 数值规整
    r.sales = r2(r.sales); r.excluded_sales = r2(r.excluded_sales); r.qty = Math.round(r.qty);
    r.refund_qty = Math.round(r.refund_qty); r.refund_amount = r2(r.refund_amount);
    r.ad = r2(r.ad); r.wfs = r2(r.wfs); r.commission = r2(r.commission);
    r.purchase_cost = r2(r.purchase_cost); r.first_leg = r2(r.first_leg); r.storage = r2(r.storage);
    r.pc_unit = Math.round(r.pc_unit * 100) / 100; r.fl_unit = Math.round(r.fl_unit * 100) / 100;
    r.wfs_unit = Math.round(r.wfs_unit * 100) / 100;
    r.storage_unit = Math.round(r.storage_unit * 1e6) / 1e6;
    r.wfs_stock = Math.round(r.wfs_stock); r.gross_profit_old = r2(r.gross_profit_old);
    r.order_profit = r2(r.order_profit);
  }
  return Array.from(rows.values());
}

function applyFilters(all: DetailRow[], ctx: Ctx): DetailRow[] {
  return all.filter((r) => {
    // 全零行不显示（与订单利润V2一致；运营日志不参与非零判定）
    const anyNonZero = r.sales !== 0 || r.excluded_sales !== 0 || r.qty !== 0 || r.refund_qty !== 0 ||
      r.refund_amount !== 0 || r.ad !== 0 || r.wfs !== 0 || r.commission !== 0 ||
      r.purchase_cost !== 0 || r.first_leg !== 0 || r.storage !== 0 || r.wfs_stock !== 0 ||
      r.gross_profit_old !== 0 || r.order_profit !== 0;
    if (!anyNonZero) return false;
    if (ctx.kw) {
      const k = ctx.kw.toLowerCase();
      const hit = ctx.kwType === "keyword"
        ? (r.item_id.toLowerCase().includes(k) || r.msku.toLowerCase().includes(k) || r.store_name.toLowerCase().includes(k) || r.product_name.toLowerCase().includes(k))
        : String((r as unknown as Record<string, unknown>)[ctx.kwType] ?? "").toLowerCase().includes(k);
      if (!hit) return false;
    }
    if (ctx.stores.length && !ctx.stores.includes(r.store_id)) return false;
    if (ctx.owners.length && !ctx.owners.includes(r.owner)) return false;
    if (ctx.stockState === "has" && !(r.wfs_stock > 0)) return false;
    if (ctx.stockState === "none" && r.wfs_stock > 0) return false;
    if (ctx.costState === "full" && r.cost_status !== "完整") return false;
    if (ctx.costState === "missing" && (r.cost_status === "完整" || r.cost_status === "-")) return false;
    const gm = r.sales > 0 ? r.gross_profit_old / r.sales : null;
    if (ctx.gmMin !== null && (gm === null || gm * 100 < ctx.gmMin)) return false;
    if (ctx.gmMax !== null && (gm === null || gm * 100 > ctx.gmMax)) return false;
    if (ctx.adMin !== null && (r.ad_ratio === null || r.ad_ratio * 100 < ctx.adMin)) return false;
    if (ctx.adMax !== null && (r.ad_ratio === null || r.ad_ratio * 100 > ctx.adMax)) return false;
    return true;
  });
}

router.get("/list", async (req: Request, res: Response) => {
  const db = await getDb();
  try {
    const { ctx, error } = await buildCtx(db, req);
    if (!ctx) { res.status(400).json({ error }); return; }
    const filtered = applyFilters(await fetchRows(db, ctx), ctx);

    const sortKey = String(req.query.sort ?? "stat_date");
    const sortDir = String(req.query.dir ?? "desc") === "asc" ? 1 : -1;
    filtered.sort((a, b) => {
      const av = (a as unknown as Record<string, unknown>)[sortKey];
      const bv = (b as unknown as Record<string, unknown>)[sortKey];
      if (typeof av === "number" || typeof bv === "number" || av === null || bv === null) {
        return ((Number(av ?? -Infinity)) - (Number(bv ?? -Infinity))) * sortDir;
      }
      return String(av ?? "").localeCompare(String(bv ?? "")) * sortDir;
    });

    const page = Math.max(1, Number(req.query.page ?? 1));
    const pageSize = Math.min(500, Math.max(1, Number(req.query.page_size ?? 50)));
    const total = filtered.length;
    const pageRows = filtered.slice((page - 1) * pageSize, page * pageSize);

    // 合计（按需求方拍板：可加项求和；利润率/ROI加权重算；单价取窗口内最新；库存取最新快照）
    // 2026-08-22 第六单（需求方拍板「乙」）：合计只统计非兜底行。
    //   兜底行没有成本与利润，计入会把合计利润率算低。
    //   合计销售额因此小于页面各行相加——这是如实体现，已写入 caliber_note。
    //   在取数源头换数组而不是事后减，才能保证利润率/ROI 的分子分母同源。
    const totalsRows = filtered.filter((x) => !x.is_fast);
    const sum = (f: (x: DetailRow) => number): number => r2(totalsRows.reduce((s, x) => s + f(x), 0));
    const totalSales = sum((x) => x.sales);
    const totalProfit = sum((x) => x.order_profit);
    const denomCny = totalsRows.reduce((s, x) => s + (x.pc_unit + x.fl_unit) * x.qty, 0);
    const latestByMsku = new Map<string, DetailRow>();
    for (const r of totalsRows) {
      const k = `${r.store_id}|${r.msku}`;
      const prev = latestByMsku.get(k);
      if (!prev || r.stat_date > prev.stat_date) latestByMsku.set(k, r);
    }
    const latestRows = Array.from(latestByMsku.values());
    const totals = {
      qty: totalsRows.reduce((s, x) => s + x.qty, 0),
      sales: totalSales, excluded_sales: sum((x) => x.excluded_sales),
      refund_qty: totalsRows.reduce((s, x) => s + x.refund_qty, 0),
      refund_amount: sum((x) => x.refund_amount),
      ad: sum((x) => x.ad), wfs: sum((x) => x.wfs), commission: sum((x) => x.commission),
      purchase_cost: sum((x) => x.purchase_cost), first_leg: sum((x) => x.first_leg),
      storage: sum((x) => x.storage), gross_profit_old: sum((x) => x.gross_profit_old),
      order_profit: totalProfit,
      profit_rate: totalSales > 0 ? Math.round((totalProfit / totalSales) * 10000) / 10000 : null,
      ad_ratio: totalSales > 0 ? Math.round((sum((x) => x.ad) / totalSales) * 10000) / 10000 : null,
      roi: denomCny > 0 ? Math.round((totalProfit * EXCHANGE_RATE / denomCny) * 100) / 100 : null,
      // 库存=各品最新快照之和；单价=各品窗口内最新单价（不可加，故取最新代表值）
      wfs_stock: latestRows.reduce((s, x) => s + x.wfs_stock, 0),
      pc_unit: latestRows.length === 1 ? latestRows[0].pc_unit : null,
      wfs_unit: latestRows.length === 1 ? latestRows[0].wfs_unit : null,
      fl_unit: latestRows.length === 1 ? latestRows[0].fl_unit : null,
      storage_unit: latestRows.length === 1 ? latestRows[0].storage_unit : null,
    };

    res.json({
      from: ctx.from, to: ctx.to, latest_biz_date: ctx.latest, days: ctx.days,
      single_item: ctx.singleItem, max_days: ctx.singleItem ? MAX_DAYS_SINGLE_ITEM : MAX_DAYS_DEFAULT,
      page, page_size: pageSize, total, rows: pageRows, totals,
      caliber_note: "逐日明细；销售额不含送样单；CS测品剔除；成本为当日快照历史价；库存为当日快照；退货率30天以结束日为锚按品计算；广告含SP+SB+SV+SEM。⚠️最近若干天为T-1兜底行（成本状态显示「−」）：只有销量、销售额与库存，广告费与利润待权威数据到位后重算；合计行不含兜底行，故合计销售额小于各行相加。",
    });
  } catch (e) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally {
    await db.end();
  }
});

/** 筛选项（店铺/负责人下拉），独立轻查询，不受分页影响 */
router.get("/options", async (_req: Request, res: Response) => {
  const db = await getDb();
  try {
    const [st] = await db.execute(
      `SELECT store_id, MAX(store_name) name FROM dim_store WHERE platform='walmart' GROUP BY store_id ORDER BY name`);
    const [ow] = await db.execute(
      `SELECT DISTINCT owner FROM dim_product WHERE platform='walmart' AND COALESCE(owner,'')<>'' ORDER BY owner`);
    res.json({
      stores: (st as Array<Record<string, unknown>>).map((x) => ({ value: String(x.store_id), label: String(x.name ?? x.store_id) })),
      owners: (ow as Array<Record<string, unknown>>).map((x) => String(x.owner)),
    });
  } catch (e) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally {
    await db.end();
  }
});

export default router;
