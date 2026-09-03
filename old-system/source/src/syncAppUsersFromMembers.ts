/**
 * syncAppUsersFromMembers.ts — 从飞书花名册自动同步应用账号（隔离新模块，2026-07-24）
 *
 * 规则：
 *   - active 成员：确保 dim_app_user 存在（username=飞书真名，feishu_member_id=open_id，
 *     初始 password_hash='!'（无效哈希，登录不了，需经飞书卡片首登设密码），must_change_password=1）；
 *     已存在但被停用的 → 重新启用。
 *   - left 成员：把其关联账号 is_active=0（永不动 is_superadmin=1 的超管账号）。
 *   - 重名（花名册 name 非唯一）：username 追加 open_id 尾4位区分。
 *
 * 安全：默认 DRY-RUN；加 --confirm-write 才真正写库。只按 feishu_member_id 匹配，绝不动手工/超管账号。
 * 运行：ts-node src/syncAppUsersFromMembers.ts [--confirm-write]
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { getDb } from "./authService";

const CONFIRM = process.argv.includes("--confirm-write");

async function main(): Promise<void> {
  const db = await getDb();
  try {
    const [members] = await db.query<mysql.RowDataPacket[]>(
      "SELECT open_id, name, employment_status FROM dim_feishu_member",
    );
    let created = 0, reactivated = 0, deactivated = 0, renamed = 0, skipped = 0;

    for (const m of members) {
      const openId = String(m.open_id ?? "").trim();
      const name = String(m.name ?? "").trim();
      const status = String(m.employment_status ?? "active");
      if (!openId || !name) { skipped++; continue; }

      const [existRows] = await db.query<mysql.RowDataPacket[]>(
        "SELECT id, username, is_active, is_superadmin FROM dim_app_user WHERE feishu_member_id = ? LIMIT 1",
        [openId],
      );
      const row = existRows[0];

      if (status === "left") {
        if (row && !row.is_superadmin && row.is_active) {
          if (CONFIRM) await db.execute("UPDATE dim_app_user SET is_active = 0 WHERE id = ?", [row.id]);
          deactivated++;
        }
        continue;
      }

      // active
      if (row) {
        if (!row.is_active && !row.is_superadmin) {
          if (CONFIRM) await db.execute("UPDATE dim_app_user SET is_active = 1 WHERE id = ?", [row.id]);
          reactivated++;
        }
        continue;
      }

      // 新建账号，处理重名
      let username = name;
      const [clash] = await db.query<mysql.RowDataPacket[]>(
        "SELECT id FROM dim_app_user WHERE username = ? LIMIT 1",
        [username],
      );
      if (clash[0]) {
        username = `${name}(${openId.slice(-4)})`;
        renamed++;
      }
      if (CONFIRM) {
        const [ins] = await db.execute<mysql.ResultSetHeader>(
          `INSERT INTO dim_app_user
             (username, password_hash, display_name, feishu_member_id, role, is_active, must_change_password, remark)
           VALUES (?, '!', ?, ?, 'member', 1, 1, '花名册自动同步')`,
          [username, name, openId],
        );
        // 2026-08-04 需求：新用户默认角色=运营组员（仅新建时赋予；已有账号/角色不动）
        await db.execute(
          `INSERT INTO dim_app_user_role (user_id, role_key, granted_by) VALUES (?, '运营组员', 'sync-auto')`,
          [ins.insertId],
        );
      }
      created++;
    }

    console.log(
      `[sync-app-users] ${CONFIRM ? "APPLIED" : "DRY-RUN（加 --confirm-write 才写库）"} ` +
      `created=${created} reactivated=${reactivated} deactivated=${deactivated} renamed=${renamed} skipped=${skipped} total=${members.length}`,
    );
  } finally {
    await db.end().catch(() => undefined);
  }
}

main().catch((e) => {
  console.error("[sync-app-users] error:", e instanceof Error ? e.message : String(e));
  process.exitCode = 1;
});
