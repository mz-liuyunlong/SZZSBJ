/**
 * feishuCardCallbackRoutes.ts — 飞书卡片回调端点（2026-07-14 新增）
 *
 * 挂载：POST /api/feishu-card-callback（Nginx 豁免 Basic Auth，安全依赖 Verification Token 验签）
 * 处理：
 *   1. url_verification 握手：校验 token 后回显 challenge
 *   2. card.action.trigger：周报会议确认卡片按钮
 *      choice=friday   → 立即异步生成（窗口至本周二）+ 生成成功自动推送
 *      choice=saturday → 写排队标记，周五 17:30 cron（checkWeeklyReportPending）生成推送
 *      choice=skip     → 记录跳过，本周不生成
 *      value.test=1    → 测试卡片：只应答 toast，不触发任何生成
 *
 * 安全：
 *   - 所有请求校验 token（url_verification 用 body.token；事件用 header.token）
 *   - 操作人校验：仅 WEEKLY_CONFIRM_RECIPIENT（默认林翔）的 open_id 可触发
 *   - event_id 进程内去重 + 业务级幂等（同周已生成/已排队/已跳过则拒绝重复触发）
 *   - 未配置 FEISHU_VERIFICATION_TOKEN 时全部拒绝（fail-closed）
 */

import { spawn } from "child_process";
import { Router, Request, Response } from "express";
import * as fs from "fs";
import * as mysql from "mysql2/promise";
import * as path from "path";
import { consumeResetToken, hashPassword, setPassword, writeAudit } from "./authService";
import { getNotifyTenantToken, getTestChatId, NotifyTarget, resolveActiveMembers, sendTextToTarget } from "./feishuNotify";
import {
  SENTINEL_NOTIFY, MAX_AUTO_ATTEMPTS, buildFixCard, buildManualCard, buildResolvedCard,
  checkDef as sentinelCheckDef, getDb as getSentinelDb, loadEvent as loadSentinelEvent,
  markManual as sentinelMarkManual, markResolved as sentinelMarkResolved, bumpAttempt as sentinelBumpAttempt,
  runRepair as sentinelRunRepair, verifyCheck as sentinelVerify,
} from "./sentinelCore";
import { sendCardToTarget } from "./feishuNotify";

const router = Router();

const STATE_DIR = process.env.WEEKLY_REPORT_STATE_DIR ?? "/opt/lingxing-auto/state";
const LOG_DIR = "/opt/lingxing-auto/logs";
const PROJECT_DIR = "/opt/lingxing-auto";
const RECIPIENT = (process.env.WEEKLY_CONFIRM_RECIPIENT ?? "林翔").trim();
// 2026-07-23 批4：兜底确认人（与 sendWeeklyReportConfirmCard 同口径）——三人任一确认均有效
const CONFIRM_BACKUPS = (process.env.WEEKLY_CONFIRM_BACKUPS ?? "陈佳聪,江梓博")
  .split(",").map((s) => s.trim()).filter(Boolean);

// event_id 进程内去重（重启丢失可接受：还有业务级幂等兜底）
const seenEvents = new Set<string>();
const SEEN_MAX = 500;

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host:     process.env.DB_HOST     ?? "127.0.0.1",
    port:     Number(process.env.DB_PORT ?? 3306),
    user:     process.env.DB_USER     ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME     ?? "walmart_ai_data",
  });
}

function toast(res: Response, type: "success" | "info" | "warning" | "error", content: string): void {
  res.json({ toast: { type, content } });
}

interface CardValue {
  biz?: string;
  choice?: string;
  week?: string;
  winEnd?: string;
  test?: number;
  id?: number | string;
  token?: string;
  owner?: string;   // 2026-08-12 sem_naming：负责人姓名
  ids?: string;     // 2026-08-12 sem_naming：alert id 逗号串
}

// ── 2026-07-20 批①：清货申请审批 ────────────────────────────────────────────
const CLEARANCE_APPROVER = (process.env.CLEARANCE_APPROVER ?? "林翔").trim();

/** 审计事件（与 feishuRawSalesRoutes.auditManualChange 同格式，独立实现避免模块耦合） */
async function auditClearanceEvent(
  db: mysql.Connection,
  args: { storeId: string; itemId: string; field: string; oldValue: string; newValue: string; operator: string },
): Promise<void> {
  try {
    await db.query(
      `INSERT INTO biz_event
         (event_date, event_type, platform, store_id, item_id, msku, owner,
          title, reason, severity, status, source_table, source_key, detected_by, extra_json)
       VALUES (CURDATE(), 'pm_manual_change', 'walmart', ?, ?, '', '',
               ?, '', 'info', 'resolved', 'dim_product', ?, 'card_callback', CAST(? AS JSON))`,
      [args.storeId, args.itemId,
       `${args.field}: ${args.oldValue || "(空)"} → ${args.newValue || "(空)"}`,
       `${args.storeId}:${args.itemId}::${args.field}:${Date.now()}`,
       JSON.stringify({ field: args.field, old: args.oldValue, new: args.newValue, operator: args.operator, at: new Date().toISOString() })],
    );
  } catch (e) {
    console.warn("[card-callback] 审计写入失败（不阻断业务）:", e instanceof Error ? e.message : String(e));
  }
}

/** 驳回后异步私信申请人（失败只记日志） */
function notifyApplicantAsync(applicant: string, text: string): void {
  setImmediate(async () => {
    try {
      const { targets } = await resolveActiveMembers([applicant]);
      const t = targets.find((x) => x.label === applicant);
      if (!t) { console.log(`[card-callback] 申请人「${applicant}」花名册未命中，跳过私信`); return; }
      const token = await getNotifyTenantToken();
      await sendTextToTarget(token, t, text, true);
    } catch (e) {
      console.log(`[card-callback] 私信申请人失败（忽略）: ${e instanceof Error ? e.message : String(e)}`);
    }
  });
}

// ── 2026-07-21 批③：清货三张自动卡（清尾/归档/复活）按钮回调 ───────────────
async function setLifecycleForItem(
  db: mysql.Connection, storeId: string, itemId: string, stage: string, byLabel: string,
): Promise<void> {
  const [msRows] = await db.execute(
    `SELECT MAX(stat_date) AS d FROM dim_product_business_state WHERE platform = 'walmart'`);
  const maxStat = (msRows as mysql.RowDataPacket[])[0]?.d ?? null;
  await db.execute(
    `UPDATE dim_product p
     LEFT JOIN dim_product_business_state bs
       ON bs.platform = p.platform AND bs.store_id = p.store_id AND bs.item_id = p.item_id
      AND COALESCE(bs.msku,'') = COALESCE(p.msku,'') AND bs.stat_date = ?
     SET p.manual_lifecycle_stage = ?,
         p.manual_lifecycle_by = ?,
         p.manual_lifecycle_at = NOW(),
         p.manual_lifecycle_system_snapshot = bs.system_lifecycle_stage,
         p.updated_at = NOW()
     WHERE p.platform = 'walmart' AND p.store_id = ? AND p.item_id = ?`,
    [maxStat, stage, byLabel, storeId, itemId],
  );
}

async function handleClearanceCard(
  res: Response,
  value: CardValue,
  operator: Record<string, unknown>,
): Promise<void> {
  const choice = String(value.choice ?? "");
  const cardId = Number(value.id ?? 0);
  const valid = new Set(["continue", "stable", "rising", "archive", "later"]);
  if (!cardId || !valid.has(choice)) { toast(res, "warning", "无法识别的卡片动作"); return; }
  if (value.test === 1) {
    toast(res, "success", `【测试】动作已接收：${choice}（卡片#${cardId}，不落库）`);
    return;
  }
  const db = await getDb();
  try {
    const [rows] = await db.execute(
      `SELECT id, card_type, store_id, store_name, item_id, mskus, owner, action
       FROM event_clearance_card WHERE id = ? LIMIT 1`, [cardId],
    );
    const ev = (rows as mysql.RowDataPacket[])[0];
    if (!ev) { toast(res, "error", `卡片记录 #${cardId} 不存在`); return; }
    if (String(ev.action ?? "")) {
      toast(res, "info", `该产品已处理过（${ev.action}），无需重复操作`);
      return;
    }
    // 操作人校验：该卡负责人本人 或 审批人（林翔）
    const allowNames = [String(ev.owner ?? ""), CLEARANCE_APPROVER].filter(Boolean);
    const { targets } = await resolveActiveMembers([...new Set(allowNames)]);
    const opId = String(operator.open_id ?? "");
    const matched = targets.find((t) => t.id === opId);
    if (!opId || !matched) {
      toast(res, "error", `仅限 ${allowNames.join("/")} 操作此卡片`);
      return;
    }
    const actor = matched.label;
    const finish = async (action: string, suppressDays: number | null): Promise<void> => {
      await db.execute(
        `UPDATE event_clearance_card
         SET status='acted', action=?, acted_by=?, acted_at=NOW(),
             suppress_until=${suppressDays === null ? "NULL" : `DATE_ADD(CURDATE(), INTERVAL ${suppressDays} DAY)`}
         WHERE id=?`,
        [action, actor, cardId],
      );
    };
    if (choice === "continue") {
      await finish("继续清货", 14);
      toast(res, "success", `已记录继续清货：${ev.mskus}，14天内不再询问`);
    } else if (choice === "later") {
      await finish("暂不归档", 7);
      toast(res, "success", `已记录暂不归档：${ev.mskus}，7天后再次确认`);
    } else if (choice === "stable" || choice === "rising") {
      const stage = choice === "rising" ? "上升期" : "稳定期";
      await setLifecycleForItem(db, String(ev.store_id), String(ev.item_id), stage, `${actor}(卡片)`);
      await auditClearanceEvent(db, {
        storeId: String(ev.store_id), itemId: String(ev.item_id),
        field: "manual_lifecycle_stage", oldValue: "清货期", newValue: `${stage}(卡片确认)`, operator: actor,
      });
      await finish(`转${stage}`, null);
      toast(res, "success", `已转${stage}：${ev.mskus}，产品移出清货中心`);
    } else if (choice === "archive") {
      // 库存拦截（与产品管理归档同口径：有库存/在途不允许归档）
      const [invRows] = await db.execute(
        `SELECT SUM(COALESCE(wfs_available_stock,0)) AS wfs, SUM(COALESCE(inbound_stock,0)) AS inbound
         FROM fact_inventory_daily
         WHERE platform='walmart' AND store_id=? AND item_id=?
           AND snapshot_date=(SELECT MAX(snapshot_date) FROM fact_inventory_daily
                              WHERE platform='walmart' AND store_id=? AND item_id=?)`,
        [ev.store_id, ev.item_id, ev.store_id, ev.item_id],
      );
      const inv = ((invRows as mysql.RowDataPacket[])[0] ?? {}) as mysql.RowDataPacket;
      const wfs = Number(inv.wfs ?? 0);
      const inbound = Number(inv.inbound ?? 0);
      if (wfs > 0 || inbound > 0) {
        toast(res, "warning", `归档被拦截：最新快照库存${wfs}/在途${inbound}，有库存或在途不允许归档`);
        return;
      }
      await db.execute(
        `UPDATE dim_product
         SET product_management_status='archived',
             product_management_status_source='card',
             product_management_status_reason='清货完成卡片归档',
             product_management_status_updated_at=NOW(),
             updated_at=NOW()
         WHERE platform='walmart' AND store_id=? AND item_id=?`,
        [ev.store_id, ev.item_id],
      );
      await auditClearanceEvent(db, {
        storeId: String(ev.store_id), itemId: String(ev.item_id),
        field: "product_management_status", oldValue: "active", newValue: "archived(清货完成卡片归档)", operator: actor,
      });
      await finish("确认归档", null);
      toast(res, "success", `已归档：${ev.mskus}（清货完成）`);
    }
    console.log(`[card-callback] 清货卡 #${cardId} ${ev.card_type} → ${choice} by ${actor}`);
  } finally {
    await db.end().catch(() => undefined);
  }
}

async function handleClearanceApproval(
  res: Response,
  value: CardValue,
  operator: Record<string, unknown>,
): Promise<void> {
  const choice = String(value.choice ?? "");
  const appId = Number(value.id ?? 0);
  if (!appId || (choice !== "approve" && choice !== "reject")) {
    toast(res, "warning", "无法识别的审批动作");
    return;
  }
  if (value.test === 1) {
    toast(res, "success", `【测试】审批动作已接收：${choice}（申请#${appId}，不落库）`);
    console.log(`[card-callback] 清货审批测试动作: ${JSON.stringify(value)}`);
    return;
  }
  const { targets } = await resolveActiveMembers([CLEARANCE_APPROVER]);
  const allowed = targets[0];
  const opId = String(operator.open_id ?? "");
  if (!allowed || !opId || allowed.id !== opId) {
    toast(res, "error", `仅限 ${CLEARANCE_APPROVER} 审批清货申请`);
    return;
  }
  const db = await getDb();
  try {
    const [rows] = await db.execute(
      `SELECT id, platform, store_id, store_name, item_id, mskus, applicant, status
       FROM event_clearance_approval WHERE id = ? LIMIT 1`, [appId],
    );
    const app = (rows as mysql.RowDataPacket[])[0];
    if (!app) { toast(res, "error", `申请 #${appId} 不存在`); return; }
    if (app.status !== "pending") {
      toast(res, "info", `该申请已处理（当前状态：${app.status}），无需重复操作`);
      return;
    }
    if (choice === "approve") {
      const [msRows] = await db.execute(
        `SELECT MAX(stat_date) AS d FROM dim_product_business_state WHERE platform = ?`, [app.platform],
      );
      const maxStat = (msRows as mysql.RowDataPacket[])[0]?.d ?? null;
      await db.beginTransaction();
      try {
        await db.execute(
          `UPDATE dim_product p
           LEFT JOIN dim_product_business_state bs
             ON bs.platform = p.platform AND bs.store_id = p.store_id AND bs.item_id = p.item_id
            AND COALESCE(bs.msku,'') = COALESCE(p.msku,'') AND bs.stat_date = ?
           SET p.manual_lifecycle_stage = '清货期',
               p.manual_lifecycle_by = ?,
               p.manual_lifecycle_at = NOW(),
               p.manual_lifecycle_system_snapshot = bs.system_lifecycle_stage,
               p.updated_at = NOW()
           WHERE p.platform = ? AND p.store_id = ? AND p.item_id = ?`,
          [maxStat, `${CLEARANCE_APPROVER}(审批)`, app.platform, app.store_id, app.item_id],
        );
        await db.execute(
          `UPDATE event_clearance_approval SET status = 'approved', approver = ?, decided_at = NOW() WHERE id = ?`,
          [CLEARANCE_APPROVER, appId],
        );
        await db.commit();
      } catch (e) {
        await db.rollback();
        throw e;
      }
      await auditClearanceEvent(db, {
        storeId: String(app.store_id), itemId: String(app.item_id),
        field: "manual_lifecycle_stage", oldValue: "", newValue: "清货期(审批通过)", operator: CLEARANCE_APPROVER,
      });
      notifyApplicantAsync(String(app.applicant),
        `✅ 你提交的清货申请已通过审批：${app.store_name} ｜ ItemID ${app.item_id} ｜ ${app.mskus}\n该产品已进入清货期。`);
      // M5b：私信审批人清货中心链接，去设本月清货目标（仅超管可填；不做卡片内数字输入）
      { const link = (process.env.BUSINESS_REPORT_BASE_URL || "http://42.193.254.170").replace(/\/+$/, "") + "/admin/#/clearance-center";
        notifyApplicantAsync(CLEARANCE_APPROVER, `📌 已通过清货：${app.store_name} ｜ ItemID ${app.item_id}。请到清货中心设置本月【清货目标数量】（仅超管可填）：\n${link}`); }
      toast(res, "success", `已批准：${app.mskus}（ItemID ${app.item_id}）进入清货期`);
      console.log(`[card-callback] 清货申请 #${appId} 已批准（${app.store_id}/${app.item_id}）`);
    } else {
      await db.execute(
        `UPDATE event_clearance_approval SET status = 'rejected', approver = ?, decided_at = NOW() WHERE id = ?`,
        [CLEARANCE_APPROVER, appId],
      );
      await auditClearanceEvent(db, {
        storeId: String(app.store_id), itemId: String(app.item_id),
        field: "clearance_apply", oldValue: "清货期(待审批)", newValue: "已驳回", operator: CLEARANCE_APPROVER,
      });
      notifyApplicantAsync(String(app.applicant),
        `❌ 你提交的清货申请被驳回：${app.store_name} ｜ ItemID ${app.item_id} ｜ ${app.mskus}\n产品生命周期维持原状，如有疑问请与 ${CLEARANCE_APPROVER} 沟通。`);
      toast(res, "success", `已驳回：${app.mskus}（ItemID ${app.item_id}），申请人将收到私信通知`);
      console.log(`[card-callback] 清货申请 #${appId} 已驳回（${app.store_id}/${app.item_id}）`);
    }
  } finally {
    await db.end().catch(() => undefined);
  }
}

// ── 2026-07-30：考勤缺卡通报"确认收到"回调 ──────────────────────────────
function lackDescLocal(t: string): string {
  return t === "上班" ? "上班卡未打" : t === "下班" ? "下班卡未打" : t === "双缺" ? "上下班均未打卡" : "缺卡";
}
/** 确认/失效后的更新卡（与原卡同为 schema 1.0） */
function buildLackAckClosedCard(name: string, statDate: string, lackType: string, kind: "confirmed" | "expired"): Record<string, unknown> {
  const ok = kind === "confirmed";
  return {
    type: "raw",
    data: {
      config: { wide_screen_mode: true },
      header: {
        template: ok ? "green" : "grey",
        title: { tag: "plain_text", content: ok ? "✅ 考勤缺卡提醒（已确认）" : "⛔ 考勤缺卡提醒（已失效）" },
      },
      elements: [
        { tag: "div", text: { tag: "lark_md", content:
          "**姓名**：" + name + "\n**日期**：" + statDate + "\n**缺卡**：" + lackDescLocal(lackType) } },
        { tag: "div", text: { tag: "lark_md", content: ok
          ? "你已确认知悉，确认状态已同步人事群。如系设备/网络异常漏打卡，请线下联系人事补卡。"
          : "本提醒已超过 24 小时失效，本次缺卡按 **旷工** 计，人事群已记录。如需更正请线下联系人事补卡。" } },
      ],
    },
  };
}

// ── 2026-08-10 P7数据哨兵卡：确认执行修复(系统代码白名单)→立即复查→当日闭环（SQL040）──
async function sentinelDmResult(card: Record<string, unknown>, fb: string): Promise<void> {
  try {
    const { targets } = await resolveActiveMembers([SENTINEL_NOTIFY]);
    const t = targets[0];
    if (t) await sendCardToTarget(t, card, fb, true);
  } catch (e) {
    console.warn(`[sentinel] 结果卡发送失败: ${e instanceof Error ? e.message : String(e)}`);
  }
}

async function handleSentinelFix(
  res: Response,
  value: CardValue,
  operator: Record<string, unknown>,
): Promise<void> {
  const choice = String(value.choice ?? "");
  if (value.test === 1) {
    toast(res, "success", `【测试】动作已接收：${choice === "fix" ? "确认执行修复" : choice === "later" ? "暂不处理" : "知悉"}（测试卡不执行不落库）`);
    return;
  }
  const evId = Number(value.id ?? 0);
  if (!evId || !["fix", "later", "ack"].includes(choice)) { toast(res, "warning", "无法识别的哨兵卡动作"); return; }
  const db = await getSentinelDb();
  try {
    const ev = await loadSentinelEvent(db, evId);
    if (!ev) { toast(res, "error", `哨兵事件 #${evId} 不存在`); return; }
    if (ev.status === "resolved") { toast(res, "info", "该异常已闭环，无需操作"); return; }
    // 操作权限：仅哨兵通报人（陈佳聪）
    const { targets } = await resolveActiveMembers([SENTINEL_NOTIFY]);
    const opId = String(operator.open_id ?? "");
    const matched = targets.find((t) => t.id === opId);
    if (!opId || !matched) { toast(res, "error", `仅限 ${SENTINEL_NOTIFY} 操作此卡片`); return; }
    if (choice === "later") { toast(res, "info", "已记录暂不处理；将每小时提醒直至闭环"); return; }
    if (choice === "ack") { toast(res, "success", "已知悉；处理完成后哨兵复查通过将自动停止提醒"); return; }
    // choice === "fix"
    const def = sentinelCheckDef(ev.check_key);
    if (!def?.repairable) { toast(res, "warning", "该检查项无自动修复动作，请人工排查"); return; }
    if (ev.attempt_count >= MAX_AUTO_ATTEMPTS) { toast(res, "warning", `自动修复已尝试${ev.attempt_count}次仍未通过，请人工排查`); return; }
    await sentinelBumpAttempt(db, ev.id);
    toast(res, "success", "已确认，系统正在执行修复，完成后将另行通知复查结果");
    // 异步执行：白名单命令 → 立即复查 → 回报（不阻塞回调应答）
    const evSnapshot = { ...ev, attempt_count: ev.attempt_count + 1 };
    setImmediate(async () => {
      const bg = await getSentinelDb();
      try {
        const rep = await sentinelRunRepair(bg, evSnapshot.check_key, evSnapshot.target_date);
        const v = await sentinelVerify(bg, evSnapshot.check_key, evSnapshot.target_date);
        console.log(`[sentinel] #${evSnapshot.id} ${evSnapshot.check_key} 修复执行 ok=${rep.ok} 复查 ok=${v.ok}`);
        if (v.ok) {
          await sentinelMarkResolved(bg, evSnapshot.id, `card:${SENTINEL_NOTIFY}`);
          const { card, fb } = buildResolvedCard(evSnapshot, `修复后复查通过：${v.detail}`);
          await sentinelDmResult(card, fb);
        } else if (evSnapshot.attempt_count >= MAX_AUTO_ATTEMPTS) {
          await sentinelMarkManual(bg, evSnapshot.id);
          evSnapshot.detail = v.detail;
          const { card, fb } = buildManualCard(evSnapshot, false);
          await sentinelDmResult(card, fb);
        } else {
          evSnapshot.detail = v.detail;
          const { card, fb } = buildFixCard(evSnapshot, false);
          await sentinelDmResult(card, fb);
        }
      } catch (e) {
        console.error(`[sentinel] #${evSnapshot.id} 修复流程异常: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        await bg.end().catch(() => undefined);
      }
    });
  } finally {
    await db.end().catch(() => undefined);
  }
}

// ── 2026-08-05 归档产品到货卡：恢复在售 / 继续归档（事件表 event_archived_restock_alert, SQL039）──
async function handleArchivedRestock(
  res: Response,
  value: CardValue,
  operator: Record<string, unknown>,
): Promise<void> {
  const choice = String(value.choice ?? "");
  if (value.test === 1) {
    toast(res, "success", `【测试】动作已接收：${choice === "restore" ? "恢复在售" : "继续归档"}（测试卡不落库）`);
    return;
  }
  const evId = Number(value.id ?? 0);
  if (!evId || !["restore", "keep"].includes(choice)) { toast(res, "warning", "无法识别的卡片动作"); return; }
  const db = await getDb();
  try {
    const [rows] = await db.execute(
      `SELECT id, platform, store_id, item_id, mskus, owner_name, decision
       FROM event_archived_restock_alert WHERE id = ?`, [evId]);
    const ev = ((rows as mysql.RowDataPacket[])[0] ?? null) as mysql.RowDataPacket | null;
    if (!ev) { toast(res, "error", `卡片记录 #${evId} 不存在`); return; }
    if (String(ev.decision ?? "")) {
      toast(res, "info", `该产品已处理过（${String(ev.decision) === "restore" ? "恢复在售" : "继续归档"}），无需重复操作`);
      return;
    }
    // 操作人校验：该卡负责人本人 或 超管（林翔/陈佳聪）
    const allowNames = [String(ev.owner_name ?? ""), CLEARANCE_APPROVER, "陈佳聪"].filter(Boolean);
    const { targets } = await resolveActiveMembers([...new Set(allowNames)]);
    const opId = String(operator.open_id ?? "");
    const matched = targets.find((t) => t.id === opId);
    if (!opId || !matched) { toast(res, "error", `仅限 ${[...new Set(allowNames)].join("/")} 操作此卡片`); return; }
    const actor = matched.label;
    if (choice === "restore") {
      await db.execute(
        `UPDATE dim_product
         SET product_management_status='active',
             product_management_status_source='card',
             product_management_status_reason=?,
             product_management_status_updated_at=NOW(), updated_at=NOW()
         WHERE platform=? AND store_id=? AND item_id=? AND product_management_status='archived'`,
        [`归档到货卡片·恢复在售(${actor})`, String(ev.platform), String(ev.store_id), String(ev.item_id)],
      );
      await db.execute(
        `UPDATE event_archived_restock_alert SET decision='restore', decided_by=?, decided_at=NOW() WHERE id=?`,
        [actor, evId]);
      toast(res, "success", `已恢复在售：${String(ev.mskus)}（将自动进入目标管理/考核）`);
    } else {
      await db.execute(
        `UPDATE event_archived_restock_alert SET decision='keep', decided_by=?, decided_at=NOW() WHERE id=?`,
        [actor, evId]);
      toast(res, "success", `已确认继续归档：${String(ev.mskus)}（暂停提醒；库存再增长时会重新提醒）`);
    }
    console.log(`[card-callback] 归档到货卡 #${evId} → ${choice} by ${actor}`);
  } finally {
    await db.end().catch(() => undefined);
  }
}

// ── 2026-08-11 WFS费用异常卡（事件表 event_wfs_fee_case, SQL042）──
// follow=转跟进中；nofollow=直接送林翔审批（需求方2026-08-12拍板：不需要填理由）；
// agree/reject=林翔审批卡按钮（同意关闭/驳回强制跟进）。
export function buildWfsApprovalCard(ev: mysql.RowDataPacket, applicant: string, test: boolean): { card: Record<string, unknown>; fb: string } {
  const est = Number(ev.est_recover ?? 0);
  const card = {
    config: { wide_screen_mode: true },
    header: { template: "orange", title: { tag: "plain_text", content: "🔶 WFS费用异常 ·「无需跟进」待你审批" } },
    elements: [
      { tag: "div", text: { tag: "lark_md", content:
        `**产品**：${String(ev.msku)}（${String(ev.item_id) || "无ItemID"}）｜ **店铺**：${String(ev.store_name) || String(ev.store_id)}\n` +
        `**人工配送费**：$${Number(ev.manual_fee).toFixed(2)} ｜ **实收费率**：$${Number(ev.actual_fee).toFixed(2)}\n` +
        `**预估追回**：<font color='red'>$${est.toFixed(2)}</font> ｜ **负责人**：${String(ev.owner_name) || "（空缺）"}\n` +
        `**申请人**：${applicant}（申请不跟进）` } },
      { tag: "action", actions: [
        { tag: "button", text: { tag: "plain_text", content: "✅ 同意关闭（不追）" }, type: "primary",
          value: Object.assign({ biz: "wfs_fee", id: Number(ev.id), choice: "agree" }, test ? { test: 1 } : {}) },
        { tag: "button", text: { tag: "plain_text", content: "↩️ 驳回（须跟进）" }, type: "danger",
          value: Object.assign({ biz: "wfs_fee", id: Number(ev.id), choice: "reject" }, test ? { test: 1 } : {}) },
      ] },
      { tag: "note", elements: [{ tag: "plain_text", content: "同意后该案关闭不再检测提醒；驳回后负责人须开Case跟进。" }] },
    ],
  };
  const fb = `【WFS费用异常·待审批】${String(ev.msku)}｜预估追回$${est.toFixed(2)}｜${applicant}申请不跟进，请审批。`;
  return { card, fb };
}

async function handleWfsFee(
  res: Response,
  value: CardValue,
  operator: Record<string, unknown>,
): Promise<void> {
  const choice = String(value.choice ?? "");
  if (value.test === 1) {
    const lbl = ({ follow: "需要跟进", nofollow: "无需跟进(送审)", agree: "同意关闭", reject: "驳回须跟进" } as Record<string, string>)[choice] ?? choice;
    toast(res, "success", `【测试】动作已接收：${lbl}（测试卡不落库）`);
    return;
  }
  const evId = Number(value.id ?? 0);
  if (!evId || !["follow", "nofollow", "agree", "reject"].includes(choice)) { toast(res, "warning", "无法识别的卡片动作"); return; }
  const db = await getDb();
  try {
    const [rows] = await db.execute(
      `SELECT id, store_id, store_name, item_id, msku, owner_name, manual_fee, actual_fee, est_recover, status, decided_by
       FROM event_wfs_fee_case WHERE id = ?`, [evId]);
    const ev = ((rows as mysql.RowDataPacket[])[0] ?? null) as mysql.RowDataPacket | null;
    if (!ev) { toast(res, "error", `WFS费用异常记录 #${evId} 不存在`); return; }
    const status = String(ev.status);
    const opId = String(operator.open_id ?? "");

    if (choice === "follow" || choice === "nofollow") {
      if (status !== "waiting") {
        toast(res, "info", `该案已是「${status}」状态，无需重复确认；进度请到智能PMC查看`);
        return;
      }
      const allowNames = [String(ev.owner_name ?? ""), CLEARANCE_APPROVER, "陈佳聪"].filter(Boolean);
      const { targets } = await resolveActiveMembers([...new Set(allowNames)]);
      const matched = targets.find((t) => t.id === opId);
      if (!opId || !matched) { toast(res, "error", `仅限 ${[...new Set(allowNames)].join("/")} 操作此卡片`); return; }
      if (choice === "follow") {
        await db.execute(
          `UPDATE event_wfs_fee_case SET status='following', decided_by=? WHERE id=? AND status='waiting'`,
          [matched.label, evId]);
        toast(res, "success", `已转跟进中：${String(ev.msku)}。请到 智能PMC → WFS费用异常 填写Case号（必填）并每周写跟进日志`);
      } else {
        await db.execute(
          `UPDATE event_wfs_fee_case SET status='approving', decided_by=? WHERE id=? AND status='waiting'`,
          [matched.label, evId]);
        toast(res, "success", `已提交林翔审批：${String(ev.msku)}（无需跟进申请）`);
        const { card, fb } = buildWfsApprovalCard(ev, matched.label, false);
        setImmediate(async () => {
          try {
            const { targets: apprs } = await resolveActiveMembers([CLEARANCE_APPROVER]);
            const t = apprs[0];
            if (t) await sendCardToTarget(t, card, fb, true);
          } catch (e) { console.error("[card-callback] wfs_fee 审批卡发送失败:", e instanceof Error ? e.message : String(e)); }
        });
      }
      console.log(`[card-callback] WFS费用卡 #${evId} → ${choice} by ${matched.label}`);
      return;
    }

    // agree / reject：仅林翔或陈佳聪
    if (status !== "approving") {
      toast(res, "info", `该案当前是「${status}」状态，无待审批申请`);
      return;
    }
    const apprNames = [CLEARANCE_APPROVER, "陈佳聪"];
    const { targets: apprTargets } = await resolveActiveMembers(apprNames);
    const appr = apprTargets.find((t) => t.id === opId);
    if (!opId || !appr) { toast(res, "error", `仅限 ${apprNames.join("/")} 审批此卡片`); return; }
    if (choice === "agree") {
      await db.execute(
        `UPDATE event_wfs_fee_case SET status='closed', approved_by=?, approved_at=NOW() WHERE id=? AND status='approving'`,
        [appr.label, evId]);
      toast(res, "success", `已同意关闭（不追）：${String(ev.msku)}`);
    } else {
      await db.execute(
        `UPDATE event_wfs_fee_case SET status='following', approved_by=?, approved_at=NOW() WHERE id=? AND status='approving'`,
        [appr.label, evId]);
      toast(res, "success", `已驳回：${String(ev.msku)} 转回跟进中，负责人须开Case跟进`);
    }
    // 结果异步通知负责人
    const ownerName = String(ev.owner_name ?? "");
    if (ownerName) {
      const msg = choice === "agree"
        ? `【WFS费用异常】${String(ev.msku)}：你的「无需跟进」申请已由${appr.label}同意，案件关闭。`
        : `【WFS费用异常】${String(ev.msku)}：你的「无需跟进」申请被${appr.label}驳回，请到 智能PMC → WFS费用异常 填写Case号开Case跟进（每周必写跟进日志）。`;
      setImmediate(async () => {
        try {
          const token = await getNotifyTenantToken();
          const { targets: ots } = await resolveActiveMembers([ownerName]);
          if (ots[0]) await sendTextToTarget(token, ots[0], msg, true);
        } catch (e) { console.error("[card-callback] wfs_fee 结果通知失败:", e instanceof Error ? e.message : String(e)); }
      });
    }
    console.log(`[card-callback] WFS费用审批 #${evId} → ${choice} by ${appr.label}`);
  } finally {
    await db.end().catch(() => undefined);
  }
}

// ── 2026-08-12 SEM命名不合规通报确认（仅对应负责人本人或超管可点）────────────────
const SEM_NAMING_ADMINS = (process.env.SEM_NAMING_ADMINS ?? "林翔,陈佳聪")
  .split(",").map((s) => s.trim()).filter(Boolean);

async function handleSemNaming(
  res: Response,
  value: CardValue,
  operator: Record<string, unknown>,
): Promise<void> {
  const owner = String(value.owner ?? "").trim();
  const ids = String(value.ids ?? "").split(",").map((s) => Number(s.trim())).filter((n) => n > 0);
  if (!owner || !ids.length) { toast(res, "warning", "无法识别的SEM命名卡片（缺owner/ids）"); return; }
  if (value.test === 1) {
    toast(res, "success", `【测试】确认已接收（${owner}·${ids.length}个campaign，不落库）`);
    return;
  }
  const db = await getDb();
  try {
    // 点击者身份：open_id → 花名册姓名；允许=本人 或 超管名单
    const opId = String(operator.open_id ?? "");
    let actorName = "";
    if (opId) {
      const [m] = await db.query<mysql.RowDataPacket[]>(
        "SELECT name FROM dim_feishu_member WHERE open_id=? AND employment_status='active' LIMIT 1", [opId]);
      actorName = String((m as mysql.RowDataPacket[])[0]?.name ?? "");
    }
    const isSelf = actorName !== "" && actorName === owner;
    const isAdmin = actorName !== "" && SEM_NAMING_ADMINS.includes(actorName);
    if (!isSelf && !isAdmin) {
      toast(res, "error", `仅限负责人「${owner}」本人（或超管）确认此项`);
      return;
    }
    const [u] = await db.query(
      `UPDATE event_sem_naming_alert
          SET ack_status='confirmed', confirmed_at=NOW(), confirmed_by=?
        WHERE id IN (${ids.map(() => "?").join(",")}) AND owner_name=? AND ack_status='pending'`,
      [actorName + (isAdmin && !isSelf ? "(超管代确认)" : ""), ...ids, owner]);
    const n = (u as mysql.ResultSetHeader).affectedRows;
    if (n === 0) { toast(res, "info", "该负责人的通报已确认过，无需重复操作"); return; }
    console.log(`[card-callback] SEM命名确认 owner=${owner} 确认${n}项 by ${actorName}(${opId.slice(0, 9)}***)`);
    toast(res, "success", `已确认收到（${owner}·${n}个campaign）。请尽快按SKU+ItemID改名并重新导入。`);
  } catch (e) {
    console.error("[card-callback] sem_naming 处理异常:", e instanceof Error ? e.message : String(e));
    toast(res, "error", "处理失败，请稍后重试");
  } finally {
    await db.end().catch(() => undefined);
  }
}

async function handleLackAck(
  res: Response,
  value: CardValue,
  operator: Record<string, unknown>,
): Promise<void> {
  const alertId = Number(value.id ?? 0);
  if (!alertId) { toast(res, "warning", "无法识别的缺卡卡片（缺 id）"); return; }
  if (value.test === 1) {
    toast(res, "success", `【测试】确认已接收（缺卡卡片#${alertId}，不落库）`);
    return;
  }
  const db = await getDb();
  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      "SELECT id, open_id, name, lack_type, ack_status, DATE_FORMAT(stat_date,'%Y-%m-%d') AS stat_date, " +
      "(push_at <= NOW() - INTERVAL 24 HOUR) AS overdue FROM event_attendance_lack_alert WHERE id = ? LIMIT 1",
      [alertId]);
    const a = (rows as mysql.RowDataPacket[])[0];
    if (!a) { toast(res, "error", `缺卡记录 #${alertId} 不存在`); return; }
    const opId = String(operator.open_id ?? "");
    if (!opId || opId !== String(a.open_id ?? "")) {
      toast(res, "error", "仅限本人确认此缺卡提醒");
      return;
    }
    if (String(a.ack_status) === "confirmed") {
      toast(res, "info", "你已确认过该缺卡，无需重复操作");
      return;
    }
    if (String(a.ack_status) === "expired" || Number(a.overdue) === 1) {
      if (String(a.ack_status) !== "expired") {
        await db.query("UPDATE event_attendance_lack_alert SET ack_status='expired', locked_at=NOW() WHERE id=? AND ack_status='pending'", [alertId]);
      }
      res.json({
        toast: { type: "warning", content: "已超过 24 小时，无法再确认，本次缺卡按旷工计。如需补卡请线下联系人事。" },
        card: buildLackAckClosedCard(String(a.name ?? ""), String(a.stat_date ?? ""), String(a.lack_type ?? ""), "expired"),
      });
      return;
    }
    await db.query("UPDATE event_attendance_lack_alert SET ack_status='confirmed', confirmed_at=NOW() WHERE id=?", [alertId]);
    console.log(`[card-callback] 缺卡确认 #${alertId} by ${String(a.name ?? "")}(${opId.slice(0, 9)}***)`);
    res.json({
      toast: { type: "success", content: "已确认收到" },
      card: buildLackAckClosedCard(String(a.name ?? ""), String(a.stat_date ?? ""), String(a.lack_type ?? ""), "confirmed"),
    });
  } catch (e) {
    console.error("[card-callback] lack_ack 处理异常:", e instanceof Error ? e.message : String(e));
    toast(res, "error", "处理失败，请稍后重试");
  } finally {
    await db.end().catch(() => undefined);
  }
}

/** 排队/跳过标记文件路径（周维度） */
function flagPath(week: string): string {
  return path.join(STATE_DIR, `weekly_confirm_${week.replace(/[^\w-]/g, "_")}.json`);
}

// 2026-08-13 修复：只认「正式全量周报」(cron触发 + owners=all + notify mode=prod)；
// 单人/manual/test 试跑(如 weekly-2026-W33-王宁)不得视为已生成，否则确认卡直接返回不写登记，
// 导致提醒死循环 + 当晚排队检查器扫不到登记而漏生成正式周报。
async function weeklyReportExists(periodKey: string): Promise<boolean> {
  const db = await getDb();
  try {
    const [rows] = await db.execute(
      "SELECT id FROM ai_business_report WHERE report_type='weekly' AND period_key=? " +
      "AND status='success' AND trigger_source='cron' " +
      "AND JSON_UNQUOTE(JSON_EXTRACT(filter_json,'$.owners'))='all' " +
      "AND JSON_UNQUOTE(JSON_EXTRACT(notify_json,'$.mode'))='prod' LIMIT 1",
      [periodKey],
    );
    return (rows as unknown[]).length > 0;
  } finally { await db.end().catch(() => undefined); }
}

/** 异步触发：生成（全量+指定窗口）成功后自动推送；detached，日志落盘 */
function spawnGenerateAndNotify(winEnd: string, tag: string): void {
  const ts = new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14);
  const logFile = path.join(LOG_DIR, `card_report_${tag}_${ts}.log`);
  const fd = fs.openSync(logFile, "a");
  const cmd =
    `cd ${PROJECT_DIR} && python3 scripts/generate_weekly_report.py ` +
    `--win-end ${winEnd} --trigger cron ` +
    `&& npx ts-node src/sendBusinessReportNotify.ts --latest --send`;
  const child = spawn("bash", ["-lc", cmd], { detached: true, stdio: ["ignore", fd, fd] });
  child.unref();
  fs.closeSync(fd);
  console.log(`[card-callback] 已触发生成+推送（winEnd=${winEnd}），日志: ${logFile}`);
}

router.post("/", async (req: Request, res: Response): Promise<void> => {
  const expected = (process.env.FEISHU_VERIFICATION_TOKEN ?? "").trim();
  if (!expected) {
    console.error("[card-callback] FEISHU_VERIFICATION_TOKEN 未配置，拒绝所有回调");
    res.status(503).json({ error: "callback not configured" });
    return;
  }
  const body = req.body as Record<string, unknown>;

  // 1) URL 验证握手
  if (body?.type === "url_verification") {
    if (body.token !== expected) {
      console.warn("[card-callback] url_verification token 不匹配，拒绝");
      res.status(403).json({ error: "invalid token" });
      return;
    }
    res.json({ challenge: body.challenge });
    return;
  }

  // 2) 事件回调（schema 2.0）
  const header = body?.header as Record<string, unknown> | undefined;
  if (!header || header.token !== expected) {
    console.warn("[card-callback] 事件 token 不匹配或缺失，拒绝");
    res.status(403).json({ error: "invalid token" });
    return;
  }
  const eventType = String(header.event_type ?? "");
  if (eventType !== "card.action.trigger") {
    // 其他事件类型：确认收到但不处理
    res.json({});
    return;
  }
  const eventId = String(header.event_id ?? "");
  if (eventId && seenEvents.has(eventId)) {
    toast(res, "info", "该操作已处理（重复点击）");
    return;
  }
  if (eventId) {
    if (seenEvents.size >= SEEN_MAX) seenEvents.clear();
    seenEvents.add(eventId);
  }

  const event = body.event as Record<string, unknown> | undefined;
  const operator = (event?.operator as Record<string, unknown>) ?? {};
  const action = (event?.action as Record<string, unknown>) ?? {};
  const value = (action.value as CardValue) ?? {};

  try {
    // 2026-07-20 批①：清货申请审批分支
    if (value.biz === "clearance_approval") {
      await handleClearanceApproval(res, value, operator);
      return;
    }
    // 2026-07-21 批③：清货三张自动卡分支
    if (value.biz === "clearance_card") {
      await handleClearanceCard(res, value, operator);
      return;
    }
    // 2026-08-05 归档产品到货卡（恢复在售/继续归档）
    if (value.biz === "archived_restock") {
      await handleArchivedRestock(res, value, operator);
      return;
    }
    // 2026-08-10 P7数据哨兵卡（确认→系统代码白名单执行→立即复查→回报）
    // 2026-08-12 SEM命名不合规通报确认
    if (value.biz === "sem_naming") {
      await handleSemNaming(res, value, operator);
      return;
    }
    if (value.biz === "wfs_fee") {
      await handleWfsFee(res, value, operator);
      return;
    }
    if (value.biz === "sentinel_fix") {
      await handleSentinelFix(res, value, operator);
      return;
    }
    if (value.biz === "password_reset") {
      const token = String(value.token ?? "").trim();
      const formValue = (action.form_value as Record<string, unknown>) ?? {};
      const newPassword = String(formValue.new_password ?? "");
      if (!token) {
        toast(res, "warning", "缺少重置令牌，请重新发起设置密码");
        return;
      }
      if (newPassword.length < 12) {
        toast(res, "warning", `密码至少 12 位（当前 ${newPassword.length} 位）`);
        return;
      }
      const consumed = consumeResetToken(token);
      if (!consumed) {
        toast(res, "warning", "设置链接已失效，请重新发起设置密码");
        return;
      }
      const opId = String(operator.open_id ?? "");
      if (!opId || opId !== consumed.openId) {
        toast(res, "error", "仅限卡片接收本人设置密码");
        return;
      }
      const db = await getDb();
      try {
        await setPassword(db, consumed.userId, await hashPassword(newPassword));
        await writeAudit(db, {
          userId: consumed.userId,
          username: opId,
          action: "password_reset_by_card",
          ip: String(req.socket.remoteAddress ?? ""),
          ua: String(req.headers["user-agent"] ?? ""),
        });
        res.json({
          toast: { type: "success", content: "密码已设置成功" },
          card: {
            type: "raw",
            data: {
              schema: "2.0",
              config: { wide_screen_mode: true, update_multi: true },
              header: { template: "green", title: { tag: "plain_text", content: "密码设置成功" } },
              body: {
                elements: [
                  { tag: "markdown", content: "✅ **密码已设置成功**，此卡片已失效。\n请回登录页用你的用户名登录。" },
                ],
              },
            },
          },
        });
      } catch (e) {
        console.error("[card-callback] password_reset 处理异常:", e instanceof Error ? e.message : String(e));
        toast(res, "error", "密码设置失败，请稍后重试");
      } finally {
        await db.end().catch(() => undefined);
      }
      return;
    }
    // 2026-07-29 恢复回归丢失的 CS测品预警"提交原因"分支（原 07-24 实现被 7a85167 对齐生产时覆盖）
    if (value.biz === "cs_test_alert") {
      const alertId = Number(value.id ?? 0);
      const testMode = value.test === 1;
      const reason = String(((action.form_value as Record<string, unknown>) ?? {}).reason ?? "").trim();
      if (!alertId) { toast(res, "warning", "无法识别的预警卡（缺 id）"); return; }
      if (reason.length < 15) { toast(res, "warning", `预警原因需不少于 15 字（当前 ${reason.length} 字）`); return; }
      const db = await getDb();
      try {
        const [rows] = await db.query<mysql.RowDataPacket[]>(
          `SELECT id, msku, item_id, owner_name, status FROM biz_cs_test_alert WHERE id = ? LIMIT 1`, [alertId]);
        const ev = (rows as mysql.RowDataPacket[])[0];
        if (!ev) { toast(res, "error", `预警记录 #${alertId} 不存在`); return; }
        if (String(ev.status ?? "") === "resolved" && !testMode) { toast(res, "info", "该预警已填写过原因，无需重复提交"); return; }
        let fillerName = testMode ? "测试提交" : String(ev.owner_name ?? "");
        if (!testMode) {
          const allowNames = [String(ev.owner_name ?? ""), CLEARANCE_APPROVER].filter(Boolean);
          const { targets } = await resolveActiveMembers([...new Set(allowNames)]);
          const opId = String(operator.open_id ?? "");
          const hit = opId ? targets.find((t) => t.id === opId) : undefined;
          if (!hit) { toast(res, "error", `仅限 ${allowNames.join("/")} 填写此预警`); return; }
          fillerName = hit.label;
        }
        await db.query(
          `UPDATE biz_cs_test_alert SET reason = ?, reason_by = ?, reason_at = NOW(), status = 'resolved' WHERE id = ?`,
          [reason, fillerName, alertId]);
        await db.query("COMMIT");
        try {
          const token = await getNotifyTenantToken();
          const fwd = `📝 CS测品预警已填原因\n产品 ${String(ev.msku ?? "")} ｜ ItemID ${String(ev.item_id ?? "")} ｜ 负责人 ${String(ev.owner_name ?? "")}\n测品超20天或销量超11未结束\n原因：${reason}`;
          if (testMode) {
            const tc = getTestChatId();
            if (tc) await sendTextToTarget(token, { type: "chat", label: "测试群", id: tc } as NotifyTarget, `【测试】${fwd}`, true);
          } else {
            const { targets } = await resolveActiveMembers([CLEARANCE_APPROVER]);
            for (const t of targets) await sendTextToTarget(token, t, fwd, true);
          }
        } catch (fe) {
          console.warn(`[cs-test-alert] 转发审批人失败（原因已入库）：${fe instanceof Error ? fe.message : String(fe)}`);
        }
        toast(res, "success", "已记录预警原因并转发审批人，感谢填写");
      } catch (e) {
        toast(res, "error", `处理失败：${e instanceof Error ? e.message : String(e)}`);
      } finally {
        await db.end().catch(() => {});
      }
      return;
    }

    // 2026-07-30：考勤缺卡通报"确认收到"分支
    if (value.biz === "lack_ack") {
      await handleLackAck(res, value, operator);
      return;
    }
    if (value.biz !== "weekly_report_confirm" || !value.choice || !value.week || !value.winEnd) {
      toast(res, "warning", "无法识别的卡片动作");
      return;
    }
    // 测试卡片：只应答，不触发
    if (value.test === 1) {
      toast(res, "success", `【测试】动作已接收：${value.choice}（week=${value.week}，不触发生成）`);
      console.log(`[card-callback] 测试动作: ${JSON.stringify(value)}`);
      return;
    }
    // 操作人校验：仅指定负责人
    // 2026-07-23 批4：操作人白名单扩为 主确认人+兜底人，任一确认均有效（兜底防漏）
    const allowedNames = [RECIPIENT, ...CONFIRM_BACKUPS];
    const { targets } = await resolveActiveMembers(allowedNames);
    const opId = String(operator.open_id ?? "");
    const opHit = opId ? targets.find((t) => t.id === opId) : undefined;
    if (!opHit) {
      toast(res, "error", `仅限 ${allowedNames.join("/")} 操作此卡片`);
      return;
    }
    // 业务级幂等
    const week = String(value.week);
    const fp = flagPath(week);
    if (await weeklyReportExists(week)) {
      // 2026-08-13 修复：先落 .done 登记再返回，否则提醒逻辑(只认登记文件)会永远判"未确认"而死循环
      try {
        if (!fs.existsSync(fp) && !fs.readdirSync(STATE_DIR).some((f) => f.startsWith(`${path.basename(fp)}.done`))) {
          fs.mkdirSync(STATE_DIR, { recursive: true });
          fs.writeFileSync(`${fp}.done.${new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14)}`,
            JSON.stringify({ biz: "weekly_report_confirm", week, choice: value.choice,
              note: "already_generated_auto_closed", at: new Date().toISOString() }, null, 1));
        }
      } catch (e) {
        console.error("[card-callback] 已生成过分支补登记失败:", e instanceof Error ? e.message : String(e));
      }
      toast(res, "info", `${week} 周报已生成过，已停止本周提醒；如需补发请到报表中心操作`);
      return;
    }
    if (fs.existsSync(fp)) {
      const prev = JSON.parse(fs.readFileSync(fp, "utf8")) as { choice?: string };
      toast(res, "info", `本周已登记选择「${prev.choice}」，如需变更请联系管理员删除登记`);
      return;
    }
    fs.mkdirSync(STATE_DIR, { recursive: true });
    const record = {
      biz: "weekly_report_confirm", week, choice: value.choice, winEnd: value.winEnd,
      operator: opId.slice(0, 9) + "***", operator_name: opHit.label, at: new Date().toISOString(),
    };
    fs.writeFileSync(fp, JSON.stringify(record, null, 1));

    if (value.choice === "friday") {
      // 2026-07-23 批4：周五开会改为登记制，周四19:30（数据链19:10收口后）由排队检查器统一生成，
      // 保证窗口尾日（周二）数据完整。仅当点击时已过本周四19:30（检查器已跑过）才立即生成兜底，
      // 且立即生成后马上把登记标记为已消费，防止后续检查器重复生成。
      const nowD = new Date();
      const dowD = nowD.getDay();
      const lateForThursdaySlot =
        dowD > 4 || (dowD === 4 && (nowD.getHours() > 19 || (nowD.getHours() === 19 && nowD.getMinutes() >= 30)));
      if (lateForThursdaySlot) {
        spawnGenerateAndNotify(String(value.winEnd), week);
        try {
          fs.renameSync(fp, `${fp}.done.${new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14)}`);
        } catch (e) {
          console.error("[card-callback] 迟点立即生成后标记已消费失败:", e instanceof Error ? e.message : String(e));
        }
        toast(res, "success", `已开始生成 ${week} 周报（窗口至${value.winEnd}，数据已收口），完成后自动推送到群和各负责人`);
      } else {
        toast(res, "success", `已登记周五开会：今晚19:30数据收口后自动生成 ${week} 周报（窗口至${value.winEnd}）并推送`);
      }
    } else if (value.choice === "saturday") {
      toast(res, "success", `已登记周六开会：周五19:30数据收口后自动生成 ${week} 周报（窗口至${value.winEnd}）并推送`);
    } else if (value.choice === "skip") {
      toast(res, "success", `已登记：本周不生成周报（${week}）`);
    } else {
      toast(res, "warning", `未知选项: ${value.choice}`);
    }
  } catch (e: unknown) {
    console.error("[card-callback] 处理异常:", e instanceof Error ? e.message : String(e));
    toast(res, "error", "处理失败，请查看服务日志");
  }
});

export default router;
