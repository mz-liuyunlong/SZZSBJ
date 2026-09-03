/**
 * src/ai_pmc/readOwners.ts
 * Phase 3 — 运营负责人映射
 *
 * 职责：
 *   - 从 ItemID负责人表 (JCZ6sry7Wh9snEtackqcCVnmnyg / <REDACTED_FEISHU_SHEET_ID>) 读取 ItemID → 运营负责人姓名
 *   - 从 config/ownerOpenIds.json 取运营负责人 open_id
 *   - 成功后写缓存 config/owners-cache.json（TTL 24h）
 *   - 读表失败且缓存未超 24h：用缓存兜底
 *   - 读表失败且缓存过期：返回空 Map（调用方降级为群汇总，不发个人提醒）
 */

process.env.TZ = 'Asia/Shanghai';

import fs from 'fs';
import path from 'path';
import { FeishuSheetWriter } from '../feishuSheetWriter';
import { logger } from './logger';

// ─────────────────────────────────────────────
// 常量
// ─────────────────────────────────────────────

const OWNER_TABLE_TOKEN = '<REDACTED_FEISHU_SPREADSHEET_TOKEN>';
const OWNER_SHEET_ID    = '<REDACTED_FEISHU_SHEET_ID>';
const CACHE_PATH        = path.resolve(process.cwd(), 'config/owners-cache.json');
const OPEN_ID_PATH      = path.resolve(process.cwd(), 'config/ownerOpenIds.json');
const CACHE_TTL_MS      = 24 * 60 * 60 * 1000; // 24h

// 新品兜底：江梓博
export const FALLBACK_OPEN_ID = '<REDACTED_FEISHU_OPEN_ID>';
export const FALLBACK_NAME    = '江梓博';

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
    logger.warn('[readOwners] 读 ownerOpenIds.json 失败，open_id 将全部为空', e);
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
    logger.warn('[readOwners] 缓存写入失败（不影响主流程）', e);
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
    logger.warn('[readOwners] 缓存读取失败', e);
    return null;
  }
}

// ─────────────────────────────────────────────
// 主函数
// ─────────────────────────────────────────────

/**
 * 读取 ItemID → 运营负责人映射。
 * 失败时用缓存兜底；缓存也过期则返回空 Map（调用方降级）。
 */
export async function readOwners(): Promise<OwnerMap> {
  const openIds = loadOpenIdJson();

  try {
    const writer = new FeishuSheetWriter(OWNER_TABLE_TOKEN, OWNER_SHEET_ID);
    // 读全表（第1行为表头，从第2行开始）
    // 假设列顺序：A=ItemID, B=运营负责人姓名（若列顺序不同，按实际调整）
    const rows: string[][] = await writer.readAll(); // 期望返回二维数组

    if (!Array.isArray(rows) || rows.length < 2) {
      throw new Error('负责人表返回数据为空或格式异常');
    }

    const map: OwnerMap = new Map();

    for (let i = 1; i < rows.length; i++) { // 跳过表头
      const row = rows[i];
      const itemId = (row[0] ?? '').toString().trim();
      const name   = (row[1] ?? '').toString().trim();
      if (!itemId || !name) continue;

      const openId = openIds[name] ?? '';
      if (!openId) {
        logger.warn(`[readOwners] 运营负责人"${name}"在 ownerOpenIds.json 中找不到 open_id，将跳过个人提醒`);
      }
      map.set(itemId, { name, openId });
    }

    logger.info(`[readOwners] 从飞书读取成功，共 ${map.size} 条`);
    writeCache(map);
    return map;

  } catch (e) {
    logger.error('[readOwners] 从飞书读取负责人表失败，尝试缓存兜底', e);
    const cached = readCache();
    if (cached) return cached;

    logger.error('[readOwners] 缓存不可用，返回空 Map，个人提醒将全部降级为群汇总');
    return new Map();
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
