/**
 * src/probeCashProfitCostSources.ts
 *
 * 单品现金利润模块 · 探针1 — 只读探测两类真实成本数据源（不猜字段，不写库，不改动生产）：
 *   ① 采购单真实成本：purchaseOrderList（syncPurchaseOrders.ts 已在用这个接口同步单号/状态/数量，
 *      但当前 PoItem 只解析了 sku/msku/product_name/quantity_*，完全没解析价格/成本类字段——
 *      本探针把 header + item 的完整原始字段打出来，核对真实成本字段叫什么名字、在 header 还是 item 上）。
 *   ② 发货单头程物流成本：目前 dim_product_cost_config.first_mile_shipping_cost 来自
 *      batchGetProductInfo 返回的 product_logistics_relation.US_cg_transport_costs，
 *      这是"产品资料页配置的头程运费"，不是"真实发货单里实际发生的物流费"。
 *      本地 docs/lingxing/ 下没有"发货单/本地发货"这个接口的官方文档、代码里也没有已确认的调用，
 *      下面 CANDIDATE_PATHS 是按 purchaseOrderList 同一 local_inventory 命名习惯列的候选路径，
 *      全部未经证实，本探针逐个尝试，成功的才可信，不成功的直接排除。
 *
 * 安全边界：
 *   - 只读：LingxingClient.assertReadOnlyPath 兜底拦截任何 add/create/update/delete/... 等写类路径。
 *   - 零数据库写入（不像 syncPurchaseOrders.ts 有 --confirm-write，本探针没有任何写分支）。
 *   - 输出脱敏：不打印供应商联系人、电话、详细地址一类字段，其余字段原样打印用于设计表结构。
 *
 * 运行（生产机，由部署工程师执行，需要真实 .env 网络与凭证；本探针不适合在无网络的本地环境跑）：
 *   npx ts-node src/probeCashProfitCostSources.ts                 # 默认：采购单2页 + 候选发货单接口全部试一遍
 *   npx ts-node src/probeCashProfitCostSources.ts --po-pages=5     # 采购单多抽几页看成本字段是否稳定
 *   npx ts-node src/probeCashProfitCostSources.ts --days=180       # 发货单候选接口的时间窗（如该接口需要）
 *
 * 用法：把完整输出贴回来，用于设计 fact_settlement_cash_flow_daily / 头程成本来源 的真实表结构，
 *      在此之前不建表、不写正式同步脚本。
 */

import "dotenv/config";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const PURCHASE_ORDER_PATH = "/erp/sc/routing/data/local_inventory/purchaseOrderList";

// 候选路径：未经证实，仅按 purchaseOrderList 同命名习惯列出，探针会逐个尝试，全部失败也如实汇报。
const DELIVER_ORDER_CANDIDATES: Array<{ path: string; paramVariants: Record<string, unknown>[] }> = [
  { path: "/erp/sc/routing/data/local_inventory/deliverOrderList", paramVariants: [{ offset: 0, length: 10 }, { pageNo: 1, pageSize: 10 }] },
  { path: "/erp/sc/routing/data/local_inventory/deliveryOrderList", paramVariants: [{ offset: 0, length: 10 }, { pageNo: 1, pageSize: 10 }] },
  { path: "/erp/sc/routing/data/local_inventory/localDeliverOrderList", paramVariants: [{ offset: 0, length: 10 }] },
  { path: "/erp/sc/routing/data/local_inventory/warehouseDeliverOrderList", paramVariants: [{ offset: 0, length: 10 }] },
  { path: "/erp/sc/routing/data/local_inventory/shipmentOrderList", paramVariants: [{ offset: 0, length: 10 }] },
  { path: "/erp/sc/routing/data/local_inventory/outboundOrderList", paramVariants: [{ offset: 0, length: 10 }] },
  { path: "/erp/sc/routing/data/local_inventory/transferOrderList", paramVariants: [{ offset: 0, length: 10 }] },
  { path: "/erp/sc/routing/data/local_inventory/localDeliveryList", paramVariants: [{ offset: 0, length: 10 }] },
];

const REDACT_KEY_PATTERN = /addr|address|phone|mobile|contact|consignee|email|linkman/i;
const COST_KEY_PATTERN = /price|cost|amount|money|fee|freight|logistic|tax|premium|expense/i;

function getArg(name: string, def: string): string {
  const prefix = `--${name}=`;
  const hit = process.argv.find((a) => a.startsWith(prefix));
  return hit ? hit.slice(prefix.length) : def;
}

function redactSample(obj: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(obj)) {
    out[k] = REDACT_KEY_PATTERN.test(k) ? "(已脱敏)" : v;
  }
  return out;
}

function flagCostKeys(keys: string[]): string[] {
  return keys.filter((k) => COST_KEY_PATTERN.test(k));
}

function pickList(data: unknown): unknown[] {
  const d = data as Record<string, unknown> | undefined;
  if (Array.isArray(d)) return d as unknown[];
  if (!d || typeof d !== "object") return [];
  if (Array.isArray((d as any).data)) return (d as any).data;
  if (Array.isArray((d as any).list)) return (d as any).list;
  if (Array.isArray((d as any).records)) return (d as any).records;
  if (Array.isArray((d as any).rows)) return (d as any).rows;
  if (Array.isArray((d as any)?.data?.list)) return (d as any).data.list;
  if (Array.isArray((d as any)?.data?.data)) return (d as any).data.data;
  return [];
}

async function probePurchaseOrderFields(client: LingxingClient, pages: number): Promise<void> {
  console.log("\n" + "=".repeat(70));
  console.log("① 采购单真实成本字段探测:", PURCHASE_ORDER_PATH);
  console.log("=".repeat(70));

  let offset = 0;
  let headerKeysSeen = new Set<string>();
  let itemKeysSeen = new Set<string>();
  let printedHeaderSample = false;
  let printedItemSample = false;
  let totalOrders = 0;
  let totalItems = 0;

  for (let page = 1; page <= pages; page++) {
    const resp = await client.post<unknown>(PURCHASE_ORDER_PATH, { offset, length: 20 });
    const outer = resp.data as { data?: { data?: unknown[]; list?: unknown[] }; list?: unknown[] };
    const list = (outer?.data?.data ?? outer?.data?.list ?? outer?.list ?? []) as Array<Record<string, unknown>>;
    console.log(`\n第 ${page} 页: ${list.length} 单`);
    if (list.length === 0) break;

    for (const h of list) {
      totalOrders += 1;
      Object.keys(h).forEach((k) => headerKeysSeen.add(k));
      if (!printedHeaderSample) {
        console.log("\n── 采购单 header 完整字段名 ──");
        console.log(Object.keys(h));
        console.log("── header 样例（已脱敏联系人/地址）──");
        console.log(JSON.stringify(redactSample(h), null, 2).slice(0, 2000));
        printedHeaderSample = true;
      }
      const items = Array.isArray(h.item_list) ? (h.item_list as Array<Record<string, unknown>>) : [];
      for (const it of items) {
        totalItems += 1;
        Object.keys(it).forEach((k) => itemKeysSeen.add(k));
        if (!printedItemSample) {
          console.log("\n── 采购单 item 完整字段名 ──");
          console.log(Object.keys(it));
          console.log("── item 样例 ──");
          console.log(JSON.stringify(it, null, 2).slice(0, 1500));
          printedItemSample = true;
        }
      }
    }

    if (list.length < 20) break;
    offset += 20;
    await new Promise((r) => setTimeout(r, 300));
  }

  console.log(`\n采样汇总：抽样 ${totalOrders} 个采购单，${totalItems} 个明细行`);
  console.log("header 出现过的全部字段:", [...headerKeysSeen]);
  console.log("header 里疑似成本/金额字段:", flagCostKeys([...headerKeysSeen]));
  console.log("item 出现过的全部字段:", [...itemKeysSeen]);
  console.log("item 里疑似成本/金额字段:", flagCostKeys([...itemKeysSeen]));
  if (flagCostKeys([...headerKeysSeen, ...itemKeysSeen]).length === 0) {
    console.log("⚠️ 没有探测到任何疑似成本/金额字段，采购单真实成本可能需要另一个接口（如采购单详情接口），需要人工确认领星后台页面上这个成本具体在哪个入口。");
  }
}

async function probeDeliverOrderCandidates(client: LingxingClient, days: number): Promise<void> {
  console.log("\n" + "=".repeat(70));
  console.log("② 发货单头程物流成本候选接口探测（以下路径均未经证实，逐个尝试）");
  console.log("=".repeat(70));

  const endDate = new Date();
  const startDate = new Date(endDate.getTime() - days * 24 * 3600 * 1000);
  const dateStr = (d: Date) => d.toISOString().slice(0, 10);

  let anySuccess = false;

  for (const cand of DELIVER_ORDER_CANDIDATES) {
    console.log(`\n--- 候选: ${cand.path} ---`);
    let succeeded = false;
    for (const baseParams of cand.paramVariants) {
      const paramsToTry: Record<string, unknown>[] = [
        baseParams,
        { ...baseParams, start_time: dateStr(startDate), end_time: dateStr(endDate) },
        { ...baseParams, startDate: dateStr(startDate), endDate: dateStr(endDate) },
      ];
      for (const params of paramsToTry) {
        try {
          const resp = await client.post<unknown>(cand.path, params);
          const list = pickList(resp.data);
          console.log(`  参数 ${JSON.stringify(params)} → 成功，列表条数=${list.length}`);
          if (list.length > 0) {
            const first = list[0] as Record<string, unknown>;
            const keys = Object.keys(first);
            console.log("  首条字段名:", keys);
            console.log("  疑似成本/金额字段:", flagCostKeys(keys));
            console.log("  首条样例（已脱敏联系人/地址）:", JSON.stringify(redactSample(first), null, 2).slice(0, 1500));
          } else {
            console.log("  （返回成功但列表为空，无法确认字段，换个时间窗或人工在领星后台确认是否真有数据）");
          }
          succeeded = true;
          anySuccess = true;
          break;
        } catch (e) {
          console.log(`  参数 ${JSON.stringify(params)} → 失败: ${e instanceof Error ? e.message : String(e)}`);
        }
      }
      if (succeeded) break;
      await new Promise((r) => setTimeout(r, 300));
    }
    if (!succeeded) console.log("  ⚠️ 全部参数组合失败，此候选路径排除。");
  }

  if (!anySuccess) {
    console.log("\n⚠️ 全部候选路径均失败。发货单/头程物流成本接口需要人工在领星开放平台文档或后台界面确认真实路径，不能继续靠猜测候选路径。");
  }
}

async function main(): Promise<void> {
  const poPages = Number(getArg("po-pages", "2")) || 2;
  const days = Number(getArg("days", "90")) || 90;

  console.log("单品现金利润模块 · 探针1（只读，零写入）");
  console.log(`采购单抽样页数: ${poPages}`);
  console.log(`发货单候选接口时间窗: 近 ${days} 天`);

  const client = new LingxingClient(loadConfig());

  await probePurchaseOrderFields(client, poPages);
  await probeDeliverOrderCandidates(client, days);

  console.log("\n探测结束（零写入）。把以上完整输出贴回来，用于设计现金利润 FACT 表真实字段。");
}

main().catch((e) => {
  console.error("probeCashProfitCostSources 致命错误:", e instanceof Error ? e.message : String(e));
  process.exitCode = 1;
});
