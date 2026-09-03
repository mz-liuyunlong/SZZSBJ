/**
 * probeOrderList.ts — 只读探测：多平台订单管理订单列表接口（2026-08-14，V2折扣数据源验证）
 * 接口：POST /pb/mp/order/v2/list（业务端订单管理，按更新时间查询，31天窗，令牌桶10）
 * 零写入：①近24h Walmart 订单样本（总量/状态分布）②0元促销单精查（验折扣字段）
 *        ③截图正常单精查（金额/税/交易费/利润逐项对照）④顶层字段清单（找退款/售后信号）
 */
import "dotenv/config";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const PATH = "/pb/mp/order/v2/list";

async function query(client: LingxingClient, params: Record<string, unknown>): Promise<Array<Record<string, unknown>>> {
  const resp = await client.request<{ list?: Array<Record<string, unknown>>; total?: number }>({
    method: "POST", path: PATH, params, timeoutMs: 30000,
  });
  const d = resp?.data as { list?: Array<Record<string, unknown>>; total?: number } | undefined;
  console.log(`  total=${d?.total ?? "?"} 返回=${d?.list?.length ?? 0}`);
  return d?.list ?? [];
}

function brief(o: Record<string, unknown>): string {
  const t = (o.transaction_info ?? {}) as Record<string, unknown>;
  return `单号=${o.platform_order_no ?? o.reference_no} 状态=${o.status} 发货方式=${o.delivery_type} ` +
    `总额=${t.order_total_amount} 商品=${t.order_item_amount} 折扣=${t.discount_amount} ` +
    `交易费=${t.transaction_fee_amount} 客付税=${t.customer_tax_amount_show} 利润=${t.profit_amount}`;
}

async function main(): Promise<void> {
  const cfg = loadConfig();
  const client = new LingxingClient(cfg);
  const now = Math.floor(Date.now() / 1000);

  console.log("== ① 近24h Walmart 订单（update_time窗）==");
  const recent = await query(client, {
    offset: 0, length: 50, date_type: "update_time",
    start_time: now - 86400, end_time: now, platform_code: ["10008"],
  });
  const stCount = new Map<string, number>();
  for (const o of recent) {
    const k = `status=${o.status}|delivery=${o.delivery_type}`;
    stCount.set(k, (stCount.get(k) ?? 0) + 1);
  }
  for (const [k, v] of stCount) console.log(`  ${k} × ${v}`);
  if (recent[0]) console.log("  样例: " + brief(recent[0]));

  console.log("\n== ② 0元促销单精查 119121314432531 ==");
  const promo = await query(client, { offset: 0, length: 20, platform_order_nos: ["119121314432531"] });
  for (const o of promo) console.log("  " + brief(o));
  if (promo[0]) console.log("整单JSON（截断8000字）:\n" + JSON.stringify(promo[0], null, 1).slice(0, 8000));

  console.log("\n== ③ 截图正常单精查 119122258104573（对照:商品17.99/税1.26/交易费-2.16/利润13.90）==");
  const normal = await query(client, { offset: 0, length: 20, platform_order_nos: ["119122258104573"] });
  for (const o of normal) console.log("  " + brief(o));
  if (normal[0]) {
    const t = (normal[0].transaction_info ?? {}) as Record<string, unknown>;
    console.log("  transaction_info全量: " + JSON.stringify(t));
  }

  console.log("\n== ④ 顶层字段清单（判断有无退款/售后信号）==");
  const sample = promo[0] ?? normal[0] ?? recent[0];
  if (sample) console.log("  keys: " + Object.keys(sample).join(", "));

  console.log("\nPROBE_DONE（零写入）");
}

main().catch((e) => { console.error("FATAL:", e instanceof Error ? e.message : String(e)); process.exit(1); });
