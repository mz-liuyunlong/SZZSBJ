/**
 * aiBusinessRoutes.ts
 *
 * Express 路由：/api/ai-business/*（AI经营分析 Tab 后端，2026-07-13 新增，隔离开发）
 *   GET  /targets              — 目标列表（可按 target_type / period_key / owner 过滤）
 *   GET  /targets/change-log   — 目标变更流水（全员可查，append-only）
 *   POST /targets              — 目标批量写入（手动/导入共用；密码门禁 TARGET_EDIT_PASSWORD）
 *   GET  /progress             — 完成率看板数据（公司=负责人合计；月度+季度；时间进度）
 *   GET  /reports              — 报表中心列表（ai_business_report）
 *   GET  /reports/:id/html/:file — 受控读取报告HTML（不做静态公开挂载；文件名白名单+目录锁定）
 *
 * 分层边界：
 *   biz_business_target / biz_business_target_change_log = 业务层人工数据，
 *     仅经本路由密码门禁写入（人工渠道），AI 任务不得写。
 *   ai_business_report = AI 层登记，由生成器写入，本路由只读。
 *   实际业绩读取 raw_feishu_table(order_profit_daily) 快照，与周报口径完全一致。
 */

import { spawn } from "child_process";
import { Router, Request, Response } from "express";
import * as fs from "fs";
import * as mysql from "mysql2/promise";
import { writeAudit } from "./authService";
import * as path from "path";

const router = Router();

const SPREADSHEET_TOKEN = "<REDACTED_FEISHU_SPREADSHEET_TOKEN>";
const ORDER_PROFIT_SHEET_ID = "order_profit_daily";
// 数据可用性：数据日D在D+2的16:45方案B链完成后入库（约17:00）。
// 故 17:00 前最新完整数据日=D-3，17:00 后=D-2，避免完成率上午少算、傍晚跳变的口径混乱。
const DATA_READY_HOUR = 17;
function dataLagDays(): number {
  return new Date().getHours() >= DATA_READY_HOUR ? 2 : 3;
}
const REPORT_FILE_RE = /^[\w.\-一-鿿（）()]{1,120}\.html$/;

// ── DB 连接工厂（与 feishuRawSalesRoutes 同规约） ────────────────────────────

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host:     process.env.DB_HOST     ?? "127.0.0.1",
    port:     Number(process.env.DB_PORT ?? 3306),
    user:     process.env.DB_USER     ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME     ?? "walmart_ai_data",
  });
}

// ── 工具 ─────────────────────────────────────────────────────────────────────

// 负责人别名归一（与生成器同源规则：RAW/目标历史数据读取时统一，2026-07-15）
const OWNER_ALIASES: Record<string, string> = { "啊四": "林翔" };

function normalizeOwner(name: unknown): string {
  const n = String(name ?? "").trim();
  return OWNER_ALIASES[n] ?? n;
}

/** 快照数值解析：容忍 "1,234.56" / "12.3%" / 空串 / null（与周报生成器 num() 口径一致） */
function num(v: unknown): number {
  if (v === null || v === undefined) return 0;
  const s = String(v).replace(/,/g, "").replace(/%/g, "").trim();
  if (s === "" || s === "-" || s.toLowerCase() === "null" || s.toLowerCase() === "none") return 0;
  const n = Number(s);
  return Number.isFinite(n) ? n : 0;
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

/** 服务器本地日期（生产为 Asia/Shanghai）偏移 delta 天，返回 YYYY-MM-DD */
function localDate(delta = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + delta);
  const p = (x: number) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

const MONTH_RE = /^\d{4}-(0[1-9]|1[0-2])$/;
const QUARTER_RE = /^\d{4}-Q[1-4]$/;

function monthRange(periodKey: string): { start: string; end: string } {
  const [y, m] = periodKey.split("-").map(Number);
  const lastDay = new Date(y, m, 0).getDate();
  const p = (x: number) => String(x).padStart(2, "0");
  return { start: `${y}-${p(m)}-01`, end: `${y}-${p(m)}-${p(lastDay)}` };
}

function quarterRange(periodKey: string): { start: string; end: string } {
  const y = Number(periodKey.slice(0, 4));
  const q = Number(periodKey.slice(6));
  const startMonth = (q - 1) * 3 + 1;
  const endMonth = startMonth + 2;
  const lastDay = new Date(y, endMonth, 0).getDate();
  const p = (x: number) => String(x).padStart(2, "0");
  return { start: `${y}-${p(startMonth)}-01`, end: `${y}-${p(endMonth)}-${p(lastDay)}` };
}

function currentMonthKey(): string {
  return localDate(0).slice(0, 7);
}

function currentQuarterKey(): string {
  const m = Number(localDate(0).slice(5, 7));
  return `${localDate(0).slice(0, 4)}-Q${Math.floor((m - 1) / 3) + 1}`;
}

/** 时间进度：窗口起点到"今天"经过的天数占比（含当天，封顶100） */
function timeProgressPct(start: string, end: string): number {
  const ms = (s: string) => new Date(`${s}T00:00:00`).getTime();
  const total = (ms(end) - ms(start)) / 86400000 + 1;
  const elapsed = (ms(localDate(0)) - ms(start)) / 86400000 + 1;
  if (total <= 0) return 0;
  return round2(Math.min(100, Math.max(0, (elapsed / total) * 100)));
}

// ── 业绩聚合（与周报口径一致：Node 侧解析 row_json） ─────────────────────────

interface OwnerActual { sales: number; profit: number; }

/** CS测品集合（business_state 最新快照）：业绩完成口径剔除 CS 测品的销售与利润（2026-07-15 定稿） */
async function fetchCsSet(db: mysql.Connection): Promise<Set<string>> {
  // 2026-07-21 堵漏：business_state 快照可能漏新CS/msku空行，并集 dim_product msku前缀兜底
  const [rows] = await db.execute(
    `SELECT DISTINCT store_id, item_id FROM dim_product_business_state
     WHERE platform = 'walmart' AND product_type = 'CS测品'
       AND stat_date = (SELECT MAX(stat_date) FROM dim_product_business_state)
     UNION
     SELECT DISTINCT store_id, item_id FROM dim_product
     WHERE platform = 'walmart' AND msku LIKE 'CS%'`,
  );
  return new Set((rows as Array<{ store_id: string; item_id: string }>)
    .map((r) => `${r.store_id}|${r.item_id}`));
}

async function aggregateActuals(
  db: mysql.Connection, start: string, end: string, exclude: Set<string>,
): Promise<Map<string, OwnerActual>> {
  const [rows] = await db.execute(
    `SELECT row_json FROM raw_feishu_table
     WHERE spreadsheet_token = ? AND sheet_id = ? AND data_date BETWEEN ? AND ?`,
    [SPREADSHEET_TOKEN, ORDER_PROFIT_SHEET_ID, start, end],
  );
  const map = new Map<string, OwnerActual>();
  for (const r of rows as Array<{ row_json: unknown }>) {
    let j: Record<string, unknown>;
    try {
      j = typeof r.row_json === "string" ? JSON.parse(r.row_json) : (r.row_json as Record<string, unknown>);
    } catch { continue; }
    if (!j) continue;
    const key = `${String(j["店铺ID"] ?? "").trim()}|${String(j["商品ID"] ?? "").trim()}`;
    if (exclude.has(key)) continue; // CS测品不计入业绩
    if (String(j["MSKU"] ?? "").trim().toUpperCase().startsWith("CS")) continue; // 行内MSKU兜底（2026-07-21堵漏）
    const owner = normalizeOwner(j["负责人"]) || "(未分配)";
    const cur = map.get(owner) ?? { sales: 0, profit: 0 };
    cur.sales += num(j["今日销售额（$）"]);
    cur.profit += num(j["毛利润（$）"]);
    map.set(owner, cur);
  }
  return map;
}

/** 按产品聚合快照窗口（月度规划表单头部"上月数据"用；字段名与周报生成器完全一致） */
interface ItemActual { sales: number; qty: number; profit: number; ad: number; }

async function aggregatePrevMonthByItem(
  db: mysql.Connection, start: string, end: string,
): Promise<Map<string, ItemActual>> {
  const [rows] = await db.execute(
    `SELECT row_json FROM raw_feishu_table
     WHERE spreadsheet_token = ? AND sheet_id = ? AND data_date BETWEEN ? AND ?`,
    [SPREADSHEET_TOKEN, ORDER_PROFIT_SHEET_ID, start, end],
  );
  const map = new Map<string, ItemActual>();
  let badRows = 0;
  for (const r of rows as Array<{ row_json: unknown }>) {
    let j: Record<string, unknown>;
    try {
      j = typeof r.row_json === "string" ? JSON.parse(r.row_json) : (r.row_json as Record<string, unknown>);
    } catch { badRows++; continue; }
    if (!j) { badRows++; continue; }
    const key = `${String(j["店铺ID"] ?? "").trim()}|${String(j["商品ID"] ?? "").trim()}`;
    const cur = map.get(key) ?? { sales: 0, qty: 0, profit: 0, ad: 0 };
    cur.sales += num(j["今日销售额（$）"]);
    cur.qty += num(j["今日销量"]);
    cur.profit += num(j["毛利润（$）"]);
    cur.ad += num(j["广告花费（$）"]);
    map.set(key, cur);
  }
  if (badRows > 0) console.warn(`[monthly-plan/todo] 上月快照解析失败行数=${badRows}`);
  return map;
}

// ── 主管确认密码映射（TARGET_CONFIRM_PASSWORDS="LX:林翔,AB:某某"；密码即身份，界面不填人名） ──

function parseConfirmPasswords(): Map<string, string> {
  const raw = (process.env.TARGET_CONFIRM_PASSWORDS ?? "").trim();
  const map = new Map<string, string>();
  for (const part of raw.split(",")) {
    const idx = part.indexOf(":");
    if (idx <= 0) continue;
    const pwd = part.slice(0, idx).trim();
    const name = part.slice(idx + 1).trim();
    if (pwd && name) map.set(pwd, name);
  }
  return map;
}

// ── 新品公式目标（2026-07-16 定稿）──────────────────────────────────────────
// 新品=上架时间(dim_product.launch_date, WFS 0→非0)落在当月；运营不填，公司统一公式：
//   销量 = ceil(上架日至月末天数 × 0.3)；单价 = 成交价众数（按日单价出现次数最多），
//   无成交取 buy_box_price（领星同步），仍无则0（只考核销量）；销售额=销量×单价；利润=销售额×5%。

interface NewProductTarget {
  store_id: string; item_id: string; mskus: string; owner: string;
  launch_date: string; days: number; qty: number;
  price: number; price_source: string; sales: number; profit: number;
}

async function computeNewProductTargets(
  db: mysql.Connection, monthKey: string,
): Promise<{ items: NewProductTarget[]; byOwner: Map<string, { sales: number; profit: number; qty: number; count: number }> }> {
  const { start, end } = monthRange(monthKey);
  const [rows] = await db.execute(
    `SELECT d.store_id, d.item_id, d.mskus, d.owner_raw, d.launch_date, d.bb_price
     FROM (
       SELECT store_id, item_id,
              MAX(COALESCE(NULLIF(owner,''),'')) AS owner_raw,
              SUBSTRING(GROUP_CONCAT(DISTINCT NULLIF(msku,'') ORDER BY msku SEPARATOR '/'),1,120) AS mskus,
              DATE_FORMAT(MIN(launch_date),'%Y-%m-%d') AS launch_date,
              MAX(buy_box_price) AS bb_price
       FROM dim_product
       WHERE platform = 'walmart'
         AND COALESCE(NULLIF(product_management_status,''),'active') NOT IN ('inactive','archived')
       GROUP BY store_id, item_id
       HAVING MIN(launch_date) BETWEEN ? AND ?
     ) d
     LEFT JOIN (
       SELECT store_id, item_id, MAX(CASE WHEN product_type='CS测品' THEN 1 ELSE 0 END) AS is_cs
       FROM dim_product_business_state
       WHERE platform='walmart' AND stat_date=(SELECT MAX(stat_date) FROM dim_product_business_state)
       GROUP BY store_id, item_id
     ) st ON st.store_id = d.store_id AND st.item_id = d.item_id
     WHERE COALESCE(st.is_cs, 0) = 0`,
    [start, end],
  );
  const prods = rows as Array<Record<string, unknown>>;
  const items: NewProductTarget[] = [];
  const byOwner = new Map<string, { sales: number; profit: number; qty: number; count: number }>();
  if (prods.length === 0) return { items, byOwner };

  // 成交价众数（按日单价，保留2位；并列取较高价）
  const pairs = prods.map((p) => [String(p.store_id), String(p.item_id)]);
  const inClause = pairs.map(() => "(?,?)").join(",");
  const [priceRows] = await db.execute(
    `SELECT store_id, item_id, ROUND(sales_amount / sales_qty, 2) AS price, COUNT(*) AS c
     FROM fact_sales_daily
     WHERE platform='walmart' AND sales_qty > 0 AND COALESCE(sales_amount,0) > 0
       AND (store_id, item_id) IN (${inClause})
     GROUP BY store_id, item_id, price`,
    pairs.flat(),
  );
  const modeMap = new Map<string, { price: number; c: number }>();
  for (const r of priceRows as Array<{ store_id: string; item_id: string; price: string | number; c: string | number }>) {
    const key = `${r.store_id}|${r.item_id}`;
    const price = Number(r.price);
    const c = Number(r.c);
    const cur = modeMap.get(key);
    if (!cur || c > cur.c || (c === cur.c && price > cur.price)) modeMap.set(key, { price, c });
  }

  const monthEndDay = Number(end.slice(8, 10));
  for (const p of prods) {
    const storeId = String(p.store_id);
    const itemId = String(p.item_id);
    const owner = normalizeOwner(p.owner_raw) || "(未分配)";
    const launch = String(p.launch_date);
    const launchDay = Number(launch.slice(8, 10));
    const days = Math.max(1, monthEndDay - launchDay + 1);
    const qty = Math.ceil(days * 0.3);
    const mode = modeMap.get(`${storeId}|${itemId}`);
    const bb = Number(p.bb_price ?? 0);
    let price = 0;
    let priceSource = "无价格（仅考核销量）";
    if (mode) { price = mode.price; priceSource = "成交价众数"; }
    else if (Number.isFinite(bb) && bb > 0) { price = round2(bb); priceSource = "BuyBox价格"; }
    const sales = round2(qty * price);
    const profit = round2(sales * 0.05);
    items.push({ store_id: storeId, item_id: itemId, mskus: String(p.mskus ?? ""), owner,
      launch_date: launch, days, qty, price, price_source: priceSource, sales, profit });
    const agg = byOwner.get(owner) ?? { sales: 0, profit: 0, qty: 0, count: 0 };
    agg.sales = round2(agg.sales + sales); agg.profit = round2(agg.profit + profit);
    agg.qty += qty; agg.count += 1;
    byOwner.set(owner, agg);
  }
  return { items, byOwner };
}

// ── GET /targets ─────────────────────────────────────────────────────────────

router.get("/targets", async (req: Request, res: Response): Promise<void> => {
  let db: mysql.Connection | null = null;
  try {
    db = await getDb();
    const conds: string[] = [];
    const params: (string | number)[] = [];
    const { target_type, period_key, owner } = req.query as Record<string, string | undefined>;
    if (target_type) { conds.push("target_type = ?"); params.push(target_type); }
    if (period_key)  { conds.push("period_key = ?");  params.push(period_key); }
    if (owner)       { conds.push("owner = ?");       params.push(owner); }
    const where = conds.length ? `WHERE ${conds.join(" AND ")}` : "";
    const [rows] = await db.execute(
      `SELECT id, target_type, period_key, platform, owner, metric, target_value,
              created_by, updated_by, created_at, updated_at
       FROM biz_business_target ${where}
       ORDER BY period_key DESC, owner, metric`,
      params,
    );
    const cu = (req as { user?: { username?: string; isSuperadmin?: boolean; roles?: Set<string> } }).user;
    const canEdit = !!cu && (cu.isSuperadmin || (cu.roles?.has("超管") ?? false));
    res.json({ rows, can_edit: canEdit, current_user: cu?.username ?? "" });
  } catch (e: unknown) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally {
    if (db) await db.end().catch(() => undefined);
  }
});

// ── GET /targets/change-log ──────────────────────────────────────────────────

router.get("/targets/change-log", async (req: Request, res: Response): Promise<void> => {
  let db: mysql.Connection | null = null;
  try {
    db = await getDb();
    const conds: string[] = [];
    const params: (string | number)[] = [];
    const { period_key, owner } = req.query as Record<string, string | undefined>;
    if (period_key) { conds.push("period_key = ?"); params.push(period_key); }
    if (owner)      { conds.push("owner = ?");      params.push(owner); }
    const where = conds.length ? `WHERE ${conds.join(" AND ")}` : "";
    const limit = Math.min(500, Math.max(1, Number(req.query.limit ?? 200) || 200));
    const [rows] = await db.execute(
      `SELECT id, target_id, target_type, period_key, platform, owner, metric,
              old_value, new_value, action, change_source, changed_by, changed_at
       FROM biz_business_target_change_log ${where}
       ORDER BY id DESC LIMIT ${limit}`,
      params,
    );
    res.json({ rows });
  } catch (e: unknown) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally {
    if (db) await db.end().catch(() => undefined);
  }
});

// ── POST /targets（密码门禁批量写入；手动/导入共用） ─────────────────────────

interface TargetItem {
  target_type: "monthly" | "quarterly";
  period_key: string;
  owner: string;
  metric: "sales" | "profit";
  target_value: number;
}

interface TargetWriteBody {
  password?: string;
  changed_by?: string;
  change_source?: "manual" | "import";
  items?: TargetItem[];
}

function validateItem(it: TargetItem): string | null {
  if (it.target_type !== "monthly" && it.target_type !== "quarterly") return "target_type 非法";
  if (it.target_type === "monthly" && !MONTH_RE.test(it.period_key)) return `period_key 非法: ${it.period_key}（月度应为 YYYY-MM）`;
  if (it.target_type === "quarterly" && !QUARTER_RE.test(it.period_key)) return `period_key 非法: ${it.period_key}（季度应为 YYYY-Q1..Q4）`;
  if (!it.owner || !String(it.owner).trim()) return "owner 不能为空";
  if (it.metric !== "sales" && it.metric !== "profit") return "metric 非法";
  const v = Number(it.target_value);
  if (!Number.isFinite(v) || v < 0 || v > 99999999999) return `target_value 非法: ${it.target_value}`;
  return null;
}

router.post("/targets", async (req: Request, res: Response): Promise<void> => {
  const cu = (req as { user?: { username?: string; isSuperadmin?: boolean; roles?: Set<string> } }).user;
  if (!cu?.username) { res.status(401).json({ error: "未登录，目标未写入" }); return; }
  if (!(cu.isSuperadmin || (cu.roles?.has("超管") ?? false))) {
    res.status(403).json({ error: "仅超管可编辑经营目标（当前为 林翔 / 陈佳聪）" }); return;
  }
  const body = req.body as TargetWriteBody;
  const supervisor = cu.username; // 超管即身份，绕过已确认锁定
  const changedBy = cu.username;  // 写入人＝登录账号（可追溯）
  const source: "manual" | "import" = body.change_source === "import" ? "import" : "manual";
  const items = Array.isArray(body.items) ? body.items : [];
  if (items.length === 0 || items.length > 500) {
    res.status(400).json({ error: "items 需为 1~500 条" });
    return;
  }
  for (const it of items) {
    const err = validateItem(it);
    if (err) { res.status(400).json({ error: err }); return; }
  }

  let db: mysql.Connection | null = null;
  try {
    db = await getDb();
    // 锁定检查：已确认的(类型,周期,负责人)非主管密码禁止修改
    if (!supervisor) {
      const keys = [...new Set(items.map((it) => `${it.target_type}|${it.period_key}|${normalizeOwner(it.owner)}`))];
      const lockedOwners: string[] = [];
      for (const k of keys) {
        const [tt, pk, ow] = k.split("|");
        const [c] = await db.execute(
          `SELECT 1 FROM biz_owner_target_confirm
           WHERE target_type=? AND period_key=? AND platform='walmart' AND owner=? LIMIT 1`,
          [tt, pk, ow],
        );
        if ((c as unknown[]).length > 0) lockedOwners.push(`${ow}(${pk})`);
      }
      if (lockedOwners.length > 0) {
        res.status(403).json({ error: `以下负责人目标已主管确认锁定，仅主管密码可修改：${lockedOwners.join("、")}` });
        return;
      }
    }
    await db.beginTransaction();
    let created = 0, updated = 0, unchanged = 0;
    for (const it of items) {
      const owner = String(it.owner).trim();
      const value = round2(Number(it.target_value));
      const [found] = await db.execute(
        `SELECT id, target_value FROM biz_business_target
         WHERE target_type=? AND period_key=? AND platform='walmart' AND owner=? AND metric=?
         FOR UPDATE`,
        [it.target_type, it.period_key, owner, it.metric],
      );
      const exist = (found as Array<{ id: number; target_value: string | number }>)[0];
      if (!exist) {
        const [ins] = await db.execute(
          `INSERT INTO biz_business_target
             (target_type, period_key, platform, owner, metric, target_value, created_by, updated_by)
           VALUES (?, ?, 'walmart', ?, ?, ?, ?, ?)`,
          [it.target_type, it.period_key, owner, it.metric, value, changedBy, changedBy],
        );
        const newId = (ins as mysql.ResultSetHeader).insertId;
        await db.execute(
          `INSERT INTO biz_business_target_change_log
             (target_id, target_type, period_key, platform, owner, metric,
              old_value, new_value, action, change_source, changed_by)
           VALUES (?, ?, ?, 'walmart', ?, ?, NULL, ?, 'create', ?, ?)`,
          [newId, it.target_type, it.period_key, owner, it.metric, value, source, changedBy],
        );
        created++;
      } else if (round2(Number(exist.target_value)) === value) {
        unchanged++;
      } else {
        await db.execute(
          `INSERT INTO biz_business_target_change_log
             (target_id, target_type, period_key, platform, owner, metric,
              old_value, new_value, action, change_source, changed_by)
           VALUES (?, ?, ?, 'walmart', ?, ?, ?, ?, 'update', ?, ?)`,
          [exist.id, it.target_type, it.period_key, owner, it.metric,
           round2(Number(exist.target_value)), value, source, changedBy],
        );
        await db.execute(
          `UPDATE biz_business_target SET target_value=?, updated_by=? WHERE id=?`,
          [value, changedBy, exist.id],
        );
        updated++;
      }
    }
    await db.commit();
    await writeAudit(db, {
      userId: Number((req as { user?: { id?: number } }).user?.id ?? 0), username: changedBy,
      action: "target_write", target: `targets:${source}`,
      detail: { created, updated, unchanged, total: items.length },
      ip: req.ip, ua: req.headers["user-agent"],
    });
    res.json({ ok: true, created, updated, unchanged, total: items.length });
  } catch (e: unknown) {
    if (db) await db.rollback().catch(() => undefined);
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally {
    if (db) await db.end().catch(() => undefined);
  }
});

// ── GET /targets/self-report?period_key=  运营自报合计（单品目标按负责人求和，只读参考） ──

router.get("/targets/self-report", async (req: Request, res: Response): Promise<void> => {
  let db: mysql.Connection | null = null;
  try {
    const periodKey = String(req.query.period_key ?? currentMonthKey());
    if (!MONTH_RE.test(periodKey)) { res.status(400).json({ error: "period_key 非法" }); return; }
    db = await getDb();
    const [rows] = await db.execute(
      `SELECT owner, COUNT(*) AS planned,
              SUM(target_sales_amount IS NOT NULL) AS with_target,
              SUM(COALESCE(target_sales_amount,0)) AS sales,
              SUM(COALESCE(target_gross_profit,0)) AS profit
       FROM biz_monthly_plan
       WHERE plan_month = ? AND platform = 'walmart'
       GROUP BY owner`,
      [periodKey],
    );
    const agg = new Map<string, { planned: number; with_target: number; sales: number; profit: number }>();
    for (const r of rows as Array<Record<string, unknown>>) {
      const owner = normalizeOwner(r.owner) || "(未分配)";
      const cur = agg.get(owner) ?? { planned: 0, with_target: 0, sales: 0, profit: 0 };
      cur.planned += Number(r.planned ?? 0);
      cur.with_target += Number(r.with_target ?? 0);
      cur.sales = round2(cur.sales + Number(r.sales ?? 0));
      cur.profit = round2(cur.profit + Number(r.profit ?? 0));
      agg.set(owner, cur);
    }
    res.json({ periodKey, rows: [...agg.entries()].map(([owner, v]) => ({ owner, ...v })) });
  } catch (e: unknown) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally {
    if (db) await db.end().catch(() => undefined);
  }
});

// ── GET /targets/new-product?period_key=  新品公式目标（系统核算，只读） ──

router.get("/targets/new-product", async (req: Request, res: Response): Promise<void> => {
  let db: mysql.Connection | null = null;
  try {
    const periodKey = String(req.query.period_key ?? currentMonthKey());
    if (!MONTH_RE.test(periodKey)) { res.status(400).json({ error: "period_key 非法" }); return; }
    db = await getDb();
    const { items, byOwner } = await computeNewProductTargets(db, periodKey);
    res.json({
      periodKey, items,
      byOwner: [...byOwner.entries()].map(([owner, v]) => ({ owner, ...v })),
    });
  } catch (e: unknown) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally {
    if (db) await db.end().catch(() => undefined);
  }
});

// ── GET /targets/confirm-status?target_type=&period_key=  最新确认状态（每负责人） ──

router.get("/targets/confirm-status", async (req: Request, res: Response): Promise<void> => {
  let db: mysql.Connection | null = null;
  try {
    const targetType = String(req.query.target_type ?? "monthly");
    const periodKey = String(req.query.period_key ?? currentMonthKey());
    db = await getDb();
    const [rows] = await db.execute(
      `SELECT owner, confirmed_sales, confirmed_profit, confirmed_by, created_at
       FROM biz_owner_target_confirm
       WHERE target_type = ? AND period_key = ? AND platform = 'walmart'
       ORDER BY id`,
      [targetType, periodKey],
    );
    const latest = new Map<string, Record<string, unknown>>();
    for (const r of rows as Array<Record<string, unknown>>) latest.set(String(r.owner), r);
    res.json({ targetType, periodKey, rows: [...latest.values()] });
  } catch (e: unknown) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally {
    if (db) await db.end().catch(() => undefined);
  }
});

// ── POST /targets/confirm  主管确认（逐负责人；密码即身份；写目标+留痕，确认后锁定） ──

router.post("/targets/confirm", async (req: Request, res: Response): Promise<void> => {
  const b = req.body as { target_type?: string; period_key?: string; owner?: string;
                          sales?: number; profit?: number; password?: string };
  const cu = (req as { user?: { username?: string; isSuperadmin?: boolean; roles?: Set<string> } }).user;
  if (!cu?.username) { res.status(401).json({ error: "未登录，无法确认" }); return; }
  if (!(cu.isSuperadmin || (cu.roles?.has("超管") ?? false))) {
    res.status(403).json({ error: "仅超管可确认经营目标（当前为 林翔 / 陈佳聪）" }); return;
  }
  const person = cu.username;
  const targetType = b.target_type === "quarterly" ? "quarterly" : "monthly";
  const periodKey = String(b.period_key ?? "").trim();
  if (targetType === "monthly" && !MONTH_RE.test(periodKey)) { res.status(400).json({ error: "period_key 非法" }); return; }
  if (targetType === "quarterly" && !QUARTER_RE.test(periodKey)) { res.status(400).json({ error: "period_key 非法" }); return; }
  const owner = normalizeOwner(b.owner);
  if (!owner) { res.status(400).json({ error: "owner 不能为空" }); return; }
  const sales = Number(b.sales);
  const profit = Number(b.profit);
  if (!Number.isFinite(sales) || sales < 0 || !Number.isFinite(profit) || profit < 0) {
    res.status(400).json({ error: "sales/profit 需为非负数字" }); return;
  }

  let db: mysql.Connection | null = null;
  try {
    db = await getDb();
    await db.beginTransaction();
    // 确认值写入目标表（含变更流水），确认留痕独立成行（append-only）
    for (const [metric, value] of [["sales", round2(sales)], ["profit", round2(profit)]] as Array<["sales" | "profit", number]>) {
      const [found] = await db.execute(
        `SELECT id, target_value FROM biz_business_target
         WHERE target_type=? AND period_key=? AND platform='walmart' AND owner=? AND metric=? FOR UPDATE`,
        [targetType, periodKey, owner, metric],
      );
      const exist = (found as Array<{ id: number; target_value: string | number }>)[0];
      if (!exist) {
        const [ins] = await db.execute(
          `INSERT INTO biz_business_target
             (target_type, period_key, platform, owner, metric, target_value, created_by, updated_by)
           VALUES (?, ?, 'walmart', ?, ?, ?, ?, ?)`,
          [targetType, periodKey, owner, metric, value, person, person],
        );
        await db.execute(
          `INSERT INTO biz_business_target_change_log
             (target_id, target_type, period_key, platform, owner, metric,
              old_value, new_value, action, change_source, changed_by)
           VALUES (?, ?, ?, 'walmart', ?, ?, NULL, ?, 'create', 'manual', ?)`,
          [(ins as mysql.ResultSetHeader).insertId, targetType, periodKey, owner, metric, value, person],
        );
      } else if (round2(Number(exist.target_value)) !== value) {
        await db.execute(
          `INSERT INTO biz_business_target_change_log
             (target_id, target_type, period_key, platform, owner, metric,
              old_value, new_value, action, change_source, changed_by)
           VALUES (?, ?, ?, 'walmart', ?, ?, ?, ?, 'update', 'manual', ?)`,
          [exist.id, targetType, periodKey, owner, metric, round2(Number(exist.target_value)), value, person],
        );
        await db.execute(
          `UPDATE biz_business_target SET target_value=?, updated_by=? WHERE id=?`,
          [value, person, exist.id],
        );
      }
    }
    await db.execute(
      `INSERT INTO biz_owner_target_confirm
         (target_type, period_key, platform, owner, confirmed_sales, confirmed_profit, confirmed_by)
       VALUES (?, ?, 'walmart', ?, ?, ?, ?)`,
      [targetType, periodKey, owner, round2(sales), round2(profit), person],
    );
    await db.commit();
    await writeAudit(db, {
      userId: Number((req as { user?: { id?: number } }).user?.id ?? 0), username: person,
      action: "target_confirm", target: `target:${targetType}:${periodKey}:${owner}`,
      detail: { sales: round2(sales), profit: round2(profit) },
      ip: req.ip, ua: req.headers["user-agent"],
    });
    res.json({ ok: true, confirmed_by: person });
  } catch (e: unknown) {
    if (db) await db.rollback().catch(() => undefined);
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally {
    if (db) await db.end().catch(() => undefined);
  }
});

// ── M6（2026-08）清货排除助手：清货判定=当月 biz_monthly_plan indicator=清货（单品级，与 M2/M4 的生命周期口径不同，需求方定稿）──
function quarterMonths(qk: string): string[] {
  const [y, q] = qk.split("-Q").map(Number);
  const m0 = (q - 1) * 3 + 1;
  return [0, 1, 2].map((i) => `${y}-${String(m0 + i).padStart(2, "0")}`);
}
async function clearanceTargetsByOwner(db: mysql.Connection, planMonths: string[]): Promise<{ keys: Set<string>; byOwner: Map<string, { sales: number; profit: number }> }> {
  const ph = planMonths.map(() => "?").join(",");
  const [rows] = await db.execute(
    `SELECT owner, store_id, item_id, COALESCE(SUM(target_sales_amount),0) AS ts, COALESCE(SUM(target_gross_profit),0) AS tp
     FROM biz_monthly_plan
     WHERE platform='walmart' AND plan_month IN (${ph})
       AND (indicator1_type='清货' OR indicator2_type='清货')
     GROUP BY owner, store_id, item_id`,
    planMonths,
  );
  const keys = new Set<string>(); const byOwner = new Map<string, { sales: number; profit: number }>();
  for (const r of rows as Array<{ owner: string; store_id: string; item_id: string; ts: string | number; tp: string | number }>) {
    keys.add(`${String(r.store_id)}|${String(r.item_id)}`);
    const o = normalizeOwner(r.owner);
    const cur = byOwner.get(o) ?? { sales: 0, profit: 0 };
    cur.sales += Number(r.ts) || 0; cur.profit += Number(r.tp) || 0; byOwner.set(o, cur);
  }
  return { keys, byOwner };
}
async function clearanceActualByOwner(db: mysql.Connection, start: string, end: string, clrKeys: Set<string>): Promise<Map<string, { sales: number; profit: number }>> {
  const m = new Map<string, { sales: number; profit: number }>();
  if (clrKeys.size === 0 || start > end) return m;
  const [rows] = await db.execute(
    `SELECT row_json FROM raw_feishu_table WHERE spreadsheet_token = ? AND sheet_id = ? AND data_date BETWEEN ? AND ?`,
    [SPREADSHEET_TOKEN, ORDER_PROFIT_SHEET_ID, start, end],
  );
  for (const r of rows as Array<{ row_json: unknown }>) {
    let j: Record<string, unknown>;
    try { j = typeof r.row_json === "string" ? JSON.parse(r.row_json) : (r.row_json as Record<string, unknown>); } catch { continue; }
    if (!j) continue;
    const key = `${String(j["店铺ID"] ?? "").trim()}|${String(j["商品ID"] ?? "").trim()}`;
    if (!clrKeys.has(key)) continue;
    if (String(j["MSKU"] ?? "").trim().toUpperCase().startsWith("CS")) continue;
    const o = normalizeOwner(j["负责人"]) || "(未分配)";
    const cur = m.get(o) ?? { sales: 0, profit: 0 };
    cur.sales += num(j["今日销售额（$）"]); cur.profit += num(j["毛利润（$）"]); m.set(o, cur);
  }
  return m;
}

// ── GET /progress（完成率看板：公司=负责人合计） ─────────────────────────────

router.get("/progress", async (req: Request, res: Response): Promise<void> => {
  let db: mysql.Connection | null = null;
  try {
    const monthKey = String(req.query.month ?? currentMonthKey());
    const quarterKey = String(req.query.quarter ?? currentQuarterKey());
    if (!MONTH_RE.test(monthKey)) { res.status(400).json({ error: `month 非法: ${monthKey}` }); return; }
    if (!QUARTER_RE.test(quarterKey)) { res.status(400).json({ error: `quarter 非法: ${quarterKey}` }); return; }

    const dataEnd = localDate(-dataLagDays());
    const m = monthRange(monthKey);
    const q = quarterRange(quarterKey);
    const mEnd = dataEnd < m.end ? dataEnd : m.end;
    const qEnd = dataEnd < q.end ? dataEnd : q.end;

    db = await getDb();
    const csSet = await fetchCsSet(db);
    const [mActual, qActual, [targetRows]] = await Promise.all([
      m.start <= mEnd ? aggregateActuals(db, m.start, mEnd, csSet) : Promise.resolve(new Map<string, OwnerActual>()),
      q.start <= qEnd ? aggregateActuals(db, q.start, qEnd, csSet) : Promise.resolve(new Map<string, OwnerActual>()),
      db.execute(
        `SELECT target_type, period_key, owner, metric, target_value FROM biz_business_target
         WHERE (target_type='monthly' AND period_key=?) OR (target_type='quarterly' AND period_key=?)`,
        [monthKey, quarterKey],
      ),
    ]);

    interface OwnerTargets { m_sales: number; m_profit: number; q_sales: number; q_profit: number; }
    const targets = new Map<string, OwnerTargets>();
    for (const r of targetRows as Array<{ target_type: string; owner: string; metric: string; target_value: string | number }>) {
      const owner = normalizeOwner(r.owner); // 别名归并（累加：啊四0值目标并入林翔）
      const t = targets.get(owner) ?? { m_sales: 0, m_profit: 0, q_sales: 0, q_profit: 0 };
      const v = Number(r.target_value) || 0;
      if (r.target_type === "monthly") { if (r.metric === "sales") t.m_sales += v; else t.m_profit += v; }
      else { if (r.metric === "sales") t.q_sales += v; else t.q_profit += v; }
      targets.set(owner, t);
    }

    // 最终业绩目标 = 主管确认/目标表值 + 新品公式目标（2026-07-16 定稿，仅月度叠加）
    const np = await computeNewProductTargets(db, monthKey);
    for (const [owner, v] of np.byOwner) {
      const t = targets.get(owner) ?? { m_sales: 0, m_profit: 0, q_sales: 0, q_profit: 0 };
      t.m_sales = round2(t.m_sales + v.sales);
      t.m_profit = round2(t.m_profit + v.profit);
      targets.set(owner, t);
    }

    const owners = new Set<string>([...targets.keys(), ...mActual.keys(), ...qActual.keys()]);
    const rows = [...owners].map((owner) => {
      const t = targets.get(owner) ?? { m_sales: 0, m_profit: 0, q_sales: 0, q_profit: 0 };
      const ma = mActual.get(owner) ?? { sales: 0, profit: 0 };
      const qa = qActual.get(owner) ?? { sales: 0, profit: 0 };
      const npo = np.byOwner.get(owner);
      return {
        owner,
        newProduct: npo ? { sales: npo.sales, profit: npo.profit, count: npo.count } : null,
        month: {
          sales:  { actual: round2(ma.sales),  target: t.m_sales,  pct: t.m_sales  ? round2((ma.sales  / t.m_sales)  * 100) : null },
          profit: { actual: round2(ma.profit), target: t.m_profit, pct: t.m_profit ? round2((ma.profit / t.m_profit) * 100) : null },
        },
        quarter: {
          sales:  { actual: round2(qa.sales),  target: t.q_sales,  pct: t.q_sales  ? round2((qa.sales  / t.q_sales)  * 100) : null },
          profit: { actual: round2(qa.profit), target: t.q_profit, pct: t.q_profit ? round2((qa.profit / t.q_profit) * 100) : null },
        },
        hasTarget: targets.has(owner),
      };
    }).sort((a, b) => (b.month.sales.actual - a.month.sales.actual));

    const sum = (f: (r: typeof rows[number]) => number) => round2(rows.reduce((s, r) => s + f(r), 0));
    const company = {
      month: {
        sales:  { actual: sum((r) => r.month.sales.actual),  target: sum((r) => r.month.sales.target) },
        profit: { actual: sum((r) => r.month.profit.actual), target: sum((r) => r.month.profit.target) },
      },
      quarter: {
        sales:  { actual: sum((r) => r.quarter.sales.actual),  target: sum((r) => r.quarter.sales.target) },
        profit: { actual: sum((r) => r.quarter.profit.actual), target: sum((r) => r.quarter.profit.target) },
      },
    };

    // M6 不含清货：按负责人扣清货单品目标+清货实际 → rows_ex_clearance；company_ex_clearance = 其合计（保证 公司=个人之和）
    const clrTgtM = await clearanceTargetsByOwner(db, [monthKey]);
    const clrTgtQ = await clearanceTargetsByOwner(db, quarterMonths(quarterKey));
    const clrActM = await clearanceActualByOwner(db, m.start, mEnd, clrTgtM.keys);
    const clrActQ = await clearanceActualByOwner(db, q.start, qEnd, clrTgtQ.keys);
    const mkPct = (actual: number, target: number) => ({ actual: round2(actual), target: round2(target), pct: target ? round2((actual / target) * 100) : null });
    const rows_ex_clearance = rows.map((r) => {
      const tM = clrTgtM.byOwner.get(r.owner) ?? { sales: 0, profit: 0 };
      const tQ = clrTgtQ.byOwner.get(r.owner) ?? { sales: 0, profit: 0 };
      const aM = clrActM.get(r.owner) ?? { sales: 0, profit: 0 };
      const aQ = clrActQ.get(r.owner) ?? { sales: 0, profit: 0 };
      return {
        owner: r.owner, newProduct: r.newProduct,
        month: {
          sales:  mkPct(r.month.sales.actual  - aM.sales,  r.month.sales.target  - tM.sales),
          profit: mkPct(r.month.profit.actual - aM.profit, r.month.profit.target - tM.profit),
        },
        quarter: {
          sales:  mkPct(r.quarter.sales.actual  - aQ.sales,  r.quarter.sales.target  - tQ.sales),
          profit: mkPct(r.quarter.profit.actual - aQ.profit, r.quarter.profit.target - tQ.profit),
        },
        hasTarget: r.hasTarget,
      };
    });
    const sumEx = (f: (r: typeof rows_ex_clearance[number]) => number) => round2(rows_ex_clearance.reduce((s, r) => s + f(r), 0));
    const company_ex_clearance = {
      month: {
        sales:  { actual: sumEx((r) => r.month.sales.actual),  target: sumEx((r) => r.month.sales.target) },
        profit: { actual: sumEx((r) => r.month.profit.actual), target: sumEx((r) => r.month.profit.target) },
      },
      quarter: {
        sales:  { actual: sumEx((r) => r.quarter.sales.actual),  target: sumEx((r) => r.quarter.sales.target) },
        profit: { actual: sumEx((r) => r.quarter.profit.actual), target: sumEx((r) => r.quarter.profit.target) },
      },
    };

    res.json({
      monthKey, quarterKey, dataEnd,
      monthWindow: { start: m.start, end: mEnd, timeProgressPct: timeProgressPct(m.start, m.end) },
      quarterWindow: { start: q.start, end: qEnd, timeProgressPct: timeProgressPct(q.start, q.end) },
      company, company_ex_clearance, rows, rows_ex_clearance,
    });
  } catch (e: unknown) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally {
    if (db) await db.end().catch(() => undefined);
  }
});

// ── GET /reports（报表中心列表） ─────────────────────────────────────────────

router.get("/reports", async (req: Request, res: Response): Promise<void> => {
  let db: mysql.Connection | null = null;
  try {
    db = await getDb();
    const conds: string[] = [];
    const params: (string | number)[] = [];
    const { report_type, period_key } = req.query as Record<string, string | undefined>;
    if (report_type) { conds.push("report_type = ?"); params.push(report_type); }
    if (period_key)  { conds.push("period_key = ?");  params.push(period_key); }
    const where = conds.length ? `WHERE ${conds.join(" AND ")}` : "";
    const limit = Math.min(200, Math.max(1, Number(req.query.limit ?? 50) || 50));
    const [rows] = await db.execute(
      `SELECT id, report_type, period_key, win_start, win_end, filter_json,
              completeness_json, status, trigger_source, generated_at
       FROM ai_business_report ${where}
       ORDER BY generated_at DESC, id DESC LIMIT ${limit}`,
      params,
    );
    res.json({ rows });
  } catch (e: unknown) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally {
    if (db) await db.end().catch(() => undefined);
  }
});

// ── POST /reports/generate（手动生成：密码门禁+窗口校验+异步生成后自动推送） ──

const GEN_TYPES = new Set(["weekly", "monthly", "quarterly", "yearly"]);
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
// 负责人输入白名单：中英文数字、括号、顿号/逗号分隔；禁止空格引号等shell元字符
const OWNERS_RE = /^(all|[\w一-鿿（）().\-]+(,[\w一-鿿（）().\-]+)*)$/;
const PROJECT_DIR = "/opt/lingxing-auto";
let lastGenerateAt = 0; // 简易节流：60秒内只允许一次手动生成

router.post("/reports/generate", async (req: Request, res: Response): Promise<void> => {
  // 2026-07-15 需求方：手动生成取消密码门禁（保留输入校验与60秒节流）
  const body = req.body as {
    report_type?: string; win_start?: string; win_end?: string; owners?: string;
  };
  const reportType = String(body.report_type ?? "");
  const winStart = String(body.win_start ?? "");
  const winEnd = String(body.win_end ?? "");
  const owners = String(body.owners ?? "all").trim();
  if (!GEN_TYPES.has(reportType)) { res.status(400).json({ error: "report_type 非法" }); return; }
  if (!DATE_RE.test(winStart) || !DATE_RE.test(winEnd)) { res.status(400).json({ error: "日期格式应为 YYYY-MM-DD" }); return; }
  if (winStart > winEnd) { res.status(400).json({ error: "起日晚于末日" }); return; }
  const maxEnd = localDate(-dataLagDays());
  if (winEnd > maxEnd) { res.status(400).json({ error: `末日晚于最新完整数据日，最晚可选 ${maxEnd}` }); return; }
  if (!OWNERS_RE.test(owners)) { res.status(400).json({ error: "负责人格式非法" }); return; }
  const now = Date.now();
  if (now - lastGenerateAt < 60000) { res.status(429).json({ error: "生成任务节流中，请1分钟后再试" }); return; }
  lastGenerateAt = now;

  const ts = new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14);
  const logFile = `${PROJECT_DIR}/logs/manual_report_${ts}.log`;
  // 2026-07-20 需求方拍板（W29周一误推整改）：手动触发的推送一律只进测试群（--test-send），
  // 不做全员推送；正式全员推送仅保留周四确认卡链路。生成的报告文件/链接不受影响。
  const cmd =
    `cd ${PROJECT_DIR} && set -o pipefail; ` +
    `RID=$(python3 scripts/generate_weekly_report.py --report-type '${reportType}' ` +
    `--win-start '${winStart}' --win-end '${winEnd}' --owners '${owners}' --trigger manual ` +
    `| tee -a '${logFile}' | sed -n 's/^REPORT_ID=//p'); ` +
    `if [ -n "$RID" ] && [ "$RID" != "None" ]; then ` +
    `npx ts-node src/sendBusinessReportNotify.ts --report-id "$RID" --send --test-send >> '${logFile}' 2>&1; fi`;
  try {
    const fd = fs.openSync(logFile, "a");
    const child = spawn("bash", ["-lc", cmd], { detached: true, stdio: ["ignore", fd, fd] });
    child.unref();
    fs.closeSync(fd);
  } catch (e: unknown) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
    return;
  }
  res.json({
    ok: true,
    message: "已开始生成，成功后自动推送（全部人=群+私聊；单人=仅私聊该负责人）。约1-2分钟后刷新报表列表。",
  });
});

// ── 月度规划（biz_monthly_plan 人工数据通道；2026-07-15 第三步新增） ──────────

const PLAN_MONTH_RE = /^\d{4}-(0[1-9]|1[0-2])$/;
const INDICATOR_TYPES = new Set(["清货", "提高毛利率", "提升销售额", "新增变体", "调整广告"]);

function currentPlanMonth(): string {
  return localDate(0).slice(0, 7);
}

// GET /monthly-plan/todo?plan_month=&owner=  待填清单（问题清单 ∪ 已填状态）
router.get("/monthly-plan/todo", async (req: Request, res: Response): Promise<void> => {
  let db: mysql.Connection | null = null;
  try {
    const planMonth = String(req.query.plan_month ?? currentPlanMonth());
    if (!PLAN_MONTH_RE.test(planMonth)) { res.status(400).json({ error: "plan_month 非法" }); return; }
    const owner = String(req.query.owner ?? "").trim();
    db = await getDb();
    // v5.0（2026-08-03 拍板·收紧）：豁免=上月整月WFS库存MAX=0 且 上月WFS销量SUM=0 且 WFS在途=0；
    //   在途=PMC四桶口径 fact_wfs_shipment(未完结) Σmax(declare−received) 经 dim_product 映射 item（库存一览表同源）。
    //   【清货期不再豁免】——清货品需照常填报，前端单列展示（历史 v3.6 的"清货期 OR 豁免"已废止）。
    // 新品不豁免（新品目标走公司公式链）；已填写的计划保留不豁免（豁免只针对未填产品）。
    // 豁免行仍返回（is_exempt=1），前端默认隐藏、可筛选查看。
    const [py0, pm0] = planMonth.split("-").map(Number);
    const prevMonth0 = pm0 === 1 ? `${py0 - 1}-12` : `${py0}-${String(pm0 - 1).padStart(2, "0")}`;
    const pr0 = monthRange(prevMonth0);
    // v3.2（2026-07-15）：清单底座=在营产品全集（非停用非归档；CS测品仍不参与规划），
    // LEFT JOIN 问题清单（issue_reasons 可空）。
    // v3.3（2026-07-16）：表单头部数据口径改为"上月自然月"（plan_month 前一个月），
    // 数据源=raw_feishu_table(order_profit_daily) 快照，与周报/月报聚合完全同源（今日销售额/今日销量/毛利润/广告花费）。
    // msku 口径：有问题行用 issue.msku（与生成器/存量规划一致），否则用 dim 聚合串（同生成器规则）。
    // 2026-07-23 豁免口径v4：上月WFS销量=fact_mp_sales_channel_daily；（v5 起库存条件由"最新快照"改为"上月整月MAX"、并新增在途=0）
    // 覆盖<25天自动回退库存等价法（上月全月WFS库存MAX=0 ⇒ 上月WFS销量必为0）。
    // 非WFS订单/销量不参与豁免判定（自发货单可能为刷划线价订单）。
    const [lmCovRows] = await db.execute(
      `SELECT COUNT(DISTINCT stat_date) AS d FROM fact_mp_sales_channel_daily
        WHERE platform = 'walmart' AND stat_date >= ? AND stat_date <= ?`,
      [pr0.start, pr0.end],
    );
    const lmCovDays = Number((lmCovRows as Array<Record<string, unknown>>)[0]?.d ?? 0);
    const lmUseWfs = lmCovDays >= 25;
    const lmxSub = lmUseWfs
      ? `SELECT store_id, item_id, SUM(COALESCE(wfs_sales_qty, 0)) AS lm_qty
         FROM fact_mp_sales_channel_daily
         WHERE platform = 'walmart' AND stat_date >= ? AND stat_date <= ?
         GROUP BY store_id, item_id`
      : `SELECT store_id, item_id, MAX(COALESCE(wfs_available_stock, 0)) AS lm_qty
         FROM fact_inventory_daily
         WHERE platform = 'walmart' AND snapshot_date >= ? AND snapshot_date <= ?
         GROUP BY store_id, item_id`;
    const [rows] = await db.execute(
      `SELECT COALESCE(NULLIF(d.owner_raw,''),'(未分配)') AS owner,
              d.store_id, COALESCE(NULLIF(ds.store_name,''), d.store_id) AS store_name, d.item_id,
              COALESCE(i.msku, d.mskus, '') AS msku,
              i.issue_reasons, i.suggested_action, i.metrics_json,
              st.profit_level, COALESCE(d.manual_lc, st.lifecycle_stage) AS lifecycle,
              st.total_inventory, d.launch_date,
              COALESCE(invx.wfs_stock, 0) AS wfs_stock,
              COALESCE(invx.non_wfs_stock, 0) AS non_wfs_stock,
              CASE WHEN COALESCE(wmaxx.wfs_max, 0) <= 0
                    ${lmUseWfs ? "AND COALESCE(lmx.lm_qty, 0) = 0" : ""}
                    AND COALESCE(trx.transit, 0) = 0
                    THEN 1 ELSE 0 END AS exempt_flag,
              p.id AS plan_id, p.indicator1_type, p.indicator1_target,
              p.target_sales_amount, p.target_gross_profit,
              p.indicator2_type, p.indicator2_target, p.deadline, p.normal_operation,
              p.note, p.issue_text, p.updated_by AS plan_updated_by, p.updated_at AS plan_updated_at
       FROM (
         SELECT store_id, item_id,
                MAX(COALESCE(NULLIF(owner,''),'')) AS owner_raw,
                SUBSTRING(GROUP_CONCAT(DISTINCT NULLIF(msku,'') ORDER BY msku SEPARATOR '/'),1,120) AS mskus,
                MAX(NULLIF(manual_lifecycle_stage,'')) AS manual_lc,
              DATE_FORMAT(MIN(launch_date),'%Y-%m-%d') AS launch_date
         FROM dim_product
         WHERE platform = 'walmart'
           AND COALESCE(NULLIF(product_management_status,''),'active') NOT IN ('inactive','archived')
         GROUP BY store_id, item_id
       ) d
       LEFT JOIN (
         SELECT store_id, item_id, MIN(profit_level) AS profit_level,
                MIN(lifecycle_stage) AS lifecycle_stage,
                SUM(COALESCE(total_inventory,0)) AS total_inventory,
                MAX(CASE WHEN product_type = 'CS测品' THEN 1 ELSE 0 END) AS is_cs
         FROM dim_product_business_state
         WHERE platform = 'walmart'
           AND stat_date = (SELECT MAX(stat_date) FROM dim_product_business_state)
         GROUP BY store_id, item_id
       ) st ON st.store_id = d.store_id AND st.item_id = d.item_id
       LEFT JOIN dim_store ds ON ds.platform = 'walmart' AND ds.store_id = d.store_id
       LEFT JOIN (
         SELECT store_id, item_id,
                SUM(COALESCE(wfs_available_stock, 0)) AS wfs_stock,
                SUM(GREATEST(COALESCE(available_stock, 0) - COALESCE(wfs_available_stock, 0), 0)) AS non_wfs_stock
         FROM fact_inventory_daily
         WHERE platform = 'walmart'
           AND snapshot_date = (SELECT MAX(snapshot_date) FROM fact_inventory_daily WHERE platform = 'walmart')
         GROUP BY store_id, item_id
       ) invx ON invx.store_id = d.store_id AND invx.item_id = d.item_id
       LEFT JOIN (
         SELECT store_id, item_id, MAX(COALESCE(wfs_available_stock, 0)) AS wfs_max
         FROM fact_inventory_daily
         WHERE platform = 'walmart' AND snapshot_date >= ? AND snapshot_date <= ?
         GROUP BY store_id, item_id
       ) wmaxx ON wmaxx.store_id = d.store_id AND wmaxx.item_id = d.item_id
       LEFT JOIN (
         ${lmxSub}
       ) lmx ON lmx.store_id = d.store_id AND lmx.item_id = d.item_id
       LEFT JOIN (
         SELECT dp.store_id, dp.item_id, SUM(t.in_transit) AS transit
         FROM (
           SELECT s.store_id, si.msku,
                  SUM(GREATEST(COALESCE(si.shipments_num,0)-COALESCE(si.received_num,0),0)) AS in_transit
           FROM fact_wfs_shipment s
           JOIN fact_wfs_shipment_item si
             ON si.platform=s.platform AND si.store_id=s.store_id AND si.shipment_id=s.shipment_id
           WHERE s.platform='walmart' AND s.to_closed_time IS NULL AND s.to_cancelled_time IS NULL
           GROUP BY s.store_id, si.msku
         ) t
         JOIN dim_product dp ON dp.platform='walmart' AND dp.store_id=t.store_id AND dp.msku=t.msku
         GROUP BY dp.store_id, dp.item_id
       ) trx ON trx.store_id = d.store_id AND trx.item_id = d.item_id
       LEFT JOIN ai_monthly_issue_item i
         ON i.plan_month = ? AND i.platform = 'walmart'
        AND i.store_id = d.store_id AND i.item_id = d.item_id
        AND i.report_id = (SELECT MAX(report_id) FROM ai_monthly_issue_item WHERE plan_month = ?)
       LEFT JOIN biz_monthly_plan p
         ON p.plan_month = ? AND p.platform = 'walmart'
        AND p.store_id = d.store_id AND p.item_id = d.item_id
        -- 2026-07-24 #4修复：按 店铺+商品ID 认规划，不再按会漂移的 MSKU 聚合串比对（唯一键同步改为 月+店+item）
       WHERE COALESCE(st.is_cs, 0) = 0
       ORDER BY (i.id IS NULL), owner, (p.id IS NOT NULL), d.item_id`,
      [pr0.start, pr0.end, pr0.start, pr0.end, planMonth, planMonth, planMonth],
    );
    // 上月自然月聚合（快照源，与周报口径一致）
    const [py, pm] = planMonth.split("-").map(Number);
    const prevMonth = pm === 1 ? `${py - 1}-12` : `${py}-${String(pm - 1).padStart(2, "0")}`;
    const pr = monthRange(prevMonth);
    const lm = await aggregatePrevMonthByItem(db, pr.start, pr.end);
    // 负责人别名归一 + owner 参数过滤（JS侧，别名与看板同源）
    const mapped = (rows as Array<Record<string, unknown>>).map((r) => {
      const m = lm.get(`${String(r.store_id)}|${String(r.item_id)}`);
      // 新品=上架时间(WFS 0→非0)落在规划月（2026-07-16 定稿）；新品由公司公式定目标，运营不填。
      // ∪ 2026-08-04 拍板：生命周期=新品期 且 无上架时间(待到货,WFS恒0推不出) 也视为新品(不填不扣不催)。
      //   一旦到货 launch_date 即被推导 → 到货当月走公司公式，次月起正常填报；
      //   人工生命周期优先——手工改为上升期/稳定期等的照常填报考核(手改必有原因，系统不碰人工字段)。
      const isNew = (typeof r.launch_date === "string" && String(r.launch_date).slice(0, 7) === planMonth)
        || (!r.launch_date && String((r as Record<string, unknown>).lifecycle ?? "") === "新品期");
      const isExempt = !isNew && r.plan_id === null && Number((r as Record<string, unknown>).exempt_flag ?? 0) === 1;
      return {
        is_exempt: isExempt ? 1 : 0,
        ...r, owner: normalizeOwner(r.owner) || "(未分配)",
        is_new_product: isNew ? 1 : 0,
        last_month_sales: m ? round2(m.sales) : null,
        last_month_qty: m ? Math.round(m.qty) : null,
        last_month_profit: m ? round2(m.profit) : null,
        last_month_ad: m ? round2(m.ad) : null,
      };
    });
    const filtered = owner ? mapped.filter((r) => r.owner === owner) : mapped;
    res.json({ planMonth, prevMonth, rows: filtered });
  } catch (e: unknown) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally {
    if (db) await db.end().catch(() => undefined);
  }
});

// POST /monthly-plan  录入/更新（人工记录通道；结构化校验保证考核可判定）
interface MonthlyPlanBody {
  plan_month?: string; store_id?: string; item_id?: string; msku?: string; owner?: string;
  issue_text?: string; indicator1_type?: string; indicator1_target?: number;
  indicator2_type?: string; indicator2_target?: number;
  deadline?: string; normal_operation?: boolean; note?: string; filled_by?: string;
  target_sales_amount?: number; target_gross_profit?: number;
}

// ── GET /monthly-plan/months  已有数据的规划月份（月报问题 ∪ 已填计划，倒序）──
// 2026-07-24 前端月份筛选改下拉（需求方拍板：只可选已有数据的月份）
router.get("/monthly-plan/months", async (_req: Request, res: Response): Promise<void> => {
  let db: mysql.Connection | null = null;
  try {
    db = await getDb();
    const [rows] = await db.execute(
      `SELECT plan_month FROM (
         SELECT DISTINCT plan_month FROM ai_monthly_issue_item
         UNION
         SELECT DISTINCT plan_month FROM biz_monthly_plan
       ) t ORDER BY plan_month DESC`,
    );
    res.json({ months: (rows as Array<{ plan_month: string }>).map((r) => String(r.plan_month)) });
  } catch (e: unknown) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally {
    if (db) await db.end().catch(() => undefined);
  }
});

// ── POST /monthly-plan/template-xlsx  批量导入模板（xlsx，含下拉数据验证）─────
// 2026-07-24 模板v3：前端传需填清单行（清单口径单一来源在前端 todo），后端仅渲染文件。
// 列（14）：店铺ID/店铺名称/ItemID/MSKU/月报问题/新品/正常运营(下拉)/指标1类型(下拉)/
//          指标1目标/指标2类型(下拉)/指标2目标/月销售额目标/月利润目标/补充说明。
router.post("/monthly-plan/template-xlsx", async (req: Request, res: Response): Promise<void> => {
  try {
    const planMonth = String(req.body?.plan_month ?? "");
    const owner = String(req.body?.owner ?? "").trim();
    const rows = Array.isArray(req.body?.rows) ? (req.body.rows as Array<Array<string | number | null>>) : [];
    if (!PLAN_MONTH_RE.test(planMonth) || !owner) { res.status(400).json({ error: "plan_month/owner 必填" }); return; }
    if (rows.length === 0 || rows.length > 1000) { res.status(400).json({ error: "rows 数量需为 1~1000" }); return; }
    const { Workbook } = await import("exceljs");
    const wb = new Workbook();
    const ws = wb.addWorksheet("月度规划");
    ws.addRow([
      "店铺ID(勿改)", "店铺名称(参考)", "ItemID(勿改)", "MSKU(勿改)", "月报问题(参考)", "新品(参考)",
      "正常运营(是/空)", "指标1类型", "指标1目标(数字)", "指标2类型(选填)", "指标2目标(选填)",
      "月销售额目标$(非新品必填)", "月利润目标$(非新品必填)", "补充说明(选填)",
    ]);
    ws.getRow(1).font = { bold: true };
    ws.views = [{ state: "frozen", ySplit: 1 }];
    [20, 22, 14, 16, 32, 8, 13, 13, 13, 13, 13, 22, 22, 26].forEach((w, i) => { ws.getColumn(i + 1).width = w; });
    for (const r of rows) ws.addRow((r ?? []).map((v) => (v === null || v === undefined ? "" : v)));
    const indList = '"清货,提高毛利率,提升销售额,新增变体,调整广告"';
    // M4：查全部清货(store|item)，清货行指标1下拉锁『清货』、指标2不设下拉（后端会拒非清货指标）
    const clearanceSet = new Set<string>();
    try {
      const cdb = await getDb();
      try {
        const [crows] = await cdb.execute(
          `SELECT dp.store_id, dp.item_id FROM (
             SELECT store_id, item_id, MAX(NULLIF(manual_lifecycle_stage,'')) AS manual_lc
             FROM dim_product WHERE platform='walmart' GROUP BY store_id, item_id
           ) dp
           LEFT JOIN (
             SELECT store_id, item_id, MIN(lifecycle_stage) AS ls FROM dim_product_business_state
             WHERE platform='walmart' AND stat_date=(SELECT MAX(stat_date) FROM dim_product_business_state)
             GROUP BY store_id, item_id
           ) st ON st.store_id=dp.store_id AND st.item_id=dp.item_id
           WHERE COALESCE(dp.manual_lc, st.ls)='清货期'`,
        );
        for (const cr of crows as Array<{ store_id: string; item_id: string }>) {
          clearanceSet.add(`${String(cr.store_id)}|${String(cr.item_id)}`);
        }
      } finally { await cdb.end().catch(() => undefined); }
    } catch { /* 查清货失败不阻断模板生成，退回全量下拉 */ }
    for (let i = 2; i <= rows.length + 1; i++) {
      const rr = rows[i - 2];
      const key = `${String(rr?.[0] ?? "").trim()}|${String(rr?.[2] ?? "").trim()}`;
      ws.getCell(`G${i}`).dataValidation = { type: "list", allowBlank: true, formulae: ['"是"'] };
      if (clearanceSet.has(key)) {
        ws.getCell(`H${i}`).dataValidation = { type: "list", allowBlank: false, formulae: ['"清货"'] };
      } else {
        ws.getCell(`H${i}`).dataValidation = { type: "list", allowBlank: true, formulae: [indList] };
        ws.getCell(`J${i}`).dataValidation = { type: "list", allowBlank: true, formulae: [indList] };
      }
    }
    const out = await wb.xlsx.writeBuffer();
    const fname = encodeURIComponent(`月度规划导入模板_${owner}_${planMonth}.xlsx`);
    res.setHeader("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
    res.setHeader("Content-Disposition", `attachment; filename*=UTF-8''${fname}`);
    res.end(Buffer.isBuffer(out) ? out : Buffer.from(out as ArrayBuffer));
  } catch (e: unknown) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  }
});

// ── POST /monthly-plan/parse-xlsx  解析导入的 xlsx → grid（前端沿用同一逐行校验链）──
router.post("/monthly-plan/parse-xlsx", async (req: Request, res: Response): Promise<void> => {
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
      for (let i = 1; i <= 14; i++) {
        arr.push(String(row.getCell(i).text ?? "").trim());
      }
      grid.push(arr);
    });
    res.json({ grid });
  } catch (e: unknown) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  }
});

router.post("/monthly-plan", async (req: Request, res: Response): Promise<void> => {
  const b = req.body as MonthlyPlanBody;
  const planMonth = String(b.plan_month ?? "");
  const storeId = String(b.store_id ?? "").trim();
  const itemId = String(b.item_id ?? "").trim();
  const msku = String(b.msku ?? "").trim();
  const owner = String(b.owner ?? "").trim();
  const cu = (req as { user?: { username?: string; display_name?: string; isSuperadmin?: boolean; roles?: Set<string> } }).user;
  const filledBy = String(cu?.username ?? "").trim() || String(b.filled_by ?? "").trim() || "admin_ui";
  const normalOp = b.normal_operation === true;
  if (!PLAN_MONTH_RE.test(planMonth)) { res.status(400).json({ error: "plan_month 非法" }); return; }
  if (!storeId || !itemId || !owner) { res.status(400).json({ error: "store_id/item_id/owner 必填" }); return; }

  // ── M1 越权闸门 + 8号截止（2026-08 新规；仅认证态且非超管时启用，超管[林翔/陈佳聪]绕过）──
  const isSuper = !!(cu && (cu.isSuperadmin || (cu.roles?.has("超管") ?? false)));
  if (cu?.username && !isSuper) {
    const meName = normalizeOwner(cu.display_name ?? "");
    if (!meName || normalizeOwner(owner) !== meName) {
      res.status(403).json({ error: "仅可填报/修改本人负责的产品目标；如需代填请联系超管（林翔/陈佳聪）" }); return;
    }
    const today = localDate(0);
    const writable = planMonth === today.slice(0, 7) && Number(today.slice(8, 10)) <= 7;
    if (!writable) {
      res.status(403).json({ error: `本月填报已于 7 号截止（今日 ${today}）；8 号起如需修改请联系超管（林翔/陈佳聪）代填。` }); return;
    }
  }

  const inds: Array<{ t: string; v: number }> = [];
  for (const i of ["1", "2"] as const) {
    const t = String((b as Record<string, unknown>)[`indicator${i}_type`] ?? "").trim();
    const vRaw = (b as Record<string, unknown>)[`indicator${i}_target`];
    if (!t) continue;
    if (!INDICATOR_TYPES.has(t)) { res.status(400).json({ error: `指标${i}类型非法: ${t}` }); return; }
    const v = Number(vRaw);
    if (!Number.isFinite(v) || v < 0 || v > 99999999) {
      res.status(400).json({ error: `指标${i}量化目标必填且需为非负数字` }); return;
    }
    inds.push({ t, v: Math.round(v * 100) / 100 });
  }
  if (!normalOp && inds.length === 0) {
    res.status(400).json({ error: "至少填写1个月优化指标（含量化目标），或勾选正常运营" }); return;
  }
  if (inds.length === 2 && inds[0].t === inds[1].t) {
    res.status(400).json({ error: "两个指标类型不能相同" }); return;
  }
  let deadline: string | null = null;
  if (!normalOp) {
    deadline = String(b.deadline ?? "").trim() || null;
    if (deadline && !/^\d{4}-\d{2}-\d{2}$/.test(deadline)) {
      res.status(400).json({ error: "deadline 格式应为 YYYY-MM-DD" }); return;
    }
  }

  let db: mysql.Connection | null = null;
  try {
    db = await getDb();
    // 单品业绩目标：非新品必填（含正常运营）；新品由公司公式核算，忽略提交值（2026-07-16 定稿）
    const [lrows] = await db.execute(
      `SELECT DATE_FORMAT(MIN(launch_date),'%Y-%m-%d') AS launch_date,
              MAX(NULLIF(manual_lifecycle_stage,'')) AS manual_lc FROM dim_product
       WHERE platform='walmart' AND store_id=? AND item_id=?`,
      [storeId, itemId],
    );
    const lr0 = (lrows as Array<{ launch_date: string | null; manual_lc: string | null }>)[0];
    const launch = String(lr0?.launch_date ?? "");
    const isNew = launch.slice(0, 7) === planMonth;
    // ── M4 清货判定（2026-08；与 todo/扣分同口径：生命周期=清货期，manual_lc 优先，回退 business_state）──
    let lifeSrc = String(lr0?.manual_lc ?? "").trim();
    if (!lifeSrc) {
      const [srows] = await db.execute(
        `SELECT MIN(lifecycle_stage) AS ls FROM dim_product_business_state
         WHERE platform='walmart' AND store_id=? AND item_id=?
           AND stat_date=(SELECT MAX(stat_date) FROM dim_product_business_state)`,
        [storeId, itemId],
      );
      lifeSrc = String((srows as Array<{ ls: string | null }>)[0]?.ls ?? "").trim();
    }
    const isClearance = lifeSrc === "清货期";
    // 清货：指标锁『清货』(清货数量>0)、禁其他指标（勾正常运营也须填清货数量+销售额，不豁免）
    if (isClearance) {
      const qh = inds.find((x) => x.t === "清货");
      if (!qh || !(qh.v > 0)) { res.status(400).json({ error: "清货期产品必须填『清货』指标（清货数量>0）" }); return; }
      if (inds.some((x) => x.t !== "清货")) { res.status(400).json({ error: "清货期产品只能填『清货』指标，不能选其他优化指标" }); return; }
    }
    let tSales: number | null = null;
    let tProfit: number | null = null;
    if (!isNew) {
      const s = Number(b.target_sales_amount);
      if (!Number.isFinite(s) || s < 0 || s > 99999999) {
        res.status(400).json({ error: "单品销售额目标必填且需为非负数字（新品除外）" }); return;
      }
      tSales = Math.round(s * 100) / 100;
      if (isClearance) {
        // M4 清货非新品：利润目标自动 = 销售额 × -10%（忽略前端提交值，只读）
        tProfit = Math.round(s * -0.10 * 100) / 100;
      } else {
        const g = Number(b.target_gross_profit);
        if (!Number.isFinite(g) || g > 99999999) {
          res.status(400).json({ error: "单品利润目标必填且需为数字（新品除外，清货可为负）" }); return;
        }
        tProfit = Math.round(g * 100) / 100;
      }
    }
    await db.execute(
      `INSERT INTO biz_monthly_plan
         (plan_month, platform, store_id, item_id, msku, owner, issue_text,
          indicator1_type, indicator1_target, indicator2_type, indicator2_target,
          deadline, normal_operation, note, target_sales_amount, target_gross_profit,
          created_by, updated_by)
       VALUES (?, 'walmart', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON DUPLICATE KEY UPDATE
         msku = VALUES(msku),
         owner = VALUES(owner), issue_text = VALUES(issue_text),
         indicator1_type = VALUES(indicator1_type), indicator1_target = VALUES(indicator1_target),
         indicator2_type = VALUES(indicator2_type), indicator2_target = VALUES(indicator2_target),
         deadline = VALUES(deadline), normal_operation = VALUES(normal_operation),
         note = VALUES(note),
         target_sales_amount = VALUES(target_sales_amount),
         target_gross_profit = VALUES(target_gross_profit),
         updated_by = VALUES(updated_by)`,
      [planMonth, storeId, itemId, msku, owner,
       String(b.issue_text ?? "").slice(0, 2000) || null,
       isClearance ? "清货" : (normalOp ? null : (inds[0]?.t ?? null)),
       isClearance ? (inds.find((x) => x.t === "清货")?.v ?? null) : (normalOp ? null : (inds[0]?.v ?? null)),
       isClearance ? null : (normalOp ? null : (inds[1]?.t ?? null)),
       isClearance ? null : (normalOp ? null : (inds[1]?.v ?? null)),
       deadline, normalOp ? 1 : 0,
       String(b.note ?? "").slice(0, 2000) || null, tSales, tProfit, filledBy, filledBy],
    );
    res.json({ ok: true, is_new_product: isNew ? 1 : 0 });
  } catch (e: unknown) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally {
    if (db) await db.end().catch(() => undefined);
  }
});

// POST /monthly-plan/variant-report  新增变体人工汇报（对账期）
router.post("/monthly-plan/variant-report", async (req: Request, res: Response): Promise<void> => {
  const b = req.body as { plan_month?: string; store_id?: string; item_id?: string; msku?: string;
                          variant_actual?: number; confirmed_by?: string };
  const planMonth = String(b.plan_month ?? "");
  if (!PLAN_MONTH_RE.test(planMonth)) { res.status(400).json({ error: "plan_month 非法" }); return; }
  const va = Number(b.variant_actual);
  if (!Number.isInteger(va) || va < 0 || va > 999) { res.status(400).json({ error: "variant_actual 需为非负整数" }); return; }
  const confirmedBy = String((req as { user?: { username?: string } }).user?.username ?? "").trim() || String(b.confirmed_by ?? "").trim() || "admin_ui";
  let db: mysql.Connection | null = null;
  try {
    db = await getDb();
    const [r] = await db.execute(
      `UPDATE biz_monthly_plan SET variant_actual = ?, variant_confirmed_by = ?, variant_confirmed_at = NOW()
       WHERE plan_month = ? AND platform = 'walmart' AND store_id = ? AND item_id = ?
         AND (indicator1_type = '新增变体' OR indicator2_type = '新增变体')`,
      [va, confirmedBy, planMonth, String(b.store_id ?? ""), String(b.item_id ?? "")],
    );
    const affected = (r as mysql.ResultSetHeader).affectedRows;
    if (!affected) { res.status(404).json({ error: "未找到含新增变体指标的对应规划" }); return; }
    res.json({ ok: true });
  } catch (e: unknown) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally {
    if (db) await db.end().catch(() => undefined);
  }
});

// ── GET /reports/:id/html/:file（受控读取报告HTML，不公开挂载静态目录） ──────

router.get("/reports/:id/html/:file", async (req: Request, res: Response): Promise<void> => {
  let db: mysql.Connection | null = null;
  try {
    const id = Number(req.params.id);
    if (!Number.isInteger(id) || id <= 0) { res.status(400).json({ error: "id 非法" }); return; }
    const file = String(req.params.file ?? "");
    if (!REPORT_FILE_RE.test(file) || file.includes("..")) {
      res.status(400).json({ error: "文件名非法" });
      return;
    }
    db = await getDb();
    const [rows] = await db.execute(
      `SELECT out_dir, status FROM ai_business_report WHERE id = ?`, [id],
    );
    const rec = (rows as Array<{ out_dir: string; status: string }>)[0];
    if (!rec) { res.status(404).json({ error: "报告不存在" }); return; }
    const baseDir = path.resolve(rec.out_dir);
    const target = path.resolve(path.join(baseDir, file));
    if (target !== path.join(baseDir, file) || !target.startsWith(baseDir + path.sep)) {
      res.status(400).json({ error: "路径非法" });
      return;
    }
    if (!fs.existsSync(target)) { res.status(404).json({ error: "文件不存在" }); return; }
    res.type("html").send(fs.readFileSync(target, "utf8"));
  } catch (e: unknown) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally {
    if (db) await db.end().catch(() => undefined);
  }
});

export default router;
