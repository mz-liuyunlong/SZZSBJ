/**
 * authRoutes.ts — 登录/登出/当前用户/改密（隔离新模块，2026-07-24，挂载于 /api/auth）
 *
 * 铁律：限流键用 socket.remoteAddress（不信任 XFF）；密码 bcrypt；全程审计。
 * cookie secure 由 env COOKIE_SECURE 控制（当前站点纯 HTTP，默认关；上 HTTPS 后置 1）。
 */

import { Router, Request, Response } from "express";
import {
  getDb,
  findUserByUsername,
  findUserByFeishuMemberId,
  verifyPassword,
  hashPassword,
  signSession,
  setPassword,
  getUserById,
  writeAudit,
  isLoginLocked,
  recordLoginFail,
  clearLoginFail,
  loginLockKey,
  createResetToken,
} from "./authService";
import { requireAuth, AuthedRequest, COOKIE_NAME } from "./authMiddleware";
import { resolveActiveMembers, sendCardToTarget } from "./feishuNotify";

const router = Router();
const COOKIE_SECURE = process.env.COOKIE_SECURE === "1";

function clientIp(req: Request): string {
  return String(req.socket.remoteAddress ?? "unknown");
}
function ua(req: Request): string {
  return String(req.headers["user-agent"] ?? "");
}

router.post("/login", async (req: Request, res: Response): Promise<void> => {
  const username = String(req.body?.username ?? "").trim();
  const password = String(req.body?.password ?? "");
  const ip = clientIp(req);
  if (!username || !password) {
    res.status(400).json({ error: "请输入用户名和密码" });
    return;
  }
  const key = loginLockKey(username, ip);
  if (isLoginLocked(key)) {
    res.status(429).json({ error: "失败次数过多，请稍后再试" });
    return;
  }

  const db = await getDb();
  try {
    const user = await findUserByUsername(db, username);
    const ok = !!user && !!user.is_active && (await verifyPassword(password, user.password_hash));
    if (!user || !ok) {
      recordLoginFail(key);
      await writeAudit(db, { userId: user?.id ?? 0, username, action: "login_fail", ip, ua: ua(req) });
      res.status(401).json({ error: "用户名或密码错误" });
      return;
    }
    clearLoginFail(key);
    const token = signSession(user);
    res.cookie(COOKIE_NAME, token, {
      httpOnly: true,
      secure: COOKIE_SECURE,
      sameSite: "lax",
      path: "/",
      // 不设 maxAge/expires => 会话不过期；吊销走 token_version
    });
    await writeAudit(db, { userId: user.id, username: user.username, action: "login", ip, ua: ua(req) });
    res.json({
      ok: true,
      username: user.username,
      display_name: user.display_name,
      role: user.role,
      must_change_password: !!user.must_change_password,
    });
  } catch (e) {
    res.status(500).json({ error: "登录失败" });
    console.error("[auth] login error:", e instanceof Error ? e.message : String(e));
  } finally {
    await db.end().catch(() => undefined);
  }
});

router.post("/logout", (_req: Request, res: Response): void => {
  res.clearCookie(COOKIE_NAME, { path: "/" });
  res.json({ ok: true });
});

router.get("/verify", requireAuth, (_req: AuthedRequest, res: Response): void => {
  res.status(200).end();
});

router.get("/me", requireAuth, (req: AuthedRequest, res: Response): void => {
  const u = req.user;
  if (!u) {
    res.status(401).json({ error: "未登录" });
    return;
  }
  res.json({
    username: u.username,
    display_name: u.display_name,
    role: u.role,
    team_name: u.team_name,
    is_superadmin: u.isSuperadmin,
    permissions: Array.from(u.permissions),
  });
});

router.post("/change-password", requireAuth, async (req: AuthedRequest, res: Response): Promise<void> => {
  const u = req.user;
  if (!u) {
    res.status(401).json({ error: "未登录" });
    return;
  }
  const oldPw = String(req.body?.old_password ?? "");
  const newPw = String(req.body?.new_password ?? "");
  if (newPw.length < 12) {
    res.status(400).json({ error: "新密码至少 12 位" });
    return;
  }
  const db = await getDb();
  try {
    const row = await getUserById(db, u.id);
    if (!row || !(await verifyPassword(oldPw, row.password_hash))) {
      res.status(403).json({ error: "原密码错误" });
      return;
    }
    await setPassword(db, u.id, await hashPassword(newPw));
    await writeAudit(db, { userId: u.id, username: u.username, action: "change_password", ip: clientIp(req), ua: ua(req) });
    res.clearCookie(COOKIE_NAME, { path: "/" }); // token_version 已 +1，旧 cookie 失效，要求重登
    res.json({ ok: true, message: "密码已更新，请重新登录" });
  } catch (e) {
    res.status(500).json({ error: "改密失败" });
    console.error("[auth] change-password error:", e instanceof Error ? e.message : String(e));
  } finally {
    await db.end().catch(() => undefined);
  }
});

// ── 首次登录 / 忘记密码：飞书名 → 发卡片设密码（Phase 2b）─────────────────────
const resetReqs = new Map<string, { count: number; windowStart: number }>();
const RESET_WINDOW_MS = 10 * 60 * 1000;
const RESET_MAX = 3;

function buildPasswordResetCard(name: string, token: string): Record<string, unknown> {
  // 卡片 JSON 2.0——结构对齐生产已验证可渲染的 csTestAlertNotify 卡：
  // form 容器内直接放 input + 提交按钮，按钮用 action_type:"form_submit" + value 直挂（非 behaviors）。
  return {
    schema: "2.0",
    config: { wide_screen_mode: true, update_multi: true },
    header: {
      template: "blue",
      title: { tag: "plain_text", content: "设置公司内部系统登录密码" },
    },
    body: {
      elements: [
        {
          tag: "markdown",
          content:
            `你好 **${name}**，请在下方设置你的登录密码（至少 12 位）后提交。\n` +
            `<font color="red">**⚠ 提示**：输入内容不会被遮盖，请勿在他人可见处操作；设置成功后本卡片即失效。</font>`,
        },
        {
          tag: "form",
          name: "pwdForm",
          elements: [
            {
              tag: "input",
              name: "new_password",
              label: { tag: "plain_text", content: "新密码（≥12位）" },
              placeholder: { tag: "plain_text", content: "输入新密码" },
              max_length: 64,
            },
            {
              tag: "button",
              text: { tag: "plain_text", content: "提交设置" },
              type: "primary",
              action_type: "form_submit",
              name: "submitPassword",
              value: { biz: "password_reset", token },
            },
          ],
        },
      ],
    },
  };
}

router.post("/request-reset", async (req: Request, res: Response): Promise<void> => {
  const feishuName = String(req.body?.feishu_name ?? "").trim();
  const ip = clientIp(req);
  if (!feishuName) {
    res.status(400).json({ error: "请输入飞书名" });
    return;
  }
  // 限流：防止对同一人反复发卡片骚扰
  const key = `${feishuName}::${ip}`;
  const now = Date.now();
  const rl = resetReqs.get(key) ?? { count: 0, windowStart: now };
  if (now - rl.windowStart > RESET_WINDOW_MS) {
    rl.count = 0;
    rl.windowStart = now;
  }
  rl.count += 1;
  resetReqs.set(key, rl);
  if (rl.count > RESET_MAX) {
    res.status(429).json({ error: "请求过于频繁，请稍后再试" });
    return;
  }

  // 花名册精确解析：0 个或重名都返回空 → 请联系人事
  const { targets } = await resolveActiveMembers([feishuName]);
  if (targets.length !== 1) {
    res.status(404).json({ error: "错误，请联系人事" });
    return;
  }
  const target = targets[0];
  const db = await getDb();
  try {
    const user = await findUserByFeishuMemberId(db, target.id);
    if (!user) {
      res.status(404).json({ error: "错误，请联系人事" });
      return;
    }
    const token = createResetToken(user.id, target.id);
    const card = buildPasswordResetCard(feishuName, token);
    const sent = await sendCardToTarget(target, card, "请到公司内部系统设置登录密码。", true);
    await writeAudit(db, { userId: user.id, username: user.username, action: "reset_card_sent", ip, ua: ua(req) });
    if (!sent.ok) {
      res.status(502).json({ error: "卡片发送失败，请稍后重试或联系人事" });
      return;
    }
    res.json({ ok: true, message: "确认卡片已发送到你本人的飞书，请在卡片上设置新密码。" });
  } catch (e) {
    res.status(500).json({ error: "请求失败" });
    console.error("[auth] request-reset error:", e instanceof Error ? e.message : String(e));
  } finally {
    await db.end().catch(() => undefined);
  }
});

export default router;
