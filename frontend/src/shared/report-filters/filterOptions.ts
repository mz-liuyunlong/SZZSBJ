export interface ReportFilterOption {
  value: string;
  label: string;
  count?: number;
  color?: string | null;
  disabled?: boolean;
}

export const EMPTY_REPORT_FILTER_OPTIONS: ReportFilterOption[] = [];

export const selectedValuesFromFilterValue = (
  value: string | string[] | undefined,
): string[] => {
  if (Array.isArray(value)) return value.map((item) => item.trim()).filter(Boolean);
  if (value) return [value.trim()].filter(Boolean);
  return [];
};

export const normalizeReportFilterOptions = (
  options: ReportFilterOption[] | undefined,
): ReportFilterOption[] => {
  const byValue = new Map<string, ReportFilterOption>();

  for (const option of options ?? []) {
    const value = String(option.value ?? "").trim();
    if (!value || byValue.has(value)) continue;

    byValue.set(value, {
      ...option,
      value,
      label: String(option.label || value),
    });
  }

  return Array.from(byValue.values());
};

export const mergeSelectedFilterOptions = (
  selected: string[] | undefined,
  options: ReportFilterOption[] | undefined,
): ReportFilterOption[] => {
  const byValue = new Map<string, ReportFilterOption>();

  for (const option of normalizeReportFilterOptions(options)) {
    byValue.set(option.value, option);
  }

  for (const rawValue of selected ?? []) {
    const value = rawValue.trim();
    if (!value || byValue.has(value)) continue;

    byValue.set(value, {
      value,
      label: `${value}（已选）`,
      count: 0,
    });
  }

  return Array.from(byValue.values());
};

export const mergeSelectedFilterValues = (
  selected: string[],
  options: ReportFilterOption[],
): string[] => mergeSelectedFilterOptions(selected, options).map((option) => option.value);


export const toReportFilterOptions = (
  values: string[] | undefined,
): ReportFilterOption[] => normalizeReportFilterOptions(
  (values ?? []).map((value) => ({
    value,
    label: value,
  })),
);
