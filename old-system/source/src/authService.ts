/**
 * authService.ts — 应用认证核心（隔离新模块，2026-07-24）
 *
 * 职责：bcrypt 密码哈希、JWT 签发/校验（不过期，吊销走 token_version）、
 *       用户/权限/审计的数据访问、登录失败锁定。
 * 铁律：密钥只从 env 读（AUTH_JWT_SECRET / DB_*），绝不硬编码；不写明文密码。
 */

import * as mysql from "mysql2/promise";
import * as bcrypt from "bcryptjs";
import * as jwt from "jsonwebtoken";
import * as crypto from "crypto";

const BCRYPT_ROUNDS = 12;

export interface AppUser {
  id: number;
  username: string;
  display_name: string;
  role: string;
  team_name: string;
  is_active: number;
  is_superadmin: number;
  token_version: number;
  must_change_password: number;
}
interface UserRow extends AppUser {
  password_hash: string;
}

export function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
}

function jwtSecret(): string {
  const s = (process.env.AUTH_JWT_SECRET ?? "").trim();
  if (!s) throw new Error("AUTH_JWT_SECRET 未配置");
  return s;
}

export async function hashPassword(plain: string): Promise<string> {
  return bcrypt.hash(plain, BCRYPT_ROUNDS);
}
export async function verifyPassword(plain: string, hash: string): Promise<boolean> {
  return bcrypt.compare(plain, hash);
}

export interface TokenPayload {
  uid: number;
  un: string;
  tv: number;
}

/** 签发会话 JWT——按需求“登录状态不过期”，不设 exp；吊销依赖 token_version */
export function signSession(user: AppUser): string {
  const payload: TokenPayload = { uid: user.id, un: user.username, tv: user.token_version };
  return jwt.sign(payload, jwtSecret(), { algorithm: "HS256" });
}
export function verifySession(token: string): TokenPayload | null {
  try {
    const p = jwt.verify(token, jwtSecret()) as Partial<TokenPayload>;
    if (typeof p.uid === "number" && typeof p.tv === "number" && typeof p.un === "string") {
      return { uid: p.uid, un: p.un, tv: p.tv };
    }
    return null;
  } catch {
    return null;
  }
}

const USER_COLUMNS =
  "id, username, password_hash, display_name, role, team_name, is_active, is_superadmin, token_version, must_change_password";

export async function findUserByUsername(db: mysql.Connection, username: string): Promise<UserRow | null> {
  const [rows] = await db.execute(
    `SELECT ${USER_COLUMNS} FROM dim_app_user WHERE username = ? LIMIT 1`,
    [username],
  );
  const r = (rows as mysql.RowDataPacket[])[0];
  return r ? (r as UserRow) : null;
}

export async function getUserById(db: mysql.Connection, id: number): Promise<UserRow | null> {
  const [rows] = await db.execute(
    `SELECT ${USER_COLUMNS} FROM dim_app_user WHERE id = ? LIMIT 1`,
    [id],
  );
  const r = (rows as mysql.RowDataPacket[])[0];
  return r ? (r as UserRow) : null;
}

export async function findUserByFeishuMemberId(db: mysql.Connection, openId: string): Promise<UserRow | null> {
  const [rows] = await db.execute(
    `SELECT ${USER_COLUMNS} FROM dim_app_user WHERE feishu_member_id = ? AND is_active = 1 LIMIT 1`,
    [openId],
  );
  const r = (rows as mysql.RowDataPacket[])[0];
  return r ? (r as UserRow) : null;
}

export async function getPermissions(db: mysql.Connection, userId: number): Promise<Set<string>> {
  const [rows] = await db.execute(
    `SELECT perm_key FROM dim_app_user_permission WHERE user_id = ?`,
    [userId],
  );
  return new Set((rows as mysql.RowDataPacket[]).map((r) => String(r.perm_key)));
}

export async function getRoles(db: mysql.Connection, userId: number): Promise<Set<string>> {
  const [rows] = await db.execute(
    `SELECT role_key FROM dim_app_user_role WHERE user_id = ?`,
    [userId],
  );
  return new Set((rows as mysql.RowDataPacket[]).map((r) => String(r.role_key)));
}

export async function setPassword(db: mysql.Connection, userId: number, newHash: string): Promise<void> {
  // 改密同时 token_version+1，令其它已登录会话立即失效
  await db.execute(
    `UPDATE dim_app_user SET password_hash = ?, must_change_password = 0, token_version = token_version + 1 WHERE id = ?`,
    [newHash, userId],
  );
}

export async function writeAudit(
  db: mysql.Connection,
  e: { userId: number; username: string; action: string; target?: string; detail?: unknown; ip?: string; ua?: string },
): Promise<void> {
  try {
    await db.execute(
      `INSERT INTO biz_app_audit_log (user_id, username, action, target, detail_json, ip, ua)
       VALUES (?, ?, ?, ?, CAST(? AS JSON), ?, ?)`,
      [e.userId, e.username, e.action, e.target ?? "", JSON.stringify(e.detail ?? {}), e.ip ?? "", (e.ua ?? "").slice(0, 255)],
    );
  } catch (err) {
    console.warn("[audit] 写入失败（不阻断）:", err instanceof Error ? err.message : String(err));
  }
}

// ── 登录失败锁定（内存，username+ip 维度，递增退避） ──────────────────────────
const loginFails = new Map<string, { fails: number; lockUntil: number }>();
const LOGIN_LOCK_THRESHOLD = 5;
const LOGIN_LOCK_BASE_MS = 30 * 1000;
const LOGIN_LOCK_MAX_MS = 30 * 60 * 1000;

export function loginLockKey(username: string, ip: string): string {
  return `${username}::${ip}`;
}
export function isLoginLocked(key: string): boolean {
  const l = loginFails.get(key);
  return !!l && Date.now() < l.lockUntil;
}
export function recordLoginFail(key: string): void {
  const l = loginFails.get(key) ?? { fails: 0, lockUntil: 0 };
  l.fails += 1;
  if (l.fails >= LOGIN_LOCK_THRESHOLD) {
    l.lockUntil = Date.now() + Math.min(LOGIN_LOCK_MAX_MS, LOGIN_LOCK_BASE_MS * 2 ** (l.fails - LOGIN_LOCK_THRESHOLD));
  }
  loginFails.set(key, l);
}
export function clearLoginFail(key: string): void {
  loginFails.delete(key);
}

// ── 飞书改密：一次性 reset token（内存，10 分钟有效） ─────────────────────────
const resetTokens = new Map<string, { userId: number; openId: string; expiresAt: number }>();
const RESET_TTL_MS = 10 * 60 * 1000;

export function createResetToken(userId: number, openId: string): string {
  for (const [k, v] of resetTokens) if (Date.now() > v.expiresAt) resetTokens.delete(k);
  const token = crypto.randomBytes(24).toString("hex");
  resetTokens.set(token, { userId, openId, expiresAt: Date.now() + RESET_TTL_MS });
  return token;
}

/** 命中即删除（一次性）；过期返回 null */
export function consumeResetToken(token: string): { userId: number; openId: string } | null {
  const t = resetTokens.get(token);
  if (!t) return null;
  resetTokens.delete(token);
  if (Date.now() > t.expiresAt) return null;
  return { userId: t.userId, openId: t.openId };
}
