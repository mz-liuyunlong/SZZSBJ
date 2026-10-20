
export async function fetchPagedOperationLogRows(
  filters: import("./operationLogTypes").OperationLogFilters,
  page: number,
  pageSize: number,
): Promise<{
  rows: OperationLogRow[];
  revisions: Record<string, number>;
  systemRecords: import("./operationLogTypes").OperationLogSystemRecord[];
  total: number;
  page: number;
  pageSize: number;
}> {
  const params = new URLSearchParams({
    start_date: filters.dateRange[0],
    end_date: filters.dateRange[1],
    page: String(page),
    page_size: String(pageSize),
    search_field: filters.searchField,
    keyword: filters.keyword.trim(),
    system_log: filters.systemLog,
    include_events: "true",
  });

  filters.owners.forEach((value) => params.append("owner", value));
  filters.stores.forEach((value) => params.append("store", value));
  filters.workTypes.forEach((value) => params.append("work_type", value));
  filters.batchValues?.forEach((value) => {
    if (value.trim()) params.append("batch_value", value.trim());
  });

  const response = await backendRequest<{
    rows: OperationLogRow[];
    revisions: Record<string, number>;
    systemRecords: import("./operationLogTypes").OperationLogSystemRecord[];
    total: number;
    page: number;
    pageSize: number;
  }>(`/api/operations/logs/rows/query?${params}`);

  return response.data;
}

import { backendRequest } from "@/api/backendApi";
import type { OperationLogRow, OperationLogLinkFormValues } from "./operationLogTypes";
export async function fetchOperationLogRows(startDate: string, endDate: string): Promise<{rows: OperationLogRow[]; revisions: Record<string, number>; systemRecords: import("./operationLogTypes").OperationLogSystemRecord[]}> {
  const response = await backendRequest<{rows: OperationLogRow[]; revisions: Record<string, number>; systemRecords: import("./operationLogTypes").OperationLogSystemRecord[]}>(`/api/operations/logs/rows?start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}`);
  return response.data;
}
export async function saveOperationLogRows(rows: OperationLogRow[], revisions: Record<string, number>, status: "draft" | "submitted") {
  const response = await backendRequest<{revisions: number[]}>("/api/operations/logs/manual/batch", {
    method: "PUT",
    body: JSON.stringify({rows: rows.map((row) => ({
      account: row.sourceAccountRef, day: row.date, store: row.storeId,
      item: row.productId, msku: row.msku ?? "",
      content: row.manualLog, work_type: row.workType,
      work_types: row.workTypes ?? [row.workType], observe_days: row.observeDays ?? null,
      status,
      revision: revisions[row.id] ?? 0,
    }))}),
  });
  return Object.fromEntries(rows.map((row, i) => [row.id, response.data.revisions[i]]));
}
export async function saveOperationLink(row: OperationLogRow, entryType: "keyword" | "ad", values: OperationLogLinkFormValues) {
  return backendRequest("/api/operations/logs/links", {
    method: "PUT",
    body: JSON.stringify({
      identity: {account: row.sourceAccountRef, day: row.date, store: row.storeId,
        item: row.productId, msku: row.msku ?? ""},
      entry_type: entryType, name: values.entryName, url: values.entryUrl, note: values.note,
    }),
  });
}

export interface ManualEntryDetail {
  id: string;
  sourceKind: string;
  createdByUserId: number | null;
  authorName: string;
  content: string;
  workType: string;
  status: string;
  updatedAt: string | null;
}
export async function fetchOperationLogDetail(row: OperationLogRow): Promise<{manual_entries: ManualEntryDetail[]}> {
  const query = new URLSearchParams({
    account: row.sourceAccountRef, day: row.date, store: row.storeId,
    item: row.productId, msku: row.msku,
  });
  const result = await backendRequest<{manual_entries: ManualEntryDetail[]}>(`/api/operations/logs?${query}`);
  return result.data;
}
