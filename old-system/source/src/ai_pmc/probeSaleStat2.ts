/**
 * probeSaleStat2.ts — 快测销量接口：单日 vs 区间，确认可用方式与字段（只读，1店铺）
 */
process.env.TZ = 'Asia/Shanghai';
import { LingxingClient } from '../lingxingClient';
import { loadConfig } from '../config';
import { STORES } from '../syncDailyBaseData';

const PATH = '/basicOpen/platformStatisticsV2/saleStat/pageList';
function ymd(d: Date) { const p = (n: number) => String(n).padStart(2, '0'); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`; }
function listOf(d: any): any[] { if (Array.isArray(d)) return d; for (const k of ['list','records','rows']) if (Array.isArray(d?.[k])) return d[k]; if (Array.isArray(d?.data?.list)) return d.data.list; return []; }

(async () => {
  const client = new LingxingClient(loadConfig());
  const store = STORES[0];
  const day = ymd(new Date(Date.now() - 3 * 86400000));      // 3天前（单日）
  const rangeStart = ymd(new Date(Date.now() - 9 * 86400000)); // 区间起
  const rangeEnd = ymd(new Date(Date.now() - 3 * 86400000));

  const tests: { label: string; params: Record<string, unknown> }[] = [
    { label: `单日 ${day}`, params: { start_date: day, end_date: day, result_type: '1', date_unit: '4', data_type: '1', page: 1, length: 50, sids: [store.storeId] } },
    { label: `区间 ${rangeStart}~${rangeEnd}`, params: { start_date: rangeStart, end_date: rangeEnd, result_type: '1', date_unit: '4', data_type: '1', page: 1, length: 50, sids: [store.storeId] } },
  ];
  for (const t of tests) {
    const started = Date.now();
    try {
      const resp = await client.request<unknown>({ method: 'POST', path: PATH, params: t.params, timeoutMs: 60000 });
      const data = (resp as any)?.data ?? resp;
      const list = listOf(data);
      console.log(`\n[${t.label}] 用时${((Date.now()-started)/1000).toFixed(1)}s 条数=${list.length}`);
      if (list[0]) {
        console.log('  字段:', Object.keys(list[0]));
        console.log('  样本:', JSON.stringify(list[0]).slice(0, 600));
      }
    } catch (e) {
      console.log(`\n[${t.label}] 用时${((Date.now()-started)/1000).toFixed(1)}s 失败: ${e instanceof Error ? e.message : String(e)}`);
    }
  }
})().catch((e) => { console.error('err:', e instanceof Error ? e.message : String(e)); process.exitCode = 1; });
