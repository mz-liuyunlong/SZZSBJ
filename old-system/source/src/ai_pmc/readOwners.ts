/**
 * src/ai_pmc/readOwners.ts
 * Phase 3 — 运营负责人映射
 *
 * ⚠️ 下游迁移（脱离飞书 <REDACTED_FEISHU_SHEET_ID>）：
 *   飞书 <REDACTED_FEISHU_SHEET_ID>（ItemID负责人表）已停止作为日常维护入口（产品管理 V1.2）。
 *   本模块改为直接从 MySQL 数据中台 `walmart_ai_data`.`dim_product` 读取负责人快照
 *   （`dim_product.owner`，由后台「产品管理」Tab 的"修改负责人"维护，是当前权威来源）。
 *   不再调用飞书 API 读取 <REDACTED_FEISHU_SHEET_ID>。
 *
 * 职责：
 *   - 从 MySQL `dim_product` 读取 (sku / item_id) → 运营负责人姓名
 *   - 从 config/ownerOpenIds.json 取运营负责人 open_id
 *   - 成功后写缓存 config/owners-cache.json（TTL 24h）
 *   - 读库失败且缓存未超 24h：用缓存兜底
 *   - 读库失败且缓存过期：返回空 Map（调用方降级为群汇总，不发个人提醒）
 */

process.env.TZ = 'Asia/Shanghai';

import 'dotenv/config';
import fs from 'fs';
import path from 'path';
import * as mysql from 'mysql2/promise';
import { logger } from './logger';

// ─────────────────────────────────────────────
// 常量
// ─────────────────────────────────────────────

const CACHE_PATH        = path.resolve(process.cwd(), 'config/owners-cache.json');
const OPEN_ID_PATH      = path.resolve(process.cwd(), 'config/ownerOpenIds.json');
const CACHE_TTL_MS      = 24 * 60 * 60 * 1000; // 24h

// 新品兜底：江梓博
export const FALLBACK_OPEN_ID = '<REDACTED_FEISHU_OPEN_ID>';
export const FALLBACK_NAME    = '江梓博';

function dbConfig() {
  return {
    host:     process.env.DB_HOST     ?? '127.0.0.1',
    port:     Number(process.env.DB_PORT ?? 3306),
    user:     process.env.DB_USER     ?? '',
    password: process.env.DB_PASSWORD ?? '',
    database: process.env.DB_NAME     ?? 'walmart_ai_data',
  };
}

// ─────────────────────────────────────────────
// 类型
// ─────────────────────────────────────────────

export interface OwnerInfo {
  name: string;
  openId: string; // '' 表示找不到 open_id，调用方应跳过个人提醒
}

/** ItemID → OwnerInfo */
export type OwnerMap = Map<string, OwnerInfo>;

interface CacheFile {
  savedAt: number; // timestamp ms
  entries: Array<{ itemId: string; name: string; openId: string }>;
}

// ─────────────────────────────────────────────
// 工具：读 ownerOpenIds.json
// ─────────────────────────────────────────────

function loadOpenIdJson(): Record<string, string> {
  try {
    const raw = fs.readFileSync(OPEN_ID_PATH, 'utf-8');
    return JSON.parse(raw) as Record<string, string>;
  } catch (e) {
    logger.warn(`[readOwners] 读 ownerOpenIds.json 失败: ${String(e)}`);
    return {};
  }
}

// ─────────────────────────────────────────────
// 工具：缓存读写
// ─────────────────────────────────────────────

function writeCache(map: OwnerMap): void {
  try {
    const dir = path.dirname(CACHE_PATH);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    const payload: CacheFile = {
      savedAt: Date.now(),
      entries: Array.from(map.entries()).map(([itemId, info]) => ({
        itemId,
        name: info.name,
        openId: info.openId,
      })),
    };
    fs.writeFileSync(CACHE_PATH, JSON.stringify(payload, null, 2), 'utf-8');
    logger.info(`[readOwners] 缓存写入成功，共 ${map.size} 条`);
  } catch (e) {
    logger.warn(`[readOwners] 缓存写入失败: ${String(e)}`);
  }
}

function readCache(): OwnerMap | null {
  try {
    if (!fs.existsSync(CACHE_PATH)) return null;
    const raw = fs.readFileSync(CACHE_PATH, 'utf-8');
    const payload = JSON.parse(raw) as CacheFile;
    if (Date.now() - payload.savedAt > CACHE_TTL_MS) {
      logger.warn('[readOwners] 缓存已超 24h，不使用');
      return null;
    }
    const map: OwnerMap = new Map(
      payload.entries.map(e => [e.itemId, { name: e.name, openId: e.openId }])
    );
    logger.info(`[readOwners] 用缓存兜底，共 ${map.size} 条（缓存时间：${new Date(payload.savedAt).toLocaleString('zh-CN')}）`);
    return map;
  } catch (e) {
    logger.warn(`[readOwners] 缓存读取失败: ${String(e)}`);
    return null;
  }
}

// ─────────────────────────────────────────────
// 主函数
// ─────────────────────────────────────────────

/**
 * 读取 ItemID/SKU → 运营负责人映射。
 * 数据源：MySQL `dim_product`（负责人快照，由产品管理页面维护）。
 * 失败时用缓存兜底；缓存也过期则返回空 Map（调用方降级）。
 */
export async function readOwners(): Promise<OwnerMap> {
  const openIds = loadOpenIdJson();

  let db: mysql.Connection | null = null;
  try {
    db = await mysql.createConnection(dbConfig());
    const [rows] = await db.query<mysql.RowDataPacket[]>(
      `SELECT sku, item_id, owner
       FROM dim_product
       WHERE platform = 'walmart'
         AND owner IS NOT NULL AND owner <> ''
         AND (COALESCE(sku, '') <> '' OR COALESCE(item_id, '') <> '')`,
    );

    if (!Array.isArray(rows) || rows.length === 0) {
      throw new Error('dim_product 负责人查询返回为空');
    }

    // 同一 sku/item_id 理论上只对应一个当前负责人快照（dim_product.owner），
    // 如果多个 store_id 下同一 item_id 出现不同负责人，后一行会覆盖前一行，
    // 与迁移前"按 item_id 去重取一个负责人"的行为保持一致（不引入新的多值语义）。
    const map: OwnerMap = new Map();
    const warned = new Set<string>();
    for (const row of rows) {
      const sku    = String(row.sku ?? '').trim();
      const itemId = String(row.item_id ?? '').trim();
      const name   = String(row.owner ?? '').trim();
      if (!name || (!sku && !itemId)) continue;

      const openId = openIds[name] ?? '';
      if (!openId && !warned.has(name)) {
        warned.add(name);
        logger.warn(`[readOwners] 运营负责人"${name}"在 ownerOpenIds.json 中找不到 open_id，将跳过个人提醒`);
      }
      const info: OwnerInfo = { name, openId };
      if (sku) map.set(sku, info);
      if (itemId) map.set(itemId, info);
    }

    logger.info(`[readOwners] 从 MySQL dim_product 读取成功，索引 ${map.size} 个键`);
    writeCache(map);
    return map;

  } catch (e) {
    logger.error('[readOwners] 从 MySQL dim_product 读取负责人失败，尝试缓存兜底', e);
    const cached = readCache();
    if (cached) return cached;

    logger.error('[readOwners] 缓存不可用，返回空 Map，个人提醒将全部降级为群汇总');
    return new Map();
  } finally {
    if (db) await db.end().catch(() => {});
  }
}

/**
 * 按 ItemID 查运营负责人。
 * 找不到时返回江梓博兜底，并记日志。
 */
export function lookupOwner(itemId: string, map: OwnerMap): OwnerInfo {
  const info = map.get(itemId);
  if (!info) {
    logger.warn(`[readOwners] ItemID=${itemId} 无运营负责人配置，兜底通知 ${FALLBACK_NAME}`);
    return { name: FALLBACK_NAME, openId: FALLBACK_OPEN_ID };
  }
  return info;
}
