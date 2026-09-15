import dayjs from "dayjs";
import "dayjs/locale/zh-cn";
import relativeTime from "dayjs/plugin/relativeTime";
import timezone from "dayjs/plugin/timezone";
import utc from "dayjs/plugin/utc";
import { EMPTY_TEXT } from "@/shared/formatters/number";

dayjs.extend(utc);
dayjs.extend(timezone);
dayjs.extend(relativeTime);
dayjs.locale("zh-cn");

export const BUSINESS_TIME_ZONE = "Asia/Shanghai";

export interface DateFormatOptions {
  format?: string;
  emptyText?: string;
  timezone?: string;
}

export interface RelativeDateFormatOptions extends Omit<DateFormatOptions, "format"> {
  now?: string | number | Date;
}

const hasExplicitTimezone = (value: string) => /(?:z|[+-]\d{2}:?\d{2})$/i.test(value);

function parseDate(value: unknown, timezoneName: string) {
  if (value === null || value === undefined || value === "") return undefined;

  const parsed = typeof value === "string" && !hasExplicitTimezone(value)
    ? dayjs.tz(value, timezoneName)
    : dayjs(value as string | number | Date).tz(timezoneName);

  return parsed.isValid() ? parsed : undefined;
}

export function formatDateTime(value: unknown, options: DateFormatOptions = {}) {
  const parsed = parseDate(value, options.timezone ?? BUSINESS_TIME_ZONE);
  if (!parsed) return options.emptyText ?? EMPTY_TEXT;
  return parsed.format(options.format ?? "YYYY-MM-DD HH:mm");
}

export function formatDateTimeSeconds(value: unknown, options: DateFormatOptions = {}) {
  return formatDateTime(value, {
    ...options,
    format: options.format ?? "YYYY-MM-DD HH:mm:ss",
  });
}

export function formatShortDateTime(value: unknown, options: DateFormatOptions = {}) {
  return formatDateTime(value, {
    ...options,
    format: options.format ?? "MM-DD HH:mm",
  });
}

export function formatDate(value: unknown, options: DateFormatOptions = {}) {
  return formatDateTime(value, {
    ...options,
    format: options.format ?? "YYYY-MM-DD",
  });
}

export function formatRelativeTime(value: unknown, options: RelativeDateFormatOptions = {}) {
  const timezoneName = options.timezone ?? BUSINESS_TIME_ZONE;
  const parsed = parseDate(value, timezoneName);
  if (!parsed) return options.emptyText ?? EMPTY_TEXT;

  const now = options.now === undefined
    ? dayjs().tz(timezoneName)
    : parseDate(options.now, timezoneName);
  if (!now) return options.emptyText ?? EMPTY_TEXT;

  return parsed.locale("zh-cn").from(now);
}
