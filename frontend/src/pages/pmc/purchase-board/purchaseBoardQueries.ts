/** TanStack Query hooks for the purchase board; keys are derived from committed filters only. */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { SERVER_STATE_STALE_TIME } from "@/api/queryClient";
import {
  buildPurchaseBoardFilterQuery,
  getPurchaseBoardOwnerOptions,
  getPurchaseBoardSummary,
  getPurchaseOrderDetail,
  listPendingPurchasePlans,
  listPurchaseBoard,
} from "@/pages/pmc/purchase-board/purchaseBoardApi";
import type { PurchaseBoardFilters } from "@/pages/pmc/purchase-board/purchaseBoardTypes";

const filterKey = (filters: PurchaseBoardFilters) => buildPurchaseBoardFilterQuery(filters).toString();

export const purchaseBoardKeys = {
  all: ["pmc-purchase-board"] as const,
  list: (filters: PurchaseBoardFilters, page: number, pageSize: number) => (
    ["pmc-purchase-board", "list", filterKey(filters), filters.sort, page, pageSize] as const
  ),
  summary: (filters: PurchaseBoardFilters) => (
    ["pmc-purchase-board", "summary", filterKey(filters)] as const
  ),
  detail: (orderSn: string) => ["pmc-purchase-board", "detail", orderSn] as const,
  pendingPlans: (page: number, pageSize: number, overdueOnly: boolean) => (
    ["pmc-purchase-board", "pending-plans", page, pageSize, overdueOnly] as const
  ),
  owners: ["pmc-purchase-board", "owners"] as const,
};

export function usePurchaseBoardListQuery(
  filters: PurchaseBoardFilters,
  page: number,
  pageSize: number,
) {
  return useQuery({
    queryKey: purchaseBoardKeys.list(filters, page, pageSize),
    queryFn: ({ signal }) => listPurchaseBoard(filters, page, pageSize, signal),
    staleTime: SERVER_STATE_STALE_TIME.list,
    placeholderData: keepPreviousData,
  });
}

export function usePurchaseBoardSummaryQuery(filters: PurchaseBoardFilters) {
  return useQuery({
    queryKey: purchaseBoardKeys.summary(filters),
    queryFn: ({ signal }) => getPurchaseBoardSummary(filters, signal),
    staleTime: SERVER_STATE_STALE_TIME.summary,
    placeholderData: keepPreviousData,
  });
}

export function usePurchaseOrderDetailQuery(orderSn: string | undefined) {
  return useQuery({
    queryKey: purchaseBoardKeys.detail(orderSn ?? "none"),
    queryFn: ({ signal }) => {
      if (!orderSn) throw new Error("PURCHASE_ORDER_SN_REQUIRED");
      return getPurchaseOrderDetail(orderSn, signal);
    },
    enabled: Boolean(orderSn),
    staleTime: SERVER_STATE_STALE_TIME.detail,
  });
}

export function usePendingPurchasePlansQuery(
  params: { page: number; pageSize: number; overdueOnly: boolean },
  enabled: boolean,
) {
  return useQuery({
    queryKey: purchaseBoardKeys.pendingPlans(params.page, params.pageSize, params.overdueOnly),
    queryFn: ({ signal }) => listPendingPurchasePlans(params, signal),
    staleTime: SERVER_STATE_STALE_TIME.list,
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function usePurchaseBoardOwnerOptionsQuery() {
  return useQuery({
    queryKey: purchaseBoardKeys.owners,
    queryFn: ({ signal }) => getPurchaseBoardOwnerOptions(signal),
    staleTime: SERVER_STATE_STALE_TIME.options,
  });
}
