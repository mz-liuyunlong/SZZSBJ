/**
 * src/ai_pmc/probeShipmentStatus.ts
 * Phase 7B 探测 — 打印 FBA/WFS 发货单状态码在真实数据里的取值分布（只读）
 *
 * 运行：TZ=Asia/Shanghai npx ts-node src/ai_pmc/probeShipmentStatus.ts
 *
 * 目的：把 FBA list[].status 和 WFS cargo_status 的所有取值+出现次数+样本单号打出来，
 *      供人工标注"哪个值=已确认发出 / 哪个值=海外到货"。不发不写。
 */

process.env.TZ = 'Asia/Shanghai';

import { LingxingClient } from '../lingxingClient';
import { loadConfig } from '../config';

const FBA_PATH = '/erp/sc/data/fba_report/shipmentPlanLists';
const WFS_PATH = '/cepf/warehouse/api/openApi/queryWFSCargoPage';
const PAGE = 100;
const MAX_PAGES = 10; // 最多取 1000 条，足够看分布

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

function pickList(d: any): any[] {
  if (Array.isArray(d)) return d;
  if (Array.isArray(d?.list)) return d.list;
  if (Array.isArray(d?.data)) return d.data;
  if (Array.isArray(d?.records)) return d.records;
  if (Array.isArray(d?.data?.list)) return d.data.list;
  return [];
}

async function fetchAll(client: LingxingClient, path: string, flatten: (row: any) => any[]): Promise<any[]> {
  const out: any[] = [];
  for (let p = 0; p < MAX_PAGES; p++) {
    let data: any;
    try {
      const resp = await client.post(path, { offset: p * PAGE, length: PAGE });
      data = (resp.data as any)?.data ?? resp.data;
    } catch (e) {
      console.log(`  拉取失败 offset=${p * PAGE}: ${e instanceof Error ? e.message : String(e)}`);
      break;
    }
    const rows = pickList(data);
    if (rows.length === 0) break;
    for (const r of rows) out.push(...flatten(r));
    if (rows.length < PAGE) break;
    await sleep(200);
  }
  return out;
}

function dist(items: any[], field: string): Record<string, { count: number; samples: string[] }> {
  const d: Record<string, { count: number; samples: string[] }> = {};
  for (const it of items) {
    const v = String(it[field]);
    if (!d[v]) d[v] = { count: 0, samples: [] };
    d[v].count++;
    if (d[v].samples.length < 3) d[v].samples.push(String(it._sn ?? it.order_sn ?? it.cargo_code ?? ''));
  }
  return d;
}

(async () => {
  const client = new LingxingClient(loadConfig());

  console.log('='.repeat(70));
  console.log('FBA 发货计划 shipmentPlanLists — list[].status 分布');
  const fbaItems = await fetchAll(client, FBA_PATH, (plan) => {
    const list = Array.isArray(plan?.list) ? plan.list : [plan];
    return list.map((it: any) => ({ ...it, _sn: it.order_sn ?? plan.seq }));
  });
  console.log(`  明细条数: ${fbaItems.length}`);
  if (fbaItems[0]) console.log('  FBA 明细全部字段名:', Object.keys(fbaItems[0]));
  console.log('  status 分布:', JSON.stringify(dist(fbaItems, 'status'), null, 2));
  // 若有文本状态字段也打出来
  for (const f of ['status_text', 'status_name', 'shipment_status_text']) {
    if (fbaItems[0] && fbaItems[0][f] !== undefined) {
      console.log(`  ${f} 分布:`, JSON.stringify(dist(fbaItems, f), null, 2));
    }
  }

  console.log('='.repeat(70));
  console.log('WFS 货件 queryWFSCargoPage — cargo_status / status 分布');
  const wfsItems = await fetchAll(client, WFS_PATH, (c) => [{ ...c, _sn: c.cargo_code }]);
  console.log(`  货件条数: ${wfsItems.length}`);
  if (wfsItems[0]) console.log('  WFS 全部字段名:', Object.keys(wfsItems[0]));
  for (const f of ['cargo_status', 'status_name', 'status', 'cargo_sync_status']) {
    if (wfsItems[0] && wfsItems[0][f] !== undefined) {
      console.log(`  ${f} 分布:`, JSON.stringify(dist(wfsItems, f), null, 2));
    }
  }

  console.log('\n探测结束。把 status / cargo_status 的分布贴回，并标注哪个值=已确认发出、哪个值=海外到货。');
})().catch((e) => { console.error('probe 致命错误:', e instanceof Error ? e.message : String(e)); process.exitCode = 1; });
