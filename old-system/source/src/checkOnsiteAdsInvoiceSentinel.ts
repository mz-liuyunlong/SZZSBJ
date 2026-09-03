/**
 * checkOnsiteAdsInvoiceSentinel.ts — Connect广告发票完整性哨兵（批2，2026-08-19）
 *
 * 背景（需求方拍板）：财务每月对账依赖发票全量入库。本哨兵每周检查发票覆盖完整性并通报，
 *   替代 2026-08-19 的手工盘点（当日全量对账详见 TASK_CHANGE_LOG）。
 *
 * 检查项（全部只读SELECT；口径起算 2026-04-01；SEM不在本哨兵——走店铺账单，checkSemImport 已覆盖）：
 *   ① 尾部缺口（核心，日期对账）：店铺最后发票账期止之后仍有非SEM日绩效花费，
 *      且缺口天数 > 该店动态阈值（历史最大账期天数+4；发票<5张的新店兜底18天）→ 疑有新账单未下载导入。
 *      阈值依据（2026-08-19 全库分布实证）：账期最长14天(CN2501/2502)、出票滞后99%≤4天。
 *   ② 中段缺口：相邻发票账期断档且窗内有非SEM花费 → 疑漏导历史账单（2026-08-19 盘点后基线=0，防回归）。
 *   ③ 待扣款清单：charge_date IS NULL 全列（信息项）；账龄>14天标红"需排查（疑支付失败）"
 *      ——阈值依据：扣款滞后分布 97分位=14天（7天会误催约24%正常等扣款的票）。
 *   ④ 金额对账+自动归因（2026-08-19 需求方追加"不一致要查出哪里的问题"）：
 *      发票TotalAdSpend↔日绩效非SEM同期合计 |差|>$0.01（排除日绩效T+2尾部滞后期），预期恒为0；
 *      出现时自动定位：发票行↔日数据campaign名匹配（2026-08-19 SV缺数归因同款方法论）——
 *      未匹配发票行合计≈差额 → 日数据缺这些campaign（附补数命令方向）；差额为负 → 日数据多计疑串店/重复。
 *   ⑤ 信息行：有非SEM投放但从未导过发票的店铺（需求方 2026-08-19 拍板暂不处理，仅提示不告警）。
 *   ⑥ 逐日覆盖核验（"7月专项复核"常驻化）：起算日至该店最后发票账期止之间，
 *      任何有非SEM花费但不落入任何发票期间的日子 → 逐日列出（预期恒为0行，出现即红色告警）。
 *
 * 通报（需求方定稿）：对象=翁骏(私信)+测试群；周一09:00全量通报（无问题也发绿色"全部闭合"卡）；
 *   周二09:00复查（--recheck：仅在仍有问题时追报，干净则静默）。
 *
 * 用法：
 *   npx ts-node src/checkOnsiteAdsInvoiceSentinel.ts                 # dry-run 预览，不发送
 *   npx ts-node src/checkOnsiteAdsInvoiceSentinel.ts --send          # 发送（周一cron）
 *   npx ts-node src/checkOnsiteAdsInvoiceSentinel.ts --send --recheck # 复查追报（周二cron，干净则不发）
 *   npx ts-node src/checkOnsiteAdsInvoiceSentinel.ts --send --no-user # 只发测试群不私信（联调用）
 *
 * 纪律：只读；连接与飞书凭证全读环境变量；日志不输出任何ID/token；不写任何表、不动定时任务。
 */
import "dotenv/config";
import * as mysql from "mysql2/promise";
import { NotifyTarget, getTestChatId, resolveActiveMembers, sendCardToTarget } from "./feishuNotify";

const START_DATE = "2026-04-01";      // 对账起算日（此前历史一刀切，需求方拍板）
const TAIL_BUFFER_DAYS = 4;           // 尾部阈值缓冲=出票滞后P99
const TAIL_FALLBACK_DAYS = 18;        // 新店（发票<5张）尾部兜底阈值
const NEW_STORE_MIN_INVOICES = 5;
const PENDING_RED_DAYS = 14;          // 待扣款标红阈值（扣款滞后P97）
const AMOUNT_TOL = 0.01;              // 金额对账容差
const PERF_TAIL_LAG_DAYS = 2;         // 日绩效T+2到账，金额对账排除尾部
const NOTIFY_USERS = ["翁骏"];        // 私信对象（花名册解析，禁止硬编码ID）
const IMPORT_PAGE = "http://42.193.254.170/admin/#/ads/connect-invoice";
const BILL_PAGE = "http://42.193.254.170/admin/#/ads/bill-fee";
const NON_SEM = "(p.campaign_type IS NULL OR p.campaign_type <> 'sem')";

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
}
const n2 = (v: unknown): number => { const n = Number(v); return Number.isFinite(n) ? n : 0; };
const money = (v: number): string => v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

interface TailGap { store: string; lastEnd: string; lastSpend: string; gapDays: number; thr: number; uncovered: number }
interface MidGap { store: string; from: string; to: string; days: number; spend: number }
interface Pending { store: string; invoice: string; period: string; invDate: string; amount: number; age: number }
interface AmountDiff { store: string; storeId: string; invoice: string; period: string; ps: string; pe: string; spend: number; perf: number; diff: number; diag: string }
interface DayGap { store: string; day: string; spend: number }

async function main(): Promise<void> {
  const doSend = process.argv.includes("--send");
  const recheck = process.argv.includes("--recheck");
  const noUser = process.argv.includes("--no-user");
  const db = await getDb();
  try {
    // ── 基础：店铺聚合（动态阈值底表）──
    const [storeRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT h.store_id, COALESCE(NULLIF(MAX(h.store_name),''), h.store_id) AS store_name,
              COUNT(*) AS invoices, MAX(DATEDIFF(h.period_end,h.period_start)+1) AS max_len,
              DATE_FORMAT(MAX(h.period_end),'%Y-%m-%d') AS last_end
         FROM fact_onsite_ads_invoice_head h GROUP BY h.store_id`);

    // ── ① 尾部缺口 ──
    const tails: TailGap[] = [];
    for (const s of storeRows) {
      const [t] = await db.query<mysql.RowDataPacket[]>(
        `SELECT DATE_FORMAT(MAX(p.stat_date),'%Y-%m-%d') AS last_spend,
                ROUND(SUM(CASE WHEN p.stat_date > ? THEN p.ad_spend ELSE 0 END),2) AS uncovered
           FROM fact_ads_product_daily p
          WHERE p.store_id = ? AND ${NON_SEM} AND p.ad_spend > 0`,
        [String(s.last_end), String(s.store_id)]);
      const lastSpend = String(t[0]?.last_spend ?? "");
      const uncovered = n2(t[0]?.uncovered);
      if (!lastSpend || uncovered <= 0) continue;
      const gapDays = Math.round((Date.parse(lastSpend) - Date.parse(String(s.last_end))) / 86400000);
      const thr = Number(s.invoices) >= NEW_STORE_MIN_INVOICES ? Number(s.max_len) + TAIL_BUFFER_DAYS : TAIL_FALLBACK_DAYS;
      if (gapDays > thr) {
        tails.push({ store: String(s.store_name), lastEnd: String(s.last_end), lastSpend, gapDays, thr, uncovered });
      }
    }

    // ── ② 中段缺口 ──
    // 与 2026-08-19 手工盘点探针同款SQL（HAVING过滤别名为MySQL已实证可用的写法）
    const [midRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COALESCE((SELECT NULLIF(MAX(x.store_name),'') FROM fact_onsite_ads_invoice_head x
                         WHERE x.store_id = t.store_id), t.store_id) AS store_name,
              DATE_FORMAT(DATE_ADD(t.prev_end, INTERVAL 1 DAY),'%Y-%m-%d') AS gap_from,
              DATE_FORMAT(DATE_SUB(t.period_start, INTERVAL 1 DAY),'%Y-%m-%d') AS gap_to,
              DATEDIFF(t.period_start, t.prev_end) - 1 AS gap_days,
              (SELECT ROUND(SUM(p.ad_spend),2) FROM fact_ads_product_daily p
                WHERE p.store_id = t.store_id AND ${NON_SEM}
                  AND p.stat_date BETWEEN DATE_ADD(t.prev_end, INTERVAL 1 DAY) AND DATE_SUB(t.period_start, INTERVAL 1 DAY)) AS gap_spend
         FROM (SELECT store_id, period_start, LAG(period_end) OVER w AS prev_end
                 FROM fact_onsite_ads_invoice_head
               WINDOW w AS (PARTITION BY store_id ORDER BY period_start, period_end)) t
        WHERE t.prev_end IS NOT NULL AND t.period_start > DATE_ADD(t.prev_end, INTERVAL 1 DAY)
       HAVING IFNULL(gap_spend, 0) > 0
        ORDER BY store_name, gap_from`);
    const mids: MidGap[] = midRows.map((r) => ({
      store: String(r.store_name), from: String(r.gap_from), to: String(r.gap_to),
      days: n2(r.gap_days), spend: n2(r.gap_spend),
    }));

    // ── ③ 待扣款 ──
    const [pendRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COALESCE(NULLIF(h.store_name,''), h.store_id) AS store_name, h.invoice_number,
              CONCAT(DATE_FORMAT(h.period_start,'%m-%d'),'~',DATE_FORMAT(h.period_end,'%m-%d')) AS period,
              DATE_FORMAT(h.invoice_date,'%Y-%m-%d') AS inv_date, h.total_charged,
              DATEDIFF(CURDATE(), h.invoice_date) AS age_days
         FROM fact_onsite_ads_invoice_head h
        WHERE h.charge_date IS NULL
        ORDER BY age_days DESC, store_name`);
    const pendings: Pending[] = pendRows.map((r) => ({
      store: String(r.store_name), invoice: String(r.invoice_number), period: String(r.period),
      invDate: String(r.inv_date ?? "—"), amount: n2(r.total_charged), age: n2(r.age_days),
    }));
    const pendingRed = pendings.filter((x) => x.age > PENDING_RED_DAYS);

    // ── ④ 金额对账附录（预期0行；排除日绩效T+2尾部）──
    const [amtRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COALESCE(NULLIF(h.store_name,''), h.store_id) AS store_name, h.store_id, h.invoice_number,
              CONCAT(DATE_FORMAT(h.period_start,'%m-%d'),'~',DATE_FORMAT(h.period_end,'%m-%d')) AS period,
              DATE_FORMAT(h.period_start,'%Y-%m-%d') AS ps, DATE_FORMAT(h.period_end,'%Y-%m-%d') AS pe,
              h.total_ad_spend,
              (SELECT ROUND(SUM(p.ad_spend),2) FROM fact_ads_product_daily p
                WHERE p.store_id = h.store_id AND ${NON_SEM}
                  AND p.stat_date BETWEEN h.period_start AND h.period_end) AS perf_sum
         FROM fact_onsite_ads_invoice_head h
        WHERE h.period_start >= ?
          AND h.period_end <= (SELECT DATE_SUB(MAX(p2.stat_date), INTERVAL ${PERF_TAIL_LAG_DAYS} DAY)
                                 FROM fact_ads_product_daily p2
                                WHERE (p2.campaign_type IS NULL OR p2.campaign_type <> 'sem'))
       HAVING ABS(h.total_ad_spend - IFNULL(perf_sum, 0)) > ${AMOUNT_TOL}
        ORDER BY store_name`, [START_DATE]);
    const amts: AmountDiff[] = amtRows.map((r) => ({
      store: String(r.store_name), storeId: String(r.store_id), invoice: String(r.invoice_number),
      period: String(r.period), ps: String(r.ps), pe: String(r.pe),
      spend: n2(r.total_ad_spend), perf: n2(r.perf_sum),
      diff: Math.round((n2(r.total_ad_spend) - n2(r.perf_sum)) * 100) / 100, diag: "",
    }));

    // ── ④b 自动归因（每轮最多诊断5张，控制查询量）：发票行↔日数据campaign名匹配 ──
    for (const a of amts.slice(0, 5)) {
      const [um] = await db.query<mysql.RowDataPacket[]>(
        `SELECT l.campaign_name, ROUND(l.amount,2) AS amount
           FROM fact_onsite_ads_invoice_line l
          WHERE l.store_id = ? AND l.invoice_number = ?
            AND NOT EXISTS (SELECT 1 FROM fact_ads_product_daily p
                             WHERE p.store_id = l.store_id AND p.campaign_name = l.campaign_name
                               AND ${NON_SEM} AND p.stat_date BETWEEN ? AND ?)
          ORDER BY l.amount DESC`, [a.storeId, a.invoice, a.ps, a.pe]);
      const umSum = Math.round(um.reduce((s, r) => s + n2(r.amount), 0) * 100) / 100;
      const top = um.slice(0, 3).map((r) => `${String(r.campaign_name)}($${money(n2(r.amount))})`).join("、");
      if (a.diff > 0 && um.length && Math.abs(umSum - a.diff) <= 0.05) {
        a.diag = `定位：日粒度数据缺这${um.length}个campaign（合计$${money(umSum)}≈差额）：${top}${um.length > 3 ? " 等" : ""} → 疑SV/新campaign日数据未同步，按期间回补（syncSbSvAdsDaily 或 syncLingxingDailyToDb --date）`;
      } else if (a.diff < 0) {
        a.diag = `定位：日粒度花费**大于**发票 → 疑该店该期间日数据串店混入或重复导入，需核查日数据来源批次`;
      } else if (um.length) {
        a.diag = `部分定位：发票有${um.length}个campaign在日数据无匹配（合计$${money(umSum)}，与差额不完全吻合）：${top} → 需人工核对（campaign改名/跨店嫌疑）`;
      } else {
        a.diag = `发票行全部能在日数据匹配到campaign但金额仍不平 → 疑个别天日数据不全，按期间逐日重跑同步后复核`;
      }
    }
    if (amts.length > 5) amts.slice(5).forEach((a) => { a.diag = "（本轮归因名额已满，下轮自动继续）"; });

    // ── ⑥ 逐日覆盖核验（7月专项常驻化；只查起算日~该店最后发票账期止，预期0行）──
    const [dayRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COALESCE(NULLIF(MAX(p.store_name),''), p.store_id) AS store_name,
              DATE_FORMAT(p.stat_date,'%Y-%m-%d') AS d, ROUND(SUM(p.ad_spend),2) AS spend
         FROM fact_ads_product_daily p
        WHERE ${NON_SEM} AND p.ad_spend > 0 AND p.stat_date >= ?
          AND p.stat_date <= (SELECT MAX(h.period_end) FROM fact_onsite_ads_invoice_head h WHERE h.store_id = p.store_id)
          AND NOT EXISTS (SELECT 1 FROM fact_onsite_ads_invoice_head h2
                           WHERE h2.store_id = p.store_id AND p.stat_date BETWEEN h2.period_start AND h2.period_end)
        GROUP BY p.store_id, p.stat_date ORDER BY store_name, d`, [START_DATE]);
    const dayGaps: DayGap[] = dayRows.map((r) => ({ store: String(r.store_name), day: String(r.d), spend: n2(r.spend) }));

    // ── ⑤ 信息行：有投放但从未导发票的店铺 ──
    const [noInvRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COALESCE(NULLIF(MAX(p.store_name),''), p.store_id) AS store_name, ROUND(SUM(p.ad_spend),2) AS spend
         FROM fact_ads_product_daily p
        WHERE ${NON_SEM} AND p.ad_spend > 0 AND p.stat_date >= ?
          AND p.store_id NOT IN (SELECT DISTINCT store_id FROM fact_onsite_ads_invoice_head)
        GROUP BY p.store_id ORDER BY spend DESC`, [START_DATE]);

    const hasIssue = tails.length > 0 || mids.length > 0 || pendingRed.length > 0 || amts.length > 0 || dayGaps.length > 0;

    // ── 组卡 ──
    const parts: string[] = [];
    if (tails.length) {
      parts.push(`❗**新账单未导入**（按店铺，请到 Walmart Connect 后台下载"缺失起"之后的全部账单，[导入入口](${IMPORT_PAGE})）\n` +
        tails.sort((a, b) => b.uncovered - a.uncovered).map((x) =>
          `　· **${x.store}**：缺 ${x.lastEnd} 之后（投放至 ${x.lastSpend}，断档${x.gapDays}天>阈值${x.thr}天），未覆盖广告费 **$${money(x.uncovered)}**`).join("\n"));
    }
    if (mids.length) {
      parts.push(`❗**历史账单缺段**（该期间有投放但无发票，请按段补导）\n` +
        mids.map((x) => `　· **${x.store}**：${x.from} ~ ${x.to}（${x.days}天，$${money(x.spend)}）`).join("\n"));
    }
    if (pendings.length) {
      parts.push(`⏳**待扣款发票**（信息项；扣款后请重新下载同发票号Receipt重导，自动补齐扣款信息）\n` +
        pendings.map((x) =>
          `　· ${x.age > PENDING_RED_DAYS ? "🔴" : "•"} ${x.store}：#${x.invoice}（${x.period}，$${money(x.amount)}，账龄${x.age}天${x.age > PENDING_RED_DAYS ? "，**超14天需排查，疑支付失败**" : ""}）`).join("\n"));
    }
    if (dayGaps.length) {
      parts.push(`🚨**逐日覆盖异常**（该日有投放但不在任何发票期间内，预期恒为0，疑发票期间错漏）\n` +
        dayGaps.slice(0, 12).map((x) => `　· ${x.store}：${x.day}（$${money(x.spend)}）`).join("\n") +
        (dayGaps.length > 12 ? `\n　· …等共 ${dayGaps.length} 天` : ""));
    }
    if (amts.length) {
      parts.push(`🚨**金额不平+自动归因**（发票↔日粒度对账，预期恒为0）\n` +
        amts.map((x) => `　· ${x.store} #${x.invoice}（${x.period}）：发票 $${money(x.spend)} vs 日粒度 $${money(x.perf)}，差 $${money(x.diff)}\n　　↳ ${x.diag}`).join("\n"));
    }
    if (noInvRows.length) {
      parts.push(`ℹ️ 从未导入发票的投放店铺（暂不处理，需求方已知）：` +
        noInvRows.map((r) => `${String(r.store_name)}($${money(n2(r.spend))})`).join("、"));
    }
    if (!hasIssue && !parts.length) parts.push("✅ 全部闭合：发票覆盖无缺口（逐日核验0异常）、无待扣款超期、发票↔日粒度金额全平。");
    else if (!hasIssue) parts.unshift("✅ 无需处理项（以下为信息项）。");

    const content = parts.join("\n\n") +
      `\n\n口径：对账起算${START_DATE}；尾部阈值=该店最大账期+${TAIL_BUFFER_DAYS}天（新店${TAIL_FALLBACK_DAYS}天）；` +
      `待扣款超${PENDING_RED_DAYS}天标红；SEM走店铺账单口径（SEM哨兵另管）。发票级明细见[广告账单扣费](${BILL_PAGE})。`;
    const header = hasIssue ? (mids.length || amts.length ? "red" : "orange") : "green";
    const title = `📄 广告发票完整性哨兵${recheck ? "·复查" : ""} ${new Date().toISOString().slice(0, 10)}` +
      (hasIssue ? `（缺口${tails.length + mids.length}项/待排查${pendingRed.length}张）` : "（全部闭合）");
    const card = {
      config: { wide_screen_mode: true },
      header: { template: header, title: { tag: "plain_text", content: title } },
      elements: [{ tag: "div", text: { tag: "lark_md", content } }],
    };
    const fb = `【发票哨兵${recheck ? "复查" : ""}】` + (hasIssue
      ? `新账单未导${tails.length}店、历史缺段${mids.length}处、待扣款${pendings.length}张(超期${pendingRed.length})、金额异常${amts.length}条`
      : "全部闭合") + `。详情见卡片。`;

    console.log(`检查完成：尾部${tails.length} 中段${mids.length} 待扣款${pendings.length}(红${pendingRed.length}) 逐日覆盖异常${dayGaps.length} 金额异常${amts.length} 未导店铺${noInvRows.length} → ${hasIssue ? "有问题" : "干净"}`);

    // ── 发送 ──
    let sentOk = false;
    if (recheck && !hasIssue) {
      console.log("复查模式且无问题 → 静默不发。");
    } else {
      const targets: NotifyTarget[] = [{ type: "chat", label: "测试群", id: getTestChatId() }];
      if (!noUser) {
        const { targets: users, warnings } = await resolveActiveMembers(NOTIFY_USERS);
        for (const w of warnings) console.log(`  ⚠️ ${w}`);
        targets.push(...users);
      }
      for (const t of targets) {
        const r = await sendCardToTarget(t, card, fb, doSend);
        if (doSend) console.log(`  → ${t.label}: ${r.ok ? "✅" : "❌ " + (r.error ?? "")}`);
        sentOk = sentOk || r.ok;
      }
    }
    console.log("SUMMARY_JSON=" + JSON.stringify({
      mode: recheck ? "recheck" : "weekly", send: doSend, has_issue: hasIssue,
      tail_gaps: tails.length, mid_gaps: mids.length, pending: pendings.length,
      pending_red: pendingRed.length, day_gaps: dayGaps.length, amount_diffs: amts.length, no_invoice_stores: noInvRows.length,
      sent_ok: sentOk,
    }));
  } finally {
    await db.end().catch(() => undefined);
  }
}

main().catch((e) => { console.error("FATAL", e); process.exit(1); });
