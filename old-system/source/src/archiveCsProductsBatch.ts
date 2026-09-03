import "dotenv/config";
import * as mysql from "mysql2/promise";
import * as fs from "fs";
import * as path from "path";

// ============================================================================
// archiveCsProductsBatch.ts — CS测品业务暂停：批量归档全部CS产品（2026-08-17 一次性）
// 背景：CS测品业务暂停（Rocky 2026-08-17 拍板），所有未归档CS产品统一归档（含有库存的，
//       等同人工特批越过库存门槛）；已归档产品后续不再恢复。
// 口径：platform='walmart' AND msku LIKE 'CS%' AND 当前状态<>archived。
//       与产品管理页归档接口同字段同审计（product_management_status_* + biz_event pm_manual_change）。
// 安全：默认 dry-run 只打印+导出候选CSV，零写入；--confirm-write 才实写。
//       每行 UPDATE 前导出旧状态到 reports/archive_cs_backup_*.csv 留档。幂等：重跑候选归零。
// 用法：npx ts-node src/archiveCsProductsBatch.ts            (dry-run)
//       npx ts-node src/archiveCsProductsBatch.ts --confirm-write
// ============================================================================

const BATCH_MARK = "system_batch_cs_pause_20260817";
const REASON = `CS测品业务暂停批量归档（${BATCH_MARK}）`;

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
}

function csvCell(v: unknown): string {
  const s = String(v ?? "");
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

async function main(): Promise<void> {
  const confirmWrite = process.argv.includes("--confirm-write");
  const db = await getDb();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, COALESCE(store_name,'') AS store_name, item_id, COALESCE(msku,'') AS msku,
              COALESCE(sku,'') AS sku, COALESCE(owner,'') AS owner,
              COALESCE(product_management_status,'') AS old_status,
              COALESCE(product_management_status_source,'') AS old_source,
              COALESCE(product_management_status_reason,'') AS old_reason
       FROM dim_product
       WHERE platform = 'walmart' AND msku LIKE 'CS%'
         AND COALESCE(product_management_status,'') <> 'archived'
       ORDER BY store_id, item_id, msku`,
    );
    console.log(`[候选] 未归档CS产品行数: ${rows.length}`);
    const byStatus = new Map<string, number>();
    for (const r of rows) {
      const k = String(r.old_status) || "(空=active)";
      byStatus.set(k, (byStatus.get(k) ?? 0) + 1);
    }
    for (const [k, n] of byStatus) console.log(`  旧状态 ${k}: ${n} 行`);

    // 口径守卫：候选必须全部 CS 开头
    const bad = rows.filter((r) => !String(r.msku).toUpperCase().startsWith("CS"));
    if (bad.length > 0) {
      console.error(`[中止] 口径守卫失败：${bad.length} 行 msku 不以CS开头，样例 ${String(bad[0].msku)}`);
      process.exitCode = 1;
      return;
    }

    const reportsDir = path.join(__dirname, "..", "reports");
    if (!fs.existsSync(reportsDir)) fs.mkdirSync(reportsDir, { recursive: true });
    const ts = new Date().toISOString().slice(0, 10).replace(/-/g, "");
    const csvPath = path.join(reportsDir, `archive_cs_backup_${ts}${confirmWrite ? "" : "_dryrun"}.csv`);
    const header = "store_id,store_name,item_id,msku,sku,owner,old_status,old_source,old_reason";
    const lines = rows.map((r) =>
      [r.store_id, r.store_name, r.item_id, r.msku, r.sku, r.owner, r.old_status, r.old_source, r.old_reason]
        .map(csvCell).join(","));
    fs.writeFileSync(csvPath, [header, ...lines].join("\n") + "\n", "utf8");
    console.log(`[留档] 旧状态CSV: ${csvPath}`);

    if (!confirmWrite) {
      console.log("[DRY-RUN] 未写入任何数据。加 --confirm-write 执行归档。");
      return;
    }

    let updated = 0;
    for (const r of rows) {
      const [result] = await db.query<mysql.ResultSetHeader>(
        `UPDATE dim_product
         SET product_management_status = 'archived',
             product_management_status_source = 'manual',
             product_management_status_reason = ?,
             product_management_status_updated_at = NOW(),
             updated_at = NOW()
         WHERE platform = 'walmart' AND item_id = ? AND COALESCE(msku,'') = COALESCE(?, '')
           AND COALESCE(store_id,'') = COALESCE(?, '')
           AND COALESCE(product_management_status,'') <> 'archived'`,
        [REASON, r.item_id, r.msku, r.store_id],
      );
      if (result.affectedRows > 0) {
        updated += result.affectedRows;
        try {
          await db.query(
            `INSERT INTO biz_event
               (event_date, event_type, platform, store_id, item_id, msku, owner,
                title, reason, severity, status, source_table, source_key, detected_by, extra_json)
             VALUES (CURDATE(), 'pm_manual_change', 'walmart', ?, ?, ?, '',
                     ?, ?, 'info', 'resolved', 'dim_product', ?, 'manual', CAST(? AS JSON))`,
            [r.store_id, r.item_id, r.msku,
             `product_management_status: ${String(r.old_status) || "(空)"} → archived`,
             REASON,
             `${r.store_id}:${r.item_id}:${r.msku}:product_management_status:${Date.now()}`,
             JSON.stringify({ field: "product_management_status", old: String(r.old_status), new: "archived",
                              operator: BATCH_MARK, at: new Date().toISOString() })],
          );
        } catch (e) {
          console.warn("[审计] biz_event 写入失败（不阻断）:", e instanceof Error ? e.message : String(e));
        }
      }
    }
    console.log(`[完成] 归档更新 ${updated} 行（候选 ${rows.length}）。标记=${BATCH_MARK}`);

    const [verify] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COUNT(*) AS remain FROM dim_product
       WHERE platform='walmart' AND msku LIKE 'CS%'
         AND COALESCE(product_management_status,'') <> 'archived'`,
    );
    console.log(`[复核] 剩余未归档CS行数: ${Number(verify[0]?.remain ?? -1)} （应为 0）`);
  } finally {
    await db.end();
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
