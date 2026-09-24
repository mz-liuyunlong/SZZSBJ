import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";

import { SERVER_STATE_STALE_TIME } from "@/api/queryClient";
import {
  fetchRefundItems,
  fetchRefundOverview,
  fetchRefundProductAnalysis,
} from "@/pages/aftersales/refundManagementApi";
import type { RefundFilters } from "@/pages/aftersales/refundManagementTypes";

const hasDateRange = (filters: RefundFilters) => Boolean(
  filters.dateRange?.[0] && filters.dateRange?.[1],
);

export const refundManagementKeys = {
  all: ["refund-management"] as const,
  overview: (filters: RefundFilters) => [
    "refund-management",
    "overview",
    filters,
  ] as const,
  productAnalysis: (filters: RefundFilters, selectedProductKey: string) => [
    "refund-management",
    "product-analysis",
    filters,
    selectedProductKey,
  ] as const,
  items: (
    filters: RefundFilters,
    page: number,
    pageSize: number,
    productKey: string,
  ) => [
    "refund-management",
    "items",
    filters,
    page,
    pageSize,
    productKey,
  ] as const,
};

export function useRefundOverviewQuery(filters: RefundFilters) {
  return useQuery({
    queryKey: refundManagementKeys.overview(filters),
    queryFn: () => fetchRefundOverview({ filters }),
    enabled: hasDateRange(filters),
    staleTime: SERVER_STATE_STALE_TIME.summary,
    placeholderData: keepPreviousData,
  });
}

export function useRefundProductAnalysisQuery(
  filters: RefundFilters,
  selectedProductKey: string,
) {
  return useQuery({
    queryKey: refundManagementKeys.productAnalysis(filters, selectedProductKey),
    queryFn: () => fetchRefundProductAnalysis({
      filters,
      selectedProductKey,
    }),
    enabled: hasDateRange(filters),
    staleTime: SERVER_STATE_STALE_TIME.summary,
    placeholderData: keepPreviousData,
  });
}

export function usePrefetchRefundProductAnalysis(filters: RefundFilters) {
  const queryClient = useQueryClient();

  return (selectedProductKey: string) => {
    const productKey = selectedProductKey.trim();
    if (!productKey || !hasDateRange(filters)) return;

    void queryClient.prefetchQuery({
      queryKey: refundManagementKeys.productAnalysis(filters, productKey),
      queryFn: () => fetchRefundProductAnalysis({
        filters,
        selectedProductKey: productKey,
      }),
      staleTime: SERVER_STATE_STALE_TIME.summary,
    });
  };
}

export function useRefundItemsQuery(
  filters: RefundFilters,
  page: number,
  pageSize: number,
  productKey = "",
) {
  return useQuery({
    queryKey: refundManagementKeys.items(filters, page, pageSize, productKey),
    queryFn: () => fetchRefundItems({
      filters,
      page,
      pageSize,
      productKey,
    }),
    enabled: hasDateRange(filters),
    staleTime: SERVER_STATE_STALE_TIME.list,
    placeholderData: keepPreviousData,
  });
}
