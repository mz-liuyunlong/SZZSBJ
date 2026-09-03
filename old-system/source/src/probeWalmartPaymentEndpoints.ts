/**
 * src/probeWalmartPaymentEndpoints.ts
 *
 * 单品现金利润模块 · 探针3 —— 探测"Walmart回款(Payment)"真实接口路径（只读，零写库，零改动生产）。
 *
 * 背景：
 *   本地 docs/lingxing/_sidebar.md（领星官方文档站目录镜像）里确实存在这两条目录项：
 *     查询可用报告列表 - Walmart Payment  →  文档页 slug: docs/MultiPlatform/V2/WalmartPaymentQueryReport
 *     查询报告详情 - Walmart Payment      →  文档页 slug: docs/MultiPlatform/V2/WalmartPaymentQueryPage
 *   这两条目录项的存在是真实的（来自领星官方索引，不是编的），大概率对应 Walmart Seller Center
 *   → Payments → Statements 里的"Payments Report"——也就是真正的回款/到账数据源。
 *
 *   但是：本地仓库里没有这两个页面的实际内容缓存（同目录下唯一有真实内容缓存的是
 *   walmart-reportAdItemSpList_17.md，跟回款无关），所以只有"文档页slug"，没有"真实API Path"。
 *   已核实同目录下其它条目的教训：文档页 slug 跟真实 API Path 完全不是同一套命名规则——
 *   比如"查询平台仓发货单列表"(slug: QueryShippingListPage) 真实路径是
 *   /erp/sc/routing/storage/shipment/getInboundShipmentList；"查询WFS货件列表"(slug: QueryWFSCargoPage)
 *   真实路径是 /cepf/warehouse/api/openApi/queryWFSCargoPage。两个 slug 长得像，真实路径前缀却完全不同。
 *   所以本探针不是"验证一个已知真实路径"，而是"在多个前缀家族里广撒网猜测"，命中率没有保证，
 *   如果这一轮全部落空，说明这条路径确实需要你从 apidoc.lingxing.com 上把这两页文档导出来才能继续。
 *
 * 探测方式：
 *   对下面 CANDIDATE_PATHS 里的每一个候选路径，依次用几组常见最小参数（空参数 / offset+length /
 *   加 startDate+endDate / 加 sids 店铺范围）发起只读请求，把每一次的 HTTP 状态、领星业务code、
 *   报错信息、返回数据摘要原样打印出来。领星接口对"路径错了"和"路径对但参数错了"通常报错信息不同
 *   （前者常是网关层 404/路由未找到，后者是业务层"缺少必填参数xxx"之类），可以用报错信息反推。
 *
 * 安全边界：
 *   - 只读：LingxingClient.assertReadOnlyPath 兜底拦截任何写类路径；下面所有候选路径都是"query/list/detail"
 *     语义，不含 add/update/delete 等写动词，理论上都能通过校验。
 *   - 零数据库读写：本探针完全不碰生产 DB，纯粹只调 LingXing API。
 *   - 不落 RAW 表、不建表、不改任何现有脚本。
 *
 * 运行（生产机，由部署工程师执行，需要真实 .env 网络/凭证）：
 *   npx ts-node src/probeWalmartPaymentEndpoints.ts
 *   npx ts-node src/probeWalmartPaymentEndpoints.ts --sids=110453560302608900   # 如果知道真实店铺id可以传
 *
 * 用法：把完整输出贴回来。如果找到了返回非报错/非404的候选路径，把命中的请求体和返回样例也一并贴出来，
 *      用于确认真实字段结构；如果全部落空，就说明必须去 apidoc.lingxing.com 导出这两页文档。
 *      在此之前不建表、不写正式同步脚本。
 */

import "dotenv/config";
import { loadConfig } from "./config";
import { LingxingClient, LingxingRequestError } from "./lingxingClient";

function getArg(name: string, fallback: string): string {
  const prefix = `--${name}=`;
  const arg = process.argv.find((a) => a.startsWith(prefix));
  return arg ? arg.slice(prefix.length) : fallback;
}

function shanghaiDate(offsetDays = 0): string {
  const d = new Date(Date.now() + 8 * 3600 * 1000);
  d.setUTCDate(d.getUTCDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

const sidsArg = getArg("sids", "");
const endDate = shanghaiDate(-2);
const startDate = shanghaiDate(-32);

function paramVariants(): Record<string, unknown>[] {
  const base: Record<string, unknown>[] = [
    {},
    { offset: 0, length: 20 },
    { offset: 0, length: 20, startDate, endDate },
    { pageNo: 1, pageSize: 20 },
    { pageNo: 1, pageSize: 20, startDate, endDate },
  ];
  if (sidsArg) {
    base.push({ offset: 0, length: 20, startDate, endDate, sids: sidsArg });
    base.push({ offset: 0, length: 20, startDate, endDate, sid: sidsArg });
  }
  return base;
}

// 候选路径：全部未经证实，按已知同目录兄弟接口的几种不同前缀家族广撒网列出。
// 命名参考：WalmartPaymentQueryReport（查询可用报告列表）/ WalmartPaymentQueryPage（查询报告详情）
const CANDIDATE_PATHS: string[] = [
  // /basicOpen/multiplatform 家族（结算利润、广告报表都在这个前缀下）
  "/basicOpen/multiplatform/walmartPayment/queryReport",
  "/basicOpen/multiplatform/walmartPayment/queryPage",
  "/basicOpen/multiplatform/walmart/payment/queryReport",
  "/basicOpen/multiplatform/walmart/payment/queryPage",
  "/basicOpen/multiplatform/walmart/paymentReport/query",
  "/basicOpen/multiplatform/walmart/paymentQueryReport",
  "/basicOpen/multiplatform/walmart/paymentQueryPage",
  "/basicOpen/multiplatform/payment/walmart/queryReport",
  "/basicOpen/multiplatform/payment/walmart/queryPage",
  // /basicOpen/finance 家族（老式利润报表在这个前缀下，如 OrderProfitListMSKU）
  "/basicOpen/finance/walmart/paymentQueryReport",
  "/basicOpen/finance/walmart/paymentQueryPage",
  "/basicOpen/finance/walmartPayment/queryReport",
  "/basicOpen/finance/walmartPayment/queryPage",
  // /erp/sc/routing 家族（发货单等本地/平台仓接口在这个前缀下）
  "/erp/sc/routing/finance/walmart/paymentQueryReport",
  "/erp/sc/routing/finance/walmart/paymentQueryPage",
  "/erp/sc/routing/multiPlatform/walmartPaymentQueryReport",
  "/erp/sc/routing/multiPlatform/walmartPaymentQueryPage",
];

interface ProbeResult {
  path: string;
  paramsLabel: string;
  outcome: "success" | "business_error" | "network_error";
  status?: number;
  message?: string;
  dataPreview?: string;
}

async function tryPath(client: LingxingClient, path: string): Promise<ProbeResult[]> {
  const results: ProbeResult[] = [];
  for (const params of paramVariants()) {
    const paramsLabel = JSON.stringify(params);
    try {
      const resp = await client.request<unknown>({
        method: "POST",
        path,
        params,
        timeoutMs: 15000,
      });
      results.push({
        path,
        paramsLabel,
        outcome: "success",
        dataPreview: JSON.stringify(resp).slice(0, 800),
      });
      // 一旦某个参数变体成功，这个路径就不用再试其它变体了
      return results;
    } catch (err) {
      if (err instanceof LingxingRequestError) {
        results.push({
          path,
          paramsLabel,
          outcome: "business_error",
          status: err.status,
          message: err.message,
        });
      } else {
        results.push({
          path,
          paramsLabel,
          outcome: "network_error",
          message: err instanceof Error ? err.message : String(err),
        });
      }
    }
    await sleep(250);
  }
  return results;
}

async function main() {
  console.log(`探针3启动 | 候选路径数=${CANDIDATE_PATHS.length} | 日期窗口(仅部分变体会用到) ${startDate}~${endDate} | sids=${sidsArg || "(未提供)"}`);

  const cfg = loadConfig();
  const client = new LingxingClient(cfg);

  const hits: ProbeResult[] = [];

  for (const path of CANDIDATE_PATHS) {
    console.log(`\n--- 尝试路径: ${path} ---`);
    const results = await tryPath(client, path);
    for (const r of results) {
      if (r.outcome === "success") {
        console.log(`  [命中!] 参数=${r.paramsLabel} → 返回: ${r.dataPreview}`);
        hits.push(r);
      } else if (r.outcome === "business_error") {
        console.log(`  [业务报错] 参数=${r.paramsLabel} → status=${r.status} message=${r.message}`);
      } else {
        console.log(`  [网络/其它报错] 参数=${r.paramsLabel} → ${r.message}`);
      }
    }
    await sleep(300);
  }

  console.log(`\n=== 汇总 ===`);
  console.log(`候选路径总数：${CANDIDATE_PATHS.length}`);
  console.log(`命中（成功拿到返回）的路径数：${hits.length}`);
  if (hits.length > 0) {
    console.log("命中详情：");
    for (const h of hits) {
      console.log(`  ${h.path} | 参数=${h.paramsLabel}`);
    }
    console.log("\n把上面命中路径对应的完整返回内容贴回来，用于确认真实字段结构。");
  } else {
    console.log(
      "本轮候选全部落空（要么路由404，要么业务报错但报错信息里看不出这是回款相关接口）。" +
        "建议直接去 apidoc.lingxing.com 找到「查询可用报告列表 - Walmart Payment」" +
        "和「查询报告详情 - Walmart Payment」这两页文档，导出后按之前的方式发过来，" +
        "比继续扩大候选列表猜测更可靠。",
    );
  }
}

main().catch((err) => {
  console.error("探针3执行失败：", err);
  process.exit(1);
});
