/**
 * src/probeStoreSettlementReconcileV2.ts
 *
 * 单品现金利润模块 · 探针5 —— 探针4结果分析后的第二轮，缩窄时间窗+拿逐条list明细做更精细核对。
 *
 * 探针4已确认的两件事：
 *   1) 领星"结算日期"≠回款到账日期——07-08~07-16(覆盖到账日Jul14)那个窗口查出来是0条，
 *      05-20~06-25(覆盖CSV里各笔交易自己的活动日期)那个窗口才有数据，说明"结算日期"对应的是
 *      交易自身发生的日期，不是打款日期。
 *   2) 但05-20~06-25这个窗口是我故意放宽的，比CSV实际覆盖的活动区间(观察到最早05/28、最晚06/19)
 *      要宽，所以salesNum=2075、salesAmount=227430.01(CNY)这些总数没法跟CSV的978笔/15900.43(USD)
 *      直接比——范围对不上，比出来的比例(汇率隐含~14倍)明显不合理，掺了窗口外的额外交易。
 *   3) 另外发现：接口返回的 currencyCode 是 CNY，不是USD——币种也得先对齐才能比金额。
 *   4) 上一轮只打印了 totalSum，里面只有 promotionAmount/platformLogisticsAmount/platformStorageAmount
 *      这类大类字段，没有 wfsShipmentFee/wfsWarehousFee/semMarketingFee 这些沃尔玛专属细分字段——
 *      这些细分字段有没有可能出现在逐条 list 明细里，本探针也一并试一下，能拿到细分才能跟CSV按
 *      Transaction Description(WFS Fulfillment fee/WFS Inbound Fee/SEM Marketing Fee等)逐项对齐。
 *
 * 本探针做的事：
 *   1) 用探针4已确认的真实 store_id (CN2602-添详商贸)，把窗口收窄到 2026-05-28~2026-06-19
 *      （CSV里观察到的实际活动区间边界），期望 salesNum 更接近CSV的978笔SALE行。
 *   2) 不止打印 totalSum，也把 list 逐条明细的完整原始JSON打出来（不筛字段），看看沃尔玛专属
 *      细分费用字段（wfsShipmentFee等）到底会不会出现在真实返回里。
 *   3) 额外查一下这个店铺 dim_product_cost_config 或其它地方有没有现成的CNY/USD汇率记录可参考
 *      ——这次不查DB汇率表（还不确定有没有这张表），先把真实接口数据拿到，汇率换算放到人工核对阶段。
 *
 * 安全边界：只读 LingXing API，零数据库写入，零改动生产，不建表。
 *
 * 运行（生产机，由部署工程师执行）：
 *   npx ts-node src/probeStoreSettlementReconcileV2.ts
 *
 * 用法：把完整输出贴回来，重点看 salesNum 是否更接近978，以及 list 明细里有没有出现
 *      wfsShipmentFee/wfsWarehousFee/semMarketingFee 等沃尔玛专属字段。
 */

import "dotenv/config";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const SETTLEMENT_MSKU_PATH = "/basicOpen/multiplatform/profit/report/msku";
const WALMART_PLATFORM_CODE = "10008";
const TARGET_STORE_ID = "110689966555011584"; // CN2602-添详商贸(邓添祥)，探针4已确认

async function main() {
  const cfg = loadConfig();
  const client = new LingxingClient(cfg);

  const startDate = "2026-05-28";
  const endDate = "2026-06-19";

  console.log(`探针5启动 | store_id=${TARGET_STORE_ID}(CN2602-添详商贸) | 窗口(结算日期) ${startDate}~${endDate}`);

  const resp = await client.request<{
    totalSum?: Record<string, unknown>;
    total?: number;
    list?: Array<Record<string, unknown>>;
  }>({
    method: "POST",
    path: SETTLEMENT_MSKU_PATH,
    params: {
      offset: 0,
      length: 200,
      platformCodeS: [WALMART_PLATFORM_CODE],
      sids: TARGET_STORE_ID,
      startDate,
      endDate,
    },
    timeoutMs: 30000,
  });

  const data = (resp as unknown as { data?: { totalSum?: Record<string, unknown>; total?: number; list?: Array<Record<string, unknown>> } }).data;

  console.log(`\ntotal字段: ${data?.total ?? "(无此字段)"}`);
  console.log(`list条数: ${data?.list?.length ?? 0}`);
  console.log(`\ntotalSum完整原始JSON:`);
  console.log(JSON.stringify(data?.totalSum ?? {}, null, 2));

  const list = data?.list ?? [];
  console.log(`\n=== list逐条明细（全部${list.length}条，完整原始JSON，不筛字段）===`);
  for (let i = 0; i < list.length; i++) {
    console.log(`\n--- 第${i + 1}条 ---`);
    console.log(JSON.stringify(list[i], null, 2));
  }

  // 顺手看一下 list 里出现过的所有字段名合集，方便一眼看出有没有沃尔玛专属细分字段
  const allKeys = new Set<string>();
  for (const row of list) {
    for (const k of Object.keys(row)) allKeys.add(k);
  }
  console.log(`\n=== list明细里出现过的全部字段名（去重）共${allKeys.size}个 ===`);
  console.log([...allKeys].sort().join(", "));
}

main().catch((err) => {
  console.error("探针5执行失败：", err);
  process.exit(1);
});
