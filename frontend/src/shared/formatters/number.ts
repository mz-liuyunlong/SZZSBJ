export const EMPTY_TEXT = "-";

export function toFiniteNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;

  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }

  return undefined;
}

export interface NumberFormatOptions {
  locale?: string;
  emptyText?: string;
  minimumFractionDigits?: number;
  maximumFractionDigits?: number;
  useGrouping?: boolean;
}

export function formatNumber(value: unknown, options: NumberFormatOptions = {}) {
  const parsed = toFiniteNumber(value);
  if (parsed === undefined) return options.emptyText ?? EMPTY_TEXT;

  return new Intl.NumberFormat(options.locale ?? "en-US", {
    minimumFractionDigits: options.minimumFractionDigits,
    maximumFractionDigits: options.maximumFractionDigits ?? 2,
    useGrouping: options.useGrouping ?? true,
  }).format(parsed);
}

export function formatInteger(value: unknown, options: Omit<NumberFormatOptions, "minimumFractionDigits" | "maximumFractionDigits"> = {}) {
  return formatNumber(value, {
    ...options,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
}

export function formatCompactNumber(value: unknown, options: NumberFormatOptions = {}) {
  const parsed = toFiniteNumber(value);
  if (parsed === undefined) return options.emptyText ?? EMPTY_TEXT;

  return new Intl.NumberFormat(options.locale ?? "en-US", {
    notation: "compact",
    maximumFractionDigits: options.maximumFractionDigits ?? 1,
  }).format(parsed);
}
