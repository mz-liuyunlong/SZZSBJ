/**
 * src/ai_pmc/probeSales.ts
 * Phase 8 探测 — 摸清领星「查询销量统计列表V2」的参数与字段（只读）
 *
 * 接口：POST /basicOpen/platformStatisticsV2/saleStat/pageList
 * 运行：TZ=Asia/Shanghai npx ts-node src/ai_pmc/probeSales.ts
 *
 * 目的：确认 ① 哪种参数组合能成功 ② 返回里哪个字段是 SKU/ItemID、哪个是销量件数、哪个是日期维度。
 */

process.env.TZ = 'Asia/Shanghai';

import { LingxingClient } from '../lingxingClient';
import { loadConfig } from '../config';

const PATH = '/basicOpen/platformStatisticsV2/saleStat/pageList';

function ymd(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

(async () => {
  const client = new LingxingClient(loadConfig());
  const today = new Date();
  const start = new Date(today.getTime() - 7 * 86400000); // 近7天，探测足够
  const sd = ymd(start), ed = ymd(today);

  // 多组候选参数（领星统计类接口常见传参不一，逐个试）
  const variants: Record<string, unknown>[] = [
    { offset: 0, length: 20, start_date: sd, end_date: ed },
    { offset: 0, length: 20, startDate: sd, endDate: ed },
    { offset: 0, length: 20, start_date: sd, end_date: ed, date_type: 'day' },
    { page: 1, length: 20, start_date: sd, end_date: ed },
    { offset: 0, length: 20, sids: [], start_date: sd, end_date: ed },
    { offset: 0, length: 20 },
  ];

  for (const params of variants) {
    try {
      const resp = await client.post(PATH, params);
      const code = (resp.data as any)?.code;
      const data = (resp.data as any)?.data ?? resp.data;
      const list: any[] =
        Array.isArray(data) ? data :
        Array.isArray(data?.list) ? data.list :
        Array.isArray(data?.records) ? data.records :
        Array.isArray(data?.rows) ? data.rows : [];
      console.log(`\n参数 ${JSON.stringify(params)} → code=${code} 列表条数=${list.length}`);
      if (list.length > 0) {
        console.log('  首条字段名:', Object.keys(list[0]));
        const k = Object.keys(list[0]);
        const skuKeys = k.filter((x) => /sku|msku|asin|item|product/i.test(x));
        const qtyKeys = k.filter((x) => /qty|quantity|num|volume|sales|order|sale_/i.test(x));
        const dateKeys = k.filter((x) => /date|time|day|month/i.test(x));
        console.log('  可能SKU字段:', skuKeys);
        console.log('  可能销量字段:', qtyKeys);
        console.log('  可能日期字段:', dateKeys);
        console.log('  首条样本(截断):', JSON.stringify(list[0]).slice(0, 1200));
        console.log('\n✅ 此参数组合可用，探测结束。');
        return;
      }
    } catch (e) {
      console.log(`\n参数 ${JSON.stringify(params)} → 失败: ${e instanceof Error ? e.message : String(e)}`);
    }
  }
  console.log('\n⚠️ 所有参数组合均未取到数据，需查领星文档确认必填参数（如 sid/日期格式/统计维度）。');
})().catch((e) => { console.error('probe 致命错误:', e instanceof Error ? e.message : String(e)); process.exitCode = 1; });
