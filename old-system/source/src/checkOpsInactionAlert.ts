/**
 * checkOpsInactionAlert.ts — 重点产品无运营动作监控 + 断货提醒（v1.3，2026-07-16 三次定稿）
 *
 * cron：每日 09:30（错开 09:05 批C、09:20 月度规划催办）。观察期以 --send --test-send 只进测试群。
 *
 * 口径（需求方拍板，07-16 下午版）：
 *   A. 无动作监控（纯运营惰怠盯防，仅限当前有库存产品）：
 *      池 = 在营非归档非CS ∧ WFS库存>0 ∧（5天不出单[新品期/测品期豁免] ∨ D级）
 *      无动作日 = 该日有日志行但 log_content 为空 或 命中无动作白名单（有行未填=无动作）
 *      触发 = 连续5个日志日无动作（v1.4：删除"近8天≥5天"密度规则——间歇有动作不通报，
 *        需求方 2026-07-16 拍板；最近有行日有动作则不报）
 *      只在"有日志行"的日子判定：断货期间无行，窗口自动跳过，复货后接着数。
 *   B. 断货提醒（补货/归档决策提醒，不算惰怠不追责）：
 *      断货补货提醒 = WFS=0 ∧ 近5个数据日有销量 ∧ 生命周期≠清货期（卖着卖着断货，提醒补货）
 *      断货归档提醒 = WFS=0 ∧ 生命周期=清货期（在途数据未建设，提示运营人工核实在途：
 *        有在途继续清货，确认不再卖则归档；系统不代判）
 *      纯零库存且近5天无销量的非清货期沉睡产品不打扰（月度规划体系管）。
 *   生命周期口径 = 人工优先（dim_product.manual_lifecycle_stage）系统兜底。
 *   频控 = 挂起模型：未解除不重报；无动作类出现实质动作日解除；
 *          断货类 WFS恢复>0 或产品移出在营（归档/停用）解除。留痕不删行。
 *
 * 分层：读 dim/fact/biz 层，只写 EVENT 层 event_ops_inaction_alert；不碰人工表。
 * 用法：
 *   npx ts-node src/checkOpsInactionAlert.ts          # dry-run：完整判定+预览，零发送零写入
 *   npx ts-node src/checkOpsInactionAlert.ts --send   # 真实发送+写 alert/resolve
 *   --test-send 或 BUSINESS_REPORT_FORCE_TEST=1 → 消息只进测试群（标注原目标）且不写 EVENT 表
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import {
  NotifyTarget,
  SendResult,
  getTestChatId,
  resolveActiveMembers,
  sendCardToTarget,
} from "./feishuNotify";
import { buildOpsInactionCard } from "./notifyRules/reminderCards";

const OWNER_ALIASES: Record<string, string> = { "啊四": "林翔" };
function normalizeOwner(name: unknown): string {
  const n = String(name ?? "").trim();
  return OWNER_ALIASES[n] ?? n;
}

// 无动作表态白名单（2026-07-16 拍板：手打变体如"今日无操作"同样算无动作，堵绕过漏洞）
const NO_ACTION_TEXTS = ["今日无运营", "今日无操作", "无运营", "无操作"];
const EXEMPT_LIFECYCLES = new Set(["新品期", "测品期"]);
const CLEARANCE_LIFECYCLE = "清货期";
const SALES_WINDOW = 5; // 不出单/断货销量窗口：最近5个数据日（07-16 拍板由7改5）
const R1_DAYS = 5;      // 连续无动作阈值
const LOG_WINDOW = 8;   // 日志窗口（多取几天，断货跳天后仍够凑连续5个有行日）
const RULE_STOCKOUT_REPLENISH = "断货补货提醒";
const RULE_STOCKOUT_ARCHIVE = "断货归档提醒";

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host:     process.env.DB_HOST     ?? "127.0.0.1",
    port:     Number(process.env.DB_PORT ?? 3306),
    user:     process.env.DB_USER     ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME     ?? "walmart_ai_data",
  });
}

function localDate(): string {
  const d = new Date();
  const p = (x: number) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

interface Product {
  storeId: string; itemId: string; mskus: string; owner: string;
  lifecycle: string; profitLevel: string;
}

/**
 * 2026-07-20 需求方指令：通报按店铺维度分组展示。
 * 店铺名三层递补（与待认领日报同口径）：dim_product 兄弟行 → dim_store_config → fact_inventory_daily；
 * 整店无名保留 store_id 兜底。后两层带防御，查询失败只记日志不影响主流程。
 */
async function fetchStoreNames(db: mysql.Connection): Promise<Map<string, string>> {
  const m = new Map<string, string>();
  const merge = (rows: unknown[]): void => {
    for (const r of rows as Array<{ store_id: unknown; store_name: unknown }>) {
      const id = String(r.store_id ?? "").trim();
      const name = String(r.store_name ?? "").trim();
      if (id && name && !m.has(id)) m.set(id, name);
    }
  };
  const [p] = await db.execute(
    `SELECT store_id, MAX(NULLIF(TRIM(store_name),'')) AS store_name
     FROM dim_product WHERE store_id IS NOT NULL AND store_id<>'' GROUP BY store_id`);
  merge(p as unknown[]);
  try {
    const [cfg] = await db.execute(
      `SELECT store_id, store_name FROM dim_store_config WHERE store_id IS NOT NULL AND store_id<>''`);
    merge(cfg as unknown[]);
  } catch (e) { console.log(`[警告] dim_store_config 店铺名兜底失败（忽略）: ${e instanceof Error ? e.message : String(e)}`); }
  try {
    const [inv] = await db.execute(
      `SELECT store_id, MAX(NULLIF(TRIM(store_name),'')) AS store_name
       FROM fact_inventory_daily WHERE store_id IS NOT NULL AND store_id<>'' GROUP BY store_id`);
    merge(inv as unknown[]);
  } catch (e) { console.log(`[警告] fact_inventory_daily 店铺名兜底失败（忽略）: ${e instanceof Error ? e.message : String(e)}`); }
  return m;
}

interface Verdict {
  p: Product; poolReason: string; ruleHit: string;
  detail: Array<{ d: string; act: 0 | 1 }>; lastActionDate: string | null;
}

interface Stockout {
  p: Product; rule: string; sales5d: number; inbound: number;
}

async function fetchProducts(db: mysql.Connection): Promise<Map<string, Product>> {
  const [rows] = await db.execute(
    `SELECT d.store_id, d.item_id, d.mskus, d.owner_raw, d.manual_lc,
            st.profit_level, st.lifecycle_stage, st.is_cs
     FROM (
       SELECT store_id, item_id,
              MAX(COALESCE(NULLIF(owner,''),'')) AS owner_raw,
              SUBSTRING(GROUP_CONCAT(DISTINCT NULLIF(msku,'') ORDER BY msku SEPARATOR '/'),1,120) AS mskus,
              MAX(NULLIF(manual_lifecycle_stage,'')) AS manual_lc
       FROM dim_product
       WHERE platform = 'walmart'
         AND COALESCE(NULLIF(product_management_status,''),'active') NOT IN ('inactive','archived')
       GROUP BY store_id, item_id
     ) d
     LEFT JOIN (
       SELECT store_id, item_id, MIN(profit_level) AS profit_level,
              MIN(lifecycle_stage) AS lifecycle_stage,
              MAX(CASE WHEN product_type = 'CS测品' THEN 1 ELSE 0 END) AS is_cs
       FROM dim_product_business_state
       WHERE platform = 'walmart'
         AND stat_date = (SELECT MAX(stat_date) FROM dim_product_business_state)
       GROUP BY store_id, item_id
     ) st ON st.store_id = d.store_id AND st.item_id = d.item_id
     WHERE COALESCE(st.is_cs, 0) = 0`,
  );
  const map = new Map<string, Product>();
  for (const r of rows as Array<Record<string, unknown>>) {
    const storeId = String(r.store_id);
    const itemId = String(r.item_id);
    map.set(`${storeId}|${itemId}`, {
      storeId, itemId,
      mskus: String(r.mskus ?? ""),
      owner: normalizeOwner(r.owner_raw) || "(未分配)",
      lifecycle: String(r.manual_lc ?? "").trim() || String(r.lifecycle_stage ?? "").trim(),
      profitLevel: String(r.profit_level ?? "").trim(),
    });
  }
  return map;
}

/** 最近5个数据日销量（产品级合计）：Map<store|item, qty> */
async function fetchSalesMap(
  db: mysql.Connection,
): Promise<{ sales: Map<string, number>; dates: string[] }> {
  const [dateRows] = await db.execute(
    `SELECT DISTINCT DATE_FORMAT(stat_date,'%Y-%m-%d') AS d FROM fact_sales_daily
     WHERE platform='walmart' ORDER BY d DESC LIMIT ${SALES_WINDOW}`,
  );
  const dates = (dateRows as Array<{ d: string }>).map((r) => r.d);
  const sales = new Map<string, number>();
  if (dates.length === 0) return { sales, dates };
  const [rows] = await db.execute(
    `SELECT store_id, item_id, SUM(COALESCE(sales_qty,0)) AS qty
     FROM fact_sales_daily
     WHERE platform='walmart' AND stat_date IN (${dates.map(() => "?").join(",")})
     GROUP BY store_id, item_id`,
    dates,
  );
  for (const r of rows as Array<{ store_id: string; item_id: string; qty: string | number }>) {
    sales.set(`${r.store_id}|${r.item_id}`, Number(r.qty ?? 0));
  }
  return { sales, dates };
}

/** 最新库存快照（产品级）：各 msku 各自最新 snapshot_date 求和 → {wfs, inbound在途} */
async function fetchStockMap(
  db: mysql.Connection,
): Promise<Map<string, { wfs: number; inbound: number }>> {
  const [rows] = await db.execute(
    `SELECT inv.store_id, inv.item_id,
            SUM(COALESCE(inv.wfs_available_stock,0)) AS wfs,
            SUM(COALESCE(inv.inbound_stock,0)) AS inbound
     FROM fact_inventory_daily inv
     JOIN (
       SELECT store_id, item_id, msku, MAX(snapshot_date) AS d
       FROM fact_inventory_daily WHERE platform='walmart'
       GROUP BY store_id, item_id, msku
     ) li ON li.store_id = inv.store_id AND li.item_id = inv.item_id
         AND li.msku = inv.msku AND inv.snapshot_date = li.d
     WHERE inv.platform='walmart'
     GROUP BY inv.store_id, inv.item_id`,
  );
  const map = new Map<string, { wfs: number; inbound: number }>();
  for (const r of rows as Array<{ store_id: string; item_id: string; wfs: string | number; inbound: string | number }>) {
    map.set(`${r.store_id}|${r.item_id}`, { wfs: Number(r.wfs ?? 0), inbound: Number(r.inbound ?? 0) });
  }
  return map;
}

/**
 * 最近8个日志日 × 产品 → 行存在矩阵 + 实质动作矩阵。
 * 判定"有行才算"：断货产品该日无行，没行≠没填（想填都没地方），窗口自动跳过。
 */
async function fetchActionMatrix(
  db: mysql.Connection,
): Promise<{ dates: string[]; exist: Map<string, Set<string>>; act: Map<string, Set<string>> }> {
  const [dateRows] = await db.execute(
    `SELECT DISTINCT DATE_FORMAT(log_date,'%Y-%m-%d') AS d FROM biz_product_operation_log
     WHERE platform='walmart' ORDER BY d DESC LIMIT ${LOG_WINDOW}`,
  );
  const dates = (dateRows as Array<{ d: string }>).map((r) => r.d); // 降序：dates[0]=最新
  const exist = new Map<string, Set<string>>();
  const act = new Map<string, Set<string>>();
  if (dates.length === 0) return { dates, exist, act };
  const [rows] = await db.execute(
    `SELECT DATE_FORMAT(log_date,'%Y-%m-%d') AS d, store_id, item_id,
            MAX(CASE WHEN TRIM(COALESCE(log_content,'')) <> ''
                      AND TRIM(log_content) NOT IN (${NO_ACTION_TEXTS.map(() => "?").join(",")})
                     THEN 1 ELSE 0 END) AS has_action
     FROM biz_product_operation_log
     WHERE platform='walmart' AND log_date IN (${dates.map(() => "?").join(",")})
     GROUP BY d, store_id, item_id`,
    [...NO_ACTION_TEXTS, ...dates],
  );
  for (const r of rows as Array<{ d: string; store_id: string; item_id: string; has_action: number }>) {
    const key = `${r.store_id}|${r.item_id}`;
    if (!exist.has(key)) exist.set(key, new Set());
    exist.get(key)!.add(r.d);
    if (Number(r.has_action) === 1) {
      if (!act.has(key)) act.set(key, new Set());
      act.get(key)!.add(r.d);
    }
  }
  return { dates, exist, act };
}

async function main(): Promise<void> {
  const send = process.argv.includes("--send");
  const testSend = process.argv.includes("--test-send")
    || (process.env.BUSINESS_REPORT_FORCE_TEST ?? "").trim() === "1";
  // EVENT 写入仅在真实发送时进行；测试群试发零副作用
  const writeEvent = send && !testSend;
  const today = localDate();

  const db = await getDb();
  const verdicts: Verdict[] = [];
  const stockouts: Stockout[] = [];
  let resolvedCount = 0;
  const resolvedItems: string[] = [];
  const skippedOpen: string[] = [];
  let insufficientRows = 0;
  try {
    const products = await fetchProducts(db);
    const { sales, dates: salesDates } = await fetchSalesMap(db);
    const stockMap = await fetchStockMap(db);
    const { dates: logDates, exist, act } = await fetchActionMatrix(db);
    if (logDates.length < R1_DAYS) {
      console.log(`SKIP 日志日不足${R1_DAYS}天（实际${logDates.length}），不判定`);
      console.log("SUMMARY_JSON=" + JSON.stringify({ today, status: "success", action: "not_enough_log_dates" }));
      return;
    }

    // 1) 解除：无动作类=出现实质动作日；断货类=WFS恢复>0 或 产品移出在营（归档/停用）
    const [openRows] = await db.execute(
      `SELECT id, store_id, item_id, rule_hit, DATE_FORMAT(alert_date,'%Y-%m-%d') AS alert_date
       FROM event_ops_inaction_alert WHERE platform='walmart' AND resolved_at IS NULL`,
    );
    const stillOpen = new Set<string>(); // key|类别 维度挂起（无动作与断货互不抑制）
    for (const o of openRows as Array<{ id: number; store_id: string; item_id: string; rule_hit: string; alert_date: string }>) {
      const key = `${o.store_id}|${o.item_id}`;
      const isStockout = String(o.rule_hit).startsWith("断货");
      let resolveNote: string | null = null;
      if (isStockout) {
        const wfs = stockMap.get(key)?.wfs ?? 0;
        if (wfs > 0) resolveNote = `WFS库存恢复=${wfs}`;
        else if (!products.has(key)) resolveNote = "产品已移出在营（归档/停用）";
      } else {
        const actionDates = [...(act.get(key) ?? [])].filter((d) => d >= o.alert_date).sort();
        if (actionDates.length > 0) resolveNote = `实质动作日：${actionDates.join(",")}`;
      }
      if (resolveNote) {
        resolvedCount++;
        resolvedItems.push(`${o.item_id}（${resolveNote}）`);
        if (writeEvent) {
          await db.execute(
            `UPDATE event_ops_inaction_alert SET resolved_at = NOW(),
                    resolved_note = ? WHERE id = ? AND resolved_at IS NULL`,
            [resolveNote, o.id],
          );
        }
      } else {
        stillOpen.add(`${key}|${isStockout ? "stockout" : "inaction"}`);
      }
    }

    // 2) 判定
    for (const [key, p] of products) {
      const qty5 = sales.get(key) ?? 0;
      const stock = stockMap.get(key) ?? { wfs: 0, inbound: 0 };

      // —— 断货分支（零库存不进无动作监控，运营日志不体现）——
      if (stock.wfs <= 0) {
        let rule: string | null = null;
        if (p.lifecycle === CLEARANCE_LIFECYCLE) rule = RULE_STOCKOUT_ARCHIVE;
        else if (qty5 > 0) rule = RULE_STOCKOUT_REPLENISH;
        if (rule) {
          if (stillOpen.has(`${key}|stockout`)) { skippedOpen.push(p.itemId); continue; }
          stockouts.push({ p, rule, sales5d: qty5, inbound: stock.inbound });
        }
        continue; // 沉睡产品（零库存+无销量+非清货期）不打扰
      }

      // —— 无动作监控（有库存产品）——
      const noSalePool = qty5 === 0 && !EXEMPT_LIFECYCLES.has(p.lifecycle);
      const dPool = p.profitLevel.startsWith("D级");
      if (!noSalePool && !dPool) continue;
      const poolReason = noSalePool && dPool ? `${SALES_WINDOW}天不出单+D级`
        : (noSalePool ? `${SALES_WINDOW}天不出单` : "D级");

      const existSet = exist.get(key) ?? new Set<string>();
      const presentDates = logDates.filter((d) => existSet.has(d)); // 降序，只保留有行日
      if (presentDates.length < R1_DAYS) { insufficientRows++; continue; } // 行数不足暂不评

      const actSet = act.get(key) ?? new Set<string>();
      const detail = presentDates.map((d) => ({ d, act: (actSet.has(d) ? 1 : 0) as 0 | 1 }));
      // v1.4：仅保留连续判定——最近5个有行日全无动作才通报（任一天有动作即豁免）
      if (!detail.slice(0, R1_DAYS).every((x) => x.act === 0)) continue;
      if (stillOpen.has(`${key}|inaction`)) { skippedOpen.push(p.itemId); continue; }

      const lastAct = [...actSet].sort().pop() ?? null;
      verdicts.push({
        p, poolReason,
        ruleHit: `连续${R1_DAYS}个日志日无动作`,
        detail, lastActionDate: lastAct,
      });
    }

    // 3) 写 alert（append；uk 防同日重复；测试模式不写）
    if (writeEvent) {
      for (const v of verdicts) {
        await db.execute(
          `INSERT IGNORE INTO event_ops_inaction_alert
             (platform, store_id, item_id, mskus, owner, pool_reason, rule_hit, window_detail, alert_date)
           VALUES ('walmart', ?, ?, ?, ?, ?, ?, ?, ?)`,
          [v.p.storeId, v.p.itemId, v.p.mskus, v.p.owner, v.poolReason, v.ruleHit,
           JSON.stringify(v.detail), today],
        );
      }
      for (const s of stockouts) {
        await db.execute(
          `INSERT IGNORE INTO event_ops_inaction_alert
             (platform, store_id, item_id, mskus, owner, pool_reason, rule_hit, window_detail, alert_date)
           VALUES ('walmart', ?, ?, ?, ?, ?, ?, ?, ?)`,
          [s.p.storeId, s.p.itemId, s.p.mskus, s.p.owner,
           s.rule === RULE_STOCKOUT_ARCHIVE ? "断货+清货期" : "断货+近期有销量",
           s.rule,
           JSON.stringify({ sales_5d: s.sales5d, wfs: 0, inbound: s.inbound, lifecycle: s.p.lifecycle }),
           today],
        );
      }
    }

    // 4) 通报文案（按负责人分组，负责人内按店铺维度分组——2026-07-20 需求方指令）
    const storeNames = await fetchStoreNames(db);
    const storeOf = (p: Product): string => storeNames.get(p.storeId) ?? p.storeId;
    const byOwner = new Map<string, Verdict[]>();
    for (const v of verdicts) {
      if (!byOwner.has(v.p.owner)) byOwner.set(v.p.owner, []);
      byOwner.get(v.p.owner)!.push(v);
    }
    // 2026-07-20 需求方指令：①断货提醒取消发送（断货检测/事件写入/自动解除逻辑全部保留，
    // 仅不再打扰运营）②无动作通报与"📉 低利润产品提醒"统一为卡片格式（负责人分区，店铺列于行内）
    const toCardItems = (list: Verdict[]) => list.map((v) => ({
      owner: v.p.owner === "(未分配)" ? "" : v.p.owner,
      storeName: storeOf(v.p),
      itemId: v.p.itemId,
      mskus: v.p.mskus || "-",
      poolReason: v.poolReason,
      ruleHit: v.ruleHit,
      lastActionDate: v.lastActionDate,
    }));
    const vOwners = [...byOwner.keys()].sort((a, b) => a.localeCompare(b, "zh"));
    const ownersSendable = vOwners.filter((o) => o !== "(未分配)");
    let planned = 0;

    // 5) 发送（卡片：总览进测试群留档；各负责人个人卡片私信，镜像自动抄送测试群）
    const results: SendResult[] = [];
    const warnings: string[] = [];
    if (verdicts.length > 0) {
      const testTarget: NotifyTarget = { type: "chat", label: "测试群(总览留档)", id: getTestChatId() };
      const ov = buildOpsInactionCard(today, toCardItems(verdicts),
        { resolvedToday: resolvedCount, titleNote: "（总览留档）", testPrefix: testSend });
      planned += 1;
      results.push(await sendCardToTarget(testTarget, ov.card, ov.fallbackText, send));
      if (testSend) {
        for (const o of ownersSendable) {
          const b = buildOpsInactionCard(today, toCardItems(byOwner.get(o)!),
            { titleNote: `（原目标:私聊 ${o}）`, testPrefix: true });
          planned += 1;
          results.push(await sendCardToTarget(
            { type: "chat", label: `测试群(预览-${o})`, id: getTestChatId() }, b.card, b.fallbackText, send));
        }
      } else {
        const { targets, warnings: w } = await resolveActiveMembers(ownersSendable);
        warnings.push(...w);
        const targetMap = new Map(targets.map((t) => [t.label, t]));
        for (const o of ownersSendable) {
          const t = targetMap.get(o);
          if (!t) { warnings.push(`私聊跳过：${o}（不在在册花名册或缺open_id）`); continue; }
          const b = buildOpsInactionCard(today, toCardItems(byOwner.get(o)!), {});
          planned += 1;
          results.push(await sendCardToTarget(t, b.card, b.fallbackText, send));
        }
      }
    }

    const sendFailed = results.filter((r) => !r.ok).length;
    console.log("SUMMARY_JSON=" + JSON.stringify({
      today, dryRun: !send, mode: testSend ? "test" : "prod",
      salesWindow: salesDates, logWindow: logDates,
      poolAlerts: verdicts.length,
      stockoutReplenish: stockouts.filter((s) => s.rule === RULE_STOCKOUT_REPLENISH).length,
      stockoutArchive: stockouts.filter((s) => s.rule === RULE_STOCKOUT_ARCHIVE).length,
      insufficientRows,
      byOwner: [...byOwner.keys()].sort().map((o) => ({ owner: o, n: byOwner.get(o)!.length })),
      skippedOpenCount: skippedOpen.length, resolvedCount, resolvedItems: resolvedItems.slice(0, 20),
      planned, sendSuccess: results.filter((r) => r.ok).length, sendFailed,
      warnings, status: sendFailed === 0 ? "success" : "partial_failed",
    }));
    process.exit(sendFailed === 0 ? 0 : 1);
  } finally {
    await db.end().catch(() => undefined);
  }
}

main().catch((e) => {
  console.error("FATAL:", e instanceof Error ? e.message : String(e));
  process.exit(1);
});
