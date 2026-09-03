/**
 * probeWfsInvRaw.ts — 原样打印 WFS 库存接口返回，定位数据所在字段（只读）
 */
process.env.TZ = 'Asia/Shanghai';
import { LingxingClient } from '../lingxingClient';
import { loadConfig } from '../config';

const WFS_CARGO_PATH = '/cepf/warehouse/api/openApi/queryWFSCargoPage';
const WFS_INV_PATH = '/cepf/warehouse/api/openApi/queryWFSInventionPage';

(async () => {
  const client = new LingxingClient(loadConfig());
  // 取一个 store_id
  const cargo = await client.post(WFS_CARGO_PATH, { offset: 0, length: 5 });
  const cargoData: any = (cargo.data as any)?.data ?? cargo.data;
  const cargoList: any[] = cargoData?.list ?? cargoData ?? [];
  const storeId = String(cargoList[0]?.store_id ?? '').trim();
  console.log('store_id =', storeId);

  const variants: Record<string, unknown>[] = [
    { store_id: storeId, offset: 0, length: 50 },
    { store_id: storeId, page: 1, page_size: 50 },
    { store_ids: [storeId], offset: 0, length: 50 },
  ];
  for (const params of variants) {
    try {
      const resp = await client.post(WFS_INV_PATH, params);
      console.log('\n参数', JSON.stringify(params));
      console.log('原始 resp.data（截断2500）:', JSON.stringify(resp.data).slice(0, 2500));
    } catch (e) {
      console.log('\n参数', JSON.stringify(params), '→ 失败:', e instanceof Error ? e.message : String(e));
    }
  }
})().catch((e) => { console.error('err:', e instanceof Error ? e.message : String(e)); process.exitCode = 1; });
