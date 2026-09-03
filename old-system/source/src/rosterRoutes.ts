/**
 * rosterRoutes.ts — 花名册·成员角色管理 API（批4，2026-07-27）
 * 分层：DIM(dim_app_user / dim_app_user_role) + 审计(biz_app_audit_log)。
 * 门禁：超管 / 人事（requireRole，超管自动绕过）。角色多对多；"超管"角色同步 is_superadmin 标志。
 *   GET  /api/roster/users                        列出所有账号+角色
 *   POST /api/roster/set-roles {user_id, roles[]} 覆盖式设角色 + 审计留痕
 */
import { Router, Response } from "express";
import * as mysql from "mysql2/promise";
import { getDb } from "./authService";
import { AuthedRequest, requireRole } from "./authMiddleware";

const router = Router();
const ALLOWED_ROLES = ["超管", "人事", "财务", "中台", "运营主管", "运营组员"];

// 列成员+角色（门禁：人事，超管绕过）
router.get("/users", requireRole("人事"), async (_req: AuthedRequest, res: Response): Promise<void> => {
  const db = await getDb();
  try {
    const [users] = await db.query<mysql.RowDataPacket[]>(
      `SELECT id, username, display_name, team_name, is_active, is_superadmin, password_hash
         FROM dim_app_user ORDER BY is_active DESC, display_name`);
    const [roleRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT user_id, role_key FROM dim_app_user_role`);
    const byUser: Record<number, string[]> = {};
    for (const r of roleRows) {
      const uid = Number(r.user_id);
      (byUser[uid] || (byUser[uid] = [])).push(String(r.role_key));
    }
    const [syncRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT DATE_FORMAT(MAX(updated_at),'%Y-%m-%d %H:%i') AS latest FROM dim_feishu_member`);
    res.json({
      allowed_roles: ALLOWED_ROLES,
      latest_sync_time: String((syncRows[0] && syncRows[0].latest) || ""),
      users: users.map((u) => ({
        id: u.id,
        username: u.username,
        display_name: u.display_name,
        team_name: u.team_name,
        is_active: !!u.is_active,
        is_superadmin: !!u.is_superadmin,
        registered: String(u.password_hash) !== "!",
        roles: byUser[Number(u.id)] || [],
      })),
    });
  } catch (e) {
    res.status(500).json({ error: String(e) });
  } finally {
    await db.end().catch(() => undefined);
  }
});

// 覆盖式设角色（门禁：人事，超管绕过）
router.post("/set-roles", requireRole("人事"), async (req: AuthedRequest, res: Response): Promise<void> => {
  const body = (req.body ?? {}) as { user_id?: number; roles?: unknown };
  const userId = Number(body.user_id ?? 0);
  const roles = Array.isArray(body.roles)
    ? Array.from(new Set(body.roles.map((r) => String(r).trim()).filter(Boolean)))
    : [];
  if (!userId) { res.status(400).json({ error: "缺少 user_id" }); return; }
  const invalid = roles.filter((r) => !ALLOWED_ROLES.includes(r));
  if (invalid.length) { res.status(400).json({ error: `非法角色：${invalid.join("、")}` }); return; }

  const operator = req.user?.username || "unknown";
  const db = await getDb();
  try {
    await db.beginTransaction();
    const [urows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT id, display_name FROM dim_app_user WHERE id = ? LIMIT 1`, [userId]);
    if (!urows.length) { await db.rollback(); res.status(404).json({ error: "账号不存在" }); return; }

    await db.query(`DELETE FROM dim_app_user_role WHERE user_id = ?`, [userId]);
    for (const r of roles) {
      await db.query(
        `INSERT INTO dim_app_user_role (user_id, role_key, granted_by) VALUES (?, ?, ?)`,
        [userId, r, operator]);
    }
    // "超管"角色同步 is_superadmin 标志（保持全站以 is_superadmin 判定的代码一致）
    await db.query(`UPDATE dim_app_user SET is_superadmin = ? WHERE id = ?`,
      [roles.includes("超管") ? 1 : 0, userId]);
    // 审计留痕
    await db.query(
      `INSERT INTO biz_app_audit_log (user_id, username, action, target, detail_json, ip, ua)
       VALUES (?, ?, 'roster.set_roles', ?, CAST(? AS JSON), '', '')`,
      [req.user?.id ?? 0, operator, String(urows[0].display_name ?? userId),
       JSON.stringify({ user_id: userId, roles, by: operator })]);
    await db.commit();
    res.json({ ok: true, user_id: userId, roles });
  } catch (e) {
    try { await db.rollback(); } catch { /* noop */ }
    res.status(500).json({ error: String(e) });
  } finally {
    await db.end().catch(() => undefined);
  }
});

export default router;
