/**
 * checkSemNamingDeduction.ts — SEM命名整改结算扣分 + 扣分通报（2026-08-12 需求方两次拍板后定稿）
 *
 * 核心口径（需求方纠正版）：
 *   - 不合规期间产品未知→负责人未知→**绝不猜测、绝不预扣**。
 *   - 「处理完再扣」：campaign改名+重新导入、ItemID解析成功（alert状态open→resolved）的那一刻，
 *     负责人才100%确定（最新数据行ItemID→dim_product.owner）——此时结算扣分：
 *       扣分 = 5分 × 拖延天数。
 *   - 拖延天数=实证口径（2026-08-19 方案B，需求方拍板）：最后一次观测到不合规的检测日 − 首次发现日——
 *     只对有观测证据的天数计费；检测流水线固有的+1天滞后（改名要等次日导入才被看见）不再误扣。
 *     历史行无 last_open_check_date 时回退 max(0, DATEDIFF(resolved_at, first_seen_date)−1) 等价冲抵。
 *   - 双开关（2026-08-19 方案B）：凡实际发出通报即写事件结算（penalty_at/penalty_points，杜绝同批每日重发）；
 *     --confirm-write 只控制是否落绩效台账 biz_perf_deduction（8/20转正式=cron加 --confirm-write --send-group）。
 *   - 「扣完直接发通报」：扣分写入后立即发群通报卡 + 私信本人。
 *   - 幂等：alert行 penalty_at 标记只结算一次；镜像 biz_perf_deduction
 *     (biz_type='sem_naming_unresolved', ref_event_id=alert.id) 靠 uq_perf_ref 防重。
 *   - 同负责人同日多个campaign结算：扣分逐campaign计算后合并为一行通报；发送窗口08:00-22:00。
 *
 * 用法（通报测试铁律）：
 *   npx ts-node src/checkSemNamingDeduction.ts                          # dry-run：零写入零发送
 *   npx ts-node src/checkSemNamingDeduction.ts --confirm-write --test-send   # 写扣分+通报只发测试群
 *   npx ts-node src/checkSemNamingDeduction.ts --confirm-write --send-group  # 真发运营群+私信本人
 *
 * 写入范围：event_sem_naming_alert(penalty_*列/owner_name实锤回填) / biz_perf_deduction(INSERT IGNORE)。
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { NotifyTarget, getTestChatId, getNotifyTenantToken, resolveActiveMembers, sendCardToTarget, sendTextToTarget } from "./feishuNotify";

const GROUP_CHAT_ID = (process.env.SEM_NAMING_CHAT_ID ?? "oc_f995c8554d2bf71abf4703396203c9f6").trim();
const POINTS_PER_DAY = 5;
const PAGE_URL = "http://42.193.254.170:3000/walmart-sem";
const WINDOW_START = 8, WINDOW_END = 22;

function dbConfig(): mysql.ConnectionOptions {
  return { host: process.env.DB_HOST ?? "127.0.0.1", port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "", password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data", dateStrings: true };
}
function cstHour(): number { return new Date(Date.now() + 8 * 3600 * 1000).getUTCHours(); }
function todayCst(): string { return new Date(Date.now() + 8 * 3600 * 1000).toISOString().slice(0, 10); }

interface Settle {
  alertId: number; storeId: string; storeName: string; campaignId: string; campaignName: string;
  itemId: string; owner: string; delayDays: number; points: number;
}

function buildCard(today: string, byOwner: Map<string, Settle[]>, test: boolean): { card: Record<string, unknown>; fb: string } {
  const lines: string[] = [];
  for (const [owner, list] of byOwner) {
    const pts = list.reduce((s, x) => s + x.points, 0);
    const det = list.map((x) => `${x.campaignName}(拖${x.delayDays}天)`).join("、");
    lines.push(pts > 0
      ? `**${owner}**　扣 **${pts} 分**：${det}`
      : `**${owner}**　✅ 当天整改不扣分：${det}`);
  }
  const card = {
    config: { wide_screen_mode: true },
    header: { template: "orange", title: { tag: "plain_text", content: `${test ? "【测试】" : ""}📉 SEM命名整改结算通报 ${today}` } },
    elements: [
      { tag: "div", text: { tag: "lark_md", content:
        "以下campaign已改名整改、归属实锤，按制度结算（**5分×拖延天数**，当天整改不扣）：\n\n" + lines.join("\n") } },
      { tag: "note", elements: [{ tag: "plain_text", content:
        "扣分已计入绩效台账（biz_type=sem_naming_unresolved）；异议可在绩效台账人工层申诉豁免。" }] },
    ],
  };
  const fb = `【SEM命名整改结算】${today}：` +
    [...byOwner.entries()].map(([o, l]) => `${o}${l.reduce((s, x) => s + x.points, 0)}分`).join("、");
  return { card, fb };
}

async function main(): Promise<void> {
  const confirmWrite = process.argv.includes("--confirm-write");
  const testSend = process.argv.includes("--test-send");
  const groupSend = process.argv.includes("--send-group");
  const doSend = testSend || groupSend;
  const today = todayCst();
  console.log("=".repeat(64));
  console.log(`SEM命名整改结算 | ${today} | ${confirmWrite ? "写入" : "dry-run零写入"} | ${groupSend ? "真发运营群+私信" : testSend ? "仅测试群" : "零发送"}`);
  console.log("=".repeat(64));

  const db = await mysql.createConnection(dbConfig());
  try {
    // 已整改且未结算的alert
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT a.id, a.store_id, a.store_name, a.campaign_id, a.campaign_name,
              DATE_FORMAT(a.first_seen_date,'%Y-%m-%d') AS first_seen,
              DATE_FORMAT(a.resolved_at,'%Y-%m-%d') AS resolved_day,
              GREATEST(0, COALESCE(
                DATEDIFF(a.last_open_check_date, a.first_seen_date),
                DATEDIFF(a.resolved_at, a.first_seen_date) - 1)) AS delay_days
         FROM event_sem_naming_alert a
        WHERE a.status='resolved' AND a.penalty_at IS NULL`);
    if (!(rows as mysql.RowDataPacket[]).length) { console.log("无待结算的整改campaign。"); return; }

    const settles: Settle[] = [];
    for (const r of rows) {
      // 负责人实锤：整改后最新数据行的ItemID → dim_product.owner（唯一命中才算；命不中留待人工）
      const [it] = await db.query<mysql.RowDataPacket[]>(
        `SELECT item_id FROM fact_ads_product_daily
          WHERE platform='walmart' AND store_id=? AND campaign_id=? AND campaign_type='sem' AND COALESCE(item_id,'')<>''
          ORDER BY stat_date DESC LIMIT 1`, [String(r.store_id), String(r.campaign_id)]);
      const itemId = String((it as mysql.RowDataPacket[])[0]?.item_id ?? "");
      let owner = "";
      if (itemId) {
        const [os] = await db.query<mysql.RowDataPacket[]>(
          `SELECT DISTINCT owner FROM dim_product
            WHERE platform='walmart' AND store_id=? AND item_id=? AND COALESCE(owner,'')<>''`,
          [String(r.store_id), itemId]);
        if ((os as mysql.RowDataPacket[]).length === 1) owner = String((os as mysql.RowDataPacket[])[0].owner);
      }
      const delay = Math.max(0, Number(r.delay_days ?? 0));
      if (!owner) {
        console.log(`  ⚠️ ${r.campaign_name}（${r.store_name}）ItemID=${itemId || "?"} 负责人无唯一命中，留待人工（不结算不扣分）`);
        continue;
      }
      settles.push({ alertId: Number(r.id), storeId: String(r.store_id), storeName: String(r.store_name ?? ""),
        campaignId: String(r.campaign_id), campaignName: String(r.campaign_name ?? ""), itemId, owner,
        delayDays: delay, points: POINTS_PER_DAY * delay });
      console.log(`  ${r.campaign_name}（${r.store_name}）→ ItemID ${itemId} → 负责人 ${owner}，拖延${delay}天 → 扣${POINTS_PER_DAY * delay}分`);
    }
    if (!settles.length) { console.log("本轮无可结算项（负责人均未唯一命中）。"); return; }

    const byOwner = new Map<string, Settle[]>();
    for (const s of settles) { if (!byOwner.has(s.owner)) byOwner.set(s.owner, []); byOwner.get(s.owner)!.push(s); }

    let sentOk = false;
    const h = cstHour();
    if (doSend && (h >= WINDOW_END || h < WINDOW_START)) {
      console.log(`当前CST ${h}点在发送窗口外，跳过发送（本轮不结算，待窗口内发出通报再结算）。`);
    } else if (doSend) {
      const { card, fb } = buildCard(today, byOwner, !groupSend);
      const target: NotifyTarget = groupSend
        ? { type: "chat", label: "运营群", id: GROUP_CHAT_ID }
        : { type: "chat", label: "测试群", id: getTestChatId() };
      const r = await sendCardToTarget(target, card, fb, true);
      sentOk = r.ok;
      console.log(`结算通报：${r.ok ? "✅" : "❌ " + (r.error ?? "")}（${target.label}）`);
      if (groupSend) {
        const owners = [...byOwner.keys()];
        const { targets, warnings } = await resolveActiveMembers(owners);
        for (const w of warnings) console.log(`  ⚠️ ${w}`);
        const token = await getNotifyTenantToken();
        for (const t of targets) {
          const list = byOwner.get(t.label) ?? [];
          const pts = list.reduce((s, x) => s + x.points, 0);
          if (!list.length) continue;
          const msg = pts > 0
            ? `【SEM命名扣分】你的campaign整改归属已确认，因命名不合规拖延，合计扣${pts}分：` +
              list.map((x) => `${x.campaignName}(拖${x.delayDays}天扣${x.points}分)`).join("、") +
              `。已计入绩效台账，异议可申诉豁免。`
            : `【SEM命名整改确认】你的campaign已当天整改完成，不扣分：` + list.map((x) => x.campaignName).join("、") + `。`;
          const pr = await sendTextToTarget(token, t, msg, true);
          console.log(`  私信${t.label}: ${pr.ok ? "✅" : "❌"}`);
        }
      }
    }
    // 方案B双开关：通报实际发出（或无发送标志的人工 --confirm-write 补账）→ 写事件结算终止重发；
    // 绩效台账只在 --confirm-write 时镜像（测试期只结算不扣真分）。
    let written = 0, perfWritten = 0;
    const settleNow = sentOk || (confirmWrite && !doSend);
    if (settleNow) {
      for (const s of settles) {
        await db.query(
          `UPDATE event_sem_naming_alert SET owner_name=?, penalty_points=?, penalty_at=NOW() WHERE id=? AND penalty_at IS NULL`,
          [s.owner, s.points, s.alertId]);
        written++;
        if (confirmWrite && s.points > 0) {
          await db.execute(
            `INSERT IGNORE INTO biz_perf_deduction
               (deduction_date, owner_name, points, entry_type, biz_type, platform, store_id, item_id, msku, ref_event_id, note, created_by)
             VALUES (?, ?, ?, 'deduct', 'sem_naming_unresolved', 'walmart', ?, ?, '', ?, ?, 'checkSemNamingDeduction')`,
            [today, s.owner, s.points, s.storeId, s.itemId, s.alertId,
             `SEM命名不合规拖延${s.delayDays}天(${s.campaignName})`]);
          perfWritten++;
        }
      }
      console.log(`事件结算：${written}个campaign（penalty标记写入，终止重发）；绩效台账镜像：${perfWritten}条${confirmWrite ? "" : "（未带--confirm-write，测试期不扣真分）"}`);
    } else if (settles.length) {
      console.log("本轮未发出通报（dry-run或发送失败/窗口外），不结算不写入。");
    }
    console.log("SUMMARY_JSON=" + JSON.stringify({
      today, mode: confirmWrite ? "write" : "dry-run", channel: groupSend ? "group" : testSend ? "test" : "none",
      settled: settles.length, written, perf_written: perfWritten, sent_ok: sentOk, owners: byOwner.size,
      total_points: settles.reduce((s, x) => s + x.points, 0),
    }));
  } finally {
    await db.end().catch(() => undefined);
  }
}

main().catch((err) => { console.error("SEM命名整改结算失败：", err); process.exit(1); });
