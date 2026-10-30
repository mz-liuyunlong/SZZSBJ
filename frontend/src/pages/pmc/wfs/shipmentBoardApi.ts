import { backendRequest, BackendRequestError } from "@/api/backendApi";
import type {
  BoardFreshness,
  ProductBoardRow,
  ShipmentBoardDetail,
  ShipmentBoardFilters,
  ShipmentBoardRow,
  ShipmentBoardSummary,
} from "./shipmentBoardTypes";

export const boardPrefix = "/api/pmc/wfs/shipment-board";

const query = (f: ShipmentBoardFilters) =>
  new URLSearchParams({
    keyword: f.keyword,
    keyword_field: f.keyword_field,
    only_test: String(f.only_test),
    ...(f.store_id ? { store_id: f.store_id } : {}),
    ...(f.status !== undefined && f.status !== null ? { status: String(f.status) } : {}),
    ...(f.sync ? { sync: f.sync } : {}),
  });

export const listShipments = (f: ShipmentBoardFilters, page: number, size: number, signal?: AbortSignal) =>
  backendRequest<{ items: ShipmentBoardRow[]; total: number; data_asof: string; freshness: BoardFreshness }>(
    `${boardPrefix}/shipments?${query(f)}&page=${page}&page_size=${size}&sort_by=created_at&sort_dir=desc`,
    { signal },
  );

export const listProducts = (f: ShipmentBoardFilters, page: number, size: number, signal?: AbortSignal) =>
  backendRequest<{ items: ProductBoardRow[]; total: number; data_asof: string; freshness: BoardFreshness }>(
    `${boardPrefix}/products?${query(f)}&page=${page}&page_size=${size}`,
    { signal },
  );

export const shipmentSummary = (f: ShipmentBoardFilters, signal?: AbortSignal) =>
  backendRequest<ShipmentBoardSummary>(`${boardPrefix}/summary?${query(f)}`, { signal });

export const boardOptions = (signal?: AbortSignal) =>
  backendRequest<{ stores: { value: string; label: string }[] }>(`${boardPrefix}/filter-options`, { signal });

export const getShipment = (id: string, signal?: AbortSignal) =>
  backendRequest<ShipmentBoardDetail>(`${boardPrefix}/shipments/${encodeURIComponent(id)}`, { signal });

export function boardError(error: unknown, kind: "list" | "detail" = "list"): string {
  if (error instanceof BackendRequestError) {
    if (error.code === "WFS_SCHEMA_NOT_READY" || error.code === "WFS_BOARD_SCHEMA_NOT_READY") {
      return "WFS 数据库结构尚未更新，请先完成迁移后重试";
    }
    if (error.status === 401) return "登录已失效，请重新登录";
    if (error.status === 403) return "没有页面权限或店铺数据范围";
    if (error.status === 404) {
      if (kind === "detail") return "货件不存在或不在当前权限范围";
      if (error.code === "NON_JSON_RESPONSE" || error.code === "INVALID_API_ENVELOPE") {
        return "货件看板接口未就绪，请重启本地后端（8010）并确认已加载最新代码";
      }
      return "货件看板接口返回 404，请重启后端；若无货件数据应显示 0 张而非本错误";
    }
  }
  return "货件看板请求失败，请重试";
}
