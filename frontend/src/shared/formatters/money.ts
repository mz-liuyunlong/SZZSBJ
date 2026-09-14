import { EMPTY_TEXT, toFiniteNumber } from "@/shared/formatters/number";

export interface MoneyFormatOptions {
  currency?: "USD" | "CNY" | "JPY" | "none" | string;
  locale?: string;
  emptyText?: string;
  minimumFractionDigits?: number;
  maximumFractionDigits?: number;
}

const currencySymbolMap: Record<string, string> = {
  USD: "$",
  CNY: "¥",
  JPY: "¥",
};

export function formatMoney(value: unknown, options: MoneyFormatOptions = {}) {
  const parsed = toFiniteNumber(value);
  if (parsed === undefined) return options.emptyText ?? EMPTY_TEXT;

  const currency = options.currency ?? "USD";

  if (currency === "none") {
    return new Intl.NumberFormat(options.locale ?? "en-US", {
      minimumFractionDigits: options.minimumFractionDigits ?? 2,
      maximumFractionDigits: options.maximumFractionDigits ?? 2,
    }).format(parsed);
  }

  try {
    return new Intl.NumberFormat(options.locale ?? "en-US", {
      style: "currency",
      currency,
      minimumFractionDigits: options.minimumFractionDigits ?? 2,
      maximumFractionDigits: options.maximumFractionDigits ?? 2,
    }).format(parsed);
  } catch {
    const symbol = currencySymbolMap[currency] ?? `${currency} `;
    return `${symbol}${parsed.toFixed(options.maximumFractionDigits ?? 2)}`;
  }
}

export function formatUsd(value: unknown, options: Omit<MoneyFormatOptions, "currency"> = {}) {
  return formatMoney(value, { ...options, currency: "USD" });
}

export function formatCny(value: unknown, options: Omit<MoneyFormatOptions, "currency"> = {}) {
  return formatMoney(value, { ...options, currency: "CNY", locale: options.locale ?? "zh-CN" });
}
