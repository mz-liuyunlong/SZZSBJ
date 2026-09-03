/**
 * lowProfitNotify.ts - 近7天低毛利率产品飞书个人通报
 *
 * 筛选近7天综合平均毛利率 < 8% 的产品（含负利润），
 * 按负责人维度生成消息，发送飞书个人消息。
 *
 * 数据来源：raw_feishu_table（sheet_id='<REDACTED_FEISHU_SHEET_ID>'，订单利润 Beta 的 raw 快照，
 *          由 syncOrderProfitDaily.ts 从 FACT/DIM 生成，负责人字段已在该脚本内改读
 *          dim_product.owner，本文件不直接依赖飞书 <REDACTED_FEISHU_SHEET_ID>，此处仅读取已生成好的快照）
 * open_id：dim_feishu_member
 *
 * 手动 dry-run（不发送）：
 *   npx ts-node src/lowProfitNotify.ts
 *
 * 手动真实发送：
 *   npx ts-node src/lowProfitNotify.ts --send
 *
 * 定时任务：每周一、周四 09:45（生产 crontab 实证 2026-07-27；此前注释误写 08:00 已订正）
 *   45 9 * * 1,4 cd /opt/lingxing-auto && npx ts-node src/lowProfitNotify.ts --send >> /opt/lingxing-auto/logs/low-profit-notify.log 2>&1
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";

const axios = require("axios/dist/node/axios.cjs") as typeof import("axios").default;

// ── 配置 ─────────────────────────────────────────────────────────────
const SPREADSHEET_TOKEN  = "<REDACTED_FEISHU_SPREADSHEET_TOKEN>";
const PROFIT_SHEET_ID    = "order_profit_daily";  // 订单利润 Beta
const PROFIT_THRESHOLD   = 8;                     // 毛利率阈值（%）
const LOOKBACK_DAYS      = 7;
const UNMATCHED_LABEL    = "未匹配负责人";

// ── 环境变量 ──────────────────────────────────────────────────────────
// 批B收口: FEISHU_APP_ID/SECRET 由 feishuNotify 模块统一读取
// 批B(2026-07-11): 统一发送模块——额外接收端（env 留空=行为与现状完全一致）
import { parseListEnv, resolveActiveMembers, fanoutText, formatResults, sendTextToTarget, getTenantToken, sendTestGroupText, NotifyTarget } from "./feishuNotify";

// ── 工具函数 ──────────────────────────────────────────────────────────
function getErrorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

function getShanghaiTimeStr(): string {
  return new Date().toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false });
}

const LAG_DAYS = 2; // 数据滞后天数

/** 计算上海时区日期范围，含2天滞后
 *  今天=6/29 → endDate=6/27，startDate=6/20（近7天）
 */
function getDateRange(): { startDate: string; endDate: string } {
  const nowMs   = Date.now() + 8 * 3600 * 1000; // 上海 UTC+8
  const fmt = (d: Date) => d.toISOString().slice(0, 10);
  const endDate   = fmt(new Date(nowMs - LAG_DAYS * 86400 * 1000));
  const startDate = fmt(new Date(nowMs - (LAG_DAYS + LOOKBACK_DAYS) * 86400 * 1000));
  return { startDate, endDate };
}

// ── JSON 字段提取工具（兼容中英文字段名）────────────────────────────
/** 提取文本字段，优先取第一个有值的字段名 */
function jt(...keys: string[]): string {
  const exprs = keys.map((k) => `NULLIF(JSON_UNQUOTE(JSON_EXTRACT(row_json, '$."${k}"')), '')`);
  return `COALESCE(${exprs.join(", ")})`;
}

/** 提取数值字段（先 UNQUOTE 再 CAST，兼容 JSON 字符串数值如 "1.23"） */
function jn(...keys: string[]): string {
  const exprs = keys.map((k) => `NULLIF(JSON_UNQUOTE(JSON_EXTRACT(row_json, '$."${k}"')), '')`);
  return `CAST(COALESCE(${exprs.join(", ")}, '0') AS DECIMAL(18,4))`;
}

// ── 数据库 ────────────────────────────────────────────────────────────
function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host:     process.env.DB_HOST     ?? "127.0.0.1",
    port:     Number(process.env.DB_PORT ?? 3306),
    user:     process.env.DB_USER     ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME     ?? "walmart_ai_data",
  });
}

// ── 类型 ──────────────────────────────────────────────────────────────
interface LowProfitItem {
  itemId:     string;
  storeName:  string;
  msku:       string;
  owner:      string;
  avgMargin:  number;  // 百分比数值，如 -5.2 或 3.1
}

// ── 查询低毛利率产品 ──────────────────────────────────────────────────
async function fetchLowProfitItems(db: mysql.Connection): Promise<LowProfitItem[]> {
  const { startDate, endDate } = getDateRange();
  console.log(`  查询日期范围: ${startDate} ～ ${endDate}（含两端，滞后${LAG_DAYS}天）`);

  // 从 order_profit_daily 聚合近7天，按加权平均毛利率筛选
  const sql = `
    SELECT
      item_id   AS itemId,
      store_name AS storeName,
      msku,
      COALESCE(NULLIF(owner, ''), '${UNMATCHED_LABEL}') AS owner,
      ROUND(
        CASE WHEN SUM(sales_amount) > 0
          THEN SUM(gross_profit) / SUM(sales_amount) * 100
          ELSE 0
        END, 2
      ) AS avgMargin
    FROM (
      SELECT
        ${jt("商品ID", "item_id")}               AS item_id,
        ${jt("店铺",   "store_name")}             AS store_name,
        ${jt("MSKU",   "msku")}                   AS msku,
        ${jt("负责人", "owner")}                  AS owner,
        ${jn("今日销售额（$）", "sales_amount")}  AS sales_amount,
        ${jn("毛利润（$）",     "gross_profit")}  AS gross_profit
      FROM raw_feishu_table
      WHERE spreadsheet_token = ?
        AND sheet_id = ?
        AND DATE(CONVERT_TZ(data_date, '+00:00', '+08:00')) >= ?
        AND DATE(CONVERT_TZ(data_date, '+00:00', '+08:00')) <= ?
    ) base
    WHERE item_id IS NOT NULL AND item_id != ''
      -- 2026-07-27 排除「已审批通过的清货」产品：清货本就不看利润，不纳入低毛利通报。
      -- 口径：dim_product.manual_lifecycle_stage='清货期' 仅在清货审批通过时写入（页面/飞书卡审批），
      -- 提交申请(pending)不写、系统自动判清货只落 system_lifecycle_stage 不进 manual，故此字段=已审批清货。
      -- 审批 UPDATE 按 platform+store_id+item_id 生效（同 item_id 全部 msku 均置清货期），故此处按 item_id 排除整品。
      AND NOT EXISTS (
        SELECT 1 FROM dim_product dp
        WHERE dp.platform = 'walmart'
          AND dp.item_id = base.item_id
          AND TRIM(dp.manual_lifecycle_stage) = '清货期'
      )
    GROUP BY item_id, store_name, msku, owner
    HAVING SUM(sales_amount) > 0
       AND avgMargin < ?
       AND NOT (avgMargin < 0 AND msku LIKE 'CS%')
    ORDER BY owner, avgMargin ASC
  `;

  const [rows] = await db.execute<mysql.RowDataPacket[]>(sql, [
    SPREADSHEET_TOKEN, PROFIT_SHEET_ID, startDate, endDate,
    PROFIT_THRESHOLD,
  ]);

  return rows.map((r) => ({
    itemId:    String(r.itemId    ?? ""),
    storeName: String(r.storeName ?? ""),
    msku:      String(r.msku      ?? ""),
    owner:     String(r.owner     ?? UNMATCHED_LABEL),
    avgMargin: Number(r.avgMargin ?? 0),
  }));
}

// ── 读取 open_id 映射 ─────────────────────────────────────────────────
// 批B第3版: loadOwnerOpenIds 已移除——统一走 feishuNotify.resolveActiveMembers
// （精确匹配+active+open_id非空；0条/重名告警跳过，禁止猜测）。

// ── 消息生成 ──────────────────────────────────────────────────────────
function buildOwnerMessage(
  owner: string,
  items: LowProfitItem[],
  notifyTime: string,
): string {
  const lines: string[] = [
    `【低毛利率产品通报】${notifyTime}`,
    `负责人：${owner}`,
    `近 ${LOOKBACK_DAYS} 天综合平均毛利率低于 ${PROFIT_THRESHOLD}% 的产品（共 ${items.length} 个）：`,
    "",
  ];

  // 按店铺分组
  const byStore = new Map<string, LowProfitItem[]>();
  for (const item of items) {
    if (!byStore.has(item.storeName)) byStore.set(item.storeName, []);
    byStore.get(item.storeName)!.push(item);
  }

  for (const [store, storeItems] of byStore.entries()) {
    lines.push(`店铺：${store}`);
    for (const item of storeItems) {
      const marginStr = item.avgMargin.toFixed(1) + "%";
      lines.push(`  商品ID：${item.itemId}  MSKU：${item.msku}  毛利率：${marginStr}`);
    }
  }

  return lines.join("\n");
}

// ── 飞书发送 ──────────────────────────────────────────────────────────
// 批B收口: 本地 getFeishuAppToken/sendToFeishuUser 已移除，
// 统一走 feishuNotify.sendTextToTarget（分类重试/敏感日志清理/分片/独立结果）

// ── 主函数 ────────────────────────────────────────────────────────────
async function main(): Promise<void> {
  const startedAt  = Date.now();
  const doSend     = process.argv.includes("--send");
  // 测试模式(2026-07-11)：--test-send 只发测试群，不发原负责人/新增接收人/生产群
  const testSend   = process.argv.includes("--test-send");
  if (testSend && doSend) {
    console.log("[错误] --send 与 --test-send 禁止同时使用");
    process.exit(1);
  }
  if (testSend && process.argv.includes("--dry-run")) {
    console.log("[错误] --dry-run 与 --test-send 禁止同时使用");
    process.exit(1);
  }
  if (process.argv.includes("--force-preview-test") && !testSend) {
    console.log("[错误] --force-preview-test 必须配合 --test-send 使用");
    process.exit(1);
  }
  const notifyTime = getShanghaiTimeStr();

  console.log("=".repeat(60));
  console.log("低毛利率产品飞书个人通报");
  console.log(`执行时间（上海）: ${notifyTime}`);
  console.log(`模式: ${testSend ? "test-send（仅应用机器人测试群）" : doSend ? "真实发送" : "dry-run（加 --send 参数发送）"}`);
  console.log(`阈值: 近 ${LOOKBACK_DAYS} 天平均毛利率 < ${PROFIT_THRESHOLD}%`);
  console.log("=".repeat(60));

  let db: mysql.Connection | null = null;

  try {
    db = await getDb();
    console.log("\n[1/3] 查询低毛利率产品...");
    const items = await fetchLowProfitItems(db);
    console.log(`  符合条件产品数: ${items.length}`);

    if (!items.length) {
      if (testSend) {
        // 空状态也必须发送一条测试消息（验证发送通道），不伪造业务明细
        const emptyText = [
          `【测试】【低毛利率产品通报】${notifyTime}`,
          "本次没有符合条件的数据。",
          "此消息仅用于验证应用机器人发送通道。",
        ].join("\n");
        const r0 = await sendTestGroupText("测试群", emptyText);
        console.log(`测试群发送结果: ${formatResults([r0])}`);
        if (!r0.ok) process.exitCode = 1;
        else console.log("NOTIFY_TEST_SENT=1");
        return;
      }
      console.log("  近7天无低毛利率产品，无需通报。");
      return;
    }

    // 按负责人分组，过滤未匹配
    const ownerMap = new Map<string, LowProfitItem[]>();
    let unmatchedCount = 0;
    for (const item of items) {
      if (item.owner === UNMATCHED_LABEL || !item.owner) {
        unmatchedCount++;
        continue;
      }
      if (!ownerMap.has(item.owner)) ownerMap.set(item.owner, []);
      ownerMap.get(item.owner)!.push(item);
    }
    if (unmatchedCount) console.log(`  未匹配负责人产品: ${unmatchedCount} 个（跳过）`);

    // ── 测试模式：真实数据 → 汇总 → 只发测试群，随后直接返回 ──
    if (testSend) {
      const allMsgs: string[] = [];
      for (const [owner, ownerItems] of ownerMap.entries()) {
        allMsgs.push(buildOwnerMessage(owner, ownerItems, notifyTime));
      }
      const testText = [
        `【测试】【低毛利率产品通报】${notifyTime}`,
        `涉及负责人数: ${ownerMap.size}`,
        "",
        allMsgs.join("\n\n"),
      ].join("\n");
      const r = await sendTestGroupText("测试群", testText);
      console.log(`测试群发送结果: ${formatResults([r])}`);
      if (!r.ok) process.exitCode = 1;
      else console.log("NOTIFY_TEST_SENT=1");
      return;
    }

    console.log("\n[2/3] 花名册解析负责人（唯一口径）...");
    const { targets: ownerTargets, warnings: ownerWarnings } =
      await resolveActiveMembers([...ownerMap.keys()]);
    ownerWarnings.forEach((w) => console.log(`  [告警] 负责人 ${w}`));
    const ownerTargetMap = new Map(ownerTargets.map((t) => [t.label, t]));

    console.log(`\n[3/3] 发送通报，共 ${ownerMap.size} 位负责人（可发送 ${ownerTargetMap.size}）...`);

    let appToken = "";
    if (doSend) {
      appToken = await getTenantToken();
      console.log("  飞书 token 获取成功");
    }

    let allOk = true;
    const sentMessages: string[] = []; // 批B: 供额外接收端汇总
    for (const [owner, ownerItems] of ownerMap.entries()) {
      const target = ownerTargetMap.get(owner);
      const message = buildOwnerMessage(owner, ownerItems, notifyTime);
      sentMessages.push(message);
      if (!target) {
        // 0条或重名：已在解析告警中说明，跳过，禁止猜测发送
        continue;
      }
      // 批B收口: 统一模块发送
      const r = await sendTextToTarget(appToken, target, message, doSend);
      if (!r.ok) allOk = false;
      if (doSend) await new Promise((r) => setTimeout(r, 500));
    }

    // ── 批B: 额外接收端（LOW_PROFIT_EXTRA_USERS / LOW_PROFIT_EXTRA_CHAT_IDS，留空即现状） ──
    const extraUserNames = parseListEnv("LOW_PROFIT_EXTRA_USERS");
    const extraChatIds = parseListEnv("LOW_PROFIT_EXTRA_CHAT_IDS");
    if (extraUserNames.length || extraChatIds.length) {
      const { targets: userTargets, warnings } = await resolveActiveMembers(extraUserNames);
      warnings.forEach((w) => console.log(`  [告警] 额外接收人 ${w}`));
      const extraTargets: NotifyTarget[] = [
        ...userTargets,
        ...extraChatIds.map((id, i) => ({ type: "chat" as const, label: `通报群${i + 1}`, id })),
      ];
      if (extraTargets.length && sentMessages.length) {
        const summaryText = [
          `【低毛利率产品通报·汇总】${notifyTime}`,
          `涉及负责人数: ${ownerMap.size}`,
          "",
          sentMessages.join("\n\n"),
        ].join("\n");
        const extraResults = await fanoutText(appToken, extraTargets, summaryText, doSend);
        console.log(`  额外接收端结果: ${formatResults(extraResults)}`);
        if (extraResults.some((r) => !r.ok)) {
          console.log("  [告警] 部分额外接收端发送失败（独立通道，不影响原接收人结果）");
        }
      }
    }

    const elapsed = ((Date.now() - startedAt) / 1000).toFixed(1);
    console.log(`\n飞书发送结果: ${allOk ? "✅ 成功" : "❌ 失败"}`);
    console.log(`执行完毕，耗时 ${elapsed}s`);

    if (!allOk) process.exitCode = 1;

  } catch (e) {
    console.log(`[错误] ${getErrorMessage(e)}`);
    process.exitCode = 1;
  } finally {
    if (db) await db.end().catch(() => {});
  }
}

if (require.main === module) {
  main();
}
