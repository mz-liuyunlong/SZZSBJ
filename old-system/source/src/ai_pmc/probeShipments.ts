/**
 * src/ai_pmc/probeShipments.ts
 * Phase 7 探测 — 摸清领星发货单接口的真实返回结构（只读，安全）
 *
 * 运行：  TZ=Asia/Shanghai npx ts-node src/ai_pmc/probeShipments.ts
 *
 * 目的：打印 FBA/WFS 发货接口的字段名、状态分布、关联键样本，
 *      供设计 fetchShipments + 发货阶段枚举使用。不发不写。
 */

process.env.TZ = 'Asia/Shanghai';

import { LingxingClient } from '../lingxingClient';
import { loadConfig } from '../config';

const ENDPOINTS: Array<{ name: string; path: string; paramVariants: Record<string, unknown>[] }> = [
  {
    name: 'FBA发货计划 shipmentPlanLists',
    path: '/erp/sc/data/fba_report/shipmentPlanLists',
    paramVariants: [{ offset: 0, length: 10 }, { offset: 0, length: 10, sid: 0 }, {}],
  },
  {
    name: 'WFS货件 queryWFSCargoPage',
    path: '/cepf/warehouse/api/openApi/queryWFSCargoPage',
    paramVariants: [{ offset: 0, length: 10 }, { pageNo: 1, pageSize: 10 }, { current: 1, size: 10 }, {}],
  },
  {
    name: 'WFS库存 queryWFSInventionPage',
    path: '/cepf/warehouse/api/openApi/queryWFSInventionPage',
    paramVariants: [{ offset: 0, length: 10 }, { pageNo: 1, pageSize: 10 }, { current: 1, size: 10 }, {}],
  },
];

function summarize(label: string, data: unknown): void {
  // 尝试在常见包装层里找到列表
  const d = data as any;
  const list: any[] | null =
    Array.isArray(d) ? d :
    Array.isArray(d?.list) ? d.list :
    Array.isArray(d?.data) ? d.data :
    Array.isArray(d?.records) ? d.records :
    Array.isArray(d?.rows) ? d.rows :
    Array.isArray(d?.data?.list) ? d.data.list :
    null;

  if (!list) {
    console.log(`  [${label}] 未识别到列表，顶层结构 keys:`, data && typeof data === 'object' ? Object.keys(data as object) : typeof data);
    console.log('  原始(截断):', JSON.stringify(data).slice(0, 800));
    return;
  }
  console.log(`  [${label}] 列表条数: ${list.length}`);
  if (list.length === 0) return;
  const first = list[0];
  console.log('  首条字段名:', Object.keys(first));
  // 找出像"状态"的字段
  const statusKeys = Object.keys(first).filter((k) => /status|state|stage|step|stat/i.test(k));
  for (const sk of statusKeys) {
    const dist: Record<string, number> = {};
    list.forEach((x) => { const v = String(x[sk]); dist[v] = (dist[v] || 0) + 1; });
    console.log(`  状态字段 ${sk} 分布:`, JSON.stringify(dist));
  }
  // 找出像"关联键/SKU/单号"的字段
  const linkKeys = Object.keys(first).filter((k) => /sku|msku|order|shipment|plan|seller_sku|fnsku|sn|batch|po/i.test(k));
  console.log('  可能的关联键:', linkKeys);
  console.log('  首条样本(截断):', JSON.stringify(first).slice(0, 1000));
}

async function probe(client: LingxingClient, ep: typeof ENDPOINTS[number]): Promise<void> {
  console.log('\n' + '='.repeat(70));
  console.log('接口:', ep.name, '→', ep.path);
  for (const params of ep.paramVariants) {
    try {
      const resp = await client.post(ep.path, params);
      console.log(`\n 参数 ${JSON.stringify(params)} → HTTP ${resp.status} code=${(resp.data as any)?.code}`);
      summarize('OK', (resp.data as any)?.data ?? resp.data);
      return; // 成功一种就够
    } catch (e) {
      console.log(`\n 参数 ${JSON.stringify(params)} → 失败: ${e instanceof Error ? e.message : String(e)}`);
    }
  }
  console.log('  ⚠️ 所有参数组合均失败，需查领星文档确认必填参数。');
}

(async () => {
  const client = new LingxingClient(loadConfig());
  for (const ep of ENDPOINTS) {
    await probe(client, ep);
    await new Promise((r) => setTimeout(r, 300));
  }
  console.log('\n探测结束。把以上输出贴回，用于设计 Phase 7。');
})().catch((e) => { console.error('probe 致命错误:', e instanceof Error ? e.message : String(e)); process.exitCode = 1; });
