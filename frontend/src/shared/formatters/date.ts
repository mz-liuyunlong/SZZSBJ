import dayjs from "dayjs";
import { EMPTY_TEXT } from "@/shared/formatters/number";

export interface DateFormatOptions {
  format?: string;
  emptyText?: string;
}

export function formatDateTime(value: unknown, options: DateFormatOptions = {}) {
  if (value === null || value === undefined || value === "") {
    return options.emptyText ?? EMPTY_TEXT;
  }

  const parsed = dayjs(value as string | number | Date);
  if (!parsed.isValid()) return options.emptyText ?? EMPTY_TEXT;

  return parsed.format(options.format ?? "YYYY-MM-DD HH:mm");
}

export function formatDate(value: unknown, options: DateFormatOptions = {}) {
  return formatDateTime(value, {
    ...options,
    format: options.format ?? "YYYY-MM-DD",
  });
}
