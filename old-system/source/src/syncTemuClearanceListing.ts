/**
 * syncTemuClearanceListing.ts — TEMU「在售」商品自动录入清货台账（2026-08-03 需求方）
 * 数据流：领星 /basicOpen/multiplatform/temu/list（两TEMU半托店，全量翻页）→ RAW留存
 *   → 过滤 status=102(在售) 且 msku 以 JJ/YC 开头 → 每个 MSKU(变体)一行
 *   → sku=完整MSKU、platform_ref=该变体 mskuId → INSERT IGNORE biz_clearance_other_channel。
 * 需求口径：owner=张桓宾、manual_stock=0、channel=TEMU、added_by=auto_temu_listing。
 * 只写一次：唯一键(sku,channel)+INSERT IGNORE —— 已存在(active/done/removed)即跳过，人工移出后不再二次写。
 * 铁律：绝不 UPDATE 已存在行（owner/platform_ref/manual_stock/remark 等人工字段不覆盖）；外部数据先入RAW。
 * 用法：npx ts-node src/syncTemuClearanceListing.ts            # dry-run（只拉取+统计，零写入）
 *       npx ts-node src/syncTemuClearanceListing.ts --confirm-write
 */
import "dotenv/config";
import * as crypto from "crypto";
import * as mysql from "mysql2/promise";
import { loadConfig } from "./config";
import { LingxingClient } from "./lingxingClient";

const API_PATH = "/basicOpen/multiplatform/temu/list";
const TEMU_STORES = ["110726789976100864", "110726793010007040"]; // 美本TEMU puravida半托 / Furniture Haven
const STATUS_ON_SALE = 102;          // 在售（由 JJ4091/JJ5121 后台在售态确认）
const SKU_PREFIX_RE = /^(JJ|YC)/i;   // 需求：基本以 JJ/YC 开头的测品
const OWNER = "张桓宾";
const CHANNEL = "TEMU";
const ADDED_BY = "auto_temu_listing";
const PAGE_LEN = 100;
const PAGE_SLEEP_MS = 2500;          // temu/list 限流
const MAX_PAGES = 40;                // 保险丝

type Dict = Record<string, unknown>;
const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));
const md5 = (s: string): string => crypto.createHash("md5").update(s).digest("hex");
const todayShanghai = (): string => new Date(Date.now() + 8 * 3600 * 1000).toISOString().slice(0, 10);

function getDb(): Promise<mysql.Connection> {
  return mysql.createConnection({
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: Number(process.env.DB_PORT ?? 3306),
    user: process.env.DB_USER ?? "",
    password: process.env.DB_PASSWORD ?? "",
    database: process.env.DB_NAME ?? "walmart_ai_data",
    dateStrings: true,
  });
}
function asList(data: unknown): Dict[] {
  if (Array.isArray(data)) return data as Dict[];
  if (data && typeof data === "object" && Array.isArray((data as Dict).list)) return (data as Dict).list as Dict[];
  return [];
}

interface Cand { sku: string; platform_ref: string; mskus: string; day30: number; storeName: string; }

async function insertRaw(db: mysql.Connection, dataDate: string, tag: string, reqParams: unknown, body: unknown): Promise<void> {
  const bodyStr = JSON.stringify(body);
  try {
    await db.query(
      `INSERT IGNORE INTO raw_lingxing_api
         (source_system, api_path, request_method, request_params_json, data_date, response_json, is_success, raw_hash, extra_json, pulled_at)
       VALUES ('lingxing', ?, 'POST', ?, ?, ?, 1, ?, ?, NOW())`,
      [API_PATH, JSON.stringify(reqParams), dataDate, bodyStr, md5(`${API_PATH}|${dataDate}|${tag}|${bodyStr}`), JSON.stringify({ tag, purpose: "temu_clearance_listing" })],
    );
  } catch (e) { console.warn(`  ⚠️ insertRaw 失败 (${tag}): ${e instanceof Error ? e.message : String(e)}`); }
}

async function main(): Promise<void> {
  const confirmWrite = process.argv.includes("--confirm-write");
  const client = new LingxingClient(loadConfig());
  const db = await getDb();
  const dataDate = todayShanghai();
  try {
    // 1) 拉取两店全量 listing（RAW 留存）
    const rows: Dict[] = [];
    for (const store of TEMU_STORES) {
      for (let page = 0; page < MAX_PAGES; page++) {
        const params: Dict = { offset: page * PAGE_LEN, length: PAGE_LEN, store_ids: [store] };
        const resp = await client.request<unknown>({ method: "POST", path: API_PATH, params, timeoutMs: 30000 });
        const list = asList(resp.data);
        if (confirmWrite) await insertRaw(db, dataDate, `${store}_p${page}`, params, resp);
        rows.push(...list);
        if (list.length < PAGE_LEN) break;
        await sleep(PAGE_SLEEP_MS);
      }
      await sleep(PAGE_SLEEP_MS);
    }
    console.log(`拉取完成：合计 listing ${rows.length} 条（两TEMU店）`);

    // 2) 过滤 在售(102) + msku非空 + JJ/YC 前缀
    const onSale = rows.filter((r) => Number(r.status) === STATUS_ON_SALE && String(r.msku ?? "").trim() !== "" && SKU_PREFIX_RE.test(String(r.msku)));
    console.log(`在售(102)且JJ/YC前缀的变体：${onSale.length} 条`);

    // 3) MSKU级：每个 msku(变体)一行，sku=完整MSKU，platform_ref=该变体 mskuId（同msku跨页去重）
    const seen = new Set<string>();
    const cands: Cand[] = [];
    for (const r of onSale) {
      const msku = String(r.msku).trim();
      const mskuId = String(r.mskuId ?? "").trim();
      if (!msku || !mskuId || seen.has(msku)) continue;
      seen.add(msku);
      cands.push({ sku: msku, platform_ref: mskuId, mskus: msku, day30: Number(r.day30SaleCnt ?? 0), storeName: String(r.storeName ?? "") });
    }
    cands.sort((a, b) => a.sku.localeCompare(b.sku));
    console.log(`去重后候选 MSKU：${cands.length} 个`);

    // 4) INSERT IGNORE（只写全新；已存在任何状态即跳过，不覆盖人工字段）
    let inserted = 0, skipped = 0;
    const newList: string[] = [];
    for (const c of cands) {
      if (confirmWrite) {
        const [res] = await db.query<mysql.ResultSetHeader>(
          `INSERT IGNORE INTO biz_clearance_other_channel
             (sku, mskus, owner, channel, platform_ref, manual_stock, status, added_by, remark)
           VALUES (?, ?, ?, ?, ?, 0, 'active', ?, '')`,
          [c.sku, c.mskus, OWNER, CHANNEL, c.platform_ref, ADDED_BY],
        );
        if (res.affectedRows > 0) { inserted++; newList.push(`${c.sku}(${c.platform_ref})`); } else skipped++;
      } else {
        const [ex] = await db.query<mysql.RowDataPacket[]>(`SELECT status FROM biz_clearance_other_channel WHERE sku=? AND channel=? LIMIT 1`, [c.sku, CHANNEL]);
        if (ex.length) skipped++; else { inserted++; newList.push(`${c.sku}(${c.platform_ref})`); }
      }
    }
    console.log(`${confirmWrite ? "写入" : "DRY-RUN 预计写入"}：新增 ${inserted}，跳过(已存在) ${skipped}`);
    if (newList.length) console.log(`  新增清单：${newList.join(", ")}`);
    if (!confirmWrite) console.log("（dry-run，未写库；加 --confirm-write 实际写入）");
  } finally {
    await db.end().catch(() => {});
  }
}
main().catch((e) => { console.error("SYNC_FATAL", e instanceof Error ? e.message : e); process.exit(1); });
