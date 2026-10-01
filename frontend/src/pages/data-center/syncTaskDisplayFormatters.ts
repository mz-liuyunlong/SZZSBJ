const pad2 = (value: number) => String(value).padStart(2, "0");
const CHINA_UTC_OFFSET_HOURS = 8;
const toChinaHour = (hour: number) => (hour + CHINA_UTC_OFFSET_HOURS) % 24;

export type SyncTaskSchedulePreset = "30m" | "1h" | "2h" | "daily_fixed";

const supportedBackfillDays = new Set([1, 2, 3, 7, 14]);

export const normalizeSyncTaskBackfillDays = (
  value: number | null | undefined,
  fallback: number | undefined,
) => (value !== null && value !== undefined && supportedBackfillDays.has(value) ? value : fallback);

export const parseSyncTaskSchedule = (value?: string | null): {
  preset: SyncTaskSchedulePreset;
  fixedRunTimes: string[];
} | null => {
  const cron = value?.trim();
  if (!cron) return null;
  if (cron === "*/30 * * * *") return { preset: "30m", fixedRunTimes: [] };
  if (cron === "0 * * * *") return { preset: "1h", fixedRunTimes: [] };
  if (cron === "0 */2 * * *") return { preset: "2h", fixedRunTimes: [] };

  const match = cron.match(/^(\d{1,2}) (\d{1,2}(?:,\d{1,2})*) \* \* \*$/);
  if (!match) return null;
  const minute = Number(match[1]);
  const hours = match[2].split(",").map(Number);
  if (minute > 59 || hours.some((hour) => hour > 23)) return null;

  return {
    preset: "daily_fixed",
    fixedRunTimes: hours
      .map(toChinaHour)
      .sort((left, right) => left - right)
      .map((hour) => `${pad2(hour)}:${pad2(minute)}`),
  };
};

export const formatSyncTaskDateTime = (value?: string | null) => {
  if (!value) return null;

  const date = new Date(value);
  if (!Number.isNaN(date.getTime())) {
    return [
      `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`,
      `${pad2(date.getHours())}:${pad2(date.getMinutes())}`,
    ].join(" ");
  }

  return value
    .replace("T", " ")
    .replace(/\.\d+/, "")
    .replace(/([+-]\d{2}:?\d{2}|Z)$/i, "")
    .slice(0, 16)
    .trim();
};

const weekDayLabels: Record<string, string> = {
  "0": "周日",
  "1": "周一",
  "2": "周二",
  "3": "周三",
  "4": "周四",
  "5": "周五",
  "6": "周六",
};

export const formatSyncTaskFrequency = (value?: string | null) => {
  if (!value || value === "-") return "-";

  const cron = value.trim();

  if (cron === "*/30 * * * *") return "每 30 分钟";
  if (cron === "0 * * * *") return "每 1 小时";
  if (cron === "0 */2 * * *") return "每 2 小时";

  const parts = cron.split(/\s+/);
  if (parts.length !== 5) return cron;

  const [minute, hour, , , weekDay] = parts;
  const isNumber = (text: string) => /^\d+$/.test(text);

  if (!isNumber(minute)) return cron;

  if (/^\d+(,\d+)*$/.test(hour)) {
    const times = hour
      .split(",")
      .map((item) => toChinaHour(Number(item)))
      .sort((left, right) => left - right)
      .map((localHour) => `${pad2(localHour)}:${pad2(Number(minute))}`)
      .join("、");

    if (weekDay === "*") return `每天 ${times}`;

    const days = weekDay
      .split(",")
      .map((item) => weekDayLabels[item] ?? item)
      .join("、");

    return `每周${days} ${times}`;
  }

  return cron;
};
