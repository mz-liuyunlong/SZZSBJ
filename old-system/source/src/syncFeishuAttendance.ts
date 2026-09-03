/**
 * syncFeishuAttendance.ts — AI人力·考勤 同步（隔离新模块，2026-07-29）
 *
 * 数据源：飞书考勤 OpenAPI（均 employee_type=employee_id，user_ids 用通讯录 open_id->user_id 换出）
 *   打卡结果 POST /attendance/v1/user_tasks/query      body{user_ids,check_date_from,check_date_to,need_overtime_result}
 *   打卡流水 POST /attendance/v1/user_flows/query       body{user_ids,check_time_from,check_time_to}(Unix秒字符串)
 *   考勤审批 POST /attendance/v1/user_approvals/query    body{user_ids,check_date_from,check_date_to}
 * 口径（用户拍板）：加班=打卡超时(当天末次打卡-排班下班,公司无加班审批)；应出勤=飞书排班日(大小周由排班定)；
 *   请假/外出取 leaves/outs 的 i18n_names.ch + interval(秒)。
 * 分层：原样入 raw_feishu_attendance；派生 upsert fact_attendance_daily。前端只读 FACT。
 *
 * 用法：
 *   npx ts-node src/syncFeishuAttendance.ts                     # dry-run 当月，零写入，打印月度核算
 *   npx ts-node src/syncFeishuAttendance.ts --month=2026-07     # 指定月 dry-run
 *   npx ts-node src/syncFeishuAttendance.ts --month=2026-07 --write  # 落库(RAW+FACT)
 */
import "dotenv/config";
import * as mysql from "mysql2/promise";
import * as crypto from "crypto";
import { getTenantToken } from "./feishuNotify";

const axios = require("axios/dist/node/axios.cjs") as typeof import("axios").default;
const BASE = "https://open.feishu.cn/open-apis";
const SHIFT_OUT_FALLBACK_HHMM = "18:30"; // 仅当排班下班缺失时兜底(公司规定18:30)
const OT_GRACE_SEC = 30 * 60; // 加班宽限:仅当末次打卡晚于排班下班30分钟以上才计加班(排除正常下班卡)

function dbConfig(): mysql.ConnectionOptions {
  return {
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  };
}
function chunk<T>(a: T[], n: number): T[][] { const o: T[][] = []; for (let i = 0; i < a.length; i += n) o.push(a.slice(i, i + n)); return o; }
function md5(s: string): string { return crypto.createHash("md5").update(s).digest("hex"); }
function toSec(v: unknown): number { const n = Number(v); return Number.isFinite(n) ? n : 0; }
/** unix秒 -> 上海墙钟 "YYYY-MM-DD HH:MM:SS"（用 +8h 偏移后取 UTC 串，确定性、不依赖本机时区） */
function secToCst(sec: number): string { if (!sec) return ""; return new Date((sec + 8 * 3600) * 1000).toISOString().slice(0, 19).replace("T", " "); }
function dayIntToDate(d: number | string): string { const s = String(d); return s.slice(0, 4) + "-" + s.slice(4, 6) + "-" + s.slice(6, 8); }

interface Member { openId: string; name: string; }
interface Enriched {
  userId: string; openId: string; name: string; statDate: string; dayInt: number;
  groupId: string; shiftId: string; isScheduled: number;
  checkInTime: string; checkOutTime: string; lastPunchTime: string;
  checkInResult: string; checkOutResult: string;
  lateMin: number; earlyMin: number; overtimeMin: number;
  leaveType: string; leaveHours: number; outHours: number;
  dayStatus: string;
}

async function feishuPost(token: string, path: string, query: string, body: unknown): Promise<any> {
  const resp = await axios.post(BASE + path + query, body, {
    headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" }, timeout: 60000,
  });
  const d = resp.data as { code: number; msg: string; data?: any };
  if (d.code !== 0) throw new Error(path + " code=" + d.code + " msg=" + d.msg);
  return d.data ?? {};
}
async function feishuGet(token: string, url: string): Promise<any> {
  const resp = await axios.get(url, { headers: { Authorization: "Bearer " + token }, timeout: 60000 });
  const d = resp.data as { code: number; msg: string; data?: any };
  if (d.code !== 0) throw new Error(url + " code=" + d.code + " msg=" + d.msg);
  return d.data ?? {};
}
function pickArray(data: any, keys: string[]): any[] {
  for (const k of keys) { if (Array.isArray(data?.[k])) return data[k]; }
  return [];
}

// ── 在职成员 ────────────────────────────────────────────────────────────────
async function getMembers(db: mysql.Connection): Promise<Member[]> {
  const [rows] = await db.query<mysql.RowDataPacket[]>(
    "SELECT open_id, name FROM dim_feishu_member WHERE COALESCE(employment_status,'active')='active' AND open_id IS NOT NULL AND open_id<>''",
  );
  return rows.map((r) => ({ openId: String(r.open_id), name: String(r.name ?? "") }));
}

// ── open_id -> user_id（通讯录批量，≤50/批） ─────────────────────────────────
async function resolveUserIds(token: string, members: Member[]): Promise<Map<string, Member & { userId: string }>> {
  const byUserId = new Map<string, Member & { userId: string }>();
  for (const grp of chunk(members, 50)) {
    const qs = grp.map((m) => "user_ids=" + encodeURIComponent(m.openId)).join("&");
    const data = await feishuGet(token, BASE + "/contact/v3/users/batch?user_id_type=open_id&" + qs);
    const items = pickArray(data, ["items"]);
    for (const it of items) {
      const uid = String(it?.user_id ?? "");
      const oid = String(it?.open_id ?? "");
      if (!uid) continue;
      const m = grp.find((x) => x.openId === oid);
      byUserId.set(uid, { userId: uid, openId: oid, name: (m?.name || String(it?.name ?? "")) });
    }
    await new Promise((r) => setTimeout(r, 120));
  }
  return byUserId;
}

// ── 三接口抓取 ──────────────────────────────────────────────────────────────
async function fetchTasks(token: string, userIds: string[], from: number, to: number, raws: any[]): Promise<any[]> {
  const out: any[] = [];
  for (const grp of chunk(userIds, 50)) {
    const data = await feishuPost(token, "/attendance/v1/user_tasks/query", "?employee_type=employee_id",
      { user_ids: grp, check_date_from: from, check_date_to: to, need_overtime_result: false });
    raws.push({ api_type: "user_tasks", date_from: from, date_to: to, user_count: grp.length, data });
    out.push(...pickArray(data, ["user_task_results", "task_results"]));
    await new Promise((r) => setTimeout(r, 150));
  }
  return out;
}
async function fetchFlows(token: string, userIds: string[], secFrom: number, secTo: number, raws: any[]): Promise<any[]> {
  const out: any[] = [];
  for (const grp of chunk(userIds, 40)) {
    const data = await feishuPost(token, "/attendance/v1/user_flows/query", "?employee_type=employee_id",
      { user_ids: grp, check_time_from: String(secFrom), check_time_to: String(secTo) });
    raws.push({ api_type: "user_flows", date_from: secFrom, date_to: secTo, user_count: grp.length, data });
    out.push(...pickArray(data, ["user_flow_results", "flow_results"]));
    await new Promise((r) => setTimeout(r, 150));
  }
  return out;
}
async function fetchApprovals(token: string, userIds: string[], from: number, to: number, raws: any[]): Promise<any[]> {
  const out: any[] = [];
  for (const grp of chunk(userIds, 50)) {
    const data = await feishuPost(token, "/attendance/v1/user_approvals/query", "?employee_type=employee_id",
      { user_ids: grp, check_date_from: from, check_date_to: to });
    raws.push({ api_type: "user_approvals", date_from: from, date_to: to, user_count: grp.length, data });
    out.push(...pickArray(data, ["user_approvals", "approvals"]));
    await new Promise((r) => setTimeout(r, 150));
  }
  return out;
}

// ── 派生：每人每天 ──────────────────────────────────────────────────────────
function derive(
  tasks: any[], flows: any[], approvals: any[], memberMap: Map<string, Member & { userId: string }>,
): Enriched[] {
  // 流水：每(user,day)末次打卡秒
  const lastPunch = new Map<string, number>();
  for (const f of flows) {
    const uid = String(f?.user_id ?? "");
    const t = toSec(f?.check_time);
    if (!uid || !t) continue;
    const day = secToCst(t).slice(0, 10);
    const key = uid + "|" + day;
    if (t > (lastPunch.get(key) ?? 0)) lastPunch.set(key, t);
  }
  // 审批：每(user,day) 请假/外出
  const appMap = new Map<string, { leaveType: string; leaveHours: number; outHours: number }>();
  for (const a of approvals) {
    const uid = String(a?.user_id ?? "");
    const day = dayIntToDate(a?.date ?? "");
    if (!uid || day.length !== 10) continue;
    const key = uid + "|" + day;
    const cur = appMap.get(key) ?? { leaveType: "", leaveHours: 0, outHours: 0 };
    for (const lv of (Array.isArray(a?.leaves) ? a.leaves : [])) {
      cur.leaveType = String(lv?.i18n_names?.ch ?? cur.leaveType ?? "");
      cur.leaveHours += toSec(lv?.interval) / 3600;
    }
    for (const ou of (Array.isArray(a?.outs) ? a.outs : [])) {
      cur.outHours += toSec(ou?.interval) / 3600;
    }
    appMap.set(key, cur);
  }
  // 打卡结果为主
  const result: Enriched[] = [];
  const seen = new Set<string>();
  for (const t of tasks) {
    const uid = String(t?.user_id ?? "");
    const m = memberMap.get(uid);
    const day = dayIntToDate(t?.day ?? "");
    if (!uid || day.length !== 10) continue;
    const key = uid + "|" + day;
    seen.add(key);
    const rec = Array.isArray(t?.records) && t.records.length ? t.records[0] : {};
    const inRes = String(rec?.check_in_result ?? "");
    const outRes = String(rec?.check_out_result ?? "");
    const inSec = toSec(rec?.check_in_record?.check_time);
    const outSec = toSec(rec?.check_out_record?.check_time);
    const inShift = toSec(rec?.check_in_shift_time);
    const outShift = toSec(rec?.check_out_shift_time);
    const lateMin = (inRes === "Late" || inRes === "SeriousLate") && inSec && inShift ? Math.max(0, Math.round((inSec - inShift) / 60)) : 0;
    const earlyMin = outRes === "Early" && outSec && outShift ? Math.max(0, Math.round((outShift - outSec) / 60)) : 0;
    // 排班日判定(实证):休息日 shift_id=="0" 且 check_in_result=="NoNeedCheck"(无需打卡);其余为工作日。
    // 大小周由飞书排班定,休息日不算应出勤/旷工。
    const isRest = inRes === "NoNeedCheck" || outRes === "NoNeedCheck" || String(t?.shift_id ?? "0") === "0";
    const isScheduled = isRest ? 0 : 1;
    const lastSec = lastPunch.get(key) ?? outSec;
    // 加班=末次打卡晚于排班下班超过宽限(排除正常18:30下班卡),仅排班日计
    const overtimeMin = isScheduled && outShift && lastSec > outShift + OT_GRACE_SEC ? Math.round((lastSec - outShift) / 60) : 0;
    const app = appMap.get(key) ?? { leaveType: "", leaveHours: 0, outHours: 0 };
    const hasCheck = !!inSec || !!outSec;
    let status: string;
    if (!isScheduled) status = "休息";
    else if (!hasCheck && app.leaveHours > 0) status = "请假";
    else if (!hasCheck) status = "旷工";
    else if (inRes === "Late" || inRes === "SeriousLate") status = "迟到";
    else if (outRes === "Early") status = "早退";
    else if (inRes === "Lack" || outRes === "Lack") status = "缺卡";
    else status = "正常";
    result.push({
      userId: uid, openId: m?.openId ?? "", name: m?.name ?? String(t?.employee_name ?? ""),
      statDate: day, dayInt: Number(String(t?.day ?? "0")), groupId: String(t?.group_id ?? ""), shiftId: String(t?.shift_id ?? ""),
      isScheduled: isScheduled, checkInTime: secToCst(inSec), checkOutTime: secToCst(outSec), lastPunchTime: secToCst(lastSec),
      checkInResult: inRes, checkOutResult: outRes, lateMin, earlyMin, overtimeMin,
      leaveType: app.leaveType, leaveHours: Math.round(app.leaveHours * 100) / 100, outHours: Math.round(app.outHours * 100) / 100, dayStatus: status,
    });
  }
  // 审批日但无打卡任务（整天请假可能无task）→ 补请假行
  for (const [key, app] of appMap) {
    if (seen.has(key)) continue;
    if (app.leaveHours <= 0 && app.outHours <= 0) continue;
    const [uid, day] = key.split("|");
    const m = memberMap.get(uid);
    result.push({
      userId: uid, openId: m?.openId ?? "", name: m?.name ?? "", statDate: day, dayInt: Number(day.replace(/-/g, "")),
      groupId: "", shiftId: "", isScheduled: 1, checkInTime: "", checkOutTime: "", lastPunchTime: "",
      checkInResult: "", checkOutResult: "", lateMin: 0, earlyMin: 0, overtimeMin: 0,
      leaveType: app.leaveType, leaveHours: Math.round(app.leaveHours * 100) / 100, outHours: Math.round(app.outHours * 100) / 100,
      dayStatus: app.leaveHours > 0 ? "请假" : "正常",
    });
  }

  // ── 二次校正(用户口径) ──────────────────────────────────────────────────
  // (1) 免打卡人员:整月0打卡 => 不走打卡机,应出勤=0、不算旷工。
  // (2) 公司非工作日:某排班日若打卡员工里绝大多数(>=80%)都没打卡 => 判为公司休/节假(兼容大小周),不计应出勤/旷工。
  const NONWORK_RATE = 0.2; // 打卡率低于此判为非工作日
  const punchDaysByUser = new Map<string, number>();
  for (const e of result) if (e.checkInTime || e.checkOutTime) punchDaysByUser.set(e.userId, (punchDaysByUser.get(e.userId) ?? 0) + 1);
  const clocking = new Set(Array.from(punchDaysByUser.keys()));
  const dayAgg = new Map<string, { sched: number; punch: number }>();
  for (const e of result) {
    if (!clocking.has(e.userId) || !e.isScheduled) continue;
    const a = dayAgg.get(e.statDate) ?? { sched: 0, punch: 0 };
    a.sched += 1; if (e.checkInTime || e.checkOutTime) a.punch += 1;
    dayAgg.set(e.statDate, a);
  }
  const nonWorkDays = new Set<string>();
  for (const [d, a] of dayAgg) if (a.sched >= 3 && a.punch / a.sched < NONWORK_RATE) nonWorkDays.add(d);
  for (const e of result) {
    if (!clocking.has(e.userId)) {
      // 免打卡/无打卡人员(整月0打卡)
      e.isScheduled = 0;
      e.dayStatus = e.leaveHours > 0 ? "请假" : "免打卡";
      e.overtimeMin = 0;
    } else if (e.isScheduled && nonWorkDays.has(e.statDate)) {
      // 公司非工作日
      e.isScheduled = 0;
      if (!(e.checkInTime || e.checkOutTime)) e.dayStatus = "休息";
    }
  }
  return result;
}

// ── 落库 ────────────────────────────────────────────────────────────────────
async function writeRaw(db: mysql.Connection, raws: any[]): Promise<number> {
  let n = 0;
  for (const r of raws) {
    const payload = JSON.stringify(r.data ?? {});
    const hash = md5(r.api_type + "|" + r.date_from + "|" + r.date_to + "|" + md5(payload));
    await db.query(
      "INSERT INTO raw_feishu_attendance (api_type,date_from,date_to,user_count,payload_json,raw_hash) VALUES (?,?,?,?,CAST(? AS JSON),?) ON DUPLICATE KEY UPDATE pulled_at=NOW()",
      [r.api_type, r.date_from, r.date_to, r.user_count ?? 0, payload, hash],
    );
    n++;
  }
  return n;
}
async function writeFact(db: mysql.Connection, rows: Enriched[]): Promise<number> {
  let n = 0;
  for (const e of rows) {
    await db.query(
      "INSERT INTO fact_attendance_daily (stat_date,open_id,user_id,name,group_id,shift_id,is_scheduled,check_in_time,check_out_time,last_punch_time,check_in_result,check_out_result,late_minutes,early_minutes,overtime_minutes,leave_type,leave_hours,out_hours,day_status) " +
      "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON DUPLICATE KEY UPDATE " +
      "user_id=VALUES(user_id),name=VALUES(name),group_id=VALUES(group_id),shift_id=VALUES(shift_id),is_scheduled=VALUES(is_scheduled),check_in_time=VALUES(check_in_time),check_out_time=VALUES(check_out_time),last_punch_time=VALUES(last_punch_time),check_in_result=VALUES(check_in_result),check_out_result=VALUES(check_out_result),late_minutes=VALUES(late_minutes),early_minutes=VALUES(early_minutes),overtime_minutes=VALUES(overtime_minutes),leave_type=VALUES(leave_type),leave_hours=VALUES(leave_hours),out_hours=VALUES(out_hours),day_status=VALUES(day_status)",
      [e.statDate, e.openId, e.userId, e.name, e.groupId, e.shiftId, e.isScheduled, e.checkInTime || null, e.checkOutTime || null, e.lastPunchTime || null,
       e.checkInResult, e.checkOutResult, e.lateMin, e.earlyMin, e.overtimeMin, e.leaveType, e.leaveHours, e.outHours, e.dayStatus],
    );
    n++;
  }
  return n;
}

// ── 月度核算汇总（dry-run 打印用） ──────────────────────────────────────────
function summarize(rows: Enriched[]): void {
  const byName = new Map<string, Enriched[]>();
  for (const e of rows) { if (!byName.has(e.name)) byName.set(e.name, []); byName.get(e.name)!.push(e); }
  console.log("\n姓名        应出勤 实出勤 迟到 早退 缺卡 旷工 请假h 加班h 出勤率");
  console.log("-".repeat(72));
  const names = Array.from(byName.keys()).sort();
  for (const name of names) {
    const days = byName.get(name)!;
    const sched = days.filter((d) => d.isScheduled).length;
    const present = days.filter((d) => d.isScheduled && (d.checkInTime || d.checkOutTime)).length; // 实出勤=排班日有打卡(休息日来打卡不计)
    const late = days.filter((d) => d.dayStatus === "迟到").length;
    const early = days.filter((d) => d.dayStatus === "早退").length;
    const lack = days.filter((d) => d.dayStatus === "缺卡").length;
    const absent = days.filter((d) => d.dayStatus === "旷工").length;
    const leaveH = days.reduce((s, d) => s + d.leaveHours, 0);
    const otH = days.reduce((s, d) => s + d.overtimeMin, 0) / 60;
    const rate = sched ? Math.round((present / sched) * 1000) / 10 : 0;
    console.log(
      (name + "          ").slice(0, 10) + " " +
      String(sched).padStart(4) + String(present).padStart(6) + String(late).padStart(5) + String(early).padStart(5) +
      String(lack).padStart(5) + String(absent).padStart(5) + leaveH.toFixed(1).padStart(6) + otH.toFixed(1).padStart(6) + (rate + "%").padStart(7),
    );
  }
  console.log("-".repeat(72));
  console.log("合计人数=" + names.length + " 记录日=" + rows.length);
}

// ── 主 ──────────────────────────────────────────────────────────────────────
interface MonthSpec { from: number; to: number; secFrom: number; secTo: number; label: string; }
function specOf(y: number, m: number): MonthSpec {
  const lastDay = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return {
    from: y * 10000 + m * 100 + 1, to: y * 10000 + m * 100 + lastDay,
    secFrom: Math.floor(Date.UTC(y, m - 1, 1, -8, 0, 0) / 1000),
    secTo: Math.floor(Date.UTC(y, m - 1, lastDay, 15, 59, 59) / 1000),
    label: y + "-" + String(m).padStart(2, "0"),
  };
}
// 要同步的月份：--month=YYYY-MM 指定单月；--daily 同步(上月+当月,覆盖跨月补卡/审批)；默认当月。
function monthsToRun(): MonthSpec[] {
  const arg = process.argv.find((a) => a.startsWith("--month="));
  const now = new Date(Date.now() + 8 * 3600 * 1000);
  const cy = now.getUTCFullYear(), cm = now.getUTCMonth() + 1;
  if (arg) { const p = arg.split("=")[1].split("-"); return [specOf(Number(p[0]), Number(p[1]))]; }
  if (process.argv.includes("--daily")) {
    const py = cm === 1 ? cy - 1 : cy, pm = cm === 1 ? 12 : cm - 1;
    return [specOf(py, pm), specOf(cy, cm)];
  }
  return [specOf(cy, cm)];
}
async function runMonth(db: mysql.Connection, token: string, memberMap: Map<string, Member & { userId: string }>, s: MonthSpec, doWrite: boolean): Promise<void> {
  const userIds = Array.from(memberMap.keys());
  const raws: any[] = [];
  const tasks = await fetchTasks(token, userIds, s.from, s.to, raws);
  const flows = await fetchFlows(token, userIds, s.secFrom, s.secTo, raws);
  const approvals = await fetchApprovals(token, userIds, s.from, s.to, raws);
  console.log("\n[" + s.label + "] 打卡结果=" + tasks.length + " 打卡流水=" + flows.length + " 审批=" + approvals.length);
  const rows = derive(tasks, flows, approvals, memberMap);
  console.log("[" + s.label + "] 派生考勤日行=" + rows.length);
  summarize(rows);
  if (doWrite) {
    const rn = await writeRaw(db, raws);
    const fn = await writeFact(db, rows);
    console.log("[" + s.label + "] 已落库: RAW " + rn + " 批, FACT " + fn + " 行");
  }
}

async function main(): Promise<void> {
  const doWrite = process.argv.includes("--write");
  const specs = monthsToRun();
  console.log("=".repeat(60));
  console.log("AI人力·考勤同步 | 月份=" + specs.map((s) => s.label).join(",") + " | 模式=" + (doWrite ? "落库(RAW+FACT)" : "dry-run(零写入)"));
  console.log("=".repeat(60));
  const db = await mysql.createConnection(dbConfig());
  try {
    const token = await getTenantToken();
    const members = await getMembers(db);
    console.log("在职成员: " + members.length);
    const memberMap = await resolveUserIds(token, members);
    console.log("换出 user_id: " + memberMap.size);
    for (const s of specs) await runMonth(db, token, memberMap, s, doWrite);
    if (!doWrite) console.log("\n(dry-run 未写库；加 --write 落库)");
  } catch (e) {
    console.error("[错误] " + (e instanceof Error ? e.message : String(e)));
    process.exitCode = 1;
  } finally {
    await db.end().catch(() => undefined);
  }
}
if (require.main === module) main();
