/**
 * probeWalmartStoresAdvertisers.ts  —— 只读探测（可删）
 *
 * 目的：为"店铺自动发现"方案做地基验证。只调两个领星接口并打印，
 *      不写数据库、不改任何同步逻辑。
 *   1) 店铺列表   /pb/mp/shop/v2/getSellerList   (platform_code=10008 Walmart)
 *   2) 广告主列表 /basicOpen/adReport/advertiser/list
 * 输出：字段样例 + 按名字的 store↔advertiser 映射 + 一对多风险 + HK2612~2615 排查
 *
 * 运行：npx ts-node src/probeWalmartStoresAdvertisers.ts
 */
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const norm = (v: unknown): string => String(v ?? "").trim();

async function main(): Promise<void> {
  const client = new LingxingClient(loadConfig());

  // ── 1. 沃尔玛店铺列表 ────────────────────────────────────────────────
  const stores: Record<string, unknown>[] = [];
  for (let offset = 0; offset < 4000; offset += 200) {
    const resp = await client.request<{ list?: unknown[]; total?: unknown }>({
      method: "POST",
      path: "/pb/mp/shop/v2/getSellerList",
      params: { offset, length: 200, platform_code: [10008] },
      timeoutMs: 60000,
    });
    const list = ((resp.data as { list?: unknown[] })?.list ?? []) as Record<string, unknown>[];
    stores.push(...list);
    if (list.length < 200) break;
  }
  console.log("===== 1. 沃尔玛店铺列表 (getSellerList) =====");
  console.log("店铺数:", stores.length);
  for (const s of stores) {
    console.log(`  store_id=${norm(s.store_id)} | store_name=${norm(s.store_name)} | is_sync=${norm(s.is_sync)} | status=${norm(s.status)}`);
  }

  // ── 2. 广告主列表 ───────────────────────────────────────────────────
  const ads: Record<string, unknown>[] = [];
  for (let page = 1; page <= 30; page++) {
    const resp = await client.request<{ list?: unknown[]; total?: unknown }>({
      method: "POST",
      path: "/basicOpen/adReport/advertiser/list",
      params: { paging: true, limit: 200, page },
      timeoutMs: 60000,
    });
    const list = ((resp.data as { list?: unknown[] })?.list ?? []) as Record<string, unknown>[];
    ads.push(...list);
    if (list.length < 200) break;
  }
  console.log("\n===== 2. 广告主列表 (advertiser/list) =====");
  console.log("广告主数:", ads.length);
  for (const a of ads) {
    console.log(`  advertiserId=${norm(a.advertiserId)} | advertiserName=${norm(a.advertiserName)} | status=${norm(a.status)}`);
  }

  // ── 3. 按名字匹配 store ↔ advertiser ────────────────────────────────
  const adByName = new Map<string, string[]>();
  for (const a of ads) {
    const n = norm(a.advertiserName);
    (adByName.get(n) ?? adByName.set(n, []).get(n)!).push(norm(a.advertiserId));
  }
  console.log("\n===== 3. store_name ↔ advertiser 名字匹配 =====");
  for (const s of stores) {
    const matched = adByName.get(norm(s.store_name)) ?? [];
    const flag = matched.length > 1 ? "  ⚠️一店多广告主" : matched.length === 0 ? "  ⚠️无匹配" : "";
    console.log(`  ${norm(s.store_name)} | store_id=${norm(s.store_id)} | advertiserId=${matched.join(",") || "(无)"}${flag}`);
  }

  // ── 4. 一个广告主名重复（一广告主多店风险）────────────────────────
  console.log("\n===== 4. 重复广告主名（一广告主多店风险）=====");
  let dup = 0;
  for (const [n, ids] of adByName) {
    if (ids.length > 1) { console.log(`  ${n}: advertiserIds=${ids.join(",")}`); dup++; }
  }
  if (!dup) console.log("  无重复广告主名");

  // ── 5. HK2612~2615 专查 ─────────────────────────────────────────────
  console.log("\n===== 5. HK2612~2615 排查 =====");
  for (const key of ["HK2612", "HK2613", "HK2614", "HK2615"]) {
    const st = stores.filter((s) => norm(s.store_name).includes(key));
    const ad = ads.filter((a) => norm(a.advertiserName).includes(key));
    console.log(`  ${key}: 店铺=[${st.map((s) => `${norm(s.store_id)}(${norm(s.store_name)})`).join("; ") || "无"}] | 广告主=[${ad.map((a) => `${norm(a.advertiserId)}(${norm(a.advertiserName)})`).join("; ") || "无"}]`);
  }
}

main().catch((e) => { console.error("探测失败:", e); process.exit(1); });
