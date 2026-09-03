/**
 * checkAutoAdSearchTermImport.ts — 自动广告搜索词导入检查 v3（数据库口径终态版）
 *
 * 2026-07-22 需求方拍板终态：
 *   1. 数据源改 MySQL `fact_ads_keyword_daily`（source_type='walmart_auto_csv'），
 *      不再读飞书表 1HeaCn——该表已随 2026-07-18 飞书副本写入关停而停更（最新 07-15），
 *      继续读它必然天天误报缺失。
 *   2. 通道：仅私信 AUTO_AD_AT_USER（默认 翁骏，按在册花名册解析 open_id）；
 *      webhook 与群通道全部取消。
 *   3. cron 由 16:10 调整为 17:25（crontab 由部署侧同批修改）。
 *
 * 判定口径不变：targetDate = 上海日期 - 3 天；库内 MAX(stat_date) >= targetDate → ok；
 *   否则 missing 通报（library 无任何行 → no_data，按缺失处理并提示核查同步链）。
 *
 * 用法：
 *   npx ts-node src/checkAutoAdSearchTermImport.ts              # dry-run：只判定+预览，零发送
 *   npx ts-node src/checkAutoAdSearchTermImport.ts --send       # 真实发送（仅缺失时私信）
 *   --test-send  消息只进测试群（带【测试】前缀），不发私信
 *
 * 本脚本零写入：不写任何数据库表、不写飞书表格（TableOperationLogger 已随飞书副本链路退役）。
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import {
  getTenantToken,
  mirrorToTestEnabled,
  resolveActiveMembers,
  sendTestGroupText,
  sendTextToTarget,
  SendResult,
} from "./feishuNotify";
import { formatDateTimeCST, getTargetDateCST } from "./notifyRules/autoAdImportCheck";

const TASK_NAME = "自动广告搜索词导入检查";
const SOURCE_TYPE = "walmart_auto_csv";
const LAG_DAYS = 3;
const IMPORT_PAGE = "http://42.193.254.170/walmart-ads-data";

interface LatestRow extends mysql.RowDataPacket {
  latest: string | null;
  total: number;
}
interface StoreRow extends mysql.RowDataPacket {
  store_name: string;
  latest: string | null;
}

function dbConfig(): mysql.ConnectionOptions {
  return {
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
    dateStrings: true, // 2026-07-11 铁律：读 DATE/DATETIME 必须 dateStrings
  };
}

async function fetchDbStatus(): Promise<{ latest: string | null; total: number; stores: StoreRow[] }> {
  const db = await mysql.createConnection(dbConfig());
  try {
    const [g] = await db.query<LatestRow[]>(
      `SELECT DATE_FORMAT(MAX(stat_date), '%Y-%m-%d') AS latest, COUNT(*) AS total
       FROM fact_ads_keyword_daily
       WHERE source_type = ?`,
      [SOURCE_TYPE],
    );
    const [stores] = await db.query<StoreRow[]>(
      `SELECT store_name, DATE_FORMAT(MAX(stat_date), '%Y-%m-%d') AS latest
       FROM fact_ads_keyword_daily
       WHERE source_type = ?
       GROUP BY store_name
       ORDER BY latest ASC, store_name ASC`,
      [SOURCE_TYPE],
    );
    return { latest: g[0]?.latest ?? null, total: Number(g[0]?.total ?? 0), stores };
  } finally {
    await db.end();
  }
}

function dayDiff(fromYmd: string, toYmd: string): number {
  const [fy, fm, fd] = fromYmd.split("-").map(Number);
  const [ty, tm, td] = toYmd.split("-").map(Number);
  return Math.round((Date.UTC(ty, tm - 1, td) - Date.UTC(fy, fm - 1, fd)) / 86400000);
}

function buildMissingBody(args: {
  targetDate: string;
  checkTime: string;
  latest: string | null;
  atName: string;
  laggingStores: StoreRow[];
}): string {
  const behind = args.latest ? `${dayDiff(args.latest, args.targetDate)} 天` : "无法计算（库内无数据）";
  const lines = [
    "悦斯自动广告搜索词数据缺失（数据库口径）",
    `应导入数据日期: ${args.targetDate}`,
    `任务检查时间: ${args.checkTime}`,
    `库内最新数据日期: ${args.latest ?? "无"}`,
    `落后天数: ${behind}`,
  ];
  if (args.laggingStores.length > 0 && args.latest) {
    const lagOnly = args.laggingStores.filter((s) => (s.latest ?? "") < args.latest!);
    if (lagOnly.length > 0) {
      lines.push(`掉队店铺: ${lagOnly.map((s) => `${s.store_name}(${s.latest ?? "无"})`).join("、")}`);
    }
  }
  lines.push(`请 ${args.atName} 尽快在导入工具上传近14天自动广告搜索词报表: ${IMPORT_PAGE}`);
  return lines.join("\n");
}

async function main(): Promise<void> {
  const send = process.argv.includes("--send");
  const testSend = process.argv.includes("--test-send");
  const now = new Date();
  const checkTime = formatDateTimeCST(now);
  const targetDate = getTargetDateCST(now, LAG_DAYS);
  const atName = (process.env.AUTO_AD_AT_USER ?? "翁骏").trim();

  console.log(`[${TASK_NAME}] 数据库口径 v3 ｜ 模式: ${testSend ? "test-send（只发测试群）" : send ? "真实发送" : "dry-run"}`);
  console.log(`应导入数据日期(T-${LAG_DAYS})=${targetDate} ｜ 检查时间=${checkTime} ｜ source_type=${SOURCE_TYPE}`);

  const { latest, total, stores } = await fetchDbStatus();
  const status: "ok" | "missing" | "no_data" = latest ? (latest >= targetDate ? "ok" : "missing") : "no_data";
  console.log(`库内最新数据日期=${latest ?? "无"} ｜ 累计行数=${total} ｜ 店铺数=${stores.length} ｜ 判定=${status}`);

  const results: SendResult[] = [];
  const warnings: string[] = [];
  let planned = 0;

  if (status === "ok") {
    console.log(`✅ 应导入数据日期 ${targetDate} 已满足（库内最新=${latest}），无需通知`);
  } else {
    const body = buildMissingBody({ targetDate, checkTime, latest, atName, laggingStores: stores });
    if (status === "no_data") {
      warnings.push("库内 walmart_auto_csv 零行——请先核查同步链/表结构，而非单纯补导入");
    }
    if (testSend) {
      planned = 1;
      results.push(await sendTestGroupText(`【测试】${TASK_NAME}`, `【测试】\n${body}`));
    } else {
      const { targets, warnings: w } = await resolveActiveMembers([atName]);
      warnings.push(...w);
      if (targets.length === 0) {
        console.log(`[警告] ${atName} 无法解析为在册接收人，本次不发送（禁止猜测发送）`);
      } else {
        planned = 1;
        if (!send) {
          results.push(await sendTextToTarget("", targets[0], body, false)); // dry-run 预览，不取 token
        } else {
          const token = await getTenantToken();
          results.push(await sendTextToTarget(token, targets[0], body, true));
          if (mirrorToTestEnabled()) {
            await sendTestGroupText(`${TASK_NAME}-监督副本`, body);
          }
        }
      }
    }
  }

  for (const w of warnings) console.log(`  [警告] ${w}`);
  const sendSuccess = results.filter((r) => r.ok).length;
  const sendFailed = results.filter((r) => !r.ok).length;
  const summary = {
    task: "checkAutoAdSearchTermImport",
    version: "v3_db",
    caliber: "db",
    source_type: SOURCE_TYPE,
    targetDate,
    latestDataDate: latest,
    totalRows: total,
    storeCount: stores.length,
    status,
    planned,
    sendSuccess,
    sendFailed,
    testSend,
    send,
  };
  console.log(`SUMMARY_JSON=${JSON.stringify(summary)}`);
  if (sendFailed > 0) process.exit(1);
}

main().catch((e) => {
  console.error(`[${TASK_NAME}] 运行失败:`, e instanceof Error ? e.message : String(e));
  process.exit(1);
});
