/**
 * wfsArrivalRule.ts - WFS到货提醒规则（纯函数模块）
 *
 * 设计：docs/wfs_arrival_notify_design.md v1.1 + 2026-07-14 R4升级追加
 * probe 实测格式（2026-07-14）：
 *   - to_*_time 为 epoch 毫秒字符串；未到达状态为 "0" → 必须解析为 null
 *   - 数量字段为字符串数字
 * 本模块零外部 IO，供 syncWfsShipments / buildArrivalEvents / arrivalNotify 与单测共用。
 */

import { toSafeQty } from "./noOrderInventoryRule";

const CST_TIMEZONE = "Asia/Shanghai";

// ── 时间解析 ─────────────────────────────────────────────────────────

/** epoch 毫秒/秒 → 上海时区 "YYYY-MM-DD HH:mm:ss"；"0"/空/非法 → null */
export function parseEpochToCstDateTime(value: unknown): string | null {
  const s = String(value ?? "").trim();
  if (!s || s === "0") return null;
  let ms: number;
  if (/^\d{13}$/.test(s)) ms = Number(s);
  else if (/^\d{10}$/.test(s)) ms = Number(s) * 1000;
  else if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(s)) return s; // datetime 字符串直接透传
  else return null;
  const d = new Date(ms);
  if (!Number.isFinite(d.getTime())) return null;
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: CST_TIMEZONE,
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).formatToParts(d);
  const get = (t: string): string => parts.find((p) => p.type === t)?.value ?? "00";
  const hour = get("hour") === "24" ? "00" : get("hour");
  return `${get("year")}-${get("month")}-${get("day")} ${hour}:${get("minute")}:${get("second")}`;
}

/** "YYYY-MM-DD HH:mm:ss" datetime 字符串（API直接给的）校验透传；非法 → null */
export function parseApiDateTime(value: unknown): string | null {
  const s = String(value ?? "").trim();
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(s)) return s;
  return null;
}

// ── R1: 货件状态跃迁 ────────────────────────────────────────────────

export const WFS_STATUS = {
  PENDING: 0,
  AWAITING: 1,
  RECEIVING: 2,
  CLOSED: 3,
  CANCELLED: 4,
} as const;

export type ShipmentTransition = "receiving" | "closed";

/**
 * 比对 DB 旧状态与 API 新状态，返回应生成的事件（可能同时补 receiving+closed，
 * 如首见即 CLOSED 时只报 closed，不补 receiving——避免迟到噪音）。
 * prevStatus=null 表示首次入库。
 */
export function detectShipmentTransitions(
  prevStatus: number | null,
  nextStatus: number,
): ShipmentTransition[] {
  const events: ShipmentTransition[] = [];
  if (nextStatus === WFS_STATUS.RECEIVING && (prevStatus === null || prevStatus < WFS_STATUS.RECEIVING)) {
    events.push("receiving");
  }
  if (nextStatus === WFS_STATUS.CLOSED && (prevStatus === null || prevStatus < WFS_STATUS.CLOSED)) {
    events.push("closed");
  }
  return events; // CANCELLED 不通报，仅落库
}

// ── R2: 库存 0→非0（上架可售）────────────────────────────────────────

/** prevWfs=null 表示上一快照无该商品行（新品首次出现且>0 同样视为可售事件） */
export function detectStockFirstAvailable(prevWfs: number | null, curWfs: number): boolean {
  const cur = toSafeQty(curWfs);
  if (cur <= 0) return false;
  if (prevWfs === null) return true;
  return toSafeQty(prevWfs) === 0;
}

// ── R3/R4: 无广告判定（锚点=可售日 D，数据 T-2）─────────────────────

export interface NoAdsInput {
  /** 可售日 D（YYYY-MM-DD） */
  sellableDate: string;
  /** 当前广告 FACT 最新可用数据日（YYYY-MM-DD）；null=完全无数据 */
  latestAdDataDate: string | null;
  /** 可售日起至最新数据日的广告花费合计 */
  adSpendSum: number;
  /** 同窗口曝光合计 */
  impressionsSum: number;
  /** 升级事件是否已存在（一次性） */
  alreadyEscalated: boolean;
  /** 持续提醒上限（数据日），默认30 */
  maxRemindDays?: number;
  /**
   * 可售日起该商品在广告报表中的行数（2026-07-15 严格口径）。
   * 领星报表每天为已存在的广告组输出全量行（含0值行），因此：
   * 行数>0 = 广告已创建（即使0投放）→ 不扣绩效、不升级；
   * 行数=0 = 未创建广告 → 满足天数即升级（绩效口径）。
   * 缺省 0（兼容旧调用视为未创建）。
   */
  adRowCount?: number;
}

export interface NoAdsDecision {
  /** 是否已有广告（终止条件，出现后不再生成任何提醒） */
  resolved: boolean;
  /** 今日是否生成日常提醒（R3） */
  remind: boolean;
  /** 是否生成一次性升级通报（R4，第3个数据日仍无广告） */
  escalate: boolean;
  /** 已覆盖的无广告数据天数（可售日起，含可售日） */
  noAdsDays: number;
  /** 数据截至日（文案用） */
  dataThrough: string | null;
}

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function daysBetweenInclusive(start: string, end: string): number {
  const [sy, sm, sd] = start.split("-").map(Number);
  const [ey, em, ed] = end.split("-").map(Number);
  const ms = Date.UTC(ey, em - 1, ed) - Date.UTC(sy, sm - 1, sd);
  return Math.floor(ms / 86400000) + 1;
}

export function evaluateNoAds(input: NoAdsInput): NoAdsDecision {
  const maxDays = input.maxRemindDays ?? 30;
  const none: NoAdsDecision = { resolved: false, remind: false, escalate: false, noAdsDays: 0, dataThrough: input.latestAdDataDate };

  if (!ISO_DATE_RE.test(input.sellableDate)) return none; // 配置异常防御，不判定

  // 终止条件：已有广告（花费或曝光任一>0）
  if (toSafeQty(input.adSpendSum) > 0 || toSafeQty(input.impressionsSum) > 0) {
    return { ...none, resolved: true };
  }

  // 数据可用性护栏：广告数据必须至少覆盖可售日 D，否则"无广告"不成立
  if (!input.latestAdDataDate || !ISO_DATE_RE.test(input.latestAdDataDate) || input.latestAdDataDate < input.sellableDate) {
    return none;
  }

  const noAdsDays = daysBetweenInclusive(input.sellableDate, input.latestAdDataDate);
  const remind = noAdsDays <= maxDays;
  // 升级（绩效口径）仅针对"未创建广告"：报表有行=已创建，不升级（由R3日常提醒+R5/R6广告组静默覆盖）
  const adsCreated = toSafeQty(input.adRowCount) > 0;
  const escalate = noAdsDays >= 3 && !input.alreadyEscalated && !adsCreated;
  return { resolved: false, remind, escalate, noAdsDays, dataThrough: input.latestAdDataDate };
}

// ── 通报文案 ─────────────────────────────────────────────────────────

export interface ShipmentEventPayload {
  storeName: string;
  cargoCode: string;
  inboundOrderId: string;
  eventTime: string | null; // to_receive_time / to_closed_time（上海）
  goods: Array<{ msku: string; productName: string; declareNum: number; receivedNum: number; damagedQty: number; owner: string }>;
}

export function buildReceivingText(p: ShipmentEventPayload): string {
  const lines = [
    `【WFS到仓通报】货件开始接收`,
    `店铺：${p.storeName}`,
    `货件单号：${p.cargoCode}（入库单 ${p.inboundOrderId}）`,
    `开始接收时间：${p.eventTime ?? "未知"}`,
    `商品 ${p.goods.length} 项：`,
  ];
  for (const g of p.goods) {
    lines.push(`  MSKU：${g.msku} ${g.productName} 申报 ${g.declareNum} 负责人：${g.owner || "未匹配"}`);
  }
  return lines.join("\n");
}

export function buildClosedText(p: ShipmentEventPayload): string {
  const lines = [
    `【WFS到仓通报】货件接收完成`,
    `店铺：${p.storeName}`,
    `货件单号：${p.cargoCode}（入库单 ${p.inboundOrderId}）`,
    `完成时间：${p.eventTime ?? "未知"}`,
    `商品 ${p.goods.length} 项（申报/签收/损坏）：`,
  ];
  for (const g of p.goods) {
    const diff = g.receivedNum - g.declareNum;
    const flag = diff !== 0 || g.damagedQty > 0 ? " ⚠️差异" : "";
    lines.push(`  MSKU：${g.msku} ${g.declareNum}/${g.receivedNum}/${g.damagedQty}${flag} 负责人：${g.owner || "未匹配"}`);
  }
  return lines.join("\n");
}

export function buildStockOnlineText(p: {
  storeName: string; msku: string; productName: string; owner: string;
  sellableDate: string; wfsQty: number;
}): string {
  return [
    `【上架可售通报】WFS库存 0 → ${p.wfsQty}`,
    `店铺：${p.storeName}`,
    `MSKU：${p.msku} ${p.productName}`,
    `可售日期：${p.sellableDate}（库存快照口径，T-2）`,
    `负责人：${p.owner || "未匹配"}，请及时创建广告并检查售价/详情页`,
  ].join("\n");
}

export function buildNoAdsOwnerText(p: {
  storeName: string; msku: string; productName: string; owner: string;
  sellableDate: string; noAdsDays: number; dataThrough: string;
}): string {
  return [
    `【广告缺失提醒】上架已 ${p.noAdsDays} 天仍无广告`,
    `店铺：${p.storeName}`,
    `MSKU：${p.msku} ${p.productName}`,
    `可售日期：${p.sellableDate}，数据截至：${p.dataThrough}`,
    `该商品自可售起广告花费与曝光均为 0（未创建广告，或已创建未投放），请当日创建/启动广告；本提醒每天发送直到检测到投放`,
  ].join("\n");
}

export function buildEscalationText(p: {
  storeName: string; msku: string; productName: string; owner: string;
  sellableDate: string; noAdsDays: number; dataThrough: string;
}): string {
  return [
    `【广告缺失升级通报 · 绩效考核口径】`,
    `商品上架可售满 3 天仍未创建广告，按运营规范计入绩效考核`,
    `店铺：${p.storeName}`,
    `MSKU：${p.msku} ${p.productName}`,
    `负责人：${p.owner || "未匹配"}`,
    `可售日期：${p.sellableDate}，无广告天数：${p.noAdsDays}，数据截至：${p.dataThrough}`,
    `请负责人当日内创建广告并在群内回复处理进展`,
  ].join("\n");
}
