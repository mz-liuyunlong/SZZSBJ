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

async function aggregateActuals(
  db: mysql.Connection, start: string, end: string,
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
    const owner = String(j["负责人"] ?? "").trim() || "(未分配)";
    const cur = map.get(owner) ?? { sales: 0, profit: 0 };
    cur.sales += num(j["今日销售额（$）"]);
    cur.profit += num(j["毛利润（$）"]);
    map.set(owner, cur);
  }
  return map;
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
    res.json({ rows });
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
  const expected = process.env.TARGET_EDIT_PASSWORD ?? "";
  if (!expected) {
    res.status(503).json({ error: "服务端未配置目标编辑密码（TARGET_EDIT_PASSWORD），拒绝写入" });
    return;
  }
  const body = req.body as TargetWriteBody;
  if ((body.password ?? "") !== expected) {
    res.status(403).json({ error: "密码错误，目标未写入" });
    return;
  }
  const changedBy = String(body.changed_by ?? "").trim();
  if (!changedBy) {
    res.status(400).json({ error: "changed_by（调整人姓名）不能为空" });
    return;
  }
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
    res.json({ ok: true, created, updated, unchanged, total: items.length });
  } catch (e: unknown) {
    if (db) await db.rollback().catch(() => undefined);
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally {
    if (db) await db.end().catch(() => undefined);
  }
});

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
    const [mActual, qActual, [targetRows]] = await Promise.all([
      m.start <= mEnd ? aggregateActuals(db, m.start, mEnd) : Promise.resolve(new Map<string, OwnerActual>()),
      q.start <= qEnd ? aggregateActuals(db, q.start, qEnd) : Promise.resolve(new Map<string, OwnerActual>()),
      db.execute(
        `SELECT target_type, period_key, owner, metric, target_value FROM biz_business_target
         WHERE (target_type='monthly' AND period_key=?) OR (target_type='quarterly' AND period_key=?)`,
        [monthKey, quarterKey],
      ),
    ]);

    interface OwnerTargets { m_sales: number; m_profit: number; q_sales: number; q_profit: number; }
    const targets = new Map<string, OwnerTargets>();
    for (const r of targetRows as Array<{ target_type: string; owner: string; metric: string; target_value: string | number }>) {
      const t = targets.get(r.owner) ?? { m_sales: 0, m_profit: 0, q_sales: 0, q_profit: 0 };
      const v = Number(r.target_value) || 0;
      if (r.target_type === "monthly") { if (r.metric === "sales") t.m_sales = v; else t.m_profit = v; }
      else { if (r.metric === "sales") t.q_sales = v; else t.q_profit = v; }
      targets.set(r.owner, t);
    }

    const owners = new Set<string>([...targets.keys(), ...mActual.keys(), ...qActual.keys()]);
    const rows = [...owners].map((owner) => {
      const t = targets.get(owner) ?? { m_sales: 0, m_profit: 0, q_sales: 0, q_profit: 0 };
      const ma = mActual.get(owner) ?? { sales: 0, profit: 0 };
      const qa = qActual.get(owner) ?? { sales: 0, profit: 0 };
      return {
        owner,
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

    res.json({
      monthKey, quarterKey, dataEnd,
      monthWindow: { start: m.start, end: mEnd, timeProgressPct: timeProgressPct(m.start, m.end) },
      quarterWindow: { start: q.start, end: qEnd, timeProgressPct: timeProgressPct(q.start, q.end) },
      company, rows,
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
  const expected = process.env.TARGET_EDIT_PASSWORD ?? "";
  if (!expected) { res.status(503).json({ error: "服务端未配置密码，拒绝生成" }); return; }
  const body = req.body as {
    password?: string; report_type?: string; win_start?: string; win_end?: string; owners?: string;
  };
  if ((body.password ?? "") !== expected) { res.status(403).json({ error: "密码错误" }); return; }

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
  // 生成成功后按 REPORT_ID 精确推送（partial 报告只私聊该负责人，逻辑在推送脚本内）
  const cmd =
    `cd ${PROJECT_DIR} && set -o pipefail; ` +
    `RID=$(python3 scripts/generate_weekly_report.py --report-type '${reportType}' ` +
    `--win-start '${winStart}' --win-end '${winEnd}' --owners '${owners}' --trigger manual ` +
    `| tee -a '${logFile}' | sed -n 's/^REPORT_ID=//p'); ` +
    `if [ -n "$RID" ] && [ "$RID" != "None" ]; then ` +
    `npx ts-node src/sendBusinessReportNotify.ts --report-id "$RID" --send >> '${logFile}' 2>&1; fi`;
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
