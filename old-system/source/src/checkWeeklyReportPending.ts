/**
 * checkWeeklyReportPending.ts — 周报排队生成检查器（2026-07-14 新增；2026-07-23 批4改造）
 *
 * cron：周四/周五 19:30（`30 19 * * 4,5`，数据链 19:10 deadline 收口后）。
 * 逻辑（2026-07-23 需求方定稿：两条链路均改为 19:30 定时生成，不再点击即生成）：
 *   周四运行 → 消费 choice=friday   登记（窗口=上周三~本周二，周二数据周四链内已收口）
 *   周五运行 → 消费 choice=saturday 登记（窗口=上周四~本周三，周三数据周五链内已收口）
 *   其余情况静默退出；生成+推送成功后把登记改名 .done 防重复。
 *
 * 用法：npx ts-node src/checkWeeklyReportPending.ts [--dry-run]
 */

import "dotenv/config";
import { execSync } from "child_process";
import * as fs from "fs";
import * as path from "path";

const STATE_DIR = process.env.WEEKLY_REPORT_STATE_DIR ?? "/opt/lingxing-auto/state";
const PROJECT_DIR = "/opt/lingxing-auto";

function isoWeekKey(d: Date): string {
  const t = new Date(d); t.setDate(t.getDate() + 3 - ((t.getDay() + 6) % 7));
  const firstThu = new Date(t.getFullYear(), 0, 4);
  firstThu.setDate(firstThu.getDate() + 3 - ((firstThu.getDay() + 6) % 7));
  const week = 1 + Math.round((t.getTime() - firstThu.getTime()) / (7 * 86400000));
  return `${t.getFullYear()}-W${String(week).padStart(2, "0")}`;
}

function main(): void {
  const dryRun = process.argv.includes("--dry-run");
  const now = new Date();
  const dow = now.getDay(); // 4=周四 5=周五（服务器 Asia/Shanghai）
  // 2026-07-23 批4：按运行日分流——周四消费 friday 登记，周五消费 saturday 登记
  const expect = dow === 4 ? "friday" : dow === 5 ? "saturday" : null;
  if (!expect) {
    console.log(`PENDING_CHECK 非周四/周五运行日（dow=${dow}），退出`);
    return;
  }
  const week = isoWeekKey(now);
  const fp = path.join(STATE_DIR, `weekly_confirm_${week.replace(/[^\w-]/g, "_")}.json`);

  if (!fs.existsSync(fp)) {
    console.log(`PENDING_CHECK week=${week} 无登记（或已消费），退出`);
    return;
  }
  const rec = JSON.parse(fs.readFileSync(fp, "utf8")) as { choice?: string; winEnd?: string };
  if (rec.choice !== expect) {
    console.log(`PENDING_CHECK week=${week} choice=${rec.choice}，今日(${expect}日程)无需处理`);
    return;
  }
  if (!rec.winEnd || !/^\d{4}-\d{2}-\d{2}$/.test(rec.winEnd)) {
    console.error(`PENDING_CHECK week=${week} winEnd 非法: ${rec.winEnd}`);
    process.exit(1);
  }
  const cmd =
    `cd ${PROJECT_DIR} && python3 scripts/generate_weekly_report.py ` +
    `--win-end ${rec.winEnd} --trigger cron ` +
    `&& npx ts-node src/sendBusinessReportNotify.ts --latest --send`;
  if (dryRun) {
    console.log(`[dry-run] 将执行: ${cmd}`);
    console.log("SUMMARY_JSON=" + JSON.stringify({ week, choice: rec.choice, winEnd: rec.winEnd, dryRun: true, status: "success" }));
    return;
  }
  console.log(`PENDING_CHECK week=${week} 执行排队生成（choice=${rec.choice}，winEnd=${rec.winEnd}）`);
  try {
    execSync(cmd, { stdio: "inherit", timeout: 30 * 60 * 1000 });
  } catch (e) {
    console.error("生成/推送失败:", e instanceof Error ? e.message : String(e));
    process.exit(1);
  }
  const done = `${fp}.done.${new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14)}`;
  fs.renameSync(fp, done);
  console.log(`SUMMARY_JSON=` + JSON.stringify({ week, choice: rec.choice, winEnd: rec.winEnd, consumed: done, status: "success" }));
}

main();
