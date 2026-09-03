/**
 * checkMonthlyPlanDeduction.ts — 月度规划「每日未填」扣分（2026-08-03；2026-08-04 修正为「每人每天5分」）
 *
 * cron：每日 09:25（催办 09:20 之后）。规则（2026-08 新规，需求方拍板）：
 *   - 当月 8 号起（7 号 23:59 截止）扫描"需填但未完成"的产品。
 *   - 扣分口径：**每负责人每天固定 5 分**——只要该负责人当天有 ≥1 个未完成品，就扣 5 分（与未完成品数无关）；
 *     不封顶（按天累计，一个月最多约 23×5=115 分）。
 *   - 需填 = 在营·非CS·非新品·非豁免(v5：上月整月WFS库存MAX=0 且 上月WFS销量SUM=0 且 在途=0)。
 *   - 完成(免扣) = 有 biz_monthly_plan 行 且 target_sales_amount 非空（勾"正常运营"也必须定目标）。
 *   - 幂等：event_monthly_plan_unfilled uq(扣分日,平台,负责人) 每人每天一行；镜像 biz_perf_deduction(biz_type=
 *     'monthly_plan_unfilled', ref_event_id=事件id) 靠 uq_perf_ref 去重 → 台账自动汇总 + 复用次月5号豁免窗口。
 *   - 当天把所有品都填完(完成) → 该负责人当天无未完成品 → 不扣；已扣历史天数保留（append-only）；仅超管可代填解锁。
 *   - 无负责人（'' / '(未分配)'）不扣（无法归属）。
 *
 * 用法：
 *   npx ts-node src/checkMonthlyPlanDeduction.ts                 # dry-run（只扫描+打印，零写入）
 *   npx ts-node src/checkMonthlyPlanDeduction.ts --confirm-write # 真实写入扣分
 *   --day N        覆盖当日日期分支（测试，1-31）
 *   --month YYYY-MM 覆盖规划月（测试）
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";

const OWNER_ALIASES: Record<string, string> = { "啊四": "林翔" };
function normalizeOwner(name: unknown): string {
  const n = String(name ?? "").trim();
  return OWNER_ALIASES[n] ?? n;
}

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
}

// 中国时区当日 YYYY-MM-DD（生产 = Asia/Shanghai）
function cstToday(): string {
  const d = new Date();
  const p = (x: number) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

const DEDUCT_START_DAY = 8; // 8 号起扣（7 号 23:59 截止）
const DAILY_POINTS = 5;     // 每人每天固定 5 分

interface OwnerUnfilled { owner: string; cnt: number; }

// 返回「当天有未完成品的负责人 + 其未完成品数」（owner 已别名归一、已排除无负责人）
async function fetchUnfilledOwners(db: mysql.Connection, planMonth: string): Promise<OwnerUnfilled[]> {
  const [py, pm] = planMonth.split("-").map(Number);
  const prevMonth = pm === 1 ? `${py - 1}-12` : `${py}-${String(pm - 1).padStart(2, "0")}`;
  const [ppy, ppm] = prevMonth.split("-").map(Number);
  const prevStart = `${prevMonth}-01`;
  const prevEnd = `${prevMonth}-${String(new Date(ppy, ppm, 0).getDate()).padStart(2, "0")}`;

  const [lmCovRows] = await db.execute(
    `SELECT COUNT(DISTINCT stat_date) AS d FROM fact_mp_sales_channel_daily
      WHERE platform='walmart' AND stat_date >= ? AND stat_date <= ?`,
    [prevStart, prevEnd],
  );
  const lmUseWfs = Number((lmCovRows as Array<Record<string, unknown>>)[0]?.d ?? 0) >= 25;
  const lmxSub = lmUseWfs
    ? `SELECT store_id, item_id, SUM(COALESCE(wfs_sales_qty,0)) AS lm_qty FROM fact_mp_sales_channel_daily WHERE platform='walmart' AND stat_date >= ? AND stat_date <= ? GROUP BY store_id, item_id`
    : `SELECT store_id, item_id, MAX(COALESCE(wfs_available_stock,0)) AS lm_qty FROM fact_inventory_daily WHERE platform='walmart' AND snapshot_date >= ? AND snapshot_date <= ? GROUP BY store_id, item_id`;

  const [rows] = await db.execute(
    `SELECT d.owner_raw AS owner, COUNT(*) AS cnt
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
       -- 2026-08-04 拍板：待到货新品(无上架时间 且 生命周期=新品期,人工优先)不扣分
       AND NOT (d.launch_ym IS NULL AND COALESCE(NULLIF(d.manual_lc,''), st.lifecycle_stage, '') = '新品期')
       AND d.owner_raw <> '' AND d.owner_raw <> '(未分配)'
       AND NOT (COALESCE(wmaxx.wfs_max,0) <= 0 ${lmUseWfs ? "AND COALESCE(lmx.lm_qty,0) = 0" : ""} AND COALESCE(trx.transit,0) = 0)
       AND (p.id IS NULL OR p.target_sales_amount IS NULL)
     GROUP BY d.owner_raw`,
    [prevStart, prevEnd, prevStart, prevEnd, planMonth, planMonth],
  );

  const agg = new Map<string, number>();
  for (const r of rows as Array<Record<string, unknown>>) {
    const owner = normalizeOwner(r.owner);
    if (!owner) continue;
    agg.set(owner, (agg.get(owner) ?? 0) + Number(r.cnt ?? 0)); // 别名归一后可能合并同人
  }
  return [...agg.entries()].map(([owner, cnt]) => ({ owner, cnt }));
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const confirmWrite = args.includes("--confirm-write");
  const dayIdx = args.indexOf("--day");
  const dayOverride = dayIdx >= 0 ? Number(args[dayIdx + 1]) : null;
  const monIdx = args.indexOf("--month");
  const monthOverride = monIdx >= 0 ? String(args[monIdx + 1]) : null;

  const today = cstToday();
  const planMonth = monthOverride ?? today.slice(0, 7);
  const dayOfMonth = dayOverride ?? Number(today.slice(8, 10));

  if (dayOfMonth < DEDUCT_START_DAY) {
    console.log("SUMMARY_JSON=" + JSON.stringify({ today, planMonth, day: dayOfMonth, skipped: `未到扣分期（<${DEDUCT_START_DAY}号）`, owners_penalized: 0, written: 0 }));
    process.exit(0);
  }

  const db = await getDb();
  try {
    const owners = await fetchUnfilledOwners(db, planMonth);
    let written = 0;
    if (confirmWrite) {
      for (const o of owners) {
        const [ev] = await db.execute(
          `INSERT INTO event_monthly_plan_unfilled (plan_month, deduction_date, platform, owner_name, unfilled_count, points)
           VALUES (?, ?, 'walmart', ?, ?, ?)
           ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)`,
          [planMonth, today, o.owner, o.cnt, DAILY_POINTS],
        );
        const eventId = (ev as mysql.ResultSetHeader).insertId;
        await db.execute(
          `INSERT IGNORE INTO biz_perf_deduction
             (deduction_date, owner_name, points, entry_type, biz_type, platform, store_id, item_id, msku, ref_event_id, note, created_by)
           VALUES (?, ?, ?, 'deduct', 'monthly_plan_unfilled', 'walmart', '', '', '', ?, '', 'checkMonthlyPlanDeduction')`,
          [today, o.owner, DAILY_POINTS, eventId],
        );
        written++;
      }
    }
    const byOwnerUnfilled: Record<string, number> = {};
    for (const o of owners) byOwnerUnfilled[o.owner] = o.cnt;
    console.log("SUMMARY_JSON=" + JSON.stringify({
      today, planMonth, day: dayOfMonth, mode: confirmWrite ? "write" : "dry-run",
      owners_penalized: owners.length, written, points_each: DAILY_POINTS,
      unfilled_by_owner: byOwnerUnfilled, status: "success",
    }));
    process.exit(0);
  } finally {
    await db.end().catch(() => undefined);
  }
}

main().catch((e) => { console.error("FATAL:", e instanceof Error ? e.message : String(e)); process.exit(1); });
