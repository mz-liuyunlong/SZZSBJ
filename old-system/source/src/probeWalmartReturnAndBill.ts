/**
 * probeWalmartReturnAndBill.ts — 只读探测：Walmart售后订单列表 + 结算账单列表（2026-08-14）
 * ①售后 /basicOpen/openapi/multiplatform/walmart/returnOrder/list：近14天按售后时间拉，
 *   按日退货量/退款金额分布 + 类型/状态分布 + 2条完整样本 → 验证退货日更源
 * ②账单 /basicOpen/multiplatformFinance/walmart/bill/statement/list：近30天无类型过滤翻页聚合，
 *   transactionType × amountType × description 全清点（行数+金额）→ 费用类目全景供需求方评估
 *   另按 transactionTypes=["Service Fee"] 单独拉一页找仓储费证据。
 * 零写入，只打印。令牌桶=1，请求间隔1500ms。
 */
import "dotenv/config";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const RETURN_PATH = "/basicOpen/openapi/multiplatform/walmart/returnOrder/list";
const BILL_PATH = "/basicOpen/multiplatformFinance/walmart/bill/statement/list";
const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));
function d(offsetDays: number): string {
  return new Date(Date.now() + 8 * 3600 * 1000 + offsetDays * 86400 * 1000).toISOString().slice(0, 10);
}

async function main(): Promise<void> {
  const cfg = loadConfig();
  const client = new LingxingClient(cfg);

  // ── ① 售后订单列表：近14天 ──
  console.log(`== ① 售后订单列表 近14天（dateType=1 售后时间）==`);
  const returns: Array<Record<string, unknown>> = [];
  for (let page = 1; page <= 10; page++) {
    const resp = await client.request<{ list?: Array<Record<string, unknown>>; total?: number }>({
      method: "POST", path: RETURN_PATH,
      params: { startDate: d(-14), endDate: d(0), dateType: 1, pageNum: page, pageSize: 100 },
      timeoutMs: 30000,
    });
    const dd = resp?.data as { list?: Array<Record<string, unknown>>; total?: number } | undefined;
    const list = dd?.list ?? [];
    if (page === 1) console.log(`total=${dd?.total ?? "?"}`);
    returns.push(...list);
    if (list.length < 100) break;
    await sleep(1500);
  }
  console.log(`拉取售后单 ${returns.length} 条`);
  const byDay = new Map<string, { orders: number; qty: number; amt: number }>();
  const byType = new Map<string, number>();
  for (const r of returns) {
    const day = String(r.returnOrderDate ?? "").slice(0, 10);
    const a = byDay.get(day) ?? { orders: 0, qty: 0, amt: 0 };
    a.orders += 1;
    for (const it of (r.items as Array<Record<string, unknown>> ?? [])) {
      a.qty += Number(it.quantityDisplay ?? 0);
      a.amt += Number(it.lineTotalAmount ?? 0);
    }
    byDay.set(day, a);
    const t = `${r.returnType}|${((r.items as Array<Record<string, unknown>>)?.[0]?.status) ?? "?"}`;
    byType.set(t, (byType.get(t) ?? 0) + 1);
  }
  console.log("按售后日分布（日｜单数｜件数｜退款额）:");
  for (const [k, v] of [...byDay.entries()].sort()) console.log(`${k}\t${v.orders}\t${v.qty}\t${Math.round(v.amt * 100) / 100}`);
  console.log("类型|状态分布:");
  for (const [k, v] of byType) console.log(`${k}\t${v}`);
  console.log("完整样本×2:\n" + JSON.stringify(returns.slice(0, 2), null, 1).slice(0, 4000));

  // ── ② 结算账单列表：近30天类目全景 ──
  await sleep(1500);
  console.log(`\n== ② 结算账单列表 近30天 类目全景 ==`);
  const agg = new Map<string, { n: number; sum: number }>();
  let billTotal = 0;
  for (let page = 0; page < 25; page++) {
    const resp = await client.request<{ list?: Array<Record<string, unknown>> }>({
      method: "POST", path: BILL_PATH,
      params: { offset: page * 200, length: 200, startDate: d(-30), endDate: d(0) },
      timeoutMs: 30000,
    });
    const list = (resp?.data as { list?: Array<Record<string, unknown>> } | undefined)?.list ?? [];
    billTotal += list.length;
    for (const r of list) {
      const k = `${r.transactionType ?? "?"}｜${r.amountType ?? "?"}｜${r.transactionDescription ?? "?"}`;
      const a = agg.get(k) ?? { n: 0, sum: 0 };
      a.n += 1; a.sum += Number(r.amount ?? 0); agg.set(k, a);
    }
    if (list.length < 200) break;
    await sleep(1500);
  }
  console.log(`账单行合计 ${billTotal}`);
  console.log("类目清单（交易类型｜费用名称｜交易描述｜行数｜金额合计）:");
  for (const [k, a] of [...agg.entries()].sort((x, y) => Math.abs(y[1].sum) - Math.abs(x[1].sum))) {
    console.log(`${k}\t${a.n}\t${Math.round(a.sum * 100) / 100}`);
  }

  // ── Service Fee 单独一页（找仓储费证据） ──
  await sleep(1500);
  const sf = await client.request<{ list?: Array<Record<string, unknown>> }>({
    method: "POST", path: BILL_PATH,
    params: { offset: 0, length: 50, startDate: d(-30), endDate: d(0), transactionTypes: ["Service Fee"] },
    timeoutMs: 30000,
  });
  const sfList = (sf?.data as { list?: Array<Record<string, unknown>> } | undefined)?.list ?? [];
  console.log(`\nService Fee 类样本 ${sfList.length} 行（前3条完整）:`);
  console.log(JSON.stringify(sfList.slice(0, 3), null, 1).slice(0, 4000));

  console.log("\nPROBE_DONE（零写入）");
}

main().catch((e) => { console.error("FATAL:", e instanceof Error ? e.message : String(e)); process.exit(1); });
