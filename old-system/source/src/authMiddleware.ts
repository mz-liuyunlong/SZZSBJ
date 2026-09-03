/**
 * authMiddleware.ts — 会话解析 + 权限门禁（隔离新模块，2026-07-24）
 *
 * resolveUser：校验 cookie JWT → 查库确认账号有效且 token_version 匹配 → 注入 req.user，返回 bool（不发响应，供全站网关用）
 * requireAuth：resolveUser 失败即 401（供单路由用）
 * requirePermission(perm)：requireAuth 之后校验 perm_key（超管绕过）
 */

import { Request, Response, NextFunction } from "express";
import { verifySession, getDb, getUserById, getPermissions, getRoles } from "./authService";

export const COOKIE_NAME = "app_session";

export interface AuthedUser {
  id: number;
  username: string;
  display_name: string;
  role: string;
  team_name: string;
  isSuperadmin: boolean;
  permissions: Set<string>;
  roles: Set<string>;
}
export interface AuthedRequest extends Request {
  user?: AuthedUser;
}

export function readCookie(req: Request, name: string): string {
  const raw = req.headers.cookie ?? "";
  for (const part of raw.split(";")) {
    const idx = part.indexOf("=");
    if (idx === -1) continue;
    if (part.slice(0, idx).trim() === name) {
      return decodeURIComponent(part.slice(idx + 1).trim());
    }
  }
  return "";
}

/** 解析并注入 req.user；有效返回 true，否则 false（不发送任何响应） */
export async function resolveUser(req: AuthedRequest): Promise<boolean> {
  const token = readCookie(req, COOKIE_NAME);
  const payload = token ? verifySession(token) : null;
  if (!payload) return false;
  const db = await getDb();
  try {
    const user = await getUserById(db, payload.uid);
    if (!user || !user.is_active || user.token_version !== payload.tv) return false;
    const permissions = await getPermissions(db, user.id);
    const roles = await getRoles(db, user.id);
    req.user = {
      id: user.id,
      username: user.username,
      display_name: user.display_name,
      role: user.role,
      team_name: user.team_name,
      isSuperadmin: !!user.is_superadmin || roles.has("超管"),
      permissions,
      roles,
    };
    return true;
  } catch (e) {
    console.error("[auth] resolveUser error:", e instanceof Error ? e.message : String(e));
    return false;
  } finally {
    await db.end().catch(() => undefined);
  }
}

export async function requireAuth(req: AuthedRequest, res: Response, next: NextFunction): Promise<void> {
  if (await resolveUser(req)) {
    next();
    return;
  }
  res.status(401).json({ error: "未登录或登录已失效" });
}

export function requirePermission(permKey: string) {
  return (req: AuthedRequest, res: Response, next: NextFunction): void => {
    const u = req.user;
    if (!u) {
      res.status(401).json({ error: "未登录" });
      return;
    }
    if (u.isSuperadmin || u.permissions.has(permKey)) {
      next();
      return;
    }
    res.status(403).json({ error: "无操作权限" });
  };
}

export function requireRole(...roleKeys: string[]) {
  return (req: AuthedRequest, res: Response, next: NextFunction): void => {
    const u = req.user;
    if (!u) {
      res.status(401).json({ error: "未登录" });
      return;
    }
    if (u.isSuperadmin || roleKeys.some((r) => u.roles.has(r))) {
      next();
      return;
    }
    res.status(403).json({ error: "无操作权限" });
  };
}
