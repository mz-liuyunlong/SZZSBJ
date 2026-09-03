/**
 * attendanceLackAlert.ts — 考勤缺卡通报（EVENT，2026-07-30）
 *
 * 规则(用户拍板)：某日缺卡(上/下班/双缺)→次日09:50推个人卡(带"确认收到"按钮)+人事群日报;
 *   推送起算:满12h未确认→再发一次(--remind,21:50);满24h未确认→锁定,该缺卡按旷工(核算联动)。
 *   确认=知悉(不改结果);人事可线下补卡(系统只锁员工自助确认)。
 * 分层：读 FACT fact_attendance_daily(缺卡日)→写 EVENT event_attendance_lack_alert;发送复用 feishuNotify。
 * 用法：
 *   npx ts-node src/attendanceLackAlert.ts --push            # dry-run(零发零写),预览昨日缺卡个人卡+人事群卡
 *   npx ts-node src/attendanceLackAlert.ts --push --test     # 仅发测试群,零写库
 *   npx ts-node src/attendanceLackAlert.ts --push --send     # 真发个人+人事群 + 写库(含24h锁定)
 *   npx ts-node src/attendanceLackAlert.ts --remind [--test|--send]  # 12h重发未确认
 */
import "dotenv/config";
import * as mysql from "mysql2/promise";
import { sendCardToTarget, getTestChatId, NotifyTarget } from "./feishuNotify";

const HR_CHAT_ID = (process.env.FEISHU_HR_CHAT_ID ?? "oc_149a50a2c1bf2dfc861dbf0236833aed").trim();
const PAGE_URL = "http://42.193.254.170/admin/#/attendance";

function dbConfig(): mysql.ConnectionOptions {
  return { host: process.env.DB_HOST ?? "127.0.0.1", port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "", password: process.env.DB_PASSWORD ?? "", database: process.env.DB_NAME ?? "walmart_ai_data" };
}
function yesterdayCst(): string {
  const d = new Date(Date.now() + 8 * 3600 * 1000 - 86400 * 1000);
  return d.toISOString().slice(0, 10);
}
function targetDay(): string {
  const a = process.argv.find((x) => x.startsWith("--date="));
  if (a) { const d = a.slice(7).trim(); if (/^\d{4}-\d{2}-\d{2}$/.test(d)) return d; }
  return yesterdayCst();
}
function weekdayCn(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00Z");
  return "日一二三四五六"[d.getUTCDay()];
}
interface AlertRow { id: number; stat_date: string; open_id: string; name: string; lack_type: string; }

function lackTypeOf(inRes: string, outRes: string): string {
  const i = inRes === "Lack", o = outRes === "Lack";
  return i && o ? "双缺" : i ? "上班" : o ? "下班" : "缺卡";
}
function lackDesc(t: string): string {
  return t === "上班" ? "上班卡未打" : t === "下班" ? "下班卡未打" : t === "双缺" ? "上下班均未打卡" : "缺卡";
}

// ── 个人卡(带"确认收到"回调按钮) ──────────────────────────────────────────────
function buildLackCard(a: AlertRow, test: boolean): { card: Record<string, unknown>; fb: string } {
  const dateLabel = a.stat_date + "（周" + weekdayCn(a.stat_date) + "）";
  const card = {
    config: { wide_screen_mode: true },
    header: { template: "red", title: { tag: "plain_text", content: "⚠️ 考勤缺卡提醒" } },
    elements: [
      { tag: "div", text: { tag: "lark_md", content:
        "**姓名**：" + a.name + "\n**日期**：" + dateLabel + "\n**缺卡**：<font color='red'>" + lackDesc(a.lack_type) + "</font>" } },
      { tag: "div", text: { tag: "lark_md", content:
        "⏰ 本提醒 **24 小时内**有效。请点击确认知悉；<font color='red'>**逾期未确认将无法处理，该缺卡按旷工计**</font>。" } },
      { tag: "action", actions: [
        { tag: "button", text: { tag: "plain_text", content: "✅ 确认收到" }, type: "primary",
          value: Object.assign({ biz: "lack_ack", id: a.id }, test ? { test: 1 } : {}) } ] },
      { tag: "note", elements: [{ tag: "plain_text", content: "如设备/网络异常漏打卡，请确认后线下向人事补卡。" }] },
    ],
  };
  const fb = "【考勤缺卡提醒】" + a.name + " " + dateLabel + " " + lackDesc(a.lack_type) +
    "；请在飞书卡片点『确认收到』，24小时内有效，逾期按旷工计。";
  return { card, fb };
}
// ── 人事群缺卡日报 ────────────────────────────────────────────────────────────
function buildHrCard(dateStr: string, alerts: AlertRow[], statusMap: Map<number, string>): { card: Record<string, unknown>; fb: string } {
  const lines: string[] = [];
  for (const a of alerts) {
    const st = statusMap.get(a.id) || "pending";
    const badge = st === "confirmed" ? "✅ 已确认" : st === "expired" ? "⛔ 已超时·未确认(记旷工)" : "🕓 待确认";
    lines.push("**" + a.name + "** · " + lackDesc(a.lack_type) + "　" + badge);
  }
  const card = {
    config: { wide_screen_mode: true },
    header: { template: "blue", title: { tag: "plain_text", content: "📋 考勤缺卡日报" } },
    elements: [
      { tag: "div", text: { tag: "lark_md", content: "缺卡日 **" + dateStr + "（周" + weekdayCn(dateStr) + "）** · 共 " + alerts.length + " 人" } },
      { tag: "hr" },
      { tag: "div", text: { tag: "lark_md", content: lines.join("\n") || "（无）" } },
      { tag: "note", elements: [{ tag: "plain_text", content: "状态实时更新；24h未确认者锁定为『未确认缺卡』按旷工计。人事可线下补卡。" }] },
    ],
  };
  const fb = "【考勤缺卡日报】" + dateStr + " 共" + alerts.length + "人：" + alerts.map((a) => a.name + "(" + lackDesc(a.lack_type) + ")").join("、");
  return { card, fb };
}

async function main(): Promise<void> {
  const isRemind = process.argv.includes("--remind");
  const doSend = process.argv.includes("--send");
  const testSend = process.argv.includes("--test");
  const writeState = doSend && !testSend;
  const realSend = doSend || testSend;
  const mode = isRemind ? "remind(12h重发)" : "push(次日通报)";
  console.log("=".repeat(60));
  console.log("考勤缺卡通报 | " + mode + " | " + (testSend ? "test(仅测试群,零写库)" : doSend ? "真发+写库" : "dry-run(零发零写)"));
  console.log("=".repeat(60));
  const db = await mysql.createConnection(dbConfig());
  try {
    if (isRemind) {
      // 12h重发：pending 且 push_at 在(12h前, 24h内)、未重发过
      const [rows] = await db.query<mysql.RowDataPacket[]>(
        "SELECT id, DATE_FORMAT(stat_date,'%Y-%m-%d') AS stat_date, open_id, name, lack_type FROM event_attendance_lack_alert " +
        "WHERE ack_status='pending' AND resend_at IS NULL AND push_at <= NOW()-INTERVAL 12 HOUR AND push_at > NOW()-INTERVAL 24 HOUR");
      const alerts = rows as unknown as AlertRow[];
      console.log("待12h重发: " + alerts.length + " 条");
      for (const a of alerts) {
        const { card, fb } = buildLackCard(a, testSend);
        const target: NotifyTarget = testSend ? { type: "chat", label: "测试群", id: getTestChatId() } : { type: "user", label: a.name, id: a.open_id };
        await sendCardToTarget(target, card, fb, realSend);
        if (writeState) await db.query("UPDATE event_attendance_lack_alert SET resend_at=NOW() WHERE id=?", [a.id]);
      }
      console.log(writeState ? "已重发并记录 resend_at" : "(未写库)");
      return;
    }

    // ── push ──
    // 1) 24h锁定:pending 且 push_at 超24h → expired
    if (writeState) {
      const [r] = await db.query<mysql.ResultSetHeader>(
        "UPDATE event_attendance_lack_alert SET ack_status='expired', locked_at=NOW() WHERE ack_status='pending' AND push_at <= NOW()-INTERVAL 24 HOUR");
      console.log("24h锁定(逾期→旷工): " + r.affectedRows + " 条");
    }
    // 2) 检测昨日缺卡(FACT)
    const day = targetDay();
    const [lrows] = await db.query<mysql.RowDataPacket[]>(
      "SELECT open_id, user_id, name, check_in_result, check_out_result FROM fact_attendance_daily " +
      "WHERE stat_date=? AND day_status='缺卡' AND open_id<>'' ORDER BY name", [day]);
    console.log("昨日(" + day + ")缺卡: " + lrows.length + " 人");
    // 3) 建告警(不存在才建)
    const alerts: AlertRow[] = [];
    for (const r of lrows) {
      const openId = String(r.open_id), name = String(r.name || "");
      const lt = lackTypeOf(String(r.check_in_result || ""), String(r.check_out_result || ""));
      const [ex] = await db.query<mysql.RowDataPacket[]>(
        "SELECT id FROM event_attendance_lack_alert WHERE stat_date=? AND open_id=? LIMIT 1", [day, openId]);
      let id = ex.length ? Number(ex[0].id) : 0;
      if (!ex.length) {
        if (writeState) {
          const [ins] = await db.query<mysql.ResultSetHeader>(
            "INSERT INTO event_attendance_lack_alert (stat_date, open_id, user_id, name, lack_type, ack_status, push_at) VALUES (?,?,?,?,?, 'pending', NOW())",
            [day, openId, String(r.user_id || ""), name, lt]);
          id = ins.insertId;
        }
        alerts.push({ id, stat_date: day, open_id: openId, name, lack_type: lt });
      } // 已存在的不重复推(避免重复打扰)
    }
    console.log("新增待推: " + alerts.length + " 条");
    // 4) 发个人卡
    for (const a of alerts) {
      const { card, fb } = buildLackCard(a, testSend);
      const target: NotifyTarget = testSend ? { type: "chat", label: "测试群", id: getTestChatId() } : { type: "user", label: a.name, id: a.open_id };
      await sendCardToTarget(target, card, fb, realSend);
    }
    // 5) 人事群日报(当日全部缺卡+状态)
    if (alerts.length) {
      const statusMap = new Map<number, string>(alerts.map((a) => [a.id, "pending"]));
      const { card, fb } = buildHrCard(day, alerts, statusMap);
      const hrTarget: NotifyTarget = testSend ? { type: "chat", label: "测试群", id: getTestChatId() } : { type: "chat", label: "人事群", id: HR_CHAT_ID };
      await sendCardToTarget(hrTarget, card, fb, realSend);
    } else {
      console.log("无缺卡,不发人事群日报");
    }
    console.log(writeState ? "已推送并写库" : "(dry-run/test 未写库)");
  } catch (e) {
    console.error("[错误] " + (e instanceof Error ? e.message : String(e)));
    process.exitCode = 1;
  } finally {
    await db.end().catch(() => undefined);
  }
}
if (require.main === module) main();
