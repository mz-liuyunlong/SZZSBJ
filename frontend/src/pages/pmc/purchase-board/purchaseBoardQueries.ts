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
import type {
  PurchaseBoardFilters,
  PurchaseBoardSummaryFilter,
} from "@/pages/pmc/purchase-board/purchaseBoardTypes";

const filterKey = (filters: PurchaseBoardFilters) => buildPurchaseBoardFilterQuery(filters).toString();

export const purchaseBoardKeys = {
  all: ["pmc-purchase-board"] as const,
  list: (
    filters: PurchaseBoardFilters,
    page: number,
    pageSize: number,
    summaryFilter?: PurchaseBoardSummaryFilter,
    cardRequest = 0,
  ) => (
    ["pmc-purchase-board", "list", filterKey(filters), filters.sort, summaryFilter ?? "", cardRequest, page, pageSize] as const
  ),
  summary: (filters: PurchaseBoardFilters) => (
    ["pmc-purchase-board", "summary", filterKey(filters)] as const
  ),
  detail: (orderSn: string) => ["pmc-purchase-board", "detail", orderSn] as const,
  pendingPlans: (page: number, pageSize: number, overdueOnly: boolean) => (
    ["pmc-purchase-board", "pending-plans", page, pageSize, overdueOnly] as const
  ),
  owners: ["pmc-purchase-board", "owners"] as const,
  overdue: (filters: PurchaseBoardFilters, cardRequest: number) => (
    ["pmc-purchase-board", "purchase-overdue", filterKey(filters), cardRequest] as const
  ),
};

const OVERDUE_FETCH_PAGE_SIZE = 200;
const OVERDUE_FETCH_MAX_PAGES = 25; // 5,000 rows per source; far above real volumes.

export interface OverdueSourceCount {
  shown: number;
  total: number;
  truncated: boolean;
}

/** Every page of a paged source, sequentially, bounded (``truncated`` when the cap is hit). */
async function fetchAllPages<T>(
  fetchPage: (page: number) => Promise<{ rows: T[]; total: number }>,
): Promise<{ rows: T[]; total: number; truncated: boolean }> {
  const rows: T[] = [];
  let total = 0;
  for (let page = 1; page <= OVERDUE_FETCH_MAX_PAGES; page += 1) {
    const result = await fetchPage(page);
    total = result.total;
    rows.push(...result.rows);
    if (rows.length >= total || result.rows.length === 0) return { rows, total, truncated: false };
  }
  return { rows, total, truncated: rows.length < total };
}

/**
 * 待采购超时 card: S2-overdue purchase-order lines (board filters apply) and overdue
 * approved-but-unconverted plans, both complete, for one merged list in the board body.
 */
export function usePurchaseOverdueRows(filters: PurchaseBoardFilters, cardRequest: number, enabled: boolean) {
  return useQuery({
    queryKey: purchaseBoardKeys.overdue(filters, cardRequest),
    queryFn: async ({ signal }) => {
      let thresholdDays: number | null = null;
      const [orders, plans] = await Promise.all([
        fetchAllPages((page) => listPurchaseBoard(filters, page, OVERDUE_FETCH_PAGE_SIZE, signal, "purchase_overdue")),
        fetchAllPages(async (page) => {
          const result = await listPendingPurchasePlans(
            { page, pageSize: OVERDUE_FETCH_PAGE_SIZE, overdueOnly: true },
            signal,
          );
          thresholdDays = result.thresholdDays;
          return result;
        }),
      ]);
      const count = (source: { rows: unknown[]; total: number; truncated: boolean }): OverdueSourceCount => ({
        shown: source.rows.length,
        total: source.total,
        truncated: source.truncated,
      });
      return { orders, plans, thresholdDays, counts: { orders: count(orders), plans: count(plans) } };
    },
    staleTime: SERVER_STATE_STALE_TIME.list,
    enabled,
  });
}

export function usePurchaseBoardListQuery(
  filters: PurchaseBoardFilters,
  page: number,
  pageSize: number,
  summaryFilter?: PurchaseBoardSummaryFilter,
  cardRequest = 0,
) {
  return useQuery({
    queryKey: purchaseBoardKeys.list(filters, page, pageSize, summaryFilter, cardRequest),
    queryFn: ({ signal }) => listPurchaseBoard(filters, page, pageSize, signal, summaryFilter),
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
