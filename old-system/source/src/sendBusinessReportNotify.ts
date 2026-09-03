/**
 * sendBusinessReportNotify.ts — AI经营分析周报提醒（双通道，2026-07-14 新增）
 *
 * 通道：
 *   群通道：BUSINESS_REPORT_CHAT_ID → 公司整体（本周销售/毛利 + 本月累计 + 报告链接）
 *   私聊通道：summary.json 中每位负责人（排除"(未分配)"）→ 各自摘要 + 个人页链接
 *   "(未分配)"的摘要并入群消息（需求方定稿 2026-07-13）
 *
 * 用法：
 *   npx ts-node src/sendBusinessReportNotify.ts --report-id 1            # dry-run（默认，零发送）
 *   npx ts-node src/sendBusinessReportNotify.ts --report-id 1 --send    # 真实发送
 *   npx ts-node src/sendBusinessReportNotify.ts --latest --send         # cron用：24h内最新成功且未发送的weekly
 *   npx ts-node src/sendBusinessReportNotify.ts --latest --kind monthly --send  # 月报cron（4号09:00）
 *   附加 --test-send：全部消息只发测试群 FEISHU_NOTIFY_TEST_CHAT_ID（标题带【测试】）
 *   附加 --force：忽略"已发送过"防重（notify_json 非空时默认拒发）
 *
 * 幂等：发送成功后写 ai_business_report.notify_json（AI层自有记录）；已有值则拒绝重发。
 */

import "dotenv/config";
import * as fs from "fs";
import * as path from "path";
import * as mysql from "mysql2/promise";
import {
  NotifyTarget,
  SendResult,
  getNotifyTenantToken,
  getTestChatId,
  resolveActiveMembers,
  sendTextToTarget,
} from "./feishuNotify";

interface SummaryOwner {
  owner: string; page: string; open_issues: number;
  sales: number; qty: number; profit: number; ad: number; items: number;
}
interface ReportSummary {
  period_key: string; win_start: string; win_end: string;
  scope?: string; // "all" | "partial"（v1.1：partial=指定负责人报告，只私聊不发群）
  report_kind?: string; // "monthly" 时文案用月报（v1.3）
  plan_month?: string;
  mtd: { start: string; end: string; sales: number; profit: number };
  company_week: { sales: number; profit: number };
  owners: SummaryOwner[];
  generated_at: string;
}

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host:     process.env.DB_HOST     ?? "127.0.0.1",
    port:     Number(process.env.DB_PORT ?? 3306),
    user:     process.env.DB_USER     ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME     ?? "walmart_ai_data",
  });
}

function fmt(n: number): string {
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function parseArgs(): { reportId: number | null; latest: boolean; kind: string; send: boolean; testSend: boolean; force: boolean } {
  const a = process.argv.slice(2);
  const idIdx = a.indexOf("--report-id");
  const reportId = idIdx >= 0 ? Number(a[idIdx + 1]) : null;
  const latest = a.includes("--latest");
  const kindIdx = a.indexOf("--kind");
  const kind = kindIdx >= 0 ? String(a[kindIdx + 1] ?? "") : "weekly";
  if (kind !== "weekly" && kind !== "monthly") {
    console.error("--kind 仅支持 weekly|monthly");
    process.exit(1);
  }
  const send = a.includes("--send");
  const testSend = a.includes("--test-send");
  const force = a.includes("--force");
  if (latest === (reportId !== null)) {
    console.error("用法: --report-id <id> 或 --latest（二选一） [--send] [--test-send] [--force]");
    process.exit(1);
  }
  if (reportId !== null && (!Number.isInteger(reportId) || reportId <= 0)) {
    console.error("--report-id 非法");
    process.exit(1);
  }
  return { reportId, latest, kind, send, testSend, force };
}

/** cron 用：取 24h 内最新 success 且未发送过的指定类型报告 id；无则退出（防止误发旧报告） */
async function resolveLatestReportId(kind: string): Promise<number> {
  const db = await getDb();
  try {
    const [rows] = await db.execute(
      "SELECT id FROM ai_business_report WHERE report_type = ? AND status='success' " +
      "AND notify_json IS NULL AND generated_at >= NOW() - INTERVAL 24 HOUR " +
      "ORDER BY generated_at DESC, id DESC LIMIT 1",
      [kind],
    );
    const r = (rows as Array<{ id: number }>)[0];
    if (!r) {
      console.error(`24小时内没有可发送的 ${kind} 成功报告（或均已发送过），退出`);
      process.exit(1);
    }
    return r.id;
  } finally { await db.end().catch(() => undefined); }
}

async function main(): Promise<void> {
  const args = parseArgs();
  const { send, force } = args;
  // 测试纪律总开关：BUSINESS_REPORT_FORCE_TEST=1 时所有推送强制进测试群（观察期用，稳定后删键切生产）
  const forceTest = (process.env.BUSINESS_REPORT_FORCE_TEST ?? "").trim() === "1";
  const testSend = args.testSend || forceTest;
  if (forceTest) console.log("[notify] BUSINESS_REPORT_FORCE_TEST=1 生效：本次推送全部进测试群");
  const reportId = args.latest ? await resolveLatestReportId(args.kind) : (args.reportId as number);
  const baseUrl = (process.env.BUSINESS_REPORT_BASE_URL ?? "").replace(/\/$/, "");
  if (!baseUrl) { console.error("缺少 BUSINESS_REPORT_BASE_URL"); process.exit(1); }

  const db = await getDb();
  let report: { period_key: string; out_dir: string; status: string; notify_json: unknown };
  try {
    const [rows] = await db.execute(
      "SELECT period_key, out_dir, status, notify_json FROM ai_business_report WHERE id = ?",
      [reportId],
    );
    const r = (rows as Array<typeof report>)[0];
    if (!r) { console.error(`报告 id=${reportId} 不存在`); process.exit(1); }
    report = r;
  } finally { await db.end().catch(() => undefined); }

  if (report.status !== "success") {
    console.error(`报告状态=${report.status}，仅 success 可发提醒`);
    process.exit(1);
  }
  if (report.notify_json && !force) {
    console.error("该报告已有发送记录（notify_json 非空），拒绝重发；如确需补发加 --force");
    process.exit(1);
  }

  const summaryPath = path.join(report.out_dir, "summary.json");
  if (!fs.existsSync(summaryPath)) { console.error(`缺少 ${summaryPath}`); process.exit(1); }
  const s = JSON.parse(fs.readFileSync(summaryPath, "utf8")) as ReportSummary;

  const link = (file: string) => `${baseUrl}/api/ai-business/reports/${reportId}/html/${encodeURIComponent(file)}`;
  const testTag = testSend ? "【测试】" : "";
  const isMonthly = s.report_kind === "monthly";
  const kindLabel = isMonthly ? "月报" : "周报";
  const planTip = isMonthly && s.plan_month
    ? `\n📝 请在 ${s.plan_month}-05 ~ 10 期间到运营日志完成问题产品的月度规划（逾期通报并计入绩效）`
    : "";
  const partial = s.scope === "partial"; // 指定负责人报告：只私聊，不发群
  const unassigned = s.owners.find((o) => o.owner === "(未分配)");
  const dmOwners = s.owners.filter((o) => o.owner !== "(未分配)");
  if (partial && dmOwners.length === 0) {
    console.error("partial 报告无可私聊负责人（仅含未分配），无事可发");
    process.exit(1);
  }

  // ── 群消息（公司整体） ──────────────────────────────────────────────
  const groupText = [
    `${testTag}【AI经营${kindLabel}】${s.period_key}（${s.win_start} ~ ${s.win_end}）已生成`,
    `${isMonthly ? "本月" : "本周"}公司整体：销售额 $${fmt(s.company_week.sales)} ｜ 毛利 $${fmt(s.company_week.profit)}`,
    isMonthly ? "" : `本月累计（${s.mtd.start} ~ ${s.mtd.end}）：销售额 $${fmt(s.mtd.sales)} ｜ 毛利 $${fmt(s.mtd.profit)}`,
    unassigned
      ? `⚠️ 未分配负责人产品：本周销售 $${fmt(unassigned.sales)}（${unassigned.items} 个Item，问题产品 ${unassigned.open_issues} 个），请尽快补录负责人`
      : "",
    `完整报告：${link("index.html")}`,
    `目标与完成率看板：${baseUrl}/admin/#/business-analysis`,
  ].filter(Boolean).join("\n");

  // ── 私聊消息（每人） ────────────────────────────────────────────────
  const dmText = (o: SummaryOwner) => [
    `${testTag}【你的经营${kindLabel}】${s.period_key}（${s.win_start} ~ ${s.win_end}）`,
    `${isMonthly ? "本月" : "本周"}：销售额 $${fmt(o.sales)} ｜ 销量 ${Math.round(o.qty)} ｜ 毛利 $${fmt(o.profit)} ｜ 广告费 $${fmt(o.ad)}`,
    `产品数 ${o.items} ｜ 问题产品 ${o.open_issues} 个${o.open_issues > 0 ? "（请优先处理）" : ""}`,
    `你的明细页：${link(o.page)}${planTip}`,
  ].join("\n");

  const token = await getNotifyTenantToken();
  const results: SendResult[] = [];
  const warnings: string[] = [];

  if (testSend) {
    // 测试模式：全部并入测试群，逐条标注原目标
    const testTarget: NotifyTarget = { type: "chat", label: "测试群", id: getTestChatId() };
    if (!partial) {
      results.push(await sendTextToTarget(token, testTarget, `[原目标:业务群]\n${groupText}`, send));
    }
    for (const o of dmOwners) {
      results.push(await sendTextToTarget(token, testTarget, `[原目标:私聊 ${o.owner}]\n${dmText(o)}`, send));
    }
  } else {
    if (!partial) {
      const chatId = (process.env.BUSINESS_REPORT_CHAT_ID ?? "").trim();
      if (!chatId) { console.error("缺少 BUSINESS_REPORT_CHAT_ID（业务群ID）"); process.exit(1); }
      results.push(await sendTextToTarget(token, { type: "chat", label: "经营周报群", id: chatId }, groupText, send));
    }
    const { targets, warnings: w } = await resolveActiveMembers(dmOwners.map((o) => o.owner));
    warnings.push(...w);
    for (const o of dmOwners) {
      const t = targets.find((x) => x.label === o.owner);
      if (!t) { warnings.push(`私聊跳过：${o.owner}（不在在册花名册或缺 open_id）`); continue; }
      results.push(await sendTextToTarget(token, t, dmText(o), send));
    }
  }

  const sendSuccess = results.filter((r) => r.ok).length;
  const sendFailed = results.filter((r) => !r.ok).length;
  const notifyRecord = {
    sentAt: new Date().toISOString(),
    mode: testSend ? "test" : "prod",
    dryRun: !send,
    sendSuccess, sendFailed,
    warnings,
    detail: results.map((r) => ({ label: r.label, type: r.type, ok: r.ok, retryCount: r.retryCount, ambiguousDelivery: r.ambiguousDelivery })),
  };

  if (send) {
    const db2 = await getDb();
    try {
      await db2.execute(
        "UPDATE ai_business_report SET notify_json = ? WHERE id = ?",
        [JSON.stringify(notifyRecord), reportId],
      );
    } finally { await db2.end().catch(() => undefined); }
  }

  console.log("SUMMARY_JSON=" + JSON.stringify({
    reportId, periodKey: s.period_key, mode: notifyRecord.mode, dryRun: !send,
    scope: partial ? "partial" : "all",
    groupPlanned: partial ? 0 : 1, dmPlanned: dmOwners.length, sendSuccess, sendFailed,
    warnings, status: sendFailed === 0 ? "success" : "partial_failed",
  }));
  process.exit(sendFailed === 0 ? 0 : 1);
}

main().catch((e) => {
  console.error("FATAL:", e instanceof Error ? e.message : String(e));
  process.exit(1);
});
