/**
 * probeTemuListing.ts — 领星 TEMU「在售」商品 listing 探测（只读，2026-08-03）
 * 目的：为"清货台账自动抓取TEMU在售品"选定端点与字段映射（SKU=MSKU前缀 / platform_ref=店铺后台SKU ID / 上架状态在售）。
 * 只读：仅调用 list/getSellerList/getPairList（assertReadOnlyPath 已拦写操作）。不写库、不改数据。
 * 用法（生产 /opt/lingxing-auto）：npx ts-node src/probeTemuListing.ts
 * 输出：stdout JSON。测品以 YC/JJ 开头。
 */
import "dotenv/config";
import { loadConfig } from "./config";
import { LingxingClient, LingxingRequestError } from "./lingxingClient";

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));
type Dict = Record<string, unknown>;

function asList(data: unknown): Dict[] {
  if (Array.isArray(data)) return data as Dict[];
  if (data && typeof data === "object") {
    const d = data as Dict;
    if (Array.isArray(d.list)) return d.list as Dict[];
  }
  return [];
}
function errInfo(e: unknown): Dict {
  if (e instanceof LingxingRequestError) return { message: e.message, status: e.status, data: e.data };
  return { message: e instanceof Error ? e.message : String(e) };
}

async function main(): Promise<void> {
  const client = new LingxingClient(loadConfig());
  const out: Dict = {};

  // 1) 店铺列表 → 找 TEMU 店铺（平台码 10022/10024 或名称含 TEMU/半托管）
  try {
    const r = await client.request<unknown>({ method: "POST", path: "/pb/mp/shop/v2/getSellerList", params: {}, timeoutMs: 30000 });
    const list = asList(r.data);
    const temu = list.filter((s) => /temu|半托管/i.test(JSON.stringify(s)) || ["10022", "10024"].includes(String((s).platform_code ?? "")));
    out.sellerList_total = list.length;
    out.sellerList_keys = list[0] ? Object.keys(list[0]) : [];
    out.temu_stores = temu.map((s) => ({ store_id: s.store_id ?? s.sid ?? s.id, name: s.store_name ?? s.name, platform_code: s.platform_code, platform_name: s.platform_name }));
  } catch (e) { out.sellerList_err = errInfo(e); }
  await sleep(2500);

  const temuStoreIds = ((out.temu_stores as Dict[] | undefined) ?? []).map((s) => String(s.store_id)).filter(Boolean);
  out.temu_store_ids_used = temuStoreIds;

  // 2) 试 /basicOpen/multiplatform/temu/list（镜像 walmart/list），按 SKU 前缀 JJ / YC 搜
  for (const kw of ["JJ", "YC"]) {
    try {
      const params: Dict = { offset: 0, length: 50, search_field: 3, search_single_value: kw };
      if (temuStoreIds.length) params.store_ids = temuStoreIds;
      const r = await client.request<unknown>({ method: "POST", path: "/basicOpen/multiplatform/temu/list", params, timeoutMs: 30000 });
      const list = asList(r.data);
      out[`temuList_${kw}`] = { code: r.code, msg: r.message ?? r.msg, count: list.length, keys: list[0] ? Object.keys(list[0]) : [], sample: list.slice(0, 3) };
    } catch (e) { out[`temuList_${kw}_err`] = errInfo(e); }
    await sleep(2500);
  }

  // 3) 回退：getPairList（TEMU 平台码），拿 msku↔sku 配对结构
  try {
    const r = await client.request<unknown>({ method: "POST", path: "/pb/mp/listing/v2/getPairList", params: { offset: 0, length: 50, platform_codes: ["10022", "10024"], sku: ["JJ4091", "JJ5121"] }, timeoutMs: 30000 });
    const list = asList(r.data);
    out.pairList = { code: r.code, count: list.length, keys: list[0] ? Object.keys(list[0]) : [], sample: list.slice(0, 3) };
  } catch (e) { out.pairList_err = errInfo(e); }

  console.log(JSON.stringify(out, null, 2));
}

main().catch((e) => { console.error("PROBE_FATAL", e instanceof Error ? e.message : e); process.exit(1); });
