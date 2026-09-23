import { keepPreviousData, useQuery } from "@tanstack/react-query";

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
    queryFn: ({ signal }) => fetchRefundOverview({ filters, signal }),
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
    queryFn: ({ signal }) => fetchRefundProductAnalysis({
      filters,
      selectedProductKey,
      signal,
    }),
    enabled: hasDateRange(filters),
    staleTime: SERVER_STATE_STALE_TIME.summary,
    placeholderData: keepPreviousData,
  });
}

export function useRefundItemsQuery(
  filters: RefundFilters,
  page: number,
  pageSize: number,
  productKey = "",
) {
  return useQuery({
    queryKey: refundManagementKeys.items(filters, page, pageSize, productKey),
    queryFn: ({ signal }) => fetchRefundItems({
      filters,
      page,
      pageSize,
      productKey,
      signal,
    }),
    enabled: hasDateRange(filters),
    staleTime: SERVER_STATE_STALE_TIME.list,
    placeholderData: keepPreviousData,
  });
}
