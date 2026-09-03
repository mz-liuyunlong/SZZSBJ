/**
 * checkCostConfigMissing.ts — 成本配置缺失/异常周报（2026-08-19 需求方指令，批B-12）
 *
 * 口径：近30天（锚点=fact_profit_daily最新业务日）「有销量但采购成本或头程成本快照为0」的品，
 *   按 店铺+MSKU 汇总，并对照 dim_product_cost_config 当前配置值自动定性三类：
 *     ①【未配置】当前配置为NULL → 运营需新建成本配置；
 *     ②【配置异常】当前配置存在但可疑（采购或头程≤0，或采购≥100且头程≤1的占位式填法）→ 需核实真实成本；
 *     ③【补录晚】当前配置正常 → 销售当天尚未配置，历史不回改，无需处理（仅统计不列明细）。
 *   CS测品(msku LIKE 'CS%')与人工作废名单不通报。
 * 铁律：只读（零写库）；通报走 feishuNotify 共享件；按通报测试铁律，--test-send 先测试群。
 * 用法：
 *   npx ts-node src/checkCostConfigMissing.ts                # dry-run 零发送
 *   npx ts-node src/checkCostConfigMissing.ts --test-send    # 仅发测试群
 *   npx ts-node src/checkCostConfigMissing.ts --group-send   # 真发目标群（cron用）
 * cron（需求方确认后挂）：每周一 09:00
 */
import "dotenv/config";
import * as mysql from "mysql2/promise";
import { NotifyTarget, getTestChatId, sendCardToTarget, resolveActiveMembers } from "./feishuNotify";

const GROUP_CHAT_ID = (process.env.COST_CONFIG_CHAT_ID ?? "oc_56f24aa35fa4adf629e2e48616f7c54e").trim(); // 2026-08-19需求方指定群
const MANUAL_EXCLUDE_ITEMS = new Set<string>(["20090164596", "20706361834"]); // 与 orderProfitV2Routes 同步维护

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
const n2 = (v: number): string => (Number.isFinite(v) ? v : 0).toFixed(2);

interface Row {
  store_id: string; store_name: string; msku: string; item_id: string;
  days: number; sales: number; qty: number; first_d: string; last_d: string;
  cfg_pc: number | null; cfg_fl: number | null; owner: string;
}
type Kind = "未配置" | "配置异常" | "补录晚";
function classify(r: Row): Kind {
  if (r.cfg_pc === null || r.cfg_fl === null) return "未配置";
  if (r.cfg_pc <= 0 || r.cfg_fl <= 0) return "配置异常";
  if (r.cfg_pc >= 100 && r.cfg_fl <= 1) return "配置异常"; // 占位式填法（如采购200/头程1）
  return "补录晚";
}

async function main(): Promise<void> {
  const testSend = process.argv.includes("--test-send");
  const groupSend = process.argv.includes("--group-send");
  const doSend = testSend || groupSend;
  const db = await getDb();
  try {
    const [mx] = await db.execute(`SELECT DATE_FORMAT(MAX(stat_date),'%Y-%m-%d') d FROM fact_profit_daily WHERE platform='walmart'`);
    const anchor = String((mx as Array<Record<string, unknown>>)[0]?.d ?? "");
    const [rowsRaw] = await db.execute(
      `SELECT f.store_id, MAX(COALESCE(s.store_name, f.store_id)) store_name, f.msku,
              MAX(f.item_id) item_id, COUNT(*) days,
              ROUND(SUM(f.sales_amount),2) sales,
              SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(f.extra_json,'$.sales_qty')) AS DECIMAL(12,2))) qty,
              DATE_FORMAT(MIN(f.stat_date),'%Y-%m-%d') first_d, DATE_FORMAT(MAX(f.stat_date),'%Y-%m-%d') last_d,
              (SELECT MAX(c.purchase_cost) FROM dim_product_cost_config c
                 WHERE c.msku=f.msku AND c.store_id=f.store_id) cfg_pc,
              (SELECT MAX(c.first_mile_shipping_cost) FROM dim_product_cost_config c
                 WHERE c.msku=f.msku AND c.store_id=f.store_id) cfg_fl,
              (SELECT MAX(COALESCE(d.owner,'')) FROM dim_product d
                 WHERE d.platform='walmart' AND d.store_id=f.store_id AND d.msku=f.msku) owner
       FROM fact_profit_daily f
       LEFT JOIN dim_store s ON s.platform='walmart' AND s.store_id=f.store_id
       WHERE f.platform='walmart' AND f.stat_date >= DATE_SUB(?, INTERVAL 30 DAY)
         AND f.msku NOT LIKE 'CS%'
         AND CAST(JSON_UNQUOTE(JSON_EXTRACT(f.extra_json,'$.sales_qty')) AS DECIMAL(12,2)) > 0
         AND (CAST(JSON_UNQUOTE(JSON_EXTRACT(f.extra_json,'$.purchase_cost_cny')) AS DECIMAL(12,2)) = 0
              OR CAST(JSON_UNQUOTE(JSON_EXTRACT(f.extra_json,'$.first_leg_cost_cny')) AS DECIMAL(12,2)) = 0)
       GROUP BY f.store_id, f.msku ORDER BY sales DESC`, [anchor]);
    const all: Row[] = (rowsRaw as Array<Record<string, unknown>>).map((r) => ({
      store_id: String(r.store_id), store_name: String(r.store_name), msku: String(r.msku),
      item_id: String(r.item_id ?? ""), days: Number(r.days ?? 0), sales: Number(r.sales ?? 0),
      qty: Number(r.qty ?? 0), first_d: String(r.first_d), last_d: String(r.last_d),
      cfg_pc: r.cfg_pc === null || r.cfg_pc === undefined ? null : Number(r.cfg_pc),
      cfg_fl: r.cfg_fl === null || r.cfg_fl === undefined ? null : Number(r.cfg_fl),
      owner: String(r.owner ?? "").trim(),
    })).filter((r) => !MANUAL_EXCLUDE_ITEMS.has(r.item_id));

    const need = all.filter((r) => classify(r) !== "补录晚");
    const late = all.filter((r) => classify(r) === "补录晚");
    const needSales = need.reduce((a, r) => a + r.sales, 0);
    console.log(`锚点=${anchor}｜近30天缺成本品 ${all.length} 个（需处理 ${need.length}｜补录晚 ${late.length}）｜需处理涉及销售额 $${n2(needSales)}`);

    if (need.length === 0) {
      console.log("SUMMARY_JSON=" + JSON.stringify({ anchor, total: all.length, need: 0, late: late.length, sent: false, status: "success" }));
      return; // 无需处理项不打扰
    }

    // 负责人 open_id 解析（在册+active+有open_id 才@，查不到只显示姓名，禁猜测）
    const ownerNames = Array.from(new Set(need.map((r) => r.owner).filter(Boolean)));
    const { targets: ownerTargets, warnings } = await resolveActiveMembers(ownerNames);
    const openIdByName = new Map(ownerTargets.map((t) => [t.label, t.id]));
    for (const w of warnings) console.log(`  ⚠️ ${w}`);
    const mention = (name: string): string => {
      if (!name) return "未分配负责人";
      const oid = openIdByName.get(name);
      return oid ? `<at id="${oid}">${name}</at>` : name;
    };

    const lines = need.map((r) => {
      const kind = classify(r);
      const cfg = kind === "未配置" ? "无成本配置" : `采购¥${n2(r.cfg_pc ?? 0)}/头程¥${n2(r.cfg_fl ?? 0)}`;
      return `**${r.msku}**（${r.store_name}）${mention(r.owner)}\n　${kind}：${cfg}`;
    });
    const md = `以下产品有销量但成本没配好，请到产品管理补齐/改正：\n\n${lines.join("\n\n")}`;
    const card = {
      config: { wide_screen_mode: true },
      header: { title: { tag: "plain_text", content: "💰 成本配置待补（订单利润V2）" }, template: "orange" },
      elements: [{ tag: "div", text: { tag: "lark_md", content: md } }],
    };
    const target: NotifyTarget = groupSend && GROUP_CHAT_ID
      ? { type: "chat", label: "目标群", id: GROUP_CHAT_ID }
      : { type: "chat", label: "测试群", id: getTestChatId() };
    const result = await sendCardToTarget(target, card, md.replace(/\*\*/g, ""), doSend);
    console.log(`发送结果：${result.ok ? "✅" : "❌ " + (result.error ?? "")}（${target.label}）`);
    console.log("SUMMARY_JSON=" + JSON.stringify({
      anchor, total: all.length, need: need.length, late: late.length,
      need_sales: Math.round(needSales * 100) / 100, sent: doSend, target: target.label,
      ok: result.ok, status: "success",
    }));
  } finally {
    await db.end();
  }
}
main().catch((e) => { console.error("FATAL:", e instanceof Error ? e.message : String(e)); process.exit(1); });
