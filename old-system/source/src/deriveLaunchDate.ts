/**
 * deriveLaunchDate.ts
 *
 * 推导 dim_product.launch_date 的每日后端任务。
 *
 * 数据流：
 *   DIM/FACT -> dim_product.launch_date
 *
 * 口径 v2：
 *   - 只处理 platform='walmart' 且 launch_date IS NULL 的商品。
 *   - CS 测品（MSKU 以 CS 开头）：与 CS测品分析 Beta 同源，
 *     fact_ads_product_daily 中 ad_spend > 0 的最早 stat_date。
 *     广告表按 platform + store_id + item_id 关联，不带 msku。
 *   - 非 CS 常规产品：fact_inventory_daily 中 wfs_available_stock > 0
 *     的最早 snapshot_date，库存表按 platform + store_id + item_id + msku 关联。
 *   - 推导不出的保持 NULL，不做兜底。
 *   - 已有 launch_date 永不修改。
 *
 * 用法：
 *   npm run derive:launch-date -- --dry-run
 *   npm run derive:launch-date -- --confirm-write   （--execute 为等价别名）
 *
 * 2026-07-11 日期格式修复（批A）：
 *   根因：mysql2 默认将 DATE 列返回为 JS Date 对象，原 formatDateOnly 用
 *   String(value).slice(0,10) 得到 "Wed Jul 08"，UPDATE 写入非法日期 →
 *   MySQL 拒绝 → 事务整体回滚 → 任务连续失败。
 *   修复：① 连接加 dateStrings:true（DATE/DATETIME 一律返回字符串，根治且
 *   规避时区偏移）② formatDateOnly 健壮化（Date对象/ISO/带时分秒/斜杠格式
 *   均归一为 YYYY-MM-DD，非法输入返回空串）③ 写库前正则校验
 *   ^\d{4}-\d{2}-\d{2}$，非法日期跳过并计数告警，绝不写入错误日期、
 *   绝不覆盖已有 launch_date ④ 摘要新增 invalidDateCount。
 */

import "dotenv/config";
import * as fs from "fs";
import * as path from "path";
import * as mysql from "mysql2/promise";

const PLATFORM = "walmart";
const CONFIRM_WRITE = process.argv.includes("--confirm-write") || process.argv.includes("--execute");
const DRY_RUN = process.argv.includes("--dry-run") || !CONFIRM_WRITE;
const SAMPLE_LIMIT = 10;

interface CandidateRow extends mysql.RowDataPacket {
  platform: string;
  store_id: string;
  item_id: string;
  msku: string;
  derived_launch_date: string;
  derive_source: "CS_AD_FIRST_SPEND" | "WFS_FIRST_STOCK";
}

interface NullCountRow extends mysql.RowDataPacket {
  null_count: number;
}

interface UpdateResult {
  matchedCandidates: number;
  updated: number;
  skippedAlreadyFilled: number;
}

function dbConfig() {
  return {
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
    // 批A修复：DATE/DATETIME 以字符串返回，杜绝 JS Date 隐式转换与时区偏移
    dateStrings: true as const,
  };
}

function isCs(msku: string): boolean {
  return String(msku ?? "").trim().toUpperCase().startsWith("CS");
}

const DATE_ONLY_RE = /^\d{4}-\d{2}-\d{2}$/;

function formatDateOnly(value: unknown): string {
  if (value == null || value === "") return "";
  // Date 对象：按本地时区取年月日（dateStrings:true 后通常不会走到这里，兜底保留）
  if (value instanceof Date) {
    if (isNaN(value.getTime())) return "";
    const y = value.getFullYear();
    const m = String(value.getMonth() + 1).padStart(2, "0");
    const d = String(value.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }
  const s = String(value).trim();
  // YYYY-MM-DD / YYYY/MM/DD，可带时分秒或 ISO 后缀
  const m = s.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})/);
  if (m) {
    return `${m[1]}-${m[2].padStart(2, "0")}-${m[3].padStart(2, "0")}`;
  }
  return ""; // 非法格式：返回空串，由调用方计数告警，不写库
}

function shanghaiDateStamp(): string {
  const d = new Date(Date.now() + 8 * 60 * 60 * 1000);
  return d.toISOString().slice(0, 10).replace(/-/g, "");
}

function shanghaiTimeStamp(): string {
  const d = new Date(Date.now() + 8 * 60 * 60 * 1000);
  return d.toISOString().slice(0, 19).replace(/[-:T]/g, "");
}

function csvEscape(value: unknown): string {
  const text = String(value ?? "");
  if (/[",\n\r]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function reportPath(): string {
  const dir = path.resolve(process.cwd(), "reports");
  const base = path.join(dir, `derive_launch_date_${shanghaiDateStamp()}.csv`);
  if (!fs.existsSync(base)) return base;
  return path.join(dir, `derive_launch_date_${shanghaiTimeStamp()}.csv`);
}

function writeCandidateReport(rows: CandidateRow[]): string {
  const filePath = reportPath();
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const header = [
    "platform",
    "store_id",
    "item_id",
    "msku",
    "derived_launch_date",
    "derive_source",
  ];
  const lines = [
    header.join(","),
    ...rows.map((row) => [
      row.platform,
      row.store_id,
      row.item_id,
      row.msku,
      formatDateOnly(row.derived_launch_date),
      row.derive_source,
    ].map(csvEscape).join(",")),
  ];
  fs.writeFileSync(filePath, `${lines.join("\n")}\n`, "utf8");
  return filePath;
}

async function countCurrentNulls(db: mysql.Connection): Promise<number> {
  const [rows] = await db.query<NullCountRow[]>(
    `SELECT COUNT(*) AS null_count
     FROM dim_product
     WHERE platform = ? AND launch_date IS NULL`,
    [PLATFORM],
  );
  return Number(rows[0]?.null_count ?? 0);
}

async function loadCandidates(db: mysql.Connection): Promise<CandidateRow[]> {
  const [rows] = await db.query<CandidateRow[]>(
    `
    SELECT
      d.platform,
      d.store_id,
      d.item_id,
      d.msku,
      CASE
        WHEN UPPER(d.msku) LIKE 'CS%' THEN cs.first_ad_date
        ELSE wfs.first_wfs_stock_date
      END AS derived_launch_date,
      CASE
        WHEN UPPER(d.msku) LIKE 'CS%' THEN 'CS_AD_FIRST_SPEND'
        ELSE 'WFS_FIRST_STOCK'
      END AS derive_source
    FROM dim_product d
    LEFT JOIN (
      SELECT platform, store_id, item_id, MIN(stat_date) AS first_ad_date
      FROM fact_ads_product_daily
      WHERE platform = ? AND ad_spend > 0
      GROUP BY platform, store_id, item_id
    ) cs
      ON cs.platform = d.platform
     AND cs.store_id = d.store_id
     AND cs.item_id = d.item_id
    LEFT JOIN (
      SELECT platform, store_id, item_id, msku, MIN(snapshot_date) AS first_wfs_stock_date
      FROM fact_inventory_daily
      WHERE platform = ? AND wfs_available_stock > 0
      GROUP BY platform, store_id, item_id, msku
    ) wfs
      ON wfs.platform = d.platform
     AND wfs.store_id = d.store_id
     AND wfs.item_id = d.item_id
     AND wfs.msku = d.msku
    WHERE d.platform = ?
      AND d.launch_date IS NULL
      AND (
        (UPPER(d.msku) LIKE 'CS%' AND cs.first_ad_date IS NOT NULL)
        OR
        (UPPER(d.msku) NOT LIKE 'CS%' AND wfs.first_wfs_stock_date IS NOT NULL)
      )
    ORDER BY derived_launch_date ASC, d.store_id ASC, d.item_id ASC, d.msku ASC
    `,
    [PLATFORM, PLATFORM, PLATFORM],
  );

  return rows.map((row) => ({
    ...row,
    derived_launch_date: formatDateOnly(row.derived_launch_date),
    derive_source: row.derive_source,
  }));
}

/** 批A修复：候选按日期合法性分流，非法日期只告警不写库 */
function splitByDateValidity(rows: CandidateRow[]): { valid: CandidateRow[]; invalid: CandidateRow[] } {
  const valid: CandidateRow[] = [];
  const invalid: CandidateRow[] = [];
  for (const row of rows) {
    if (DATE_ONLY_RE.test(row.derived_launch_date)) valid.push(row);
    else invalid.push(row);
  }
  return { valid, invalid };
}

async function updateLaunchDates(db: mysql.Connection, rows: CandidateRow[]): Promise<UpdateResult> {
  let updated = 0;
  let skippedAlreadyFilled = 0;

  await db.beginTransaction();
  try {
    for (const row of rows) {
      // 批A修复：写库前最终校验，非法日期绝不入库（双保险，正常应已被 splitByDateValidity 拦截）
      if (!DATE_ONLY_RE.test(formatDateOnly(row.derived_launch_date))) {
        skippedAlreadyFilled += 0; // 不计入既有指标，防御性跳过
        continue;
      }
      const [result] = await db.query<mysql.ResultSetHeader>(
        `UPDATE dim_product
         SET launch_date = ?
         WHERE platform = ?
           AND store_id = ?
           AND item_id = ?
           AND msku = ?
           AND launch_date IS NULL`,
        [
          formatDateOnly(row.derived_launch_date),
          row.platform,
          row.store_id,
          row.item_id,
          row.msku,
        ],
      );

      if (result.affectedRows === 1) updated += 1;
      else skippedAlreadyFilled += 1;
    }
    await db.commit();
  } catch (err) {
    await db.rollback();
    throw err;
  }

  return { matchedCandidates: rows.length, updated, skippedAlreadyFilled };
}

function printSummary(currentNulls: number, candidates: CandidateRow[]): void {
  const csCount = candidates.filter((row) => isCs(row.msku)).length;
  const regularCount = candidates.length - csCount;
  const stillNull = currentNulls - candidates.length;

  console.log("=".repeat(72));
  console.log("deriveLaunchDate");
  console.log(`模式: ${DRY_RUN ? "dry-run" : "confirm-write"}`);
  console.log("口径: launch_date v2 / CS ad_spend > 0 / WFS first stock");
  console.log("=".repeat(72));
  console.log(`当前 Walmart launch_date IS NULL: ${currentNulls}`);
  console.log(`预计写入总数: ${candidates.length}`);
  console.log(`  CS测品: ${csCount}`);
  console.log(`  常规产品: ${regularCount}`);
  console.log(`推导后仍为 NULL: ${Math.max(stillNull, 0)}`);
  console.log("");
  console.log(`样例 ${Math.min(SAMPLE_LIMIT, candidates.length)} 条:`);
  for (const row of candidates.slice(0, SAMPLE_LIMIT)) {
    console.log(
      [
        `  ${row.derive_source}`,
        row.store_id,
        row.item_id,
        row.msku,
        formatDateOnly(row.derived_launch_date),
      ].join(" | "),
    );
  }
}

async function run() {
  const db = await mysql.createConnection(dbConfig());
  try {
    const currentNulls = await countCurrentNulls(db);
    const all = await loadCandidates(db);
    const { valid: candidates, invalid } = splitByDateValidity(all);
    printSummary(currentNulls, candidates);
    console.log(`非法日期候选(仅告警不写库): ${invalid.length}`);
    if (invalid.length) {
      for (const row of invalid.slice(0, SAMPLE_LIMIT)) {
        console.log(`  [非法日期] ${row.derive_source} | ${row.store_id} | ${row.item_id} | ${row.msku} | 原值="${row.derived_launch_date}"`);
      }
    }

    if (DRY_RUN) {
      console.log("");
      console.log("dry-run 不写库、不导出 CSV。加 --confirm-write（或 --execute）后会先导出白名单 CSV，再写库。");
      return;
    }

    const filePath = writeCandidateReport(candidates);
    console.log("");
    console.log(`已导出写入白名单: ${filePath}`);

    const result = await updateLaunchDates(db, candidates);
    console.log(`扫描候选总数: ${all.length}`);
    console.log(`合法候选数: ${result.matchedCandidates}`);
    console.log(`非法日期跳过: ${invalid.length}`);
    console.log(`实际写入: ${result.updated}`);
    console.log(`写入前已被其他流程补值而跳过: ${result.skippedAlreadyFilled}`);
  } finally {
    await db.end();
  }
}

run().catch((err) => {
  console.error("deriveLaunchDate failed:", err);
  process.exit(1);
});
