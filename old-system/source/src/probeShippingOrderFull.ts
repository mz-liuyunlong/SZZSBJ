/**
 * src/probeShippingOrderFull.ts
 *
 * 单品现金利润 · 探针1c — 平台仓发货单**完整记录**只读转储（零写库）
 *
 * 背景（探针1b 实锤）：
 *   - 命中路径 /cepf/warehouse/api/openApi/queryShippingListPage，解包 resp.data.data.records
 *   - 头层已见：shipping_code / head_fee_type("按计费重") / shipping_logistics[] / shipping_goods[]
 *     / shipping_accessories / shipping_first_lets
 *   - shipping_logistics[0].transportation_cost = 2992.00（真实头程运费，CNY）
 *   - **但 shipping_goods 输出被截断、shipping_first_lets 与 shipping_accessories 未展开**
 *
 * 本探针要回答的唯一问题：
 *   **领星是否已经把头程运费分摊到 SKU 了？**若已分摊，直接取现成值，不自建分摊逻辑。
 *   为此把整条记录完整打印（不 slice 截断），并对每个子数组逐字段列名+样值输出，
 *   同时统计各子数组里"疑似金额字段"的非零命中情况，避免只看一条样本下错结论。
 *
 * 安全边界：
 *   - 只读：LingxingClient.assertReadOnlyPath 兜底；本文件无 mysql 依赖、无写分支、无 --confirm-write
 *   - 脱敏：联系人/电话/地址/邮箱类字段打码；图片URL截短
 *
 * 运行（生产机）：
 *   npx ts-node src/probeShippingOrderFull.ts --sids=110687423514268160 --dump=2 --pages=3
 */

import "dotenv/config";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const PATH = "/cepf/warehouse/api/openApi/queryShippingListPage";
const REDACT = /addr|address|phone|mobile|contact|consignee|email|linkman|tel\b/i;
const URLISH = /url|image|img|file/i;
const COSTY = /price|cost|amount|money|fee|freight|charge|total|expense/i;

function getArg(name: string, def: string): string {
  const p = `--${name}=`;
  const hit = process.argv.find((a) => a.startsWith(p));
  return hit ? hit.slice(p.length) : def;
}

/** 递归脱敏 + 截短长URL，保留结构与全部字段名 */
function clean(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(clean);
  if (v && typeof v === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, val] of Object.entries(v as Record<string, unknown>)) {
      if (REDACT.test(k)) out[k] = "(已脱敏)";
      else if (URLISH.test(k) && typeof val === "string") out[k] = val.slice(0, 40) + (val.length > 40 ? "…" : "");
      else out[k] = clean(val);
    }
    return out;
  }
  return v;
}

function unwrapRecords(resp: unknown): { list: Array<Record<string, unknown>>; via: string } {
  const r = resp as Record<string, unknown> | undefined;
  const d1 = r?.data as Record<string, unknown> | undefined;
  const d2 = d1?.data as Record<string, unknown> | undefined;
  const cands: Array<[string, unknown]> = [
    ["resp.data.data.records", d2?.records],
    ["resp.data.data.list", d2?.list],
    ["resp.data.data", d1?.data],
    ["resp.data.records", d1?.records],
    ["resp.data.list", d1?.list],
  ];
  for (const [via, v] of cands) if (Array.isArray(v) && v.length) return { list: v as Array<Record<string, unknown>>, via };
  for (const [via, v] of cands) if (Array.isArray(v)) return { list: [], via: via + "(空)" };
  return { list: [], via: "未找到数组" };
}

function isNonZero(v: unknown): boolean {
  if (v === null || v === undefined || v === "") return false;
  const n = Number(v);
  return Number.isFinite(n) ? Math.abs(n) > 0 : false;
}

/** 子数组字段统计：字段名 → {出现次数, 非零次数, 首个非零样值} */
interface FieldStat { seen: number; nonZero: number; sample: string }

function scanArrayField(
  rec: Record<string, unknown>, field: string, acc: Map<string, FieldStat>, rowCount: { n: number },
): void {
  const arr = rec[field];
  if (!Array.isArray(arr)) return;
  for (const row of arr) {
    if (!row || typeof row !== "object") continue;
    rowCount.n += 1;
    for (const [k, v] of Object.entries(row as Record<string, unknown>)) {
      const st = acc.get(k) ?? { seen: 0, nonZero: 0, sample: "" };
      st.seen += 1;
      if (isNonZero(v)) { st.nonZero += 1; if (!st.sample) st.sample = String(v).slice(0, 40); }
      acc.set(k, st);
    }
  }
}

function printStats(title: string, acc: Map<string, FieldStat>, rows: number): void {
  console.log(`\n── ${title}：共 ${rows} 行，字段统计（字段名 | 出现 | 非零 | 首个非零样值）──`);
  if (!acc.size) { console.log("  （该字段不存在或为空/非数组）"); return; }
  const entries = [...acc.entries()].sort((a, b) => b[1].nonZero - a[1].nonZero);
  for (const [k, st] of entries) {
    const flag = COSTY.test(k) ? " ★疑似金额" : "";
    console.log(`  ${k} | ${st.seen} | ${st.nonZero} | ${st.sample || "-"}${flag}`);
  }
  const costy = entries.filter(([k, st]) => COSTY.test(k) && st.nonZero > 0).map(([k]) => k);
  console.log(`  → 有非零值的疑似金额字段: ${costy.length ? costy.join(", ") : "（无）"}`);
}

async function main(): Promise<void> {
  const sids = getArg("sids", "");
  const dumpN = Number(getArg("dump", "2")) || 2;
  const pages = Number(getArg("pages", "3")) || 3;

  console.log("平台仓发货单 · 探针1c（只读，零写库）");
  console.log(`路径=${PATH} | sids=${sids || "(未提供)"} | 完整转储条数=${dumpN} | 扫描页数=${pages}`);

  const client = new LingxingClient(loadConfig());

  const goodsAcc = new Map<string, FieldStat>(); const goodsRows = { n: 0 };
  const logiAcc = new Map<string, FieldStat>(); const logiRows = { n: 0 };
  const firstAcc = new Map<string, FieldStat>(); const firstRows = { n: 0 };
  const accAcc = new Map<string, FieldStat>(); const accRows = { n: 0 };
  const headKeys = new Set<string>();
  let dumped = 0, total = 0;

  for (let p = 0; p < pages; p++) {
    const params: Record<string, unknown> = { offset: p * 10, length: 10 };
    if (sids) params.sids = sids;
    const resp = await client.post<unknown>(PATH, params);
    const { list, via } = unwrapRecords(resp);
    console.log(`\n第 ${p + 1} 页: ${list.length} 单（解包: ${via}）`);
    if (!list.length) break;

    for (const rec of list) {
      total += 1;
      Object.keys(rec).forEach((k) => headKeys.add(k));
      if (dumped < dumpN) {
        dumped += 1;
        console.log("\n" + "=".repeat(70));
        console.log(`【完整记录 ${dumped}】shipping_code=${String(rec.shipping_code ?? "")}`);
        console.log("=".repeat(70));
        console.log(JSON.stringify(clean(rec), null, 2));
      }
      scanArrayField(rec, "shipping_goods", goodsAcc, goodsRows);
      scanArrayField(rec, "shipping_logistics", logiAcc, logiRows);
      scanArrayField(rec, "shipping_first_lets", firstAcc, firstRows);
      scanArrayField(rec, "shipping_accessories", accAcc, accRows);
    }
    if (list.length < 10) break;
    await new Promise((r) => setTimeout(r, 300));
  }

  console.log("\n" + "=".repeat(70));
  console.log(`统计汇总：扫描 ${total} 张发货单`);
  console.log("=".repeat(70));
  console.log("发货单头层全部字段:", [...headKeys]);
  printStats("shipping_goods（商品行）", goodsAcc, goodsRows.n);
  printStats("shipping_logistics（物流行=真实头程运费所在）", logiAcc, logiRows.n);
  printStats("shipping_first_lets（头程?）", firstAcc, firstRows.n);
  printStats("shipping_accessories（辅料/附加?）", accAcc, accRows.n);

  console.log("\n【判读要点】若 shipping_goods 里出现带非零值的单品级费用字段（如 head_fee / first_fee /" +
    " transport_cost / apportion 之类），说明领星已按品分摊好头程，直接取现成值，不自建分摊逻辑；" +
    "若只有 shipping_logistics 里有整单 transportation_cost，则需自建分摊，基数再由需求方拍板。");
  console.log("\n探测结束（零写库）。");
}

main().catch((e) => {
  console.error("探针异常:", e instanceof Error ? e.stack : String(e));
  process.exit(1);
});
