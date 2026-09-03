/**
 * probeT1AndOrderPrice.ts —— 只读探测：T-1 可得性 + 订单级成交价数据盘点 + 广告配置快照时效
 *
 * 缘起（需求方 2026-08-21，运营日志一期设计收尾）：
 *   ① 需求方指出「不能依赖均价」——一天内多笔不同价会被平均掉，调价当天均价既不等于旧价也不等于新价，
 *      判定必然误报。⇒ 调价核对只能用**订单级成交价**。需求方称「数据库里面已经有数据了」，本探针**盘点求证**，不预设答案。
 *   ② 需求方称「广告没办法做到 T-1」。代码侧提出反证：我们要的是**配置快照**（keywordBid/dailyBudget/状态），
 *      不是**花费指标**（adSpend 有 day=14 归因延迟）。配置若是「当前值」则 T-0 可得。本探针实测判定。
 *      —— 这一条直接决定广告事件的日期该标业务日还是检出日（需求方原话：若能当天探出就不用写成检出日）。
 *   ③ 数据能否从现在的 T-2/T-3 提前到 T-1（美西日刚收，北京次日 15:00 后）。
 *
 * 时区事实（已核查代码，非注释）：
 *   · `usPacific.ts` 是全系统美西日界共享件（2026-08-18 立规），`laToday(-1)` = 美西昨天。
 *   · ⚠️ `syncWalmartListingPrice.ts:55-56` 的 captureDate 走 `Date.now()+8h` = **北京日**，与 FACT 的美西日**错位**。
 *     代码侧在两轮价格探针里用北京日 JOIN 美西日，已自认该错位（同向率 13.43% 可能被污染）。本探针不重复该错误。
 *
 * 只读约束：只 SELECT + 只读接口；不建表、不写 FACT/DIM/BIZ、不改任何现有文件与定时任务。
 *   每次接口响应写 raw_lingxing_api 留痕（RAW 留存＝铁律，不算写业务库）。
 * 限流：queryCampaignSpList 令牌桶容量=1，所有接口调用间隔 SLEEP_MS（默认 2500ms）。
 * 失败即如实打印 code/message，**绝不改参数去凑成功**（API_MAP §6-1）。
 * 无静默截断：任何分页上限触顶都会显式打印「已截断」。
 *
 * 用法：
 *   npx ts-node src/probeT1AndOrderPrice.ts
 *   npx ts-node src/probeT1AndOrderPrice.ts --store=<store_id> --advertiser=571910 --sleep=3000
 */
import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";
import { laToday, laDayBounds } from "./usPacific";

const P_KEYWORD_SP = "/basicOpen/multiplatform/ads/reportKeywordSpList";
const P_CAMPAIGN_SP = "/basicOpen/multiplatform/ads/queryCampaignSpList";
const P_SALESTAT = "/basicOpen/platformStatisticsV2/saleStat/pageList";
const P_ORDER = "/pb/mp/order/v2/list";
const PLATFORM_WALMART = "10008";
const TIMEOUT_MS = 60000;
const SALE_PAGE_SIZE = 200, SALE_MAX_PAGES = 10;
const ORDER_PAGE_SIZE = 200, ORDER_MAX_PAGES = 20;

function getArg(n: string, d: string): string {
  const p = `--${n}=`; const a = process.argv.find((x) => x.startsWith(p));
  return a ? a.slice(p.length) : d;
}
const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));
const num = (v: unknown): number => Number(v ?? 0);

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1", port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "", password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data", dateStrings: true,
  });
}
async function insertRaw(db: mysql.Connection, apiPath: string, params: unknown, resp: unknown, d: string): Promise<void> {
  try {
    const pj = JSON.stringify(params), rj = JSON.stringify(resp);
    const code = String((resp as { code?: unknown })?.code ?? "");
    await db.query(
      `INSERT INTO raw_lingxing_api (source_system, api_path, request_method, request_params_json, response_json,
         response_code, is_success, data_date, pulled_at, raw_hash, extra_json)
       VALUES ('lingxing', ?, 'POST', ?, ?, ?, ?, ?, NOW(), ?, JSON_OBJECT('probe','t1_and_order_price'))`,
      [apiPath, pj, rj, code, code === "0" ? 1 : 0, d,
       crypto.createHash("sha256").update(pj + rj).digest("hex")]);
  } catch (e) { console.warn(`  [RAW写入失败,忽略] ${e instanceof Error ? e.message : String(e)}`); }
}

async function main(): Promise<void> {
  const sleepMs = Number(getArg("sleep", "2500"));
  const db = await getDb();
  const client = new LingxingClient(loadConfig());
  console.log("=".repeat(92));
  console.log("T-1 可得性 + 订单级成交价盘点 + 广告配置快照时效（只读）");
  console.log("=".repeat(92));

  try {
    // ── 步骤0：样本店铺 ─────────────────────────────────────────────────────
    console.log("\n【步骤0】样本店铺");
    let storeId = getArg("store", "");
    let advertiserId = Number(getArg("advertiser", "0"));
    // 2026-08-21 修正：店铺↔广告主的**权威表是 dim_store_config**，不是 dim_store。
    //   依据=syncWalmartStores.ts:149 写入 dim_store_config；storeRegistry.ts:33 也从该表读。
    //   首版本探针查了 dim_store.advertiser_id（DATABASE_MAP 把它列为核心字段），实测**生产全空**，
    //   直接判成「无可用店铺」中止 —— 又一次「文档写了 ≠ 实测有值」（API_MAP 维护规矩第 2 条）。
    const [sr] = await db.query<mysql.RowDataPacket[]>(
      `SELECT store_id, store_name, advertiser_id, is_active FROM dim_store_config
        WHERE advertiser_id IS NOT NULL AND advertiser_id<>''
        ORDER BY store_name LIMIT 30`);
    console.log(`  dim_store_config 可用店铺（前30）：`);
    for (const r of sr as Array<Record<string, unknown>>) {
      console.log(`    ${String(r.store_id).padEnd(22)} advertiser=${String(r.advertiser_id).padEnd(10)} `
        + `active=${String(r.is_active)}  ${r.store_name}`);
    }
    if (!storeId || !advertiserId) {
      const pick = (sr as Array<Record<string, unknown>>).find((r) => String(r.store_name ?? "").includes("CN2601"))
        ?? (sr as Array<Record<string, unknown>>)[0];
      if (!pick) {
        // 探针设计修正：查不到就只喊"中止"等于零诊断信息。这里把两张候选表都倒出来，让这一趟不白跑。
        console.log("  ⚠️ dim_store_config 无带 advertiser_id 的店铺。倒出两张候选表全貌供判读：");
        for (const t of ["dim_store_config", "dim_store"]) {
          try {
            const [cols] = await db.query<mysql.RowDataPacket[]>(
              `SELECT COLUMN_NAME FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=? ORDER BY ORDINAL_POSITION`, [t]);
            console.log(`    ▸ ${t} 列：${(cols as Array<Record<string, unknown>>).map((c) => c.COLUMN_NAME).join(", ")}`);
            const [rws] = await db.query<mysql.RowDataPacket[]>(`SELECT * FROM \`${t}\` LIMIT 15`);
            for (const r of rws as Array<Record<string, unknown>>) console.log(`      ${JSON.stringify(r)}`);
          } catch (e) { console.log(`    ▸ ${t} 读取失败：${e instanceof Error ? e.message : String(e)}`); }
        }
        console.log("  ⇒ 探测中止（缺样本店铺）。以上两张表的实际内容已倒出，据此决定下一版探针取哪张表。");
        return;
      }
      storeId = storeId || String(pick.store_id);
      advertiserId = advertiserId || Number(pick.advertiser_id);
    }
    console.log(`  ⇒ 本次样本 store_id=${storeId}  advertiserId=${advertiserId}`);
    console.log(`  美西日参考：昨天=${laToday(-1)}  前天=${laToday(-2)}  大前天=${laToday(-3)}`);

    // ── 步骤1：数据库盘点——现有哪些表能给出「订单级成交价」───────────────────
    console.log("\n【步骤1】数据库盘点：现有哪些表同时含「订单标识」与「价格/金额」列");
    console.log("  （需求方称『数据库里面已经有数据了』，本步求证，不预设答案）");
    const [cand] = await db.query<mysql.RowDataPacket[]>(
      `SELECT TABLE_NAME,
              GROUP_CONCAT(CASE WHEN COLUMN_NAME REGEXP 'order_no|order_item|order_id|order_sn'
                                THEN COLUMN_NAME END ORDER BY ORDINAL_POSITION) order_cols,
              GROUP_CONCAT(CASE WHEN COLUMN_NAME REGEXP 'price|amount|unit_fee'
                                THEN COLUMN_NAME END ORDER BY ORDINAL_POSITION) price_cols
         FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        GROUP BY TABLE_NAME
       HAVING SUM(COLUMN_NAME REGEXP 'order_no|order_item|order_id|order_sn') > 0
          AND SUM(COLUMN_NAME REGEXP 'price|amount|unit_fee') > 0
        ORDER BY TABLE_NAME`);
    const cands = cand as Array<Record<string, unknown>>;
    console.log(`  命中 ${cands.length} 张表：`);
    for (const t of cands) {
      const tn = String(t.TABLE_NAME);
      let cnt = -1;
      try {
        const [c] = await db.query<mysql.RowDataPacket[]>(`SELECT COUNT(*) n FROM \`${tn}\``);
        cnt = Number((c as Array<Record<string, unknown>>)[0]?.n ?? -1);
      } catch { /* 忽略，打 -1 */ }
      console.log(`\n    ▸ ${tn}   行数=${cnt}`);
      console.log(`      订单类列：${t.order_cols}`);
      console.log(`      价格类列：${t.price_cols}`);
    }
    console.log(`\n  另：全库所有含 "price" 的列（看有没有遗漏的单价来源）：`);
    const [pc] = await db.query<mysql.RowDataPacket[]>(
      `SELECT TABLE_NAME, COLUMN_NAME, COLUMN_COMMENT FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=DATABASE() AND COLUMN_NAME LIKE '%price%' ORDER BY TABLE_NAME, ORDINAL_POSITION`);
    for (const r of pc as Array<Record<string, unknown>>) {
      console.log(`    ${String(r.TABLE_NAME).padEnd(34)} ${String(r.COLUMN_NAME).padEnd(26)} ${r.COLUMN_COMMENT}`);
    }
    console.log(`\n  已知事实（代码侧核对，供判读）：`);
    console.log(`    · raw_mp_order_discount 是订单级，但 syncMpOrderDiscount.ts 有 "if (disc === 0) continue"`);
    console.log(`      ⇒ **全价单一行都没存**，只有折扣行。下面用 SQL 实证这一点。`);
    const [dchk] = await db.query<mysql.RowDataPacket[]>(
      `SELECT COUNT(*) n_all, SUM(discount_amount = 0) n_zero_disc,
              MIN(purchase_date) d0, MAX(purchase_date) d1
         FROM raw_mp_order_discount`);
    const dc = (dchk as Array<Record<string, unknown>>)[0] ?? {};
    console.log(`    · 实证：raw_mp_order_discount 共 ${dc.n_all} 行，其中 discount_amount=0 的 ${dc.n_zero_disc} 行`
      + `（若为 0 则证实全价单确实没入库）；覆盖 ${dc.d0} ~ ${dc.d1}`);

    // ── 步骤2：广告配置是「当前值」还是「区间值」──────────────────────────────
    console.log("\n【步骤2】广告配置快照时效：keywordBid / dailyBudget 是当前值还是区间值？");
    console.log("  方法：同一 advertiser，用两个**不同的历史区间**各查一次，比对同一实体上的值是否相同。");
    console.log("  判读：完全相同 ⇒ 是**当前值**（配置快照 T-0 可得，广告事件可用业务日）；");
    console.log("        有差异   ⇒ 是**区间值**（只能按区间取，事件日期需另定）。");
    const recentEnd = laToday(-1), recentStart = laToday(-7);
    const oldEnd = laToday(-21), oldStart = laToday(-27);
    const kwBase = { advertiserIds: [advertiserId], day: 14, pageNum: 1, pageSize: 200, paging: true,
      campaignType: ["sponsoredProducts-manual", "sponsoredProducts-auto"] };

    async function kwMap(tag: string, s: string, e: string): Promise<Map<string, string>> {
      const params = { ...kwBase, startDate: s, endDate: e };
      const resp = await client.request<unknown>({ method: "POST", path: P_KEYWORD_SP, params, timeoutMs: TIMEOUT_MS });
      await insertRaw(db, P_KEYWORD_SP, params, resp, e);
      await sleep(sleepMs);
      const code = String((resp as { code?: unknown })?.code ?? "");
      const d = (resp as { data?: { list?: unknown; total?: unknown } })?.data;
      const rows: Array<Record<string, unknown>> = Array.isArray(d?.list) ? (d?.list as Array<Record<string, unknown>>) : [];
      console.log(`    ${tag} ${s}~${e}  code=${code}  total=${d?.total ?? "?"}  本页行数=${rows.length}`);
      if (code !== "0") console.log(`      ✗ 原始响应前 400 字符：${JSON.stringify(resp).slice(0, 400)}`);
      const m = new Map<string, string>();
      for (const r of rows) { const k = String(r.keywordId ?? ""); if (k) m.set(k, String(r.keywordBid ?? "")); }
      return m;
    }
    const mRecent = await kwMap("区间A(近)", recentStart, recentEnd);
    const mOld = await kwMap("区间B(远)", oldStart, oldEnd);
    const inter = [...mRecent.keys()].filter((k) => mOld.has(k));
    console.log(`    两区间交集 keywordId = ${inter.length} 个`);
    if (inter.length === 0) {
      console.log(`    ⚠️ 交集为 0，无法判定。先排除样本问题（该店远区间是否有投放），不要判成"接口不支持"。`);
    } else {
      const diff = inter.filter((k) => mRecent.get(k) !== mOld.get(k));
      console.log(`    其中 keywordBid 不同的 = ${diff.length} 个  (${((diff.length / inter.length) * 100).toFixed(2)}%)`);
      for (const k of diff.slice(0, 10)) console.log(`      keywordId=${k}  近=${mRecent.get(k)}  远=${mOld.get(k)}`);
      console.log(`    ⇒ 判定：${diff.length === 0 ? "**全部相同 ⇒ keywordBid 是当前值，配置快照 T-0 可得**"
        : "**存在差异 ⇒ keywordBid 随区间变化，属区间值**"}`);
    }
    // 同样测 dailyBudget
    const campBase = { advertiserIds: [advertiserId], day: 14, operationSourceType: "gateway",
      pageNum: 1, pageSize: 200, paging: true, campaignType: ["sponsoredProducts-manual", "sponsoredProducts-auto"] };
    async function campMap(tag: string, s: string, e: string): Promise<Map<string, string>> {
      const params = { ...campBase, startDate: s, endDate: e };
      const resp = await client.request<unknown>({ method: "POST", path: P_CAMPAIGN_SP, params, timeoutMs: TIMEOUT_MS });
      await insertRaw(db, P_CAMPAIGN_SP, params, resp, e);
      await sleep(sleepMs);
      const code = String((resp as { code?: unknown })?.code ?? "");
      const d = (resp as { data?: { list?: unknown; total?: unknown } })?.data;
      const rows: Array<Record<string, unknown>> = Array.isArray(d?.list) ? (d?.list as Array<Record<string, unknown>>) : [];
      console.log(`    ${tag} ${s}~${e}  code=${code}  total=${d?.total ?? "?"}  本页行数=${rows.length}`);
      if (code !== "0") console.log(`      ✗ 原始响应前 400 字符：${JSON.stringify(resp).slice(0, 400)}`);
      const m = new Map<string, string>();
      for (const r of rows) {
        const k = String(r.campaignId ?? ""); if (!k) continue;
        const bs = r.biddingStrategy as { strategy?: unknown } | undefined;
        m.set(k, `${String(r.dailyBudget ?? "")}|${String(r.campaignStatus ?? "")}|${String(bs?.strategy ?? "")}`);
      }
      return m;
    }
    console.log(`\n    —— 同法测 dailyBudget / campaignStatus / biddingStrategy ——`);
    const cRecent = await campMap("区间A(近)", recentStart, recentEnd);
    const cOld = await campMap("区间B(远)", oldStart, oldEnd);
    const cInter = [...cRecent.keys()].filter((k) => cOld.has(k));
    console.log(`    两区间交集 campaignId = ${cInter.length} 个`);
    if (cInter.length > 0) {
      const cDiff = cInter.filter((k) => cRecent.get(k) !== cOld.get(k));
      console.log(`    其中 预算|状态|策略 不同的 = ${cDiff.length} 个  (${((cDiff.length / cInter.length) * 100).toFixed(2)}%)`);
      for (const k of cDiff.slice(0, 10)) console.log(`      campaignId=${k}  近=${cRecent.get(k)}  远=${cOld.get(k)}`);
      console.log(`    ⇒ 判定：${cDiff.length === 0 ? "**全部相同 ⇒ 活动配置是当前值，T-0 可得**" : "**存在差异 ⇒ 属区间值**"}`);
    }

    // ── 步骤3：saleStat 各日可得性 ───────────────────────────────────────────
    console.log("\n【步骤3】saleStat 各美西日的可得性与完整度（决定销售数据能提前到哪天）");
    console.log(`  ${"美西日".padEnd(12)}${"接口行数".padStart(10)}${"销量合计".padStart(10)}${"销售额合计".padStart(14)}${"FACT已有销量".padStart(14)}${"FACT已有销售额".padStart(16)}`);
    for (const off of [-1, -2, -3, -4]) {
      const d = laToday(off);
      let rows1 = 0, qty = 0, rows3 = 0, amt = 0, truncated = false;
      for (const [rt, isQty] of [["1", true], ["3", false]] as Array<[string, boolean]>) {
        for (let page = 1; page <= SALE_MAX_PAGES; page++) {
          const params = { start_date: d, end_date: d, result_type: rt, date_unit: "4", data_type: "1",
            page, length: SALE_PAGE_SIZE, sids: [storeId] };
          const resp = await client.request<unknown>({ method: "POST", path: P_SALESTAT, params, timeoutMs: TIMEOUT_MS });
          await insertRaw(db, P_SALESTAT, params, resp, d);
          await sleep(sleepMs);
          const dd = (resp as { data?: unknown })?.data;
          const list: Array<Record<string, unknown>> = Array.isArray(dd) ? (dd as Array<Record<string, unknown>>)
            : Array.isArray((dd as { list?: unknown })?.list) ? ((dd as { list: unknown }).list as Array<Record<string, unknown>>) : [];
          for (const it of list) {
            const v = num(it.value ?? it.total ?? it.num ?? it.amount);
            if (isQty) { rows1++; qty += v; } else { rows3++; amt += v; }
          }
          if (list.length < SALE_PAGE_SIZE) break;
          if (page === SALE_MAX_PAGES) truncated = true;
        }
      }
      const [f] = await db.query<mysql.RowDataPacket[]>(
        `SELECT COALESCE(SUM(sales_qty),0) q, COALESCE(SUM(sales_amount),0) a FROM fact_sales_daily
          WHERE platform='walmart' AND stat_date=? AND store_id=?`, [d, storeId]);
      const fr = (f as Array<Record<string, unknown>>)[0] ?? {};
      console.log(`  ${d.padEnd(12)}${String(rows1 + rows3).padStart(10)}${qty.toFixed(0).padStart(10)}`
        + `${amt.toFixed(2).padStart(14)}${num(fr.q).toFixed(0).padStart(14)}${num(fr.a).toFixed(2).padStart(16)}`
        + (truncated ? "  ⚠️已截断(触顶10页)" : ""));
    }
    console.log("  判读：接口行数/合计在 T-1 与 T-2/T-3 同量级 ⇒ T-1 可用；T-1 明显偏小 ⇒ 当天仍在滚动补数。");
    console.log("  注意：saleStat 各 result_type 的返回结构若与本探针假设不符，上面合计会全为 0——");
    console.log("        那说明**取值字段名猜错了**，属探针缺陷，不得据此判定「T-1 无数据」。首行原始 JSON 见下。");

    // ── 步骤4：库存最新快照 ─────────────────────────────────────────────────
    console.log("\n【步骤4】库存快照最新日（fact_inventory_daily）");
    const [inv] = await db.query<mysql.RowDataPacket[]>(
      `SELECT DATE_FORMAT(MAX(snapshot_date),'%Y-%m-%d') dmax FROM fact_inventory_daily WHERE platform='walmart'`);
    const dmax = String((inv as Array<Record<string, unknown>>)[0]?.dmax ?? "");
    console.log(`  最新 snapshot_date = ${dmax}（美西今天=${laToday(0)}，昨天=${laToday(-1)}）`);
    const [invd] = await db.query<mysql.RowDataPacket[]>(
      `SELECT DATE_FORMAT(snapshot_date,'%Y-%m-%d') d, COUNT(*) n FROM fact_inventory_daily
        WHERE platform='walmart' GROUP BY d ORDER BY d DESC LIMIT 6`);
    for (const r of invd as Array<Record<string, unknown>>) console.log(`    ${r.d}  ${r.n} 行`);

    // ── 步骤5：订单接口全量行体量 ────────────────────────────────────────────
    console.log("\n【步骤5】订单接口全量行体量（决定新表要不要保留期）");
    const targetDay = laToday(-2);
    const { startTs, endTs } = laDayBounds(targetDay);
    console.log(`  样本：美西日 ${targetDay}（unix ${startTs}~${endTs}），全店铺，date_type=global_purchase_time`);
    let orders = 0, itemLines = 0, discLines = 0, fullLines = 0, oTrunc = false;
    const priceSample: string[] = [];
    for (let page = 0; page < ORDER_MAX_PAGES; page++) {
      const params = { offset: page * ORDER_PAGE_SIZE, length: ORDER_PAGE_SIZE,
        date_type: "global_purchase_time", start_time: startTs, end_time: endTs, platform_code: [PLATFORM_WALMART] };
      const resp = await client.request<unknown>({ method: "POST", path: P_ORDER, params, timeoutMs: TIMEOUT_MS });
      await insertRaw(db, P_ORDER, params, resp, targetDay);
      await sleep(sleepMs);
      const code = String((resp as { code?: unknown })?.code ?? "");
      if (code !== "0") { console.log(`  ✗ code=${code} 原始响应前 400 字符：${JSON.stringify(resp).slice(0, 400)}`); break; }
      const dd = (resp as { data?: unknown })?.data;
      const list: Array<Record<string, unknown>> = Array.isArray(dd) ? (dd as Array<Record<string, unknown>>)
        : Array.isArray((dd as { list?: unknown })?.list) ? ((dd as { list: unknown }).list as Array<Record<string, unknown>>) : [];
      orders += list.length;
      for (const o of list) {
        const items = (o as { item_info?: Array<Record<string, unknown>> }).item_info ?? [];
        for (const it of items) {
          itemLines++;
          if (num(it.discount_amount) === 0) fullLines++; else discLines++;
          if (priceSample.length < 8) {
            priceSample.push(`      订单${String(o.reference_no ?? o.global_order_no ?? "")} msku=${String(it.msku ?? "")}`
              + ` 件数=${num(it.quantity)} 商品金额=${num(it.item_price_amount)} 折扣=${num(it.discount_amount)}`);
          }
        }
      }
      if (list.length < ORDER_PAGE_SIZE) break;
      if (page === ORDER_MAX_PAGES - 1) oTrunc = true;
    }
    console.log(`  订单数=${orders}  商品行数=${itemLines}  其中折扣行=${discLines}  全价行=${fullLines}` + (oTrunc ? "  ⚠️已截断(触顶20页)" : ""));
    console.log(`  ⇒ 31 天体量估算：订单 ≈ ${orders * 31}，商品行 ≈ ${itemLines * 31}（按本日线性外推，仅供量级参考）`);
    console.log(`  ⇒ 现有 raw_mp_order_discount 只存了其中 ${discLines} 行/日，**丢弃了 ${fullLines} 行/日全价单**。`);
    console.log(`  订单行样例（证明 item_price_amount 是订单级成交金额）：`);
    for (const s of priceSample) console.log(s);

    // ── 步骤6：结论 ────────────────────────────────────────────────────────
    console.log("\n【步骤6】结论（只陈述实测事实，不替需求方选方案）");
    console.log("  ① 订单级成交价：看步骤1 的表盘点 + 步骤5 的样例，判断是否需要新增一张全量订单行 RAW。");
    console.log("  ② 广告配置时效：看步骤2 的两个「判定」行 —— 决定广告事件用业务日还是检出日。");
    console.log("  ③ 销售 T-1：看步骤3 各日是否同量级 —— 决定数据能提前到哪天。");
    console.log("  ④ 库存：看步骤4 最新 snapshot_date 与美西今天/昨天的差距。");
    console.log("  ⑤ 体量：看步骤5 的 31 天外推，决定新表是否需要保留期。");
  } catch (e) {
    console.error(`✗ 探测异常: ${e instanceof Error ? e.message : String(e)}`);
    console.error("  按规矩：报错的查询不得用于支撑任何结论（API_MAP §6-1）。");
  } finally {
    await db.end().catch(() => undefined);
  }
}

main().catch((e: unknown) => { console.error("探测脚本异常:", e); process.exit(1); });
