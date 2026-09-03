/**
 * src/ai_pmc/probeReplenish.ts （v2 精准版）
 * Phase 8 探测 — 销量统计V2 必填参数 + WFS库存(遍历店铺)
 */

process.env.TZ = 'Asia/Shanghai';

import { LingxingClient } from '../lingxingClient';
import { loadConfig } from '../config';

const SALES_PATH = '/basicOpen/platformStatisticsV2/saleStat/pageList';
const WFS_CARGO_PATH = '/cepf/warehouse/api/openApi/queryWFSCargoPage';
const WFS_INV_PATH = '/cepf/warehouse/api/openApi/queryWFSInventionPage';

function ymd(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
function listOf(data: any): any[] {
  if (Array.isArray(data)) return data;
  for (const k of ['list', 'records', 'rows']) if (Array.isArray(data?.[k])) return data[k];
  if (Array.isArray(data?.data?.list)) return data.data.list;
  return [];
}
function describe(label: string, list: any[]) {
  console.log(`  [${label}] 条数=${list.length}`);
  if (!list.length) return;
  const k = Object.keys(list[0]);
  console.log('  字段名:', k);
  console.log('  可能SKU:', k.filter((x) => /sku|msku|asin|item|product/i.test(x)));
  console.log('  可能数量/销量:', k.filter((x) => /qty|quantity|num|volume|sales|stock|available|valid|inventory|sale/i.test(x)));
  console.log('  样本(截断):', JSON.stringify(list[0]).slice(0, 1100));
}

(async () => {
  const client = new LingxingClient(loadConfig());
  const today = new Date();
  const sd = ymd(new Date(today.getTime() - 7 * 86400000)), ed = ymd(today);
  const base = { offset: 0, length: 20, start_date: sd, end_date: ed };

  // ① 销量统计V2：补全常见必填字段
  console.log('='.repeat(70) + '\n① 销量统计V2');
  const salesVariants: Record<string, unknown>[] = [
    { ...base, summary_field: 'sku', sort_field: 'volume', sort_type: 'desc' },
    { ...base, summary_field: 'msku', sort_field: 'volume', sort_type: 'desc' },
    { ...base, summary_field: 'sku', sort_field: 'volume', sort_type: 'desc', req_time_type: 1 },
    { ...base, summary_field: 'asin', sort_field: 'volume', sort_type: 'desc' },
    { ...base, summary_field: 'local_sku', sort_field: 'volume', sort_type: 'desc' },
    { ...base, summary_field: 'sku' },
  ];
  for (const params of salesVariants) {
    try {
      const resp = await client.post(SALES_PATH, params);
      const data = (resp.data as any)?.data ?? resp.data;
      const list = listOf(data);
      console.log(`\n 参数 ${JSON.stringify(params)} → code=${(resp.data as any)?.code} 条数=${list.length}`);
      if (list.length) { describe('销量', list); console.log(' ✅ 销量参数可用'); break; }
    } catch (e) {
      console.log(`\n 参数 ${JSON.stringify(params)} → 失败: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  // ② WFS库存：收集所有 store_id，逐店查到非空
  console.log('\n' + '='.repeat(70) + '\n② WFS库存（遍历店铺）');
  const storeIds = new Set<string>();
  try {
    for (let off = 0; off < 300; off += 100) {
      const resp = await client.post(WFS_CARGO_PATH, { offset: off, length: 100 });
      const list = listOf((resp.data as any)?.data ?? resp.data);
      if (!list.length) break;
      for (const c of list) { const s = String(c?.store_id ?? '').trim(); if (s) storeIds.add(s); }
      if (list.length < 100) break;
    }
  } catch (e) { console.log('  收集 store_id 失败:', e instanceof Error ? e.message : String(e)); }
  console.log('  店铺数:', storeIds.size, [...storeIds].slice(0, 5));

  let found = false;
  for (const sid of storeIds) {
    try {
      const resp = await client.post(WFS_INV_PATH, { offset: 0, length: 50, store_id: sid });
      const list = listOf((resp.data as any)?.data ?? resp.data);
      if (list.length) {
        console.log(`\n  store_id=${sid} → 条数=${list.length}`);
        describe('WFS库存', list);
        console.log(' ✅ WFS库存参数可用（store_id 逐店查）');
        found = true;
        break;
      }
    } catch { /* 跳过该店 */ }
  }
  if (!found) console.log('  所有店铺 WFS 库存均为空或失败（可能近期无 WFS 库存）。');

  console.log('\n探测结束。把销量、WFS库存两段的字段贴回。');
})().catch((e) => { console.error('probe 致命错误:', e instanceof Error ? e.message : String(e)); process.exitCode = 1; });
