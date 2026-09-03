/**
 * src/probeBatchCost.ts — 探针1d·批次成本接口探测（只读，零写库）
 *
 * 背景（2026-08-13 需求方拍板）：单品现金利润一刀切时点 = 2026-05-01（业务变动）。
 *   切点前已有存货的老 SKU 需要「期初单价一刀」，候选取值源之一 = 领星批次成本接口
 *   （定稿 v1.4 预留的 GetBatchDetailList，cost_source='batch_api'）。
 *   文档目录存在条目「查询批次明细 docs/Warehouse/GetBatchDetailList」「查询批次流水 GetBatchStatementList」，
 *   但正文未镜像，**真实路径未知**——以下候选按仓库内已实证的命名习惯推得
 *   （InventoryDetails → /erp/sc/routing/data/local_inventory/*，syncLocalInventory 用
 *   /erp/sc/data/local_inventory/warehouse），全部未经证实，逐个试，全失败即如实报告。
 *
 * 要回答的问题：
 *   ① 哪个路径能通；②返回里有没有 SKU / 批次单价(成本) / 结存数量 / 入库时间 这类字段——
 *     有单价+结存才够格当期初一刀的取值源。
 *
 * 安全边界：只读（assertReadOnlyPath 兜底）；无 mysql 依赖、无写分支；联系人/地址类字段脱敏。
 *
 * 运行：npx ts-node src/probeBatchCost.ts
 */

import "dotenv/config";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const CANDIDATES: string[] = [
  "/erp/sc/routing/data/local_inventory/getBatchDetailList",
  "/erp/sc/routing/data/local_inventory/batchDetailList",
  "/erp/sc/data/local_inventory/getBatchDetailList",
  "/erp/sc/data/local_inventory/batchDetailList",
  "/erp/sc/routing/data/warehouse/getBatchDetailList",
  "/erp/sc/routing/data/local_inventory/batchList",
];
const REDACT = /addr|address|phone|mobile|contact|consignee|email|linkman|tel\b/i;
const COSTY = /price|cost|amount|money|fee|freight|expense|balance|stock|qty|quantity|num\b/i;

function redact(o: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(o)) out[k] = REDACT.test(k) ? "(已脱敏)" : v;
  return out;
}
function unwrap(resp: unknown): { list: Array<Record<string, unknown>>; via: string } {
  const r = resp as Record<string, unknown> | undefined;
  const d1 = r?.data as Record<string, unknown> | undefined;
  const d2 = d1?.data as Record<string, unknown> | undefined;
  const cands: Array<[string, unknown]> = [
    ["resp.data.data", d1?.data], ["resp.data.list", d1?.list], ["resp.data.records", d1?.records],
    ["resp.data.data.records", d2?.records], ["resp.data.data.list", d2?.list],
    ["resp.data(数组)", d1],
  ];
  for (const [via, v] of cands) if (Array.isArray(v) && v.length) return { list: v as Array<Record<string, unknown>>, via };
  for (const [via, v] of cands) if (Array.isArray(v)) return { list: [], via: via + "(空)" };
  return { list: [], via: "未找到数组" };
}
function topShape(resp: unknown): string {
  const r = resp as Record<string, unknown> | undefined;
  if (!r || typeof r !== "object") return String(r);
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(r)) {
    out[k] = Array.isArray(v) ? `Array(${v.length})`
      : v && typeof v === "object" ? `Object{${Object.keys(v as object).slice(0, 12).join(",")}}` : typeof v;
  }
  return JSON.stringify(out);
}

async function main(): Promise<void> {
  console.log("探针1d·批次成本接口（只读，零写库）");
  const client = new LingxingClient(loadConfig());
  let anyHit = false;

  for (const path of CANDIDATES) {
    console.log(`\n--- 候选: ${path} ---`);
    const variants: Record<string, unknown>[] = [
      { offset: 0, length: 20 },
      { offset: 0, length: 20, wid: 16168 },        // 惠州仓库 wid（采购单实测值）
      { pageNo: 1, pageSize: 20 },
    ];
    let hit = false;
    for (const params of variants) {
      try {
        const resp = await client.post<unknown>(path, params);
        const { list, via } = unwrap(resp);
        console.log(`  参数 ${JSON.stringify(params)} → 成功，条数=${list.length}（解包: ${via}）`);
        if (!list.length) { console.log("  顶层结构:", topShape(resp)); hit = true; anyHit = true; continue; }
        const keys = Object.keys(list[0]);
        console.log("  首条字段全名:", keys);
        console.log("  疑似成本/数量字段:", keys.filter((k) => COSTY.test(k)));
        for (let i = 0; i < Math.min(3, list.length); i++) {
          console.log(`  样例${i + 1}:`, JSON.stringify(redact(list[i]), null, 2).slice(0, 1800));
        }
        hit = true; anyHit = true;
        break;
      } catch (e) {
        console.log(`  参数 ${JSON.stringify(params)} → 失败: ${e instanceof Error ? e.message : String(e)}`);
      }
      await new Promise((r) => setTimeout(r, 300));
    }
    if (!hit) console.log("  ⚠️ 全部参数组合失败，此候选排除。");
    if (anyHit && hit) { /* 命中一个即可，其余仍试完以便对比 */ }
  }

  if (!anyHit) {
    console.log("\n⚠️ 全部候选路径失败。请需求方把领星文档站「查询批次明细 GetBatchDetailList」页面存为 HTML 提供，" +
      "以真实路径与参数为准，不再猜测。");
  }
  console.log("\n探测结束（零写库）。");
}

main().catch((e) => {
  console.error("探针异常:", e instanceof Error ? e.stack : String(e));
  process.exit(1);
});
