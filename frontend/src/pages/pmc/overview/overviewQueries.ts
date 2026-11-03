/** TanStack Query hooks for the overview board; keys derive from committed filters only. */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { SERVER_STATE_STALE_TIME } from "@/api/queryClient";
import {
  buildOverviewFilterQuery,
  getOverviewFilterOptions,
  getOverviewItem,
  getOverviewRules,
  getOverviewSummary,
  getOverviewWarehouses,
  listOverviewItems,
} from "@/pages/pmc/overview/overviewApi";
import type { OverviewFilters } from "@/pages/pmc/overview/overviewTypes";

export const overviewKeys = {
  summary: ["pmc-overview", "summary"] as const,
  items: (filters: OverviewFilters, page: number, pageSize: number) => (
    ["pmc-overview", "items", buildOverviewFilterQuery(filters).toString(), page, pageSize] as const
  ),
  item: (itemId: string) => ["pmc-overview", "item", itemId] as const,
  options: ["pmc-overview", "options"] as const,
  warehouses: ["pmc-overview", "warehouses"] as const,
  rules: ["pmc-overview", "rules"] as const,
};

export const useOverviewSummaryQuery = () => useQuery({
  queryKey: overviewKeys.summary,
  queryFn: ({ signal }) => getOverviewSummary(signal),
  staleTime: SERVER_STATE_STALE_TIME.summary,
});

export const useOverviewItemsQuery = (filters: OverviewFilters, page: number, pageSize: number) => useQuery({
  queryKey: overviewKeys.items(filters, page, pageSize),
  queryFn: ({ signal }) => listOverviewItems(filters, page, pageSize, signal),
  staleTime: SERVER_STATE_STALE_TIME.list,
  placeholderData: keepPreviousData,
});

export const useOverviewItemQuery = (itemId?: string) => useQuery({
  queryKey: overviewKeys.item(itemId ?? ""),
  queryFn: ({ signal }) => getOverviewItem(itemId ?? "", signal),
  enabled: Boolean(itemId),
  staleTime: SERVER_STATE_STALE_TIME.list,
});

export const useOverviewOptionsQuery = () => useQuery({
  queryKey: overviewKeys.options,
  queryFn: ({ signal }) => getOverviewFilterOptions(signal),
  staleTime: SERVER_STATE_STALE_TIME.summary,
});

export const useOverviewWarehousesQuery = (enabled: boolean) => useQuery({
  queryKey: overviewKeys.warehouses,
  queryFn: ({ signal }) => getOverviewWarehouses(signal),
  enabled,
  staleTime: SERVER_STATE_STALE_TIME.summary,
});

export const useOverviewRulesQuery = (enabled: boolean) => useQuery({
  queryKey: overviewKeys.rules,
  queryFn: ({ signal }) => getOverviewRules(signal),
  enabled,
  staleTime: SERVER_STATE_STALE_TIME.summary,
});
