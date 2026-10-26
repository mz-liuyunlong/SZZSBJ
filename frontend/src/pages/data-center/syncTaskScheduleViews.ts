import type { SyncScheduleItem, SyncTaskRow } from "@/pages/data-center/syncTaskTypes";

const weekdayNames = ["日", "一", "二", "三", "四", "五", "六"];
const daySymbols: Record<string, number> = {
  sun: 0, mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6,
};
const monthSymbols: Record<string, number> = {
  jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6,
  jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12,
};

const parseNumber = (input: string, names: Record<string, number> = {}) => {
  const name = input.trim().toLowerCase();
  return names[name] ?? (/^\d+$/.test(name) ? Number(name) : Number.NaN);
};

function cronValues(
  expression: string, min: number, max: number,
  names: Record<string, number> = {},
): Set<number> | null {
  const result = new Set<number>();
  for (const part of expression.split(",")) {
    const [range, stepText] = part.split("/");
    if (!range || part.split("/").length > 2) return null;
    const step = stepText === undefined ? 1 : Number(stepText);
    if (!Number.isInteger(step) || step < 1) return null;
    let first: number, last: number;
    if (range === "*") {
      first = min; last = max;
    } else if (range.includes("-")) {
      const bounds = range.split("-");
      if (bounds.length !== 2) return null;
      first = parseNumber(bounds[0], names);
      last = parseNumber(bounds[1], names);
    } else {
      first = parseNumber(range, names);
      last = stepText ? max : first;
    }
    if (!Number.isInteger(first) || !Number.isInteger(last)
        || first < min || last > max || first > last) return null;
    for (let value = first; value <= last; value += step) result.add(value);
  }
  return result;
}

interface ScheduleViews {
  day: SyncScheduleItem[];
  week: SyncScheduleItem[];
  weekly: SyncScheduleItem[];
  dayTruncated: boolean;
  unsupported: string[];
}

export function buildSyncScheduleViews(
  rows: SyncTaskRow[],
  now = new Date(),
): ScheduleViews {
  // Scheduler uses UTC Cron; UI uses China (UTC+8) calendar boundaries.
  const chinaDate = new Date(now.getTime() + 8 * 3600000);
  const chinaMidnightUtc = Date.UTC(
    chinaDate.getUTCFullYear(), chinaDate.getUTCMonth(), chinaDate.getUTCDate(),
  ) - 8 * 3600000;
  const chinaWeekday = chinaDate.getUTCDay();
  const weekStart = chinaMidnightUtc - ((chinaWeekday + 6) % 7) * 86400000;
  const weekEnd = weekStart + 7 * 86400000;
  const dayEnd = chinaMidnightUtc + 86400000;
  const day: SyncScheduleItem[] = [];
  const week: SyncScheduleItem[] = [];
  const weekly: SyncScheduleItem[] = [];
  const unsupported: string[] = [];

  for (const task of rows) {
    if (!task.autoSync || !task.scheduleCron) continue;
    const parts = task.scheduleCron.trim().split(/\s+/);
    const minute = parts.length === 5 ? cronValues(parts[0], 0, 59) : null;
    const hour = parts.length === 5 ? cronValues(parts[1], 0, 23) : null;
    const dom = parts.length === 5 ? cronValues(parts[2], 1, 31) : null;
    const month = parts.length === 5 ? cronValues(parts[3], 1, 12, monthSymbols) : null;
    const dow = parts.length === 5 ? cronValues(parts[4], 0, 7, daySymbols) : null;
    if (!minute || !hour || !dom || !month || !dow) {
      unsupported.push(task.taskName);
      continue;
    }
    const isWeekly = parts[4] !== "*";
    const shownDays = new Set<string>();
    for (let timestamp = weekStart; timestamp < weekEnd; timestamp += 60000) {
      const date = new Date(timestamp);
      const weekday = date.getUTCDay();
      // Match scheduler behavior: day-of-month and day-of-week are AND conditions.
      if (!minute.has(date.getUTCMinutes()) || !hour.has(date.getUTCHours())
          || !month.has(date.getUTCMonth() + 1) || !dom.has(date.getUTCDate())
          || !(dow.has(weekday) || (weekday === 0 && dow.has(7)))) continue;
      const localDay = new Date(timestamp + 8 * 3600000);
      const key = localDay.toISOString().slice(0, 10);
      const item: SyncScheduleItem = {
        id: `${task.id}:${timestamp}`,
        time: date.toISOString(),
        taskName: task.taskName,
        module: task.module,
        frequency: task.frequency,
        status: task.lastStatus,
        weekDay: `周${weekdayNames[localDay.getUTCDay()]}`,
      };
      if (timestamp >= chinaMidnightUtc && timestamp < dayEnd) day.push(item);
      if (!shownDays.has(key)) {
        week.push(item);
        if (isWeekly) weekly.push(item);
        shownDays.add(key);
      }
    }
  }
  day.sort((a, b) => Date.parse(a.time) - Date.parse(b.time));
  week.sort((a, b) => Date.parse(a.time) - Date.parse(b.time));
  weekly.sort((a, b) => Date.parse(a.time) - Date.parse(b.time));
  const limit = 500;
  return {
    day: day.slice(0, limit),
    week,
    weekly,
    dayTruncated: day.length > limit,
    unsupported,
  };
}
