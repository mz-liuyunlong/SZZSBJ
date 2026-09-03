/**
 * hrRoutes.ts — AI 智能人事系统 后端（隔离新模块）
 * 挂载：adminServer `/api/hr`（位于 Admin Basic Auth 之后，继承既有鉴权，不新增登录体系）
 * 只读接口：
 *   GET  /api/hr/perf/weeks                                 可选评估周列表
 *   GET  /api/hr/perf/log-review?week_start=&owner=         周评级表（summary+items）
 *   GET  /api/hr/perf/deduction-months                      绩效台账可选月份（YYYY-MM）
 *   GET  /api/hr/perf/deductions?month=&start=&end=&owner=  月度绩效台账（明细+按人汇总；LEFT JOIN 人工层，合计排除已豁免）
 * 写接口（人工层 biz_perf_deduction_note，biz_perf_deduction 零改动）：
 *   POST /api/hr/perf/note/save   {deduction_id, explanation, filled_by?}   绩效说明（本人填；次月5号窗口内）
 *   POST /api/hr/perf/exempt      {deduction_id, exempt_by, exempt_reason?, exempt?}  豁免/撤销（黄少如/林翔；窗口内）
 * 说明：豁免=写 exempt_status=1，不删原扣分行；合计时排除已豁免。窗口=该扣分所属月的次月5号(含)前。
 *   身份硬鉴权（本人/指定人）暂缓，待用户名系统上线；本期 filled_by/exempt_by 为软记录。
 */

import { Router, Request, Response } from "express";
import * as mysql from "mysql2/promise";
import { writeAudit } from "./authService";
import { getNotifyTenantToken, resolveActiveMembers, sendCardToTarget, uploadImageToFeishu, NotifyTarget } from "./feishuNotify";

const router = Router();

// 豁免指定人（黄少如=人事HR / 林翔=主管，任一可点）；env 可覆盖，便于后续调整
const PERF_EXEMPT_APPROVERS = (process.env.PERF_EXEMPT_APPROVERS ?? "黄少如,林翔")
  .split(",").map((x) => x.trim()).filter(Boolean);

// 人事群 chat_id（人工绩效通报目标之一；env 可覆盖）
const PERF_HR_CHAT_ID = process.env.PERF_HR_CHAT_ID ?? "oc_149a50a2c1bf2dfc861dbf0236833aed";
// 后台基址（人工绩效卡片"查看绩效台账"跳转；env 可覆盖）
const ADMIN_BASE_URL = process.env.ADMIN_BASE_URL ?? "http://42.193.254.170/admin";

function dbConfig(): mysql.ConnectionOptions {
  return {
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
    dateStrings: true,
  };
}
async function getDb(): Promise<mysql.Connection> { return mysql.createConnection(dbConfig()); }
function s(v: unknown): string { return String(v ?? "").trim(); }
const YMD = /^\d{4}-\d{2}-\d{2}$/;
const YM = /^\d{4}-\d{2}$/;

router.get("/perf/weeks", async (_req: Request, res: Response): Promise<void> => {
  const db = await getDb();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT DATE_FORMAT(week_start,'%Y-%m-%d') AS week_start,
              COUNT(*) AS owners, SUM(good_count) AS good_total, SUM(bad_count) AS bad_total
       FROM ai_ops_log_review_summary GROUP BY week_start ORDER BY week_start DESC LIMIT 26`,
    );
    res.json({ weeks: rows });
  } catch (err) {
    console.warn("[hr] weeks 查询失败:", err instanceof Error ? err.message : String(err));
    res.status(500).json({ error: String(err) });
  } finally { await db.end(); }
});

router.get("/perf/log-review", async (req: Request, res: Response): Promise<void> => {
  const weekStart = s(req.query.week_start);
  const owner = s(req.query.owner);
  if (!YMD.test(weekStart)) { res.status(400).json({ error: "缺少或非法 week_start（YYYY-MM-DD，周一）" }); return; }
  const db = await getDb();
  try {
    const sumWhere = ["week_start = ?"]; const sumArgs: unknown[] = [weekStart];
    if (owner) { sumWhere.push("owner_name = ?"); sumArgs.push(owner); }
    const [summaries] = await db.query<mysql.RowDataPacket[]>(
      `SELECT owner_name, total_logs, substantive_logs, reviewed_logs, good_count, bad_count,
              ai_comment, status, llm_model, remark,
              DATE_FORMAT(updated_at,'%Y-%m-%d %H:%i') AS updated_at
       FROM ai_ops_log_review_summary
       WHERE ${sumWhere.join(" AND ")}
       ORDER BY (bad_count / GREATEST(good_count + bad_count, 1)) DESC, bad_count DESC, owner_name`,
      sumArgs,
    );
    const [items] = await db.query<mysql.RowDataPacket[]>(
      `SELECT owner_name, src_log_id, DATE_FORMAT(log_date,'%Y-%m-%d') AS log_date,
              store_name, store_id, item_id, msku, log_excerpt, signals_excerpt,
              verdict, reason, suggestion, remark
       FROM ai_ops_log_review_item
       WHERE ${sumWhere.join(" AND ")}
       ORDER BY owner_name, verdict, log_date`,
      sumArgs,
    );
    res.json({ week_start: weekStart, summaries, items });
  } catch (err) {
    console.warn("[hr] log-review 查询失败:", err instanceof Error ? err.message : String(err));
    res.status(500).json({ error: String(err) });
  } finally { await db.end(); }
});

// 绩效台账可选月份（按 deduction_date 归月，倒序）
router.get("/perf/deduction-months", async (_req: Request, res: Response): Promise<void> => {
  const db = await getDb();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT DATE_FORMAT(deduction_date,'%Y-%m') AS ym, COUNT(*) AS records
       FROM biz_perf_deduction GROUP BY ym ORDER BY ym DESC LIMIT 36`,
    );
    res.json({ months: rows });
  } catch (err) {
    console.warn("[hr] deduction-months 查询失败:", err instanceof Error ? err.message : String(err));
    res.status(500).json({ error: String(err) });
  } finally { await db.end(); }
});

router.get("/perf/deductions", async (req: Request, res: Response): Promise<void> => {
  const month = s(req.query.month);
  const start = s(req.query.start);
  const end = s(req.query.end);
  const owner = s(req.query.owner);
  const where: string[] = []; const args: unknown[] = [];
  if (month) { if (!YM.test(month)) { res.status(400).json({ error: "month 非法（YYYY-MM）" }); return; } where.push("DATE_FORMAT(d.deduction_date,'%Y-%m') = ?"); args.push(month); }
  if (start) { if (!YMD.test(start)) { res.status(400).json({ error: "start 非法" }); return; } where.push("d.deduction_date >= ?"); args.push(start); }
  if (end) { if (!YMD.test(end)) { res.status(400).json({ error: "end 非法" }); return; } where.push("d.deduction_date <= ?"); args.push(end); }
  if (owner) { where.push("d.owner_name = ?"); args.push(owner); }
  // 2026-07-30 行级隐私：非(超管/人事/运营主管)只能看自己的绩效行（owner_name=登录人姓名）
  const cuPriv = (req as { user?: { username?: string; isSuperadmin?: boolean; roles?: Set<string> } }).user;
  const privileged = !!cuPriv && (cuPriv.isSuperadmin || (cuPriv.roles?.has("人事") ?? false) || (cuPriv.roles?.has("运营主管") ?? false));
  if (!privileged) { where.push("d.owner_name = ?"); args.push(cuPriv?.username ?? ""); }
  const whereSql = where.length ? `WHERE ${where.join(" AND ")}` : "";
  const db = await getDb();
  try {
    // 明细：LEFT JOIN 人工层带出说明/豁免；within_window=该扣分所属月的次月5号(含)前
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT d.id, DATE_FORMAT(d.deduction_date,'%Y-%m-%d') AS deduction_date, d.owner_name, d.points,
              COALESCE(d.entry_type,'deduct') AS entry_type, d.biz_type,
              d.platform, d.store_id, d.item_id, d.msku, d.ref_event_id, d.note,
              DATE_FORMAT(d.created_at,'%Y-%m-%d %H:%i') AS created_at,
              COALESCE(n.explanation,'') AS explanation, COALESCE(n.explanation_by,'') AS explanation_by,
              DATE_FORMAT(n.explanation_at,'%Y-%m-%d %H:%i') AS explanation_at,
              COALESCE(n.exempt_status,0) AS exempt_status, COALESCE(n.exempt_by,'') AS exempt_by,
              DATE_FORMAT(n.exempt_at,'%Y-%m-%d %H:%i') AS exempt_at, COALESCE(n.exempt_reason,'') AS exempt_reason,
              (c.ref_deduction_id IS NOT NULL) AS has_cert,
              (CURDATE() <= DATE_ADD(DATE_ADD(DATE_FORMAT(d.deduction_date,'%Y-%m-01'), INTERVAL 1 MONTH), INTERVAL 4 DAY)) AS within_window
       FROM biz_perf_deduction d
       LEFT JOIN biz_perf_deduction_note n ON n.ref_deduction_id = d.id
       LEFT JOIN biz_perf_cert c ON c.ref_deduction_id = d.id
       ${whereSql}
       ORDER BY d.deduction_date DESC, d.id DESC LIMIT 2000`,
      args,
    );
    // 按人汇总：扣分合计/净分排除已豁免；另给已豁免笔数/免除分
    const [byOwner] = await db.query<mysql.RowDataPacket[]>(
      `SELECT d.owner_name, COUNT(*) AS records,
              SUM(CASE WHEN COALESCE(d.entry_type,'deduct') = 'award' THEN d.points ELSE 0 END) AS award_points,
              SUM(CASE WHEN COALESCE(d.entry_type,'deduct') <> 'award' AND COALESCE(n.exempt_status,0) = 0 THEN d.points ELSE 0 END) AS deduct_points,
              SUM(CASE WHEN COALESCE(n.exempt_status,0) = 1 THEN 1 ELSE 0 END) AS exempt_count,
              SUM(CASE WHEN COALESCE(d.entry_type,'deduct') <> 'award' AND COALESCE(n.exempt_status,0) = 1 THEN d.points ELSE 0 END) AS exempt_points,
              SUM(CASE WHEN COALESCE(d.entry_type,'deduct') = 'award' THEN d.points
                       WHEN COALESCE(n.exempt_status,0) = 1 THEN 0
                       ELSE -d.points END) AS net_points
       FROM biz_perf_deduction d
       LEFT JOIN biz_perf_deduction_note n ON n.ref_deduction_id = d.id
       ${whereSql}
       GROUP BY d.owner_name ORDER BY net_points ASC`,
      args,
    );
    const cu = (req as { user?: { username?: string; isSuperadmin?: boolean; roles?: Set<string> } }).user;
    const canExempt = !!cu && (cu.isSuperadmin || (cu.roles?.has("人事") ?? false) || (cu.roles?.has("运营主管") ?? false));
    res.json({ rows, by_owner: byOwner, exempt_approvers: PERF_EXEMPT_APPROVERS, can_exempt: canExempt, current_user: cu?.username ?? "" });
  } catch (err) {
    console.warn("[hr] deductions 查询失败:", err instanceof Error ? err.message : String(err));
    res.status(500).json({ error: String(err) });
  } finally { await db.end(); }
});

// 取扣分行 + 窗口判断（次月5号含前）；返回 null=不存在
async function fetchDeductionGate(db: mysql.Connection, deductionId: number): Promise<{ ym: string; owner_name: string; within_window: number } | null> {
  const [rows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT DATE_FORMAT(deduction_date,'%Y-%m') AS ym, owner_name,
            (CURDATE() <= DATE_ADD(DATE_ADD(DATE_FORMAT(deduction_date,'%Y-%m-01'), INTERVAL 1 MONTH), INTERVAL 4 DAY)) AS within_window
     FROM biz_perf_deduction WHERE id = ? LIMIT 1`,
    [deductionId],
  );
  const r = (rows as mysql.RowDataPacket[])[0];
  if (!r) return null;
  return { ym: String(r.ym ?? ""), owner_name: String(r.owner_name ?? ""), within_window: Number(r.within_window ?? 0) };
}

// 绩效说明（本人填）：窗口内可写；biz_perf_deduction 零改动，写人工层 note 表
router.post("/perf/note/save", async (req: Request, res: Response): Promise<void> => {
  const body = (req.body ?? {}) as Record<string, unknown>;
  const deductionId = Number(body.deduction_id ?? 0);
  const explanation = s(body.explanation);
  const filledByIn = s(body.filled_by);
  if (!deductionId) { res.status(400).json({ error: "缺少 deduction_id" }); return; }
  if (!explanation) { res.status(400).json({ error: "绩效说明不能为空" }); return; }
  if (explanation.length > 500) { res.status(400).json({ error: "绩效说明不超过 500 字" }); return; }
  const db = await getDb();
  try {
    const gate = await fetchDeductionGate(db, deductionId);
    if (!gate) { res.status(404).json({ error: `扣分记录 #${deductionId} 不存在` }); return; }
    if (!gate.within_window) { res.status(403).json({ error: `该月台账已锁定（绩效说明限次月5号前填写）` }); return; }
    // 身份硬鉴权待用户名系统；本期 filled_by 软记录，缺省用该行 owner_name（“本人”约定）
    const filledBy = s((req as { user?: { username?: string } }).user?.username) || filledByIn || gate.owner_name;
    await db.query(
      `INSERT INTO biz_perf_deduction_note (ref_deduction_id, ym, explanation, explanation_by, explanation_at)
       VALUES (?, ?, ?, ?, NOW())
       ON DUPLICATE KEY UPDATE explanation = VALUES(explanation), explanation_by = VALUES(explanation_by), explanation_at = NOW()`,
      [deductionId, gate.ym, explanation, filledBy],
    );
    await db.query("COMMIT");
    res.json({ ok: true, deduction_id: deductionId, explanation, explanation_by: filledBy });
  } catch (err) {
    console.warn("[hr] note/save 失败:", err instanceof Error ? err.message : String(err));
    res.status(500).json({ error: String(err) });
  } finally { await db.end(); }
});

// 豁免/撤销（黄少如/林翔）：窗口内可写；豁免=exempt_status=1（不删原扣分行）
router.post("/perf/exempt", async (req: Request, res: Response): Promise<void> => {
  const body = (req.body ?? {}) as Record<string, unknown>;
  const deductionId = Number(body.deduction_id ?? 0);
  const cu = (req as { user?: { username?: string; isSuperadmin?: boolean; roles?: Set<string> } }).user;
  const exemptBy = s(cu?.username);
  const exemptReason = s(body.exempt_reason);
  const doExempt = body.exempt === undefined ? true : Boolean(body.exempt); // 默认豁免；exempt:false=撤销
  if (!deductionId) { res.status(400).json({ error: "缺少 deduction_id" }); return; }
  if (!exemptBy) { res.status(401).json({ error: "未登录，无法豁免" }); return; }
  if (!(cu?.isSuperadmin || (cu?.roles?.has("人事") ?? false) || (cu?.roles?.has("运营主管") ?? false))) {
    res.status(403).json({ error: "你没有绩效豁免权限（仅 人事 / 运营主管 / 超管 可操作）" }); return;
  }
  const db = await getDb();
  try {
    const gate = await fetchDeductionGate(db, deductionId);
    if (!gate) { res.status(404).json({ error: `扣分记录 #${deductionId} 不存在` }); return; }
    if (!gate.within_window) { res.status(403).json({ error: `该月台账已锁定（豁免限次月5号前）` }); return; }
    if (doExempt) {
      await db.query(
        `INSERT INTO biz_perf_deduction_note (ref_deduction_id, ym, exempt_status, exempt_by, exempt_at, exempt_reason)
         VALUES (?, ?, 1, ?, NOW(), ?)
         ON DUPLICATE KEY UPDATE exempt_status = 1, exempt_by = VALUES(exempt_by), exempt_at = NOW(), exempt_reason = VALUES(exempt_reason)`,
        [deductionId, gate.ym, exemptBy, exemptReason],
      );
    } else {
      // 撤销豁免（窗口内纠错）：置回 0，保留 exempt_by/at 痕迹于 reason
      await db.query(
        `UPDATE biz_perf_deduction_note
         SET exempt_status = 0, exempt_reason = CONCAT('（', ?, ' 撤销豁免）', exempt_reason)
         WHERE ref_deduction_id = ?`,
        [exemptBy, deductionId],
      );
    }
    await db.query("COMMIT");
    await writeAudit(db, {
      userId: Number((req as { user?: { id?: number } }).user?.id ?? 0), username: exemptBy,
      action: doExempt ? "perf_exempt" : "perf_exempt_revoke", target: `deduction:${deductionId}`,
      detail: { ym: gate.ym, exempt_reason: exemptReason },
      ip: req.ip, ua: req.headers["user-agent"],
    });
    res.json({ ok: true, deduction_id: deductionId, exempt_status: doExempt ? 1 : 0, exempt_by: exemptBy });
  } catch (err) {
    console.warn("[hr] exempt 失败:", err instanceof Error ? err.message : String(err));
    res.status(500).json({ error: String(err) });
  } finally { await db.end(); }
});

// 2026-07-30 人工绩效录入用：公司在册成员名单（供选人下拉）
router.get("/perf/members", async (req: Request, res: Response): Promise<void> => {
  const cu = (req as { user?: { username?: string; isSuperadmin?: boolean; roles?: Set<string> } }).user;
  if (!(cu?.isSuperadmin || (cu?.roles?.has("人事") ?? false))) {
    res.status(403).json({ error: "仅 人事 / 超管 可用人工绩效录入" }); return;
  }
  const db = await getDb();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT name FROM dim_feishu_member WHERE employment_status = 'active' AND COALESCE(name,'') <> '' ORDER BY name`,
    );
    res.json({ members: rows.map((r) => String(r.name)) });
  } catch (err) { res.status(500).json({ error: String(err) }); }
  finally { await db.end(); }
});

// 2026-07-30 人工绩效录入（超管/人事）：写台账 biz_type='manual' + 飞书通报当事人+人事群（卡片内嵌凭证图）
router.post("/perf/manual-entry", async (req: Request, res: Response): Promise<void> => {
  const body = (req.body ?? {}) as Record<string, unknown>;
  const cu = (req as { user?: { id?: number; username?: string; isSuperadmin?: boolean; roles?: Set<string> } }).user;
  const operator = s(cu?.username);
  if (!operator) { res.status(401).json({ error: "未登录" }); return; }
  if (!(cu?.isSuperadmin || (cu?.roles?.has("人事") ?? false))) {
    res.status(403).json({ error: "仅 人事 / 超管 可录入人工绩效" }); return;
  }
  const ownerName = s(body.owner_name);
  const entryType = s(body.entry_type) === "award" ? "award" : "deduct";
  const points = Math.abs(Number(body.points ?? 0));
  const reason = s(body.reason);
  const imageB64 = s(body.image_base64);
  if (!ownerName) { res.status(400).json({ error: "请选择被记分人" }); return; }
  if (!points || !Number.isFinite(points)) { res.status(400).json({ error: "分数需为正数" }); return; }
  if (reason.length < 2) { res.status(400).json({ error: "请填写原因（≥2字）" }); return; }
  const db = await getDb();
  try {
    const { targets, warnings } = await resolveActiveMembers([ownerName]);
    const personTarget = targets.find((t) => t.label === ownerName) ?? null;
    let imageKey = "";
    let imageBuf: Buffer | null = null;
    let imageMime = "image/jpeg";
    if (imageB64) {
      const mm = imageB64.match(/^data:(image\/[\w.+-]+);base64,/);
      if (mm) imageMime = mm[1];
      try { imageBuf = Buffer.from(imageB64.replace(/^data:image\/[\w.+-]+;base64,/, ""), "base64"); } catch { imageBuf = null; }
      if (imageBuf) {
        try { imageKey = await uploadImageToFeishu(imageBuf); }
        catch (ie) { console.warn("[hr] 凭证图上传飞书失败(继续):", ie instanceof Error ? ie.message : String(ie)); }
      }
    }
    const refEventId = 9000000000 + (Date.now() % 1000000000);
    const note = `【人工${entryType === "award" ? "加分" : "扣分"}】${reason}`;
    const [ins] = await db.query<mysql.ResultSetHeader>(
      `INSERT INTO biz_perf_deduction
         (deduction_date, owner_name, points, entry_type, biz_type, platform, store_id, item_id, msku, ref_event_id, note, created_by)
       VALUES (CURDATE(), ?, ?, ?, 'manual', 'walmart', '', '', '', ?, ?, ?)`,
      [ownerName, points, entryType, refEventId, note, operator],
    );
    await db.query("COMMIT");
    const newId = (ins as mysql.ResultSetHeader).insertId;
    if (imageBuf) {
      try {
        await db.query("INSERT INTO biz_perf_cert (ref_deduction_id, mime, image_data, uploaded_by) VALUES (?, ?, ?, ?)",
          [newId, imageMime, imageBuf, operator]);
      } catch (ce) { console.warn("[hr] 凭证入库失败(不影响录入):", ce instanceof Error ? ce.message : String(ce)); }
    }
    const isAward = entryType === "award";
    const elements: Record<string, unknown>[] = [
      { tag: "div", text: { tag: "lark_md", content: `**${ownerName}** ｜ ${isAward ? "🎉 加分 +" : "⚠️ 扣分 -"}${points} 分\n\n**原因**：${reason}\n\n**录入人**：${operator}（人工绩效）` } },
    ];
    if (imageKey) elements.push({ tag: "img", img_key: imageKey, alt: { tag: "plain_text", content: "凭证" } });
    elements.push({ tag: "action", actions: [{ tag: "button", text: { tag: "plain_text", content: "查看绩效台账" }, type: "default", url: `${ADMIN_BASE_URL}/#/hr-performance` }] });
    const card = { config: { wide_screen_mode: true }, header: { template: isAward ? "green" : "red", title: { tag: "plain_text", content: isAward ? "🎉 绩效加分通知" : "⚠️ 绩效扣分通知" } }, elements };
    const fb = `绩效${isAward ? "加分" : "扣分"}：${ownerName} ${isAward ? "+" : "-"}${points}分；原因：${reason}；录入人：${operator}`;
    const notify: string[] = [];
    if (personTarget) { const r = await sendCardToTarget(personTarget, card, fb, true); notify.push(`本人:${r.ok ? "ok" : "fail"}`); }
    else notify.push(`本人:花名册未命中(${warnings.join(";")})`);
    const hrTarget: NotifyTarget = { type: "chat", label: "人事群", id: PERF_HR_CHAT_ID };
    const rHr = await sendCardToTarget(hrTarget, card, fb, true); notify.push(`人事群:${rHr.ok ? "ok" : "fail"}`);
    await writeAudit(db, {
      userId: Number(cu?.id ?? 0), username: operator, action: "perf_manual_entry", target: `owner:${ownerName}`,
      detail: { entry_type: entryType, points, reason, has_image: !!imageKey, notify }, ip: req.ip, ua: req.headers["user-agent"],
    });
    res.json({ ok: true, id: (ins as mysql.ResultSetHeader).insertId, entry_type: entryType, points, notify });
  } catch (err) {
    console.warn("[hr] manual-entry 失败:", err instanceof Error ? err.message : String(err));
    res.status(500).json({ error: String(err) });
  } finally { await db.end(); }
});

// 2026-07-31 取凭证图（每人只看自己：特权全看，否则 owner_name=登录人）
router.get("/perf/cert/:id", async (req: Request, res: Response): Promise<void> => {
  const id = Number(req.params.id ?? 0);
  const cu = (req as { user?: { username?: string; isSuperadmin?: boolean; roles?: Set<string> } }).user;
  if (!id) { res.status(400).send("bad id"); return; }
  const db = await getDb();
  try {
    const [dr] = await db.query<mysql.RowDataPacket[]>("SELECT owner_name FROM biz_perf_deduction WHERE id = ? LIMIT 1", [id]);
    if (!dr.length) { res.status(404).send("not found"); return; }
    const privileged = !!cu && (cu.isSuperadmin || (cu.roles?.has("人事") ?? false) || (cu.roles?.has("运营主管") ?? false));
    if (!privileged && String(dr[0].owner_name ?? "") !== s(cu?.username)) { res.status(403).send("forbidden"); return; }
    const [cr] = await db.query<mysql.RowDataPacket[]>("SELECT mime, image_data FROM biz_perf_cert WHERE ref_deduction_id = ? LIMIT 1", [id]);
    if (!cr.length) { res.status(404).send("no cert"); return; }
    res.set("Content-Type", String(cr[0].mime ?? "image/jpeg"));
    res.set("Cache-Control", "private, max-age=3600");
    res.send(cr[0].image_data as Buffer);
  } catch (err) { res.status(500).send(String(err)); }
  finally { await db.end(); }
});

export default router;
