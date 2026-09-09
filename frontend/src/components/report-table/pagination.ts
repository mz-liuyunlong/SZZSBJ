/** Shared page-size policy for dense report tables. */
export const REPORT_TABLE_DEFAULT_PAGE_SIZE = 50;
export const REPORT_TABLE_PAGE_SIZE_OPTIONS = ["50", "100", "200", "500", "1000"];
export const normalizeReportTablePageSize = (pageSize: number) =>
  Math.max(REPORT_TABLE_DEFAULT_PAGE_SIZE, pageSize);
