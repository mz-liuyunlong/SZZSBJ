/**
 * helpRoutes.ts — 帮助中心 + 数据下载权限（2026-07-20 新增，隔离开发）
 *
 * 功能：
 *   GET  /api/help/articles        帮助文章目录（分组+标题+更新时间，不含正文）
 *   GET  /api/help/article?key=    单篇文章（Markdown正文 + 跳转链接）
 *   POST /api/help/export-verify   下载密码校验：{password, page_key, filters}
 *                                  → 校验 dim_access_password(scope=download,active)
 *                                  → 写 biz_event 审计 → 返回一次性 token（10分钟有效）
 *
 * 导出令牌：内存 Map（admin 单进程），feishuRawSalesRoutes 通过 isValidExportToken()
 * 校验后放宽 page_size 上限（普通请求仍封顶200，防误用）。
 *
 * 内容维护约定：帮助正文存 dim_page_help，每次涉及页面规则的代码交付都随部署
 * 提示词附带对应 UPDATE SQL，保证文档与口径同步上线（不做在线编辑）。
 */

import { Router, Request, Response } from "express";
import * as mysql from "mysql2/promise";
import * as crypto from "crypto";

const router = Router();

const EXPORT_TOKEN_TTL_MS = 10 * 60 * 1000;
const EXPORT_MAX_ROWS = 50000;
const VERIFY_WINDOW_MS = 10 * 60 * 1000;
const VERIFY_MAX_ATTEMPTS = 10; // 每IP每10分钟最多10次密码尝试

const exportTokens = new Map<string, { person: string; expiresAt: number }>();
const verifyAttempts = new Map<string, { count: number; windowStart: number }>();

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host:     process.env.DB_HOST     ?? "127.0.0.1",
    port:     Number(process.env.DB_PORT ?? 3306),
    user:     process.env.DB_USER     ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME     ?? "walmart_ai_data",
  });
}

/** 导出令牌校验（供 feishuRawSalesRoutes 放宽 page_size 用） */
export function isValidExportToken(token: string): boolean {
  const t = exportTokens.get(token);
  if (!t) return false;
  if (Date.now() > t.expiresAt) {
    exportTokens.delete(token);
    return false;
  }
  return true;
}

export function exportMaxRows(): number {
  return EXPORT_MAX_ROWS;
}

// ── 帮助文章 ──────────────────────────────────────────────────────────────────

router.get("/articles", async (_req: Request, res: Response): Promise<void> => {
  const db = await getDb();
  try {
    const [rows] = await db.execute(
      `SELECT page_key, group_name, title, target_url,
              DATE_FORMAT(updated_at, '%Y-%m-%d') AS updated_at
       FROM dim_page_help
       WHERE is_active = 1
       ORDER BY group_sort, group_name, sort, id`,
    );
    res.json({ articles: rows });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end().catch(() => undefined);
  }
});

router.get("/article", async (req: Request, res: Response): Promise<void> => {
  const key = String(req.query.key ?? "").trim();
  if (!key) {
    res.status(400).json({ error: "缺少 key" });
    return;
  }
  const db = await getDb();
  try {
    const [rows] = await db.execute(
      `SELECT page_key, group_name, title, content_md, target_url,
              DATE_FORMAT(updated_at, '%Y-%m-%d %H:%i') AS updated_at
       FROM dim_page_help
       WHERE page_key = ? AND is_active = 1
       LIMIT 1`,
      [key],
    );
    const article = (rows as mysql.RowDataPacket[])[0];
    if (!article) {
      res.status(404).json({ error: "文章不存在" });
      return;
    }
    res.json(article);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end().catch(() => undefined);
  }
});

// ── 下载密码校验 ──────────────────────────────────────────────────────────────

router.post("/export-verify", async (req: Request, res: Response): Promise<void> => {
  const password = String(req.body?.password ?? "").trim();
  const pageKey = String(req.body?.page_key ?? "").trim();
  const filters = String(req.body?.filters ?? "").slice(0, 1000);
  const ip = String(req.headers["x-forwarded-for"] ?? req.socket.remoteAddress ?? "unknown");

  // 尝试次数限制（防爆破）
  const now = Date.now();
  const attempt = verifyAttempts.get(ip) ?? { count: 0, windowStart: now };
  if (now - attempt.windowStart > VERIFY_WINDOW_MS) {
    attempt.count = 0;
    attempt.windowStart = now;
  }
  attempt.count += 1;
  verifyAttempts.set(ip, attempt);
  if (attempt.count > VERIFY_MAX_ATTEMPTS) {
    res.status(429).json({ error: "尝试次数过多，请10分钟后再试" });
    return;
  }

  if (!password) {
    res.status(400).json({ error: "请输入下载密码" });
    return;
  }

  const db = await getDb();
  try {
    const [rows] = await db.execute(
      `SELECT person FROM dim_access_password
       WHERE password = ? AND scope = 'download' AND is_active = 1
       LIMIT 1`,
      [password],
    );
    const hit = (rows as mysql.RowDataPacket[])[0];
    if (!hit) {
      res.status(403).json({ error: "下载密码错误" });
      return;
    }
    const person = String(hit.person);

    // 审计留痕（失败不阻断）
    try {
      await db.execute(
        `INSERT INTO biz_event
           (event_date, event_type, platform, store_id, item_id, msku, owner,
            title, reason, severity, status, source_table, source_key, detected_by, extra_json)
         VALUES (CURDATE(), 'data_export', 'walmart', '', '', '', ?,
                 ?, ?, 'info', 'resolved', 'dim_access_password', ?, 'manual', CAST(? AS JSON))`,
        [person,
         `数据下载: ${pageKey}`,
         filters,
         `export:${pageKey}:${Date.now()}`,
         JSON.stringify({ page_key: pageKey, person, ip, at: new Date().toISOString() })],
      );
    } catch (e) {
      console.warn("[下载审计] biz_event 写入失败（不阻断）:", e instanceof Error ? e.message : String(e));
    }

    const token = crypto.randomBytes(24).toString("hex");
    exportTokens.set(token, { person, expiresAt: Date.now() + EXPORT_TOKEN_TTL_MS });
    // 清理过期令牌
    for (const [k, v] of exportTokens) {
      if (Date.now() > v.expiresAt) exportTokens.delete(k);
    }
    res.json({ ok: true, person, token, max_rows: EXPORT_MAX_ROWS });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  } finally {
    await db.end().catch(() => undefined);
  }
});

export default router;
