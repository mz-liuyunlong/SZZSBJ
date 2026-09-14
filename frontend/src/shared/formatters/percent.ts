import { EMPTY_TEXT, toFiniteNumber } from "@/shared/formatters/number";

export interface PercentFormatOptions {
  emptyText?: string;
  minimumFractionDigits?: number;
  maximumFractionDigits?: number;
  ratio?: boolean;
}

export function formatPercent(value: unknown, options: PercentFormatOptions = {}) {
  const parsed = toFiniteNumber(value);
  if (parsed === undefined) return options.emptyText ?? EMPTY_TEXT;

  const percentValue = options.ratio ? parsed * 100 : parsed;

  return `${percentValue.toLocaleString("en-US", {
    minimumFractionDigits: options.minimumFractionDigits ?? 2,
    maximumFractionDigits: options.maximumFractionDigits ?? 2,
  })}%`;
}
