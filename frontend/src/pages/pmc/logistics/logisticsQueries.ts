/** Queries and error text shared by the 物流 pages. */
import { useQuery } from "@tanstack/react-query";
import { BackendRequestError } from "@/api/backendApi";
import { getOptions } from "./logisticsApi";

export const logisticsKey = (scope: string, ...rest: unknown[]) => ["pmc-logistics", scope, ...rest];

/** Filter options, rule summary and source counts (one request per data day and user). */
export const useLogisticsOptions = (scope: string) =>
  useQuery({
    queryKey: logisticsKey(scope, "options"),
    queryFn: ({ signal }) => getOptions(signal),
    retry: false,
    staleTime: 60_000,
  });

export function logisticsError(error: unknown): string {
  if (error instanceof BackendRequestError) {
    if (error.code === "WFS_BOARD_SCHEMA_NOT_READY") return "WFS 数据库结构尚未更新，请先完成迁移后重试";
    if (error.status === 401) return "登录已失效，请重新登录";
    if (error.status === 403) return "没有页面权限或店铺数据范围";
    if (error.status === 404) return "物流接口未就绪，请重启本地后端（8010）并确认已加载最新代码";
  }
  return "物流数据请求失败，请重试";
}

export const PAGE_SIZE = 50;
