/** Queries are keyed by committed filters; abort signals cancel superseded searches. */
import { useQuery } from "@tanstack/react-query";
import { domesticFilterQuery, getDomesticFilterOptions, getDomesticSummary, getDomesticTrace, listDomesticBatches } from "./domesticWarehouseApi";
import type { DomesticFilters } from "./domesticWarehouseTypes";

export function useDomesticBoard(filters: DomesticFilters, page: number, pageSize: number, scope: string, enabled = true) {
  const supported = !filters.businessStatus;
  const filterKey = supported ? domesticFilterQuery(filters).toString() : `unsupported:${filters.businessStatus}`;
  const list = useQuery({
    queryKey: ["domestic-board", scope, "list", filterKey, filters.sort, page, pageSize],
    queryFn: ({ signal }) => listDomesticBatches(filters, page, pageSize, signal), retry: false, enabled: enabled && supported,
  });
  const summary = useQuery({
    queryKey: ["domestic-board", scope, "summary", filterKey],
    queryFn: ({ signal }) => getDomesticSummary(filters, signal), retry: false, enabled: enabled && supported,
  });
  return { list, summary };
}
export function useDomesticTrace(id: string | undefined, scope: string) {
  return useQuery({
    queryKey: ["domestic-board", scope, "trace", id],
    queryFn: ({ signal }) => getDomesticTrace(id!, signal),
    enabled: Boolean(id), retry: false,
  });
}

/** Scope the option cache to the signed-in user; packing remains a structure-only page. */
export function useDomesticFilterOptions(scope: string, enabled: boolean) {
  return useQuery({
    queryKey: ["domestic-board", scope, "filter-options"],
    queryFn: ({ signal }) => getDomesticFilterOptions(signal),
    enabled, retry: false, staleTime: 60_000,
  });
}
