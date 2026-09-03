/**
 * noOrderInventoryRule.ts - 不出单通报库存规则（纯函数模块）
 *
 * 业务口径（2026-07-13 定稿）：
 *   WFS 可售 = 0 且 非WFS 可售 <= 1 → 不进入不出单通报
 *   其余情况（WFS 可售 > 0；或 WFS = 0 且非WFS > 1）→ 保留原不出单判断
 *
 * 字段定义（领星 walmart/list 返回）：
 *   wfs_available_quantity  WFS 可售库存
 *   available_quantity      非 WFS / 自发货可售库存
 *   inbound_stock           在途或待入库参考（API 返回时才透传）
 *   warehouse_stock         仓库库存参考（API 返回时才透传）
 *
 * 本模块不依赖任何外部 IO，供 noOrderNotify.ts（本地版/生产 feishuNotify 版）与单元测试共用。
 */

/**
 * 库存值安全转换：null / undefined / 空字符串 / 非数字 一律按 0 处理，禁止产生 NaN。
 */
export function toSafeQty(value: unknown): number {
  if (value === null || value === undefined) return 0;
  if (typeof value === "string" && value.trim() === "") return 0;
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

export interface InventorySnapshot {
  /** WFS 可售库存 */
  wfsAvailableQty: number;
  /** 非 WFS / 自发货可售库存 */
  nonWfsAvailableQty: number;
  /** 总可售 = wfsAvailableQty + nonWfsAvailableQty（口径与旧 inventory 字段一致） */
  totalAvailableQty: number;
  /** 在途/待入库参考；仅在 API 确实返回该字段时存在 */
  inboundQty?: number;
  /** 仓库库存参考；仅在 API 确实返回该字段时存在 */
  warehouseQty?: number;
}

/** 从领星商品列表原始行构建库存快照（所有值经 toSafeQty，禁止 NaN） */
export function buildInventorySnapshot(raw: Record<string, unknown>): InventorySnapshot {
  const wfsAvailableQty = toSafeQty(raw.wfs_available_quantity);
  const nonWfsAvailableQty = toSafeQty(raw.available_quantity);
  const snapshot: InventorySnapshot = {
    wfsAvailableQty,
    nonWfsAvailableQty,
    totalAvailableQty: wfsAvailableQty + nonWfsAvailableQty,
  };
  // 仅在 API 确实返回时透传，不做无数据支撑的默认值
  if (raw.inbound_stock !== undefined && raw.inbound_stock !== null) {
    snapshot.inboundQty = toSafeQty(raw.inbound_stock);
  }
  if (raw.warehouse_stock !== undefined && raw.warehouse_stock !== null) {
    snapshot.warehouseQty = toSafeQty(raw.warehouse_stock);
  }
  return snapshot;
}

/**
 * 核心过滤：是否进入不出单通报。
 * 返回 false = 明确排除（WFS 可售为 0 且非 WFS 可售 <= 1）；
 * 返回 true  = 不排除，继续走原有"总可售 > 0 且近 3/5/7 天没出单"判断。
 */
export function shouldIncludeInNoOrderNotify(product: {
  wfsAvailableQty: number;
  nonWfsAvailableQty: number;
}): boolean {
  if (product.wfsAvailableQty === 0 && product.nonWfsAvailableQty <= 1) {
    return false;
  }
  return true;
}

/**
 * 近 3/5/7 天互斥分类（口径不变，从 noOrderNotify.ts 原地逻辑提取）：
 * 优先级 7 > 5 > 3，一个产品只出现在一个分组；近 3 天有出单返回 null。
 */
export function classifyNoOrderGroup(sales: {
  orders7: number;
  orders5: number;
  orders3: number;
}): 7 | 5 | 3 | null {
  if (sales.orders7 === 0) return 7;
  if (sales.orders5 === 0) return 5;
  if (sales.orders3 === 0) return 3;
  return null;
}

/*
 * ── 预留：新品待入库通报 ────────────────────────────────────────────
 * 排查结论（2026-07-13）：生命周期=新品期 且 WFS 可售=0 且 inbound_stock>0
 * 的商品当前命中数量为 0，本次不实现"新品待入库"通报、不新增数据库查询。
 * 未来若需要，按以下签名在此实现纯函数，并配套命中数据验证后再接入：
 *
 *   export function isNewProductAwaitingInbound(product: {
 *     lifecycleStage: string | null;   // 读 dim_product_business_state.lifecycle_stage
 *     wfsAvailableQty: number;
 *     inboundQty?: number;
 *   }): boolean
 */
