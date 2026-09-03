/**
 * dateUtil.ts - 统一北京时间解析与天数计算（P0-1 / P1-3 / P1-9）
 *
 * 全模块所有"距今天数""时间解析"必须走本文件，禁止其它文件自行 new Date 算天数。
 * 规则：
 *  - 领星返回的时间字符串一律按 Asia/Shanghai 解析；
 *  - "距今天数" = 北京时间日期差（向下取整到天）；
 *  - 空值口径：'' / null / undefined / '0000-00-00 00:00:00' 均视为空。
 */

const SHANGHAI_TZ = "Asia/Shanghai";
const MS_PER_DAY = 24 * 60 * 60 * 1000;

/** P1-9 空值口径：判定某时间字段是否"未发生" */
export function isEmptyTime(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  const s = String(value).trim();
  if (s === "") return true;
  if (s === "0000-00-00 00:00:00" || s === "0000-00-00") return true;
  return false;
}

/**
 * 将领星时间字符串按北京时间解析为「北京日历日」的 UTC 毫秒（当天 00:00 北京）。
 * 支持 "YYYY-MM-DD HH:mm:ss" / "YYYY-MM-DD" / "YYYY/MM/DD ..." / 纯数字时间戳。
 * 解析失败或空值返回 null。
 */
export function parseBJDateMs(value: unknown): number | null {
  if (isEmptyTime(value)) return null;
  const s = String(value).trim();

  // 纯数字 → 时间戳（秒或毫秒）
  if (/^\d{10}$/.test(s)) return floorToBJDay(Number(s) * 1000);
  if (/^\d{13}$/.test(s)) return floorToBJDay(Number(s));

  // 提取 年-月-日（领星时间本身即北京时间，直接取日期部分即可，无需时区换算）
  const m = s.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})/);
  if (!m) return null;
  const year = Number(m[1]);
  const month = Number(m[2]);
  const day = Number(m[3]);
  if (!year || !month || !day) return null;
  // 用 UTC 构造"北京当天 00:00"对应的绝对时刻（北京=UTC+8）
  return Date.UTC(year, month - 1, day, 0, 0, 0) - 8 * 60 * 60 * 1000;
}

/** 将任意绝对毫秒时刻向下取整到"北京当天 00:00"的绝对毫秒 */
function floorToBJDay(absMs: number): number {
  const bjMs = absMs + 8 * 60 * 60 * 1000; // 平移到北京挂钟
  const dayIndex = Math.floor(bjMs / MS_PER_DAY);
  return dayIndex * MS_PER_DAY - 8 * 60 * 60 * 1000;
}

/** 北京"今天 00:00"的绝对毫秒 */
export function todayBJDateMs(now: Date = new Date()): number {
  return floorToBJDay(now.getTime());
}

/**
 * "距今天数"：北京日历日差（向下取整）。
 * 例：审批时间为今天 → 0；昨天 → 1。空值返回 null。
 */
export function daysSince(value: unknown, now: Date = new Date()): number | null {
  const dateMs = parseBJDateMs(value);
  if (dateMs === null) return null;
  const diff = todayBJDateMs(now) - dateMs;
  return Math.floor(diff / MS_PER_DAY);
}

/** 两个时间字符串之间的北京日历日差（a 相对 b，b 默认现在）。空值返回 null。 */
export function daysBetween(a: unknown, b: unknown): number | null {
  const aMs = parseBJDateMs(a);
  const bMs = parseBJDateMs(b);
  if (aMs === null || bMs === null) return null;
  return Math.floor((bMs - aMs) / MS_PER_DAY);
}

/** 当前北京时间字符串 "YYYY-MM-DD HH:mm" */
export function nowBJString(now: Date = new Date()): string {
  return formatBJ(now, false);
}

/** 当前北京日期字符串 "YYYY-MM-DD" */
export function todayBJString(now: Date = new Date()): string {
  return formatBJ(now, false).slice(0, 10);
}

/** 格式化为北京时间字符串；withSeconds=true 带秒 */
export function formatBJ(d: Date, withSeconds = false): string {
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: SHANGHAI_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "00";
  const base = `${get("year")}-${get("month")}-${get("day")} ${get("hour")}:${get("minute")}`;
  return withSeconds ? `${base}:${get("second")}` : base;
}
