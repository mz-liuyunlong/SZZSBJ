/**
 * clearanceApprovalNotify.ts - 清货申请审批汇总卡（批①，2026-07-20 需求方定稿）
 *
 * 数据流：event_clearance_approval (status=pending)
 *        → 🧹 汇总卡（每申请一分区+同意/驳回按钮）→ 审批人（CLEARANCE_APPROVER，默认 林翔）
 * 回调：feishuCardCallbackRoutes biz=clearance_approval（同意=写清货期/驳回=私信申请人）
 *
 * 模式（批B规范）：
 *   默认 dry-run（零发送零回写）；--send 发审批人并回写 notify_count/last_notified_at；
 *   --test-send 卡片发测试群、按钮带 test=1（回调只应答）、不回写。
 * 体积：每卡最多 CHUNK=10 个申请，超出拆多张卡。
 * cron（部署时加）：33 9 * * * npx ts-node src/clearanceApprovalNotify.ts --send
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { getTestChatId, resolveActiveMembers, sendCardToTarget, SendResult } from "./feishuNotify";
import { buildClearanceApprovalCard, ClearanceApprovalItem } from "./notifyRules/reminderCards";

const SCRIPT_NAME = "clearanceApprovalNotify";
const CHUNK = 10;
const APPROVER = (process.env.CLEARANCE_APPROVER ?? "林翔").trim();

const doSend = process.argv.includes("--send");
const testSend = process.argv.includes("--test-send");
if (doSend && testSend) {
  console.log("[错误] --send 与 --test-send 禁止同时使用");
  process.exit(1);
}

function cstToday(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai" }).format(new Date());
}

async function main(): Promise<void> {
  const mode = testSend ? "test-send（测试群，按钮test=1）" : doSend ? "真实发送" : "dry-run";
  console.log("=".repeat(60));
  console.log(`清货申请审批卡 模式=${mode} 审批人=${APPROVER}`);
  console.log("=".repeat(60));

  const db = await mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
    dateStrings: true,
  });

  try {
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT id, store_name, store_id, item_id, mskus, sku, owner, applicant, metrics_json
       FROM event_clearance_approval WHERE status = 'pending' ORDER BY id ASC`,
    );
    console.log(`待审批申请: ${rows.length}`);
    if (!rows.length) {
      if (testSend) {
        const r = await sendCardToTarget(
          { type: "chat", label: "测试群", id: getTestChatId() },
          buildClearanceApprovalCard(cstToday(), [], { testMode: true }).card,
          "【测试】清货审批链路验证：当前无待审批申请。", true,
        );
        console.log(`[test-send] 空卡结果 ok=${r.ok}`);
        if (r.ok) console.log("NOTIFY_TEST_SENT=1");
      }
      return;
    }

    const items: ClearanceApprovalItem[] = rows.map((r) => {
      const m = (typeof r.metrics_json === "object" && r.metrics_json ? r.metrics_json : {}) as Record<string, unknown>;
      return {
        id: Number(r.id),
        storeName: String(r.store_name || r.store_id || "-"),
        itemId: String(r.item_id),
        mskus: String(r.mskus || "-"),
        sku: String(r.sku || ""),
        owner: String(r.owner || "-"),
        applicant: String(r.applicant || "-"),
        sales30: Number(m.sales30 ?? 0),
        stock: Number(m.stock ?? 0),
        inbound: Number(m.inbound ?? 0),
        turnoverDays: m.turnoverDays === null || m.turnoverDays === undefined ? null : Number(m.turnoverDays),
      };
    });

    const chunks: ClearanceApprovalItem[][] = [];
    for (let i = 0; i < items.length; i += CHUNK) chunks.push(items.slice(i, i + CHUNK));

    const results: SendResult[] = [];
    let anyFail = false;

    if (testSend) {
      for (const [ci, chunk] of chunks.entries()) {
        const bundle = buildClearanceApprovalCard(cstToday(), chunk, { testMode: true });
        const r = await sendCardToTarget(
          { type: "chat", label: `测试群(审批卡${ci + 1}/${chunks.length})`, id: getTestChatId() },
          bundle.card, bundle.fallbackText, true,
        );
        results.push(r);
        if (!r.ok) anyFail = true;
      }
      console.log(`[test-send] 发送 ${results.filter((r) => r.ok).length}/${results.length} 张卡，不回写 notify_count`);
      if (!anyFail) console.log("NOTIFY_TEST_SENT=1");
      else process.exitCode = 1;
      return;
    }

    const { targets, warnings } = await resolveActiveMembers([APPROVER]);
    for (const w of warnings) console.log(`  [花名册] ${w}`);
    const target = targets.find((t) => t.label === APPROVER);
    if (doSend && !target) {
      console.log(`[错误] 审批人「${APPROVER}」花名册未命中，本次不发送`);
      process.exitCode = 1;
      return;
    }

    for (const [ci, chunk] of chunks.entries()) {
      const bundle = buildClearanceApprovalCard(cstToday(), chunk, {});
      const r = await sendCardToTarget(
        target ?? { type: "user", label: APPROVER, id: "" },
        bundle.card, bundle.fallbackText, doSend,
      );
      results.push(r);
      if (!r.ok) { anyFail = true; continue; }
      if (doSend) {
        await db.query(
          `UPDATE event_clearance_approval
           SET notify_count = notify_count + 1, last_notified_at = NOW()
           WHERE id IN (${chunk.map(() => "?").join(",")})`,
          chunk.map((c) => c.id),
        );
      }
      console.log(`  卡片 ${ci + 1}/${chunks.length}：${chunk.length} 项${doSend ? "，notify_count 已回写" : "（dry-run 不回写）"}`);
    }

    if (anyFail) process.exitCode = 1;
    if (!doSend) console.log("[dry-run] 零发送零回写，加 --send 生产发送。");
  } finally {
    await db.end().catch(() => {});
  }
}

main().catch((e) => {
  console.error(`${SCRIPT_NAME} 失败:`, e instanceof Error ? e.message : String(e));
  process.exit(1);
});
