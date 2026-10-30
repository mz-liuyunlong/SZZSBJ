import { backendRequest, BackendRequestError } from "@/api/backendApi";
import type { ExceptionDetail, ExceptionFilters, ExceptionRow, ExceptionSummary } from "./exceptionCenterTypes";

export const exceptionPrefix = "/api/pmc/wfs/exception-center";

const query = (f: ExceptionFilters) => {
  const p = new URLSearchParams({
    keyword: f.keyword,
    keyword_field: f.keyword_field,
    only_test: String(f.only_test),
    due_soon: String(f.due_soon),
  });
  if (f.store_id) p.set("store_id", f.store_id);
  if (f.shipment_id) p.set("shipment_id", f.shipment_id);
  if (f.rule_family) p.set("rule_family", f.rule_family);
  if (f.status) p.set("status", f.status);
  if (f.severity) p.set("severity", f.severity);
  if (f.assignee_user_id) p.set("assignee_user_id", f.assignee_user_id);
  return p;
};

export const listCases = (f: ExceptionFilters, page: number, size: number, signal?: AbortSignal) =>
  backendRequest<{ items: ExceptionRow[]; total: number }>(
    `${exceptionPrefix}/cases?${query(f)}&page=${page}&page_size=${size}&sort_by=first_detected_at&sort_dir=desc`,
    { signal },
  );

export const exceptionSummary = (f: ExceptionFilters, signal?: AbortSignal) =>
  backendRequest<ExceptionSummary>(`${exceptionPrefix}/summary?${query(f)}`, { signal });

export const exceptionOptions = (signal?: AbortSignal) =>
  backendRequest<{ stores: { value: string; label: string }[]; assignees: string[] }>(
    `${exceptionPrefix}/filter-options`,
    { signal },
  );

export const getCase = (id: string, signal?: AbortSignal) =>
  backendRequest<ExceptionDetail>(`${exceptionPrefix}/cases/${id}`, { signal });

export const assignCase = (id: string, body: { assignee_user_id: string; expected_version: number }) =>
  backendRequest<ExceptionDetail>(`${exceptionPrefix}/cases/${id}/assign`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const postCaseEvent = (
  id: string,
  body: { action: string; expected_version: number; note?: string; reason?: string; platform_case_ref?: string },
) =>
  backendRequest<ExceptionDetail>(`${exceptionPrefix}/cases/${id}/events`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export function exceptionError(error: unknown, kind: "list" | "detail" = "list"): string {
  if (error instanceof BackendRequestError) {
    if (error.code === "WFS_EXCEPTION_SCHEMA_NOT_READY") {
      return "WFS 异常中心数据库结构尚未更新，请先完成本地迁移后重试";
    }
    if (error.status === 403) return "没有页面权限、动作权限或店铺数据范围";
    if (error.status === 404) {
      return kind === "detail" ? "异常案件不存在或不在当前权限范围" : "异常中心接口未就绪，请重启本地后端";
    }
    if (error.status === 409) return "案件已被他人更新，请关闭抽屉后重新打开";
  }
  return "异常中心请求失败，请重试";
}
