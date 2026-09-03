/**
 * syncLingxingFxRate.ts — 领星汇率同步（AI财务 批7c）
 *
 * 链路：领星 /erp/sc/routing/finance/currency/currencyMonth → raw_lingxing_api（RAW-first）
 *       → fact_lingxing_fx_rate（rate_month × currency_code 唯一，幂等 upsert）
 *
 * 口径（官方文档实锤）：
 *   - 请求参数只有 date（汇率月份，形如 "2026-08"，必填），一次返回该月全部币种
 *   - 返回字段：date / code / icon / name / rate_org(官方汇率) / my_rate(我的汇率) / update_time
 *   - my_rate 文档原话「用户自定义汇率，系统首先使用该汇率数据」→ 领星算单品成本用的就是它，
 *     我方折算美元费用必须同源，否则与 wfs_stock_price 等成品值存在系统性偏差
 *   - 人工台账 biz_finance_exchange_rate 不受本脚本影响（兜底/覆盖层，一行不动）
 *
 * 规范：默认 dry-run 零写入；--confirm-write 才写库；RAW 写入失败的月份不写 FACT；
 *       不发送任何飞书消息；不改动任何既有表。
 *
 * 运行：
 *   npx ts-node src/syncLingxingFxRate.ts                              # dry-run，近13个月
 *   npx ts-node src/syncLingxingFxRate.ts --month=2026-08              # 只跑一个月
 *   npx ts-node src/syncLingxingFxRate.ts --from=2026-01 --to=2026-08
 *   npx ts-node src/syncLingxingFxRate.ts --confirm-write
 */

import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const SCRIPT_NAME = "syncLingxingFxRate";
const API_PATH = "/erp/sc/routing/finance/currency/currencyMonth";
const REQ_DELAY_MS = 700;
const DEFAULT_MONTHS = 13;

const CONFIRM_WRITE = process.argv.includes("--confirm-write");

function getArg(name: string, def = ""): string {
  const p = `--${name}=`;
  const hit = process.argv.find((a) => a.startsWith(p));
  return hit ? hit.slice(p.length) : def;
}
function sleep(ms: number): Promise<void> { return new Promise((r) => setTimeout(r, ms)); }
function s(v: unknown): string { return String(v ?? "").trim(); }
function numOrZero(v: unknown): number { const x = Number(v); return Number.isFinite(x) ? x : 0; }
function toDateTime(v: unknown): string | null {
  const t = s(v);
  const m = t.match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}):(\d{2}):(\d{1,2})/);
  if (m) return `${m[1]} ${m[2]}:${m[3]}:${m[4].padStart(2, "0")}`;
  return /^\d{4}-\d{2}-\d{2}$/.test(t) ? `${t} 00:00:00` : null;
}

/** 生成 yyyy-MM 列表（含端点），按 CST 当月回溯 */
function buildMonths(): string[] {
  const one = getArg("month", "");
  if (one) {
    if (!/^\d{4}-\d{2}$/.test(one)) throw new Error(`--month 格式应为 yyyy-MM，收到 ${one}`);
    return [one];
  }
  const from = getArg("from", ""), to = getArg("to", "");
  const nowCst = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit" })
    .format(new Date()).slice(0, 7);
  const end = to || nowCst;
  if (!/^\d{4}-\d{2}$/.test(end)) throw new Error(`--to 格式应为 yyyy-MM，收到 ${end}`);
  let start = from;
  if (!start) {
    const [y, m] = end.split("-").map(Number);
    const d = new Date(Date.UTC(y, m - 1 - (DEFAULT_MONTHS - 1), 1));
    start = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
  }
  if (!/^\d{4}-\d{2}$/.test(start)) throw new Error(`--from 格式应为 yyyy-MM，收到 ${start}`);
  const out: string[] = [];
  const [sy, sm] = start.split("-").map(Number);
  const [ey, em] = end.split("-").map(Number);
  let cur = new Date(Date.UTC(sy, sm - 1, 1));
  const last = new Date(Date.UTC(ey, em - 1, 1));
  while (cur <= last && out.length < 60) {
    out.push(`${cur.getUTCFullYear()}-${String(cur.getUTCMonth() + 1).padStart(2, "0")}`);
    cur = new Date(Date.UTC(cur.getUTCFullYear(), cur.getUTCMonth() + 1, 1));
  }
  return out;
}

interface FxRow { date?: unknown; code?: unknown; icon?: unknown; name?: unknown; rate_org?: unknown; my_rate?: unknown; update_time?: unknown }

function unwrapList(resp: unknown): FxRow[] {
  const r = resp as Record<string, unknown> | undefined;
  const d1 = r?.data as Record<string, unknown> | undefined;
  if (Array.isArray(d1)) return d1 as FxRow[];
  const cands = [d1?.data, d1?.list, d1?.records];
  for (const v of cands) if (Array.isArray(v)) return v as FxRow[];
  return [];
}

async function insertRaw(db: mysql.Connection, params: unknown, resp: unknown, month: string): Promise<number> {
  const requestJson = JSON.stringify(params);
  const responseJson = JSON.stringify(resp);
  const rawHash = crypto.createHash("sha256").update(`${API_PATH}|${requestJson}|${responseJson}`).digest("hex");
  const extraJson = JSON.stringify({ script: SCRIPT_NAME, month });
  await db.query(
    `INSERT IGNORE INTO raw_lingxing_api
       (source_system, api_path, request_method, request_params_json, response_json,
        response_code, is_success, error_message, data_date, raw_hash, extra_json)
     VALUES ('lingxing', ?, 'POST', CAST(? AS JSON), CAST(? AS JSON), '0', 1, NULL, CURDATE(), ?, CAST(? AS JSON))`,
    [API_PATH, requestJson, responseJson, rawHash, extraJson],
  );
  const [rows] = await db.query<mysql.RowDataPacket[]>(
    `SELECT id FROM raw_lingxing_api WHERE api_path=? AND data_date=CURDATE() AND raw_hash=? ORDER BY id DESC LIMIT 1`,
    [API_PATH, rawHash],
  );
  const rawId = Number(rows[0]?.id ?? 0);
  if (!rawId) throw new Error(`RAW 写入/回查失败（${month}），该月不写 FACT`);
  return rawId;
}

async function main(): Promise<void> {
  const months = buildMonths();
  console.log("=".repeat(64));
  console.log(`领星汇率同步 ${CONFIRM_WRITE ? "[confirm-write 写库]" : "[dry-run 零写入]"}`);
  console.log(`接口=${API_PATH} | 月份=${months[0]} ~ ${months[months.length - 1]}（共 ${months.length} 个月）`);
  console.log("主口径 my_rate（领星「我的汇率」，其算成本优先用它）；人工台账 biz_finance_exchange_rate 不受影响");
  console.log("=".repeat(64));

  const client = new LingxingClient(loadConfig());
  const db = await mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
    dateStrings: true,
  });

  let rowsSeen = 0, upserts = 0, monthsOk = 0;
  const usdTable: Array<{ m: string; org: number; mine: number }> = [];
  const emptyMonths: string[] = [];

  try {
    for (const m of months) {
      const params = { date: m };
      const resp = await client.post<unknown>(API_PATH, params);
      const list = unwrapList(resp);
      if (!list.length) { emptyMonths.push(m); console.log(`  ${m}: 0 条`); await sleep(REQ_DELAY_MS); continue; }
      monthsOk += 1;
      let rawId = 0;
      if (CONFIRM_WRITE) rawId = await insertRaw(db, { api: API_PATH, ...params }, resp, m);

      for (const r of list) {
        const code = s(r.code).toUpperCase();
        const month = s(r.date) || m;
        if (!code || !/^\d{4}-\d{2}$/.test(month)) continue;
        rowsSeen += 1;
        const org = numOrZero(r.rate_org), mine = numOrZero(r.my_rate);
        if (code === "USD") usdTable.push({ m: month, org, mine });
        if (!CONFIRM_WRITE) continue;
        await db.query(
          `INSERT INTO fact_lingxing_fx_rate
             (rate_month, currency_code, currency_name, icon, rate_org, my_rate, lx_update_time, source_raw_id)
           VALUES (?,?,?,?,?,?,?,?)
           ON DUPLICATE KEY UPDATE
             currency_name=VALUES(currency_name), icon=VALUES(icon),
             rate_org=VALUES(rate_org), my_rate=VALUES(my_rate),
             lx_update_time=VALUES(lx_update_time), source_raw_id=VALUES(source_raw_id), updated_at=NOW()`,
          [month, code, s(r.name).slice(0, 32), s(r.icon).slice(0, 8), org, mine, toDateTime(r.update_time), rawId],
        );
        upserts += 1;
      }
      console.log(`  ${m}: ${list.length} 条币种`);
      await sleep(REQ_DELAY_MS);
    }

    console.log("\n" + "=".repeat(64));
    console.log(`成功月份 ${monthsOk}/${months.length}｜币种行 ${rowsSeen}｜upsert ${upserts}`);
    if (emptyMonths.length) console.log(`⚠️ 无数据月份：${emptyMonths.join(", ")}`);
    if (usdTable.length) {
      console.log("\nUSD→CNY 逐月（判读用，官方汇率 vs 我的汇率）：");
      console.log("  月份      官方汇率    我的汇率");
      for (const u of usdTable.sort((a, b) => a.m.localeCompare(b.m))) {
        console.log(`  ${u.m}   ${u.org.toFixed(4)}      ${u.mine.toFixed(4)}${u.mine === 0 ? "  ⚠️ 我的汇率为0，折算需退官方汇率" : ""}`);
      }
    }
    console.log(CONFIRM_WRITE ? "已写库。" : "dry-run 结束，未写入任何数据。");
  } finally {
    await db.end().catch(() => undefined);
  }
}

main().catch((e) => {
  console.error("同步失败:", e instanceof Error ? e.stack : String(e));
  process.exit(1);
});
