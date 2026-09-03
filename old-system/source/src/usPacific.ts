/**
 * usPacific.ts — 美西时间(America/Los_Angeles)换算共享件（2026-08-18 需求方立规）
 * 规则（PROJECT_CONTEXT 长期口径）：全系统业务数据日界一律美西时间，自动含夏令时PDT/冬令时PST，
 *   禁止硬编码固定偏移。本件用 Intl 走 IANA tz 数据库，DST 切换自动正确。
 */
const FMT = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/Los_Angeles",
  year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
});

/** unix秒 → 美西 "YYYY-MM-DD HH:mm:ss" */
export function laDateTime(tsSec: number): string {
  const parts: Record<string, string> = {};
  for (const p of FMT.formatToParts(new Date(tsSec * 1000))) parts[p.type] = p.value;
  const hh = parts.hour === "24" ? "00" : parts.hour; // en-CA 个别环境午夜给 24
  return `${parts.year}-${parts.month}-${parts.day} ${hh}:${parts.minute}:${parts.second}`;
}
/** unix秒 → 美西日 "YYYY-MM-DD" */
export function laDate(tsSec: number): string {
  return laDateTime(tsSec).slice(0, 10);
}
/** 美西日历日 → 当日起止unix秒（DST感知：逐偏移试解并用 Intl 回验） */
export function laDayBounds(date: string): { startTs: number; endTs: number } {
  let startTs = 0;
  for (const offH of [7, 8]) { // PDT=UTC-7 / PST=UTC-8
    const cand = Date.parse(`${date}T00:00:00Z`) / 1000 + offH * 3600;
    if (laDate(cand) === date && laDateTime(cand).slice(11) === "00:00:00") { startTs = cand; break; }
  }
  if (!startTs) throw new Error(`laDayBounds 无法定位美西日界: ${date}`);
  // 当日长度可能为 23/24/25 小时（DST切换日），从次日 00:00 反推
  const next = new Date(Date.parse(`${date}T00:00:00Z`) + 86400000).toISOString().slice(0, 10);
  let endTs = startTs + 86400 - 1;
  for (const offH of [7, 8]) {
    const cand = Date.parse(`${next}T00:00:00Z`) / 1000 + offH * 3600;
    if (laDate(cand) === next && laDateTime(cand).slice(11) === "00:00:00") { endTs = cand - 1; break; }
  }
  return { startTs, endTs };
}
/** 当前美西日（offsetDays 偏移） */
export function laToday(offsetDays: number): string {
  return laDate(Math.floor(Date.now() / 1000) + offsetDays * 86400);
}
