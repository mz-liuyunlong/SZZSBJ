/**
 * noOrderNotify.ts - 不出单产品飞书机器人通报
 *
 * 筛选"库存不为 0，但近 3/5/7 天没出单"的产品，
 * 按负责人维度生成消息，发送到飞书机器人 Webhook。
 *
 * 手动 dry-run（不发送）：
 *   npx ts-node src/noOrderNotify.ts
 *
 * 手动真实发送：
 *   npx ts-node src/noOrderNotify.ts --send
 *
 * 分组优先级：近 7 天没出单 > 近 5 天没出单 > 近 3 天没出单
 * 一个产品只出现在一个分组。
 */

import currentReport from "../config/currentReportFieldMapping.json";
import { STORES } from "./syncDailyBaseData";
import { loadConfig } from "./config";
import { FeishuSheetWriter } from "./feishuSheetWriter";
import { LingxingClient } from "./lingxingClient";
import { TableOperationLogger } from "./tableOperationLogger";
import * as mysql from "mysql2/promise";

// axios 复用项目已有依赖
const axios = require("axios/dist/node/axios.cjs") as typeof import("axios").default;

// ── 配置 ─────────────────────────────────────────────────────────────
const WALMART_LIST_PATH = "/basicOpen/multiplatform/walmart/list";
const SALE_STAT_PATH = "/basicOpen/platformStatisticsV2/saleStat/pageList";
const PAGE_LENGTH = 200;
const WALMART_MAX_PAGES = 50;
const SALE_STAT_PAGE_LENGTH = 200;
const SALE_STAT_MAX_PAGES = 20;
// 下游迁移（脱离飞书 ItemID负责人 / <REDACTED_FEISHU_SHEET_ID>）：负责人映射改读 MySQL dim_product.owner，
// 口径与 syncOrderProfitDaily.ts / ai_pmc/readOwners.ts 一致，不再调用飞书 API 读取 <REDACTED_FEISHU_SHEET_ID>。
const OWNER_DATA_SOURCE_LABEL = "领星API + dim_product.owner";
const TIMEOUT_MS = 120000;
const MAX_RETRIES = 3;
const UNMATCHED_LABEL = "未匹配负责人";

// ── 环境变量 ──────────────────────────────────────────────────────────
// 批B收口: FEISHU_APP_ID/SECRET 由 feishuNotify 模块统一读取
// 批B(2026-07-11): 统一发送模块——额外接收端（env 留空=行为与现状完全一致）
import { parseListEnv, resolveActiveMembers, fanoutText, formatResults, sendTextToTarget, getTenantToken, sendTestGroupText, NotifyTarget } from "./feishuNotify";
import { buildInventorySnapshot, shouldIncludeInNoOrderNotify } from "./notifyRules/noOrderInventoryRule";

function createRunId(): string {
  return `run_${new Date().toISOString().replace(/[-:.TZ]/g, "")}_${Math.random().toString(36).slice(2, 8)}`;
}

// ── 类型 ─────────────────────────────────────────────────────────────
interface WalmartItem {
  item_id: string;
  msku: string;
  store_name: string;
  inventory: number; // totalAvailableQty，兼容原消息展示
  wfsAvailableQty: number;
  nonWfsAvailableQty: number;
  totalAvailableQty: number;
  inboundQty?: number;
  warehouseQty?: number;
}

interface SalesData {
  orders7: number;
  orders5: number;
  orders3: number;
}

interface ProductWithData extends WalmartItem, SalesData {
  owner: string;
  group: 7 | 5 | 3;
}

interface OwnerGroup {
  owner: string;
  group7: ProductWithData[];
  group5: ProductWithData[];
  group3: ProductWithData[];
}

interface DateWindows {
  today: string;
  yesterday: string;
  threeDaysAgo: string;
  fiveDaysAgo: string;
  sevenDaysAgo: string;
}

// ── 日期工具 ─────────────────────────────────────────────────────────
function getShanghaiDateWindows(): DateWindows {
  const nowUtc = new Date();
  // 上海 = UTC+8
  const shanghaiMs = nowUtc.getTime() + 8 * 60 * 60 * 1000;
  const shanghaiNow = new Date(shanghaiMs);

  const fmtUtc = (d: Date): string => {
    const y = d.getUTCFullYear();
    const m = String(d.getUTCMonth() + 1).padStart(2, "0");
    const day = String(d.getUTCDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  };

  const shiftDays = (base: Date, delta: number): Date =>
    new Date(base.getTime() + delta * 86400000);

  return {
    today: fmtUtc(shanghaiNow),
    yesterday: fmtUtc(shiftDays(shanghaiNow, -1)),
    threeDaysAgo: fmtUtc(shiftDays(shanghaiNow, -3)),
    fiveDaysAgo: fmtUtc(shiftDays(shanghaiNow, -5)),
    sevenDaysAgo: fmtUtc(shiftDays(shanghaiNow, -7)),
  };
}

function getShanghaiTimeStr(): string {
  return new Date().toLocaleString("zh-CN", {
    timeZone: "Asia/Shanghai",
    hour12: false,
  });
}

// ── 通用工具 ─────────────────────────────────────────────────────────
function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function toNumber(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function normKey(value: unknown): string {
  return String(value ?? "").trim();
}

/** 兼容 API 返回 JSON 字符串数组或普通数组 */
function toArrayValues(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(normKey).filter(Boolean);
  if (typeof value === "string") {
    const text = value.trim();
    if (!text) return [];
    try {
      const parsed = JSON.parse(text);
      if (Array.isArray(parsed)) return parsed.map(normKey).filter(Boolean);
    } catch {
      // 普通字符串
    }
    return [text];
  }
  const n = normKey(value);
  return n ? [n] : [];
}

function extractListItems(data: unknown): unknown[] {
  if (Array.isArray(data)) return data;
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    for (const key of ["list", "data", "rows", "records"]) {
      if (Array.isArray(d[key])) return d[key] as unknown[];
    }
  }
  return [];
}

async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function withRetry<T>(label: string, fn: () => Promise<T>): Promise<T> {
  let lastErr: unknown;
  for (let i = 1; i <= MAX_RETRIES; i++) {
    try {
      return await fn();
    } catch (e) {
      lastErr = e;
      console.log(`  [重试 ${i}/${MAX_RETRIES}] ${label}: ${getErrorMessage(e)}`);
      if (i < MAX_RETRIES) await sleep(1000 * i);
    }
  }
  throw lastErr;
}

// ── 领星：抓取商品列表（库存）────────────────────────────────────────
async function fetchAllProducts(client: LingxingClient): Promise<WalmartItem[]> {
  const all: WalmartItem[] = [];

  for (const [i, store] of STORES.entries()) {
    if (i > 0) await sleep(800);
    console.log(`  → 店铺: ${store.storeName}`);

    for (let page = 0; page < WALMART_MAX_PAGES; page++) {
      const offset = page * PAGE_LENGTH;
      try {
        const resp = await withRetry(`${store.storeName} 商品列表 page=${page + 1}`, () =>
          client.request<unknown>({
            method: "POST",
            path: WALMART_LIST_PATH,
            params: {
              store_ids: [store.storeId],
              status: [0], // PUBLISHED
              offset,
              length: PAGE_LENGTH,
            },
            timeoutMs: TIMEOUT_MS,
          }),
        );

        const items = extractListItems(resp.data);
        for (const raw of items) {
          const r = raw as Record<string, unknown>;
          const item_id = normKey(r.item_id);
          const msku = normKey(r.msku);
          if (!item_id && !msku) {
            console.log(`  [跳过] item_id 和 msku 均为空，店铺=${store.storeName}`);
            continue;
          }
          const inventorySnapshot = buildInventorySnapshot(r);
          all.push({
            item_id: item_id || msku,
            msku: msku || item_id,
            store_name: normKey(r.store_name) || store.storeName,
            inventory: inventorySnapshot.totalAvailableQty,
            wfsAvailableQty: inventorySnapshot.wfsAvailableQty,
            nonWfsAvailableQty: inventorySnapshot.nonWfsAvailableQty,
            totalAvailableQty: inventorySnapshot.totalAvailableQty,
            inboundQty: inventorySnapshot.inboundQty,
            warehouseQty: inventorySnapshot.warehouseQty,
          });
        }

        if (items.length < PAGE_LENGTH) break;
      } catch (e) {
        console.log(`  [警告] ${store.storeName} 商品列表第 ${page + 1} 页失败，跳过: ${getErrorMessage(e)}`);
        break;
      }
    }
  }

  return all;
}

// ── 领星：抓取近 7 天销售订单数 ──────────────────────────────────────
/** 解析 date_collect JSON 字符串 → {日期: 订单数} */
function parseDateCollect(raw: unknown): Record<string, number> {
  if (!raw) return {};
  try {
    const obj = typeof raw === "string" ? JSON.parse(raw) : raw;
    if (obj && typeof obj === "object" && !Array.isArray(obj)) {
      const result: Record<string, number> = {};
      for (const [date, val] of Object.entries(obj as Record<string, unknown>)) {
        result[date] = toNumber(val);
      }
      return result;
    }
  } catch {
    // ignore
  }
  return {};
}

/** 汇总 date_collect 中 [start, end] 日期范围的订单数 */
function sumDateRange(dc: Record<string, number>, start: string, end: string): number {
  return Object.entries(dc)
    .filter(([date]) => date >= start && date <= end)
    .reduce((sum, [, v]) => sum + v, 0);
}

async function fetchSalesDataMap(
  client: LingxingClient,
  dates: DateWindows,
): Promise<Map<string, SalesData>> {
  const result = new Map<string, SalesData>();

  for (const [i, store] of STORES.entries()) {
    if (i > 0) await sleep(800);
    console.log(`  → 店铺: ${store.storeName}`);

    for (let page = 1; page <= SALE_STAT_MAX_PAGES; page++) {
      try {
        const resp = await withRetry(`${store.storeName} 销售统计 page=${page}`, () =>
          client.request<unknown>({
            method: "POST",
            path: SALE_STAT_PATH,
            params: {
              start_date: dates.sevenDaysAgo,
              end_date: dates.yesterday,
              result_type: "2", // 订单量
              date_unit: "4",   // 日
              data_type: "1",   // item_id (ASIN/Walmart商品ID) 维度
              page,
              length: SALE_STAT_PAGE_LENGTH,
              sids: [store.storeId],
            },
            timeoutMs: TIMEOUT_MS,
          }),
        );

        const items = extractListItems(resp.data);
        for (const raw of items) {
          const r = raw as Record<string, unknown>;
          const ids = toArrayValues(r.platform_product_id);
          if (!ids.length) continue;

          const dc = parseDateCollect(r.date_collect);
          const orders7 = sumDateRange(dc, dates.sevenDaysAgo, dates.yesterday);
          const orders5 = sumDateRange(dc, dates.fiveDaysAgo, dates.yesterday);
          const orders3 = sumDateRange(dc, dates.threeDaysAgo, dates.yesterday);

          for (const id of ids) {
            const existing = result.get(id);
            if (existing) {
              existing.orders7 += orders7;
              existing.orders5 += orders5;
              existing.orders3 += orders3;
            } else {
              result.set(id, { orders7, orders5, orders3 });
            }
          }
        }

        if (items.length < SALE_STAT_PAGE_LENGTH) break;
      } catch (e) {
        console.log(`  [警告] ${store.storeName} 销售统计第 ${page} 页失败，跳过: ${getErrorMessage(e)}`);
        break;
      }
    }
  }

  return result;
}

// ── MySQL：读取负责人映射（替代飞书 ItemID负责人 表）────────────────────
async function loadOwnerMapFromMysql(): Promise<Map<string, string>> {
  let db: mysql.Connection | null = null;
  try {
    db = await mysql.createConnection({
      host:     process.env.DB_HOST     ?? "127.0.0.1",
      port:     Number(process.env.DB_PORT ?? 3306),
      user:     process.env.DB_USER     ?? "",
      password: process.env.DB_PASSWORD ?? "",
      database: process.env.DB_NAME     ?? "walmart_ai_data",
    });
    const [rows] = await db.execute<mysql.RowDataPacket[]>(
      "SELECT item_id, owner FROM dim_product WHERE owner IS NOT NULL AND owner <> ''",
    );
    const map = new Map<string, string>();
    for (const r of rows) {
      const id = normKey(r.item_id);
      if (!id) continue;
      map.set(id, normKey(r.owner));
    }
    return map;
  } finally {
    if (db) await db.end().catch(() => {});
  }
}

// ── 筛选 & 分组 ──────────────────────────────────────────────────────
interface ClassifyStats {
  totalProducts: number;
  withInventory: number;
  group7: number;
  group5: number;
  group3: number;
  matched: number;
  unmatched: number;
  lowEffectiveInventoryExcluded: number;
}

function classifyProducts(
  products: WalmartItem[],
  salesMap: Map<string, SalesData>,
  ownerMap: Map<string, string>,
): { results: ProductWithData[]; stats: ClassifyStats } {
  const results: ProductWithData[] = [];
  const stats: ClassifyStats = {
    totalProducts: products.length,
    withInventory: 0,
    group7: 0,
    group5: 0,
    group3: 0,
    matched: 0,
    unmatched: 0,
    lowEffectiveInventoryExcluded: 0,
  };

  for (const p of products) {
    // 只处理库存 > 0
    if (p.inventory <= 0) continue;
    stats.withInventory++;
    if (!shouldIncludeInNoOrderNotify(p)) {
      stats.lowEffectiveInventoryExcluded++;
      continue;
    }

    // 获取订单数（不在 salesMap 中 = 0订单）
    const sales = salesMap.get(p.item_id) ?? { orders7: 0, orders5: 0, orders3: 0 };

    // 分组（互斥，优先级 7 > 5 > 3）
    let group: 7 | 5 | 3 | null = null;
    if (sales.orders7 === 0) {
      group = 7;
      stats.group7++;
    } else if (sales.orders5 === 0) {
      group = 5;
      stats.group5++;
    } else if (sales.orders3 === 0) {
      group = 3;
      stats.group3++;
    }

    if (group === null) continue; // 近 3 天有出单，不通报

    // 负责人匹配
    const ownerInMap = ownerMap.get(p.item_id);
    if (ownerInMap !== undefined) {
      stats.matched++;
    } else {
      stats.unmatched++;
    }
    const owner = ownerInMap !== undefined ? ownerInMap || UNMATCHED_LABEL : UNMATCHED_LABEL;

    results.push({ ...p, ...sales, owner, group });
  }

  return { results, stats };
}

// ── 飞书消息生成 ──────────────────────────────────────────────────────

/** 从 dim_feishu_member 表读取 负责人名 → open_id 映射 */
// 批B第3版: loadOwnerOpenIds 已移除——原负责人与新增个人接收人统一走
// feishuNotify.resolveActiveMembers（精确匹配+active+open_id非空；0条/重名告警跳过，禁止猜测）。

function buildOwnerMessage(og: OwnerGroup, notifyTime: string): string {
  const lines: string[] = [
    `【不出单产品通报】${notifyTime}`,
    `负责人：${og.owner}`,
  ];

  const sections: [string, ProductWithData[]][] = [
    ["近 7 天没出单", og.group7],
    ["近 5 天没出单", og.group5],
    ["近 3 天没出单", og.group3],
  ];

  for (const [label, items] of sections) {
    if (!items.length) continue;
    lines.push(`${label}：${items.length} 个`);

    const byStore = new Map<string, ProductWithData[]>();
    for (const item of items) {
      if (!byStore.has(item.store_name)) byStore.set(item.store_name, []);
      byStore.get(item.store_name)!.push(item);
    }
    for (const [storeName, storeItems] of byStore.entries()) {
      lines.push(`店铺：${storeName}`);
      for (const i of storeItems) {
        lines.push(`  MSKU：${i.msku} 库存：${i.inventory}`);
      }
    }
  }

  return lines.join("\n");
}

/** 按负责人拆分，返回每人的 { owner, message } */
function buildOwnerMessages(products: ProductWithData[], notifyTime: string): { owner: string; message: string }[] {
  if (!products.length) return [];

  // 按负责人归组
  const ownerGroupMap = new Map<string, OwnerGroup>();
  for (const p of products) {
    if (!ownerGroupMap.has(p.owner)) {
      ownerGroupMap.set(p.owner, { owner: p.owner, group7: [], group5: [], group3: [] });
    }
    const g = ownerGroupMap.get(p.owner)!;
    if (p.group === 7) g.group7.push(p);
    else if (p.group === 5) g.group5.push(p);
    else g.group3.push(p);
  }

  // 排序：有名字的在前，过滤掉未匹配负责人（由独立的 unmatchedOwnerNotify 处理）
  const owners = [...ownerGroupMap.values()]
    .filter((og) => og.owner !== UNMATCHED_LABEL)
    .sort((a, b) => a.owner.localeCompare(b.owner, "zh-CN"));

  return owners.map((og) => ({ owner: og.owner, message: buildOwnerMessage(og, notifyTime) }));
}

// ── 飞书个人消息发送 ──────────────────────────────────────────────────
// 批B收口: 本地 getFeishuAppToken/sendToFeishuUser 已移除，
// 原负责人个人消息统一走 feishuNotify.sendTextToTarget（分类重试/敏感日志清理/分片/独立结果）
// 数据查询、分组和消息内容不变。

// ── 主函数 ───────────────────────────────────────────────────────────
async function main(): Promise<void> {
  const startedAt = Date.now();
  const runId = createRunId();
  const doSend = process.argv.includes("--send");
  // 测试模式(2026-07-11)：--test-send 只发测试群（应用机器人），不发原负责人/新增接收人/生产群/webhook，
  // 不写操作日志（finally 的 !doSend 门禁天然覆盖）；--send 与 --test-send 禁止同用
  const testSend = process.argv.includes("--test-send");
  if (testSend && doSend) {
    console.log("[错误] --send 与 --test-send 禁止同时使用");
    process.exit(1);
  }
  if (testSend && process.argv.includes("--dry-run")) {
    console.log("[错误] --dry-run 与 --test-send 禁止同时使用");
    process.exit(1);
  }
  if (process.argv.includes("--force-preview-test") && !testSend) {
    console.log("[错误] --force-preview-test 必须配合 --test-send 使用");
    process.exit(1);
  }

  const dates = getShanghaiDateWindows();
  const notifyTime = getShanghaiTimeStr();

  console.log("=".repeat(60));
  console.log("不出单产品飞书机器人通报");
  console.log(`执行时间（上海）: ${getShanghaiTimeStr()}`);
  console.log(`模式: ${testSend ? "test-send（仅应用机器人测试群）" : doSend ? "真实发送" : "dry-run（加 --send 参数发送）"}`);
  console.log(`统计窗口: ${dates.sevenDaysAgo} ～ ${dates.yesterday}`);
  console.log(`  近 3 天: ${dates.threeDaysAgo} ～ ${dates.yesterday}`);
  console.log(`  近 5 天: ${dates.fiveDaysAgo} ～ ${dates.yesterday}`);
  console.log(`  近 7 天: ${dates.sevenDaysAgo} ～ ${dates.yesterday}`);
  console.log("=".repeat(60));

  const config = loadConfig();
  config.timeoutMs = TIMEOUT_MS;
  const client = new LingxingClient(config);
  const writer = new FeishuSheetWriter();
  const logger = new TableOperationLogger(writer, {
    spreadsheetToken: currentReport.spreadsheetToken,
    logSheetId: currentReport.sheets["表格操作日志"],
    dryRun: false,
    confirmWrite: true,
  });

  let status = doSend ? "success" : "dry-run";
  let errorMessage = "";
  let fetchedCount = 0;
  let sentCount = 0;
  let skippedCount = 0;

  try {
    // ─ 步骤 1：抓取商品列表（含库存）────────────────────────────────────
    console.log(`\n[1/4] 抓取所有店铺商品列表（共 ${STORES.length} 个店铺）...`);
    const allProducts = await fetchAllProducts(client);
    console.log(`  抓取商品总数: ${allProducts.length}`);
    fetchedCount = allProducts.length;

    // ─ 步骤 2：抓取近 7 天订单数 ─────────────────────────────────────────
    console.log(`\n[2/4] 抓取近 7 天销售订单数（${dates.sevenDaysAgo} ～ ${dates.yesterday}）...`);
    const salesMap = await fetchSalesDataMap(client, dates);
    console.log(`  有出单记录的 item_id 数: ${salesMap.size}`);

    // ─ 步骤 3：读取 MySQL 负责人映射 ─────────────────────────────────────
    console.log(`\n[3/4] 读取 MySQL dim_product 负责人映射...`);
    const ownerMap = await loadOwnerMapFromMysql();
    console.log(`  有效 ITEM ID 映射条数: ${ownerMap.size}`);

    // ─ 步骤 4：筛选 & 发送 ────────────────────────────────────────────────
    console.log("\n[4/4] 筛选不出单产品，生成并发送通报...");
    const { results, stats } = classifyProducts(allProducts, salesMap, ownerMap);

    console.log(`  总商品数: ${stats.totalProducts}`);
    console.log(`  库存 > 0: ${stats.withInventory}`);
    console.log(`  排除低有效库存商品数：${stats.lowEffectiveInventoryExcluded} 个（WFS=0 且 非WFS<=1）`);
    console.log(`  近 7 天没出单: ${stats.group7}`);
    console.log(`  近 5 天没出单: ${stats.group5}`);
    console.log(`  近 3 天没出单: ${stats.group3}`);
    console.log(`  匹配到负责人: ${stats.matched}`);
    console.log(`  未匹配负责人: ${stats.unmatched}`);
    skippedCount = stats.totalProducts - stats.withInventory;

    const ownerMessages = buildOwnerMessages(results, notifyTime);

    // ── 测试模式：真实数据 → 汇总 → 只发测试群，随后直接返回 ──
    if (testSend) {
      // 空状态也必须发送一条测试消息（验证发送通道），不伪造业务明细
      const bodyText = ownerMessages.length
        ? ownerMessages.map((m) => m.message).join("\n\n")
        : "本次没有符合条件的数据。\n此消息仅用于验证应用机器人发送通道。";
      const testText = [
        `【测试】【不出单产品通报】${notifyTime}`,
        `统计窗口: ${dates.sevenDaysAgo} ~ ${dates.yesterday}`,
        `待通报负责人数: ${ownerMessages.length}`,
        "",
        bodyText,
      ].join("\n");
      const r = await sendTestGroupText("测试群", testText);
      console.log(`测试群发送结果: ${formatResults([r])}`);
      if (!r.ok) {
        status = "failed";
        errorMessage = r.error ?? "test send failed";
        process.exitCode = 1;
      } else {
        status = "test_send_success";
        console.log("NOTIFY_TEST_SENT=1");
      }
      return;
    }

    // 批B第3版: 唯一花名册解析口径（一次批量解析全部负责人）
    const { targets: ownerTargets, warnings: ownerWarnings } =
      await resolveActiveMembers(ownerMessages.map((m) => m.owner));
    ownerWarnings.forEach((w) => console.log(`  [告警] 负责人 ${w}`));
    const ownerTargetMap = new Map(ownerTargets.map((t) => [t.label, t]));
    console.log(`  待通报负责人数: ${ownerMessages.length}（可发送 ${ownerTargetMap.size}）`);

    let appToken = "";
    if (doSend) {
      appToken = await getTenantToken();
      console.log("  飞书 token 获取成功");
    }

    let allOk = true;
    for (const { owner, message } of ownerMessages) {
      const target = ownerTargetMap.get(owner);
      if (!target) {
        // 0条或重名：已在解析告警中说明，跳过，禁止猜测发送
        skippedCount++;
        continue;
      }
      // 批B收口: 统一模块发送（重试/分片/安全日志/独立结果）
      const r = await sendTextToTarget(appToken, target, message, doSend);
      if (!r.ok) allOk = false;
      if (doSend) await sleep(500);
      sentCount++;
    }
    // ── 批B: 额外接收端（NO_ORDER_EXTRA_USERS / NO_ORDER_EXTRA_CHAT_IDS，留空即现状） ──
    const extraUserNames = parseListEnv("NO_ORDER_EXTRA_USERS");
    const extraChatIds = parseListEnv("NO_ORDER_EXTRA_CHAT_IDS");
    if (extraUserNames.length || extraChatIds.length) {
      const { targets: userTargets, warnings } = await resolveActiveMembers(extraUserNames);
      warnings.forEach((w) => console.log(`  [告警] 额外接收人 ${w}`));
      const extraTargets: NotifyTarget[] = [
        ...userTargets,
        ...extraChatIds.map((id, i) => ({ type: "chat" as const, label: `通报群${i + 1}`, id })),
      ];
      if (!ownerMessages.length) {
        console.log("  额外接收端：本次无待通报内容，不发送");
      } else if (extraTargets.length) {
        const summaryText = [
          `【不出单产品通报·汇总】${notifyTime}`,
          `统计窗口: ${dates.sevenDaysAgo} ~ ${dates.yesterday}`,
          `待通报负责人数: ${ownerMessages.length}`,
          "",
          ownerMessages.map((m) => m.message).join("\n\n"),
        ].join("\n");
        const extraResults = await fanoutText(appToken, extraTargets, summaryText, doSend);
        console.log(`  额外接收端结果: ${formatResults(extraResults)}`);
        if (extraResults.some((r) => !r.ok)) {
          console.log("  [告警] 部分额外接收端发送失败（独立通道，不影响原接收人结果）");
        }
      }
    }

    const sendOk = allOk;

    const elapsed = ((Date.now() - startedAt) / 1000).toFixed(1);
    console.log(`\n飞书发送结果: ${sendOk ? "✅ 成功" : "❌ 失败"}`);
    console.log(`执行完毕，耗时 ${elapsed}s`);

    if (!sendOk) {
      status = "failed";
      errorMessage = "飞书发送失败";
      process.exitCode = 1;
    }
  } catch (e) {
    status = "failed";
    errorMessage = getErrorMessage(e);
    console.log(`[错误] ${errorMessage}`);
    process.exitCode = 1;
  } finally {
    if (!doSend) {
      console.log(`[${testSend ? "test-send" : "dry-run"}] 跳过操作日志写入。`);
      return;
    }
    try {
      logger.append({
        executedAt: new Date().toISOString(),
        taskName: "不出单通知",
        targetSheet: "飞书机器人",
        operationType: doSend ? "notify:send" : "dry-run",
        dataSource: OWNER_DATA_SOURCE_LABEL,
        dateRange: `${dates.sevenDaysAgo}~${dates.yesterday}`,
        fetchedCount,
        writtenCount: sentCount,
        updatedCount: 0,
        skippedCount,
        failedCount: status === "failed" ? 1 : 0,
        status,
        errorMessage,
        durationSeconds: Number(((Date.now() - startedAt) / 1000).toFixed(3)),
        runId,
        environment: "server",
        remark:
          `CODEX执行：不出单产品飞书通报` +
          `，发送=${doSend}` +
          `，商品总数=${fetchedCount}` +
          `，消息条数=${sentCount}` +
          (errorMessage ? `，失败原因=${errorMessage}` : ""),
      });
    } catch (logError) {
      console.log(`记录操作日志失败: ${logError instanceof Error ? logError.message : String(logError)}`);
    }
  }
}

if (require.main === module) {
  main().catch((e) => {
    console.log(`[致命错误] ${getErrorMessage(e)}`);
    process.exitCode = 1;
  });
}
