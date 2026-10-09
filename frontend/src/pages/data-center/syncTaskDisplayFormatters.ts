const pad2 = (value: number) => String(value).padStart(2, "0");
const CHINA_UTC_OFFSET_HOURS = 8;
const toChinaHour = (hour: number) => (hour + CHINA_UTC_OFFSET_HOURS) % 24;

export type SyncTaskSchedulePreset = "30m" | "1h" | "2h" | "daily_fixed";

const supportedBackfillDays = new Set([1, 2, 3, 5, 7, 10, 14, 30]);

export const normalizeSyncTaskBackfillDays = (
  value: number | null | undefined,
  fallback: number | undefined,
) =>
  value !== null && value !== undefined && supportedBackfillDays.has(value)
    ? value
    : fallback;

export const parseSyncTaskSchedule = (
  value?: string | null,
): {
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
  if (!cron) return "-";
  if (cron === "手动任务") return "手动任务";

  const parts = cron.split(/\s+/);
  if (parts.length !== 5) return cron;

  const [minute, hour, dayOfMonth, month, weekDay] = parts;
  const isEveryDay = dayOfMonth === "*" && month === "*";
  const isStep = (text: string) => /^\*\/\d+$/.test(text);
  const parseNumberList = (text: string, min: number, max: number) => {
    if (!/^\d+(,\d+)*$/.test(text)) return null;
    const values = text.split(",").map(Number);
    if (
      values.some((item) => !Number.isInteger(item) || item < min || item > max)
    ) {
      return null;
    }
    return Array.from(new Set(values)).sort((left, right) => left - right);
  };

  if (isStep(minute) && hour === "*" && isEveryDay && weekDay === "*") {
    return `每 ${minute.slice(2)} 分钟`;
  }

  const minutes = parseNumberList(minute, 0, 59);

  if (minutes && hour === "*" && isEveryDay && weekDay === "*") {
    if (minutes.length === 1 && minutes[0] === 0) return "每小时";
    return `每小时第 ${minutes.map(pad2).join("、")} 分钟`;
  }

  const hourStep = hour.match(/^\*\/(\d+)$/);
  if (minutes?.length === 1 && hourStep && isEveryDay && weekDay === "*") {
    return minutes[0] === 0
      ? `每 ${hourStep[1]} 小时`
      : `每 ${hourStep[1]} 小时第 ${pad2(minutes[0])} 分钟`;
  }

  const hours = parseNumberList(hour, 0, 23);
  if (minutes && hours && isEveryDay) {
    const times = hours
      .flatMap((item) =>
        minutes.map(
          (minuteValue) => `${pad2(toChinaHour(item))}:${pad2(minuteValue)}`,
        ),
      )
      .sort()
      .join("、");

    if (weekDay === "*") return `每天 ${times}`;

    const days = weekDay
      .split(",")
      .map((item) => weekDayLabels[item] ?? item)
      .join("、");

    return `每周${days} ${times}`;
  }

  if (!cron.includes("*")) return cron;

  return "高级计划";
};
