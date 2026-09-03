/**
 * src/probeSbSvAdEndpoints.ts
 *
 * AI财务 · 探针16 —— 领星 SB/SV 广告接口路径与数据形态探测（只读，零写库，零改动生产）。
 *
 * 背景：
 *   领星API文档目录里存在"SB广告/SV广告"两组接口（广告活动/广告组/广告/关键词/平台/页面类型），
 *   但仓库里只有SP系5个端点，SB/SV真实路径未知。真实账单已闭环：对账单"Walmart Product
 *   Advertising"三笔合计-$14,430.60=三张发票之和分毫不差，发票明细含SBV活动（YC00019-SBV
 *   窗口1=$345.32）——SBV花费就在这笔扣款里，是API现覆盖缺口（窗口1 SP总$6059.69 vs 发票
 *   $6607.08，差额~$547主体=SBV）。
 *
 * 本探针做的事（对 CN2601，窗口1 2026-07-10~07-15）：
 *   1) 按SP命名规律枚举SB/SV候选路径（reportAdItem/Keyword/Campaign/AdGroup/Product ×
 *      Sb/Sv），每路径先不带campaignType请求1页50条；失败则原样打印接口error_details
 *      （其中会提示必填字段），再按提示试campaignType候选枚举
 *      （sponsoredBrands/sponsoredVideos及-manual变体）。
 *   2) 任一路径成功返回数据：打印行数、全部字段名、前2条原始JSON、按campaignName聚合的
 *      spend清单（重点找"YC00019"/"SBV"字样活动），候选花费字段逐个求和；
 *      检查行内有无 itemId/adItemId 字段=能否原生归属到品。
 *   3) 末尾汇总表：每个候选路径的探测结果（成功/失败原因），供定稿SBV数据接入方案。
 *
 * 安全边界：只读 LingXing API + 无DB写入（仅查 dim_store_config），零改动生产。
 * 运行（生产机，由部署工程师执行）：npx ts-node src/probeSbSvAdEndpoints.ts
 * 用法：完整输出贴回；重点看成功路径的字段名清单与"YC00019/SBV"活动金额对$345.32的占比。
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const WINDOW = { startDate: "2026-07-10", endDate: "2026-07-15" };
const SBV_INVOICE_SAMPLE = 345.32; // 窗口1发票里 YC00019-SBV-5.11-TEST 的真实花费

const DIMS = ["AdItem", "Keyword", "Campaign", "AdGroup", "Product"];
const TYPES = ["Sb", "Sv"];
const CT_VARIANTS: Array<string[] | undefined> = [
  undefined,
  ["sponsoredBrands"],
  ["sponsoredVideos"],
  ["sponsoredBrands-manual"],
  ["sponsoredVideo"],
];
const SPEND_FIELDS = ["adSpend", "spend", "cost", "adCost", "totalSpend", "amount"];

function toNum(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}
function toStr(v: unknown): string {
  return String(v ?? "").trim();
}
function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
function extractList(data: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(data)) return data as Array<Record<string, unknown>>;
  const d = data as { list?: unknown; data?: unknown } | null;
  if (Array.isArray(d?.list)) return d!.list as Array<Record<string, unknown>>;
  if (Array.isArray(d?.data)) return d!.data as Array<Record<string, unknown>>;
  return [];
}
function errInfo(e: unknown): string {
  const anyE = e as { message?: string; data?: unknown };
  const dataStr = anyE?.data ? JSON.stringify(anyE.data) : "";
  return `${anyE?.message ?? String(e)}${dataStr ? "  data=" + dataStr.slice(0, 500) : ""}`;
}

interface Result {
  path: string;
  outcome: string; // ok(变体X, N行) / 全部失败
  rows: number;
  hasItemField: boolean;
}

async function main() {
  const db = await mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
  const [storeRows] = await db.execute(
    `SELECT store_id, store_name, advertiser_id FROM dim_store_config WHERE platform='walmart' AND store_name LIKE '%瑞盈龙盛%'`,
  );
  await db.end();
  const stores = storeRows as Array<{ store_id: string; store_name: string; advertiser_id: string | null }>;
  if (stores.length === 0 || !stores[0].advertiser_id) { console.log("没匹配到店铺或缺advertiser_id，终止。"); return; }
  const advertiserId = String(stores[0].advertiser_id);
  console.log(`目标店铺: ${stores[0].store_name}  advertiser_id=${advertiserId}  窗口: ${WINDOW.startDate}~${WINDOW.endDate}\n`);

  const client = new LingxingClient(loadConfig());
  const results: Result[] = [];

  for (const t of TYPES) {
    for (const dim of DIMS) {
      const path = `/basicOpen/multiplatform/ads/report${dim}${t}List`;
      console.log(`\n────── 探测 ${path} ──────`);
      const res: Result = { path, outcome: "全部失败", rows: 0, hasItemField: false };
      for (const ct of CT_VARIANTS) {
        const label = ct === undefined ? "不带campaignType" : `campaignType=${JSON.stringify(ct)}`;
        try {
          const params: Record<string, unknown> = {
            advertiserIds: [advertiserId],
            startDate: WINDOW.startDate,
            endDate: WINDOW.endDate,
            pageNum: 1,
            pageSize: 50,
            paging: true,
          };
          if (ct !== undefined) params.campaignType = ct;
          const resp = await client.request<unknown>({ method: "POST", path, params, timeoutMs: 30000 });
          const list = extractList((resp as { data?: unknown }).data);
          console.log(`  [${label}] 成功，返回 ${list.length} 行`);
          res.outcome = `ok(${label}, ${list.length}行)`;
          res.rows = list.length;
          if (list.length > 0) {
            const keys = new Set<string>();
            for (const r of list) for (const k of Object.keys(r)) keys.add(k);
            res.hasItemField = [...keys].some((k) => /item|product/i.test(k));
            console.log(`  字段名: ${[...keys].sort().join(", ")}`);
            console.log(`  前2条原始JSON:`);
            for (const r of list.slice(0, 2)) console.log(JSON.stringify(r));
            const camp = new Map<string, number>();
            let spendField = "";
            for (const f of SPEND_FIELDS) {
              const s = list.reduce((a, r) => a + toNum(r[f]), 0);
              if (s !== 0 && !spendField) spendField = f;
              if (s !== 0) console.log(`  候选花费字段 ${f} 求和=${s.toFixed(2)}`);
            }
            for (const r of list) {
              const name = toStr(r.campaignName) || toStr(r.campaignId) || "(无名)";
              camp.set(name, (camp.get(name) ?? 0) + toNum(r[spendField || "adSpend"]));
            }
            console.log(`  按活动聚合(${spendField || "adSpend"}):`);
            for (const [n, s] of [...camp.entries()].sort((a, b) => b[1] - a[1]).slice(0, 20)) {
              const mark = /YC00019|SBV/i.test(n) ? `  ← SBV样本活动（发票$${SBV_INVOICE_SAMPLE}，占比${((s / SBV_INVOICE_SAMPLE) * 100).toFixed(1)}%）` : "";
              console.log(`    $${s.toFixed(2).padEnd(10)} ${n}${mark}`);
            }
          }
          break; // 本路径已成功，不再试其他变体
        } catch (e) {
          console.log(`  [${label}] 失败: ${errInfo(e)}`);
        }
        await sleep(600);
      }
      results.push(res);
      await sleep(800);
    }
  }

  console.log(`\n=== 汇总 ===\n`);
  for (const r of results) {
    console.log(`${r.path.padEnd(58)} ${r.outcome}${r.rows > 0 ? `  含item字段=${r.hasItemField}` : ""}`);
  }
  console.log(`\n判读：成功且含item字段的路径=SBV可原生归属到品；成功但仅campaign级=SBV需按活动名前缀解析归属；全部失败=需向领星要SB/SV接口文档确认真实路径。`);
  console.log("\n探针16结束。");
}

main().catch((err) => {
  console.error("探针16执行失败：", err);
  process.exit(1);
});
