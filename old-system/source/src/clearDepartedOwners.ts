/**
 * clearDepartedOwners.ts - 离职第8天自动清空商品负责人（v3 最终安全版）
 *
 * 业务规则（2026-07-11 需求方定稿）：
 *   离册（不在花名册=离职）1~7天：每天在【产品管理缺负责人提醒】提醒移交；
 *   第8天仍未改派：自动清空 dim_product.owner，dim_product_owner 对应记录置 inactive
 *  （保留历史不删除）。清空后产品转入既有缺负责人每日提醒。
 *
 * v3 变更（相对 v2，消除并发竞态 + 严格全键 + 严格命中数检查）：
 *   0. FOR UPDATE 命中数严格检查：0行=真实并发变化计 skipped 继续；
 *      1行=正常；>1行=全键重复数据完整性错误，立即 throw 整体 rollback exit 1
 *   0b. UPDATE dim_product affectedRows 必须严格=1，否则 throw 整体 rollback
 *      （SQL 已执行，0或>1均不可当作跳过）；skippedConcurrentRows 仅用于锁定0行场景
 *   0c. 提交前双重一致性校验：auditRows=clearedProductRows 且
 *      clearedProductRows+skippedConcurrentRows=plannedProductRows
 *   1. --execute 开启事务后逐商品 SELECT ... FOR UPDATE 重新锁定核对全键；
 *      锁定未命中（人工改派/归档/数据变化）→ 跳过：不写审计、不动 dim_product_owner，
 *      日志输出"并发变化，已跳过"
 *   2. 锁定命中 → UPDATE dim_product 并检查 affectedRows=1，仅此时才允许
 *      更新 dim_product_owner 与写审计（审计后置，杜绝"审计已写但未清空"）
 *   3. dim_product_owner 店铺匹配严格主键优先：有 store_id 只按 store_id，
 *      无 store_id 才按 store_name 兜底；platform/item_id/msku/owner_name/status 同时匹配
 *   4. dim_product 全键与锁定均用 COALESCE(store_id,'')，兼容空 store_id；
 *      审计 store_id 写 p.store_id ?? ''
 *   5. 一致性校验：auditRows 必须等于 clearedProductRows，否则整体 rollback、exit 1
 *   6. dry-run 仍用 fetchTargets 预览（与 execute 初选同口径；execute 以事务内锁定核对为准）
 *
 * 人员判定（同 v2）：无同名 active + MAX(left_detected_at) 满7天；
 * 范围：platform='walmart' + 非 archived + owner 仍=离职者。
 *
 * dry-run（默认）：npx ts-node src/clearDepartedOwners.ts
 * 真实执行：npx ts-node src/clearDepartedOwners.ts --execute
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";

const AUDIT_TABLE = "event_product_owner_clear";

interface DepartedRow extends mysql.RowDataPacket {
  name: string;
  left_at: string; // MAX(left_detected_at)
}

interface ProductRow extends mysql.RowDataPacket {
  platform: string;
  store_id: string | null;
  store_name: string | null;
  item_id: string;
  msku: string | null;
  owner: string;
}

function dbConfig() {
  return {
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  };
}

function getShanghaiTimeStr(): string {
  return new Date().toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false });
}

function makeTaskRunId(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `DEPCLR-${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}-${Math.random().toString(36).slice(2, 6)}`;
}

/** 满7天且无同名在册的可清空离职者（与提醒段同口径，仅时间窗不同） */
async function fetchEligibleDeparted(db: mysql.Connection): Promise<DepartedRow[]> {
  const [rows] = await db.query<DepartedRow[]>(
    `SELECT d.name, DATE_FORMAT(d.left_at, '%Y-%m-%d %H:%i:%s') AS left_at
     FROM (
       SELECT name, MAX(left_detected_at) AS left_at
       FROM dim_feishu_member
       WHERE employment_status = 'left' AND left_detected_at IS NOT NULL
       GROUP BY name
     ) d
     WHERE d.left_at <= NOW() - INTERVAL 7 DAY
       AND NOT EXISTS (
         SELECT 1 FROM dim_feishu_member a
         WHERE a.name = d.name AND a.employment_status = 'active'
       )
     ORDER BY d.left_at, d.name`,
  );
  return rows;
}

/** 目标产品初选（dry-run 预览与 execute 初选共用；execute 以事务内 FOR UPDATE 核对为准） */
async function fetchTargets(db: mysql.Connection, name: string): Promise<ProductRow[]> {
  const [rows] = await db.query<ProductRow[]>(
    `SELECT platform, store_id, store_name, item_id, msku, owner
     FROM dim_product
     WHERE platform = 'walmart'
       AND owner = ?
       AND COALESCE(product_management_status, 'active') <> 'archived'
     ORDER BY store_id, item_id, msku`,
    [name],
  );
  return rows;
}

async function main(): Promise<void> {
  const doExecute = process.argv.includes("--execute");
  const taskRunId = makeTaskRunId();
  console.log("=".repeat(60));
  console.log("离职第8天负责人清空任务 v3");
  console.log(`执行时间（上海）: ${getShanghaiTimeStr()} ｜ task_run_id: ${taskRunId}`);
  console.log(`模式: ${doExecute ? "真实执行（事务内逐行锁定核对）" : "dry-run（加 --execute 执行）"}`);
  console.log("=".repeat(60));

  const db = await mysql.createConnection(dbConfig());
  let plannedProductRows = 0;
  let clearedProductRows = 0;
  let skippedConcurrentRows = 0;
  let inactivatedOwnerRows = 0;
  let auditRows = 0;
  let status = "success";

  try {
    const departed = await fetchEligibleDeparted(db);
    console.log(`满7天且无同名在册的离职者: ${departed.length} 人`);
    if (!departed.length) {
      console.log("无需处理。");
      return;
    }

    // 初选目标（dry-run 预览口径）
    const plan: { name: string; leftAt: string; products: ProductRow[] }[] = [];
    for (const d of departed) {
      const name = String(d.name || "").trim();
      if (!name) continue;
      const products = await fetchTargets(db, name);
      plan.push({ name, leftAt: d.left_at, products });
      plannedProductRows += products.length;
      console.log(`[目标] ${name}（最新离册 ${d.left_at}）名下 walmart 非归档产品 ${products.length} 个：`);
      for (const p of products) {
        console.log(`  - ${p.store_name ?? p.store_id ?? "-"} ｜ ItemID ${p.item_id} ｜ MSKU ${p.msku ?? "-"} ｜ 原负责人 ${p.owner}`);
      }
    }

    if (!doExecute) {
      console.log("DRY-RUN 预览完毕，未写库（execute 时将逐行锁定重核，人工改派的行会自动跳过）。");
      return;
    }

    // ---- 单事务执行：逐行 FOR UPDATE 锁定核对 → 清空 → 停用 → 审计 ----
    await db.beginTransaction();
    try {
      for (const item of plan) {
        for (const p of item.products) {
          // 1) 事务内按全键重新锁定核对（消除 plan 生成后的并发改派竞态）
          const [locked] = await db.query<ProductRow[]>(
            `SELECT platform, store_id, store_name, item_id, msku, owner
             FROM dim_product
             WHERE platform = ?
               AND COALESCE(store_id, '') = COALESCE(?, '')
               AND item_id = ?
               AND COALESCE(msku, '') = COALESCE(?, '')
               AND owner = ?
               AND COALESCE(product_management_status, 'active') <> 'archived'
             FOR UPDATE`,
            [p.platform, p.store_id, p.item_id, p.msku, p.owner],
          );
          if (locked.length === 0) {
            skippedConcurrentRows += 1;
            console.log(`[跳过] 并发变化，已跳过：ItemID ${p.item_id} ｜ MSKU ${p.msku ?? "-"}（已人工改派/归档/数据变化）`);
            continue;
          }
          if (locked.length > 1) {
            throw new Error(
              `dim_product 全键重复(数据完整性错误): 命中${locked.length}行, ` +
              `platform=${p.platform}, store_id=${p.store_id ?? ""}, ` +
              `item_id=${p.item_id}, msku=${p.msku ?? ""}`,
            );
          }
          const cur = locked[0];

          // 2) 清空 dim_product（全键，COALESCE 兼容空 store_id）
          const [r1]: any = await db.query(
            `UPDATE dim_product
                SET owner = '', updated_at = NOW()
              WHERE platform = ?
                AND COALESCE(store_id, '') = COALESCE(?, '')
                AND item_id = ?
                AND COALESCE(msku, '') = COALESCE(?, '')
                AND owner = ?
                AND COALESCE(product_management_status, 'active') <> 'archived'`,
            [cur.platform, cur.store_id, cur.item_id, cur.msku, cur.owner],
          );
          const affected = Number(r1.affectedRows || 0);
          if (affected !== 1) {
            // SQL 已执行：0或>1均为异常，必须整体回滚，不得计入 skipped、不得继续
            throw new Error(
              `dim_product 清空命中数异常: affectedRows=${affected}, ` +
              `platform=${cur.platform}, store_id=${cur.store_id ?? ""}, ` +
              `item_id=${cur.item_id}, msku=${cur.msku ?? ""}`,
            );
          }
          clearedProductRows += 1;

          // 3) 停用 dim_product_owner（严格主键优先：有 store_id 只按 store_id，无才按 store_name 兜底）
          const [r2]: any = await db.query(
            `UPDATE dim_product_owner
                SET status = 'inactive', updated_at = NOW()
              WHERE platform = ?
                AND item_id = ?
                AND COALESCE(msku, '') = COALESCE(?, '')
                AND (
                  (
                    COALESCE(?, '') <> ''
                    AND COALESCE(store_id, '') = COALESCE(?, '')
                  )
                  OR
                  (
                    COALESCE(?, '') = ''
                    AND COALESCE(store_name, '') = COALESCE(?, '')
                  )
                )
                AND owner_name = ?
                AND status = 'active'`,
            [cur.platform, cur.item_id, cur.msku,
             cur.store_id, cur.store_id,
             cur.store_id, cur.store_name ?? "",
             cur.owner],
          );
          inactivatedOwnerRows += Number(r2.affectedRows || 0);

          // 4) 审计后置：仅在清空成功后写入
          await db.query(
            `INSERT INTO ${AUDIT_TABLE}
               (event_time, source, task_run_id, platform, store_id, store_name,
                item_id, msku, old_owner, left_detected_at, action)
             VALUES (NOW(), 'departure_auto_clear', ?, ?, ?, ?, ?, ?, ?, ?, 'clear_owner')`,
            [taskRunId, cur.platform, cur.store_id ?? "", cur.store_name ?? "",
             cur.item_id, cur.msku ?? "", cur.owner, item.leftAt],
          );
          auditRows += 1;
        }
      }

      // 5) 提交前双重一致性校验
      if (auditRows !== clearedProductRows) {
        throw new Error(`一致性校验失败: auditRows=${auditRows} != clearedProductRows=${clearedProductRows}`);
      }
      if (clearedProductRows + skippedConcurrentRows !== plannedProductRows) {
        throw new Error(
          `一致性校验失败: cleared(${clearedProductRows}) + skipped(${skippedConcurrentRows})` +
          ` != planned(${plannedProductRows})`,
        );
      }

      await db.commit();
      console.log("事务提交完成。");
    } catch (e) {
      await db.rollback();
      status = "failed";
      console.log(`[ERR] 执行失败已整体回滚: ${e instanceof Error ? e.message : String(e)}`);
      process.exitCode = 1;
      return;
    }
  } catch (e) {
    status = "failed";
    console.log(`[致命错误] ${e instanceof Error ? e.message : String(e)}`);
    process.exitCode = 1;
  } finally {
    console.log("\n运行摘要：");
    console.log(JSON.stringify({
      taskRunId,
      executed: doExecute,
      status,
      plannedProductRows,
      clearedProductRows,
      skippedConcurrentRows,
      inactivatedOwnerRows,
      auditRows,
      auditTable: AUDIT_TABLE,
      note: doExecute
        ? "已清空的产品将进入缺负责人每日提醒；skipped 为并发变化自动跳过"
        : "dry-run 预览，未写库",
    }, null, 2));
    await db.end();
  }
}

main().catch((e) => {
  console.log(`[致命错误] ${e instanceof Error ? e.message : String(e)}`);
  process.exitCode = 1;
});
