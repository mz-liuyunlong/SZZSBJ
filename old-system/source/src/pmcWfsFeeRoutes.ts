/**
 * pmcWfsFeeRoutes.ts — 智能PMC · WFS费用异常跟进（2026-08-12，隔离新模块）
 * 挂载：/api/pmc/wfs-fee（adminServer；全局 authMiddleware 提供 req.user）
 *
 * GET  /list   → { rows, kpi }（全部案件；前端默认排序=跟进中最前·立案时间升序）
 * POST /update → { id, action, ... } 动作：
 *   save_cases{case_nos} / save_log{follow_log} / save_remark{remark}
 *   follow{case_nos必填} waiting→following ｜ nofollow waiting→approving(发林翔审批卡)
 *   giveup following→approving(发审批卡) ｜ done{claim_amount,recovered_amount} following→done
 *   approve approving→closed ｜ reject approving→following（仅林翔/超管；异步通知负责人）
 *
 * 权限（镜像 M1 越权闸门模式）：认证态且非超管 → 案件操作仅限 owner_name 本人；
 *   approve/reject 仅 林翔 或 超管。未认证(旧 Basic Auth 通道) actor='admin_ui' 视同超管。
 * 铁律：本路由只写 event_wfs_fee_case 人工列与状态流转；判定系统列(manual/actual/units/est)只读。
 */
import { Router, Request, Response } from "express";
import * as mysql from "mysql2/promise";
import { resolveActiveMembers, sendCardToTarget, getNotifyTenantToken, sendTextToTarget } from "./feishuNotify";
import { buildWfsApprovalCard } from "./feishuCardCallbackRoutes";

const router = Router();
const APPROVER = (process.env.WFS_FEE_APPROVER ?? "林翔").trim();

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
    dateStrings: true,
  });
}
interface Cu { username?: string; display_name?: string; isSuperadmin?: boolean; roles?: Set<string> }
function cu(req: Request): Cu | undefined { return (req as { user?: Cu }).user; }
function actorOf(u: Cu | undefined): string { return String(u?.display_name ?? u?.username ?? "").trim() || "admin_ui"; }
function isSuper(u: Cu | undefined): boolean {
  if (!u?.username) return true; // 旧 Basic Auth 内网通道，视同管理
  return !!(u.isSuperadmin || (u.roles?.has("超管") ?? false));
}

router.get("/list", async (_req: Request, res: Response): Promise<void> => {
  const db = await getDb();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT id, store_id, store_name, item_id, msku, owner_name,
              manual_fee, actual_fee, total_units, est_recover, status,
              case_nos, reason, follow_log, log_updated_at, claim_amount, recovered_amount,
              decided_by, approved_by, approved_at, done_at, first_alert_at, remark,
              DATE_FORMAT(created_at,'%Y-%m-%d') AS created_date, created_at, updated_at,
              (status='following' AND (log_updated_at IS NULL OR log_updated_at < NOW() - INTERVAL 7 DAY)) AS log_stale
       FROM event_wfs_fee_case ORDER BY created_at ASC`);
    const kpi = { waiting: 0, following: 0, approving: 0, done: 0, closed: 0, est_open: 0, recovered_total: 0 };
    for (const r of rows) {
      const st = String(r.status);
      if (st in kpi) (kpi as Record<string, number>)[st] += 1;
      if (["waiting", "following", "approving"].includes(st)) kpi.est_open += Number(r.est_recover ?? 0);
      kpi.recovered_total += Number(r.recovered_amount ?? 0);
    }
    kpi.est_open = Math.round(kpi.est_open * 100) / 100;
    kpi.recovered_total = Math.round(kpi.recovered_total * 100) / 100;
    // §1 元信息：同步时间 = 事件表最近刷新 与 实收费率表最近刷新 取较新者
    const [syncRows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT GREATEST(
         COALESCE((SELECT MAX(updated_at) FROM event_wfs_fee_case), '1970-01-01'),
         COALESCE((SELECT MAX(updated_at) FROM dim_product_wfs_fee_auto), '1970-01-01')
       ) AS t`);
    const latestSync = String(syncRows[0]?.t ?? "");
    res.json({ rows, kpi, latest_sync_time: latestSync });
  } catch (e) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally { await db.end().catch(() => undefined); }
});

router.post("/update", async (req: Request, res: Response): Promise<void> => {
  const b = req.body as Record<string, unknown>;
  const id = Number(b.id ?? 0);
  const action = String(b.action ?? "");
  const u = cu(req);
  const actor = actorOf(u);
  if (!id || !action) { res.status(400).json({ error: "id/action 必填" }); return; }
  const db = await getDb();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(`SELECT * FROM event_wfs_fee_case WHERE id=?`, [id]);
    const ev = rows[0];
    if (!ev) { res.status(404).json({ error: `案件 #${id} 不存在` }); return; }
    const status = String(ev.status);
    const ownerName = String(ev.owner_name ?? "").trim();
    const superUser = isSuper(u);
    const isApprover = superUser || actor === APPROVER;
    const isOwnerOrSuper = superUser || (!!actor && actor === ownerName);

    const ownerActions = ["save_cases", "save_log", "save_remark", "follow", "nofollow", "giveup", "done"];
    if (ownerActions.includes(action) && !isOwnerOrSuper) {
      res.status(403).json({ error: `仅限负责人（${ownerName || "未分配"}）或超管操作；如需代操作请联系超管` }); return;
    }
    if (["approve", "reject"].includes(action) && !isApprover) {
      res.status(403).json({ error: `仅限 ${APPROVER} 或超管审批` }); return;
    }

    const sendApproval = (applicant: string): void => {
      const { card, fb } = buildWfsApprovalCard(ev, applicant, false);
      setImmediate(async () => {
        try {
          const { targets } = await resolveActiveMembers([APPROVER]);
          if (targets[0]) await sendCardToTarget(targets[0], card, fb, true);
        } catch (e) { console.error("[wfs-fee] 审批卡发送失败:", e instanceof Error ? e.message : String(e)); }
      });
    };
    const notifyOwner = (msg: string): void => {
      if (!ownerName) return;
      setImmediate(async () => {
        try {
          const token = await getNotifyTenantToken();
          const { targets } = await resolveActiveMembers([ownerName]);
          if (targets[0]) await sendTextToTarget(token, targets[0], msg, true);
        } catch (e) { console.error("[wfs-fee] 负责人通知失败:", e instanceof Error ? e.message : String(e)); }
      });
    };

    if (action === "save_cases") {
      const caseNos = String(b.case_nos ?? "").trim().slice(0, 255);
      await db.execute(`UPDATE event_wfs_fee_case SET case_nos=? WHERE id=?`, [caseNos, id]);
      res.json({ ok: true }); return;
    }
    if (action === "save_log") {
      const log = String(b.follow_log ?? "");
      // 2026-08-12 需求方拍板：系统直接判定，不符合模板不给写入（不接AI）。
      // 模板：MM-DD [HH:MM] 第N次跟进：内容（≥10字，非敷衍词）
      const LOG_LINE_RE = /^\d{2}-\d{2}(\s+\d{1,2}:\d{2})?\s*第\d+次跟进[：:]\s*(.+)$/;
      const LOG_BLACKLIST = ["跟进中", "等回复", "等待", "等待中", "无进展", "待处理", "无", "处理中"];
      const lines = log.split("\n").map((x) => x.trim()).filter(Boolean);
      const bad: string[] = [];
      for (const line of lines) {
        const m = line.match(LOG_LINE_RE);
        if (!m) { bad.push(`「${line.slice(0, 30)}…」缺时间或"第N次跟进："`); continue; }
        const content = String(m[2] ?? "").trim();
        const core = content.replace(/[；;。.，,、\s]/g, "");
        if (core.length < 10) { bad.push(`「${line.slice(0, 30)}…」内容不足10字`); continue; }
        if (LOG_BLACKLIST.includes(core) || LOG_BLACKLIST.some((w) => core === w)) {
          bad.push(`「${line.slice(0, 30)}…」内容为敷衍词`); continue;
        }
      }
      if (bad.length) {
        res.status(400).json({ error: `日志未保存，${bad.length}行不符合模板：${bad.slice(0, 3).join("；")}。模板：MM-DD HH:MM 第N次跟进：做了什么/Walmart说了什么；下一步：xxx（内容≥10字）` });
        return;
      }
      await db.execute(`UPDATE event_wfs_fee_case SET follow_log=?, log_updated_at=NOW() WHERE id=?`, [log, id]);
      res.json({ ok: true }); return;
    }
    if (action === "save_remark") {
      const remark = String(b.remark ?? "").trim().slice(0, 255);
      await db.execute(`UPDATE event_wfs_fee_case SET remark=? WHERE id=?`, [remark, id]);
      res.json({ ok: true }); return;
    }
    if (action === "follow") {
      if (status !== "waiting") { res.status(409).json({ error: `当前状态「${status}」不可确认跟进` }); return; }
      const caseNos = String(b.case_nos ?? "").trim().slice(0, 255);
      if (!caseNos) { res.status(400).json({ error: "Case号必填（可多个，逗号分隔）" }); return; }
      await db.execute(
        `UPDATE event_wfs_fee_case SET status='following', case_nos=?, decided_by=? WHERE id=? AND status='waiting'`,
        [caseNos, actor, id]);
      res.json({ ok: true }); return;
    }
    if (action === "nofollow" || action === "giveup") {
      const need = action === "nofollow" ? "waiting" : "following";
      if (status !== need) { res.status(409).json({ error: `当前状态「${status}」不可提交审批` }); return; }
      const reasonRaw = String(b.reason ?? "").trim().slice(0, 480);
      const reason = reasonRaw ? (action === "giveup" ? `（放弃跟进）${reasonRaw}` : reasonRaw) : "";
      if (reason) {
        await db.execute(
          `UPDATE event_wfs_fee_case SET status='approving', decided_by=?, reason=? WHERE id=? AND status=?`,
          [actor, reason, id, need]);
      } else {
        await db.execute(
          `UPDATE event_wfs_fee_case SET status='approving', decided_by=? WHERE id=? AND status=?`,
          [actor, id, need]);
      }
      sendApproval(actor);
      res.json({ ok: true }); return;
    }
    if (action === "done") {
      if (status !== "following") { res.status(409).json({ error: `当前状态「${status}」不可完成` }); return; }
      const claim = Number(b.claim_amount), recovered = Number(b.recovered_amount);
      if (!Number.isFinite(claim) || !Number.isFinite(recovered) || claim < 0 || recovered < 0) {
        res.status(400).json({ error: "完成时须填写有效的 索赔金额/追回金额" }); return;
      }
      await db.execute(
        `UPDATE event_wfs_fee_case SET status='done', claim_amount=?, recovered_amount=?, done_at=NOW(), decided_by=? WHERE id=? AND status='following'`,
        [claim, recovered, actor, id]);
      res.json({ ok: true }); return;
    }
    if (action === "approve" || action === "reject") {
      if (status !== "approving") { res.status(409).json({ error: `当前状态「${status}」无待审批申请` }); return; }
      if (action === "approve") {
        await db.execute(
          `UPDATE event_wfs_fee_case SET status='closed', approved_by=?, approved_at=NOW() WHERE id=? AND status='approving'`,
          [actor, id]);
        notifyOwner(`【WFS费用异常】${String(ev.msku)}：你的「无需跟进」申请已由${actor}同意，案件关闭。`);
      } else {
        await db.execute(
          `UPDATE event_wfs_fee_case SET status='following', approved_by=?, approved_at=NOW() WHERE id=? AND status='approving'`,
          [actor, id]);
        notifyOwner(`【WFS费用异常】${String(ev.msku)}：你的申请被${actor}驳回，请到 智能PMC → WFS费用异常 开Case跟进（每周必写跟进日志）。`);
      }
      res.json({ ok: true }); return;
    }
    res.status(400).json({ error: `未知动作 ${action}` });
  } catch (e) {
    res.status(500).json({ error: e instanceof Error ? e.message : String(e) });
  } finally { await db.end().catch(() => undefined); }
});

export default router;
