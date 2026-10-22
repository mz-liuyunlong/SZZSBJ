/** A separate cache namespace prevents receipt data surviving the contract switch. */
import { useQuery } from "@tanstack/react-query";
import { domesticFilterQuery, getDomesticFilterOptions, getDomesticSummary, getDomesticTrace, listDomesticBatches } from "./domesticWarehouseApi";
import type { DomesticFilters } from "./domesticWarehouseTypes";

export function useDomesticBoard(filters: DomesticFilters, page: number, pageSize: number, scope: string, enabled = true) {
  const filterKey = domesticFilterQuery(filters).toString();
  const list = useQuery({
    queryKey: ["domestic-inbound-board", scope, "list", filterKey, filters.sort, page, pageSize],
    queryFn: ({ signal }) => listDomesticBatches(filters, page, pageSize, signal), retry: false, enabled,
  });
  const summary = useQuery({
    queryKey: ["domestic-inbound-board", scope, "summary", filterKey],
    queryFn: ({ signal }) => getDomesticSummary(filters, signal), retry: false, enabled,
  });
  return { list, summary };
}
export function useDomesticFilterOptions(warehouseIds: string[], scope: string, enabled = true) {
  return useQuery({
    queryKey: ["domestic-inbound-board", scope, "filter-options", [...warehouseIds].sort()],
    queryFn: ({ signal }) => getDomesticFilterOptions(warehouseIds, signal), enabled, retry: false,
  });
}
export function useDomesticTrace(id: string | undefined, scope: string, enabled = true) {
  return useQuery({
    queryKey: ["domestic-inbound-board", scope, "trace", id],
    queryFn: ({ signal }) => getDomesticTrace(id!, signal), enabled: enabled && Boolean(id), retry: false,
  });
}
