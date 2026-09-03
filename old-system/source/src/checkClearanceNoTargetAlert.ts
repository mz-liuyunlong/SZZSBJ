/**
 * checkClearanceNoTargetAlert.ts — 清货「无目标待特批」自动发现（2026-08-04，M5c，命门）
 *
 * cron：每日（建议 09:33 清货审批卡之后）。规则：
 *   - 扫描 生命周期=清货期（manual_lifecycle_stage 优先，回退 business_state.lifecycle_stage）、在营、
 *     且当月 biz_monthly_plan 无有效清货目标（indicator=清货 且 target 非空）的产品。
 *   - DM 清货审批人（CLEARANCE_APPROVER，默认林翔）名单，提示到「目标管理/清货中心」设定清货目标。
 *   - 不落库、只通知（幂等：每天扫当日现状，已设目标者次日自动移出名单）。
 *
 * 用法：
 *   npx ts-node src/checkClearanceNoTargetAlert.ts                # dry-run（只打印，零发送）
 *   npx ts-node src/checkClearanceNoTargetAlert.ts --send         # 真实私聊审批人
 *   npx ts-node src/checkClearanceNoTargetAlert.ts --test-send --send  # 发测试群（标注原目标）
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import {
  NotifyTarget, getNotifyTenantToken, getTestChatId, resolveActiveMembers, sendTextToTarget,
} from "./feishuNotify";

const APPROVER = (process.env.CLEARANCE_APPROVER ?? "林翔").trim();

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
}
function chinaMonth(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit" })
    .format(new Date()).slice(0, 7);
}
function chinaDay(): number {
  return Number(new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", day: "2-digit" }).format(new Date()));
}
const ALERT_START_DAY = 8; // 每月 8 号起才发（7 号 23:59 填报截止；与每日扣分同步）

interface Row { store_id: string; item_id: string; owner: string; mskus: string; store_name: string; }

async function fetchNoTarget(db: mysql.Connection, planMonth: string): Promise<Row[]> {
  const [rows] = await db.execute(
    `SELECT d.store_id, d.item_id, d.owner_raw AS owner,
            COALESCE(d.mskus,'') AS mskus, COALESCE(NULLIF(ds.store_name,''), d.store_id) AS store_name
     FROM (
       SELECT store_id, item_id,
              MAX(COALESCE(NULLIF(owner,''),'')) AS owner_raw,
              SUBSTRING(GROUP_CONCAT(DISTINCT NULLIF(msku,'') ORDER BY msku SEPARATOR '/'),1,120) AS mskus,
              MAX(NULLIF(manual_lifecycle_stage,'')) AS manual_lc
       FROM dim_product
       WHERE platform='walmart' AND COALESCE(NULLIF(product_management_status,''),'active') NOT IN ('inactive','archived')
       GROUP BY store_id, item_id
     ) d
     LEFT JOIN (
       SELECT store_id, item_id, MIN(lifecycle_stage) AS ls FROM dim_product_business_state
       WHERE platform='walmart' AND stat_date=(SELECT MAX(stat_date) FROM dim_product_business_state)
       GROUP BY store_id, item_id
     ) st ON st.store_id=d.store_id AND st.item_id=d.item_id
     LEFT JOIN dim_store ds ON ds.platform='walmart' AND ds.store_id=d.store_id
     LEFT JOIN biz_monthly_plan p
       ON p.plan_month=? AND p.platform='walmart' AND p.store_id=d.store_id AND p.item_id=d.item_id
      AND ((p.indicator1_type='清货' AND p.indicator1_target IS NOT NULL)
           OR (p.indicator2_type='清货' AND p.indicator2_target IS NOT NULL))
     WHERE COALESCE(d.manual_lc, st.ls)='清货期'
       AND p.id IS NULL
     ORDER BY d.owner_raw, d.item_id`,
    [planMonth],
  );
  return (rows as Array<Record<string, unknown>>).map((r) => ({
    store_id: String(r.store_id), item_id: String(r.item_id), owner: String(r.owner ?? "") || "(未分配)",
    mskus: String(r.mskus ?? ""), store_name: String(r.store_name ?? ""),
  }));
}

async function main(): Promise<void> {
  const a = process.argv.slice(2);
  const send = a.includes("--send");
  const testSend = a.includes("--test-send") || (process.env.BUSINESS_REPORT_FORCE_TEST ?? "").trim() === "1";
  const planMonth = chinaMonth();
  const dayIdx = a.indexOf("--day");
  const day = dayIdx >= 0 ? Number(a[dayIdx + 1]) : chinaDay();
  // 每月 8 号起才发（test-send DEMO 不受限，便于随时演示）
  if (!testSend && day < ALERT_START_DAY) {
    console.log(`CLEARANCE_NOTARGET_SKIP 未到发送期（<${ALERT_START_DAY}号，当前${day}号）`);
    console.log("SUMMARY_JSON=" + JSON.stringify({ planMonth, day, skipped: `未到发送期（<${ALERT_START_DAY}号）`, count: 0, status: "success" }));
    return;
  }

  const db = await getDb();
  let list: Row[] = [];
  try { list = await fetchNoTarget(db, planMonth); }
  finally { await db.end().catch(() => undefined); }

  if (list.length === 0) {
    console.log(`CLEARANCE_NOTARGET_SKIP ${planMonth} 无「清货无目标」产品`);
    console.log("SUMMARY_JSON=" + JSON.stringify({ planMonth, count: 0, status: "success" }));
    return;
  }

  const baseUrl = (process.env.BUSINESS_REPORT_BASE_URL ?? "").replace(/\/$/, "");
  const shown = list.slice(0, 40);
  const more = list.length - shown.length;
  const lines = [
    `${testSend ? "【测试】" : ""}【清货待特批】${planMonth} 有 ${list.length} 个清货产品当月【无清货目标】，请尽快设定清货数量目标：`,
    ...shown.map((r) => `· ${r.owner}｜${r.store_name}｜ItemID ${r.item_id}｜${r.mskus || "-"}`),
    more > 0 ? `…另有 ${more} 个未列出` : "",
    `入口：目标管理（超管可代填）或 清货中心。数据来源：AI经营分析系统自动对账`,
    baseUrl ? `${baseUrl}/admin/#/clearance-center` : "",
  ].filter(Boolean).join("\n");

  if (!send) {
    console.log("[dry-run] 将发送给", testSend ? "测试群" : APPROVER, "\n" + lines);
    console.log("SUMMARY_JSON=" + JSON.stringify({ planMonth, count: list.length, mode: "dry-run", status: "success" }));
    return;
  }

  const token = await getNotifyTenantToken();
  let target: NotifyTarget | null = null;
  if (testSend) {
    target = { type: "chat", label: "测试群", id: getTestChatId() };
  } else {
    const { targets } = await resolveActiveMembers([APPROVER]);
    target = targets[0] ?? null;
  }
  if (!target) {
    console.log(`CLEARANCE_NOTARGET_WARN 找不到发送目标（${testSend ? "测试群" : APPROVER}）`);
    console.log("SUMMARY_JSON=" + JSON.stringify({ planMonth, count: list.length, mode: "send", sent: false, status: "partial_failed" }));
    process.exit(1);
  }
  const body = testSend ? `[原目标:私聊 ${APPROVER}]\n${lines}` : lines;
  const r = await sendTextToTarget(token, target, body, true);
  console.log("SUMMARY_JSON=" + JSON.stringify({
    planMonth, count: list.length, mode: testSend ? "test" : "send", sent: r.ok, status: r.ok ? "success" : "partial_failed",
  }));
  process.exit(r.ok ? 0 : 1);
}

main().catch((e) => { console.error("FATAL:", e instanceof Error ? e.message : String(e)); process.exit(1); });
