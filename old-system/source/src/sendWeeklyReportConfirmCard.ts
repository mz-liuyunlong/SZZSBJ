/**
 * sendWeeklyReportConfirmCard.ts — 周四会议确认交互卡片（2026-07-14 新增；2026-07-23 批4改造）
 *
 * cron：周四 16:00 私聊 WEEKLY_CONFIRM_RECIPIENT（默认林翔）。
 * 卡片三按钮（由 /api/feishu-card-callback 处理；2026-07-23 起两条链路均登记后定时生成）：
 *   周五开会 → 登记，周四19:30数据收口后自动生成（窗口=上周三~本周二）并推送
 *   周六开会 → 登记，周五19:30数据收口后自动生成（窗口=上周四~本周三）并推送
 *   本周不开会 → 跳过
 *
 * 用法：
 *   npx ts-node src/sendWeeklyReportConfirmCard.ts             # dry-run（打印卡片JSON，零发送）
 *   npx ts-node src/sendWeeklyReportConfirmCard.ts --send      # 真实发送给指定负责人
 *   附加 --test-send：发到测试群 FEISHU_NOTIFY_TEST_CHAT_ID，按钮带 test=1（点击不触发生成）
 *   附加 --remind：提醒模式（cron 每30分钟跑：`*[/]30 * * * 4,5`）——仅在提醒窗口内
 *     （周四16:30~21:00、周五09:30~19:00）且本周尚未确认（无登记文件及.done）时，
 *     重发一张带⏰前缀的确认卡；已确认/窗口外静默退出（exit 0）。
 */

import "dotenv/config";
import * as fs from "fs";
import {
  getNotifyTenantToken,
  getTestChatId,
  mirrorToTestEnabled,
  resolveActiveMembers,
  sendWithRetry,
} from "./feishuNotify";

const axios = require("axios/dist/node/axios.cjs") as typeof import("axios").default;

const RECIPIENT = (process.env.WEEKLY_CONFIRM_RECIPIENT ?? "林翔").trim();
// 2026-07-23 批4：兜底确认人——周四19:00仍未确认时，提醒升级为 主确认人+兜底人 同发；三人任一确认均有效
const BACKUPS = (process.env.WEEKLY_CONFIRM_BACKUPS ?? "陈佳聪,江梓博")
  .split(",").map((s) => s.trim()).filter(Boolean);

function iso(d: Date): string {
  const p = (x: number) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** 本ISO周的周二/周三（周四20:00运行：周二=今天-2，周三=今天-1；用通用公式防手动补跑偏移） */
function thisWeekDates(): { tue: string; wed: string; week: string } {
  const now = new Date();
  const dow = now.getDay() === 0 ? 7 : now.getDay(); // 1=周一...7=周日
  const tue = new Date(now); tue.setDate(now.getDate() - (dow - 2));
  const wed = new Date(tue); wed.setDate(tue.getDate() + 1);
  // ISO周号：以周二所在周计
  const t = new Date(tue); t.setDate(t.getDate() + 3 - ((t.getDay() + 6) % 7));
  const firstThu = new Date(t.getFullYear(), 0, 4);
  firstThu.setDate(firstThu.getDate() + 3 - ((firstThu.getDay() + 6) % 7));
  const week = 1 + Math.round((t.getTime() - firstThu.getTime()) / (7 * 86400000));
  return { tue: iso(tue), wed: iso(wed), week: `${t.getFullYear()}-W${String(week).padStart(2, "0")}` };
}

function buildCard(week: string, tue: string, wed: string, test: boolean, remind = false): Record<string, unknown> {
  const v = (choice: string, winEnd: string) => ({
    biz: "weekly_report_confirm", choice, week, winEnd, ...(test ? { test: 1 } : {}),
  });
  const tag = (remind ? "⏰提醒｜" : "") + (test ? "【测试】" : "");
  return {
    config: { wide_screen_mode: true },
    header: {
      template: remind ? "orange" : "blue",
      title: { tag: "plain_text", content: `${tag}经营周报会议确认 ${week}` },
    },
    elements: [
      {
        tag: "div",
        text: {
          tag: "lark_md",
          content:
            (remind ? `**本周会议安排尚未确认**，请点击下方按钮确认：\n` : `本周经营周报数据窗口已就绪，请确认会议安排：\n`) +
            `**周五开会**：窗口 上周三 ~ ${tue}（周二），周四19:30数据收口后自动生成并推送\n` +
            `**周六开会**：窗口 上周四 ~ ${wed}（周三），周五19:30数据收口后自动生成并推送\n` +
            `**不开会**：本周跳过（两周一会时选这个）` +
            (test ? "\n\n*测试卡片：点击按钮只验证回调链路，不会真实生成*" : ""),
        },
      },
      {
        tag: "action",
        actions: [
          { tag: "button", text: { tag: "plain_text", content: "周五开会，生成周报" },
            type: "primary", value: v("friday", tue) },
          { tag: "button", text: { tag: "plain_text", content: "周六开会，周五生成" },
            type: "default", value: v("saturday", wed) },
          { tag: "button", text: { tag: "plain_text", content: "本周不开会" },
            type: "default", value: v("skip", tue) },
        ],
      },
    ],
  };
}

async function postCard(token: string, receiveIdType: "open_id" | "chat_id", id: string,
                        card: Record<string, unknown>): Promise<void> {
  const r = await sendWithRetry(`card->${receiveIdType}`, async () => {
    const resp = await axios.post(
      `https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=${receiveIdType}`,
      { receive_id: id, msg_type: "interactive", content: JSON.stringify(card) },
      { headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, timeout: 15000 },
    );
    const data = resp.data as { code?: number; msg?: string };
    if (data.code !== 0) throw new Error(`飞书返回 code=${data.code} msg=${data.msg}`);
  });
  if (!r.ok) throw new Error(r.error ?? "卡片发送失败");
}

// ── 2026-07-23 批4：提醒模式门禁 ─────────────────────────────────────────────
const STATE_DIR = process.env.WEEKLY_REPORT_STATE_DIR ?? "/opt/lingxing-auto/state";

/** 本周是否已确认（存在登记文件或其 .done 消费产物） */
function weekConfirmed(week: string): boolean {
  const base = `weekly_confirm_${week.replace(/[^\w-]/g, "_")}.json`;
  try {
    return fs.readdirSync(STATE_DIR).some((f) => f === base || f.startsWith(`${base}.done`));
  } catch {
    return false; // 状态目录不存在=从未登记
  }
}

/** 提醒窗口：周四16:30~21:00、周五09:30~19:00（服务器 Asia/Shanghai） */
function inRemindWindow(now: Date): boolean {
  const dow = now.getDay();
  const hm = now.getHours() * 60 + now.getMinutes();
  if (dow === 4) return hm >= 16 * 60 + 30 && hm <= 21 * 60;
  if (dow === 5) return hm >= 9 * 60 + 30 && hm <= 19 * 60;
  return false;
}

/** 升级判定：周四19:00起（含）及整个周五窗口，提醒扩大到 主确认人+兜底人 */
function isEscalated(now: Date): boolean {
  const dow = now.getDay();
  const hm = now.getHours() * 60 + now.getMinutes();
  return (dow === 4 && hm >= 19 * 60) || dow === 5;
}

async function main(): Promise<void> {
  const a = process.argv.slice(2);
  const send = a.includes("--send");
  const testSend = a.includes("--test-send");
  const remind = a.includes("--remind");
  const { tue, wed, week } = thisWeekDates();

  // 提醒模式门禁：窗口外或已确认 → 静默退出（exit 0，cron 每30分钟跑不产生噪音）
  if (remind) {
    const now = new Date();
    if (!inRemindWindow(now)) {
      console.log(`REMIND_SKIP week=${week} 不在提醒窗口（周四16:30~21:00/周五09:30~19:00）`);
      return;
    }
    if (weekConfirmed(week)) {
      console.log(`REMIND_SKIP week=${week} 本周已确认，无需提醒`);
      return;
    }
    // 升级：周四19:00起未确认 → 主确认人+兜底人 同发；三人任一确认即停（兜底防漏）
    const escalated = isEscalated(now);
    const names = escalated ? [RECIPIENT, ...BACKUPS] : [RECIPIENT];
    console.log(`REMIND_FIRE week=${week} 未确认且在窗口内，发送提醒卡（escalated=${escalated ? 1 : 0}，接收=${names.join("/")}）`);
    const remindCard = buildCard(week, tue, wed, testSend, true);
    if (!send) {
      console.log(`[dry-run] remind 接收人=${testSend ? "测试群" : names.join("/")}`);
      console.log("SUMMARY_JSON=" + JSON.stringify({ week, remind: 1, escalated: escalated ? 1 : 0, recipients: names, dryRun: true, sent: 0, status: "success" }));
      return;
    }
    const tokenR = await getNotifyTenantToken();
    if (testSend) {
      await postCard(tokenR, "chat_id", getTestChatId(), remindCard);
      console.log("SUMMARY_JSON=" + JSON.stringify({ week, mode: "test", remind: 1, escalated: escalated ? 1 : 0, sent: 1, status: "success" }));
      return;
    }
    const { targets: rTargets, warnings: rWarnings } = await resolveActiveMembers(names);
    if (!rTargets.length) {
      console.error(`提醒接收人均无法解析: ${rWarnings.join("; ")}`);
      process.exit(1);
    }
    let sentN = 0;
    for (const t of rTargets) {
      try { await postCard(tokenR, "open_id", t.id, remindCard); sentN++; }
      catch (e) { console.error(`[提醒] 发送给 ${t.label} 失败:`, e instanceof Error ? e.message : String(e)); }
    }
    let mirroredR = 0;
    if (mirrorToTestEnabled() && getTestChatId()) {
      try { await postCard(tokenR, "chat_id", getTestChatId(), buildCard(week, tue, wed, true, true)); mirroredR = 1; }
      catch (e) { console.error("[镜像] 测试群副本失败(忽略):", e instanceof Error ? e.message : String(e)); }
    }
    if (rWarnings.length) console.warn(`[提醒] 解析警告: ${rWarnings.join("; ")}`);
    console.log("SUMMARY_JSON=" + JSON.stringify({
      week, mode: "prod", remind: 1, escalated: escalated ? 1 : 0,
      recipients: rTargets.map((t) => t.label), sent: sentN, mirrored: mirroredR, status: sentN > 0 ? "success" : "failed",
    }));
    if (sentN === 0) process.exit(1);
    return;
  }

  const card = buildCard(week, tue, wed, testSend, remind);

  if (!send) {
    console.log(`[dry-run] week=${week} tue=${tue} wed=${wed} remind=${remind ? 1 : 0} 接收人=${testSend ? "测试群" : RECIPIENT}`);
    console.log(JSON.stringify(card, null, 1));
    console.log("SUMMARY_JSON=" + JSON.stringify({ week, tue, wed, remind: remind ? 1 : 0, dryRun: true, sent: 0, status: "success" }));
    return;
  }
  const token = await getNotifyTenantToken();
  if (testSend) {
    await postCard(token, "chat_id", getTestChatId(), card);
    console.log("SUMMARY_JSON=" + JSON.stringify({ week, mode: "test", remind: remind ? 1 : 0, sent: 1, status: "success" }));
    return;
  }
  const { targets, warnings } = await resolveActiveMembers([RECIPIENT]);
  if (!targets[0]) {
    console.error(`接收人 ${RECIPIENT} 不在在册花名册或缺 open_id: ${warnings.join("; ")}`);
    process.exit(1);
  }
  await postCard(token, "open_id", targets[0].id, card);
  // 监督镜像（2026-07-16）：生产卡片抄送测试群一份测试态副本（按钮带test=1，点击不触发生成）
  let mirrored = 0;
  if (mirrorToTestEnabled() && getTestChatId()) {
    try {
      await postCard(token, "chat_id", getTestChatId(), buildCard(week, tue, wed, true, remind));
      mirrored = 1;
    } catch (e) {
      console.error("[镜像] 测试群副本失败(忽略不影响主发送):", e instanceof Error ? e.message : String(e));
    }
  }
  console.log("SUMMARY_JSON=" + JSON.stringify({ week, mode: "prod", recipient: RECIPIENT, remind: remind ? 1 : 0, sent: 1, mirrored, status: "success" }));
}

main().catch((e) => {
  console.error("FATAL:", e instanceof Error ? e.message : String(e));
  process.exit(1);
});
