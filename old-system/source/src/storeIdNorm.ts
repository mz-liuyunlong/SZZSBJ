/**
 * storeIdNorm.ts — 领星 store_id 数字精度损坏修复共享件（2026-08-18）
 * 背景：部分领星接口返回数字型 storeId，超JS安全整数，JSON.parse 即损坏（末位差±≤16）。
 * 规则与 AI财务 aiFinanceRoutes.normStore 逐字同源：前缀完全相同 + 末4位数值差≤16 → 就近映射
 * 回 dim_store 合法id；无候选返回 null（调用方决定保留原值或剔除）。
 */
import * as mysql from "mysql2/promise";

export function closeId(a: string, b: string): boolean {
  if (a.length !== b.length || a.length < 5) return false;
  if (a.slice(0, -4) !== b.slice(0, -4)) return false;
  return Math.abs(Number(a.slice(-4)) - Number(b.slice(-4))) <= 16;
}

export async function buildStoreNormalizer(db: mysql.Connection): Promise<(id: string) => string | null> {
  const [rows] = await db.execute(`SELECT store_id FROM dim_store WHERE platform='walmart'`);
  const valid = new Set<string>();
  for (const r of rows as Array<Record<string, unknown>>) valid.add(String(r.store_id));
  const validArr = Array.from(valid);
  const cache = new Map<string, string | null>();
  return (id: string): string | null => {
    if (!id) return null;
    if (valid.has(id)) return id;
    if (cache.has(id)) return cache.get(id)!;
    let hit: string | null = null;
    for (const v of validArr) { if (closeId(v, id)) { hit = v; break; } }
    cache.set(id, hit);
    return hit;
  };
}
