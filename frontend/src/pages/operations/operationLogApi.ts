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
      content: row.manualLog, work_type: row.workType, status,
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
