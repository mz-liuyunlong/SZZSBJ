/**
 * syncFeishuItemOwnerToMysql.ts
 *
 * ⚠️ V1.2 硬锁定：本脚本已降级为 RAW-only 历史镜像脚本。
 *
 * 背景：
 *   飞书 <REDACTED_FEISHU_SHEET_ID>（ItemID负责人表）已停止作为日常维护入口。负责人、WFS配送费（$）、
 *   产品状态统一通过后台「产品管理」Tab 维护（写 dim_product / dim_product_owner /
 *   dim_product_cost_config）。本脚本如果继续写这几张结构化表，手工执行时会用飞书表的
 *   旧数据把产品管理页面刚维护好的数据覆盖回去，因此从 V1.2 起硬性关闭这条写入路径。
 *
 * 现在这个脚本只做：
 *   1. 读取飞书 <REDACTED_FEISHU_SHEET_ID>
 *   2. 写入 raw_feishu_table（RAW 层历史镜像，用于排查、对账、审计）
 *   3. 输出同步摘要
 *
 * 本脚本【不会再写】：
 *   - dim_product
 *   - dim_product_owner
 *   - dim_product_cost_config
 *   - dim_product_identity
 *   - dim_owner
 * 尤其不会覆盖 dim_product.owner / dim_product.launch_date /
 * dim_product_owner 当前 active 负责人 / dim_product_cost_config.delivery_fee ——
 * 这些字段现在只能通过产品管理页面维护。
 *
 * 下面的 writeStructuredLayersDEPRECATED() 函数保留了 V1.1 及之前版本对
 * dim_product_identity / dim_owner / dim_product / dim_product_owner /
 * dim_product_cost_config 的写入逻辑，仅作代码可读性/历史参考，main() 不再调用它。
 * 如果未来确实需要恢复"飞书 → 结构化表"的写入能力，必须另开任务评审，不要绕过这里
 * 直接调用这个函数或复制其中的 SQL 去别处使用。本次不提供任何一键恢复覆盖写入的参数。
 *
 * 用法:
 *   npx ts-node src/syncFeishuItemOwnerToMysql.ts                # dry-run（默认，不写 MySQL）
 *   npx ts-node src/syncFeishuItemOwnerToMysql.ts --confirm-write # 正式写入 raw_feishu_table（仅RAW）
 */

import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { FeishuSheetWriter } from "./feishuSheetWriter";
import type { CellValue } from "./feishuSheetWriter";
import currentReport from "../config/currentReportFieldMapping.json";

// ── 配置 ──────────────────────────────────────────────────────────────────────

const SPREADSHEET_TOKEN = currentReport.spreadsheetToken;
const SHEET_ID          = (currentReport.sheets as Record<string, string>)["ItemID负责人"];
const SHEET_NAME        = "ItemID负责人";
const DATA_START_ROW    = 2;      // 第1行是表头，第2行起是数据
const MAX_READ_ROWS     = 3000;
const SOURCE_SYSTEM     = "feishu_item_owner";
const TODAY             = new Date().toISOString().slice(0, 10);

const CONFIRM_WRITE = process.argv.includes("--confirm-write");
const DRY_RUN       = !CONFIRM_WRITE;

// ── 列名别名映射（自动识别表头，不写死列号）────────────────────────────────────
// 仍然用于识别飞书表头、写入 raw_feishu_table 的字段解析预览；不再用于结构化写入。

const COL_ALIASES: Record<string, string[]> = {
  sku:          ["SKU", "sku"],
  msku:         ["MSKU", "msku"],
  item_id:      ["商品ID", "ItemID", "item_id", "商品id", "ItemId", "商品 ID"],
  item_name:    ["中文名称", "商品名称", "产品名称", "item_name", "product_name"],
  owner:        ["负责人", "owner", "Owner", "负责人姓名"],
  delivery_fee: ["WFS配送费（$）", "WFS配送费", "配送费（$）", "配送费", "delivery_fee", "shipping_fee"],
  store_name:   ["店铺", "店铺名称", "store_name", "Store"],
  launch_date:  ["上架时间", "上架日期", "launch_date", "Launch Date", "上线时间"],
  platform:     ["平台", "platform", "Platform"],
  status:       ["状态", "status"],
  remark:       ["备注", "remark", "备注信息"],
};

// ── 工具函数 ──────────────────────────────────────────────────────────────────

function toStr(v: unknown): string {
  return String(v ?? "").trim();
}

function md5(s: string): string {
  return crypto.createHash("md5").update(s).digest("hex").slice(0, 64);
}

function dbConfig() {
  return {
    host:     process.env.DB_HOST     ?? "127.0.0.1",
    port:     Number(process.env.DB_PORT ?? 3306),
    user:     process.env.DB_USER     ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME     ?? "walmart_ai_data",
  };
}

// ── 表头解析 ──────────────────────────────────────────────────────────────────

function buildColIndex(headerRow: CellValue[]): Record<string, number> {
  const idx: Record<string, number> = {};
  for (const [field, aliases] of Object.entries(COL_ALIASES)) {
    for (let i = 0; i < headerRow.length; i++) {
      const cell = toStr(headerRow[i]).toLowerCase();
      if (aliases.some((a) => a.toLowerCase() === cell)) {
        idx[field] = i;
        break;
      }
    }
  }
  return idx;
}

function getCol(row: CellValue[], idx: Record<string, number>, field: string): string {
  const i = idx[field];
  return i !== undefined ? toStr(row[i]) : "";
}

// ── 统计计数器（V1.2：只统计 RAW 层） ─────────────────────────────────────────

interface Counter {
  raw_insert: number;
  raw_skip: number;
  skipped_empty: number;
}

function emptyCounter(): Counter {
  return { raw_insert: 0, raw_skip: 0, skipped_empty: 0 };
}

// ── 主流程（V1.2：RAW-only） ──────────────────────────────────────────────────

async function main(): Promise<void> {
  console.log("═".repeat(60));
  console.log(`  飞书 ItemID负责人 → MySQL  [${DRY_RUN ? "DRY-RUN（预览）" : "CONFIRM-WRITE（写入）"}]`);
  console.log("  ⚠️  当前脚本已降级为 RAW-only 模式（V1.2）");
  console.log("  只写 raw_feishu_table，不会写 dim_product / dim_product_owner / dim_product_cost_config");
  console.log("  不会覆盖产品管理页面维护的负责人、WFS配送费、产品状态");
  console.log("═".repeat(60));

  // ── 步骤1: 读取飞书 ─────────────────────────────────────────────────────────
  console.log(`\n📖 读取飞书表格: ${SHEET_NAME} (${SHEET_ID})`);
  const reader  = new FeishuSheetWriter();
  const allRows = reader.readValues({
    spreadsheetToken: SPREADSHEET_TOKEN,
    sheetId:  SHEET_ID,
    range:    `A1:Z${MAX_READ_ROWS}`,
  });

  if (!allRows.length) throw new Error("飞书表格为空或读取失败");

  // ── 步骤2: 解析表头（仅用于预览展示，不再驱动结构化写入）────────────────────
  const headerRow = allRows[0];
  const colIdx    = buildColIndex(headerRow);

  const detectedCols = Object.entries(colIdx)
    .map(([k, v]) => `${k}→第${v + 1}列`)
    .join("  ");
  console.log(`  识别表头: ${detectedCols || "（未识别任何列）"}`);

  const dataRows = allRows.slice(DATA_START_ROW - 1);
  console.log(`  数据行: ${dataRows.length}（共读取 ${allRows.length} 行含表头）`);

  // ── dry-run 预览 ────────────────────────────────────────────────────────────
  if (DRY_RUN) {
    console.log("\n⚡ dry-run 模式：预览前5行（不写入 MySQL，仅展示 RAW 将解析到的字段）\n");
    for (const row of dataRows.slice(0, 5)) {
      console.log({
        sku:          getCol(row, colIdx, "sku"),
        msku:         getCol(row, colIdx, "msku"),
        item_id:      getCol(row, colIdx, "item_id"),
        item_name:    getCol(row, colIdx, "item_name"),
        owner:        getCol(row, colIdx, "owner"),
        delivery_fee: getCol(row, colIdx, "delivery_fee"),
        store_name:   getCol(row, colIdx, "store_name"),
        launch_date:  getCol(row, colIdx, "launch_date"),
      });
    }
    console.log(`\n加 --confirm-write 参数正式写入 raw_feishu_table（仅 RAW，不写结构化表）。`);
    return;
  }

  // ── 步骤3: 连接 MySQL ───────────────────────────────────────────────────────
  const db  = await mysql.createConnection(dbConfig());
  const cnt = emptyCounter();

  try {
    // ── 步骤4: 逐行只写 raw_feishu_table ────────────────────────────────────────
    for (let i = 0; i < dataRows.length; i++) {
      const row      = dataRows[i];
      const rowIndex = i + DATA_START_ROW;

      const sku       = getCol(row, colIdx, "sku");
      const msku      = getCol(row, colIdx, "msku");
      const item_id   = getCol(row, colIdx, "item_id");
      const item_name = getCol(row, colIdx, "item_name");
      const owner     = getCol(row, colIdx, "owner");

      // 跳过全空行
      if (!sku && !msku && !item_id && !owner && !item_name) {
        cnt.skipped_empty++;
        continue;
      }

      const rowJson = JSON.stringify(
        Object.fromEntries(
          headerRow.map((h, ci) => [toStr(h) || `col_${ci}`, row[ci] ?? null]),
        ),
      );
      const rawHash = md5(rowJson);

      const [[{ existRaw }]] = await db.query<mysql.RowDataPacket[]>(
        "SELECT COUNT(*) AS existRaw FROM raw_feishu_table WHERE sheet_id=? AND row_index=? AND raw_hash=?",
        [SHEET_ID, rowIndex, rawHash],
      );

      if (Number(existRaw) === 0) {
        await db.query(
          `INSERT INTO raw_feishu_table
             (spreadsheet_token, sheet_id, sheet_name, row_index, row_json, data_date, raw_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?)`,
          [SPREADSHEET_TOKEN, SHEET_ID, SHEET_NAME, rowIndex, rowJson, TODAY, rawHash],
        );
        cnt.raw_insert++;
      } else {
        cnt.raw_skip++;
      }

      // ⚠️ V1.2 起，dim_product_identity / dim_owner / dim_product / dim_product_owner /
      // dim_product_cost_config 的写入已整体停用，见文件顶部说明和
      // writeStructuredLayersDEPRECATED()（未被调用，仅供历史参考）。
    }

    // ── 步骤5: 写 sync_task_log（target_table 只剩 raw_feishu_table）───────────
    await db.query(
      `INSERT INTO sync_task_log
         (task_name, source_system, target_table, status,
          inserted_count, updated_count, failed_count, finished_at, error_message)
       VALUES (?, 'feishu', 'raw_feishu_table', 'success', ?, 0, 0, NOW(), NULL)`,
      ["feishu_item_owner_sync_raw_only", cnt.raw_insert],
    );

    // ── 步骤6: 输出统计 ───────────────────────────────────────────────────────
    console.log("\n" + "═".repeat(60));
    console.log("✅ 同步完成（RAW-only 模式）");
    console.log("═".repeat(60));
    console.log(`飞书总行数:          ${dataRows.length}`);
    console.log(`  全空行（跳过）:    ${cnt.skipped_empty}`);
    console.log(`─────────────────────────────────────────`);
    console.log(`raw_feishu_table:    新增 ${cnt.raw_insert}  |  跳过(重复) ${cnt.raw_skip}`);
    console.log(`─────────────────────────────────────────`);
    console.log(`dim_product / dim_product_owner / dim_product_cost_config / dim_product_identity / dim_owner: 本次未写入（RAW-only 硬锁定）`);
    console.log("═".repeat(60));
  } finally {
    await db.end();
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 以下代码【已停用，main() 不再调用】，仅保留作为历史参考/审计用途。
// V1.1 及之前版本靠这段逻辑把飞书 <REDACTED_FEISHU_SHEET_ID> 同步进 dim_product_identity / dim_owner /
// dim_product / dim_product_owner / dim_product_cost_config。V1.2 起该数据流已停止，
// 负责人 / WFS配送费 / 产品状态改由产品管理页面维护。
// 不要重新在 main() 里调用本函数，也不要复制其中的 SQL 到其他地方使用。
// 如确实需要恢复，必须另开任务评审（数据覆盖风险、唯一键风险都需要重新确认）。
// ═══════════════════════════════════════════════════════════════════════════

/* eslint-disable @typescript-eslint/no-unused-vars */
async function writeStructuredLayersDEPRECATED(
  db: mysql.Connection,
  params: {
    platform: string; storeId: string; resolvedStoreName: string;
    item_id: string; msku: string; sku: string; item_name: string; owner: string;
    launch_date: string | null; delivery_fee: number | null;
    status: string; sourceRawId: string; extraBase: string;
  },
): Promise<void> {
  const {
    platform, storeId, resolvedStoreName, item_id, msku, sku,
    item_name, owner, launch_date, delivery_fee, status, sourceRawId, extraBase,
  } = params;

  // dim_product_identity
  await db.query(
    `INSERT INTO dim_product_identity
       (platform, store_id, store_name, item_id, msku, sku,
        source_system, source_raw_id, status, extra_json)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON DUPLICATE KEY UPDATE
       sku=VALUES(sku), store_id=VALUES(store_id),
       source_raw_id=VALUES(source_raw_id), status=VALUES(status),
       extra_json=VALUES(extra_json), updated_at=NOW()`,
    [platform, storeId, resolvedStoreName, item_id, msku, sku,
     SOURCE_SYSTEM, sourceRawId, status, extraBase],
  );

  // dim_owner
  const [[{ existOwner }]] = await db.query<mysql.RowDataPacket[]>(
    "SELECT COUNT(*) AS existOwner FROM dim_owner WHERE owner_name=?",
    [owner],
  );
  if (Number(existOwner) === 0) {
    await db.query("INSERT INTO dim_owner (owner_name, status) VALUES (?, 'active')", [owner]);
  }

  // dim_product
  if (storeId) {
    await db.query(
      `INSERT INTO dim_product
         (platform, store_id, store_name, item_id, msku, sku,
          item_name, owner, launch_date, source_system, extra_json)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON DUPLICATE KEY UPDATE
         item_name=VALUES(item_name), owner=VALUES(owner), sku=VALUES(sku),
         launch_date=COALESCE(VALUES(launch_date), launch_date),
         store_name=VALUES(store_name), extra_json=VALUES(extra_json),
         updated_at=NOW()`,
      [platform, storeId, resolvedStoreName, item_id, msku, sku,
       item_name, owner, launch_date, SOURCE_SYSTEM, extraBase],
    );
  }

  // dim_product_owner + 旧 active 置 inactive + dim_product 负责人快照
  await db.query(
    `INSERT INTO dim_product_owner
       (platform, store_id, store_name, item_id, msku, owner_name,
        effective_date, status, source_system, source_raw_id)
     VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
     ON DUPLICATE KEY UPDATE
       store_id=VALUES(store_id), store_name=VALUES(store_name),
       status='active', source_raw_id=VALUES(source_raw_id), updated_at=NOW()`,
    [platform, storeId, resolvedStoreName, item_id, msku, owner, TODAY, SOURCE_SYSTEM, sourceRawId],
  );
  await db.query(
    `UPDATE dim_product_owner dpo
     JOIN (
       SELECT id,
              ROW_NUMBER() OVER (
                PARTITION BY platform, item_id, msku
                ORDER BY CASE WHEN status='active' THEN 0 ELSE 1 END,
                         effective_date DESC, updated_at DESC, id DESC
              ) AS rn
       FROM dim_product_owner
       WHERE platform=? AND item_id=? AND COALESCE(msku, '')=COALESCE(?, '')
     ) ranked ON ranked.id=dpo.id
     SET dpo.status='inactive', dpo.updated_at=NOW()
     WHERE dpo.platform=? AND dpo.item_id=? AND COALESCE(dpo.msku, '')=COALESCE(?, '')
       AND ranked.rn > 1 AND dpo.status='active'`,
    [platform, item_id, msku, platform, item_id, msku],
  );
  await db.query(
    `UPDATE dim_product
     SET owner=?, launch_date=COALESCE(?, launch_date), updated_at=NOW()
     WHERE platform=? AND item_id=? AND COALESCE(msku, '')=COALESCE(?, '')
       AND (owner IS NULL OR owner='' OR owner<>? OR (? IS NOT NULL AND launch_date IS NULL))`,
    [owner, launch_date, platform, item_id, msku, owner, launch_date],
  );

  // dim_product_cost_config
  if (delivery_fee !== null) {
    await db.query(
      `INSERT INTO dim_product_cost_config
         (platform, store_id, store_name, item_id, msku, sku,
          delivery_fee, effective_date, status, source_system, source_raw_id)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
       ON DUPLICATE KEY UPDATE
         delivery_fee=VALUES(delivery_fee),
         source_raw_id=VALUES(source_raw_id), updated_at=NOW()`,
      [platform, storeId, resolvedStoreName, item_id, msku, sku,
       delivery_fee, TODAY, SOURCE_SYSTEM, sourceRawId],
    );
  }
}
/* eslint-enable @typescript-eslint/no-unused-vars */

main().catch((e: unknown) => {
  console.error("\n❌ 同步失败:", e instanceof Error ? e.message : String(e));
  process.exit(1);
});
