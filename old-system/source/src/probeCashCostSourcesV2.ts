/**
 * src/probeCashCostSourcesV2.ts
 *
 * 单品现金利润模块 · 探针1b — 只读探测三件事（不猜字段，零写库，不改生产）：
 *
 *   ① 采购单真实成本字段：purchaseOrderList
 *      —— 探针1（probeCashCostSources.ts）返回 0 单，根因是**解包多剥了一层**：
 *         现网在跑的 syncPurchaseOrders.ts 取法是 resp.data.data（2026-07-21 RAW#38710/38711 实证 total=586），
 *         探针1 写成了 resp.data 当外层再取 .data.data = resp.data.data.data，永远空数组。
 *         本探针改为逐层尝试并**打印实际命中的解包路径**，不再默认任何一种。
 *
 *   ② 平台仓发货单（头程物流费真实来源）候选路径：
 *      —— 探针1 的候选全在 /erp/sc/routing/data/local_inventory/* 下，全部"服务不存在"。
 *         方向错了：Walmart 多平台仓这条线的真实前缀是 /cepf/warehouse/api/openApi/*
 *         （WFS 货件 queryWFSCargoPage 实锤，仓库内 12 处代码在用）。
 *         领星文档目录里存在「查询平台仓发货单列表 / v2」条目（_sidebar.md L597-598），
 *         按 QueryWFSCargoPage → /cepf/warehouse/api/openApi/queryWFSCargoPage 的同一命名习惯推候选。
 *         **候选仍属未证实推断，逐个试，成功的才可信，全失败就如实报告并停手。**
 *
 *   ③ WFS 货件接口本身是否已带费用字段：把 queryWFSCargoPage 单条记录的全字段打出来，
 *      若头程/物流费本就在货件里，就不必再找发货单接口。
 *
 * 安全边界：
 *   - 只读：LingxingClient.assertReadOnlyPath 兜底拦截 add/create/update/delete 等写类路径。
 *   - 零数据库写入：本文件没有任何 mysql 依赖、没有任何写分支、没有 --confirm-write。
 *   - 输出脱敏：联系人/电话/地址/邮箱类字段一律打码后再打印。
 *
 * 运行（生产机）：
 *   npx ts-node src/probeCashCostSourcesV2.ts --sids=110687423514268160
 *   npx ts-node src/probeCashCostSourcesV2.ts --po-pages=3 --days=120 --sids=110687423514268160
 */

import "dotenv/config";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const PURCHASE_ORDER_PATH = "/erp/sc/routing/data/local_inventory/purchaseOrderList";
const WFS_CARGO_PATH = "/cepf/warehouse/api/openApi/queryWFSCargoPage";

// 候选：按 cepf 命名习惯从文档目录条目推得，未经证实，逐个试
const SHIPPING_CANDIDATES: string[] = [
  "/cepf/warehouse/api/openApi/queryShippingListV2",
  "/cepf/warehouse/api/openApi/queryShippingListPage",
  "/cepf/warehouse/api/openApi/queryShippingList",
  "/cepf/warehouse/api/openApi/shippingListV2",
  "/cepf/warehouse/api/openApi/queryPlatformShippingListPage",
];

const REDACT = /addr|address|phone|mobile|contact|consignee|email|linkman|tel\b/i;
const COSTY = /price|cost|amount|money|fee|freight|logistic|tax|premium|expense|charge|total/i;

function getArg(name: string, def: string): string {
  const p = `--${name}=`;
  const hit = process.argv.find((a) => a.startsWith(p));
  return hit ? hit.slice(p.length) : def;
}
function redact(o: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(o)) out[k] = REDACT.test(k) ? "(已脱敏)" : v;
  return out;
}
function costKeys(keys: string[]): string[] { return keys.filter((k) => COSTY.test(k)); }
function shanghaiDate(offsetDays = 0): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

/** 逐层尝试解包，返回列表与实际命中的路径描述（不默认任何一种） */
function unwrapList(resp: unknown): { list: Array<Record<string, unknown>>; via: string } {
  const cands: Array<[string, unknown]> = [];
  const r = resp as Record<string, unknown> | undefined;
  const d1 = r?.data as Record<string, unknown> | undefined;
  const d2 = d1?.data as Record<string, unknown> | undefined;
  cands.push(["resp.data.data", d1?.data]);
  cands.push(["resp.data.list", d1?.list]);
  cands.push(["resp.data.records", d1?.records]);
  cands.push(["resp.data.rows", d1?.rows]);
  cands.push(["resp.data.data.data", d2?.data]);
  cands.push(["resp.data.data.list", d2?.list]);
  cands.push(["resp.data.data.records", d2?.records]);
  cands.push(["resp.list", r?.list]);
  cands.push(["resp.data(本身是数组)", d1]);
  cands.push(["resp(本身是数组)", r]);
  for (const [via, v] of cands) {
    if (Array.isArray(v) && v.length > 0) return { list: v as Array<Record<string, unknown>>, via };
  }
  for (const [via, v] of cands) {
    if (Array.isArray(v)) return { list: [], via: via + "(空数组)" };
  }
  return { list: [], via: "未找到任何数组，见下方顶层结构" };
}

function topShape(resp: unknown): string {
  const r = resp as Record<string, unknown> | undefined;
  if (!r || typeof r !== "object") return String(r);
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(r)) {
    out[k] = Array.isArray(v) ? `Array(${v.length})`
      : v && typeof v === "object" ? `Object{${Object.keys(v as object).slice(0, 12).join(",")}}`
      : typeof v;
  }
  return JSON.stringify(out);
}

async function probePurchase(client: LingxingClient, pages: number): Promise<void> {
  console.log("\n" + "=".repeat(70));
  console.log("① 采购单真实成本字段:", PURCHASE_ORDER_PATH);
  console.log("=".repeat(70));

  let offset = 0, orders = 0, items = 0;
  const hKeys = new Set<string>(), iKeys = new Set<string>();
  let printedH = false, printedI = false;

  for (let page = 1; page <= pages; page++) {
    const resp = await client.post<unknown>(PURCHASE_ORDER_PATH, { offset, length: 20 });
    if (page === 1) console.log("顶层结构:", topShape(resp));
    const { list, via } = unwrapList(resp);
    console.log(`第 ${page} 页: ${list.length} 单（解包路径命中: ${via}）`);
    if (!list.length) break;

    for (const h of list) {
      orders++;
      Object.keys(h).forEach((k) => hKeys.add(k));
      if (!printedH) {
        console.log("\n── 采购单 header 完整字段名 ──");
        console.log(Object.keys(h));
        console.log("── header 样例（已脱敏）──");
        console.log(JSON.stringify(redact(h), null, 2).slice(0, 2500));
        printedH = true;
      }
      const its = Array.isArray(h.item_list) ? (h.item_list as Array<Record<string, unknown>>) : [];
      for (const it of its) {
        items++;
        Object.keys(it).forEach((k) => iKeys.add(k));
        if (!printedI) {
          console.log("\n── 采购单 item 完整字段名 ──");
          console.log(Object.keys(it));
          console.log("── item 样例 ──");
          console.log(JSON.stringify(it, null, 2).slice(0, 2000));
          printedI = true;
        }
      }
    }
    if (list.length < 20) break;
    offset += 20;
    await new Promise((r) => setTimeout(r, 300));
  }

  console.log(`\n采样汇总：${orders} 个采购单，${items} 个明细行`);
  console.log("header 全部字段:", [...hKeys]);
  console.log("header 疑似成本/金额字段:", costKeys([...hKeys]));
  console.log("item 全部字段:", [...iKeys]);
  console.log("item 疑似成本/金额字段:", costKeys([...iKeys]));
  if (!costKeys([...hKeys, ...iKeys]).length) {
    console.log("⚠️ 列表接口没有成本字段 → 采购成本可能只在「采购单详情」接口，需人工在领星文档确认，禁止继续猜路径。");
  }
}

async function probeWfsCargoFields(client: LingxingClient, sids: string, days: number): Promise<void> {
  console.log("\n" + "=".repeat(70));
  console.log("③ WFS货件接口是否自带费用字段:", WFS_CARGO_PATH);
  console.log("=".repeat(70));
  const variants: Record<string, unknown>[] = [
    { offset: 0, length: 5 },
    { offset: 0, length: 5, startDate: shanghaiDate(-days), endDate: shanghaiDate(0) },
  ];
  if (sids) variants.unshift({ offset: 0, length: 5, sids });
  for (const params of variants) {
    try {
      const resp = await client.post<unknown>(WFS_CARGO_PATH, params);
      const { list, via } = unwrapList(resp);
      console.log(`参数 ${JSON.stringify(params)} → 成功，条数=${list.length}（解包: ${via}）`);
      if (list.length) {
        const k = Object.keys(list[0]);
        console.log("  货件字段全名:", k);
        console.log("  疑似费用字段:", costKeys(k));
        console.log("  首条样例（已脱敏）:", JSON.stringify(redact(list[0]), null, 2).slice(0, 2000));
        return;
      }
    } catch (e) {
      console.log(`参数 ${JSON.stringify(params)} → 失败: ${e instanceof Error ? e.message : String(e)}`);
    }
    await new Promise((r) => setTimeout(r, 300));
  }
  console.log("⚠️ 未取到货件样例，无法判断是否自带费用字段。");
}

async function probeShipping(client: LingxingClient, sids: string, days: number): Promise<void> {
  console.log("\n" + "=".repeat(70));
  console.log("② 平台仓发货单（头程物流费）候选路径 —— cepf 前缀，均未经证实，逐个试");
  console.log("=".repeat(70));
  const sd = shanghaiDate(-days), ed = shanghaiDate(0);
  let anyHit = false;

  for (const path of SHIPPING_CANDIDATES) {
    console.log(`\n--- 候选: ${path} ---`);
    const variants: Record<string, unknown>[] = [
      { offset: 0, length: 10 },
      { offset: 0, length: 10, startDate: sd, endDate: ed },
      { pageNo: 1, pageSize: 10 },
      { pageNo: 1, pageSize: 10, startDate: sd, endDate: ed },
    ];
    if (sids) {
      variants.unshift({ offset: 0, length: 10, sids });
      variants.push({ offset: 0, length: 10, startDate: sd, endDate: ed, sids });
      variants.push({ offset: 0, length: 10, startDate: sd, endDate: ed, sid: sids });
    }
    let hit = false;
    for (const params of variants) {
      try {
        const resp = await client.post<unknown>(path, params);
        const { list, via } = unwrapList(resp);
        console.log(`  参数 ${JSON.stringify(params)} → 成功，条数=${list.length}（解包: ${via}）`);
        if (list.length) {
          const k = Object.keys(list[0]);
          console.log("  首条字段全名:", k);
          console.log("  疑似成本/金额字段:", costKeys(k));
          console.log("  首条样例（已脱敏）:", JSON.stringify(redact(list[0]), null, 2).slice(0, 2000));
          hit = true; anyHit = true;
          break;
        }
        console.log("  （成功但列表为空：路径可能对、时间窗或店铺参数不对）");
        hit = true; anyHit = true;
      } catch (e) {
        console.log(`  参数 ${JSON.stringify(params)} → 失败: ${e instanceof Error ? e.message : String(e)}`);
      }
      await new Promise((r) => setTimeout(r, 250));
    }
    if (!hit) console.log("  ⚠️ 全部参数组合失败，此候选路径排除。");
  }

  if (!anyHit) {
    console.log("\n⚠️ 全部候选路径均失败。头程物流费接口需人工在领星开放平台文档确认真实路径" +
      "（文档目录条目：MultiPlatform/V2/QueryShippingListPage、QueryShippingListV2），不再靠猜。");
  }
}

async function main(): Promise<void> {
  const poPages = Number(getArg("po-pages", "3")) || 3;
  const days = Number(getArg("days", "120")) || 120;
  const sids = getArg("sids", "");

  console.log("单品现金利润 · 探针1b（只读，零写库）");
  console.log(`采购单抽样页数=${poPages} | 时间窗=近${days}天 | sids=${sids || "(未提供)"}`);

  const client = new LingxingClient(loadConfig());
  await probePurchase(client, poPages);
  await probeShipping(client, sids, days);
  await probeWfsCargoFields(client, sids, days);
  console.log("\n探测结束（零写库）。");
}

main().catch((e) => {
  console.error("探针异常:", e instanceof Error ? e.stack : String(e));
  process.exit(1);
});
