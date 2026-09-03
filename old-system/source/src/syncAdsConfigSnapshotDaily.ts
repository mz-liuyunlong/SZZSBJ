/**
 * syncAdsConfigSnapshotDaily.ts —— 广告配置日快照同步（运营日志一期·第二单）
 *
 * 它是什么：每天把「广告活动 / 广告组 / 关键词」的**当前配置**拍一张快照存下来。
 * 它不是什么：**不产生任何运营日志事件**。差分与事件生成在第三单，本脚本纯取数。
 *
 * 为什么快照日 = 美西当日（而不是 T-1 或 T-2）：
 *   2026-08-21 探针 probeT1AndOrderPrice 实测——同一 advertiser 用**相隔三周的两个区间**各查一次：
 *     · keywordBid：交集 79 个 keywordId，差异 **0** 个
 *     · dailyBudget|campaignStatus|biddingStrategy：交集 123 个 campaignId，差异 **0** 个
 *     · 且两区间 data.total 完全相同（关键词 8613/8613、活动 920/920）
 *   ⇒ 接口返回的是**全部实体的当前配置**，根本不按区间过滤。配置是「当前值」不是「区间值」，
 *     故每天拉一次即得当下状态，快照日就是业务日，广告事件可用业务日标注。
 *   （需要区别对待的是**花费指标** adSpend——那个有 day=14 归因延迟，但本脚本不取花费。）
 *
 * 接口与参数：**逐个抄自已实测通过的探针，不统一、不推断**（API_MAP §6-5：路径未经 apidoc 正文确认者，
 *   结论只能写「路径未证实」，不得写「接口不可用」）。
 *   · campaign：queryCampaignSpList        —— 带 operationSourceType='gateway'（probeAdsBidBudgetStrategy 实测）
 *   · group   ：SP=queryGroupSpList（实测 1071/392 组）/ SB=reportAdGroupSbList（实测 code=0,total=0）
 *               / SV=queryAdGroupSvList（**实测报「参数有误」，路径未证实**——照做进去，失败如实记状态表）
 *   · keyword ：SP=reportKeywordSpList / SB=reportKeywordSbList / SV=reportKeywordSvList
 *               —— **不带 operationSourceType**（probeSpKeywordStatus 与 probeT1AndOrderPrice 均以此形态实测通过）
 *
 * 字段映射的防御：结构化列一律「宽容读取 + 兜底空值」，且**每行都原样存 row_json**。
 *   即使某个列名与接口实际不符（探针只核对过重点字段，非全字段），数据也不会丢，可从 row_json 事后补列。
 *
 * 完整性（本脚本最重要的产出之一）：每个「日×店×实体×广告类型」组合写一行 fact_ads_snapshot_status，
 *   记录 api_code / api_total / fetched_rows / pages / hit_page_cap / is_complete。
 *   **第三单的差分脚本必须先查这张表：is_complete=0 的组合当天一律不产生「关闭/删除」类事件。**
 *   否则一次限流或分页失败会被差分读成"运营把几百个关键词全关了"。
 *   （同源教训 API_MAP §6-2：total=0 不等于接口不可用，必须先排除样本问题。）
 *
 * 写入范围（严格限定）：4 张新表 + raw_lingxing_api 留痕 + sync_task_log 收尾。
 *   **不触碰任何既有 FACT/DIM/BIZ 表、不改任何现有文件、不动任何定时任务。**
 *   本脚本不自带 cron（挂 cron 需求方已口头批准，但仍由部署单显式添加）。
 *   **不含任何清理/DELETE 逻辑**——7 天保留策略跑满一周看真实体量后单独发单实现。
 *
 * 用法：
 *   npx ts-node src/syncAdsConfigSnapshotDaily.ts                       # dry-run（默认，零写入）
 *   npx ts-node src/syncAdsConfigSnapshotDaily.ts --confirm-write
 *   npx ts-node src/syncAdsConfigSnapshotDaily.ts --store=110687423514268160 --confirm-write
 *   npx ts-node src/syncAdsConfigSnapshotDaily.ts --only=campaign --confirm-write
 *   npx ts-node src/syncAdsConfigSnapshotDaily.ts --sleep-query=3000 --sleep-report=1500
 *   npx ts-node src/syncAdsConfigSnapshotDaily.ts --confirm-write --if-incomplete   # 条件补拍：当日快照已完整则直接退出（哨兵自愈，2026-08-24）
 */
import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";
import { loadStores } from "./storeRegistry";
import { laToday } from "./usPacific";

const BASE = "/basicOpen/multiplatform/ads/";
const TASK_NAME = "ads_config_snapshot_daily";
const PAGE_SIZE = 200;          // 200 是唯一被实测验证过的页长，不擅自加大
const MAX_PAGES = 80;           // 关键词单店实测 total=8613 → 43 页，留足余量；触顶会显式标 hit_page_cap
const TIMEOUT_MS = 60000;
const ATTR_DAY = 14;

type CT = "sp" | "sba" | "video";
const CT_LIST: CT[] = ["sp", "sba", "video"];
const CT_PARAM: Record<CT, string[]> = {
  sp: ["sponsoredProducts-manual", "sponsoredProducts-auto"],
  sba: ["sba"],
  video: ["video"],
};
type Entity = "campaign" | "group" | "keyword";
const ENTITY_LIST: Entity[] = ["campaign", "group", "keyword"];

/** 路径表：**每格都标注实测状态**，勿凭印象改 */
const PATHS: Record<Entity, Record<CT, string>> = {
  // 同一个接口能返回 SP 与 SV（实测 CN2601 SP=918 / video=13）；SB 返回 total=0＝公司未投放
  campaign: { sp: BASE + "queryCampaignSpList", sba: BASE + "queryCampaignSpList", video: BASE + "queryCampaignSpList" },
  // SP 实测可用；SB 实测 code=0/total=0；SV 实测「参数有误」——路径未证实，如实记录不掩盖
  group: { sp: BASE + "queryGroupSpList", sba: BASE + "reportAdGroupSbList", video: BASE + "queryAdGroupSvList" },
  // 三个路径均实测调通（SB/SV 的 total=0 属公司未投放）
  keyword: { sp: BASE + "reportKeywordSpList", sba: BASE + "reportKeywordSbList", video: BASE + "reportKeywordSvList" },
};
/** campaign/group 走 query 系需带 gateway；keyword 走 report 系实测**不带**也通，照实测形态发 */
const WITH_GATEWAY: Record<Entity, boolean> = { campaign: true, group: true, keyword: false };
/** query 系令牌桶容量=1（文档标注），report 系无此标注，故分开限速 */
const IS_QUERY: Record<Entity, boolean> = { campaign: true, group: true, keyword: false };

function getArg(name: string, dflt = ""): string {
  const p = `--${name}=`;
  const a = process.argv.find((x) => x.startsWith(p));
  return a ? a.slice(p.length) : dflt;
}
const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));
const str = (v: unknown): string => (v === null || v === undefined ? "" : String(v));
function numOrNull(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(String(v).replace(/[^0-9.eE+-]/g, ""));
  return Number.isFinite(n) ? n : null;
}
/** 接口日期串 → DATE/DATETIME 或 null（空串一律 null，绝不写 '0000-00-00'） */
function dtOrNull(v: unknown): string | null {
  const s = str(v).trim();
  if (!s || s.startsWith("0000")) return null;
  return s;
}

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
  });
}

async function insertRaw(
  db: mysql.Connection, apiPath: string, params: unknown, resp: unknown, dataDate: string,
): Promise<void> {
  try {
    const pj = JSON.stringify(params), rj = JSON.stringify(resp);
    const code = str((resp as { code?: unknown })?.code);
    await db.query(
      `INSERT INTO raw_lingxing_api
         (source_system, api_path, request_method, request_params_json, response_json,
          response_code, is_success, data_date, pulled_at, raw_hash, extra_json)
       VALUES ('lingxing', ?, 'POST', ?, ?, ?, ?, ?, NOW(), ?, JSON_OBJECT('job','ads_config_snapshot'))`,
      [apiPath, pj, rj, code, code === "0" ? 1 : 0, dataDate,
       crypto.createHash("sha256").update(pj + rj).digest("hex")]);
  } catch (e) {
    console.warn(`    [RAW写入失败,忽略] ${e instanceof Error ? e.message : String(e)}`);
  }
}

type Row = Record<string, unknown>;
interface PullResult {
  code: string; message: string; total: number | null;
  rows: Row[]; pages: number; hitCap: boolean;
}

/** 分页拉取一个（实体 × 广告类型）组合。失败不重试、不换参数、不换路径——如实返回。 */
async function pull(
  db: mysql.Connection, client: LingxingClient,
  path: string, baseParams: Record<string, unknown>, dataDate: string, sleepMs: number,
): Promise<PullResult> {
  const rows: Row[] = [];
  let code = "", message = "", total: number | null = null, pages = 0, hitCap = false;
  for (let pageNum = 1; pageNum <= MAX_PAGES; pageNum++) {
    const params = { ...baseParams, pageNum, pageSize: PAGE_SIZE, paging: true };
    const resp = await client.request<unknown>({ method: "POST", path, params, timeoutMs: TIMEOUT_MS });
    await insertRaw(db, path, params, resp, dataDate);
    pages = pageNum;
    code = str((resp as { code?: unknown })?.code);
    message = str((resp as { message?: unknown })?.message);
    const d = (resp as { data?: { list?: unknown; total?: unknown } })?.data;
    if (pageNum === 1) {
      const t = d?.total;
      total = t === null || t === undefined ? null : Number(t);
      if (total !== null && !Number.isFinite(total)) total = null;
    }
    if (code !== "0") break;                       // 失败立即停，保留 code/message 原文
    const list: Row[] = Array.isArray(d?.list) ? (d?.list as Row[]) : [];
    rows.push(...list);
    await sleep(sleepMs);
    if (list.length < PAGE_SIZE) break;
    if (pageNum === MAX_PAGES) hitCap = true;      // 触顶＝必然不完整，显式标记，绝不静默截断
  }
  return { code, message, total, rows, pages, hitCap };
}

async function main(): Promise<void> {
  const confirmWrite = process.argv.includes("--confirm-write");
  const storeFilter = getArg("store");
  const onlyEntity = getArg("only") as Entity | "";
  const onlyCt = getArg("ct") as CT | "";
  const sleepQuery = Number(getArg("sleep-query", "2500"));
  const sleepReport = Number(getArg("sleep-report", "1200"));
  const snapshotDate = getArg("date") || laToday(0);
  // 接口仍要求日期区间；配置是当前值、与区间无关（实测两区间 total 相同），
  // 故取一个已被实测验证过的短窗，减少服务端负担。endDate 用 laToday(-1)（探针即以此形态跑通）。
  const startDate = laToday(-7), endDate = laToday(-1);

  console.log("=".repeat(88));
  console.log("广告配置日快照同步（campaign / group / keyword）");
  console.log(`  快照日=${snapshotDate}（美西日界）  接口窗=${startDate}~${endDate}  write=${confirmWrite}`);
  console.log(`  限速 query系=${sleepQuery}ms  report系=${sleepReport}ms  pageSize=${PAGE_SIZE}  maxPages=${MAX_PAGES}`);
  if (storeFilter) console.log(`  仅店铺 ${storeFilter}`);
  if (onlyEntity) console.log(`  仅实体 ${onlyEntity}`);
  if (onlyCt) console.log(`  仅广告类型 ${onlyCt}`);
  console.log("=".repeat(88));

  const allStores = await loadStores();
  const stores = allStores.filter((s) => s.advertiserId && (!storeFilter || s.storeId === storeFilter));
  console.log(`\n店铺 ${stores.length} 个（已过滤无 advertiserId 的）`);
  if (stores.length === 0) { console.log("⚠️ 无可用店铺，退出。"); return; }

  const db = await getDb();
  const client = new LingxingClient(loadConfig());
  let upCamp = 0, upGroup = 0, upKw = 0, statusRows = 0, comboFail = 0, comboIncomplete = 0;

  try {
    // ── 条件补拍闸门（2026-08-24 哨兵机制·自愈半边）────────────────────────────
    //   --if-incomplete：当日快照已完整 ⇒ 直接退出，零接口调用零写入；不完整 ⇒ 正常补拍。
    //   判据只认 fact_ads_snapshot_status.is_complete：每店应有 8 个完整组合（9 组合 − group/video 结构性参数错）。
    //   ⚠️ 不得改用 sync_task_log.status 当判据——SV group「参数有误」使本任务天天记 failed，无区分度（2026-08-24 实测）。
    //   带 --store/--only/--ct 过滤时本闸门不生效（判据按全店口径设计，过滤场景下无意义）。
    if (process.argv.includes("--if-incomplete") && !storeFilter && !onlyEntity && !onlyCt) {
      const [chk] = await db.query<mysql.RowDataPacket[]>(
        `SELECT COUNT(*) AS n FROM fact_ads_snapshot_status WHERE snapshot_date = ? AND is_complete = 1`,
        [snapshotDate]);
      const okCombos = Number((chk[0] as { n?: unknown } | undefined)?.n ?? 0);
      const needCombos = stores.length * 8;
      console.log(`\n[--if-incomplete] 当日(${snapshotDate})完整组合=${okCombos} / 需=${needCombos}`);
      if (okCombos >= needCombos) {
        console.log("  ✅ 快照已完整，本次补拍跳过（零接口调用、零写入）。");
        console.log("SUMMARY_JSON=" + JSON.stringify({
          snapshotDate, dryRun: !confirmWrite, skipped: "already_complete",
          ok_combos: okCombos, need_combos: needCombos, status: "success",
        }));
        return;
      }
      console.log("  ⚠️ 快照不完整，执行补拍。");
    }
    for (const s of stores) {
      console.log(`\n── ${s.storeName || s.storeId}  advertiser=${s.advertiserId} ──`);
      for (const entity of ENTITY_LIST) {
        if (onlyEntity && entity !== onlyEntity) continue;
        for (const ct of CT_LIST) {
          if (onlyCt && ct !== onlyCt) continue;
          const path = PATHS[entity][ct];
          const baseParams: Record<string, unknown> = {
            advertiserIds: [s.advertiserId],
            campaignType: CT_PARAM[ct],
            startDate, endDate, day: ATTR_DAY,
          };
          if (WITH_GATEWAY[entity]) baseParams.operationSourceType = "gateway";
          const sleepMs = IS_QUERY[entity] ? sleepQuery : sleepReport;

          let r: PullResult;
          try {
            r = await pull(db, client, path, baseParams, snapshotDate, sleepMs);
          } catch (e) {
            r = { code: "EXCEPTION", message: e instanceof Error ? e.message : String(e),
                  total: null, rows: [], pages: 0, hitCap: false };
          }
          const ok = r.code === "0";
          const complete = ok && !r.hitCap && (r.total === null || r.rows.length >= r.total);
          if (!ok) comboFail++;
          else if (!complete) comboIncomplete++;
          console.log(`  ${entity.padEnd(9)}${ct.padEnd(7)} code=${r.code.padEnd(10)} total=${r.total ?? "-"}`
            + ` 取回=${r.rows.length} 页=${r.pages}${r.hitCap ? " ⚠️触顶" : ""}`
            + ` ${complete ? "✅完整" : "⚠️不完整"}${r.message && !ok ? "  message=" + r.message.slice(0, 80) : ""}`);

          if (confirmWrite) {
            // ① 明细
            for (const row of r.rows) {
              const rj = JSON.stringify(row);
              if (entity === "campaign") {
                const bs = (row.biddingStrategy ?? {}) as Record<string, unknown>;
                await db.execute(
                  `INSERT INTO fact_ads_campaign_snapshot_daily
                     (snapshot_date, platform, store_id, advertiser_id, campaign_id, campaign_name, campaign_type,
                      campaign_status, targeting_type, daily_budget, total_budget, budget_type, rollover,
                      bidding_strategy, troas, bidding_strategy_status, start_date, end_date, entity_create_at, row_json)
                   VALUES (?, 'walmart', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON DUPLICATE KEY UPDATE
                     campaign_name=VALUES(campaign_name), campaign_type=VALUES(campaign_type),
                     campaign_status=VALUES(campaign_status), targeting_type=VALUES(targeting_type),
                     daily_budget=VALUES(daily_budget), total_budget=VALUES(total_budget),
                     budget_type=VALUES(budget_type), rollover=VALUES(rollover),
                     bidding_strategy=VALUES(bidding_strategy), troas=VALUES(troas),
                     bidding_strategy_status=VALUES(bidding_strategy_status),
                     start_date=VALUES(start_date), end_date=VALUES(end_date),
                     entity_create_at=VALUES(entity_create_at), row_json=VALUES(row_json)`,
                  [snapshotDate, s.storeId, str(s.advertiserId),
                   str(row.campaignId), str(row.campaignName ?? row.name), str(row.campaignType),
                   str(row.campaignStatus), str(row.targetingType),
                   numOrNull(row.dailyBudget), numOrNull(row.totalBudget), str(row.budgetType), str(row.rollover),
                   str(bs.strategy), numOrNull(bs.troas), str(bs.biddingStrategyStatus),
                   dtOrNull(row.startDate), dtOrNull(row.endDate), dtOrNull(row.entityCreateAt), rj]);
                upCamp++;
              } else if (entity === "group") {
                await db.execute(
                  `INSERT INTO fact_ads_group_snapshot_daily
                     (snapshot_date, platform, store_id, advertiser_id, campaign_id, ad_group_id, ad_group_name,
                      ad_group_status, campaign_type, entity_create_at, row_json)
                   VALUES (?, 'walmart', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON DUPLICATE KEY UPDATE
                     campaign_id=VALUES(campaign_id), ad_group_name=VALUES(ad_group_name),
                     ad_group_status=VALUES(ad_group_status), campaign_type=VALUES(campaign_type),
                     entity_create_at=VALUES(entity_create_at), row_json=VALUES(row_json)`,
                  [snapshotDate, s.storeId, str(s.advertiserId), str(row.campaignId),
                   str(row.adGroupId), str(row.adGroupName ?? row.name), str(row.adGroupStatus),
                   str(row.campaignType) || ct, dtOrNull(row.entityCreateAt), rj]);
                upGroup++;
              } else {
                const kwId = str(row.keywordId);
                if (!kwId) continue;               // 无 keywordId 的行不写（唯一键要求非空，且实测 200/200 有值）
                await db.execute(
                  `INSERT INTO fact_ads_keyword_snapshot_daily
                     (snapshot_date, platform, store_id, advertiser_id, campaign_id, ad_group_id, keyword_id,
                      keyword_name, keyword_bid, keyword_state, keyword_status, match_type,
                      campaign_status, ad_group_status, campaign_type, row_json)
                   VALUES (?, 'walmart', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON DUPLICATE KEY UPDATE
                     campaign_id=VALUES(campaign_id), ad_group_id=VALUES(ad_group_id),
                     keyword_name=VALUES(keyword_name), keyword_bid=VALUES(keyword_bid),
                     keyword_state=VALUES(keyword_state), keyword_status=VALUES(keyword_status),
                     match_type=VALUES(match_type), campaign_status=VALUES(campaign_status),
                     ad_group_status=VALUES(ad_group_status), campaign_type=VALUES(campaign_type),
                     row_json=VALUES(row_json)`,
                  [snapshotDate, s.storeId, str(s.advertiserId), str(row.campaignId), str(row.adGroupId), kwId,
                   str(row.keywordName ?? row.keywordText), numOrNull(row.keywordBid),
                   str(row.keywordState), str(row.keywordStatus), str(row.matchType),
                   str(row.campaignStatus), str(row.adGroupStatus), str(row.campaignType) || ct, rj]);
                upKw++;
              }
            }
            // ② 完整性状态（无论成败都写——失败与不完整本身就是要留档的事实）
            await db.execute(
              `INSERT INTO fact_ads_snapshot_status
                 (snapshot_date, platform, store_id, store_name, entity_type, campaign_type,
                  api_path, api_code, api_total, fetched_rows, pages_fetched, hit_page_cap, is_complete, error_message)
               VALUES (?, 'walmart', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON DUPLICATE KEY UPDATE
                 store_name=VALUES(store_name), api_path=VALUES(api_path), api_code=VALUES(api_code),
                 api_total=VALUES(api_total), fetched_rows=VALUES(fetched_rows),
                 pages_fetched=VALUES(pages_fetched), hit_page_cap=VALUES(hit_page_cap),
                 is_complete=VALUES(is_complete), error_message=VALUES(error_message)`,
              [snapshotDate, s.storeId, s.storeName ?? "", entity, ct, path, r.code, r.total,
               r.rows.length, r.pages, r.hitCap ? 1 : 0, complete ? 1 : 0, ok ? null : r.message]);
            statusRows++;
          }
        }
      }
    }

    if (confirmWrite) {
      await db.query(
        `INSERT INTO sync_task_log
           (task_name, source_system, target_table, status, pulled_count, inserted_count, failed_count, finished_at, error_message)
         VALUES (?, 'lingxing_api', 'fact_ads_*_snapshot_daily', ?, ?, ?, ?, NOW(), ?)`,
        [TASK_NAME, comboFail > 0 ? "failed" : "success",
         upCamp + upGroup + upKw, upCamp + upGroup + upKw, comboFail,
         comboFail > 0 ? `${comboFail} 个组合接口失败，${comboIncomplete} 个组合不完整` : null]);
    }

    console.log("\n" + "=".repeat(88));
    console.log(`快照日 ${snapshotDate}  写入=${confirmWrite}`);
    console.log(`  campaign upsert=${upCamp}   group upsert=${upGroup}   keyword upsert=${upKw}`);
    console.log(`  状态行=${statusRows}   接口失败组合=${comboFail}   不完整组合=${comboIncomplete}`);
    console.log(`  ⚠️ 提醒：is_complete=0 的组合，第三单的差分脚本**当天一律不得产生「关闭/删除」类事件**。`);
    console.log("SUMMARY_JSON=" + JSON.stringify({
      snapshotDate, apiWindow: `${startDate}~${endDate}`, dryRun: !confirmWrite,
      stores: stores.length, campaign_upserts: upCamp, group_upserts: upGroup, keyword_upserts: upKw,
      status_rows: statusRows, combo_failed: comboFail, combo_incomplete: comboIncomplete,
      status: comboFail > 0 ? "partial" : "success",
    }));
  } finally {
    await db.end().catch(() => undefined);
  }
}

main().catch((e: unknown) => { console.error("同步失败：", e instanceof Error ? e.message : String(e)); process.exit(1); });
