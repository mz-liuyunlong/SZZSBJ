/**
 * src/probeStoreSettlementReconcile.ts
 *
 * 单品现金利润模块 · 探针4 —— 用真实Walmart回款CSV核对领星结算利润接口是否可信（只读，零写库，零改动生产）。
 *
 * 背景：
 *   用户提供了店铺"CN2602-添详商贸(邓添祥)"2026-06-07~06-21这期真实Walmart回款的官方CSV
 *   （Payments Report 旧版，transaction_type/amount_type字段体系），本地手工核对：
 *   除PaymentSummary行外，全部5035行Amount列求和 = 5372.14，跟Payoneer实际到账金额一分不差。
 *   按 Amount Type 拆出的真实分类金额（作为本探针的比对基准，全部来自这份已验证过的真实CSV）：
 *     Product Price(销售额)            +15900.43
 *     Commission on Product(产品佣金)   -1341.34
 *     WFS Inbound Fee(WFS入仓费)        -1202.44
 *     WFS Inventory Fee/Reimbursement   +655.36
 *     Promo Code(促销折扣)              -155.67
 *     Total Walmart Funded Savings      +14.75
 *     SEM Marketing Fee                 -4.07
 *     Other tax (Fees)                  +0.69
 *     WFS Fulfillment fee(WFS发货/尾程费) -5044.67  (977笔)
 *     Walmart Product Advertising(广告费) -3169.95  (3笔)
 *     WFS Return Processing Fee(WFS退货处理费) -273.60 (36笔)
 *     Product tax / Product tax withheld  净0(代收代缴)
 *
 * 本探针做的事：
 *   1) 从生产DB dim_store_config 按店铺名模糊匹配"添详"/"CN2602"/"邓添祥"，找出真实 store_id。
 *      如果一个都没匹配上，把全部10个walmart店铺原样打出来，人工核对选哪个。
 *   2) 用探针2已验证可用的 /basicOpen/multiplatform/profit/report/msku 接口，加上这个店铺的
 *      sids，分别用两个候选日期窗口去查（因为不确定"结算日期"对应CSV里的哪个日期概念）：
 *        窗口甲：2026-05-20~2026-06-25（覆盖CSV里逐行"Period Start/End Date"实际发生的活动区间）
 *        窗口乙：2026-07-08~2026-07-16（覆盖CSV PaymentSummary行的Transaction Posted Timestamp
 *                07/11和邮件里的Date processed Jul 14）
 *      两个窗口都要，不猜哪个对，让真实返回的totalSum数字自己说话——哪个窗口的totalSum跟上面CSV
 *      基准数字对得上，就说明"结算日期"在领星里是按哪个语义在算。
 *   3) 把每个窗口返回的完整 totalSum 原始JSON打印出来（不做字段筛选，避免遗漏），供人工逐项核对。
 *
 * 安全边界：
 *   - 只读 LingXing API + 只读 DB SELECT（dim_store_config），零写库、零改动生产、不建表。
 *
 * 运行（生产机，由部署工程师执行）：
 *   npx ts-node src/probeStoreSettlementReconcile.ts
 *   npx ts-node src/probeStoreSettlementReconcile.ts --store-like=添详   # 换个模糊匹配关键字
 *
 * 用法：把完整输出贴回来，重点是两个窗口各自的 totalSum 原始JSON，我会逐项跟CSV基准数字核对。
 */

import "dotenv/config";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const SETTLEMENT_MSKU_PATH = "/basicOpen/multiplatform/profit/report/msku";
const WALMART_PLATFORM_CODE = "10008";

function getArg(name: string, fallback: string): string {
  const prefix = `--${name}=`;
  const arg = process.argv.find((a) => a.startsWith(prefix));
  return arg ? arg.slice(prefix.length) : fallback;
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

async function main() {
  const storeLike = getArg("store-like", "");

  const db = await mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });

  const [allStores] = await db.execute(
    `SELECT store_id, store_name FROM dim_store_config WHERE platform = 'walmart'`,
  );
  const stores = allStores as Array<{ store_id: string; store_name: string }>;
  console.log("生产DB dim_store_config 里全部 walmart 店铺：");
  for (const s of stores) console.log(`  store_id=${s.store_id}  store_name=${s.store_name}`);

  const keywords = storeLike ? [storeLike] : ["添详", "CN2602", "邓添祥"];
  const matched = stores.filter((s) => keywords.some((kw) => (s.store_name || "").includes(kw)));
  console.log(`\n按关键字 [${keywords.join(", ")}] 模糊匹配到 ${matched.length} 个店铺：`);
  for (const s of matched) console.log(`  store_id=${s.store_id}  store_name=${s.store_name}`);

  await db.end();

  if (matched.length === 0) {
    console.log("\n没匹配到任何店铺，无法继续调用结算利润接口。把上面打印的全部店铺名贴回来，人工指认哪个是目标店铺。");
    return;
  }
  if (matched.length > 1) {
    console.log("\n匹配到不止一个店铺，下面会对每一个都各查一遍，人工从结果里辨认哪个是目标店铺。");
  }

  const cfg = loadConfig();
  const client = new LingxingClient(cfg);

  const windows: Array<{ label: string; startDate: string; endDate: string }> = [
    { label: "窗口甲(覆盖CSV逐行活动区间 05-20~06-25)", startDate: "2026-05-20", endDate: "2026-06-25" },
    { label: "窗口乙(覆盖PaymentSummary发放日 07-08~07-16)", startDate: "2026-07-08", endDate: "2026-07-16" },
  ];

  for (const store of matched) {
    console.log(`\n\n########## 店铺 store_id=${store.store_id} (${store.store_name}) ##########`);
    for (const w of windows) {
      console.log(`\n--- ${w.label}：${w.startDate} ~ ${w.endDate} ---`);
      try {
        const resp = await client.request<{ totalSum?: Record<string, unknown>; total?: number; list?: unknown[] }>({
          method: "POST",
          path: SETTLEMENT_MSKU_PATH,
          params: {
            offset: 0,
            length: 200,
            platformCodeS: [WALMART_PLATFORM_CODE],
            sids: store.store_id,
            startDate: w.startDate,
            endDate: w.endDate,
          },
          timeoutMs: 30000,
        });
        const data = (resp as unknown as { data?: { totalSum?: Record<string, unknown>; total?: number; list?: unknown[] } }).data;
        console.log(`  匹配记录总数(total): ${data?.total ?? "(无此字段)"}`);
        console.log(`  本页list条数: ${data?.list?.length ?? 0}`);
        console.log(`  totalSum完整原始JSON:`);
        console.log(JSON.stringify(data?.totalSum ?? {}, null, 2));
      } catch (err) {
        console.log(`  请求失败: ${err instanceof Error ? err.message : String(err)}`);
      }
      await sleep(400);
    }
  }
}

main().catch((err) => {
  console.error("探针4执行失败：", err);
  process.exit(1);
});
