/**
 * scripts/updateProductManagementStatus.ts
 *
 * 产品管理：系统自动判断"停用"（只判停用，不判归档）。
 *
 * 停用规则（全部满足才判定 inactive）：
 *   1. dim_product.launch_date 距今 > 120 天
 *   2. 近90天 fact_sales_daily.sales_qty 合计 = 0（或无记录）
 *   3. 最新一次 fact_inventory_daily 快照：available_stock = 0 且 inbound_stock = 0
 *      —— 若该产品从未出现在 fact_inventory_daily（无任何库存快照），本脚本保守跳过，
 *         不判定停用（没有库存证据时不主动下结论，避免误伤刚接入还没同步过库存的新品）。
 *   4. 近30天 fact_ads_product_daily.ad_spend 合计 = 0（或无记录）
 *   5. product_management_status <> 'archived'（归档产品优先级最高，本脚本绝对不处理）
 *
 * 未命中停用规则、且当前是系统标记的 inactive 时，恢复为 active（人工归档/人工设置的状态不动）。
 *
 * 用法:
 *   npx ts-node scripts/updateProductManagementStatus.ts                 # dry-run（默认，不写库）
 *   npx ts-node scripts/updateProductManagementStatus.ts --confirm-write # 正式写入 inactive
 *
 * 只更新 dim_product，不动 RAW / FACT。可重复执行，幂等（已是目标状态的行不重复写）。
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";

const CONFIRM_WRITE = process.argv.includes("--confirm-write");
const DRY_RUN = !CONFIRM_WRITE;
const SALES_WINDOW_DAYS = 90;
const AD_WINDOW_DAYS = 30;
const LAUNCH_DATE_THRESHOLD_DAYS = 120;
const AUTO_STOP_REASON = "自动停用：超过120天无销量且无库存无广告";
const AUTO_RECOVER_REASON = "系统判断：已不满足停用候选条件，恢复在用";

function dbConfig() {
  return {
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  };
}

interface CandidateRow extends mysql.RowDataPacket {
  product_key: number;
  platform: string;
  store_id: string;
  item_id: string;
  msku: string;
  owner: string | null;
  product_management_status: string;
  product_management_status_source: string;
  launch_date: string | null;
  qty_90d: number;
  has_inventory_data: number;
  available_stock: number | null;
  inbound_stock: number | null;
  spend_30d: number;
}

async function main(): Promise<void> {
  console.log("═".repeat(60));
  console.log(`  产品管理状态自动判断（只判停用）  [${DRY_RUN ? "DRY-RUN（预览）" : "CONFIRM-WRITE（写入）"}]`);
  console.log("═".repeat(60));

  const db = await mysql.createConnection(dbConfig());
  try {
    const [rows] = await db.query<CandidateRow[]>(
      `WITH product_scope AS (
         SELECT product_key, platform, store_id, item_id, msku, owner,
                product_management_status, product_management_status_source, launch_date
         FROM dim_product
         WHERE platform = 'walmart' AND product_management_status <> 'archived'
       ),
       sales_recent AS (
         SELECT platform, store_id, item_id, msku, SUM(sales_qty) AS qty
         FROM fact_sales_daily
         WHERE platform = 'walmart' AND stat_date >= DATE_SUB(CURDATE(), INTERVAL ? DAY)
         GROUP BY platform, store_id, item_id, msku
       ),
       latest_inventory AS (
         SELECT f.platform, f.store_id, f.item_id, f.msku, f.available_stock, f.inbound_stock
         FROM fact_inventory_daily f
         JOIN (
           SELECT platform, store_id, item_id, msku, MAX(snapshot_date) AS snapshot_date
           FROM fact_inventory_daily
           WHERE platform = 'walmart'
           GROUP BY platform, store_id, item_id, msku
         ) m ON m.platform = f.platform AND m.store_id = f.store_id AND m.item_id = f.item_id
            AND COALESCE(m.msku, '') = COALESCE(f.msku, '') AND m.snapshot_date = f.snapshot_date
       ),
       ads_recent AS (
         SELECT platform, store_id, item_id, msku, SUM(ad_spend) AS spend
         FROM fact_ads_product_daily
         WHERE platform = 'walmart' AND stat_date >= DATE_SUB(CURDATE(), INTERVAL ? DAY)
         GROUP BY platform, store_id, item_id, msku
       )
       SELECT
         p.product_key, p.platform, p.store_id, p.item_id, p.msku, p.owner,
         p.product_management_status, p.product_management_status_source, p.launch_date,
         COALESCE(s.qty, 0) AS qty_90d,
         (li.available_stock IS NOT NULL) AS has_inventory_data,
         li.available_stock, li.inbound_stock,
         COALESCE(a.spend, 0) AS spend_30d
       FROM product_scope p
       LEFT JOIN sales_recent s
         ON s.platform = p.platform AND s.store_id = p.store_id AND s.item_id = p.item_id
        AND COALESCE(s.msku, '') = COALESCE(p.msku, '')
       LEFT JOIN latest_inventory li
         ON li.platform = p.platform AND li.store_id = p.store_id AND li.item_id = p.item_id
        AND COALESCE(li.msku, '') = COALESCE(p.msku, '')
       LEFT JOIN ads_recent a
         ON a.platform = p.platform AND a.store_id = p.store_id AND a.item_id = p.item_id
        AND COALESCE(a.msku, '') = COALESCE(p.msku, '')`,
      [SALES_WINDOW_DAYS, AD_WINDOW_DAYS],
    );

    const now = Date.now();
    const thresholdMs = LAUNCH_DATE_THRESHOLD_DAYS * 24 * 3600 * 1000;

    const toInactive: CandidateRow[] = [];
    const toActive: CandidateRow[] = [];
    let skippedNoInventoryData = 0;
    let skippedManualInactive = 0;
    let missingLaunchDate = 0;
    let launchDateFilled = 0;
    let olderThanThreshold = 0;
    let olderAndNoSales = 0;
    let olderAndNoSalesNoStock = 0;
    let olderAndNoSalesNoStockNoAds = 0;

    for (const row of rows) {
      const launchDateMs = row.launch_date ? new Date(row.launch_date).getTime() : NaN;
      const hasLaunchDate = Number.isFinite(launchDateMs);
      const isOldEnough = hasLaunchDate && (now - launchDateMs) > thresholdMs;
      const noSales = Number(row.qty_90d) === 0;
      const noAds = Number(row.spend_30d) === 0;
      const hasInventoryData = Number(row.has_inventory_data) === 1;
      const noStock = hasInventoryData
        && Number(row.available_stock ?? 0) === 0
        && Number(row.inbound_stock ?? 0) === 0;

      if (hasLaunchDate) {
        launchDateFilled++;
      } else {
        missingLaunchDate++;
      }

      if (isOldEnough) olderThanThreshold++;
      if (isOldEnough && noSales) olderAndNoSales++;
      if (isOldEnough && noSales && noStock) olderAndNoSalesNoStock++;
      if (isOldEnough && noSales && noStock && noAds) olderAndNoSalesNoStockNoAds++;

      if (!hasLaunchDate) {
        continue;
      }

      if (!hasInventoryData) {
        // 无任何库存快照，无法确认"无库存"，保守跳过，不判定停用
        if (row.product_management_status === "active") skippedNoInventoryData++;
        continue;
      }

      const shouldStop = isOldEnough && noSales && noStock && noAds;

      if (shouldStop && row.product_management_status === "active") {
        toInactive.push(row);
      } else if (!shouldStop && row.product_management_status === "inactive") {
        if (row.product_management_status_source === "system") {
          toActive.push(row);
        } else {
          skippedManualInactive++;
        }
      }
    }

    console.log(`\n本次扫描产品数量（非归档）: ${rows.length}`);
    console.log(`launch_date 有值数量: ${launchDateFilled}`);
    console.log(`缺上架时间数量: ${missingLaunchDate}`);
    console.log(`超过 ${LAUNCH_DATE_THRESHOLD_DAYS} 天数量: ${olderThanThreshold}`);
    console.log(`超过 ${LAUNCH_DATE_THRESHOLD_DAYS} 天且近 ${SALES_WINDOW_DAYS} 天无销量: ${olderAndNoSales}`);
    console.log(`超过 ${LAUNCH_DATE_THRESHOLD_DAYS} 天且无销量且库存/在途为0: ${olderAndNoSalesNoStock}`);
    console.log(`超过 ${LAUNCH_DATE_THRESHOLD_DAYS} 天且无销量且库存/在途为0且近 ${AD_WINDOW_DAYS} 天无广告费: ${olderAndNoSalesNoStockNoAds}`);
    console.log(`将被标记 inactive 的数量: ${toInactive.length}`);
    console.log(`将恢复 active 的数量: ${toActive.length}`);
    console.log(`跳过 archived 的数量: 0（已在 SQL WHERE 中排除，未参与本次扫描）`);
    console.log(`因无库存快照数据保守跳过（active 未判定）: ${skippedNoInventoryData}`);
    console.log(`人工标记的 inactive（不做自动恢复）: ${skippedManualInactive}`);

    console.log("\n过滤漏斗:");
    console.log(`  active: ${rows.length}`);
    console.log(`  launch_date > ${LAUNCH_DATE_THRESHOLD_DAYS}天: ${olderThanThreshold}`);
    console.log(`  近${SALES_WINDOW_DAYS}天无销量: ${olderAndNoSales}`);
    console.log(`  库存=0且在途=0: ${olderAndNoSalesNoStock}`);
    console.log(`  近${AD_WINDOW_DAYS}天广告费=0: ${olderAndNoSalesNoStockNoAds}`);
    console.log(`  最终 inactive 候选: ${toInactive.length}`);

    console.log("\nTOP 20 停用候选（按 launch_date 升序）:");
    const topInactive = [...toInactive]
      .sort((a, b) => String(a.launch_date ?? "").localeCompare(String(b.launch_date ?? "")))
      .slice(0, 20);
    for (const r of topInactive) {
      console.log(
        `  item_id=${r.item_id} msku=${r.msku} store_id=${r.store_id} owner=${r.owner ?? ""} ` +
        `launch_date=${r.launch_date ?? ""} qty_90d=${r.qty_90d} available=${r.available_stock ?? ""} ` +
        `inbound=${r.inbound_stock ?? ""} ad_spend_30d=${r.spend_30d} status=inactive`,
      );
    }
    console.log("\n抽样明细（最多10条，将恢复为 active）:");
    for (const r of toActive.slice(0, 10)) {
      console.log(`  item_id=${r.item_id} msku=${r.msku} store_id=${r.store_id} owner=${r.owner ?? ""}`);
    }

    if (DRY_RUN) {
      console.log("\n加 --confirm-write 参数正式写入 MySQL。");
      return;
    }

    let updatedInactive = 0;
    for (const r of toInactive) {
      const [result] = await db.query<mysql.ResultSetHeader>(
        `UPDATE dim_product
         SET product_management_status = 'inactive',
             product_management_status_source = 'system',
             product_management_status_reason = ?,
             product_management_status_updated_at = NOW(),
             updated_at = NOW()
         WHERE product_key = ? AND product_management_status = 'active'`,
        [AUTO_STOP_REASON, r.product_key],
      );
      updatedInactive += result.affectedRows;
    }

    let updatedActive = 0;
    for (const r of toActive) {
      const [result] = await db.query<mysql.ResultSetHeader>(
        `UPDATE dim_product
         SET product_management_status = 'active',
             product_management_status_source = 'system',
             product_management_status_reason = ?,
             product_management_status_updated_at = NOW(),
             updated_at = NOW()
         WHERE product_key = ? AND product_management_status = 'inactive'
           AND product_management_status_source = 'system'`,
        [AUTO_RECOVER_REASON, r.product_key],
      );
      updatedActive += result.affectedRows;
    }

    console.log(`\n✅ 写入完成：inactive ${updatedInactive} 行，active(恢复) ${updatedActive} 行`);

    const [archivedCntRows] = await db.query<mysql.RowDataPacket[]>(
      "SELECT COUNT(*) AS cnt FROM dim_product WHERE product_management_status = 'archived'",
    );
    console.log(`归档产品数量（本脚本执行前后应保持不变）: ${archivedCntRows[0]?.cnt ?? 0}`);
  } finally {
    await db.end();
  }
}

main().catch((e: unknown) => {
  console.error("\n❌ 执行失败:", e instanceof Error ? e.message : String(e));
  process.exit(1);
});
