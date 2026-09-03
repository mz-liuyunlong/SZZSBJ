/**
 * checkMonthlyPlanReminder.ts — 月度规划催办链（2026-07-15，月报体系第四步）
 *
 * cron：每日 09:20（与批C 09:05 错开）。按日期分支（方案定稿）：
 *   5号        首提：群（整体进度+截止提示）+ 私聊每位有未完成的负责人
 *   7号        末次催办：只私聊未完成者（今日23:59截止，明日起每天扣5分）
 *   8号        逾期：群内点名（已进入每日扣分）+ 私聊人事（MONTHLY_PLAN_HR，默认黄少如）逾期名单
 *   其他日期   静默退出（exit 0，日志一行）
 *
 * 用法：
 *   npx ts-node src/checkMonthlyPlanReminder.ts             # dry-run（按今天日期分支，零发送）
 *   npx ts-node src/checkMonthlyPlanReminder.ts --send      # 真实发送
 *   --day N     覆盖日期分支（测试用，1-31）
 *   --test-send 或 env BUSINESS_REPORT_FORCE_TEST=1 → 全部消息只进测试群（标注原目标）
 *
 * 数据源：ai_monthly_issue_item（当月 plan_month 最新 report）LEFT JOIN biz_monthly_plan。
 * "(未分配)"不可私聊，其未填数并入群消息提示。
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import {
  NotifyTarget,
  SendResult,
  getNotifyTenantToken,
  getTestChatId,
  resolveActiveMembers,
  sendTextToTarget,
} from "./feishuNotify";

const HR_NAME = (process.env.MONTHLY_PLAN_HR ?? "黄少如").trim();

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host:     process.env.DB_HOST     ?? "127.0.0.1",
    port:     Number(process.env.DB_PORT ?? 3306),
    user:     process.env.DB_USER     ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME     ?? "walmart_ai_data",
  });
}

interface OwnerStat { owner: string; total: number; unfilled: number; }

async function fetchStats(planMonth: string): Promise<OwnerStat[]> {
  // 2026-08-04 v5（与 /monthly-plan/todo、每日扣分 checkMonthlyPlanDeduction 完全同口径）：
  //   底座=在营全集(dim_product active·非CS·非新品)，非仅问题清单；豁免=上月整月WFS库存MAX=0 且
  //   上月WFS销量SUM=0(覆盖<25天回退库存兜底) 且 在途=0(PMC口径)；清货期不再豁免。
  //   完成(免催/免扣)=有 biz_monthly_plan 行 且 target_sales_amount 非空。
  const [py, pm] = planMonth.split("-").map(Number);
  const prevMonth = pm === 1 ? `${py - 1}-12` : `${py}-${String(pm - 1).padStart(2, "0")}`;
  const [ppy, ppm] = prevMonth.split("-").map(Number);
  const prevStart = `${prevMonth}-01`;
  const prevEnd = `${prevMonth}-${String(new Date(ppy, ppm, 0).getDate()).padStart(2, "0")}`;
  const db = await getDb();
  try {
    // 豁免口径v4：上月WFS销量覆盖检测（与 /monthly-plan/todo 同源逻辑）
    const [lmCovRows] = await db.execute(
      `SELECT COUNT(DISTINCT stat_date) AS d FROM fact_mp_sales_channel_daily
        WHERE platform = 'walmart' AND stat_date >= ? AND stat_date <= ?`,
      [prevStart, prevEnd],
    );
    const lmCovDays = Number((lmCovRows as Array<Record<string, unknown>>)[0]?.d ?? 0);
    const lmUseWfs = lmCovDays >= 25;
    console.log(`[monthly-plan-reminder] 上月WFS销量覆盖=${lmCovDays}天 → ${lmUseWfs ? '真实WFS销量口径' : '库存等价法回退'}`);
    const lmxSub = lmUseWfs
      ? `SELECT store_id, item_id, SUM(COALESCE(wfs_sales_qty, 0)) AS lm_qty
         FROM fact_mp_sales_channel_daily
         WHERE platform = 'walmart' AND stat_date >= ? AND stat_date <= ?
         GROUP BY store_id, item_id`
      : `SELECT store_id, item_id, MAX(COALESCE(wfs_available_stock, 0)) AS lm_qty
         FROM fact_inventory_daily
         WHERE platform = 'walmart' AND snapshot_date >= ? AND snapshot_date <= ?
         GROUP BY store_id, item_id`;
    const [rows] = await db.execute(
      `SELECT COALESCE(NULLIF(d.owner_raw,''),'(未分配)') AS owner,
              COUNT(*) AS total,
              SUM(CASE WHEN (p.id IS NULL OR p.target_sales_amount IS NULL) THEN 1 ELSE 0 END) AS unfilled
       FROM (
         SELECT store_id, item_id,
                MAX(COALESCE(NULLIF(owner,''),'')) AS owner_raw,
                MAX(NULLIF(manual_lifecycle_stage,'')) AS manual_lc,
                DATE_FORMAT(MIN(launch_date),'%Y-%m') AS launch_ym
         FROM dim_product
         WHERE platform='walmart' AND COALESCE(NULLIF(product_management_status,''),'active') NOT IN ('inactive','archived')
         GROUP BY store_id, item_id
       ) d
       LEFT JOIN (
         SELECT store_id, item_id, MAX(CASE WHEN product_type='CS测品' THEN 1 ELSE 0 END) AS is_cs,
                MIN(lifecycle_stage) AS lifecycle_stage
         FROM dim_product_business_state
         WHERE platform='walmart' AND stat_date=(SELECT MAX(stat_date) FROM dim_product_business_state)
         GROUP BY store_id, item_id
       ) st ON st.store_id=d.store_id AND st.item_id=d.item_id
       LEFT JOIN (
         SELECT store_id, item_id, MAX(COALESCE(wfs_available_stock,0)) AS wfs_max
         FROM fact_inventory_daily
         WHERE platform='walmart' AND snapshot_date >= ? AND snapshot_date <= ?
         GROUP BY store_id, item_id
       ) wmaxx ON wmaxx.store_id=d.store_id AND wmaxx.item_id=d.item_id
       LEFT JOIN ( ${lmxSub} ) lmx ON lmx.store_id=d.store_id AND lmx.item_id=d.item_id
       LEFT JOIN (
         SELECT dp.store_id, dp.item_id, SUM(t.in_transit) AS transit
         FROM (
           SELECT s.store_id, si.msku, SUM(GREATEST(COALESCE(si.shipments_num,0)-COALESCE(si.received_num,0),0)) AS in_transit
           FROM fact_wfs_shipment s
           JOIN fact_wfs_shipment_item si ON si.platform=s.platform AND si.store_id=s.store_id AND si.shipment_id=s.shipment_id
           WHERE s.platform='walmart' AND s.to_closed_time IS NULL AND s.to_cancelled_time IS NULL
           GROUP BY s.store_id, si.msku
         ) t
         JOIN dim_product dp ON dp.platform='walmart' AND dp.store_id=t.store_id AND dp.msku=t.msku
         GROUP BY dp.store_id, dp.item_id
       ) trx ON trx.store_id=d.store_id AND trx.item_id=d.item_id
       LEFT JOIN biz_monthly_plan p
         ON p.plan_month=? AND p.platform='walmart' AND p.store_id=d.store_id AND p.item_id=d.item_id
       WHERE COALESCE(st.is_cs,0)=0
         AND COALESCE(d.launch_ym,'') <> ?
         -- 2026-08-04 拍板：待到货新品(无上架时间 且 生命周期=新品期,人工优先)不催办
         AND NOT (d.launch_ym IS NULL AND COALESCE(NULLIF(d.manual_lc,''), st.lifecycle_stage, '') = '新品期')
         AND NOT (COALESCE(wmaxx.wfs_max,0) <= 0 ${lmUseWfs ? "AND COALESCE(lmx.lm_qty,0) = 0" : ""} AND COALESCE(trx.transit,0) = 0)
       GROUP BY d.owner_raw ORDER BY unfilled DESC`,
      [prevStart, prevEnd, prevStart, prevEnd, planMonth, planMonth],
    );
    return (rows as Array<{ owner: string; total: string | number; unfilled: string | number }>)
      .map((r) => ({ owner: String(r.owner), total: Number(r.total), unfilled: Number(r.unfilled) }));
  } finally { await db.end().catch(() => undefined); }
}

async function main(): Promise<void> {
  const a = process.argv.slice(2);
  const send = a.includes("--send");
  const forceTest = (process.env.BUSINESS_REPORT_FORCE_TEST ?? "").trim() === "1";
  const testSend = a.includes("--test-send") || forceTest;
  const dayIdx = a.indexOf("--day");
  const day = dayIdx >= 0 ? Number(a[dayIdx + 1]) : new Date().getDate();
  const now = new Date();
  const planMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;

  if (![5, 7, 8].includes(day)) {
    console.log(`REMINDER_SKIP day=${day} 非催办日（5/7/8），静默退出`);
    console.log("SUMMARY_JSON=" + JSON.stringify({ day, planMonth, action: "skip", status: "success" }));
    return;
  }

  const stats = await fetchStats(planMonth);
  if (stats.length === 0) {
    console.log(`REMINDER_SKIP plan_month=${planMonth} 无在营需填产品，退出`);
    console.log("SUMMARY_JSON=" + JSON.stringify({ day, planMonth, action: "no_issue_items", status: "success" }));
    return;
  }
  const totalAll = stats.reduce((s, r) => s + r.total, 0);
  const unfilledAll = stats.reduce((s, r) => s + r.unfilled, 0);
  const pending = stats.filter((r) => r.unfilled > 0);
  const dmOwners = pending.filter((r) => r.owner !== "(未分配)");
  const unassigned = pending.find((r) => r.owner === "(未分配)");

  if (unfilledAll === 0 && day !== 5) {
    console.log(`REMINDER_SKIP 全部已填（${totalAll}个），无需催办`);
    console.log("SUMMARY_JSON=" + JSON.stringify({ day, planMonth, action: "all_filled", status: "success" }));
    return;
  }

  const baseUrl = (process.env.BUSINESS_REPORT_BASE_URL ?? "").replace(/\/$/, "");
  const planUrl = `${baseUrl}/admin/#/feishu-raw-sales-data`;
  const testTag = testSend ? "【测试】" : "";
  const deadline = `${planMonth}-07`;

  // 组装消息
  const jobs: Array<{ kind: "group" | "user"; name: string; text: string }> = [];
  // 组装消息（5=首提 / 7=末次催办 / 8=逾期已开扣）
  if (day === 5) {
    jobs.push({
      kind: "group", name: "经营周报群",
      text: [
        `${testTag}【月度规划】${planMonth} 已开启`,
        `需填产品共 ${totalAll} 个 ｜ 已完成 ${totalAll - unfilledAll} ｜ 未完成 ${unfilledAll}`,
        `请各负责人于 ${deadline} 23:59 前在"运营日志→月度规划"完成填报（每产品设2个优化指标或勾"正常运营"，均须定目标）`,
        `⚠️ 8号 00:00 起未完成者每天扣 5 分（不封顶），且填报锁定、仅可联系林翔代填`,
        unassigned ? `⚠️ 另有未分配负责人产品 ${unassigned.unfilled} 个，待补录负责人后处理（不计扣分）` : "",
        `入口：${planUrl}`,
      ].filter(Boolean).join("\n"),
    });
    for (const o of dmOwners) {
      jobs.push({
        kind: "user", name: o.owner,
        text: [
          `${testTag}【月度规划】${planMonth} 待填报`,
          `你有需填产品 ${o.total} 个，其中未完成 ${o.unfilled} 个`,
          `请于 ${deadline} 23:59 前完成；8号起未完成每天扣 5 分（不封顶），逾期锁定需联系林翔代填`,
          `入口：${planUrl}`,
        ].join("\n"),
      });
    }
  } else if (day === 7) {
    for (const o of dmOwners) {
      jobs.push({
        kind: "user", name: o.owner,
        text: [
          `${testTag}【末次催办】${planMonth} 月度规划今日截止`,
          `你还有 ${o.unfilled} 个产品未完成，今日 23:59 截止！明日（8号）起未完成每天扣 5 分，且填报锁定需联系林翔代填`,
          `入口：${planUrl}`,
        ].join("\n"),
      });
    }
  } else {
    // day === 8 逾期通报（已进入每日扣分）
    const roll = dmOwners.map((o) => `${o.owner}（${o.unfilled}个）`).join("、");
    if (dmOwners.length > 0 || unassigned) {
      jobs.push({
        kind: "group", name: "经营周报群",
        text: [
          `${testTag}【逾期通报】${planMonth} 月度规划已截止（${deadline} 23:59），今日起未完成每天扣 5 分`,
          dmOwners.length ? `以下负责人仍未完成、已进入每日扣分：${roll}` : "",
          unassigned ? `另有未分配负责人产品 ${unassigned.unfilled} 个未处理（不计扣分）` : "",
        ].filter(Boolean).join("\n"),
      });
      jobs.push({
        kind: "user", name: HR_NAME,
        text: [
          `${testTag}【人事通知】${planMonth} 月度规划逾期名单（截止 ${deadline}）`,
          dmOwners.length ? `未完成、今日起每日扣分（每人5分/天）：${roll}` : "全员完成，无逾期",
          `如需代填请协调林翔。数据来源：AI经营分析系统自动对账`,
        ].join("\n"),
      });
    }
  }

  if (jobs.length === 0) {
    console.log("REMINDER_SKIP 本分支无需发送");
    console.log("SUMMARY_JSON=" + JSON.stringify({ day, planMonth, action: "nothing_to_send", status: "success" }));
    return;
  }

  const token = await getNotifyTenantToken();
  const results: SendResult[] = [];
  const warnings: string[] = [];

  if (testSend) {
    const t: NotifyTarget = { type: "chat", label: "测试群", id: getTestChatId() };
    for (const j of jobs) {
      results.push(await sendTextToTarget(token, t, `[原目标:${j.kind === "group" ? "业务群" : `私聊 ${j.name}`}]\n${j.text}`, send));
    }
  } else {
    const chatId = (process.env.BUSINESS_REPORT_CHAT_ID ?? "").trim();
    const userJobs = jobs.filter((j) => j.kind === "user");
    const { targets, warnings: w } = await resolveActiveMembers([...new Set(userJobs.map((j) => j.name))]);
    warnings.push(...w);
    for (const j of jobs) {
      if (j.kind === "group") {
        if (!chatId) { warnings.push("缺少 BUSINESS_REPORT_CHAT_ID，群消息跳过"); continue; }
        results.push(await sendTextToTarget(token, { type: "chat", label: "经营周报群", id: chatId }, j.text, send));
      } else {
        const t = targets.find((x) => x.label === j.name);
        if (!t) { warnings.push(`私聊跳过：${j.name}（不在在册花名册或缺open_id）`); continue; }
        results.push(await sendTextToTarget(token, t, j.text, send));
      }
    }
  }

  const sendSuccess = results.filter((r) => r.ok).length;
  const sendFailed = results.filter((r) => !r.ok).length;
  console.log("SUMMARY_JSON=" + JSON.stringify({
    day, planMonth, mode: testSend ? "test" : "prod", dryRun: !send,
    totalIssues: totalAll, unfilledTotal: unfilledAll,
    pendingOwners: pending.map((o) => ({ owner: o.owner, unfilled: o.unfilled })),
    planned: jobs.length, sendSuccess, sendFailed, warnings,
    status: sendFailed === 0 ? "success" : "partial_failed",
  }));
  process.exit(sendFailed === 0 ? 0 : 1);
}

main().catch((e) => {
  console.error("FATAL:", e instanceof Error ? e.message : String(e));
  process.exit(1);
});
