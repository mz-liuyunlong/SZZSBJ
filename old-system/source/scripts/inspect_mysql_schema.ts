/**
 * inspect_mysql_schema.ts
 *
 * 检查现有 MySQL 数据库 walmart_ai_data 的表结构，
 * 输出评估报告并打印下一步建议。
 *
 * 执行方式（dry-run，不修改任何数据）：
 *   npx ts-node scripts/inspect_mysql_schema.ts
 *
 * 环境变量（从 .env 读取）：
 *   DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME
 */

import "dotenv/config";
import * as fs from "fs";
import * as path from "path";
import * as mysql from "mysql2/promise";

// ── 配置（全部从 .env 读取，不硬编码） ──────────────────────────────────────

const DB_CONFIG = {
  host:     process.env.DB_HOST     ?? "localhost",
  port:     Number(process.env.DB_PORT ?? 3306),
  user:     process.env.DB_USER     ?? "",
  password: process.env.DB_PASSWORD ?? "",
  database: process.env.DB_NAME     ?? "walmart_ai_data",
};

// ── 新架构表（用于对比现有表） ────────────────────────────────────────────────

const NEW_TABLES = new Set([
  "raw_lingxing_api",
  "raw_feishu_table",
  "raw_frontend_upload",
  "raw_walmart_ads_csv",
  "dim_store",
  "dim_product",
  "dim_owner",
  "dim_keyword",
  "fact_sales_daily",
  "fact_inventory_daily",
  "fact_ads_product_daily",
  "fact_ads_keyword_daily",
  "fact_profit_daily",
  "fact_purchase_daily",
  "biz_event",
  "ai_analysis_result",
  "sync_task_log",
  "data_reconcile_log",
  "schema_change_log",
]);

// ── 表命名规范前缀 ─────────────────────────────────────────────────────────

const VALID_PREFIXES = ["raw_", "dim_", "fact_", "biz_", "ai_", "sync_", "data_", "schema_"];

// ── 类型定义 ───────────────────────────────────────────────────────────────

interface TableInfo {
  name: string;
  rowCount: number;
  engine: string;
  createTime: string;
  columns: ColumnInfo[];
}

interface ColumnInfo {
  name: string;
  type: string;
  nullable: string;
  default: string | null;
  comment: string;
}

type TableCategory = "keep" | "migrate" | "deprecate" | "unknown";

interface TableAssessment {
  name: string;
  category: TableCategory;
  reason: string;
  rowCount: number;
  columns: ColumnInfo[];
}

// ── 主逻辑 ─────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  console.log("═".repeat(60));
  console.log("  MySQL 数据库结构检查工具");
  console.log("  数据库:", DB_CONFIG.database, "@ ", DB_CONFIG.host);
  console.log("═".repeat(60));
  console.log();

  // 1. 连接数据库
  let conn: mysql.Connection;
  try {
    conn = await mysql.createConnection(DB_CONFIG);
    console.log("✅ 数据库连接成功");
    console.log();
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("❌ 数据库连接失败:", msg);
    console.error();
    console.error("请检查 .env 中的以下变量是否正确：");
    console.error("  DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME");
    process.exit(1);
  }

  try {
    // 2. 获取所有现有表
    const [tableRows] = await conn.query<mysql.RowDataPacket[]>(
      `SELECT TABLE_NAME, TABLE_ROWS, ENGINE,
              DATE_FORMAT(CREATE_TIME, '%Y-%m-%d %H:%i') AS CREATE_TIME
       FROM information_schema.TABLES
       WHERE TABLE_SCHEMA = ?
       ORDER BY TABLE_NAME`,
      [DB_CONFIG.database],
    );

    if (tableRows.length === 0) {
      console.log("⚠️  数据库中暂无表，将直接执行建表脚本");
      await generateEmptyReport();
      return;
    }

    console.log(`📋 发现 ${tableRows.length} 张表，开始评估...\n`);

    // 3. 获取每张表的列信息 + 真实行数
    const tables: TableInfo[] = [];
    for (const row of tableRows) {
      const tableName = row.TABLE_NAME as string;

      const [colRows] = await conn.query<mysql.RowDataPacket[]>(
        `SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_COMMENT
         FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
         ORDER BY ORDINAL_POSITION`,
        [DB_CONFIG.database, tableName],
      );

      // 真实行数（COUNT）
      let realRowCount = 0;
      try {
        const [countRows] = await conn.query<mysql.RowDataPacket[]>(
          `SELECT COUNT(*) AS cnt FROM \`${tableName}\``,
        );
        realRowCount = Number(countRows[0]?.cnt ?? 0);
      } catch {
        realRowCount = -1; // 无法读取
      }

      tables.push({
        name:       tableName,
        rowCount:   realRowCount,
        engine:     row.ENGINE as string ?? "InnoDB",
        createTime: row.CREATE_TIME as string ?? "",
        columns: colRows.map((c) => ({
          name:     c.COLUMN_NAME as string,
          type:     c.COLUMN_TYPE as string,
          nullable: c.IS_NULLABLE as string,
          default:  c.COLUMN_DEFAULT as string | null,
          comment:  c.COLUMN_COMMENT as string ?? "",
        })),
      });
    }

    // 4. 评估每张表
    const assessments: TableAssessment[] = tables.map((t) => assess(t));

    // 5. 打印评估结果
    printAssessment(assessments);

    // 6. 输出报告文件
    const reportMd = buildReportMarkdown(assessments);
    const reportPath = path.join(process.cwd(), "reports", "mysql_schema_assessment.md");
    fs.mkdirSync(path.dirname(reportPath), { recursive: true });
    fs.writeFileSync(reportPath, reportMd, "utf8");
    console.log(`\n📄 评估报告已写入: reports/mysql_schema_assessment.md`);

    // 7. 下一步建议
    printNextSteps(assessments);

  } finally {
    await conn.end();
  }
}

// ── 评估单张表 ─────────────────────────────────────────────────────────────

function assess(table: TableInfo): TableAssessment {
  const name = table.name;

  // 已在新架构中 → 直接保留
  if (NEW_TABLES.has(name)) {
    return { name, category: "keep", reason: "已在新架构表清单中，符合命名规范", rowCount: table.rowCount, columns: table.columns };
  }

  // 命名符合新前缀但不在新表清单 → 可能需要迁移
  const hasValidPrefix = VALID_PREFIXES.some((p) => name.startsWith(p));
  if (hasValidPrefix) {
    return { name, category: "migrate", reason: "命名前缀符合规范，但不在新架构表清单，需人工确认业务含义", rowCount: table.rowCount, columns: table.columns };
  }

  // 无数据
  if (table.rowCount === 0) {
    return { name, category: "deprecate", reason: "表中无数据，且命名不符合新架构规范", rowCount: 0, columns: table.columns };
  }

  // 有数据但命名不规范 → 不确定
  return { name, category: "unknown", reason: "有数据但命名不符合新架构规范，需人工确认业务含义后再决定", rowCount: table.rowCount, columns: table.columns };
}

// ── 打印评估结果 ───────────────────────────────────────────────────────────

const ICONS: Record<TableCategory, string> = {
  keep:      "✅",
  migrate:   "🔄",
  deprecate: "❌",
  unknown:   "❓",
};

const LABELS: Record<TableCategory, string> = {
  keep:      "可保留",
  migrate:   "可迁移",
  deprecate: "可废弃",
  unknown:   "不确定",
};

function printAssessment(assessments: TableAssessment[]): void {
  const groups: Record<TableCategory, TableAssessment[]> = { keep: [], migrate: [], deprecate: [], unknown: [] };
  for (const a of assessments) groups[a.category].push(a);

  for (const cat of ["keep", "migrate", "unknown", "deprecate"] as TableCategory[]) {
    const list = groups[cat];
    if (list.length === 0) continue;
    console.log(`\n${ICONS[cat]} ${LABELS[cat]}（${list.length} 张）`);
    console.log("─".repeat(50));
    for (const a of list) {
      const rowStr = a.rowCount < 0 ? "无法读取" : `${a.rowCount.toLocaleString()} 行`;
      console.log(`  ${a.name.padEnd(35)} ${rowStr}`);
      console.log(`  → ${a.reason}`);
    }
  }
}

function printNextSteps(assessments: TableAssessment[]): void {
  const deprecate = assessments.filter((a) => a.category === "deprecate");
  const unknown   = assessments.filter((a) => a.category === "unknown");

  console.log("\n" + "═".repeat(60));
  console.log("📋 下一步建议");
  console.log("═".repeat(60));
  console.log("1. 执行建表脚本（安全，IF NOT EXISTS 不影响现有表）:");
  console.log("   mysql -u<user> -p walmart_ai_data < sql/001_create_data_warehouse_tables.sql");
  console.log("2. 执行索引脚本:");
  console.log("   mysql -u<user> -p walmart_ai_data < sql/002_add_indexes.sql");

  if (deprecate.length > 0) {
    console.log(`\n3. ⚠️  以下 ${deprecate.length} 张表建议废弃，请人工确认后再执行 DROP：`);
    for (const t of deprecate) console.log(`   - ${t.name}`);
  }

  if (unknown.length > 0) {
    console.log(`\n4. ❓ 以下 ${unknown.length} 张表业务含义不明，需人工确认：`);
    for (const t of unknown) console.log(`   - ${t.name}（${t.rowCount.toLocaleString()} 行）`);
  }

  console.log("\n⚠️  所有 DROP TABLE 操作必须经人工确认，本脚本不会自动执行任何删除。");
  console.log();
}

// ── 生成 Markdown 报告 ────────────────────────────────────────────────────

function buildReportMarkdown(assessments: TableAssessment[]): string {
  const now = new Date().toISOString().slice(0, 16).replace("T", " ");
  const groups: Record<TableCategory, TableAssessment[]> = { keep: [], migrate: [], deprecate: [], unknown: [] };
  for (const a of assessments) groups[a.category].push(a);

  const lines: string[] = [
    `# MySQL 表结构评估报告`,
    ``,
    `> 生成时间：${now}`,
    `> 数据库：${DB_CONFIG.database}`,
    `> 模式：**dry-run（只读，未修改任何数据）**`,
    ``,
    `---`,
    ``,
    `## 汇总`,
    ``,
    `| 分类 | 数量 |`,
    `|------|------|`,
    ...Object.entries(groups).map(([cat, list]) =>
      `| ${ICONS[cat as TableCategory]} ${LABELS[cat as TableCategory]} | ${list.length} |`
    ),
    ``,
  ];

  for (const cat of ["keep", "migrate", "unknown", "deprecate"] as TableCategory[]) {
    const list = groups[cat];
    if (list.length === 0) continue;

    lines.push(`## ${ICONS[cat]} ${LABELS[cat]}（${list.length} 张）`, ``);

    for (const a of list) {
      const rowStr = a.rowCount < 0 ? "无法读取" : `${a.rowCount.toLocaleString()} 行`;
      lines.push(
        `### \`${a.name}\``,
        ``,
        `- **实际行数**：${rowStr}`,
        `- **评估结论**：${a.reason}`,
        ``,
        `| 字段名 | 类型 | 可空 | 备注 |`,
        `|--------|------|------|------|`,
        ...a.columns.map((c) =>
          `| ${c.name} | ${c.type} | ${c.nullable} | ${c.comment || "-"} |`
        ),
        ``,
      );
    }
  }

  lines.push(
    `---`,
    ``,
    `## 下一步操作`,
    ``,
    `1. 执行 \`sql/001_create_data_warehouse_tables.sql\` 创建新表`,
    `2. 执行 \`sql/002_add_indexes.sql\` 添加索引`,
    `3. 人工确认 ❓ 不确定表的业务含义`,
    `4. 人工确认 ❌ 可废弃表后，再手动执行 DROP`,
    ``,
    `> ⚠️ 所有 DROP TABLE 必须人工确认，不允许脚本自动执行。`,
  );

  return lines.join("\n");
}

async function generateEmptyReport(): Promise<void> {
  const now = new Date().toISOString().slice(0, 16).replace("T", " ");
  const content = [
    `# MySQL 表结构评估报告`,
    ``,
    `> 生成时间：${now}`,
    `> 数据库：${DB_CONFIG.database}`,
    ``,
    `## 结论`,
    ``,
    `数据库中暂无表，可直接执行建表脚本：`,
    ``,
    `\`\`\`bash`,
    `mysql -u<user> -p walmart_ai_data < sql/001_create_data_warehouse_tables.sql`,
    `mysql -u<user> -p walmart_ai_data < sql/002_add_indexes.sql`,
    `\`\`\``,
  ].join("\n");

  const reportPath = path.join(process.cwd(), "reports", "mysql_schema_assessment.md");
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.writeFileSync(reportPath, content, "utf8");
  console.log("📄 报告已写入: reports/mysql_schema_assessment.md");
}

// ── 入口 ───────────────────────────────────────────────────────────────────

main().catch((e: unknown) => {
  console.error("脚本异常:", e instanceof Error ? e.message : String(e));
  process.exit(1);
});
