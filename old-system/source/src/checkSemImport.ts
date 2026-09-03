/**
 * checkSemImport.ts — SEM 每日导入监控 + 账单↔日绩效哨兵（2026-08-13 需求方定稿）
 *
 * 两类告警（一个脚本，按条件发不同对象；前期通报全经测试群，一周后人工去掉 --test-group）：
 *   ① 缺数据：翁骏应每天（约 17:30）导入 SEM 两份报表——账单历史(sem_billing) + 日绩效(sem_daily)。
 *      判定 = 目标日在 raw_walmart_sem_csv 有没有「当天新导入」task（DATE(created_at)=目标日）；
 *      两份都要，缺任一即告警，并说明缺哪份。数据到齐当天自动停。
 *      目标日：CST ≥ 19:00 看「今天」，否则看「昨天」（漏了次日 09:00 继续追）。
 *      → 私信 SEM_IMPORT_AT_MISSING（默认 翁骏）。
 *   ② 哨兵（不能有偏差）：账单与日绩效是同一笔 SEM 花费的两份 Walmart 报表，必须对得上。
 *      按「对齐日」(账单 billing_from = 日绩效 stat_date) 逐日核 Σ账单DEBIT vs Σ日绩效spend，
 *      同一天两边都有数就必须相等（差 ≥ $0.01 即告警），附差异明细。
 *      → 私信 SEM_IMPORT_AT_SENTINEL（默认 翁骏,陈佳聪）。
 *
 * 2026-08-14 哨兵三处修正（需求方反馈「不指出店铺没法排查」+ 实测误报归因）：
 *   a) **按店铺×日期出明细**：告警直接点名是哪个店铺哪天差多少，运营可直接排查（原仅报日期无法定位）。
 *   b) **排除非campaign返还行**：账单含 campaign_id='NA' 的返还行（如 "Spend to get reimbursement"、
 *      AD_CREDIT），日绩效本就不含这类，纳入比对必然假警（08-11 实测 -$120.68 全部来自此类）。
 *   c) **结算滞后 LAG 3→5 天**：实证时序「花费日 +2天开票 +1天翁骏导入」，LAG=3 会撞上"票刚开出、尚未导入"
 *      的空档必然假警（CN2602 08-11 发票 -$8.84 在沃尔玛已处理、我方尚未导入即为此例）。
 *   d) **新增「账单缺该日」检测**：已过结算期(≥5天)而日绩效有花费、账单却无任何 DEBIT 行 → 判为疑漏导，
 *      通报点名店铺并指引重新导入该店该期账单历史（此前该情形被 has_b>0 条件静默跳过，真漏导也发现不了）。
 *
 * 定时：每 30 分钟跑；发送窗口 09:00-21:00 CST（窗口外静默）。
 * 通道：全程走 feishuNotify（私信按花名册解析 open_id、测试群卡片），不硬编码 open_id/chat_id。
 * 用法（通报测试铁律）：
 *   npx ts-node src/checkSemImport.ts                    # dry-run：只检测打印，零发送
 *   npx ts-node src/checkSemImport.ts --send --test-group   # 过渡：私信真人 + 测试群卡（cron 用这个）
 *   npx ts-node src/checkSemImport.ts --send             # 正式：仅私信真人（一周后人工去掉 --test-group）
 *
 * 只读：本脚本零写库（不碰任何表），纯检测 + 通报。
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { NotifyTarget, getTestChatId, getNotifyTenantToken, resolveActiveMembers, sendCardToTarget, sendTextToTarget } from "./feishuNotify";

const WINDOW_START = 9;   // CST 发送窗口起
const WINDOW_END = 21;    // CST 发送窗口止（>=21 静默）
const DUE_HOUR = 19;      // 当天 SEM 导入应完成时点（≥此点起查「今天」，否则查「昨天」）
// 哨兵只核「已结算」的近窗口日期：避开近几天开票滞后造成的假警，老差异随窗口滚动老化。
// 2026-08-14 实证的完整时序：花费日 →(+2天)→ 沃尔玛开票 →(次日)→ 翁骏导入。
//   实例：CN2602 花费日08-09→发票日08-11、08-10→08-12、08-11→08-13（金额分毫不差）。
//   故一个花费日需 3~4 天才能稳定落到我方账单表 → LAG 取 5（2开票+1导入+2缓冲），避免撞开票空档。
const SENTINEL_SETTLED_LAG = 5;   // 结算滞后：只核 今天-5 之前
const SENTINEL_WINDOW_DAYS = 14;  // 回看窗口：今天-5 起往前 14 天
const PAGE_URL = "http://42.193.254.170:3000/walmart-sem";
const MISSING_AT = (process.env.SEM_IMPORT_AT_MISSING ?? "翁骏").split(",").map((s) => s.trim()).filter(Boolean);
const SENTINEL_AT = (process.env.SEM_IMPORT_AT_SENTINEL ?? "翁骏,陈佳聪").split(",").map((s) => s.trim()).filter(Boolean);

function dbConfig(): mysql.ConnectionOptions {
  return { host: process.env.DB_HOST ?? "127.0.0.1", port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "", password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data", dateStrings: true };
}
function cstNow(): Date { return new Date(Date.now() + 8 * 3600 * 1000); }
function cstHour(): number { return cstNow().getUTCHours(); }
function cstYmd(d: Date): string { return d.toISOString().slice(0, 10); }
function todayCst(): string { return cstYmd(cstNow()); }
function yesterdayCst(): string { const d = cstNow(); d.setUTCDate(d.getUTCDate() - 1); return cstYmd(d); }

interface MissingResult { targetDate: string; missing: string[] }
/** kind: missing=已过结算期但账单该店该日无任何DEBIT行(疑漏导，需重新导入) / diff=两侧都有数但金额不符 */
interface Mismatch { date: string; storeId: string; storeName: string; billing: number; daily: number; diff: number; kind: "missing" | "diff" }
/** 账单中不参与「花费对账」的非campaign行（返还/报销类，日绩效侧本就不含） */
const NON_CAMPAIGN_IDS = ["", "NA", "N/A", "na"];

/** ① 缺数据：目标日有没有当天新导入 task（两份都要） */
async function checkMissing(db: mysql.Connection): Promise<MissingResult> {
  const targetDate = cstHour() >= DUE_HOUR ? todayCst() : yesterdayCst();
  const [rows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT csv_type, COUNT(*) AS c FROM raw_walmart_sem_csv WHERE DATE(created_at)=? GROUP BY csv_type`,
    [targetDate]);
  const seen = new Set(rows.map((r) => String(r.csv_type)));
  const missing: string[] = [];
  if (!seen.has("sem_billing")) missing.push("账单历史(sem_billing)");
  if (!seen.has("sem_daily")) missing.push("日绩效(sem_daily)");
  return { targetDate, missing };
}

/** ② 哨兵：账单DEBIT vs 日绩效spend 按【店铺×对齐日】逐日核
 *  修正(2026-08-14)：a)出店铺明细 b)排除campaign_id='NA'的返还/报销行
 *    c)LAG放宽至5天（覆盖「花费日+2天开票+1天导入」全时序）
 *    d)新增「账单缺该日」检测：已过结算期(≥LAG天)而日绩效有花费、账单却无任何DEBIT行 → 判为疑漏导，
 *      需翁骏重新导入该店该期账单（此前该情形被 has_b>0 条件静默跳过，真漏导也发现不了）。 */
async function checkSentinel(db: mysql.Connection): Promise<{ list: Mismatch[]; skipped: number }> {
  const ph = NON_CAMPAIGN_IDS.map(() => "?").join(",");
  const [rows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT t.store_id, t.d,
            ROUND(SUM(t.billing),2) AS billing, ROUND(SUM(t.daily),2) AS daily,
            SUM(t.has_b) AS has_b, SUM(t.has_d) AS has_d,
            MAX(cov.bill_max) AS bill_max,
            COALESCE(MAX(s.store_name), t.store_id) AS store_name
       FROM (
         SELECT store_id, DATE_FORMAT(billing_from,'%Y-%m-%d') AS d,
                SUM(CASE WHEN charge_type='DEBIT' THEN line_amount ELSE 0 END) AS billing, 0 AS daily,
                1 AS has_b, 0 AS has_d
           FROM fact_sem_billing_daily
          WHERE COALESCE(campaign_id,'') NOT IN (${ph})
          GROUP BY store_id, d
         UNION ALL
         SELECT store_id, DATE_FORMAT(stat_date,'%Y-%m-%d') AS d, 0, SUM(ad_spend), 0, 1
           FROM fact_ads_product_daily
          WHERE platform='walmart' AND campaign_type='sem'
          GROUP BY store_id, d
       ) t
       LEFT JOIN (SELECT store_id, MAX(billing_to) AS bill_max
                    FROM fact_sem_billing_daily GROUP BY store_id) cov ON cov.store_id = t.store_id
       LEFT JOIN dim_store s ON s.store_id = t.store_id AND s.platform='walmart'
      GROUP BY t.store_id, t.d
      HAVING has_d > 0
      ORDER BY t.d, t.store_id`, NON_CAMPAIGN_IDS);
  // 已结算窗口：[今天-LAG-WINDOW, 今天-LAG]，避开近几天开票滞后假警
  const hi = cstNow(); hi.setUTCDate(hi.getUTCDate() - SENTINEL_SETTLED_LAG);
  const lo = cstNow(); lo.setUTCDate(lo.getUTCDate() - SENTINEL_SETTLED_LAG - SENTINEL_WINDOW_DAYS);
  const cutoffHi = cstYmd(hi), cutoffLo = cstYmd(lo);
  const out: Mismatch[] = [];
  let skipped = 0;
  for (const r of rows) {
    const date = String(r.d);
    if (date > cutoffHi || date < cutoffLo) { skipped++; continue; } // 只核已结算的近窗口（LAG内的新日期不核）
    const hasB = Number(r.has_b) > 0;
    const b = Math.round((Number(r.billing) || 0) * 100) / 100;
    const dd = Math.round((Number(r.daily) || 0) * 100) / 100;
    const base = { date, storeId: String(r.store_id), storeName: String(r.store_name ?? r.store_id) };
    if (!hasB) {
      // 已过结算期（≥LAG天）却连一行DEBIT都没有，而日绩效确有花费 → 账单疑似漏导
      if (dd >= 0.01) out.push({ ...base, billing: 0, daily: dd, diff: -dd, kind: "missing" });
      continue;
    }
    const diff = Math.round((b - dd) * 100) / 100;
    if (Math.abs(diff) >= 0.01) out.push({ ...base, billing: b, daily: dd, diff, kind: "diff" });
  }
  return { list: out, skipped };
}

function buildMissingCard(m: MissingResult, test: boolean): { card: Record<string, unknown>; fb: string } {
  const content = `📥 **SEM 数据未导入**（${m.targetDate}）\n` +
    `缺少：**${m.missing.join(" + ")}**\n` +
    `请到 [SEM导入页](${PAGE_URL}) 下载并导入（账单历史 + 日绩效两份都要）。导入完成后本提醒自动停止。`;
  const card = {
    config: { wide_screen_mode: true },
    header: { template: "orange", title: { tag: "plain_text", content: `${test ? "【测试】" : ""}📥 SEM导入提醒` } },
    elements: [{ tag: "div", text: { tag: "lark_md", content } },
      { tag: "note", elements: [{ tag: "plain_text", content: "每30分钟提醒一次（21:00-次日09:00静默），导入后自动停止。" }] }],
  };
  const fb = `【SEM导入提醒】${m.targetDate} 缺少 ${m.missing.join("+")}，请尽快导入（账单+日绩效两份）。`;
  return { card, fb };
}

/** 按日期分组渲染一组明细（组内按差额绝对值降序） */
function renderByDate(items: Mismatch[], fmt: (x: Mismatch) => string): string {
  const byDate = new Map<string, Mismatch[]>();
  for (const x of items) { if (!byDate.has(x.date)) byDate.set(x.date, []); byDate.get(x.date)!.push(x); }
  const dates = [...byDate.keys()].sort().reverse();
  return dates.slice(0, 6).map((d) => {
    const g = (byDate.get(d) ?? []).sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff));
    const rows = g.slice(0, 8).map((x) => `　· ${fmt(x)}`).join("\n")
      + (g.length > 8 ? `\n　· …等共 ${g.length} 个店铺` : "");
    return `**${d}**\n${rows}`;
  }).join("\n\n") + (dates.length > 6 ? `\n\n…等共 ${dates.length} 天` : "");
}

function buildSentinelCard(list: Mismatch[], test: boolean): { card: Record<string, unknown>; fb: string } {
  // 需求方2026-08-14：必须点名店铺；且「账单缺该日(疑漏导)」与「金额不符」两类处置动作不同，分开展示
  const missing = list.filter((x) => x.kind === "missing");
  const diffs = list.filter((x) => x.kind === "diff");
  const dateCnt = new Set(list.map((x) => x.date)).size;
  const storeCnt = new Set(list.map((x) => x.storeId)).size;

  const parts: string[] = [];
  if (missing.length) {
    parts.push(`❗**账单缺该日**（已过结算期仍无发票行，**疑漏导 → 请重新导入该店该期账单历史**）\n` +
      renderByDate(missing, (x) => `**${x.storeName}**：日绩效 $${x.daily.toFixed(2)}，账单**无对应发票行**`));
  }
  if (diffs.length) {
    parts.push(`⚠️**金额不符**（两侧都有数但对不上，需人工核对是否串数/漏行）\n` +
      renderByDate(diffs, (x) => `**${x.storeName}**：账单 $${x.billing.toFixed(2)} vs 日绩效 $${x.daily.toFixed(2)}　**差 $${x.diff.toFixed(2)}**`));
  }

  const content = `⚖️ **SEM 账单↔日绩效对不上**（同一笔花费两份报表应相等）\n\n${parts.join("\n\n")}\n\n` +
    `处置：到 [SEM导入页](${PAGE_URL}) 重新导入对应店铺的**账单历史**（日期区间需覆盖上述花费日）。\n` +
    `（口径：花费日+2天开票+1天导入，故只核 ${SENTINEL_SETTLED_LAG} 天前的花费日；已排除账单返还行）`;
  const card = {
    config: { wide_screen_mode: true },
    header: { template: "red", title: { tag: "plain_text", content:
      `${test ? "【测试】" : ""}⚖️ SEM账单↔日绩效哨兵（${dateCnt}天 / ${storeCnt}个店铺）` } },
    elements: [{ tag: "div", text: { tag: "lark_md", content } }],
  };
  const top = list.slice().sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff))[0];
  const fb = `【SEM哨兵】${missing.length ? `账单缺${missing.length}条(疑漏导)；` : ""}` +
    `${diffs.length ? `金额不符${diffs.length}条；` : ""}共 ${dateCnt} 天 / ${storeCnt} 个店铺` +
    (top ? `（最大：${top.date} ${top.storeName} 差 $${top.diff.toFixed(2)}）` : "") + "，请重新导入账单或人工核对。";
  return { card, fb };
}

async function sendPrivate(atNames: string[], text: string): Promise<void> {
  const { targets, warnings } = await resolveActiveMembers(atNames);
  for (const w of warnings) console.log(`  ⚠️ ${w}`);
  const token = await getNotifyTenantToken();
  for (const t of targets) {
    const r = await sendTextToTarget(token, t, text, true);
    console.log(`  私信 ${t.label}: ${r.ok ? "✅" : "❌ " + (r.error ?? "")}`);
  }
}

async function main(): Promise<void> {
  const doSend = process.argv.includes("--send");
  const toTestGroup = process.argv.includes("--test-group");
  const fireTest = process.argv.includes("--fire-test"); // 强制发样例卡到测试群，验证飞书链路
  const h = cstHour();

  if (fireTest) {
    const db0 = await mysql.createConnection(dbConfig());
    let miss: MissingResult, mism: Mismatch[];
    try { miss = await checkMissing(db0); mism = (await checkSentinel(db0)).list; }
    finally { await db0.end().catch(() => undefined); }
    const demoMiss: MissingResult = miss.missing.length ? miss : { targetDate: miss.targetDate, missing: ["账单历史(sem_billing)", "日绩效(sem_daily)"] };
    const demoMism: Mismatch[] = mism.length ? mism : [
      { date: miss.targetDate, storeId: "DEMO002", storeName: "CN2602-添详商贸(邓添祥)", billing: 0, daily: 8.84, diff: -8.84, kind: "missing" },
      { date: miss.targetDate, storeId: "DEMO001", storeName: "CN2601-瑞盈龙盛(刘云龙）", billing: 100.0, daily: 88.88, diff: 11.12, kind: "diff" }];
    const testTarget: NotifyTarget = { type: "chat", label: "测试群", id: getTestChatId() };
    const c1 = buildMissingCard(demoMiss, true);
    const r1 = await sendCardToTarget(testTarget, c1.card, "【测试】" + c1.fb, true);
    console.log(`样例·缺数据卡 → 测试群: ${r1.ok ? "✅" : "❌ " + (r1.error ?? "")}`);
    const c2 = buildSentinelCard(demoMism, true);
    const r2 = await sendCardToTarget(testTarget, c2.card, "【测试】" + c2.fb, true);
    console.log(`样例·哨兵卡 → 测试群: ${r2.ok ? "✅" : "❌ " + (r2.error ?? "")}`);
    console.log("SUMMARY_JSON=" + JSON.stringify({ fire_test: true, missing_card: r1.ok, sentinel_card: r2.ok }));
    return;
  }

  console.log("=".repeat(64));
  console.log(`SEM导入监控+哨兵 | CST ${h}点 | ${doSend ? (toTestGroup ? "私信真人+测试群" : "仅私信真人") : "dry-run零发送"}`);
  console.log("=".repeat(64));

  const db = await mysql.createConnection(dbConfig());
  try {
    const miss = await checkMissing(db);
    const sen = await checkSentinel(db);
    const mism = sen.list;
    console.log(`缺数据：目标日=${miss.targetDate}，缺=${miss.missing.length ? miss.missing.join("+") : "无（两份齐）"}`);
    const senDates = new Set(mism.map((x) => x.date)).size;
    const senStores = new Set(mism.map((x) => x.storeId)).size;
    const nMissing = mism.filter((x) => x.kind === "missing").length;
    const nDiff = mism.filter((x) => x.kind === "diff").length;
    console.log(`哨兵：不一致 ${senDates} 天 / ${senStores} 个店铺（账单缺该日 ${nMissing} 条、金额不符 ${nDiff} 条）；窗口外未核 ${sen.skipped} 条`);
    for (const x of mism.slice(0, 15)) {
      console.log(x.kind === "missing"
        ? `   ❗${x.date}  ${x.storeName}  日绩效$${x.daily.toFixed(2)}  账单无发票行（疑漏导）`
        : `   ⚠️${x.date}  ${x.storeName}  账单$${x.billing.toFixed(2)} vs 日绩效$${x.daily.toFixed(2)}  差$${x.diff.toFixed(2)}`);
    }
    if (mism.length > 15) console.log(`   …等共 ${mism.length} 条`);

    const inWindow = h >= WINDOW_START && h < WINDOW_END;
    if (!doSend) { console.log("dry-run：不发送。"); }
    else if (!inWindow) { console.log(`当前 CST ${h}点在发送窗口(${WINDOW_START}-${WINDOW_END})外，跳过发送。`); }
    else {
      const testTarget: NotifyTarget = { type: "chat", label: "测试群", id: getTestChatId() };
      // ① 缺数据 → 私信翁骏（+测试群卡）
      if (miss.missing.length) {
        const { card, fb } = buildMissingCard(miss, true);
        await sendPrivate(MISSING_AT, fb);
        if (toTestGroup) { const r = await sendCardToTarget(testTarget, card, fb, true); console.log(`  缺数据→测试群: ${r.ok ? "✅" : "❌"}`); }
      }
      // ② 哨兵 → 私信翁骏+陈佳聪（+测试群卡）
      if (mism.length) {
        const { card, fb } = buildSentinelCard(mism, true);
        await sendPrivate(SENTINEL_AT, fb);
        if (toTestGroup) { const r = await sendCardToTarget(testTarget, card, fb, true); console.log(`  哨兵→测试群: ${r.ok ? "✅" : "❌"}`); }
      }
      if (!miss.missing.length && !mism.length) console.log("一切正常，无需通报。");
    }

    console.log("SUMMARY_JSON=" + JSON.stringify({
      cst_hour: h, target_date: miss.targetDate, missing: miss.missing,
      sentinel_mismatch_days: senDates, sentinel_mismatch_stores: senStores,
      sentinel_rows: mism.length, sentinel_missing: nMissing, sentinel_diff: nDiff,
      sentinel_out_of_window: sen.skipped,
      sent: doSend && (h >= WINDOW_START && h < WINDOW_END),
    }));
  } finally {
    await db.end().catch(() => undefined);
  }
}

main().catch((err) => { console.error("SEM导入监控失败：", err instanceof Error ? err.stack : String(err)); process.exit(1); });
