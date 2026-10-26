import type { SyncScheduleItem, SyncTaskRow } from "@/pages/data-center/syncTaskTypes";

const matches = (expression: string, value: number, min: number, max: number) => {
  if (expression === "*") return true;
  return expression.split(",").some((part) => {
    if (part.startsWith("*/")) {
      const step = Number(part.slice(2));
      return Number.isInteger(step) && step > 0 && (value - min) % step === 0;
    }
    if (part.includes("-")) {
      const [start, end] = part.split("-").map(Number);
      return Number.isInteger(start) && Number.isInteger(end)
        && start >= min && end <= max && value >= start && value <= end;
    }
    const numeric = Number(part);
    return Number.isInteger(numeric) && numeric === value && numeric >= min && numeric <= max;
  });
};

export function buildSyncScheduleViews(
  rows: SyncTaskRow[],
  now = new Date(),
): { day: SyncScheduleItem[]; week: SyncScheduleItem[] } {
  // Display dates in the system's China timezone, while Cron is persisted in UTC.
  const startChina = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(now);
  const chinaMidnight = Date.parse(`${startChina}T00:00:00+08:00`);
  const weekEnd = chinaMidnight + 7 * 86400000;
  const dayEnd = chinaMidnight + 86400000;
  const day: SyncScheduleItem[] = [];
  const week: SyncScheduleItem[] = [];
  for (const task of rows) {
    if (!task.autoSync || !task.scheduleCron) continue;
    const fields = task.scheduleCron.trim().split(/\s+/);
    if (fields.length !== 5) continue;
    const [minute, hour, dom, month, dow] = fields;
    // Every day can have many executions. Week view shows the first
    // scheduled execution for each day, rather than pretending it is a full run list.
    const shownDays = new Set<string>();
    for (let timestamp = chinaMidnight; timestamp < weekEnd; timestamp += 60000) {
      const instant = new Date(timestamp);
      const weekday = instant.getUTCDay();
      const weekdayValue = weekday === 0 ? 0 : weekday;
      const valid = matches(minute, instant.getUTCMinutes(), 0, 59)
        && matches(hour, instant.getUTCHours(), 0, 23)
        && matches(month, instant.getUTCMonth() + 1, 1, 12)
        && (dom === "*" || matches(dom, instant.getUTCDate(), 1, 31))
        && (dow === "*" || matches(dow, weekdayValue, 0, 7)
          || (weekday === 0 && matches(dow, 7, 0, 7)));
      if (!valid) continue;
      const chinaDay = new Date(timestamp + 8 * 3600000).toISOString().slice(0, 10);
      const item: SyncScheduleItem = {
        id: `${task.id}:${timestamp}`,
        time: instant.toISOString(),
        taskName: task.taskName,
        module: task.module,
        frequency: task.frequency,
        status: task.lastStatus,
        weekDay: `周${["日","一","二","三","四","五","六"][new Date(timestamp + 8 * 3600000).getUTCDay()]}`,
      };
      if (timestamp < dayEnd) day.push(item);
      if (!shownDays.has(chinaDay)) {
        week.push(item);
        shownDays.add(chinaDay);
      }
      if (day.length > 600) break;
    }
  }
  return {
    day: day.sort((a,b) => Date.parse(a.time) - Date.parse(b.time)),
    week: week.sort((a,b) => Date.parse(a.time) - Date.parse(b.time)),
  };
}
