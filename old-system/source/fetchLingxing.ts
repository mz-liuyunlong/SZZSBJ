/**
 * src/ai_pmc/fetchLingxing.ts
 * Phase 2 — 领星采购单拉取
 *
 * 职责：
 *   - 分页拉取 purchaseOrderList（length=100，间隔200ms）
 *   - 失败指数退避重试3次（1s/2s/4s），仍失败记日志跳过
 *   - 返回标准化 PurchaseOrder[]
 *   - 首次运行时打印原始字段，供人工确认 D0/店铺字段名（见文末 TODO 注释）
 *
 * 验收：输出真实采购单 ≥3 条，并在日志中打印 rawFieldsSnapshot 供确认
 */

process.env.TZ = 'Asia/Shanghai';

import { LingxingClient } from '../lingxingClient';
import { logger } from './logger';

// ─────────────────────────────────────────────
// 类型定义
// ─────────────────────────────────────────────

/** item_list 明细行（按文档字段映射） */
export interface PurchaseOrderItem {
  sku: string;
  msku: string[];
  product_name: string;
  quantity_real: number;   // 应入库数量
  quantity_entry: number;  // 已入库数量
  expect_arrive_time: string | null;
}

/** 标准化采购单 */
export interface PurchaseOrder {
  order_sn: string;
  status: number;
  status_text: string;
  auditor_time: string | null;      // 审批通过时间
  auditor_realname: string | null;
  order_time: string | null;        // 下单时间
  status_shipped: number | null;    // 到货状态 1=未到货；2=发货完成（终态DONE）
  status_shipped_text: string | null;
  create_time: string | null;
  update_time: string | null;
  ware_house_name: string | null;
  principal_uids: string[];

  // ── Phase 2 待确认字段 ──
  // 【D0】到仓/收货/入库时间 — 字段名待确认，取到后替换下面的 null
  arrival_time: string | null;      // TODO: 确认字段名后从 raw 映射
  // 【C列】店铺/卖家 — 字段名待确认
  shop_name: string | null;         // TODO: 确认字段名后从 raw 映射

  item_list: PurchaseOrderItem[];

  /** 原始响应（仅在 DEBUG_RAW=true 时保留，用于字段确认） */
  _raw?: Record<string, unknown>;
}

// ─────────────────────────────────────────────
// 内部工具：sleep / retry
// ─────────────────────────────────────────────

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

async function withRetry<T>(
  fn: () => Promise<T>,
  label: string,
  retries = 3,
  delays = [1000, 2000, 4000],
): Promise<T> {
  for (let i = 0; i <= retries; i++) {
    try {
      return await fn();
    } catch (err) {
      if (i === retries) {
        logger.error(`[fetchLingxing] ${label} 重试${retries}次仍失败，跳过本批`, err);
        throw err;
      }
      const wait = delays[i] ?? 4000;
      logger.warn(`[fetchLingxing] ${label} 第${i + 1}次失败，${wait}ms 后重试`, err);
      await sleep(wait);
    }
  }
  throw new Error('unreachable');
}

// ─────────────────────────────────────────────
// 字段映射：raw → PurchaseOrderItem
// ─────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapItem(raw: any): PurchaseOrderItem {
  return {
    sku: raw.sku ?? '',
    msku: Array.isArray(raw.msku) ? raw.msku : (raw.msku ? [raw.msku] : []),
    product_name: raw.product_name ?? raw.goods_name ?? '',
    quantity_real: Number(raw.quantity_real ?? raw.num ?? 0),
    quantity_entry: Number(raw.quantity_entry ?? raw.entry_num ?? 0),
    expect_arrive_time: raw.expect_arrive_time ?? raw.expect_time ?? null,
  };
}

// ─────────────────────────────────────────────
// 字段映射：raw → PurchaseOrder
//
// Phase 2 已确认字段（不再修改）：
//   D0 到仓时间   → warehouse_time
//   C列 店铺      → shop_name
//   终态 DONE     → status_shipped === 2
// ─────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapOrder(raw: any, keepRaw: boolean): PurchaseOrder {
  // ── 到仓时间（D0）：已确认字段 warehouse_time ──
  const arrival_time: string | null = raw.warehouse_time ?? null;

  // ── 店铺（C列）：已确认字段 shop_name ──
  const shop_name: string | null = raw.shop_name ?? null;

  return {
    order_sn: raw.order_sn ?? '',
    status: Number(raw.status ?? 0),
    status_text: raw.status_text ?? '',
    auditor_time: raw.auditor_time ?? null,
    auditor_realname: raw.auditor_realname ?? null,
    order_time: raw.order_time ?? null,
    status_shipped: raw.status_shipped != null ? Number(raw.status_shipped) : null,
    status_shipped_text: raw.status_shipped_text ?? null,
    create_time: raw.create_time ?? null,
    update_time: raw.update_time ?? null,
    ware_house_name: raw.ware_house_name ?? null,
    principal_uids: Array.isArray(raw.principal_uids) ? raw.principal_uids.map(String) : [],
    arrival_time,
    shop_name,
    item_list: Array.isArray(raw.item_list) ? raw.item_list.map(mapItem) : [],
    ...(keepRaw ? { _raw: raw } : {}),
  };
}

// ─────────────────────────────────────────────
// 主函数
// ─────────────────────────────────────────────

/**
 * 拉取全部采购单。
 * @param status  可选筛选状态（不传=全部）
 * @param maxOrders 测试用，限制最大条数（≤500，V01验收约束）
 */
export async function fetchPurchaseOrders(
  status?: number,
  maxOrders = 500,
): Promise<PurchaseOrder[]> {
  const client = new LingxingClient();
  const PAGE_SIZE = 100;
  const PAGE_INTERVAL = 200; // ms，P2-2

  const DEBUG_RAW = process.env.DEBUG_RAW === 'true';
  const results: PurchaseOrder[] = [];
  let offset = 0;
  let pageNum = 0;

  logger.info(`[fetchLingxing] 开始拉取采购单，status=${status ?? '全部'}，上限=${maxOrders}`);

  while (true) {
    pageNum++;
    const params: Record<string, unknown> = { offset, length: PAGE_SIZE };
    if (status !== undefined) params.status = status;

    let pageData: unknown[];
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const resp: any = await withRetry(
        () => client.post('/erp/sc/routing/data/local_inventory/purchaseOrderList', params),
        `page${pageNum}(offset=${offset})`,
      );

      // 兼容领星包装层：data / list / result / records 等常见结构
      const body = resp?.data ?? resp?.result ?? resp;
      pageData = Array.isArray(body)
        ? body
        : Array.isArray(body?.list)
          ? body.list
          : Array.isArray(body?.data)
            ? body.data
            : [];

      if (pageData.length === 0) {
        logger.info(`[fetchLingxing] 第${pageNum}页空，拉取结束，共${results.length}条`);
        break;
      }
    } catch {
      // withRetry 已记日志，这里直接终止本次拉取
      break;
    }

    // ── Phase 2 字段快照（第一页打印前3条原始字段，供人工确认） ──
    if (pageNum === 1) {
      const snapshot = pageData.slice(0, 3).map((r: any) => {
        const keys = Object.keys(r);
        // 只保留可能与 D0/店铺/发货 相关的字段
        const keywordsRe = /time|date|shop|store|seller|arrive|receipt|entry|warehouse|ship|dispatch/i;
        const relevant = keys.filter(k => keywordsRe.test(k));
        return { order_sn: r.order_sn, relevant_fields: relevant, sample: Object.fromEntries(relevant.map(k => [k, r[k]])) };
      });
      logger.info('[fetchLingxing] ★ rawFieldsSnapshot（Phase 2 字段确认）', JSON.stringify(snapshot, null, 2));
    }

    for (const raw of pageData) {
      if (results.length >= maxOrders) break;
      results.push(mapOrder(raw, DEBUG_RAW));
    }

    if (results.length >= maxOrders) {
      logger.warn(`[fetchLingxing] 已达上限 ${maxOrders} 条，停止拉取（V01验收约束）`);
      break;
    }

    offset += PAGE_SIZE;
    await sleep(PAGE_INTERVAL); // P2-2 限流
  }

  logger.info(`[fetchLingxing] 完成，共 ${results.length} 条采购单`);

  // ── Phase 2 验收输出：打印前3条标准化结果 ──
  logger.info('[fetchLingxing] 前3条标准化结果：', JSON.stringify(results.slice(0, 3), null, 2));

  return results;
}
