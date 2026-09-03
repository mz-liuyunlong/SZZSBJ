/**
 * apiDocRoutes.ts — 内部 API 接口文档（隔离新模块，2026-07-27）
 *
 * 访问控制：仅超管（is_superadmin）或 env 白名单 API_DOC_ALLOWED_USERS 中的 username 可读。
 * 内容来源：data/api_doc_spec.json（每周更新只替换该文件，后端每请求读取，热更、免重部署）。
 * 铁律：只读；不写库；密钥/名单只从 env 读，不硬编码。
 */

import { Router, Response } from "express";
import * as fs from "fs";
import * as path from "path";
import { requireAuth, AuthedRequest } from "./authMiddleware";

const router = Router();

const SPEC_PATH = path.join(__dirname, "../data/api_doc_spec.json");

function allowedUsers(): string[] {
  return (process.env.API_DOC_ALLOWED_USERS ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function canView(req: AuthedRequest): boolean {
  const u = req.user;
  if (!u) return false;
  return u.isSuperadmin || allowedUsers().includes(u.username);
}

/** 导航门控：登录用户查询自己是否有权看 API 文档（前端据此隐藏菜单项） */
router.get("/access", requireAuth, (req: AuthedRequest, res: Response): void => {
  res.json({ allowed: canView(req) });
});

/** 文档数据：门控后返回 spec；无权 403，内容根本不下发 */
router.get("/spec", requireAuth, (req: AuthedRequest, res: Response): void => {
  if (!canView(req)) {
    res.status(403).json({ error: "无权访问 API 接口文档" });
    return;
  }
  try {
    const raw = fs.readFileSync(SPEC_PATH, "utf-8");
    res.type("application/json").send(raw);
  } catch (e) {
    console.error("[api-doc] 读取 spec 失败:", e instanceof Error ? e.message : String(e));
    res.status(500).json({ error: "文档数据读取失败" });
  }
});

export default router;
