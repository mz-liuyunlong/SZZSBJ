/**
 * probeSpKeywordStatus.ts —— 只读探测：SP 关键词接口是否返回「关键词状态」字段
 *
 * 为什么单独写一个脚本：
 *   2026-08-21 曾用 `npx ts-node -e "..."` 内联跑同样的探测，**失败**——内联代码同样走项目的 strict tsconfig，
 *   回调参数 (o/f) 全部报 TS7006 隐式 any。教训：**探测逻辑一律落成正式 .ts 文件**，不用 -e 内联。
 *
 * 要回答的唯一问题：
 *   `reportKeywordSpList` 是否返回 keywordId / keywordState / keywordStatus？
 *   —— 这决定「关闭关键词」这一类人工操作能否靠**状态字段**判定。
 *   若不返回，就只能靠"行从 fact_ads_keyword_daily 里消失"去猜，而**消失 ≠ 关闭**：
 *   同步脚本 syncManualAdKeywordDaily.ts v2 有「五项指标全为 0 的行不写 FACT」规则，
 *   一个关键词当天没曝光就会消失，拿消失当关闭会造出大量假记录。
 *
 * 对照基准（2026-08-21 实测）：SV 的 reportKeywordSvList 返回 keywordState=enabled、keywordStatus=approved、
 *   keywordId、matchType、adGroupStatus，共 66 个字段。SP 若同构，则六类人工操作全部可判定。
 *
 * 只读约束：只调 report 系只读接口；不建表、不写任何 FACT/DIM/BIZ；每页响应写 raw_lingxing_api 留痕。
 * 用法：
 *   npx ts-node src/probeSpKeywordStatus.ts
 *   npx ts-node src/probeSpKeywordStatus.ts --advertiser=571910 --start=2026-08-01 --end=2026-08-18
 */
import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const PATH_SP_KW = "/basicOpen/multiplatform/ads/reportKeywordSpList";
const TIMEOUT_MS = 60000;

/** 与 SV 实测字段对齐的关注清单（SV 已确认全部有值，用作同构性对照） */
const FOCUS: string[] = [
  "keywordBid", "keywordId", "keywordName", "keywordState", "keywordStatus",
  "matchType", "adGroupStatus", "adGroupId", "campaignStatus", "campaignId", "targetingType",
];

function getArg(name: string, dflt: string): string {
  const p = `--${name}=`;
  const a = process.argv.find((x: string) => x.startsWith(p));
  return a ? a.slice(p.length) : dflt;
}

function isEmpty(v: unknown): boolean {
  return v === null || v === undefined || v === "" ||
    (Array.isArray(v) && v.length === 0);
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
): Promise<number | null> {
  try {
    const paramsJson = JSON.stringify(params);
    const respJson = JSON.stringify(resp);
    const rawHash = crypto.createHash("sha256").update(paramsJson + respJson).digest("hex");
    const code = String((resp as { code?: unknown })?.code ?? "");
    const [res] = await db.query<mysql.ResultSetHeader>(
      `INSERT INTO raw_lingxing_api
         (source_system, api_path, request_method, request_params_json, response_json,
          response_code, is_success, data_date, pulled_at, raw_hash, extra_json)
       VALUES ('lingxing', ?, 'POST', ?, ?, ?, ?, ?, NOW(), ?, JSON_OBJECT('probe','sp_keyword_status'))`,
      [apiPath, paramsJson, respJson, code, code === "0" ? 1 : 0, dataDate, rawHash],
    );
    return res.insertId ?? null;
  } catch (e) {
    console.warn(`  [RAW写入失败,忽略] ${e instanceof Error ? e.message : String(e)}`);
    return null;
  }
}

function distribution(rows: Record<string, unknown>[], field: string): string {
  const m = new Map<string, number>();
  for (const r of rows) {
    const k = isEmpty(r[field]) ? "(空)" : String(r[field]);
    m.set(k, (m.get(k) ?? 0) + 1);
  }
  return [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10)
    .map(([k, n]) => `${k}=${n}`).join("  ");
}

async function main(): Promise<void> {
  const advertiserId = Number(getArg("advertiser", "571910")); // CN2601-瑞盈龙盛，SP/SV 都有数据
  const startDate = getArg("start", "2026-08-01");
  const endDate = getArg("end", "2026-08-18");

  const client = new LingxingClient(loadConfig());
  const db = await getDb();
  const params: Record<string, unknown> = {
    advertiserIds: [advertiserId],
    campaignType: ["sponsoredProducts-manual", "sponsoredProducts-auto"],
    startDate, endDate, day: 14,
    pageNum: 1, pageSize: 200, paging: true,
  };

  console.log("═".repeat(78));
  console.log("SP 关键词接口 关键词状态字段 只读探测");
  console.log(`  ${PATH_SP_KW}`);
  console.log(`  advertiserId=${advertiserId}  区间=${startDate}~${endDate}`);
  console.log(`  请求参数: ${JSON.stringify(params)}`);
  console.log("═".repeat(78));

  try {
    const resp = await client.request<unknown>({ method: "POST", path: PATH_SP_KW, params, timeoutMs: TIMEOUT_MS });
    const rawId = await insertRaw(db, PATH_SP_KW, params, resp, endDate);
    const code = (resp as { code?: unknown })?.code;
    const msg = (resp as { message?: unknown })?.message;
    const total = (resp as { data?: { total?: unknown } })?.data?.total;
    console.log(`业务 code=${String(code)} | message=${String(msg ?? "")} | data.total=${total ?? "?"} | raw_id=${rawId ?? "?"}`);

    if (String(code) !== "0") {
      console.log("✗ 业务失败，原始响应前 800 字符（**不改参数重试，如实记录**）：");
      console.log(JSON.stringify(resp).slice(0, 800));
      return;
    }

    const d = (resp as { data?: { list?: unknown } })?.data;
    const rows: Record<string, unknown>[] = Array.isArray(d?.list) ? (d?.list as Record<string, unknown>[]) : [];
    if (rows.length === 0) {
      console.log("⚠️ code=0 但 0 行。注意：0 行不等于接口不可用，先排除样本问题（本店铺该区间是否真有 SP 关键词数据）。");
      console.log(JSON.stringify(resp).slice(0, 800));
      return;
    }

    const keys: string[] = [...new Set(rows.flatMap((o: Record<string, unknown>) => Object.keys(o)))].sort();
    console.log(`\n样本行数=${rows.length}  字段数=${keys.length}`);
    console.log(`全部字段名：\n  ${keys.join(", ")}`);

    console.log(`\n── 定向判定（文档有 ≠ 实测有值）──`);
    for (const f of FOCUS) {
      if (!keys.includes(f)) { console.log(`  ${f.padEnd(18)} ❌ 接口不返回该字段`); continue; }
      const n = rows.filter((o: Record<string, unknown>) => !isEmpty(o[f])).length;
      const s = rows.find((o: Record<string, unknown>) => !isEmpty(o[f]));
      const mark = n === 0 ? "❌ 全空" : n === rows.length ? "✅ 全有值" : "⚠️ 部分有值";
      console.log(`  ${f.padEnd(18)} ${mark.padEnd(12)} ${n}/${rows.length}  样例=${s ? JSON.stringify(s[f]) : ""}`);
    }

    console.log(`\n── 取值分布（状态类字段最关心分布：只有一个值＝无区分度）──`);
    for (const f of ["keywordState", "keywordStatus", "campaignStatus", "adGroupStatus", "matchType", "targetingType"]) {
      if (keys.includes(f)) console.log(`  ${f.padEnd(18)} ${distribution(rows, f)}`);
    }

    console.log(`\n── 与 SV 的同构性结论（SV 实测有 keywordState/keywordStatus/keywordId）──`);
    const hasState = keys.includes("keywordState") || keys.includes("keywordStatus");
    const hasId = keys.includes("keywordId");
    console.log(`  SP 是否返回关键词状态字段：${hasState ? "✅ 是" : "❌ 否"}`);
    console.log(`  SP 是否返回 keywordId    ：${hasId ? "✅ 是" : "❌ 否"}`);
    console.log(`  ⇒ 「关闭关键词」判定方式：${hasState ? "可用状态字段直接判定" : "只能靠行消失推断（不可靠，需另定口径）"}`);

    console.log(`\n── 首行完整 JSON ──`);
    console.log(JSON.stringify(rows[0]).slice(0, 1600));
  } catch (e) {
    console.error(`✗ 调用异常: ${e instanceof Error ? e.message : String(e)}`);
  } finally {
    await db.end().catch(() => undefined);
  }
}

main().catch((e: unknown) => { console.error("探测脚本异常:", e); process.exit(1); });
