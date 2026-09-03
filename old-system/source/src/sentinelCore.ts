/**
 * sentinelCore.ts — P7 数据完整性哨兵·共享核心（2026-08-10 设计v4定稿）
 *
 * 被两处引用（本模块无 main，纯函数库）：
 *   - src/checkDataSentinel.ts        CLI：--check(20:15) / --remind(整点) / --weekly(周一09:00)
 *   - src/feishuCardCallbackRoutes.ts 卡片回调 biz='sentinel_fix'：确认→系统代码白名单执行→立即复查→回报
 *
 * 口径（需求方 2026-08-10 拍板）：
 *   - 权威口径=saleStat族(fact_sales_daily/订单利润RAW/fact_profit_daily) 日度恒等【零容差】；
 *   - fact_mp_sales_channel_daily 仅查当日有无（WFS判定专用，禁比数值）；
 *   - 库存快照缺失的修复=把修复当下的实时库存补录进缺失日（source_system='sentinel_backfill'，
 *     系 2026-07-18“snapshot_date恒为拉取当日”护栏的显式例外通道，仅限哨兵确认后触发）；
 *   - 修复执行主体=系统代码（本文件白名单命令，child_process），AI 不参与运行时决策；
 *   - 仅通报 SENTINEL_NOTIFY（默认陈佳聪）。
 */

import { execFile } from "child_process";
import * as mysql from "mysql2/promise";

export const SENTINEL_NOTIFY = (process.env.SENTINEL_NOTIFY ?? "陈佳聪").trim();
export const CXEC21_MIN_ROWS = Number(process.env.SENTINEL_CXEC21_MIN_ROWS ?? 600);
export const MAX_AUTO_ATTEMPTS = 2; // 同款自动修复满2次转人工

export function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
}

export function chinaDateStr(offsetDays: number): string {
  const now = new Date(Date.now() + offsetDays * 86400_000);
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}

// ── 检查注册表 ────────────────────────────────────────────────────────────────
export interface CheckDef {
  key: string;
  label: string;
  repairable: boolean;
  /** 本次主检要核的目标日期列表（T-N 以中国时区计） */
  targetDates: () => string[];
  /** 修复动作的人类可读说明（卡片展示；实际命令由 runRepair 白名单执行） */
  repairDesc: (d: string) => string;
}

export const CHECKS: CheckDef[] = [
  {
    key: "sales_family_eq", label: "saleStat族三表日度恒等",
    repairable: true, targetDates: () => [chinaDateStr(-2), chinaDateStr(-3), chinaDateStr(-4)],
    repairDesc: (d) => `重跑 ${d} 销量FACT+订单利润RAW 同步，并重算利润FACT(ETL覆盖T-4~昨天)`,
  },
  {
    key: "<REDACTED_FEISHU_SHEET_ID>_rows", label: "每日销售明细RAW(<REDACTED_FEISHU_SHEET_ID>)行数",
    repairable: true, targetDates: () => [chinaDateStr(-2)],
    repairDesc: (d) => `重生成 ${d} 每日销售明细（--only=detail）`,
  },
  {
    key: "inventory_snapshot", label: "当日库存快照存在",
    repairable: true, targetDates: () => [chinaDateStr(0)],
    repairDesc: (d) => d === chinaDateStr(0)
      ? `立即拉取实时库存写入今日快照`
      : `把修复当下的实时库存补录进 ${d}（标记 sentinel_backfill，近似值）`,
  },
  {
    key: "msku_blank", label: "msku空串脏行(近7天增量)",
    repairable: false, targetDates: () => [chinaDateStr(-2)],
    repairDesc: () => "无自动修复：疑似写入方bug苗头，需人工排查",
  },
  {
    key: "channel_presence", label: "渠道表当日有无数据",
    repairable: true, targetDates: () => [chinaDateStr(-2)],
    repairDesc: (d) => `重跑 ${d} 渠道订单同步（--start/--end 同日）`,
  },
  {
    // 20:30 构建器写 stat_date=最新可用业务日(=当天T-2)，故 20:15 检查时点库内最新只能到 T-3（T-1 会天天误报，2026-08-11 dry-run 实测修正）
    key: "business_state_snapshot", label: "经营状态快照(T-3)存在",
    repairable: true, targetDates: () => [chinaDateStr(-3)],
    repairDesc: (d) => `重建 ${d} 经营状态快照（buildProductBusinessState --date；人工字段取当前值，近似历史）`,
  },
  {
    // 2026-08-18 批4c：订单利润V2三链守恒（全量全局校验，与日期无关，targetDates给当天仅作展示位）
    key: "v2_conservation", label: "订单利润V2守恒(退货/折扣/仓储)",
    repairable: false, targetDates: () => [chinaDateStr(0)],
    repairDesc: () => "无自动修复：退货/折扣=重跑对应同步(FACT窗口重算幂等)；仓储=重跑 expandStorageFeeDaily --confirm-write",
  },
];

export function checkDef(key: string): CheckDef | undefined {
  return CHECKS.find((c) => c.key === key);
}

// ── 核查实现（全部只读） ──────────────────────────────────────────────────────
export async function verifyCheck(db: mysql.Connection, key: string, date: string): Promise<{ ok: boolean; detail: string }> {
  const one = async (sql: string, params: Array<string | number>): Promise<Record<string, unknown>> => {
    const [rows] = await db.execute(sql, params);
    return ((rows as Array<Record<string, unknown>>)[0] ?? {});
  };
  if (key === "sales_family_eq") {
    const s = await one(
      `SELECT COUNT(*) c, COALESCE(SUM(sales_qty),0) q, ROUND(COALESCE(SUM(sales_amount),0),2) a
       FROM fact_sales_daily WHERE platform='walmart' AND stat_date=?`, [date]);
    const r = await one(
      `SELECT COALESCE(SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(row_json,'$."今日销量"')) AS DECIMAL(14,2))),0) q,
              ROUND(COALESCE(SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(row_json,'$."今日销售额（$）"')) AS DECIMAL(14,2))),0),2) a
       FROM raw_feishu_table WHERE sheet_id='<REDACTED_FEISHU_SHEET_ID>'
         AND JSON_UNQUOTE(JSON_EXTRACT(row_json,'$."日期"'))=?`, [date]);
    const p = await one(
      `SELECT ROUND(COALESCE(SUM(sales_amount),0),2) a
       FROM fact_profit_daily WHERE platform='walmart' AND stat_date=?`, [date]);
    const sc = Number(s.c), sq = Number(s.q), sa = Number(s.a), rq = Number(r.q), ra = Number(r.a), pa = Number(p.a);
    // 2026-08-11 修漏报洞：三源全空时 0=0=0 恒等会静默通过；销量表行数=0 直接判异常
    const ok = sc > 0 && sq === rq && sa === ra && pa === sa;
    return { ok, detail: `销量表 rows=${sc}/qty=${sq}/amt=${sa} | 订单利润RAW qty=${rq}/amt=${ra} | 利润FACT amt=${pa}${ok ? "（三表恒等✓）" : (sc === 0 ? "（销量表0行，疑三源全空❌）" : "（不等❌）")}` };
  }
  if (key === "<REDACTED_FEISHU_SHEET_ID>_rows") {
    const r = await one(
      `SELECT COUNT(*) c FROM raw_feishu_table WHERE sheet_id='<REDACTED_FEISHU_SHEET_ID>'
         AND JSON_UNQUOTE(JSON_EXTRACT(row_json,'$."日期"'))=?`, [date]);
    const c = Number(r.c);
    return { ok: c >= CXEC21_MIN_ROWS, detail: `明细行数=${c}（阈值≥${CXEC21_MIN_ROWS}）` };
  }
  if (key === "v2_conservation") {
    // ①退货：RAW(REFUND)↔FACT 件数/金额逐分守恒（口径见 syncWalmartReturnOrders）
    const r1 = await one(
      `SELECT SUM(quantity) q, ROUND(SUM(line_total_amount),2) a FROM raw_walmart_return_order WHERE return_type='REFUND'`, []);
    const r2 = await one(
      `SELECT SUM(refund_qty) q, ROUND(SUM(refund_amount),2) a FROM fact_refund_daily WHERE platform='walmart'`, []);
    const refundOk = Number(r1.q ?? 0) === Number(r2.q ?? 0) && Number(r1.a ?? 0) === Number(r2.a ?? 0);
    // ②折扣：RAW(非取消)↔FACT 金额逐分守恒
    const p1 = await one(
      `SELECT ROUND(SUM(ABS(discount_amount)),2) a FROM raw_mp_order_discount WHERE order_status <> 7`, []);
    const p2 = await one(
      `SELECT ROUND(SUM(discount_amount),2) a FROM fact_promo_discount_daily WHERE platform='walmart'`, []);
    const promoOk = Number(p1.a ?? 0) === Number(p2.a ?? 0);
    // ③仓储：账期源表↔日摊派生表 总额守恒（±0.05 舍入容差）
    const s1 = await one(`SELECT ROUND(SUM(final_storage_fee),2) a FROM fact_wfs_storage_fee`, []);
    const s2 = await one(`SELECT ROUND(SUM(storage_fee),2) a FROM fact_storage_fee_daily WHERE platform='walmart'`, []);
    const storageOk = Math.abs(Number(s1.a ?? 0) - Number(s2.a ?? 0)) < 0.05;
    const ok = refundOk && promoOk && storageOk;
    return { ok, detail:
      `退货 RAW ${r1.q ?? 0}件/$${r1.a ?? 0} vs FACT ${r2.q ?? 0}件/$${r2.a ?? 0} ${refundOk ? "✓" : "✗"}；` +
      `折扣 RAW $${p1.a ?? 0} vs FACT $${p2.a ?? 0} ${promoOk ? "✓" : "✗"}；` +
      `仓储 账期 $${s1.a ?? 0} vs 日摊 $${s2.a ?? 0} ${storageOk ? "✓" : "✗"}` };
  }
  if (key === "inventory_snapshot") {
    const r = await one(
      `SELECT COUNT(*) c FROM fact_inventory_daily WHERE platform='walmart' AND snapshot_date=?`, [date]);
    const c = Number(r.c);
    return { ok: c > 0, detail: `${date} 库存快照行数=${c}` };
  }
  if (key === "msku_blank") {
    const r = await one(
      `SELECT COUNT(*) c FROM fact_sales_daily WHERE platform='walmart' AND msku=''
         AND stat_date BETWEEN ? AND ?`, [chinaDateStr(-7), chinaDateStr(-2)]);
    const c = Number(r.c);
    return { ok: c === 0, detail: `近7天(T-7~T-2) msku空串行=${c}` };
  }
  if (key === "channel_presence") {
    const r = await one(
      `SELECT COUNT(*) c FROM fact_mp_sales_channel_daily WHERE platform='walmart' AND stat_date=?`, [date]);
    const c = Number(r.c);
    return { ok: c > 0, detail: `${date} 渠道表行数=${c}（仅查有无，不比数值）` };
  }
  if (key === "business_state_snapshot") {
    const r = await one(
      `SELECT COUNT(*) c FROM dim_product_business_state WHERE platform='walmart' AND stat_date=?`, [date]);
    const c = Number(r.c);
    return { ok: c > 0, detail: `${date} 经营状态快照行数=${c}` };
  }
  return { ok: true, detail: `未知检查 ${key}（跳过）` };
}

// ── 白名单修复执行（系统代码，确定性命令；卡片只传事件id，命令由此处按 key+date 推导） ──
const APP_DIR = "/opt/lingxing-auto";
const PROFIT_ETL = ["/opt/ads-ai-api/scripts/build_fact_profit_daily_from_raw_feishu.py", "--execute"];

function run(cmd: string, args: string[], timeoutMs: number): Promise<{ ok: boolean; tail: string }> {
  return new Promise((resolve) => {
    execFile(cmd, args, { cwd: APP_DIR, timeout: timeoutMs, maxBuffer: 8 * 1024 * 1024 }, (err, stdout, stderr) => {
      const tail = `${String(stdout).slice(-500)}${stderr ? `\nSTDERR:${String(stderr).slice(-300)}` : ""}`;
      resolve({ ok: !err, tail: err ? `${String(err.message).slice(0, 200)}\n${tail}` : tail });
    });
  });
}

export async function runRepair(db: mysql.Connection, key: string, date: string): Promise<{ ok: boolean; log: string }> {
  const T = 15 * 60 * 1000;
  const logs: string[] = [];
  const step = async (label: string, cmd: string, args: string[]): Promise<boolean> => {
    const r = await run(cmd, args, T);
    logs.push(`[${label}] ${r.ok ? "OK" : "FAIL"}`);
    if (!r.ok) logs.push(r.tail);
    return r.ok;
  };
  if (key === "sales_family_eq") {
    if (!(await step("销量FACT", "npx", ["ts-node", "src/syncLingxingDailyToDb.ts", `--date=${date}`]))) return { ok: false, log: logs.join("\n") };
    if (!(await step("订单利润RAW", "npx", ["ts-node", "src/syncOrderProfitDaily.ts", `--date=${date}`]))) return { ok: false, log: logs.join("\n") };
    if (!(await step("利润ETL", "python3", PROFIT_ETL))) return { ok: false, log: logs.join("\n") };
    return { ok: true, log: logs.join("\n") };
  }
  if (key === "<REDACTED_FEISHU_SHEET_ID>_rows") {
    const ok = await step("明细重生成", "npx", ["ts-node", "src/syncLingxingToRawFeishu.ts", date, "--only=detail"]);
    return { ok, log: logs.join("\n") };
  }
  if (key === "inventory_snapshot") {
    if (date === chinaDateStr(0)) {
      const ok = await step("库存拉取(今日)", "npx", ["ts-node", "src/syncLingxingDailyToDb.ts", `--date=${chinaDateStr(-2)}`]);
      return { ok, log: logs.join("\n") };
    }
    // 历史缺失日：补录“修复当下”的库存（复制最新快照，标记来源；需求方 2026-08-10 拍板的显式例外通道）
    const [latestRows] = await db.execute(
      `SELECT MAX(snapshot_date) d FROM fact_inventory_daily WHERE platform='walmart'`);
    const latest = String((latestRows as Array<Record<string, unknown>>)[0]?.d ?? "");
    if (!latest) return { ok: false, log: "无任何库存快照可作为补录源" };
    const [ret] = await db.execute(
      `INSERT INTO fact_inventory_daily
         (snapshot_date, platform, store_id, store_name, item_id, msku, sku,
          available_stock, non_wfs_available_stock, wfs_available_stock, warehouse_stock,
          inbound_stock, reserved_stock, stock_days, source_system, source_raw_id)
       SELECT ?, platform, store_id, store_name, item_id, msku, sku,
              available_stock, non_wfs_available_stock, wfs_available_stock, warehouse_stock,
              inbound_stock, reserved_stock, stock_days, 'sentinel_backfill', source_raw_id
       FROM fact_inventory_daily
       WHERE platform='walmart' AND snapshot_date=?
       ON DUPLICATE KEY UPDATE snapshot_date=fact_inventory_daily.snapshot_date`, [date, latest]);
    const n = Number((ret as mysql.ResultSetHeader).affectedRows ?? 0);
    logs.push(`[库存补录] 以 ${latest} 快照补录 ${date}，affected=${n}（source_system=sentinel_backfill，近似值）`);
    return { ok: n > 0, log: logs.join("\n") };
  }
  if (key === "channel_presence") {
    const ok = await step("渠道订单同步", "npx", ["ts-node", "src/syncMpOrdersChannelDaily.ts", `--start=${date}`, `--end=${date}`, "--execute"]);
    return { ok, log: logs.join("\n") };
  }
  if (key === "business_state_snapshot") {
    const ok = await step("经营状态重建", "npx", ["ts-node", "src/buildProductBusinessState.ts", `--date=${date}`, "--confirm-write"]);
    return { ok, log: logs.join("\n") };
  }
  return { ok: false, log: `检查项 ${key} 无自动修复动作` };
}

// ── 事件表访问 ────────────────────────────────────────────────────────────────
export interface SentinelEvent {
  id: number; check_key: string; target_date: string; status: string;
  attempt_count: number; remind_count: number; detail: string;
}

export async function upsertOpenEvent(db: mysql.Connection, key: string, date: string, detail: string): Promise<number> {
  const [ret] = await db.execute(
    `INSERT INTO event_sentinel_alert (check_key, target_date, detail, status, first_alert_at)
     VALUES (?, ?, ?, 'open', NOW())
     ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id), detail=VALUES(detail),
       status=IF(status='resolved','open',status),
       first_alert_at=IF(status='resolved',NOW(),first_alert_at)`,
    [key, date, detail.slice(0, 480)]);
  return Number((ret as mysql.ResultSetHeader).insertId ?? 0);
}

export async function loadEvent(db: mysql.Connection, id: number): Promise<SentinelEvent | null> {
  const [rows] = await db.execute(
    `SELECT id, check_key, DATE_FORMAT(target_date,'%Y-%m-%d') target_date, status, attempt_count, remind_count, detail
     FROM event_sentinel_alert WHERE id=?`, [id]);
  const r = (rows as Array<Record<string, unknown>>)[0];
  if (!r) return null;
  return { id: Number(r.id), check_key: String(r.check_key), target_date: String(r.target_date),
    status: String(r.status), attempt_count: Number(r.attempt_count), remind_count: Number(r.remind_count),
    detail: String(r.detail ?? "") };
}

export async function listUnresolved(db: mysql.Connection): Promise<SentinelEvent[]> {
  const [rows] = await db.execute(
    `SELECT id, check_key, DATE_FORMAT(target_date,'%Y-%m-%d') target_date, status, attempt_count, remind_count, detail
     FROM event_sentinel_alert WHERE status IN ('open','manual') ORDER BY id`);
  return (rows as Array<Record<string, unknown>>).map((r) => ({
    id: Number(r.id), check_key: String(r.check_key), target_date: String(r.target_date),
    status: String(r.status), attempt_count: Number(r.attempt_count), remind_count: Number(r.remind_count),
    detail: String(r.detail ?? "") }));
}

export async function markResolved(db: mysql.Connection, id: number, by: string): Promise<void> {
  await db.execute(
    `UPDATE event_sentinel_alert SET status='resolved', resolved_at=NOW(), resolved_by=? WHERE id=?`, [by, id]);
}

export async function markManual(db: mysql.Connection, id: number): Promise<void> {
  await db.execute(`UPDATE event_sentinel_alert SET status='manual' WHERE id=?`, [id]);
}

export async function bumpAttempt(db: mysql.Connection, id: number): Promise<void> {
  await db.execute(`UPDATE event_sentinel_alert SET attempt_count=attempt_count+1 WHERE id=?`, [id]);
}

export async function bumpRemind(db: mysql.Connection, id: number): Promise<void> {
  await db.execute(`UPDATE event_sentinel_alert SET remind_count=remind_count+1, last_remind_at=NOW() WHERE id=?`, [id]);
}

// ── 卡片构造 ─────────────────────────────────────────────────────────────────
export function buildFixCard(ev: SentinelEvent, test: boolean): { card: Record<string, unknown>; fb: string } {
  const def = checkDef(ev.check_key);
  const label = def?.label ?? ev.check_key;
  const attemptNote = ev.attempt_count > 0 ? `（自动修复已尝试 ${ev.attempt_count} 次）` : "";
  const isInvToday = ev.check_key === "inventory_snapshot" && ev.target_date === chinaDateStr(0);
  const urgency = isInvToday ? `\n<font color='red'>**⏰ 今日 23:59 前不修复，该日快照将永久缺失**</font>` : "";
  const card = {
    config: { wide_screen_mode: true },
    header: { template: "red", title: { tag: "plain_text", content: `🚨 数据哨兵异常 · ${label}` } },
    elements: [
      { tag: "div", text: { tag: "lark_md", content:
        `**检查项**：${label}${attemptNote}\n**目标日期**：${ev.target_date}\n**实测**：${ev.detail}${urgency}` } },
      { tag: "div", text: { tag: "lark_md", content:
        `**修复动作**（点确认后由系统代码自动执行并当场复查）：\n${def?.repairDesc(ev.target_date) ?? "-"}` } },
      { tag: "action", actions: [
        { tag: "button", text: { tag: "plain_text", content: "✅ 确认执行修复" }, type: "primary",
          value: Object.assign({ biz: "sentinel_fix", id: ev.id, choice: "fix" }, test ? { test: 1 } : {}) },
        { tag: "button", text: { tag: "plain_text", content: "🕓 暂不处理" }, type: "default",
          value: Object.assign({ biz: "sentinel_fix", id: ev.id, choice: "later" }, test ? { test: 1 } : {}) },
      ] },
      { tag: "note", elements: [{ tag: "plain_text", content: `未处理将每小时提醒（当日至23:59，次日09:00起）。仅${SENTINEL_NOTIFY}可操作。` }] },
    ],
  };
  const fb = `【数据哨兵异常】${label}｜${ev.target_date}｜${ev.detail}；请在卡片点“确认执行修复”。`;
  return { card, fb };
}

export function buildManualCard(ev: SentinelEvent, test: boolean): { card: Record<string, unknown>; fb: string } {
  const def = checkDef(ev.check_key);
  const label = def?.label ?? ev.check_key;
  const why = def?.repairable ? `自动修复已尝试 ${ev.attempt_count} 次仍未通过` : "该项无自动修复动作";
  const card = {
    config: { wide_screen_mode: true },
    header: { template: "orange", title: { tag: "plain_text", content: `🔧 需人工排查 · ${label}` } },
    elements: [
      { tag: "div", text: { tag: "lark_md", content:
        `**检查项**：${label}\n**目标日期**：${ev.target_date}\n**实测**：${ev.detail}\n**说明**：<font color='red'>${why}</font>，请人工排查根因；处理完成后哨兵复查通过将自动停止提醒。` } },
      { tag: "action", actions: [
        { tag: "button", text: { tag: "plain_text", content: "👌 知悉" }, type: "default",
          value: Object.assign({ biz: "sentinel_fix", id: ev.id, choice: "ack" }, test ? { test: 1 } : {}) },
      ] },
      { tag: "note", elements: [{ tag: "plain_text", content: "每小时提醒直至复查通过。" }] },
    ],
  };
  const fb = `【数据哨兵·需人工排查】${label}｜${ev.target_date}｜${ev.detail}（${why}）`;
  return { card, fb };
}

export function buildResolvedCard(ev: SentinelEvent, extra: string): { card: Record<string, unknown>; fb: string } {
  const def = checkDef(ev.check_key);
  const label = def?.label ?? ev.check_key;
  const card = {
    config: { wide_screen_mode: true },
    header: { template: "green", title: { tag: "plain_text", content: `✅ 数据哨兵·已解决 · ${label}` } },
    elements: [
      { tag: "div", text: { tag: "lark_md", content:
        `**检查项**：${label}\n**目标日期**：${ev.target_date}\n**复查结果**：${extra}` } },
      { tag: "note", elements: [{ tag: "plain_text", content: "本事件闭环，停止提醒。" }] },
    ],
  };
  const fb = `【数据哨兵·已解决】${label}｜${ev.target_date}｜${extra}`;
  return { card, fb };
}
