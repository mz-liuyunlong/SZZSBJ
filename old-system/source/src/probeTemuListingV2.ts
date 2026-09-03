/**
 * probeTemuListingV2.ts — 领星 TEMU listing 精准探测 v2（只读，2026-08-03）
 * 目的：确认 mskuId 是否=订单口径SKU ID(JJ4091应=174152333938300)、"在售"对应 status 值、msku/sku 配对形态。
 * 只读。用法（生产）：npx ts-node src/probeTemuListingV2.ts
 */
import "dotenv/config";
import { loadConfig } from "./config";
import { LingxingClient, LingxingRequestError } from "./lingxingClient";

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));
type Dict = Record<string, unknown>;
const PATH = "/basicOpen/multiplatform/temu/list";
const STORES = ["110726789976100864", "110726793010007040"]; // puravida半托 / Furniture Haven

function asList(data: unknown): Dict[] {
  if (Array.isArray(data)) return data as Dict[];
  if (data && typeof data === "object" && Array.isArray((data as Dict).list)) return (data as Dict).list as Dict[];
  return [];
}
function errInfo(e: unknown): Dict {
  if (e instanceof LingxingRequestError) return { message: e.message, status: e.status, data: e.data };
  return { message: e instanceof Error ? e.message : String(e) };
}
function pick(r: Dict): Dict {
  return { store: r.storeName, msku: r.msku, sku: r.sku, mskuId: r.mskuId, spuId: r.spuId, status: r.status, day7: r.day7SaleCnt, day30: r.day30SaleCnt, title: String(r.title ?? "").slice(0, 30) };
}

async function main(): Promise<void> {
  const client = new LingxingClient(loadConfig());
  const out: Dict = {};

  // A) 试 MSKU 搜索（search_field=1）看 temu/list 是否支持精确过滤
  try {
    const r = await client.request<unknown>({ method: "POST", path: PATH, params: { offset: 0, length: 50, store_ids: STORES, search_field: 1, search_single_value: "JJ4091" }, timeoutMs: 30000 });
    const list = asList(r.data);
    out.search_msku_JJ4091 = { count: list.length, matches: list.filter((x) => /^JJ4091/i.test(String(x.msku ?? ""))).map(pick), first3: list.slice(0, 3).map(pick) };
  } catch (e) { out.search_msku_JJ4091_err = errInfo(e); }
  await sleep(2500);

  // B) 翻页+客户端过滤 msku ~ ^(JJ|YC)，两店合并；打印 status 分布
  const matched: Dict[] = [];
  const statusCount: Record<string, number> = {};
  let scanned = 0;
  for (const store of STORES) {
    for (let page = 0; page < 20; page++) {
      let list: Dict[] = [];
      try {
        const r = await client.request<unknown>({ method: "POST", path: PATH, params: { offset: page * 50, length: 50, store_ids: [store] }, timeoutMs: 30000 });
        list = asList(r.data);
      } catch (e) { out[`paginate_err_${store}_p${page}`] = errInfo(e); break; }
      scanned += list.length;
      for (const x of list) {
        const st = String(x.status ?? "");
        statusCount[st] = (statusCount[st] ?? 0) + 1;
        if (/^(JJ|YC)/i.test(String(x.msku ?? ""))) matched.push(pick(x));
      }
      if (list.length < 50) break;
      await sleep(2500);
    }
  }
  out.scanned = scanned;
  out.status_distribution = statusCount;
  out.matched_JJ_YC_count = matched.length;
  out.matched_JJ_YC = matched;
  out.jj4091 = matched.filter((m) => /^JJ4091/i.test(String(m.msku ?? "")));
  out.jj5121 = matched.filter((m) => /^JJ5121/i.test(String(m.msku ?? "")));

  console.log(JSON.stringify(out, null, 2));
}
main().catch((e) => { console.error("PROBE_FATAL", e instanceof Error ? e.message : e); process.exit(1); });
